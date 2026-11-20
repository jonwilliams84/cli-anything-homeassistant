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


# ── pairing: inclusion / exclusion runs (v1.63.0 refine pass) ───────────────


class TestRunPairing:
    """`add_node` / `remove_node` — the ack-then-stream-to-outcome shape."""

    def test_add_node_streams_to_node_added(self, client):
        client.set_run_events(
            {"event": "inclusion started"},
            {"event": "node found", "node": {"nodeId": 9}},
            {"event": "node added", "node": {"node_id": 9, "status": 1, "ready": False}},
        )
        out = zwave_core.add_node(client, "e1")
        assert out["result"] == "ok"
        assert out["outcome"] == "node added"
        assert "node 9 added" in out["note"]
        call = client.run_event_calls[-1]
        assert call["type"] == "zwave_js/add_node"
        assert call["payload"] == {"entry_id": "e1"}
        assert call["timeout"] == 300.0  # pairing waits for a button press

    def test_add_node_default_strategy_not_sent(self, client):
        """The schema defaults `inclusion_strategy` — sending it adds nothing."""
        client.set_run_events({"event": "node added", "node": {}})
        zwave_core.add_node(client, "e1")
        assert "inclusion_strategy" not in client.run_event_calls[-1]["payload"]

    def test_add_node_named_strategy(self, client):
        client.set_run_events({"event": "node added", "node": {}})
        zwave_core.add_node(client, "e1", strategy="security-s2")
        assert client.run_event_calls[-1]["payload"]["inclusion_strategy"] == 4

    def test_add_node_raw_strategy_id(self, client):
        client.set_run_events({"event": "node added", "node": {}})
        zwave_core.add_node(client, "e1", strategy=2)
        assert client.run_event_calls[-1]["payload"]["inclusion_strategy"] == 2

    def test_add_node_refuses_smart_start_strategy(self, client):
        """HA's schema refuses SMART_START — SmartStart rides a provisioning option."""
        with pytest.raises(ValueError, match="smart_start"):
            zwave_core.add_node(client, "e1", strategy="smart_start")
        assert not client.run_event_calls

    def test_add_node_provisioning_options_are_mutually_exclusive(self, client):
        with pytest.raises(ValueError, match="at most one"):
            zwave_core.add_node(client, "e1", qr_code_string="90:…", dsk="33005-…")

    def test_add_node_qr_rides_the_run(self, client):
        """A QR option is provisioning, NOT a SmartStart strategy — the schema
        refuses strategy 1, and `inclusion_strategy` defaults client-side."""
        client.set_run_events({"event": "node added", "node": {}})
        zwave_core.add_node(client, "e1", qr_code_string="90:00000,1")
        payload = client.run_event_calls[-1]["payload"]
        assert payload["qr_code_string"] == "90:00000,1"
        assert "inclusion_strategy" not in payload

    def test_add_node_failure_outcome(self, client):
        client.set_run_events({"event": "inclusion started"}, {"event": "inclusion failed"})
        out = zwave_core.add_node(client, "e1")
        assert out["result"] == "failed"
        assert out["outcome"] == "inclusion failed"

    def test_add_node_timeout_reports_pending(self, client):
        """No terminal event in the window = still pairing, not an error."""
        client.set_run_events({"event": "inclusion started"})
        out = zwave_core.add_node(client, "e1")
        assert out["result"] == "pending"
        assert "add-node" in out["note"] or "pairing" in out["note"]

    def test_add_node_absent_integration_names_it(self, client):
        client.set_ws_error("zwave_js/add_node", "unknown_command", "Invalid")
        with pytest.raises(HomeAssistantError, match="no Z-Wave controller"):
            zwave_core.add_node(client, "e1")

    def test_custom_timeout_rides_the_call(self, client):
        client.set_run_events({"event": "node added", "node": {}})
        zwave_core.add_node(client, "e1", timeout=30)
        assert client.run_event_calls[-1]["timeout"] == 30

    def test_remove_node_streams_to_node_removed(self, client):
        client.set_run_events(
            {"event": "exclusion started"},
            {"event": "node removed", "node": {"node_id": 4, "reason": "excluded"}},
        )
        out = zwave_core.remove_node(client, "e1")
        assert out["result"] == "ok"
        assert "node 4 removed" in out["note"]
        assert client.run_event_calls[-1]["type"] == "zwave_js/remove_node"
        assert client.run_event_calls[-1]["payload"] == {"entry_id": "e1"}

    def test_remove_node_exclusion_failed(self, client):
        client.set_run_events({"event": "exclusion failed"})
        out = zwave_core.remove_node(client, "e1")
        assert out["result"] == "failed"

    def test_remove_node_named_strategy(self, client):
        client.set_run_events({"event": "node removed", "node": {"node_id": 1}})
        zwave_core.remove_node(client, "e1", strategy="default")
        assert client.run_event_calls[-1]["payload"] == {"entry_id": "e1"}

    def test_replace_failed_node_uses_device_id(self, client):
        client.set_ws("config/entity_registry/get", {"device_id": "dev-9"})
        client.set_run_events({"event": "node added", "node": {"node_id": 9}})
        zwave_core.replace_failed_node(client, "lock.front")
        call = client.run_event_calls[-1]
        assert call["type"] == "zwave_js/replace_failed_node"
        assert call["payload"] == {"device_id": "dev-9"}

    def test_replace_failed_node_unknown_entity(self, client):
        client.set_ws("config/entity_registry/get", {})
        with pytest.raises(ValueError, match="not linked"):
            zwave_core.replace_failed_node(client, "lock.ghost")


