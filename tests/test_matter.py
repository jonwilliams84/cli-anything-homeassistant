"""Unit tests for core/matter.py — payload shapes, guards and refusals.

Uses the shared FakeClient; no Home Assistant needed. The ws_calls recorder
asserts the exact WS command and payload each function builds, because the
matter integration's schemas are strict about identifier shapes (device_id
vs setup pin vs pairing code) and about which commands carry admin-only
weight upstream — shapes a real HA would reject at the websocket layer if
the wrappers got them wrong.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import matter as matter_core
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
        client.set_ws("get_config", {"components": ["matter", "zwave_js"]})
        out = matter_core.available(client)
        assert out["available"] is True
        assert "works here" in out["note"]

    def test_not_loaded(self, client):
        client.set_ws("get_config", {"components": ["hue"]})
        out = matter_core.available(client)
        assert out["available"] is False
        assert "matter" in out["note"]

    def test_get_config_failure_is_NOT_a_wrong_answer(self, client):
        """An unreachable instance must NOT be reported as 'not loaded'."""
        client.set_ws_error("get_config", "unknown_error", "boom")
        with pytest.raises(HomeAssistantError, match="unknown_error"):
            matter_core.available(client)


class TestAbsentGuard:
    def test_unknown_command_becomes_the_note(self, client):
        client.set_ws_error("matter/commission", "unknown_command", "Invalid")
        with pytest.raises(HomeAssistantError, match="no Matter controller"):
            matter_core.commission(client, "MT:abcdefgh")

    def test_names_the_core_install_reason(self, client):
        client.set_ws_error("matter/ping_node", "unknown_command", "Invalid")
        with pytest.raises(HomeAssistantError, match="python-matter-server"):
            matter_core.ping_node(client, "dev-1")

    def test_other_codes_pass_through(self, client):
        """`unauthorized` is NOT 'not loaded' — it must not be rewritten."""
        client.set_ws_error("matter/commission", "unauthorized", "no")
        with pytest.raises(HomeAssistantError, match="unauthorized"):
            matter_core.commission(client, "MT:abcdefgh")

    def test_the_node_not_found_code_becomes_a_remedy(self, client):
        client.set_ws_error("matter/ping_node", "node_not_found", "no such node")
        with pytest.raises(ValueError, match="matter nodes"):
            matter_core.ping_node(client, "dev-1")


# ── identifiers ─────────────────────────────────────────────────────────────


class TestResolveDeviceId:
    def test_bare_string_passthrough(self, client):
        assert matter_core.resolve_device_id(client, "dev-1") == "dev-1"

    def test_entity_id_resolves_through_the_registry(self, client):
        client.set_ws(
            "config/entity_registry/get", {"entity_id": "light.hall", "device_id": "d9"}
        )
        assert matter_core.resolve_device_id(client, "light.hall") == "d9"
        assert _last_ws(client)["payload"] == {"entity_id": "light.hall"}

    def test_orphan_entity_names_the_entity(self, client):
        client.set_ws("config/entity_registry/get", {"entity_id": "light.hall"})
        with pytest.raises(ValueError, match="light.hall"):
            matter_core.resolve_device_id(client, "light.hall")

    def test_empty_refused(self, client):
        with pytest.raises(ValueError, match="required"):
            matter_core.resolve_device_id(client, "  ")


class TestListNodes:
    DEVICES = [
        {
            "id": "d1",
            "name": "Hall Switch",
            "identifiers": [["matter", "deviceid_00000000AABBCCDD-000000000004D2-MatterNodeDevice"]],
        },
        {
            "id": "d2",
            "name_by_user": "Hue Motion",
            "identifiers": [["matter", "deviceid_00000000AABBCCDD-000000000004D3-3"]],
        },
        {"id": "d3", "name": "Zigbee Bulb", "identifiers": [["zha", "abc"]]},
        {"id": "d4", "name": "Weird Matter Row", "identifiers": [["matter", "not-deviceid"]]},
    ]

    def test_extracts_node_fabric_endpoint(self, client):
        client.set_ws("config/device_registry/list", self.DEVICES)
        nodes = matter_core.list_nodes(client)
        by_id = {n["id"]: n for n in nodes}
        assert set(by_id) == {"d1", "d2", "d4"}
        assert by_id["d1"]["node_id"] == 0x4D2
        assert by_id["d1"]["fabric_id"] == 0xAABBCCDD
        assert by_id["d1"]["endpoint"] is None  # whole-node device
        assert by_id["d2"]["node_id"] == 0x4D3
        assert by_id["d2"]["endpoint"] == 3  # bridged: one row per endpoint

    def test_unparseable_identifier_is_None_never_zero(self, client):
        client.set_ws("config/device_registry/list", self.DEVICES)
        by_id = {n["id"]: n for n in matter_core.list_nodes(client)}
        assert by_id["d4"]["node_id"] is None

    def test_pattern_filters_on_both_name_fields(self, client):
        client.set_ws("config/device_registry/list", self.DEVICES)
        assert [n["id"] for n in matter_core.list_nodes(client, pattern="hall")] == ["d1"]
        assert [n["id"] for n in matter_core.list_nodes(client, pattern="hue")] == ["d2"]

    def test_empty_registry(self, client):
        client.set_ws("config/device_registry/list", [])
        assert matter_core.list_nodes(client) == []


# ── commissioning ───────────────────────────────────────────────────────────


class TestCommission:
    def test_payload_shape(self, client):
        matter_core.commission(client, "MT:abcdefgh", network_only=False)
        assert _last_ws(client)["type"] == "matter/commission"
        assert _last_ws(client)["payload"] == {"code": "MT:abcdefgh", "network_only": False}

    def test_empty_result_is_reported_not_dropped(self, client):
        matter_core.commission(client, "MT:abcdefgh")
        out = matter_core.commission(client, "MT:xyz")
        assert out["result"] == "ok"
        assert "matter nodes" in out["note"]

    def test_network_only_defaults_to_ha_default_true(self, client):
        matter_core.commission(client, "MT:abcdefgh")
        assert _last_ws(client)["payload"]["network_only"] is True

    def test_blank_code_refused(self, client):
        with pytest.raises(ValueError, match="pairing code"):
            matter_core.commission(client, "  ")


class TestCommissionOnNetwork:
    def test_payload_with_ip(self, client):
        matter_core.commission_on_network(client, 12345678, ip_addr="10.0.0.9")
        assert _last_ws(client)["type"] == "matter/commission_on_network"
        assert _last_ws(client)["payload"] == {"pin": 12345678, "ip_addr": "10.0.0.9"}

    def test_payload_without_ip(self, client):
        matter_core.commission_on_network(client, 12345678)
        assert _last_ws(client)["payload"] == {"pin": 12345678}

    def test_pin_must_be_an_int(self, client):
        with pytest.raises(ValueError, match="pin"):
            matter_core.commission_on_network(client, "12345678")  # type: ignore[arg-type]

    @pytest.mark.parametrize("pin", [1, 1234567, 123456789012])
    def test_pin_length_guard(self, client, pin):
        with pytest.raises(ValueError, match="8- or 11-digit"):
            matter_core.commission_on_network(client, pin)

    @pytest.mark.parametrize("pin", [12345678, 12345678901])
    def test_valid_pin_lengths(self, client, pin):
        matter_core.commission_on_network(client, pin)
        assert _last_ws(client)["payload"]["pin"] == pin


class TestNetworkCredentials:
    def test_wifi_payload(self, client):
        matter_core.set_wifi_credentials(client, "home", "hunter2")
        assert _last_ws(client)["type"] == "matter/set_wifi_credentials"
        assert _last_ws(client)["payload"] == {
            "network_name": "home",
            "password": "hunter2",
        }

    def test_wifi_blank_ssid_refused(self, client):
        with pytest.raises(ValueError, match="SSID"):
            matter_core.set_wifi_credentials(client, "  ", "hunter2")

    def test_wifi_password_must_be_a_string(self, client):
        with pytest.raises(ValueError, match="string"):
            matter_core.set_wifi_credentials(client, "home", 123)  # type: ignore[arg-type]

    def test_thread_payload_uses_the_exact_schema_key(self, client):
        matter_core.set_thread(client, "1af303")
        assert _last_ws(client)["type"] == "matter/set_thread"
        assert _last_ws(client)["payload"] == {"thread_operation_dataset": "1af303"}

    def test_thread_blank_dataset_refused(self, client):
        with pytest.raises(ValueError, match="dataset"):
            matter_core.set_thread(client, " ")


# ── node operations ─────────────────────────────────────────────────────────


class TestNodeOperations:
    @pytest.mark.parametrize(
        ("fn", "ws_type"),
        [
            ("node_diagnostics", "matter/node_diagnostics"),
            ("ping_node", "matter/ping_node"),
            ("interview_node", "matter/interview_node"),
            ("open_commissioning_window", "matter/open_commissioning_window"),
        ],
    )
    def test_node_scoped_payloads(self, client, fn, ws_type):
        getattr(matter_core, fn)(client, "dev-1")
        assert _last_ws(client)["type"] == ws_type
        assert _last_ws(client)["payload"] == {"device_id": "dev-1"}

    def test_node_scoped_accepts_an_entity_id(self, client):
        client.set_ws("config/entity_registry/get", {"device_id": "d9"})
        matter_core.ping_node(client, "light.hall")
        assert _last_ws(client)["payload"] == {"device_id": "d9"}

    def test_diagnostics_passthrough_result(self, client):
        client.set_ws("matter/node_diagnostics", {"node_id": 1, "attributes": []})
        out = matter_core.node_diagnostics(client, "dev-1")
        assert out == {"node_id": 1, "attributes": []}

    def test_interview_empty_result_reported(self, client):
        out = matter_core.interview_node(client, "dev-1")
        assert out["result"] == "ok"
        assert "entity states" in out["note"]

    def test_node_not_found_names_the_remedy(self, client):
        client.set_ws_error("matter/ping_node", "node_not_found", "Could not resolve")
        with pytest.raises(ValueError, match="does not resolve to a Matter node"):
            matter_core.ping_node(client, "not-a-matter-device")


class TestRemoveFabric:
    def test_payload_shape(self, client):
        matter_core.remove_fabric(client, "dev-1", 2)
        assert _last_ws(client)["type"] == "matter/remove_matter_fabric"
        assert _last_ws(client)["payload"] == {"device_id": "dev-1", "fabric_index": 2}

    def test_index_bounds(self, client):
        with pytest.raises(ValueError, match="1..254"):
            matter_core.remove_fabric(client, "dev-1", 0)
        with pytest.raises(ValueError, match="1..254"):
            matter_core.remove_fabric(client, "dev-1", 255)

    def test_index_must_be_an_int(self, client):
        with pytest.raises(ValueError, match="integer"):
            matter_core.remove_fabric(client, "dev-1", "2")  # type: ignore[arg-type]

    def test_no_bools_as_index(self, client):
        with pytest.raises(ValueError, match="integer"):
            matter_core.remove_fabric(client, "dev-1", True)

    def test_empty_result_is_reported(self, client):
        out = matter_core.remove_fabric(client, "dev-1", 2)
        assert out["result"] == "ok"
        assert "fabric 2" in out["note"]
