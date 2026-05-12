"""Unit tests for cli_anything.homeassistant.core.device_automation.

All tests run against FakeClient (auto-injected via the ``fake_client``
fixture in conftest.py) — no live Home Assistant required.

WS message types covered:
  device_automation/trigger/list           — list_triggers
  device_automation/condition/list         — list_conditions
  device_automation/action/list            — list_actions
  device_automation/trigger/capabilities   — trigger_capabilities
  device_automation/condition/capabilities — condition_capabilities
  device_automation/action/capabilities    — action_capabilities
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import device_automation


DEVICE_ID = "abc123def456"

SAMPLE_TRIGGERS = [
    {"device_id": DEVICE_ID, "domain": "zha", "type": "device_offline"},
    {"device_id": DEVICE_ID, "domain": "zha", "type": "device_online"},
]
SAMPLE_CONDITIONS = [
    {"device_id": DEVICE_ID, "domain": "zha", "type": "is_on"},
]
SAMPLE_ACTIONS = [
    {"device_id": DEVICE_ID, "domain": "zha", "type": "toggle"},
    {"device_id": DEVICE_ID, "domain": "zha", "type": "turn_on"},
    {"device_id": DEVICE_ID, "domain": "zha", "type": "turn_off"},
]
SAMPLE_TRIGGER = SAMPLE_TRIGGERS[0]
SAMPLE_CONDITION = SAMPLE_CONDITIONS[0]
SAMPLE_ACTION = SAMPLE_ACTIONS[0]

SAMPLE_CAPABILITIES = {
    "extra_fields": [
        {"name": "for", "optional": True, "type": "positive_time_period_dict"},
    ]
}


class TestDeviceAutomation:
    # ────────────────────────────────────────── list_triggers ────────────────

    def test_list_triggers_happy_path_payload(self, fake_client):
        """list_triggers sends ``device_automation/trigger/list`` with {device_id}."""
        fake_client.set_ws("device_automation/trigger/list", SAMPLE_TRIGGERS)
        device_automation.list_triggers(fake_client, device_id=DEVICE_ID)
        call = fake_client.ws_calls[-1]
        assert call["type"] == "device_automation/trigger/list"
        assert call["payload"] == {"device_id": DEVICE_ID}

    def test_list_triggers_returns_list(self, fake_client):
        """list_triggers returns the list from the WS response."""
        fake_client.set_ws("device_automation/trigger/list", SAMPLE_TRIGGERS)
        result = device_automation.list_triggers(fake_client, device_id=DEVICE_ID)
        assert result == SAMPLE_TRIGGERS
        assert isinstance(result, list)

    def test_list_triggers_empty_device_id_raises(self, fake_client):
        """list_triggers raises ValueError when device_id is empty."""
        with pytest.raises(ValueError, match="device_id is required"):
            device_automation.list_triggers(fake_client, device_id="")

    # ────────────────────────────────────────── list_conditions ──────────────

    def test_list_conditions_happy_path_payload(self, fake_client):
        """list_conditions sends ``device_automation/condition/list`` with {device_id}."""
        fake_client.set_ws("device_automation/condition/list", SAMPLE_CONDITIONS)
        device_automation.list_conditions(fake_client, device_id=DEVICE_ID)
        call = fake_client.ws_calls[-1]
        assert call["type"] == "device_automation/condition/list"
        assert call["payload"] == {"device_id": DEVICE_ID}

    def test_list_conditions_returns_list(self, fake_client):
        """list_conditions returns the list from the WS response."""
        fake_client.set_ws("device_automation/condition/list", SAMPLE_CONDITIONS)
        result = device_automation.list_conditions(fake_client, device_id=DEVICE_ID)
        assert result == SAMPLE_CONDITIONS
        assert isinstance(result, list)

    def test_list_conditions_empty_device_id_raises(self, fake_client):
        """list_conditions raises ValueError when device_id is empty."""
        with pytest.raises(ValueError, match="device_id is required"):
            device_automation.list_conditions(fake_client, device_id="")

    # ────────────────────────────────────────── list_actions ─────────────────

    def test_list_actions_happy_path_payload(self, fake_client):
        """list_actions sends ``device_automation/action/list`` with {device_id}."""
        fake_client.set_ws("device_automation/action/list", SAMPLE_ACTIONS)
        device_automation.list_actions(fake_client, device_id=DEVICE_ID)
        call = fake_client.ws_calls[-1]
        assert call["type"] == "device_automation/action/list"
        assert call["payload"] == {"device_id": DEVICE_ID}

    def test_list_actions_returns_list(self, fake_client):
        """list_actions returns the list from the WS response."""
        fake_client.set_ws("device_automation/action/list", SAMPLE_ACTIONS)
        result = device_automation.list_actions(fake_client, device_id=DEVICE_ID)
        assert result == SAMPLE_ACTIONS
        assert isinstance(result, list)

    def test_list_actions_empty_device_id_raises(self, fake_client):
        """list_actions raises ValueError when device_id is empty."""
        with pytest.raises(ValueError, match="device_id is required"):
            device_automation.list_actions(fake_client, device_id="")

    # ──────────────────────────────────────── trigger_capabilities ───────────

    def test_trigger_capabilities_happy_path_payload(self, fake_client):
        """trigger_capabilities sends ``device_automation/trigger/capabilities``
        with {trigger}."""
        fake_client.set_ws(
            "device_automation/trigger/capabilities", SAMPLE_CAPABILITIES
        )
        device_automation.trigger_capabilities(
            fake_client, trigger=SAMPLE_TRIGGER
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "device_automation/trigger/capabilities"
        assert call["payload"] == {"trigger": SAMPLE_TRIGGER}

    def test_trigger_capabilities_returns_schema(self, fake_client):
        """trigger_capabilities returns the capabilities dict from the WS response."""
        fake_client.set_ws(
            "device_automation/trigger/capabilities", SAMPLE_CAPABILITIES
        )
        result = device_automation.trigger_capabilities(
            fake_client, trigger=SAMPLE_TRIGGER
        )
        assert result == SAMPLE_CAPABILITIES

    def test_trigger_capabilities_empty_dict_raises(self, fake_client):
        """trigger_capabilities raises ValueError when trigger is an empty dict."""
        with pytest.raises(ValueError, match="trigger must be a non-empty dict"):
            device_automation.trigger_capabilities(fake_client, trigger={})

    def test_trigger_capabilities_non_dict_raises(self, fake_client):
        """trigger_capabilities raises ValueError when trigger is not a dict."""
        with pytest.raises(ValueError, match="trigger must be a non-empty dict"):
            device_automation.trigger_capabilities(
                fake_client, trigger="not-a-dict"
            )

    # ──────────────────────────────────────── condition_capabilities ─────────

    def test_condition_capabilities_happy_path_payload(self, fake_client):
        """condition_capabilities sends
        ``device_automation/condition/capabilities`` with {condition}."""
        fake_client.set_ws(
            "device_automation/condition/capabilities", SAMPLE_CAPABILITIES
        )
        device_automation.condition_capabilities(
            fake_client, condition=SAMPLE_CONDITION
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "device_automation/condition/capabilities"
        assert call["payload"] == {"condition": SAMPLE_CONDITION}

    def test_condition_capabilities_returns_schema(self, fake_client):
        """condition_capabilities returns the capabilities dict."""
        fake_client.set_ws(
            "device_automation/condition/capabilities", SAMPLE_CAPABILITIES
        )
        result = device_automation.condition_capabilities(
            fake_client, condition=SAMPLE_CONDITION
        )
        assert result == SAMPLE_CAPABILITIES

    def test_condition_capabilities_empty_dict_raises(self, fake_client):
        """condition_capabilities raises ValueError when condition is an empty dict."""
        with pytest.raises(ValueError, match="condition must be a non-empty dict"):
            device_automation.condition_capabilities(fake_client, condition={})

    def test_condition_capabilities_non_dict_raises(self, fake_client):
        """condition_capabilities raises ValueError when condition is not a dict."""
        with pytest.raises(ValueError, match="condition must be a non-empty dict"):
            device_automation.condition_capabilities(
                fake_client, condition=["not", "a", "dict"]
            )

    # ──────────────────────────────────────── action_capabilities ────────────

    def test_action_capabilities_happy_path_payload(self, fake_client):
        """action_capabilities sends ``device_automation/action/capabilities``
        with {action}."""
        fake_client.set_ws(
            "device_automation/action/capabilities", SAMPLE_CAPABILITIES
        )
        device_automation.action_capabilities(
            fake_client, action=SAMPLE_ACTION
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "device_automation/action/capabilities"
        assert call["payload"] == {"action": SAMPLE_ACTION}

    def test_action_capabilities_returns_schema(self, fake_client):
        """action_capabilities returns the capabilities dict."""
        fake_client.set_ws(
            "device_automation/action/capabilities", SAMPLE_CAPABILITIES
        )
        result = device_automation.action_capabilities(
            fake_client, action=SAMPLE_ACTION
        )
        assert result == SAMPLE_CAPABILITIES

    def test_action_capabilities_empty_dict_raises(self, fake_client):
        """action_capabilities raises ValueError when action is an empty dict."""
        with pytest.raises(ValueError, match="action must be a non-empty dict"):
            device_automation.action_capabilities(fake_client, action={})

    def test_action_capabilities_non_dict_raises(self, fake_client):
        """action_capabilities raises ValueError when action is not a dict."""
        with pytest.raises(ValueError, match="action must be a non-empty dict"):
            device_automation.action_capabilities(
                fake_client, action=None
            )

    # ──────────────────────────────────────── summarise_device ───────────────

    def test_summarise_device_happy_path_all_three_keys(self, fake_client):
        """summarise_device returns a dict with triggers/conditions/actions keys."""
        fake_client.set_ws("device_automation/trigger/list", SAMPLE_TRIGGERS)
        fake_client.set_ws("device_automation/condition/list", SAMPLE_CONDITIONS)
        fake_client.set_ws("device_automation/action/list", SAMPLE_ACTIONS)
        result = device_automation.summarise_device(
            fake_client, device_id=DEVICE_ID
        )
        assert "triggers" in result
        assert "conditions" in result
        assert "actions" in result

    def test_summarise_device_values_match_list_responses(self, fake_client):
        """summarise_device aggregates the three list responses correctly."""
        fake_client.set_ws("device_automation/trigger/list", SAMPLE_TRIGGERS)
        fake_client.set_ws("device_automation/condition/list", SAMPLE_CONDITIONS)
        fake_client.set_ws("device_automation/action/list", SAMPLE_ACTIONS)
        result = device_automation.summarise_device(
            fake_client, device_id=DEVICE_ID
        )
        assert result["triggers"] == SAMPLE_TRIGGERS
        assert result["conditions"] == SAMPLE_CONDITIONS
        assert result["actions"] == SAMPLE_ACTIONS

    def test_summarise_device_empty_device_id_raises(self, fake_client):
        """summarise_device raises ValueError when device_id is empty."""
        with pytest.raises(ValueError, match="device_id is required"):
            device_automation.summarise_device(fake_client, device_id="")

    def test_summarise_device_return_shape(self, fake_client):
        """summarise_device returns a dict with exactly the expected keys."""
        fake_client.set_ws("device_automation/trigger/list", [])
        fake_client.set_ws("device_automation/condition/list", [])
        fake_client.set_ws("device_automation/action/list", [])
        result = device_automation.summarise_device(
            fake_client, device_id=DEVICE_ID
        )
        assert set(result.keys()) == {"triggers", "conditions", "actions"}
        assert isinstance(result["triggers"], list)
        assert isinstance(result["conditions"], list)
        assert isinstance(result["actions"], list)
