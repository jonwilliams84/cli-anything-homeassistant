"""Unit tests for cli_anything.homeassistant.core.script — no real HA required."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import script


class TestListScripts:
    def test_filters_to_script_domain(self, fake_client):
        fake_client.set("GET", "states", [
            {"entity_id": "script.morning", "state": "off"},
            {"entity_id": "light.kitchen", "state": "on"},
            {"entity_id": "script.evening", "state": "off"},
        ])
        rows = script.list_scripts(fake_client)
        assert {r["entity_id"] for r in rows} == {"script.morning", "script.evening"}

    def test_non_list_response_returns_empty(self, fake_client):
        fake_client.set("GET", "states", None)
        assert script.list_scripts(fake_client) == []


class TestRun:
    def test_run_without_variables(self, fake_client):
        script.run(fake_client, "script.morning")
        call = fake_client.service_calls[-1]
        assert call["domain"] == "script"
        assert call["service"] == "turn_on"
        # target entity_id is folded into service_data by call_service
        assert call["service_data"]["entity_id"] == "script.morning"
        assert "variables" not in call["service_data"]

    def test_run_with_variables(self, fake_client):
        script.run(fake_client, "script.morning", {"brightness": 100})
        call = fake_client.service_calls[-1]
        assert call["service_data"]["variables"] == {"brightness": 100}
        assert call["service_data"]["entity_id"] == "script.morning"

    def test_non_script_entity_raises(self, fake_client):
        with pytest.raises(ValueError, match="script entity_id"):
            script.run(fake_client, "light.kitchen")


class TestReload:
    def test_calls_reload_service(self, fake_client):
        script.reload(fake_client)
        call = fake_client.service_calls[-1]
        assert call["domain"] == "script"
        assert call["service"] == "reload"

    def test_script_reload_alias(self, fake_client):
        """script_reload is an alias for reload."""
        script.script_reload(fake_client)
        call = fake_client.service_calls[-1]
        assert call["service"] == "reload"


class TestGetConfig:
    def test_returns_config_from_ws_response(self, fake_client):
        fake_client.set_ws("script/config", {"config": {"mode": "single"}})
        result = script.get_config(fake_client, "script.morning")
        assert result == {"mode": "single"}

    def test_returns_response_when_no_config_key(self, fake_client):
        fake_client.set_ws("script/config", {"mode": "restart"})
        result = script.get_config(fake_client, "script.morning")
        assert result == {"mode": "restart"}

    def test_falls_back_to_rest_on_non_dict(self, fake_client):
        fake_client.set_ws("script/config", [])
        fake_client.set("GET", "config/script/config/morning", {"mode": "queued"})
        result = script.get_config(fake_client, "script.morning")
        assert result == {"mode": "queued"}

    def test_non_script_entity_raises(self, fake_client):
        with pytest.raises(ValueError, match="script entity_id"):
            script.get_config(fake_client, "light.kitchen")


class TestSaveConfig:
    def test_saves_config(self, fake_client):
        fake_client.set("POST", "config/script/config/morning", {"ok": True})
        result = script.save_config(fake_client, "script.morning", {"mode": "single"})
        assert result == {"ok": True}
        assert fake_client.calls[-1]["verb"] == "POST"
        assert fake_client.calls[-1]["path"] == "config/script/config/morning"
        assert fake_client.calls[-1]["payload"] == {"mode": "single"}

    def test_non_script_entity_raises(self, fake_client):
        with pytest.raises(ValueError, match="script entity_id"):
            script.save_config(fake_client, "light.kitchen", {})

    def test_non_dict_config_raises(self, fake_client):
        with pytest.raises(ValueError, match="config must be a dict"):
            script.save_config(fake_client, "script.morning", "not a dict")


class TestDeleteConfig:
    def test_deletes_config(self, fake_client):
        fake_client.set("DELETE", "config/script/config/morning", {"ok": True})
        result = script.delete_config(fake_client, "script.morning")
        assert result == {"ok": True}
        assert fake_client.calls[-1]["verb"] == "DELETE"
        assert fake_client.calls[-1]["path"] == "config/script/config/morning"

    def test_non_script_entity_raises(self, fake_client):
        with pytest.raises(ValueError, match="script entity_id"):
            script.delete_config(fake_client, "light.kitchen")


class TestListTraces:
    def test_returns_list(self, fake_client):
        fake_client.set_ws("trace/list", [{"run_id": "1"}, {"run_id": "2"}])
        result = script.list_traces(fake_client, "script.morning")
        assert len(result) == 2
        assert fake_client.ws_calls[-1]["payload"] == {
            "domain": "script", "item_id": "morning",
        }

    def test_non_list_returns_empty(self, fake_client):
        fake_client.set_ws("trace/list", None)
        assert script.list_traces(fake_client, "script.morning") == []

    def test_non_script_entity_raises(self, fake_client):
        with pytest.raises(ValueError, match="script entity_id"):
            script.list_traces(fake_client, "light.kitchen")


class TestGetTrace:
    def test_with_explicit_run_id(self, fake_client):
        fake_client.set_ws("trace/get", {"trace": "data"})
        result = script.get_trace(fake_client, "script.morning", "run42")
        assert result == {"trace": "data"}
        assert fake_client.ws_calls[-1]["payload"] == {
            "domain": "script", "item_id": "morning", "run_id": "run42",
        }

    def test_without_run_id_uses_most_recent(self, fake_client):
        fake_client.set_ws("trace/list", [{"run_id": "r1"}, {"run_id": "r2"}])
        fake_client.set_ws("trace/get", {"trace": "data"})
        result = script.get_trace(fake_client, "script.morning")
        assert result == {"trace": "data"}
        assert fake_client.ws_calls[-1]["payload"]["run_id"] == "r2"

    def test_without_run_id_no_traces_returns_empty(self, fake_client):
        fake_client.set_ws("trace/list", [])
        result = script.get_trace(fake_client, "script.morning")
        assert result == {}

    def test_without_run_id_empty_traces_response(self, fake_client):
        fake_client.set_ws("trace/list", None)
        result = script.get_trace(fake_client, "script.morning")
        assert result == {}

    def test_most_recent_trace_has_no_run_id(self, fake_client):
        """If the last trace has no run_id, return empty dict."""
        fake_client.set_ws("trace/list", [{"run_id": ""}])
        result = script.get_trace(fake_client, "script.morning")
        assert result == {}

    def test_non_script_entity_raises(self, fake_client):
        with pytest.raises(ValueError, match="script entity_id"):
            script.get_trace(fake_client, "light.kitchen")
