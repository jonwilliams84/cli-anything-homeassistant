"""LIVE end-to-end tests for the pre-authentication auth API.

WHY THESE EXIST AND THE UNIT TESTS ARE NOT ENOUGH. The fakes in
`test_auth_login.py` were written from the same reading of Home Assistant's
source as the client, so they agree with the client whether or not that reading
is right. Everything asserted here is read back off a REAL Home Assistant over a
REAL socket: the two body encodings, the 200-with-errors password rejection, the
client_id pinning on the refresh grant, and the fact that the resulting token
actually authenticates.

The `hass_instance` fixture provisions user `agent` with password
`test-password`, so a genuine username/password login can be driven end to end.

ON THE ONE DELIBERATE BAD PASSWORD BELOW: Home Assistant counts failed logins
toward an IP ban, but `login_attempts_threshold` defaults to
`NO_LOGIN_ATTEMPT_THRESHOLD` (-1), which disables banning. One attempt is made,
never a loop.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

from cli_anything.homeassistant.core import auth_login, auth_tokens
from cli_anything.homeassistant.utils.homeassistant_backend import (
    HomeAssistantClient,
    HomeAssistantError,
)

USERNAME = "agent"
PASSWORD = "test-password"  # nosec: B105 - the fixture's own test credential


def _resolve_cli() -> list[str]:
    path = shutil.which("cli-anything-homeassistant")
    if path:
        return [path]
    return [sys.executable, "-m", "cli_anything.homeassistant.homeassistant_cli"]


@pytest.fixture
def anon_client(hass_instance) -> HomeAssistantClient:
    """A client with NO token — the situation these endpoints exist for."""
    return HomeAssistantClient(url=hass_instance["url"], token=None, timeout=30)


@pytest.fixture
def authed_client(hass_instance) -> HomeAssistantClient:
    return HomeAssistantClient(
        url=hass_instance["url"], token=hass_instance["token"], timeout=30
    )


# ─────────────────────────────────────────────────────────────── discovery


class TestDiscoveryLive:
    def test_oauth_metadata(self, anon_client):
        doc = auth_login.oauth_metadata(anon_client)
        assert doc["token_endpoint"] == "/auth/token"
        assert doc["revocation_endpoint"] == "/auth/revoke"
        assert "code" in doc["response_types_supported"]

    def test_providers_without_a_token(self, anon_client):
        providers = auth_login.list_providers(anon_client)["providers"]
        assert {"homeassistant"} <= {p["type"] for p in providers}

    def test_resolve_handler_matches_the_live_instance(self, anon_client):
        assert auth_login.resolve_handler(anon_client) == ["homeassistant", None]

    def test_an_unknown_provider_is_named_locally(self, anon_client):
        """Sent to HA an unknown handler is a bare 500 text/plain; resolving
        against /auth/providers first turns it into this."""
        with pytest.raises(ValueError, match="homeassistant"):
            auth_login.resolve_handler(anon_client, provider_type="not_a_provider")


# ─────────────────────────────────────────────────────────────── login flow


class TestLoginFlowLive:
    def test_start_returns_the_credential_schema(self, anon_client):
        step = auth_login.start_login_flow(anon_client)
        try:
            assert step["type"] == "form"
            names = {f["name"] for f in step["data_schema"]}
            assert names == {"username", "password"}
        finally:
            auth_login.abort_login_flow(anon_client, flow_id=step["flow_id"])

    def test_abort_then_abort_again(self, anon_client):
        step = auth_login.start_login_flow(anon_client)
        assert auth_login.abort_login_flow(anon_client, flow_id=step["flow_id"])["aborted"]
        with pytest.raises(HomeAssistantError, match="nothing to abort"):
            auth_login.abort_login_flow(anon_client, flow_id=step["flow_id"])

    def test_a_wrong_password_is_an_http_200_and_is_still_raised(self, anon_client):
        """THE CENTRAL TRAP, PROVEN LIVE. HA answers the rejected credential
        with status 200 — a client trusting the status reports success."""
        step = auth_login.start_login_flow(anon_client)
        status, body = anon_client.root_request(
            "POST",
            f"/auth/login_flow/{step['flow_id']}",
            json_payload={
                "client_id": auth_login.default_client_id(anon_client.base_url),
                "username": USERNAME,
                "password": "definitely-not-the-password",
            },
            send_auth=False,
        )
        assert status == 200, "measured: a rejected password is not an HTTP error"
        assert body["errors"]["base"] == "invalid_auth"

        with pytest.raises(HomeAssistantError, match="invalid_auth"):
            auth_login.login(
                anon_client, username=USERNAME, password="definitely-not-the-password"
            )

    def test_a_form_body_is_rejected_by_the_json_only_half(self, anon_client):
        """`/auth/login_flow` parses JSON only — the mirror image of
        `/auth/token`, which parses a form body only."""
        status, body = anon_client.root_request(
            "POST",
            "/auth/login_flow",
            form={
                "client_id": auth_login.default_client_id(anon_client.base_url),
                "handler": "homeassistant",
                "redirect_uri": auth_login.default_client_id(anon_client.base_url),
            },
            send_auth=False,
        )
        assert status == 400
        assert "Invalid JSON" in json.dumps(body)

    def test_an_unknown_handler_really_is_a_500(self, anon_client):
        """Documented as 404 'Invalid handler specified' in the view's own
        source; measured as a 500 with a text/plain body."""
        status, _ = anon_client.root_request(
            "POST",
            "/auth/login_flow",
            json_payload={
                "client_id": auth_login.default_client_id(anon_client.base_url),
                "handler": ["no_such_provider", None],
                "redirect_uri": auth_login.default_client_id(anon_client.base_url),
            },
            send_auth=False,
        )
        assert status == 500
        with pytest.raises(HomeAssistantError, match="UNKNOWN auth provider"):
            auth_login.start_login_flow(anon_client, handler=["no_such_provider", None])

    def test_manual_flow_produces_a_usable_code(self, anon_client):
        step = auth_login.start_login_flow(anon_client)
        done = auth_login.advance_login_flow(
            anon_client,
            flow_id=step["flow_id"],
            step_data={"username": USERNAME, "password": PASSWORD},
        )
        assert done["type"] == "create_entry"
        tokens = auth_login.exchange_code(anon_client, code=done["result"])
        assert tokens["access_token"]


# ────────────────────────────────────────────────────────────────── tokens


class TestLoginLive:
    def test_login_returns_a_token_that_actually_authenticates(self, anon_client):
        """The point of the whole feature: username + password in, a working
        credential out, starting from no token at all."""
        result = auth_login.login(anon_client, username=USERNAME, password=PASSWORD)
        assert result["token_type"] == "Bearer"
        assert result["expires_in"] > 0
        assert result["ha_auth_provider"] == "homeassistant"

        probe = HomeAssistantClient(url=anon_client.base_url, token=result["access_token"])
        assert probe.get("") == {"message": "API running."}
        assert auth_tokens.current_user(probe)["name"]

    def test_the_access_token_can_mint_a_long_lived_one(self, anon_client):
        """Composability with the commands that already existed: `auth login`
        bootstraps, `auth tokens create` makes it durable."""
        result = auth_login.login(anon_client, username=USERNAME, password=PASSWORD)
        probe = HomeAssistantClient(url=anon_client.base_url, token=result["access_token"])
        long_lived = auth_tokens.create_long_lived_access_token(
            probe, client_name="cli-anything-e2e-login", lifespan=1
        )
        durable = HomeAssistantClient(url=anon_client.base_url, token=long_lived)
        assert durable.get("") == {"message": "API running."}

    def test_a_code_is_single_use(self, anon_client):
        step = auth_login.start_login_flow(anon_client)
        done = auth_login.advance_login_flow(
            anon_client,
            flow_id=step["flow_id"],
            step_data={"username": USERNAME, "password": PASSWORD},
        )
        auth_login.exchange_code(anon_client, code=done["result"])
        with pytest.raises(HomeAssistantError, match="Invalid code"):
            auth_login.exchange_code(anon_client, code=done["result"])

    def test_a_json_token_request_is_refused_and_the_error_names_the_cause(
        self, anon_client
    ):
        """Sending JSON to `/auth/token` — which is what this client's default
        session header does unless overridden — is answered
        `unsupported_grant_type`, blaming a grant type that was correct."""
        status, body = anon_client.root_request(
            "POST",
            "/auth/token",
            json_payload={"grant_type": "refresh_token", "refresh_token": "x"},
            send_auth=False,
        )
        assert status == 400
        assert body["error"] == "unsupported_grant_type"

    def test_refresh_requires_the_original_client_id(self, anon_client):
        result = auth_login.login(anon_client, username=USERNAME, password=PASSWORD)
        refreshed = auth_login.refresh_access_token(
            anon_client,
            refresh_token=result["refresh_token"],
            client_id=result["client_id"],
        )
        assert refreshed["access_token"]
        assert "refresh_token" not in refreshed, "the refresh grant returns no new refresh token"

        with pytest.raises(HomeAssistantError, match="ISSUED to"):
            auth_login.refresh_access_token(
                anon_client,
                refresh_token=result["refresh_token"],
                client_id="http://somewhere-else.local:8123/",
            )

    def test_revoke_reports_success_for_a_bogus_token(self, anon_client):
        """RFC 7009 §2.2 — which is why `--verify` exists."""
        out = auth_login.revoke_token(anon_client, token="not-a-real-token")
        assert out["revoked"] is True and out["verified"] is False

    def test_revoke_with_verify_confirms_a_real_revocation(self, anon_client):
        result = auth_login.login(anon_client, username=USERNAME, password=PASSWORD)
        out = auth_login.revoke_token(
            anon_client,
            token=result["refresh_token"],
            verify=True,
            client_id=result["client_id"],
        )
        assert out["revoked"] is True and out["verified"] is True
        with pytest.raises(HomeAssistantError, match="invalid_grant"):
            auth_login.refresh_access_token(
                anon_client,
                refresh_token=result["refresh_token"],
                client_id=result["client_id"],
            )

    def test_link_user_needs_a_token_and_rejects_a_bad_code(
        self, anon_client, authed_client
    ):
        with pytest.raises(HomeAssistantError, match="one auth endpoint that needs"):
            auth_login.link_user(anon_client, code="whatever")
        with pytest.raises(HomeAssistantError, match="Invalid code"):
            auth_login.link_user(authed_client, code="whatever")


# ────────────────────────────────────────────────────────── through the CLI


class TestAuthLoginViaCli:
    def _run(self, hass_instance, *args, env_token=True):
        env = os.environ.copy()
        env["HASS_URL"] = hass_instance["url"]
        if env_token:
            env["HASS_TOKEN"] = hass_instance["token"]
        else:
            env.pop("HASS_TOKEN", None)
        return subprocess.run(
            _resolve_cli() + list(args),
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )

    def test_providers_via_cli_without_a_token(self, hass_instance):
        result = self._run(hass_instance, "auth", "providers", "--json", env_token=False)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["providers"][0]["type"] == "homeassistant"

    def test_login_via_cli_without_a_token(self, hass_instance, tmp_path):
        """A CLI run with no HASS_TOKEN at all, producing one."""
        result = self._run(
            hass_instance,
            "--config", str(tmp_path / "profile.json"),
            "auth", "login",
            "--username", USERNAME,
            "--password", PASSWORD,
            "--json",
            env_token=False,
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["username"] == USERNAME
        probe = HomeAssistantClient(url=hass_instance["url"], token=payload["access_token"])
        assert probe.get("") == {"message": "API running."}

    def test_login_save_writes_a_working_profile(self, hass_instance, tmp_path):
        cfg = tmp_path / "profile.json"
        result = self._run(
            hass_instance,
            "--config", str(cfg),
            "auth", "login",
            "--username", USERNAME,
            "--password", PASSWORD,
            "--save", "--json",
            env_token=False,
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(cfg.read_text())["token"]
        assert oct(cfg.stat().st_mode)[-3:] == "600"

        # The saved profile alone is now enough to run an authenticated command.
        whoami = self._run(hass_instance, "--config", str(cfg), "auth", "me", "--json", env_token=False)
        assert whoami.returncode == 0, whoami.stderr
        assert json.loads(whoami.stdout)["name"]

    def test_bad_password_via_cli_is_a_clean_error(self, hass_instance):
        result = self._run(
            hass_instance,
            "auth", "login", "--username", USERNAME, "--password", "wrong-on-purpose",
            "--json",
            env_token=False,
        )
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "Traceback" not in combined
        assert "invalid_auth" in combined

    def test_oauth_metadata_via_cli(self, hass_instance):
        result = self._run(hass_instance, "auth", "oauth-metadata", "--json", env_token=False)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["token_endpoint"] == "/auth/token"
