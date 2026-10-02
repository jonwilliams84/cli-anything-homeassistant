"""Unit tests for core/knx.py — payload shapes, guards and refusals.

Uses the shared FakeClient; no Home Assistant needed. The ws_calls recorder
asserts the exact WS command and payload each function builds, because the
knx integration's entity-store schema is strict (platform restricted to
switch/light, one of name/device_info required, update REPLACES the data)
and its absent-integration refusal is the same ``unknown_command`` a typo
gets — shapes the wrappers must get right before HA ever sees them.
"""

from __future__ import annotations

import threading

import pytest

from cli_anything.homeassistant.core import knx as knx_core
from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

from .conftest import FakeClient, SubscribingFakeClient


@pytest.fixture
def client():
    return FakeClient()


@pytest.fixture
def sub_client():
    return SubscribingFakeClient()


def _last_ws(client):
    return client.ws_calls[-1]


# ── availability ────────────────────────────────────────────────────────────


class TestAvailable:
    def test_loaded(self, client):
        client.set_ws("get_config", {"components": ["knx", "hue"]})
        out = knx_core.available(client)
        assert out["available"] is True
        assert "works here" in out["note"]

    def test_not_loaded(self, client):
        client.set_ws("get_config", {"components": ["hue"]})
        out = knx_core.available(client)
        assert out["available"] is False
        assert "knx" in out["note"]

    def test_get_config_failure_is_NOT_a_wrong_answer(self, client):
        """An unreachable instance must NOT be reported as 'not loaded'."""
        client.set_ws_error("get_config", "unknown_error", "boom")
        with pytest.raises(HomeAssistantError, match="boom"):
            knx_core.available(client)


# ── the absent guard ────────────────────────────────────────────────────────


class TestAbsentGuard:
    def test_unknown_command_becomes_the_note(self, client):
        client.set_ws_error("knx/info", "unknown_command", "Invalid")
        with pytest.raises(HomeAssistantError, match="no KNX bus"):
            knx_core.info(client)

    def test_names_the_core_install_packages(self, client):
        client.set_ws_error("knx/group_monitor_info", "unknown_command", "Invalid")
        with pytest.raises(HomeAssistantError, match="xknx"):
            knx_core.group_monitor(client)

    def test_the_half_loaded_edge_is_named_too(self, client):
        """'KNX integration not loaded.' rides home_assistant_error — same note."""
        client.set_ws_error("knx/info", "home_assistant_error", "KNX integration not loaded.")
        with pytest.raises(HomeAssistantError, match="no KNX bus"):
            knx_core.info(client)

    def test_unrelated_home_assistant_error_passes_through(self, client):
        client.set_ws_error("knx/info", "home_assistant_error", "tunnel dead")
        with pytest.raises(HomeAssistantError, match="tunnel dead"):
            knx_core.info(client)

    def test_other_codes_pass_through(self, client):
        client.set_ws_error("knx/info", "unauthorized", "no")
        with pytest.raises(HomeAssistantError, match="unauthorized"):
            knx_core.info(client)

    def test_available_does_not_go_through_the_guard(self, client):
        """available answers the components list, never the missing command."""
        client.set_ws("get_config", {"components": []})
        assert knx_core.available(client)["available"] is False


# ── information ─────────────────────────────────────────────────────────────


class TestInformation:
    def test_info_payload_and_result(self, client):
        client.set_ws("knx/info", {"connected": True, "current_address": "1.1.1"})
        out = knx_core.info(client)
        assert out["connected"] is True
        assert _last_ws(client)["type"] == "knx/info"

    def test_group_monitor(self, client):
        client.set_ws("knx/group_monitor_info", {"recent_telegrams": [1], "project_loaded": True})
        out = knx_core.group_monitor(client)
        assert out["project_loaded"] is True

    def test_group_telegrams(self, client):
        client.set_ws("knx/group_telegrams", [{"ga": "1/1/7"}])
        out = knx_core.group_telegrams(client)
        assert out[0]["ga"] == "1/1/7"


