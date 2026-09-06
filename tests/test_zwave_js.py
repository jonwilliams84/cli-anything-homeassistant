"""Unit tests for core/zwave_js.py — payload shapes, guards and refusals.

Uses the shared FakeClient; no Home Assistant needed. The ws_calls recorder
asserts the exact WS command and payload each function builds, because the
zwave_js integration's schemas are mutually exclusive about identifiers
(entry_id vs device_id) and int-vs-bitmask about values — shapes that a
real HA would reject at the websocket layer if the wrappers got them wrong.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import zwave_js as zwave_core
from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

from .conftest import FakeClient


@pytest.fixture
def client():
    return FakeClient()


def _last_ws(client):
    return client.ws_calls[-1]


# ── availability ────────────────────────────────────────────────────────────


class TestAvailable:
    def test_loaded(self, client):
        client.set_ws("get_config", {"components": ["zwave_js", "mqtt"]})
        out = zwave_core.available(client)
        assert out["available"] is True

    def test_not_loaded(self, client):
        client.set_ws("get_config", {"components": ["hue"]})
        out = zwave_core.available(client)
        assert out["available"] is False
        assert "zwave_js" in out["note"]


class TestAbsentGuard:
    def test_unknown_command_becomes_the_note(self, client):
        """`unknown_command` on any zwave_js/… call names the integration."""
        client.set_ws_error("zwave_js/network_status", "unknown_command", "Invalid")
        with pytest.raises(HomeAssistantError, match="no Z-Wave controller"):
            zwave_core.network_status(client, entry_id="e1")

    def test_other_codes_pass_through(self, client):
        """`unauthorized` is NOT 'not loaded' — it must not be rewritten."""
        client.set_ws_error("zwave_js/network_status", "unauthorized", "no")
        with pytest.raises(HomeAssistantError, match="unauthorized"):
            zwave_core.network_status(client, entry_id="e1")

    def test_service_call_to_an_unloaded_domain_becomes_the_note(self, client):
        """REST 400 with an empty body — the shape an unloaded domain gives."""
        client.set_rest_error("POST", "services/zwave_js/ping", 400)
        with pytest.raises(HomeAssistantError, match="no Z-Wave controller"):
            zwave_core.ping(client, "lock.front")

    def test_service_error_passes_through_when_zwave_js_is_loaded(self, client):
        """A 400 with zwave_js loaded is a REAL error, not an absence."""
        client.set_ws("get_config", {"components": ["zwave_js"]})
        client.set_rest_error("POST", "services/zwave_js/ping", 400)
        with pytest.raises(HomeAssistantError, match="400"):
            zwave_core.ping(client, "lock.front")

    def test_service_guard_survives_a_failing_components_check(self, client):
        """If the availability probe itself fails, surface the ORIGINAL error."""
        client.set_rest_error("POST", "services/zwave_js/ping", 400)
        client.set_ws_error("get_config", "unknown_error", "")
        with pytest.raises(HomeAssistantError, match="400"):
            zwave_core.ping(client, "lock.front")


# ── identifiers ─────────────────────────────────────────────────────────────


class TestResolveDeviceId:
    def test_bare_id_passes_through(self, client):
        assert zwave_core.resolve_device_id(client, "abc123") == "abc123"
        assert client.ws_calls == []

    def test_entity_id_resolves_through_the_registry(self, client):
        client.set_ws("config/entity_registry/get", {"device_id": "dev-9"})
        assert zwave_core.resolve_device_id(client, "lock.front_door") == "dev-9"
        assert client.ws_calls[-1] == {
            "type": "config/entity_registry/get",
            "payload": {"entity_id": "lock.front_door"},
        }

    def test_entity_without_a_device_is_named(self, client):
        client.set_ws("config/entity_registry/get", {})
        with pytest.raises(ValueError, match="lock.orphan"):
            zwave_core.resolve_device_id(client, "lock.orphan")

    def test_empty_is_rejected(self, client):
        with pytest.raises(ValueError, match="required"):
            zwave_core.resolve_device_id(client, "")


# ── network / node reads ────────────────────────────────────────────────────


class TestNetworkStatus:
    def test_by_entry(self, client):
        client.set_ws("zwave_js/network_status", {"home_id": 111})
        out = zwave_core.network_status(client, entry_id="e1")
        assert out["home_id"] == 111
        assert client.ws_calls[-1]["payload"] == {"entry_id": "e1"}

    def test_by_device_via_entity(self, client):
        client.set_ws("config/entity_registry/get", {"device_id": "dev-9"})
        zwave_core.network_status(client, device_id="lock.front")
        assert client.ws_calls[-1]["payload"] == {"device_id": "dev-9"}

    def test_requires_exactly_one_identifier(self, client):
        with pytest.raises(ValueError, match="exactly one"):
            zwave_core.network_status(client)

    def test_both_identifiers_refused(self, client):
        with pytest.raises(ValueError, match="exactly one"):
            zwave_core.network_status(client, entry_id="e", device_id="d")

    def test_blank_entry_id_refused(self, client):
        with pytest.raises(ValueError, match="entry_id"):
            zwave_core.network_status(client, entry_id="  ")


class TestNodeReads:
    @pytest.mark.parametrize(
        "fn,cmd",
        [
            (zwave_core.node_status, "zwave_js/node_status"),
            (zwave_core.node_metadata, "zwave_js/node_metadata"),
            (zwave_core.node_alerts, "zwave_js/node_alerts"),
            (zwave_core.node_capabilities, "zwave_js/node_capabilities"),
            (zwave_core.refresh_node_info, "zwave_js/refresh_node_info"),
            (zwave_core.refresh_node_values, "zwave_js/refresh_node_values"),
            (zwave_core.rebuild_node_routes, "zwave_js/rebuild_node_routes"),
            (zwave_core.remove_failed_node, "zwave_js/remove_failed_node"),
        ],
    )
    def test_each_resolves_the_entity_then_targets_the_device(self, client, fn, cmd):
        client.set_ws("config/entity_registry/get", {"device_id": "dev-1"})
        fn(client, "light.tree")
        assert client.ws_calls[-1] == {"type": cmd, "payload": {"device_id": "dev-1"}}


# ── config parameters ───────────────────────────────────────────────────────


class TestConfigParameters:
    def test_list(self, client):
        client.set_ws("zwave_js/get_config_parameters", {"21-112-0-3": {"property": 3}})
        out = zwave_core.config_parameters(client, "dev-1")
        assert out["21-112-0-3"]["property"] == 3
        assert client.ws_calls[-1]["type"] == "zwave_js/get_config_parameters"


class TestSetConfigParameter:
    def test_minimal_payload(self, client):
        zwave_core.set_config_parameter(client, "dev-1", 3, 1)
        call = client.ws_calls[-1]
        assert call["type"] == "zwave_js/set_config_parameter"
        assert call["payload"] == {
            "device_id": "dev-1",
            "property": 3,
            "endpoint": 0,
            "value": 1,
        }

    def test_property_key_and_endpoint(self, client):
        zwave_core.set_config_parameter(client, "dev-1", 3, 1, property_key=2, endpoint=4)
        payload = client.ws_calls[-1]["payload"]
        assert payload["property_key"] == 2
        assert payload["endpoint"] == 4

    def test_bitmask_value_passes_through(self, client):
        zwave_core.set_config_parameter(client, "dev-1", 3, {"1": True})
        assert client.ws_calls[-1]["payload"]["value"] == {"1": True}

    def test_entity_id_resolution(self, client):
        client.set_ws("config/entity_registry/get", {"device_id": "dev-2"})
        zwave_core.set_config_parameter(client, "lock.front", 1, 0)
        assert client.ws_calls[-1]["payload"]["device_id"] == "dev-2"

    @pytest.mark.parametrize("parameter", ["3", True, 3.5, None])
    def test_non_integer_parameter_refused(self, client, parameter):
        with pytest.raises(ValueError, match="parameter must be an integer"):
            zwave_core.set_config_parameter(client, "dev-1", parameter, 1)

    @pytest.mark.parametrize("value", ["1", True, 1.5, [1], None])
    def test_bad_value_refused(self, client, value):
        with pytest.raises(ValueError, match="value must be an integer or a bitmask"):
            zwave_core.set_config_parameter(client, "dev-1", 3, value)


# ── entry-scoped commands ───────────────────────────────────────────────────


class TestEntryScoped:
    def test_begin_and_stop_rebuild(self, client):
        zwave_core.begin_rebuilding_routes(client, "e1")
        assert client.ws_calls[-1] == {
            "type": "zwave_js/begin_rebuilding_routes",
            "payload": {"entry_id": "e1"},
        }
        zwave_core.stop_rebuilding_routes(client, "e1")
        assert client.ws_calls[-1]["type"] == "zwave_js/stop_rebuilding_routes"

    def test_hard_reset(self, client):
        zwave_core.hard_reset_controller(client, "e1")
        assert client.ws_calls[-1]["type"] == "zwave_js/hard_reset_controller"

    def test_blank_entry_refused(self, client):
        with pytest.raises(ValueError, match="entry_id"):
            zwave_core.begin_rebuilding_routes(client, "")


class TestLogConfig:
    def test_get(self, client):
        client.set_ws("zwave_js/get_log_config", {"level": "info"})
        assert zwave_core.get_log_config(client, "e1")["level"] == "info"

    def test_update_sends_only_passed_fields(self, client):
        zwave_core.update_log_config(client, "e1", level="debug")
        assert client.ws_calls[-1]["payload"] == {
            "entry_id": "e1",
            "config": {"level": "debug"},
        }

    def test_update_all_fields(self, client):
        zwave_core.update_log_config(
            client, "e1", level="off", log_to_file=True, filename="/tmp/z.log", force_console=False
        )
        assert client.ws_calls[-1]["payload"]["config"] == {
            "level": "off",
            "log_to_file": True,
            "filename": "/tmp/z.log",
            "force_console": False,
        }

    def test_update_with_nothing_refused(self, client):
        with pytest.raises(ValueError, match="at least one"):
            zwave_core.update_log_config(client, "e1")


class TestTelemetry:
    def test_status_and_preference(self, client):
        zwave_core.data_collection_status(client, "e1")
        assert client.ws_calls[-1]["type"] == "zwave_js/data_collection_status"
        zwave_core.update_data_collection_preference(client, "e1", opted_in=True)
        payload = client.ws_calls[-1]["payload"]
        assert payload == {"entry_id": "e1", "opted_in": True}

    def test_updates_check_and_install(self, client):
        zwave_core.check_for_config_updates(client, "e1")
        assert client.ws_calls[-1]["type"] == "zwave_js/check_for_config_updates"
        zwave_core.install_config_update(client, "e1")
        assert client.ws_calls[-1]["type"] == "zwave_js/install_config_update"

    def test_integration_settings(self, client):
        zwave_core.integration_settings(client, "e1")
        assert client.ws_calls[-1]["type"] == "zwave_js/get_integration_settings"


# ── node inventory ──────────────────────────────────────────────────────────


class TestListNodes:
    def _devices(self):
        return [
            {
                "id": "d1",
                "name": "Front door",
                "name_by_user": "Front door",
                "identifiers": [["zwave_js", "4032732064-2"]],
            },
            {"id": "d2", "name": "Hue hub", "identifiers": [["hue", "1"]]},
            {"id": "d3", "name": "Motion", "identifiers": []},
        ]

    def test_only_zwave_devices_survive(self, client):
        client.set_ws("config/device_registry/list", self._devices())
        out = zwave_core.list_nodes(client)
        assert [r["id"] for r in out] == ["d1"]
        assert out[0]["node_id"] == "2"

    def test_pattern_filters_on_both_names(self, client):
        client.set_ws(
            "config/device_registry/list",
            [
                {"id": "d1", "name": "Front door", "identifiers": [["zwave_js", "1-2"]]},
                {
                    "id": "d2",
                    "name": "Motion",
                    "name_by_user": "Back porch",
                    "identifiers": [["zwave_js", "1-3"]],
                },
            ],
        )
        assert [r["id"] for r in zwave_core.list_nodes(client, pattern="porch")] == ["d2"]

    def test_identifier_without_node_part(self, client):
        client.set_ws(
            "config/device_registry/list", [{"id": "d1", "identifiers": [["zwave_js", None]]}]
        )
        assert zwave_core.list_nodes(client)[0]["node_id"] is None


# ── services ────────────────────────────────────────────────────────────────


class TestServices:
    def test_ping(self, client):
        zwave_core.ping(client, "sensor.door_battery")
        assert client.calls[-1]["path"] == "services/zwave_js/ping"
        assert client.calls[-1]["payload"] == {"entity_id": "sensor.door_battery"}

    def test_ping_requires_an_entity(self, client):
        with pytest.raises(ValueError, match="entity_id"):
            zwave_core.ping(client, "  ")

    def test_set_lock_usercode(self, client):
        zwave_core.set_lock_usercode(client, "lock.front", 3, "1234")
        assert client.calls[-1]["payload"] == {
            "entity_id": "lock.front",
            "code_slot": 3,
            "usercode": "1234",
        }

    def test_set_lock_usercode_rejects_other_domains(self, client):
        with pytest.raises(ValueError, match="lock.*"):
            zwave_core.set_lock_usercode(client, "light.tree", 3, "1234")

    def test_set_lock_usercode_rejects_bad_slots(self, client):
        for slot in (0, -1, "2", True):
            with pytest.raises(ValueError, match="code_slot"):
                zwave_core.set_lock_usercode(client, "lock.front", slot, "1234")

    def test_clear_lock_usercode(self, client):
        zwave_core.clear_lock_usercode(client, "lock.front", 3)
        assert client.calls[-1]["payload"] == {"entity_id": "lock.front", "code_slot": 3}

    def test_set_lock_configuration(self, client):
        zwave_core.set_lock_configuration(
            client, "lock.front", operation_type="timed", lock_timeout=30
        )
        assert client.calls[-1]["payload"] == {
            "entity_id": "lock.front",
            "operation_type": "timed",
            "lock_timeout": 30,
        }

    def test_set_lock_configuration_operation_types(self, client):
        with pytest.raises(ValueError, match="operation_type"):
            zwave_core.set_lock_configuration(client, "lock.front", operation_type="whenever")
        zwave_core.set_lock_configuration(client, "lock.front", operation_type="constant")
        assert client.calls[-1]["payload"]["operation_type"] == "constant"

    def test_lock_commands_reject_non_lock_entities(self, client):
        with pytest.raises(ValueError, match="lock.*"):
            zwave_core.clear_lock_usercode(client, "switch.fan", 1)
