"""Unit tests for cli_anything.homeassistant.core.control — no real HA required."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import control


class TestRestart:
    def test_restart_no_safe_mode(self, fake_client):
        control.restart(fake_client)
        call = fake_client.service_calls[-1]
        assert call["domain"] == "homeassistant"
        assert call["service"] == "restart"
        # No safe_mode → no safe_mode key in the payload
        assert "safe_mode" not in call["service_data"]

    def test_restart_safe_mode(self, fake_client):
        control.restart(fake_client, safe_mode=True)
        call = fake_client.service_calls[-1]
        assert call["service_data"]["safe_mode"] is True


class TestStop:
    def test_stop_calls_service(self, fake_client):
        control.stop(fake_client)
        call = fake_client.service_calls[-1]
        assert call["domain"] == "homeassistant"
        assert call["service"] == "stop"


class TestReloadCoreConfig:
    def test_calls_service(self, fake_client):
        control.reload_core_config(fake_client)
        call = fake_client.service_calls[-1]
        assert call["domain"] == "homeassistant"
        assert call["service"] == "reload_core_config"


class TestReloadConfigEntry:
    def test_sends_ws_call(self, fake_client):
        fake_client.set_ws("config_entries/reload", {"ok": True})
        result = control.reload_config_entry(fake_client, "entry123")
        assert result == {"ok": True}
        assert fake_client.ws_calls[-1]["type"] == "config_entries/reload"
        assert fake_client.ws_calls[-1]["payload"] == {"entry_id": "entry123"}

    def test_empty_entry_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="entry_id is required"):
            control.reload_config_entry(fake_client, "")


class TestReloadAll:
    def test_calls_service(self, fake_client):
        control.reload_all(fake_client)
        call = fake_client.service_calls[-1]
        assert call["domain"] == "homeassistant"
        assert call["service"] == "reload_all"


class TestCheckConfig:
    def test_valid_when_no_notification(self, fake_client):
        """No config_check_failed notification → valid=True."""
        fake_client.set("GET", "states/persistent_notification.config_check_failed", None)
        result = control.check_config(fake_client, wait_secs=0.2)
        assert result["valid"] is True
        assert result["errors"] is None

    def test_valid_when_state_is_unknown(self, fake_client):
        fake_client.set("GET", "states/persistent_notification.config_check_failed",
                        {"state": "unknown"})
        result = control.check_config(fake_client, wait_secs=0.2)
        assert result["valid"] is True

    def test_valid_when_state_is_unavailable(self, fake_client):
        fake_client.set("GET", "states/persistent_notification.config_check_failed",
                        {"state": "unavailable"})
        result = control.check_config(fake_client, wait_secs=0.2)
        assert result["valid"] is True

    def test_invalid_when_notification_has_message(self, fake_client):
        fake_client.set("GET", "states/persistent_notification.config_check_failed",
                        {"state": "config_check_failed",
                         "attributes": {"message": "Bad YAML", "title": "Error",
                                        "created_at": "2024-01-01"}})
        result = control.check_config(fake_client, wait_secs=0.2)
        assert result["valid"] is False
        assert result["message"] == "Bad YAML"
        assert result["title"] == "Error"
        assert result["created_at"] == "2024-01-01"

    def test_invalid_uses_default_title_when_missing(self, fake_client):
        fake_client.set("GET", "states/persistent_notification.config_check_failed",
                        {"state": "config_check_failed",
                         "attributes": {"message": "Bad YAML"}})
        result = control.check_config(fake_client, wait_secs=0.2)
        assert result["valid"] is False
        assert result["title"] == "Config Check Failed"

    def test_invalid_with_no_attributes(self, fake_client):
        fake_client.set("GET", "states/persistent_notification.config_check_failed",
                        {"state": "config_check_failed"})
        result = control.check_config(fake_client, wait_secs=0.2)
        assert result["valid"] is False
        assert result["message"] is None
        assert result["title"] == "Config Check Failed"

    def test_triggers_check_config_service(self, fake_client):
        """check_config must call the homeassistant.check_config service first."""
        fake_client.set("GET", "states/persistent_notification.config_check_failed", None)
        control.check_config(fake_client, wait_secs=0.2)
        svc = fake_client.service_calls[0]
        assert svc["domain"] == "homeassistant"
        assert svc["service"] == "check_config"


class TestSafeRestart:
    def test_restarts_on_valid_config(self, fake_client):
        fake_client.set("GET", "states/persistent_notification.config_check_failed", None)
        result = control.safe_restart(fake_client, wait_check_secs=0.2)
        assert result["restarted"] is True
        # The last service call should be restart
        assert fake_client.service_calls[-1]["service"] == "restart"

    def test_does_not_restart_on_invalid_config(self, fake_client):
        fake_client.set("GET", "states/persistent_notification.config_check_failed",
                        {"state": "config_check_failed",
                         "attributes": {"message": "Bad"}})
        result = control.safe_restart(fake_client, wait_check_secs=0.2)
        assert result["restarted"] is False
        assert result["reason"] == "check_config failed"
        # No restart call should have been made
        services_called = [c["service"] for c in fake_client.service_calls]
        assert "restart" not in services_called
