"""CLI wiring for the pre-authentication auth commands.

Covers what the core tests cannot: that each option actually reaches the core
function, that `--save` writes the profile, and that a core `ValueError` is
presented as a clean `error:` line rather than a traceback (`_HandledGroup`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli_anything.homeassistant import homeassistant_cli as cli_mod
from cli_anything.homeassistant.core import project
from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

pytest_plugins = ()

TOKENS = {
    "access_token": "acc-1",
    "refresh_token": "ref-1",
    "token_type": "Bearer",
    "expires_in": 1800,
    "client_id": "http://fake.local:8123/",
    "username": "agent",
    "handler": ["homeassistant", None],
    "steps": ["init"],
}


@pytest.fixture
def client(fake_client, monkeypatch):
    monkeypatch.setattr(cli_mod, "make_client", lambda ctx: fake_client)
    return fake_client


def _invoke(*args, json_out=True, config_path=None, input=None):
    """Invoke the ROOT group, not the subcommand.

    `--config` has to be passed as a real argument rather than seeded into
    `obj`: the root callback runs on every invocation and unconditionally
    reassigns `ctx.obj["config_path"]` (and url/token/…) from its own options,
    so anything preset in `obj` is overwritten before a subcommand sees it.
    Seeding it instead made the `--save` tests write to the developer's REAL
    `~/.config/cli-anything-homeassistant.json`.
    """
    full = ["--url", "http://fake.local:8123", "--token", "t"]
    if config_path is not None:
        full += ["--config", str(config_path)]
    if json_out:
        full.append("--json")
    return CliRunner().invoke(cli_mod.cli, full + list(args), input=input, obj={})


def _json(result):
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


# ───────────────────────────────────────────────────────────────── discovery


def test_providers(client):
    client.set_root(
        "GET", "/auth/providers", 200, {"providers": [{"type": "homeassistant", "id": None}]}
    )
    assert _json(_invoke("auth", "providers"))["providers"][0]["type"] == "homeassistant"


def test_oauth_metadata(client):
    client.set_root(
        "GET", "/.well-known/oauth-authorization-server", 200, {"token_endpoint": "/auth/token"}
    )
    assert _json(_invoke("auth", "oauth-metadata"))["token_endpoint"] == "/auth/token"


def test_providers_error_is_a_clean_line_not_a_traceback(client):
    client.set_root(
        "GET", "/auth/providers", 400, {"message": "Onboarding not finished", "code": "onboarding_required"}
    )
    result = _invoke("auth", "providers")
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "onboarding" in result.output


# ───────────────────────────────────────────────────────────────────── login


def test_login_forwards_every_option(client, monkeypatch):
    seen = {}

    def _login(_client, **kwargs):
        seen.update(kwargs)
        return dict(TOKENS)

    monkeypatch.setattr(cli_mod.auth_login_core, "login", _login)
    out = _json(
        _invoke(
            "auth", "login",
            "--username", "agent",
            "--password", "pw",
            "--mfa-code", "123456",
            "--client-id", "https://ha.example.com/",
            "--redirect-uri", "https://ha.example.com/cb",
            "--provider-type", "homeassistant",
            "--provider-id", "p1",
        )
    )
    assert seen == {
        "username": "agent",
        "password": "pw",
        "mfa_code": "123456",
        "client_id": "https://ha.example.com/",
        "redirect_uri": "https://ha.example.com/cb",
        "provider_type": "homeassistant",
        "provider_id": "p1",
    }
    assert out["access_token"] == "acc-1"


def test_login_prompts_for_a_hidden_password(client, monkeypatch):
    monkeypatch.setattr(cli_mod.auth_login_core, "login", lambda _c, **kw: {**TOKENS, "pw": kw["password"]})
    result = _invoke("auth", "login", "--username", "agent", input="secret\n")
    assert result.exit_code == 0, result.output
    prompt, _, body = result.output.partition("{")
    assert prompt.strip() == "Password:", "the prompt must not echo what was typed"
    assert "secret" not in prompt
    assert json.loads("{" + body)["pw"] == "secret"


def test_login_save_writes_the_access_token_to_the_profile(client, monkeypatch, tmp_path):
    monkeypatch.setattr(cli_mod.auth_login_core, "login", lambda _c, **kw: dict(TOKENS))
    cfg = tmp_path / "profile.json"
    out = _json(
        _invoke("auth", "login", "--username", "u", "--password", "p", "--save", config_path=cfg)
    )
    assert out["saved_to"] == str(cfg)
    assert json.loads(cfg.read_text())["token"] == "acc-1"


def test_login_save_keeps_mode_0600(client, monkeypatch, tmp_path):
    monkeypatch.setattr(cli_mod.auth_login_core, "login", lambda _c, **kw: dict(TOKENS))
    cfg = tmp_path / "profile.json"
    _invoke("auth", "login", "--username", "u", "--password", "p", "--save", config_path=cfg)
    assert oct(cfg.stat().st_mode)[-3:] == "600"


def test_login_without_save_writes_nothing(client, monkeypatch, tmp_path):
    monkeypatch.setattr(cli_mod.auth_login_core, "login", lambda _c, **kw: dict(TOKENS))
    cfg = tmp_path / "profile.json"
    _invoke("auth", "login", "--username", "u", "--password", "p", config_path=cfg)
    assert not cfg.exists()


def test_login_end_to_end_through_the_fake_wire(client):
    """No monkeypatching — the CLI drives the real core against queued
    `root_request` answers."""
    client.set_root("GET", "/auth/providers", 200, {"providers": [{"type": "homeassistant", "id": None}]})
    client.set_root("POST", "/auth/login_flow", 200, {"type": "form", "flow_id": "f1", "step_id": "init", "errors": {}})
    client.set_root("POST", "/auth/login_flow/f1", 200, {"type": "create_entry", "result": "code-1"})
    client.set_root("POST", "/auth/token", 200, {"access_token": "A", "refresh_token": "R", "expires_in": 1800})
    out = _json(_invoke("auth", "login", "--username", "agent", "--password", "pw"))
    assert out["access_token"] == "A" and out["refresh_token"] == "R"


def test_login_bad_password_is_a_clean_error(client):
    client.set_root("GET", "/auth/providers", 200, {"providers": [{"type": "homeassistant", "id": None}]})
    client.set_root("POST", "/auth/login_flow", 200, {"type": "form", "flow_id": "f1", "step_id": "init", "errors": {}})
    client.set_root("POST", "/auth/login_flow/f1", 200, {"type": "form", "errors": {"base": "invalid_auth"}})
    result = _invoke("auth", "login", "--username", "agent", "--password", "bad")
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "invalid_auth" in result.output


# ─────────────────────────────────────────────────────────────────── refresh


def test_refresh(client):
    client.set_root("POST", "/auth/token", 200, {"access_token": "new-acc", "expires_in": 1800})
    out = _json(_invoke("auth", "refresh", "--refresh-token", "R"))
    assert out["access_token"] == "new-acc"
    assert client.root_calls[-1]["form"]["grant_type"] == "refresh_token"


def test_refresh_save(client, tmp_path):
    client.set_root("POST", "/auth/token", 200, {"access_token": "new-acc", "expires_in": 1800})
    cfg = tmp_path / "p.json"
    out = _json(_invoke("auth", "refresh", "--refresh-token", "R", "--save", config_path=cfg))
    assert out["saved_to"] == str(cfg)
    assert json.loads(cfg.read_text())["token"] == "new-acc"


def test_refresh_client_id_is_forwarded(client):
    client.set_root("POST", "/auth/token", 200, {"access_token": "a"})
    _invoke("auth", "refresh", "--refresh-token", "R", "--client-id", "https://ha.example.com/")
    assert client.root_calls[-1]["form"]["client_id"] == "https://ha.example.com/"


# ──────────────────────────────────────────────────────────────────── revoke


def test_revoke_needs_confirmation(client):
    client.set_root("POST", "/auth/revoke", 200, "")
    result = _invoke("auth", "revoke", "--token", "R")
    assert result.exit_code != 0
    assert client.root_calls == []


def test_revoke_with_yes(client):
    client.set_root("POST", "/auth/revoke", 200, "")
    out = _json(_invoke("auth", "revoke", "--token", "R", "--yes"))
    assert out["revoked"] is True and out["verified"] is False


def test_revoke_verify(client):
    client.set_root("POST", "/auth/revoke", 200, "")
    client.set_root("POST", "/auth/token", 400, {"error": "invalid_grant"})
    out = _json(_invoke("auth", "revoke", "--token", "R", "--verify", "--yes"))
    assert out["verified"] is True


# ────────────────────────────────────────────────────── codes and link-user


def test_exchange_code(client):
    client.set_root("POST", "/auth/token", 200, {"access_token": "A"})
    out = _json(_invoke("auth", "exchange-code", "code-1"))
    assert out["access_token"] == "A"
    assert client.root_calls[-1]["form"]["code"] == "code-1"


def test_link_user(client):
    client.set_root("POST", "/auth/link_user", 200, {"message": "User linked"})
    assert _json(_invoke("auth", "link-user", "code-1"))["linked"] is True


# ────────────────────────────────────────────────────────────── login-flow


def test_login_flow_start(client):
    client.set_root("GET", "/auth/providers", 200, {"providers": [{"type": "homeassistant", "id": None}]})
    client.set_root("POST", "/auth/login_flow", 200, {"type": "form", "flow_id": "f1", "errors": {}})
    out = _json(_invoke("auth", "login-flow", "start"))
    assert out["flow_id"] == "f1"


def test_login_flow_start_link_user_type(client):
    client.set_root("GET", "/auth/providers", 200, {"providers": [{"type": "homeassistant", "id": None}]})
    client.set_root("POST", "/auth/login_flow", 200, {"type": "form", "flow_id": "f1", "errors": {}})
    _invoke("auth", "login-flow", "start", "--type", "link_user")
    assert client.root_calls[-1]["json"]["type"] == "link_user"


def test_login_flow_start_rejects_an_unknown_type(client):
    result = _invoke("auth", "login-flow", "start", "--type", "nonsense")
    assert result.exit_code != 0
    assert "nonsense" in result.output


def test_login_flow_step_parses_repeated_fields(client):
    client.set_root("POST", "/auth/login_flow/f1", 200, {"type": "create_entry", "result": "c"})
    out = _json(
        _invoke(
            "auth", "login-flow", "step", "f1",
            "--field", "username=agent", "--field", "password=p=w=d",
        )
    )
    assert out["result"] == "c"
    body = client.root_calls[-1]["json"]
    assert body["username"] == "agent"
    assert body["password"] == "p=w=d", "only the FIRST '=' separates name from value"


def test_login_flow_step_rejects_a_field_without_an_equals(client):
    result = _invoke("auth", "login-flow", "step", "f1", "--field", "username")
    assert result.exit_code != 0
    assert "NAME=VALUE" in result.output


def test_login_flow_abort(client):
    client.set_root("DELETE", "/auth/login_flow/f1", 200, {"message": "Flow aborted"})
    assert _json(_invoke("auth", "login-flow", "abort", "f1"))["aborted"] is True


# ──────────────────────────────────────────────────────────────── plumbing


@pytest.mark.parametrize(
    "args",
    [
        ("auth", "providers"),
        ("auth", "oauth-metadata"),
        ("auth", "login-flow", "abort", "f1"),
    ],
)
def test_human_output_is_not_json(client, args):
    client.set_root("GET", "/auth/providers", 200, {"providers": [{"type": "homeassistant", "id": None}]})
    client.set_root("GET", "/.well-known/oauth-authorization-server", 200, {"token_endpoint": "/auth/token"})
    client.set_root("DELETE", "/auth/login_flow/f1", 200, {"message": "Flow aborted"})
    result = _invoke(*args, json_out=False)
    assert result.exit_code == 0, result.output
    assert not result.output.strip().startswith("{")


def test_every_new_command_is_registered():
    names = set(cli_mod.cli.commands["auth"].commands)
    assert {
        "providers", "oauth-metadata", "login", "refresh", "revoke",
        "exchange-code", "link-user", "login-flow",
    } <= names
    assert {"start", "step", "abort"} == set(
        cli_mod.cli.commands["auth"].commands["login-flow"].commands
    )


def test_the_pre_auth_commands_are_defined_before_the_main_guard():
    """Anything defined after `if __name__ == '__main__': main()` never
    registers under `python -m`, which is the e2e fallback path."""
    source = Path(cli_mod.__file__).read_text()
    guard = source.index('if __name__ == "__main__"')
    for marker in ('@auth.command("login")', '@auth.group("login-flow")'):
        assert source.index(marker) < guard