class TestSubscribeTelegrams:
    def test_no_stop_no_max_is_a_refusal(self, sub_client):
        with pytest.raises(ValueError, match="stop_event or max_events"):
            knx_core.subscribe_telegrams(sub_client, lambda e: None)

    def test_recorded_shape_and_delivery(self, sub_client):
        sub_client.queue_events({"destination_address": "1/1/7"})
        seen = []
        stop = threading.Event()
        knx_core.subscribe_telegrams(sub_client, seen.append, stop_event=stop)
        assert sub_client.subscribe_calls[-1][0] == "knx/subscribe_telegrams"
        assert seen == [{"destination_address": "1/1/7"}]

    def test_max_events(self, sub_client):
        sub_client.queue_events(*[{"n": i} for i in range(5)])
        seen = []
        knx_core.subscribe_telegrams(sub_client, seen.append, max_events=2)
        assert len(seen) == 2

    def test_not_callable_on_event(self, sub_client):
        with pytest.raises(ValueError, match="callable"):
            knx_core.subscribe_telegrams(sub_client, "nope", max_events=1)

    def test_unknown_command_raises_the_note(self, sub_client):
        """The subscribe path guards the same note as the request/response path."""

        def boom(msg_type, payload, on_message, stop_event):
            raise HomeAssistantError("Invalid", code="unknown_command")

        sub_client.ws_subscribe = boom
        with pytest.raises(HomeAssistantError, match="no KNX bus"):
            knx_core.subscribe_telegrams(sub_client, lambda e: None, max_events=1)


# ── project (ETS) ───────────────────────────────────────────────────────────


class TestProject:
    def test_project_get(self, client):
        client.set_ws("knx/get_knx_project", {"project_loaded": True})
        assert knx_core.project_get(client)["project_loaded"] is True

    def test_project_process_payload_and_ack_shape(self, client):
        client.set_ws("knx/project_file_process", None)
        out = knx_core.project_process(client, "file_123", "hunter2")
        assert _last_ws(client)["payload"] == {
            "file_id": "file_123",
            "password": "hunter2",
        }
        assert out["result"] == "ok"
        assert "project-get" in out["note"]

    def test_project_process_nonempty_result_is_returned(self, client):
        client.set_ws("knx/project_file_process", {"parsed": 42})
        assert knx_core.project_process(client, "f", "") == {"result": {"parsed": 42}}

    def test_project_process_empty_file_id(self, client):
        with pytest.raises(ValueError, match="file_id"):
            knx_core.project_process(client, "", "pw")

    def test_project_process_error_names_the_action(self, client):
        client.set_ws_error("knx/project_file_process", "home_assistant_error", "bad password")
        with pytest.raises(HomeAssistantError, match="bad password"):
            knx_core.project_process(client, "f", "wrong")

    def test_project_remove_ack_says_what_it_means(self, client):
        client.set_ws("knx/project_file_remove", None)
        out = knx_core.project_remove(client)
        assert _last_ws(client)["type"] == "knx/project_file_remove"
        assert "raw addresses" in out["note"]


# ── entity store ────────────────────────────────────────────────────────────


SWITCH_DATA = {"ga_switch": {"write": [["1/1/7"]], "state": [["1/1/8"]]}}


class TestEntityPayloadShape:
    def test_platform_is_lowercased_and_checked(self, client):
        client.set_ws("knx/validate_entity", {"success": True})
        knx_core.validate_entity(client, "SWITCH", SWITCH_DATA, name="n")
        assert _last_ws(client)["payload"]["platform"] == "switch"

    def test_unsupported_platform_is_refused_client_side(self, client):
        with pytest.raises(ValueError, match="not one of the KNX entity-store"):
            knx_core.validate_entity(client, "climate", SWITCH_DATA, name="n")

    def test_empty_data_is_PASSED_THROUGH_to_the_server(self, client):
        """HA's structured validation result is the product of validate — a
        client-side refusal would hide which keys the platform data misses."""
        client.set_ws("knx/validate_entity", {"success": False, "error": "ga_switch required"})
        knx_core.validate_entity(client, "switch", {}, name="n")
        assert _last_ws(client)["payload"]["data"] == {}

    def test_data_must_be_a_dict(self, client):
        with pytest.raises(ValueError, match="JSON object"):
            knx_core.validate_entity(client, "switch", ["x"], name="n")

    def test_one_of_name_or_device_is_required(self, client):
        """HA's message names neither CLI spelling; ours names both options."""
        with pytest.raises(ValueError, match="--name.*--device|--device.*--name"):
            knx_core.validate_entity(client, "switch", SWITCH_DATA)

    def test_name_and_device_and_category_flow_through(self, client):
        client.set_ws("knx/validate_entity", {"success": True})
        knx_core.validate_entity(
            client, "light", {"ga_switch": {"write": [["1/2/9"]]}},
            name="Hall", device_info="dev-uuid", entity_category="diagnostic",
        )
        payload = _last_ws(client)["payload"]
        assert payload["name"] == "Hall"
        assert payload["device_info"] == "dev-uuid"
        assert payload["entity_category"] == "diagnostic"
        assert payload["data"]["ga_switch"]["write"] == [["1/2/9"]]

    def test_bad_category_refused(self, client):
        with pytest.raises(ValueError, match="config.*diagnostic"):
            knx_core.validate_entity(client, "switch", SWITCH_DATA, name="n", entity_category="silly")


