"""CLI wiring for the `cloud` group, `system ping` and the owner-only user commands.

Asserts the options actually reach the core functions — a flag that parses and
then is not forwarded is the failure mode these catch.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from cli_anything.homeassistant import homeassistant_cli as cli_mod


@pytest.fixture
def runner(monkeypatch, fake_client):
    monkeypatch.setattr(cli_mod, "make_client", lambda ctx: fake_client)
    return CliRunner()


def _invoke(runner, *args, json_out=True, **kwargs):
    full = ["--json"] + list(args) if json_out else list(args)
    return runner.invoke(
        cli_mod.cli,
        full,
        obj={
            "url": "http://x", "token": "t", "verify_ssl": False,
            "timeout": 5, "as_json": json_out, "config_path": None,
        },
        **kwargs,
    )


# ────────────────────────────────────────────────────────────── cloud status


class TestCloudStatus:
    def test_status(self, runner, fake_client):
        fake_client.set_ws(
            "cloud/status",
            {"logged_in": True, "email": "a@b.c", "cloud": "connected", "prefs": {}},
        )
        r = _invoke(runner, "cloud", "status")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["logged_in"] is True
        assert data["email"] == "a@b.c"

    def test_logged_out_status_is_exit_zero(self, runner, fake_client):
        fake_client.set_ws("cloud/status", {"logged_in": False, "cloud": "disconnected"})
        r = _invoke(runner, "cloud", "status")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["logged_in"] is False

    def test_subscription_logged_out_is_exit_zero(self, runner, fake_client):
        """A READ has a true answer when signed out; it must not be an error."""
        fake_client.set_ws_error("cloud/subscription", "not_logged_in", "")
        r = _invoke(runner, "cloud", "subscription")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["subscription"] is None


# ─────────────────────────────────────────────────────────── cloud set-prefs


class TestCloudSetPrefs:
    def test_alexa_on(self, runner, fake_client):
        r = _invoke(runner, "cloud", "set-prefs", "--alexa")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {"alexa_enabled": True}

    def test_alexa_off(self, runner, fake_client):
        r = _invoke(runner, "cloud", "set-prefs", "--no-alexa")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {"alexa_enabled": False}

    def test_several_flags_combine(self, runner, fake_client):
        r = _invoke(
            runner, "cloud", "set-prefs",
            "--google", "--google-report-state", "--no-ice-servers",
        )
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {
            "google_enabled": True,
            "google_report_state": True,
            "cloud_ice_servers_enabled": False,
        }

    def test_pin_and_clear(self, runner, fake_client):
        assert _invoke(runner, "cloud", "set-prefs", "--google-pin", "9999").exit_code == 0
        assert fake_client.ws_calls[-1]["payload"] == {"google_secure_devices_pin": "9999"}
        assert _invoke(runner, "cloud", "set-prefs", "--google-pin", "").exit_code == 0
        assert fake_client.ws_calls[-1]["payload"] == {"google_secure_devices_pin": None}

    def test_tts_voice_takes_two_values(self, runner, fake_client):
        r = _invoke(runner, "cloud", "set-prefs", "--tts-voice", "en-GB", "RyanNeural")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"]["tts_default_voice"] == ["en-GB", "RyanNeural"]

    def test_no_flags_is_a_clean_error(self, runner, fake_client):
        r = _invoke(runner, "cloud", "set-prefs")
        assert r.exit_code == 1
        assert "Nothing to update" in r.output
        assert fake_client.ws_calls == []


# ────────────────────────────────────────────────────────────── cloud remote


class TestCloudRemote:
    def test_connect(self, runner, fake_client):
        r = _invoke(runner, "cloud", "remote", "connect")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["type"] == "cloud/remote/connect"

    def test_disconnect_needs_confirmation(self, runner, fake_client):
        r = _invoke(runner, "cloud", "remote", "disconnect", input="n\n")
        assert r.exit_code != 0
        assert fake_client.ws_calls == []

    def test_disconnect_with_yes(self, runner, fake_client):
        r = _invoke(runner, "cloud", "remote", "disconnect", "--yes")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["type"] == "cloud/remote/disconnect"

    def test_connect_logged_out_is_an_error(self, runner, fake_client):
        """A WRITE must not report success when nothing happened."""
        fake_client.set_ws_error("cloud/remote/connect", "not_logged_in", "")
        r = _invoke(runner, "cloud", "remote", "connect")
        assert r.exit_code == 1
        assert "not logged in" in r.output


# ─────────────────────────────────────────────────────── cloud alexa/google


class TestCloudAssistants:
    def test_alexa_entities(self, runner, fake_client):
        fake_client.set_ws("cloud/alexa/entities", [{"entity_id": "light.k"}])
        r = _invoke(runner, "cloud", "alexa", "entities")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["entities"][0]["entity_id"] == "light.k"

    def test_alexa_entity(self, runner, fake_client):
        fake_client.set_ws("cloud/alexa/entities/get", None)
        r = _invoke(runner, "cloud", "alexa", "entity", "light.k")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["supported"] is True

    def test_alexa_sync(self, runner, fake_client):
        r = _invoke(runner, "cloud", "alexa", "sync")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["type"] == "cloud/alexa/sync"

    def test_google_entities(self, runner, fake_client):
        fake_client.set_ws("cloud/google_assistant/entities", [{"entity_id": "lock.f"}])
        r = _invoke(runner, "cloud", "google", "entities")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["entities"][0]["entity_id"] == "lock.f"

    def test_google_set_2fa_default_requires_the_pin(self, runner, fake_client):
        r = _invoke(runner, "cloud", "google", "set-2fa", "lock.front")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"]["disable_2fa"] is False

    def test_google_set_2fa_skip_inverts_it(self, runner, fake_client):
        """`--skip` must become `disable_2fa: true` — the flag names differ."""
        r = _invoke(runner, "cloud", "google", "set-2fa", "lock.front", "--skip")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"]["disable_2fa"] is True


# ────────────────────────────────────────────────── cloud tts + remove-data


class TestCloudTtsAndRemoveData:
    def test_tts_voices(self, runner, fake_client):
        fake_client.set_ws("cloud/tts/info", {"languages": [["en-GB", "A"], ["en-GB", "B"]]})
        r = _invoke(runner, "cloud", "tts-voices")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["voices"] == {"en-GB": ["A", "B"]}

    def test_tts_voices_language_filter(self, runner, fake_client):
        fake_client.set_ws("cloud/tts/info", {"languages": [["en-GB", "A"], ["nl-NL", "C"]]})
        r = _invoke(runner, "cloud", "tts-voices", "--language", "nl-NL")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["languages"] == ["nl-NL"]

    def test_remove_data_is_dry_run_by_default(self, runner, fake_client):
        r = _invoke(runner, "cloud", "remove-data")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["applied"] is False
        assert fake_client.ws_calls == []

    def test_remove_data_apply(self, runner, fake_client):
        r = _invoke(runner, "cloud", "remove-data", "--apply")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["type"] == "cloud/remove_data"


# ──────────────────────────────────────────────────────────────── system ping


class TestSystemPing:
    def test_ping(self, runner, fake_client):
        fake_client.set_ping(5.0)
        r = _invoke(runner, "system", "ping")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["latency_ms"] == 5.0

    def test_count_is_forwarded(self, runner, fake_client):
        fake_client.set_ping(1.0, 2.0, 3.0)
        r = _invoke(runner, "system", "ping", "--count", "3")
        assert r.exit_code == 0, r.output
        assert fake_client.ping_calls == 3
        assert json.loads(r.output)["avg_ms"] == 2.0


# ───────────────────────────────────────────── owner-only user credentials


class TestUserCredentialAdmin:
    def test_reset_password(self, runner, fake_client):
        r = _invoke(runner, "auth", "user", "reset-password", "u1", "--password", "s3cret")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1] == {
            "type": "config/auth_provider/homeassistant/admin_change_password",
            "payload": {"user_id": "u1", "password": "s3cret"},
        }

    def test_reset_password_prompts_when_omitted(self, runner, fake_client):
        r = _invoke(runner, "auth", "user", "reset-password", "u1", input="pw\npw\n")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"]["password"] == "pw"

    def test_unauthorized_is_explained(self, runner, fake_client):
        fake_client.set_ws_error(
            "config/auth_provider/homeassistant/admin_change_password", "unauthorized", ""
        )
        r = _invoke(runner, "auth", "user", "reset-password", "u1", "--password", "p")
        assert r.exit_code == 1
        assert "OWNER-only" in r.output

    def test_rename_login_needs_confirmation(self, runner, fake_client):
        r = _invoke(runner, "auth", "user", "rename-login", "u1", "newname", input="n\n")
        assert r.exit_code != 0
        assert fake_client.ws_calls == []

    def test_rename_login_with_yes(self, runner, fake_client):
        r = _invoke(runner, "auth", "user", "rename-login", "u1", "newname", "--yes")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1] == {
            "type": "config/auth_provider/homeassistant/admin_change_username",
            "payload": {"user_id": "u1", "username": "newname"},
        }