class TestPairingControls:
    def test_stop_inclusion(self, client):
        client.set_ws("zwave_js/stop_inclusion", True)
        out = zwave_core.stop_inclusion(client, "e1")
        assert out["result"] == "ok"
        assert client.ws_calls[-1]["payload"] == {"entry_id": "e1"}

    def test_stop_exclusion(self, client):
        client.set_ws("zwave_js/stop_exclusion", True)
        zwave_core.stop_exclusion(client, "e1")
        assert client.ws_calls[-1]["payload"] == {"entry_id": "e1"}

    def test_cancel_secure_bootstrap_s2(self, client):
        client.set_ws("zwave_js/cancel_secure_bootstrap_s2", None)
        zwave_core.cancel_secure_bootstrap_s2(client, "e1")
        assert client.ws_calls[-1]["type"] == "zwave_js/cancel_secure_bootstrap_s2"

    def test_blank_entry_id_refused_everywhere(self, client):
        for fn in (
            zwave_core.stop_inclusion,
            zwave_core.stop_exclusion,
            zwave_core.cancel_secure_bootstrap_s2,
        ):
            with pytest.raises(ValueError, match="entry_id"):
                fn(client, "  ")


class TestS2Callbacks:
    def test_grant_by_name(self, client):
        zwave_core.grant_security_classes(client, "e1", ["s2_authenticated", "s0_legacy"])
        payload = client.ws_calls[-1]["payload"]
        # Names are sent as the ENUM NAMES HA's vol.Coerce(SecurityClass) likes.
        assert payload == {"entry_id": "e1", "securityClasses": ["S2_Authenticated", "S0_Legacy"]}

    def test_grant_by_id(self, client):
        zwave_core.grant_security_classes(client, "e1", [0, 1])
        assert client.ws_calls[-1]["payload"]["securityClasses"] == [0, 1]

    def test_grant_rejects_unknown_names(self, client):
        with pytest.raises(ValueError, match="unknown security class"):
            zwave_core.grant_security_classes(client, "e1", ["s2_titanium"])

    def test_grant_rejects_ids_out_of_range(self, client):
        with pytest.raises(ValueError, match="0-3"):
            zwave_core.grant_security_classes(client, "e1", [9])

    def test_grant_rejects_empty(self, client):
        with pytest.raises(ValueError, match="at least one"):
            zwave_core.grant_security_classes(client, "e1", [])

    def test_grant_client_side_auth_rides(self, client):
        zwave_core.grant_security_classes(client, "e1", ["s2_authenticated"], client_side_auth=True)
        assert client.ws_calls[-1]["payload"]["clientSideAuth"] is True

    def test_validate_dsk_pin(self, client):
        zwave_core.validate_dsk_and_enter_pin(client, "e1", "12345")
        assert client.ws_calls[-1]["payload"] == {"entry_id": "e1", "pin": "12345"}

    def test_validate_dsk_pin_required(self, client):
        with pytest.raises(ValueError, match="PIN"):
            zwave_core.validate_dsk_and_enter_pin(client, "e1", "  ")