class TestEntityStoreCommands:
    def test_validate_entity_sends_the_shared_shape(self, client):
        client.set_ws("knx/validate_entity", {"success": True})
        out = knx_core.validate_entity(client, "switch", SWITCH_DATA, name="Hall Light")
        assert out == {"success": True}
        call = _last_ws(client)
        assert call["type"] == "knx/validate_entity"
        assert call["payload"] == {
            "platform": "switch",
            "data": SWITCH_DATA,
            "name": "Hall Light",
        }

    def test_create_entity(self, client):
        client.set_ws("knx/create_entity", {"success": True, "entity_id": "switch.hall"})
        out = knx_core.create_entity(client, "switch", SWITCH_DATA, name="Hall Light")
        assert out["entity_id"] == "switch.hall"
        assert _last_ws(client)["type"] == "knx/create_entity"

    def test_update_entity_carries_entity_id(self, client):
        client.set_ws("knx/update_entity", {"success": True})
        knx_core.update_entity(client, "switch.hall", "switch", SWITCH_DATA, name="Hall")
        payload = _last_ws(client)["payload"]
        assert payload["entity_id"] == "switch.hall"
        assert payload["platform"] == "switch"

    def test_update_entity_empty_id_refused(self, client):
        with pytest.raises(ValueError, match="entity_id"):
            knx_core.update_entity(client, "", "switch", SWITCH_DATA, name="n")

    def test_create_entity_failure_names_the_action(self, client):
        client.set_ws_error("knx/create_entity", "home_assistant_error", "dup id")
        with pytest.raises(HomeAssistantError, match="^knx create-entity:") as exc:
            knx_core.create_entity(client, "switch", SWITCH_DATA, name="n")
        assert exc.value.code == "home_assistant_error"

    def test_update_entity_failure_names_the_action(self, client):
        client.set_ws_error("knx/update_entity", "home_assistant_error", "boom")
        with pytest.raises(HomeAssistantError, match="^knx update-entity:"):
            knx_core.update_entity(client, "switch.hall", "switch", SWITCH_DATA, name="n")

    def test_entity_config_failure_names_the_action(self, client):
        client.set_ws_error("knx/get_entity_config", "home_assistant_error", "missing")
        with pytest.raises(HomeAssistantError, match="^knx entity-config:"):
            knx_core.entity_config(client, "switch.hall")

    def test_delete_entity_payload_and_ack(self, client):
        client.set_ws("knx/delete_entity", None)
        out = knx_core.delete_entity(client, "switch.hall")
        assert _last_ws(client)["payload"] == {"entity_id": "switch.hall"}
        assert "switch.hall" in out["note"]

    def test_delete_entity_empty_id(self, client):
        with pytest.raises(ValueError, match="entity_id"):
            knx_core.delete_entity(client, "  ")

    def test_list_entities(self, client):
        client.set_ws("knx/get_entity_entries", [{"entity_id": "switch.hall"}])
        out = knx_core.list_entities(client)
        assert out[0]["entity_id"] == "switch.hall"

    def test_entity_config(self, client):
        client.set_ws("knx/get_entity_config", {"platform": "switch", "data": SWITCH_DATA})
        out = knx_core.entity_config(client, "switch.hall")
        assert out["platform"] == "switch"


# ── devices ─────────────────────────────────────────────────────────────────


class TestCreateDevice:
    def test_payload_with_and_without_area(self, client):
        client.set_ws("knx/create_device", {"id": "d1"})
        knx_core.create_device(client, "Hall Bus Unit", area_id="a1")
        assert _last_ws(client)["payload"] == {"name": "Hall Bus Unit", "area_id": "a1"}
        client.set_ws("knx/create_device", {"id": "d2"})
        knx_core.create_device(client, "Other")
        assert _last_ws(client)["payload"] == {"name": "Other"}

    def test_empty_name_refused(self, client):
        with pytest.raises(ValueError, match="name"):
            knx_core.create_device(client, "   ")
