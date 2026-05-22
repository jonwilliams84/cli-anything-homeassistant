"""CLI wiring tests for the third refine pass — sysadmin & auth.

Covers: auth tokens extensions, auth me, auth sign-path, auth user subgroup,
category group, logger WS variants, system manifest/analytics/app-credentials/
issue/usb-scan/zha-permit/hardware/log subgroups.
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


def _invoke(runner, *args, json_out=True, input_text=None):
    full = ["--json"] + list(args) if json_out else list(args)
    return runner.invoke(cli_mod.cli, full,
                         obj={
                             "url": "http://x", "token": "t", "verify_ssl": False,
                             "timeout": 5, "as_json": json_out, "config_path": None,
                         },
                         input=input_text)


# ──────────────────────────────────────────────────────────────────── auth me / sign-path

class TestAuthCoreExtensions:
    def test_me(self, runner, fake_client):
        fake_client.set_ws("auth/current_user",
                           {"id": "u1", "name": "Jon", "is_admin": True})
        r = _invoke(runner, "auth", "me")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["name"] == "Jon"

    def test_sign_path(self, runner, fake_client):
        fake_client.set_ws("auth/sign_path",
                           {"path": "/api/camera_proxy/x?auth=token"})
        r = _invoke(runner, "auth", "sign-path",
                    "/api/camera_proxy/camera.front",
                    "--expires", "120")
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert last["type"] == "auth/sign_path"
        assert last["payload"] == {
            "path": "/api/camera_proxy/camera.front", "expires": 120,
        }


# ──────────────────────────────────────────────────────────────────── auth tokens

class TestAuthTokensExtensions:
    def test_list(self, runner, fake_client):
        fake_client.set_ws("auth/refresh_tokens",
                           [{"id": "t1"}, {"id": "t2"}])
        r = _invoke(runner, "auth", "tokens", "list")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert len(data) == 2

    def test_delete_requires_confirm(self, runner, fake_client):
        r = _invoke(runner, "auth", "tokens", "delete", "tok-123")
        assert r.exit_code != 0  # aborted by confirmation prompt

    def test_delete_with_yes(self, runner, fake_client):
        fake_client.set_ws("auth/delete_refresh_token", {"ok": True})
        r = _invoke(runner, "auth", "tokens", "delete", "tok-123", "--yes")
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert last["payload"] == {"refresh_token_id": "tok-123"}

    def test_delete_all_with_yes(self, runner, fake_client):
        fake_client.set_ws("auth/delete_all_refresh_tokens", {"deleted": 3})
        r = _invoke(runner, "auth", "tokens", "delete-all", "--yes")
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        # delete_current_token defaults to False; token_type defaults to omitted.
        assert last["payload"].get("delete_current_token") is False

    def test_delete_all_with_current(self, runner, fake_client):
        fake_client.set_ws("auth/delete_all_refresh_tokens", {"deleted": 4})
        r = _invoke(runner, "auth", "tokens", "delete-all",
                    "--delete-current", "--yes")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"]["delete_current_token"] is True

    def test_set_expiry(self, runner, fake_client):
        fake_client.set_ws("auth/refresh_token_set_expiry", {"ok": True})
        r = _invoke(runner, "auth", "tokens", "set-expiry", "tok-123",
                    "--no-expiry")
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert last["payload"] == {
            "refresh_token_id": "tok-123", "enable_expiry": False,
        }


# ──────────────────────────────────────────────────────────────────── auth user

class TestAuthUserCli:
    def test_create_minimal(self, runner, fake_client):
        fake_client.set_ws("config/auth/create",
                           {"user": {"id": "u-new", "name": "Bob"}})
        r = _invoke(runner, "auth", "user", "create", "Bob")
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert last["type"] == "config/auth/create"
        assert last["payload"]["name"] == "Bob"

    def test_create_with_groups(self, runner, fake_client):
        fake_client.set_ws("config/auth/create", {"user": {"id": "u"}})
        r = _invoke(runner, "auth", "user", "create", "Admin",
                    "--group", "system-admin", "--local-only")
        assert r.exit_code == 0, r.output
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["group_ids"] == ["system-admin"]
        assert payload["local_only"] is True

    def test_update_requires_at_least_one_field(self, runner, fake_client):
        r = _invoke(runner, "auth", "user", "update", "user-id-123")
        assert r.exit_code != 0
        assert "--name" in r.output

    def test_update_with_fields(self, runner, fake_client):
        fake_client.set_ws("config/auth/update", {"user": {"id": "u"}})
        r = _invoke(runner, "auth", "user", "update", "user-id-123",
                    "--name", "Bob Smith", "--inactive")
        assert r.exit_code == 0, r.output
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["user_id"] == "user-id-123"
        assert payload["name"] == "Bob Smith"
        assert payload["is_active"] is False

    def test_credential_create(self, runner, fake_client):
        fake_client.set_ws("config/auth_provider/homeassistant/create",
                           {"ok": True})
        r = _invoke(runner, "auth", "user", "credential-create",
                    "user-id-123", "bob",
                    "--password", "secret")
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert last["payload"] == {
            "user_id": "user-id-123", "username": "bob", "password": "secret",
        }

    def test_credential_delete_with_yes(self, runner, fake_client):
        fake_client.set_ws("config/auth_provider/homeassistant/delete",
                           {"ok": True})
        r = _invoke(runner, "auth", "user", "credential-delete", "bob",
                    "--yes")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {"username": "bob"}

    def test_change_password(self, runner, fake_client):
        fake_client.set_ws("config/auth_provider/homeassistant/change_password",
                           {"ok": True})
        r = _invoke(runner, "auth", "user", "change-password",
                    "--current-password", "old", "--new-password", "newpass1")
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert last["payload"] == {
            "current_password": "old", "new_password": "newpass1",
        }


# ──────────────────────────────────────────────────────────────────── category

class TestCategoryCli:
    def test_list(self, runner, fake_client):
        fake_client.set_ws("config/category_registry/list",
                           [{"category_id": "c1", "name": "Alerts"}])
        r = _invoke(runner, "category", "list", "automation")
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert last["payload"] == {"scope": "automation"}

    def test_create(self, runner, fake_client):
        fake_client.set_ws("config/category_registry/create",
                           {"category_id": "c-new", "name": "Lighting"})
        r = _invoke(runner, "category", "create", "automation", "Lighting",
                    "--icon", "mdi:lightbulb")
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert last["payload"] == {
            "scope": "automation", "name": "Lighting", "icon": "mdi:lightbulb",
        }

    def test_update_requires_field(self, runner, fake_client):
        r = _invoke(runner, "category", "update", "automation", "c1")
        assert r.exit_code != 0

    def test_update(self, runner, fake_client):
        fake_client.set_ws("config/category_registry/update", {"ok": True})
        r = _invoke(runner, "category", "update", "automation", "c1",
                    "--name", "Lights & Switches")
        assert r.exit_code == 0, r.output
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["name"] == "Lights & Switches"

    def test_delete_with_yes(self, runner, fake_client):
        fake_client.set_ws("config/category_registry/delete", {"ok": True})
        r = _invoke(runner, "category", "delete", "automation", "c1", "--yes")
        assert r.exit_code == 0, r.output

    def test_by_name(self, runner, fake_client):
        fake_client.set_ws("config/category_registry/list", [
            {"category_id": "c1", "name": "Alerts"},
            {"category_id": "c2", "name": "Routines"},
        ])
        r = _invoke(runner, "category", "by-name", "automation")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert set(data.keys()) == {"Alerts", "Routines"}


# ──────────────────────────────────────────────────────────────────── logger (WS variants)

class TestLoggerWsCli:
    def test_info_ws(self, runner, fake_client):
        fake_client.set_ws("logger/log_info",
                           [{"domain": "homeassistant", "level": 20}])
        r = _invoke(runner, "logger", "info-ws")
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert last["type"] == "logger/log_info"

    def test_level_get_requires_arg(self, runner, fake_client):
        r = _invoke(runner, "logger", "level-get")
        assert r.exit_code != 0

    def test_level_get_integration(self, runner, fake_client):
        fake_client.set_ws("logger/log_level", {"level": "debug"})
        r = _invoke(runner, "logger", "level-get", "--integration", "mqtt")
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert last["payload"]["integration"] == "mqtt"

    def test_level_set(self, runner, fake_client):
        fake_client.set_ws("logger/integration_log_level", {"ok": True})
        r = _invoke(runner, "logger", "level-set", "mqtt", "debug",
                    "--persistence", "once")
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert last["type"] == "logger/integration_log_level"
        assert last["payload"] == {
            "integration": "mqtt", "level": "debug", "persistence": "once",
        }


# ──────────────────────────────────────────────────────────────────── system extensions

class TestSystemExtensionsCli:
    def test_manifest_list(self, runner, fake_client):
        fake_client.set_ws("manifest/list", {"mqtt": {"version": "1.0"}})
        r = _invoke(runner, "system", "manifest", "list")
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert last["type"] == "manifest/list"

    def test_manifest_get(self, runner, fake_client):
        fake_client.set_ws("manifest/get",
                           {"domain": "mqtt", "version": "1.0"})
        r = _invoke(runner, "system", "manifest", "get", "mqtt")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {"integration": "mqtt"}

    def test_analytics_get(self, runner, fake_client):
        fake_client.set_ws("analytics",
                           {"preferences": {}, "onboarded": True})
        r = _invoke(runner, "system", "analytics", "get")
        assert r.exit_code == 0, r.output

    def test_analytics_set_validates_json(self, runner, fake_client):
        r = _invoke(runner, "system", "analytics", "set", "not-json")
        assert r.exit_code != 0
        assert "valid JSON" in r.output

    def test_analytics_set(self, runner, fake_client):
        fake_client.set_ws("analytics/preferences", {"ok": True})
        r = _invoke(runner, "system", "analytics", "set",
                    '{"base":true,"usage":false}')
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {
            "preferences": {"base": True, "usage": False},
        }

    def test_app_credentials_config(self, runner, fake_client):
        fake_client.set_ws("application_credentials/config",
                           {"domains": ["google_calendar"]})
        r = _invoke(runner, "system", "app-credentials", "config")
        assert r.exit_code == 0, r.output

    def test_app_credentials_entry(self, runner, fake_client):
        fake_client.set_ws("application_credentials/config_entry",
                           {"client_id": "abc"})
        r = _invoke(runner, "system", "app-credentials", "entry", "cfg-123")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {"config_entry_id": "cfg-123"}

    def test_issue_get_data(self, runner, fake_client):
        fake_client.set_ws("repairs/get_issue_data",
                           {"issue_data": {"foo": "bar"}})
        r = _invoke(runner, "system", "issue", "get-data",
                    "homeassistant", "broken_yaml")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {
            "domain": "homeassistant", "issue_id": "broken_yaml",
        }

    def test_issue_ignore(self, runner, fake_client):
        fake_client.set_ws("repairs/ignore_issue", {"ok": True})
        r = _invoke(runner, "system", "issue", "ignore",
                    "homeassistant", "broken_yaml")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"]["ignore"] is True

    def test_issue_unignore(self, runner, fake_client):
        fake_client.set_ws("repairs/ignore_issue", {"ok": True})
        r = _invoke(runner, "system", "issue", "ignore",
                    "homeassistant", "broken_yaml", "--unignore")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"]["ignore"] is False

    def test_usb_scan(self, runner, fake_client):
        fake_client.set_ws("usb/scan", {"ok": True})
        r = _invoke(runner, "system", "usb-scan")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["type"] == "usb/scan"

    def test_zha_permit_join(self, runner, fake_client):
        fake_client.set_ws("zha/devices/permit", {"ok": True})
        r = _invoke(runner, "system", "zha-permit-join",
                    "--duration", "120")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"]["duration"] == 120

    def test_hardware_info(self, runner, fake_client):
        fake_client.set_ws("hardware/info", {"hostname": "ha"})
        r = _invoke(runner, "system", "hardware-info")
        assert r.exit_code == 0, r.output

    def test_board_info(self, runner, fake_client):
        fake_client.set_ws("hardware/boards", [{"name": "rpi5"}])
        r = _invoke(runner, "system", "board-info")
        assert r.exit_code == 0, r.output

    def test_cpu_info(self, runner, fake_client):
        fake_client.set_ws("hardware/cpus",
                           [{"model": "Cortex-A76"}])
        r = _invoke(runner, "system", "cpu-info")
        assert r.exit_code == 0, r.output


# ──────────────────────────────────────────────────────────────────── system log

class TestSystemLogCli:
    def test_errors(self, runner, fake_client):
        fake_client.set_ws("system_log_list",
                           [{"level": "ERROR", "message": "boom"}])
        r = _invoke(runner, "system", "log", "errors")
        assert r.exit_code == 0, r.output

    def test_clear_with_yes(self, runner, fake_client):
        fake_client.set("POST", "services/system_log/clear", {})
        r = _invoke(runner, "system", "log", "clear", "--yes")
        assert r.exit_code == 0, r.output

    def test_write_default(self, runner, fake_client):
        fake_client.set("POST", "services/system_log/write", {})
        r = _invoke(runner, "system", "log", "write", "hello world")
        assert r.exit_code == 0, r.output
        last = fake_client.calls[-1]
        assert last["path"] == "services/system_log/write"
        assert last["payload"]["message"] == "hello world"
        assert last["payload"]["level"] == "error"

    def test_write_with_level_and_logger(self, runner, fake_client):
        fake_client.set("POST", "services/system_log/write", {})
        r = _invoke(runner, "system", "log", "write", "low-level event",
                    "--level", "warning",
                    "--logger-name", "homeassistant.components.mqtt")
        assert r.exit_code == 0, r.output
        payload = fake_client.calls[-1]["payload"]
        assert payload["level"] == "warning"
        assert payload["logger"] == "homeassistant.components.mqtt"
