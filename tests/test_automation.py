"""Unit tests for cli_anything.homeassistant.core.automation.

Covers trigger, toggle, turn_on, turn_off, reload, get_config,
_automation_item_id, list_traces, get_trace, save_config, delete_config.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import automation


# ── trigger ───────────────────────────────────────────────────────────────────


class TestTrigger:
    def test_trigger_calls_service(self, fake_client):
        fake_client.set_service("automation", "trigger", {"ok": True})
        result = automation.trigger(fake_client, "automation.my_auto")
        assert result == {"ok": True}
        call = fake_client.service_calls[-1]
        assert call["domain"] == "automation"
        assert call["service"] == "trigger"
        assert call["service_data"] == {"entity_id": "automation.my_auto"}  # skip_condition=False → no extra data

    def test_trigger_with_skip_condition(self, fake_client):
        fake_client.set_service("automation", "trigger", {})
        automation.trigger(fake_client, "automation.my_auto", skip_condition=True)
        call = fake_client.service_calls[-1]
        assert call["service_data"] == {"skip_condition": True, "entity_id": "automation.my_auto"}

    def test_trigger_invalid_entity_raises(self, fake_client):
        with pytest.raises(ValueError, match="Expected an automation entity_id"):
            automation.trigger(fake_client, "sensor.temp")


# ── toggle / turn_on / turn_off ───────────────────────────────────────────────


class TestToggleTurnOnOff:
    def test_toggle(self, fake_client):
        fake_client.set_service("automation", "toggle", {"toggled": True})
        result = automation.toggle(fake_client, "automation.x")
        assert result == {"toggled": True}
        call = fake_client.service_calls[-1]
        assert call["service"] == "toggle"

    def test_turn_on(self, fake_client):
        fake_client.set_service("automation", "turn_on", {})
        automation.turn_on(fake_client, "automation.x")
        assert fake_client.service_calls[-1]["service"] == "turn_on"

    def test_turn_off(self, fake_client):
        fake_client.set_service("automation", "turn_off", {})
        automation.turn_off(fake_client, "automation.x")
        assert fake_client.service_calls[-1]["service"] == "turn_off"


# ── reload ─────────────────────────────────────────────────────────────────────


class TestReload:
    def test_reload_calls_service(self, fake_client):
        fake_client.set_service("automation", "reload", {"reloaded": True})
        result = automation.reload(fake_client)
        assert result == {"reloaded": True}
        call = fake_client.service_calls[-1]
        assert call["domain"] == "automation"
        assert call["service"] == "reload"

    def test_automation_reload_alias(self):
        assert automation.automation_reload is automation.reload


# ── get_config ─────────────────────────────────────────────────────────────────


class TestGetConfig:
    def test_returns_config_from_response(self, fake_client):
        fake_client.set_ws("automation/config", {"config": {"alias": "My Auto", "id": "42"}})
        result = automation.get_config(fake_client, "automation.my_auto")
        assert result == {"alias": "My Auto", "id": "42"}

    def test_returns_flat_response_when_no_config_key(self, fake_client):
        fake_client.set_ws("automation/config", {"alias": "Flat", "id": "42"})
        result = automation.get_config(fake_client, "automation.my_auto")
        assert result == {"alias": "Flat", "id": "42"}

    def test_returns_empty_dict_on_none(self, fake_client):
        fake_client.set_ws("automation/config", None)
        result = automation.get_config(fake_client, "automation.my_auto")
        assert result == {}

    def test_invalid_entity_raises(self, fake_client):
        with pytest.raises(ValueError, match="Expected an automation entity_id"):
            automation.get_config(fake_client, "sensor.temp")


# ── _automation_item_id ───────────────────────────────────────────────────────


class TestAutomationItemId:
    def test_resolves_id_from_config(self, fake_client):
        fake_client.set_ws("automation/config", {"config": {"id": "42"}})
        result = automation._automation_item_id(fake_client, "automation.my_auto")
        assert result == "42"

    def test_resolves_id_from_flat_config(self, fake_client):
        fake_client.set_ws("automation/config", {"id": "99"})
        result = automation._automation_item_id(fake_client, "automation.my_auto")
        assert result == "99"

    def test_raises_when_no_id(self, fake_client):
        fake_client.set_ws("automation/config", {"alias": "No ID"})
        with pytest.raises(ValueError, match="could not resolve numeric `id`"):
            automation._automation_item_id(fake_client, "automation.my_auto")

    def test_raises_when_config_is_none(self, fake_client):
        fake_client.set_ws("automation/config", None)
        with pytest.raises(ValueError, match="could not resolve numeric `id`"):
            automation._automation_item_id(fake_client, "automation.my_auto")

    def test_invalid_entity_raises(self, fake_client):
        with pytest.raises(ValueError, match="Expected an automation entity_id"):
            automation._automation_item_id(fake_client, "sensor.temp")


# ── list_traces ───────────────────────────────────────────────────────────────


class TestListTraces:
    def test_returns_trace_list(self, fake_client):
        fake_client.set_ws("automation/config", {"id": "42"})
        fake_client.set_ws("trace/list", [{"run_id": "r1"}, {"run_id": "r2"}])
        result = automation.list_traces(fake_client, "automation.my_auto")
        assert len(result) == 2
        assert result[0]["run_id"] == "r1"

    def test_returns_empty_list_on_non_list(self, fake_client):
        fake_client.set_ws("automation/config", {"id": "42"})
        fake_client.set_ws("trace/list", {"not": "a list"})
        result = automation.list_traces(fake_client, "automation.my_auto")
        assert result == []


# ── get_trace ─────────────────────────────────────────────────────────────────


class TestGetTrace:
    def test_get_trace_by_run_id(self, fake_client):
        fake_client.set_ws("automation/config", {"id": "42"})
        fake_client.set_ws("trace/get", {"trace": "data", "run_id": "r1"})
        result = automation.get_trace(fake_client, "automation.my_auto", run_id="r1")
        assert result == {"trace": "data", "run_id": "r1"}

    def test_get_trace_most_recent(self, fake_client):
        fake_client.set_ws("automation/config", {"id": "42"})
        fake_client.set_ws("trace/list", [{"run_id": "r1"}, {"run_id": "r2"}])
        fake_client.set_ws("trace/get", {"trace": "latest"})
        result = automation.get_trace(fake_client, "automation.my_auto")
        assert result == {"trace": "latest"}
        # Should use the last trace's run_id
        trace_get_call = [c for c in fake_client.ws_calls if c["type"] == "trace/get"][0]
        assert trace_get_call["payload"]["run_id"] == "r2"

    def test_get_trace_no_traces_returns_empty(self, fake_client):
        fake_client.set_ws("automation/config", {"id": "42"})
        fake_client.set_ws("trace/list", [])
        result = automation.get_trace(fake_client, "automation.my_auto")
        assert result == {}

    def test_get_trace_most_recent_no_run_id(self, fake_client):
        """When the most recent trace has no run_id, return empty dict."""
        fake_client.set_ws("automation/config", {"id": "42"})
        fake_client.set_ws("trace/list", [{"some_key": "no run_id"}])
        result = automation.get_trace(fake_client, "automation.my_auto")
        assert result == {}


# ── save_config ───────────────────────────────────────────────────────────────


class TestSaveConfig:
    def test_saves_config(self, fake_client):
        fake_client.set("POST", "config/automation/config/42", {"saved": True})
        result = automation.save_config(fake_client, "automation.my_auto", {"id": "42", "alias": "X"})
        assert result == {"saved": True}

    def test_invalid_entity_raises(self, fake_client):
        with pytest.raises(ValueError, match="Expected an automation entity_id"):
            automation.save_config(fake_client, "sensor.temp", {"id": "1"})

    def test_non_dict_config_raises(self, fake_client):
        with pytest.raises(ValueError, match="config must be a dict"):
            automation.save_config(fake_client, "automation.x", "not a dict")

    def test_missing_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="config\\['id'\\] is required"):
            automation.save_config(fake_client, "automation.x", {"alias": "no id"})


# ── delete_config ─────────────────────────────────────────────────────────────


class TestDeleteConfig:
    def test_deletes_config(self, fake_client):
        fake_client.set_ws("automation/config", {"id": "42"})
        fake_client.set("DELETE", "config/automation/config/42", {"deleted": True})
        result = automation.delete_config(fake_client, "automation.my_auto")
        assert result == {"deleted": True}

    def test_invalid_entity_raises(self, fake_client):
        with pytest.raises(ValueError, match="Expected an automation entity_id"):
            automation.delete_config(fake_client, "sensor.temp")
