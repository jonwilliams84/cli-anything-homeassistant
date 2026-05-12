"""Unit tests for cli_anything.homeassistant.core.system_log."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import system_log


class TestSystemLog:
    # ── list_errors ────────────────────────────────────────────────────────

    def test_list_errors_happy(self, fake_client):
        entries = [
            {
                "name": "homeassistant.components.hue",
                "message": ["Error connecting"],
                "level": "ERROR",
                "source": ("components/hue/__init__.py", 42),
                "timestamp": 1700000000.0,
                "exception": "",
                "count": 1,
                "first_occurred": 1700000000.0,
            }
        ]
        fake_client.set_ws("system_log/list", entries)
        result = system_log.list_errors(fake_client)
        assert result == entries
        last_ws = fake_client.ws_calls[-1]
        assert last_ws["type"] == "system_log/list"

    def test_list_errors_empty_log(self, fake_client):
        fake_client.set_ws("system_log/list", [])
        result = system_log.list_errors(fake_client)
        assert result == []

    def test_list_errors_return_shape(self, fake_client):
        entries = [
            {"name": "comp.a", "message": ["msg"], "level": "WARNING",
             "source": ("a.py", 1), "timestamp": 1.0,
             "exception": "", "count": 2, "first_occurred": 1.0},
            {"name": "comp.b", "message": ["msg2"], "level": "ERROR",
             "source": ("b.py", 10), "timestamp": 2.0,
             "exception": "", "count": 1, "first_occurred": 2.0},
        ]
        fake_client.set_ws("system_log/list", entries)
        result = system_log.list_errors(fake_client)
        assert isinstance(result, list)
        assert len(result) == 2
        assert all("name" in e and "level" in e for e in result)

    def test_list_errors_ws_call_recorded(self, fake_client):
        fake_client.set_ws("system_log/list", [])
        system_log.list_errors(fake_client)
        assert any(c["type"] == "system_log/list" for c in fake_client.ws_calls)

    # ── clear ──────────────────────────────────────────────────────────────

    def test_clear_happy(self, fake_client):
        fake_client.set("POST", "services/system_log/clear", {"result": "ok"})
        result = system_log.clear(fake_client)
        # Default FakeClient POST returns {} when no matching response registered
        last = fake_client.calls[-1]
        assert last["verb"] == "POST"
        assert last["path"] == "services/system_log/clear"

    def test_clear_posts_empty_payload(self, fake_client):
        system_log.clear(fake_client)
        last = fake_client.calls[-1]
        assert last["payload"] == {}

    def test_clear_service_call_recorded(self, fake_client):
        system_log.clear(fake_client)
        assert any(
            c["domain"] == "system_log" and c["service"] == "clear"
            for c in fake_client.service_calls
        )

    # ── write ──────────────────────────────────────────────────────────────

    def test_write_happy_default_level(self, fake_client):
        system_log.write(fake_client, message="Test message")
        last = fake_client.calls[-1]
        assert last["verb"] == "POST"
        assert last["path"] == "services/system_log/write"
        assert last["payload"]["message"] == "Test message"
        assert last["payload"]["level"] == "error"

    def test_write_custom_level(self, fake_client):
        system_log.write(fake_client, message="Debug msg", level="debug")
        last = fake_client.calls[-1]
        assert last["payload"]["level"] == "debug"

    def test_write_with_logger(self, fake_client):
        system_log.write(
            fake_client, message="Info msg", level="info", logger="my.custom.logger"
        )
        last = fake_client.calls[-1]
        assert last["payload"]["logger"] == "my.custom.logger"

    def test_write_without_logger_omits_key(self, fake_client):
        system_log.write(fake_client, message="No logger", level="warning")
        last = fake_client.calls[-1]
        assert "logger" not in last["payload"]

    def test_write_all_valid_levels(self, fake_client):
        for lvl in ("debug", "info", "warning", "error", "critical"):
            system_log.write(fake_client, message="msg", level=lvl)
            last = fake_client.calls[-1]
            assert last["payload"]["level"] == lvl

    def test_write_invalid_level_raises(self, fake_client):
        with pytest.raises(ValueError, match="level"):
            system_log.write(fake_client, message="msg", level="verbose")

    def test_write_empty_message_raises(self, fake_client):
        with pytest.raises(ValueError, match="message"):
            system_log.write(fake_client, message="")

    def test_write_service_call_recorded(self, fake_client):
        system_log.write(fake_client, message="test", level="error")
        assert any(
            c["domain"] == "system_log" and c["service"] == "write"
            for c in fake_client.service_calls
        )

    def test_write_return_shape(self, fake_client):
        fake_client.set("POST", "services/system_log/write", [{"entity_id": "x"}])
        result = system_log.write(fake_client, message="hello", level="critical")
        # Result is whatever HA returns (list of affected entities or {})
        assert result is not None