class TestSmartStartProvisioning:
    def test_provision_from_qr(self, client):
        zwave_core.provision_smart_start_node(client, "e1", qr_code_string="90:00000,1")
        payload = client.ws_calls[-1]["payload"]
        assert payload == {"entry_id": "e1", "qr_code_string": "90:00000,1"}
        assert client.ws_calls[-1]["type"] == "zwave_js/provision_smart_start_node"

    def test_provision_requires_a_qr(self, client):
        with pytest.raises(ValueError, match="QR"):
            zwave_core.provision_smart_start_node(client, "e1", qr_code_string=" ")

    def test_unprovision_by_dsk(self, client):
        zwave_core.unprovision_smart_start_node(client, "e1", dsk="33005-…")
        assert client.ws_calls[-1]["payload"] == {"entry_id": "e1", "dsk": "33005-…"}

    def test_unprovision_by_node_id(self, client):
        zwave_core.unprovision_smart_start_node(client, "e1", node_id=7)
        assert client.ws_calls[-1]["payload"] == {"entry_id": "e1", "node_id": 7}

    def test_unprovision_requires_exactly_one(self, client):
        with pytest.raises(ValueError, match="exactly one"):
            zwave_core.unprovision_smart_start_node(client, "e1")
        with pytest.raises(ValueError, match="exactly one"):
            zwave_core.unprovision_smart_start_node(client, "e1", dsk="d", node_id=1)

    def test_get_provisioning_entries(self, client):
        client.set_ws("zwave_js/get_provisioning_entries", [{"dsk": "1-2-3"}])
        out = zwave_core.get_provisioning_entries(client, "e1")
        assert out == [{"dsk": "1-2-3"}]

    def test_parse_qr_code_string(self, client):
        client.set_ws("zwave_js/parse_qr_code_string", {"dsk": "…", "securityClasses": []})
        out = zwave_core.parse_qr_code_string(client, "e1", "90:12345,1")
        assert out["dsk"] == "…"
        assert client.ws_calls[-1]["payload"]["qr_code_string"] == "90:12345,1"

    def test_try_parse_dsk(self, client):
        client.set_ws("zwave_js/try_parse_dsk_from_qr_code_string", {})
        out = zwave_core.try_parse_dsk_from_qr_code_string(client, "e1", "nonsense-but-allowed")
        assert out == {}


# ── command classes / raw config parameters ─────────────────────────────────


class TestCcCommands:
    def test_refresh_cc_values(self, client):
        client.set_ws("config/entity_registry/get", {"device_id": "dev-9"})
        zwave_core.refresh_node_cc_values(client, "lock.front", 112)
        assert client.ws_calls[-1]["payload"] == {"device_id": "dev-9", "command_class_id": 112}

    def test_refresh_cc_values_rejects_non_int(self, client):
        with pytest.raises(ValueError, match="integer"):
            zwave_core.refresh_node_cc_values(client, "lock.front", "112")

    def test_invoke_cc_api_minimal(self, client):
        client.set_ws("config/entity_registry/get", {"device_id": "dev-9"})
        zwave_core.invoke_cc_api(client, "dev-9", 112, "get")
        payload = client.ws_calls[-1]["payload"]
        assert payload == {"device_id": "dev-9", "command_class": 112, "method_name": "get", "parameters": []}

    def test_invoke_cc_api_full(self, client):
        zwave_core.invoke_cc_api(
            client, "dev-9", 64, "set", parameters=[1], endpoint=2, wait_for_result=True
        )
        payload = client.ws_calls[-1]["payload"]
        assert payload["parameters"] == [1]
        assert payload["endpoint"] == 2
        assert payload["wait_for_result"] is True

    def test_invoke_cc_api_requires_a_method(self, client):
        with pytest.raises(ValueError, match="method_name"):
            zwave_core.invoke_cc_api(client, "dev-9", 112, "  ")

    def test_invoke_cc_api_rejects_bad_parameters_json(self, client):
        # parameters must be a LIST — HA's schema says `list`, not `dict`
        with pytest.raises(ValueError, match="list"):
            zwave_core.invoke_cc_api(client, "dev-9", 64, "set", parameters={"0": True})

    def test_supports_feature(self, client):
        client.set_ws("zwave_js/supports_feature", {"supported": True})
        out = zwave_core.supports_feature(client, "e1", 0)
        assert out == {"supported": True}
        assert client.ws_calls[-1]["payload"] == {"entry_id": "e1", "feature": 0}

    def test_supports_feature_rejects_bad_id(self, client):
        with pytest.raises(ValueError, match="feature"):
            zwave_core.supports_feature(client, "e1", "smartstart")


