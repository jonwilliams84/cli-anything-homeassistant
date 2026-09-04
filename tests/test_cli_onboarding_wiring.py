"""CLI wiring for the `onboarding` group.

CliRunner + FakeClient, so the real Click decorators, prompts and `--save`
path are exercised without booting Home Assistant.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from cli_anything.homeassistant import homeassistant_cli as cli_mod
from cli_anything.homeassistant.core import onboarding

BASE = "/api/onboarding"


@pytest.fixture
def runner(monkeypatch, fake_client):
    monkeypatch.setattr(cli_mod, "make_client", lambda ctx: fake_client)
    return CliRunner()


def _invoke(runner, *args, json_out=True, input=None, config_path=None):
    # `--config` is a ROOT option and must go on argv: the group callback
    # rebuilds ctx.obj from the parsed options, so an `obj=` passed to
    # CliRunner is overwritten before any subcommand sees it. Getting this
    # wrong made `--save` write the developer's REAL connection profile.
    full = ["--url", "http://fake.local:8123"]
    if json_out:
        full.append("--json")
    if config_path:
        full += ["--config", str(config_path)]
    full += list(args)
    return runner.invoke(
        cli_mod.cli,
        full,
        input=input,
        obj={
            "url": "http://fake.local:8123",
            "token": None,
            "verify_ssl": False,
            "timeout": 5,
            "as_json": json_out,
            "config_path": config_path,
        },
    )


def steps_body(**done):
    return [{"step": s, "done": bool(done.get(s))} for s in onboarding.STEPS]


class TestReadCommands:
    def test_status(self, runner, fake_client):
        fake_client.set_root("GET", BASE, 200, steps_body(user=True))
        r = _invoke(runner, "onboarding", "status")
        assert r.exit_code == 0, r.output
        out = json.loads(r.output)
        assert out["onboarded"] is False
        assert out["done"] == ["user"]

    def test_installation_type(self, runner, fake_client):
        fake_client.set_root(
            "GET", f"{BASE}/installation_type", 200, {"installation_type": "Container"}
        )
        r = _invoke(runner, "onboarding", "installation-type")
        assert json.loads(r.output)["installation_type"] == "Container"

    def test_installation_type_401_is_a_clean_error_not_a_traceback(self, runner, fake_client):
        fake_client.set_root("GET", f"{BASE}/installation_type", 401, "401: Unauthorized")
        r = _invoke(runner, "onboarding", "installation-type")
        assert r.exit_code != 0
        assert "before onboarding STARTS" in r.output
        assert "Traceback" not in r.output


class TestCreateUserCli:
    def test_creates(self, runner, fake_client):
        fake_client.set_root("POST", f"{BASE}/users", 200, {"auth_code": "AC1"})
        r = _invoke(
            runner, "onboarding", "create-user",
            "--name", "Agent", "--username", "agent", "--password", "pw",
        )
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["auth_code"] == "AC1"

    def test_password_is_prompted_and_confirmed(self, runner, fake_client):
        fake_client.set_root("POST", f"{BASE}/users", 200, {"auth_code": "AC1"})
        r = _invoke(
            runner, "onboarding", "create-user", "--name", "A", "--username", "a",
            input="s3cret\ns3cret\n",
        )
        assert r.exit_code == 0, r.output
        assert fake_client.root_calls[-1]["json"]["password"] == "s3cret"

    def test_a_mistyped_confirmation_never_reaches_the_wire(self, runner, fake_client):
        r = _invoke(
            runner, "onboarding", "create-user", "--name", "A", "--username", "a",
            input="s3cret\nother\n",
        )
        assert r.exit_code != 0
        assert fake_client.root_calls == []

    def test_language_option(self, runner, fake_client):
        fake_client.set_root("POST", f"{BASE}/users", 200, {"auth_code": "AC1"})
        _invoke(
            runner, "onboarding", "create-user", "--name", "A", "--username", "a",
            "--password", "p", "--language", "de",
        )
        assert fake_client.root_calls[-1]["json"]["language"] == "de"


class TestStepCommands:
    def test_finish_step(self, runner, fake_client):
        fake_client.set_root("POST", f"{BASE}/analytics", 200, {})
        r = _invoke(runner, "onboarding", "finish-step", "analytics")
        assert json.loads(r.output)["ok"] is True

    def test_finish_step_rejects_a_step_it_does_not_own(self, runner, fake_client):
        r = _invoke(runner, "onboarding", "finish-step", "user")
        assert r.exit_code != 0
        assert fake_client.root_calls == []

    def test_core_config_500_exits_zero_because_the_step_is_done(self, runner, fake_client):
        """`ok: false, committed: true` is an OUTCOME. Exiting non-zero would
        invite the retry that HA answers with `already done`."""
        fake_client.set_root("POST", f"{BASE}/core_config", 500, "Server got itself in trouble")
        r = _invoke(runner, "onboarding", "finish-step", "core_config")
        assert r.exit_code == 0, r.output
        out = json.loads(r.output)
        assert out["ok"] is False and out["committed"] is True

    def test_finish_integration(self, runner, fake_client):
        fake_client.set_root("POST", f"{BASE}/integration", 200, {"auth_code": "AC2"})
        r = _invoke(runner, "onboarding", "finish-integration")
        assert json.loads(r.output)["auth_code"] == "AC2"


class TestProvisionCli:
    def prime(self, client):
        client.set_root("GET", BASE, 200, steps_body())
        client.set_root("POST", f"{BASE}/users", 200, {"auth_code": "AC1"})
        client.set_root(
            "POST", "/auth/token", 200,
            {"access_token": "ACCESS", "refresh_token": "REFRESH",
             "expires_in": 1800, "token_type": "Bearer"},
        )
        client.set_root("POST", f"{BASE}/analytics", 200, {})
        client.set_root("POST", f"{BASE}/core_config", 200, {})
        client.set_root("POST", f"{BASE}/integration", 200, {"auth_code": "AC2"})
        client.set_root("GET", BASE, 200, steps_body(**{s: True for s in onboarding.STEPS}))

    def test_provision(self, runner, fake_client):
        self.prime(fake_client)
        r = _invoke(
            runner, "onboarding", "provision",
            "--name", "Agent", "--username", "agent", "--password", "pw",
        )
        assert r.exit_code == 0, r.output
        out = json.loads(r.output)
        assert out["access_token"] == "ACCESS"
        assert out["onboarded"] is True

    def test_no_finish(self, runner, fake_client):
        self.prime(fake_client)
        r = _invoke(
            runner, "onboarding", "provision", "--name", "A", "--username", "a",
            "--password", "p", "--no-finish",
        )
        out = json.loads(r.output)
        assert out["onboarded"] is False
        assert "integration" in out["steps_skipped"]

    def test_save_writes_the_profile(self, runner, fake_client, tmp_path):
        self.prime(fake_client)
        profile = tmp_path / "profile.json"
        r = _invoke(
            runner, "onboarding", "provision", "--name", "A", "--username", "a",
            "--password", "p", "--save", config_path=str(profile),
        )
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["saved_to"] == str(profile)
        assert json.loads(profile.read_text())["token"] == "ACCESS"

    def test_an_already_owned_instance_is_a_clean_error(self, runner, fake_client):
        fake_client.set_root("GET", BASE, 200, steps_body(user=True))
        r = _invoke(
            runner, "onboarding", "provision", "--name", "A", "--username", "a",
            "--password", "p",
        )
        assert r.exit_code != 0
        assert "auth login" in r.output
        assert "Traceback" not in r.output