class TestRawConfigParameter:
    def test_get(self, client):
        client.set_ws("zwave_js/get_raw_config_parameter", {"value": 3})
        zwave_core.get_raw_config_parameter(client, "dev-9", 7)
        assert client.ws_calls[-1]["payload"] == {"device_id": "dev-9", "property": 7}

    def test_set_by_name(self, client):
        zwave_core.set_raw_config_parameter(
            client, "dev-9", 7, 255, value_size=1, value_format="unsigned-integer"
        )
        payload = client.ws_calls[-1]["payload"]
        assert payload["value_size"] == 1
        assert payload["value_format"] == "UnsignedInteger"

    def test_set_by_id(self, client):
        zwave_core.set_raw_config_parameter(client, "dev-9", 7, -1, value_size=2, value_format=0)
        assert client.ws_calls[-1]["payload"]["value_format"] == 0

    def test_set_rejects_bad_format_names(self, client):
        with pytest.raises(ValueError, match="value_format"):
            zwave_core.set_raw_config_parameter(client, "dev-9", 7, 1, value_size=1, value_format="hex")

    def test_set_rejects_bad_size(self, client):
        for size in (0, 5, 1.5, "1", True):
            with pytest.raises(ValueError, match="value_size"):
                zwave_core.set_raw_config_parameter(
                    client, "dev-9", 7, 1, value_size=size, value_format="bitfield"
                )

    def test_set_rejects_bad_value(self, client):
        with pytest.raises(ValueError, match="value"):
            zwave_core.set_raw_config_parameter(
                client, "dev-9", 7, "255", value_size=1, value_format="bitfield"
            )


# ── firmware ────────────────────────────────────────────────────────────────


class TestFirmware:
    def test_capabilities_by_entity(self, client):
        client.set_ws("config/entity_registry/get", {"device_id": "dev-2"})
        client.set_ws("zwave_js/get_node_firmware_update_capabilities", {"targets": [0]})
        out = zwave_core.get_node_firmware_update_capabilities(client, "light.fan")
        assert out == {"targets": [0]}
        assert client.ws_calls[-1]["payload"] == {"device_id": "dev-2"}

    def test_node_in_progress(self, client):
        client.set_ws("zwave_js/is_node_firmware_update_in_progress", {"inProgress": False})
        zwave_core.is_node_firmware_update_in_progress(client, "dev-2")
        assert client.ws_calls[-1]["type"] == "zwave_js/is_node_firmware_update_in_progress"

    def test_any_in_progress_entry_scoped(self, client):
        client.set_ws("zwave_js/is_any_ota_firmware_update_in_progress", False)
        out = zwave_core.is_any_ota_firmware_update_in_progress(client, "e1")
        assert out is False
        assert client.ws_calls[-1]["payload"] == {"entry_id": "e1"}

    def test_abort(self, client):
        client.set_ws("zwave_js/abort_firmware_update", None)
        out = zwave_core.abort_firmware_update(client, "dev-2")
        assert out["result"] == "ok"
