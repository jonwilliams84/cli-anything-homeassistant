"""Unit tests for core/zha.py — payload shapes, guards and refusals.

Uses the shared FakeClient; no Home Assistant needed. The ws_calls recorder
asserts the exact WS command and payload each function builds, because the
zha integration's schemas are strict about shapes a real HA would reject at
the websocket layer if the wrappers got them wrong: IEEE addresses are
EUI-64s, group members ride as {ieee, endpoint_id}, bindings as four-key
objects, channels as 11–26 or "auto", and the cluster command's args/params
are mutually exclusive.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import zha as zha_core
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
        client.set_ws("get_config", {"components": ["zha", "mqtt"]})
        out = zha_core.available(client)
        assert out["available"] is True
        assert "zha is loaded" in out["note"]

    def test_not_loaded(self, client):
        client.set_ws("get_config", {"components": ["hue"]})
        out = zha_core.available(client)
        assert out["available"] is False
        assert "zha" in out["note"]


class TestAbsentGuard:
    def test_unknown_command_becomes_the_note(self, client):
        """`unknown_command` on any zha/… call names the integration."""
        client.set_ws_error("zha/devices", "unknown_command", "Invalid")
        with pytest.raises(HomeAssistantError, match="no ZHA"):
            zha_core.list_devices(client)

    def test_other_codes_pass_through(self, client):
        """`unauthorized` is NOT 'not loaded' — it must not be rewritten."""
        client.set_ws_error("zha/devices", "unauthorized", "no")
        with pytest.raises(HomeAssistantError, match="unauthorized"):
            zha_core.list_devices(client)

    def test_service_call_to_an_unloaded_domain_becomes_the_note(self, client):
        """REST 400 with an empty body — the shape an unloaded domain gives."""
        client.set_rest_error("POST", "services/zha/remove", 400)
        with pytest.raises(HomeAssistantError, match="no ZHA"):
            zha_core.remove_device(client, "00:0d:6f:00:05:7d:2d:34")

    def test_service_error_passes_through_when_zha_is_loaded(self, client):
        """A 400 with zha loaded is a REAL error, not an absence."""
        client.set_ws("get_config", {"components": ["zha"]})
        client.set_rest_error("POST", "services/zha/remove", 400)
        with pytest.raises(HomeAssistantError, match="400"):
            zha_core.remove_device(client, "00:0d:6f:00:05:7d:2d:34")

    def test_service_guard_survives_a_failing_components_check(self, client):
        """If the availability probe itself fails, surface the ORIGINAL error."""
        client.set_rest_error("POST", "services/zha/remove", 400)
        client.set_ws_error("get_config", "unknown_error", "")
        with pytest.raises(HomeAssistantError, match="400"):
            zha_core.remove_device(client, "00:0d:6f:00:05:7d:2d:34")


# ── identifiers ─────────────────────────────────────────────────────────────


class TestParseIeee:
    def test_colon_form_passes_through(self, client):
        ieee = "00:0d:6f:00:05:7d:2d:34"
        assert zha_core.parse_ieee(ieee) == ieee
        assert client.ws_calls == []

    def test_dash_and_bare_forms(self, client):
        assert zha_core.parse_ieee("00-0d-6f-00-05-7d-2d-34") == "00-0d-6f-00-05-7d-2d-34"
        assert zha_core.parse_ieee("000d6f00057d2d34") == "000d6f00057d2d34"
        assert zha_core.parse_ieee("0x000d6f00057d2d34") == "0x000d6f00057d2d34"
        assert zha_core.parse_ieee(" 000d.6f00.057d.2d34 ") == "000d.6f00.057d.2d34"

    def test_rejects_short_and_non_hex(self, client):
        with pytest.raises(ValueError, match="IEEE"):
            zha_core.parse_ieee("00:0d:6f")
        with pytest.raises(ValueError, match="IEEE"):
            zha_core.parse_ieee("zz:0d:6f:00:05:7d:2d:34")

    def test_rejects_empty(self, client):
        with pytest.raises(ValueError, match="required"):
            zha_core.parse_ieee("")

    def test_every_ws_call_shapes_the_ieee(self, client):
        """A badly formed IEEE dies BEFORE the wire, on every ieee-taking call."""
        client.set_ws_error("zha/device", "unknown_command", "")
        with pytest.raises(ValueError, match="IEEE"):
            zha_core.get_device(client, "nope")


class TestParseMember:
    def test_compact_form(self, client):
        assert zha_core.parse_member("00:0d:6f:00:05:7d:2d:34:1") == {
            "ieee": "00:0d:6f:00:05:7d:2d:34",
            "endpoint_id": 1,
        }

    def test_rejects_missing_endpoint_and_non_int(self, client):
        # A colon IEEE without `:endpoint` parses as endpoint=34 against the
        # truncated IEEE, which fails the EUI-64 shape check — the error
        # names the IEEE, which is the part that is actually malformed.
        with pytest.raises(ValueError, match="IEEE"):
            zha_core.parse_member("00:0d:6f:00:05:7d:2d:34")
        with pytest.raises(ValueError, match="integer"):
            zha_core.parse_member("00:0d:6f:00:05:7d:2d:34:x")
        with pytest.raises(ValueError, match="member"):
            zha_core.parse_member("000d6f00057d2d34")

    def test_rejects_bad_ieee(self, client):
        with pytest.raises(ValueError, match="IEEE"):
            zha_core.parse_member("zz:1")


class TestParseBinding:
    def test_json_object(self, client):
        out = zha_core.parse_binding('{"name": "0x0006", "type": "in", "id": 6, "endpoint_id": 1}')
        assert out == {"name": "0x0006", "type": "in", "id": 6, "endpoint_id": 1}

    def test_missing_keys_are_named(self, client):
        with pytest.raises(ValueError, match="missing"):
            zha_core.parse_binding('{"name": "x"}')

    def test_non_json_and_non_object(self, client):
        with pytest.raises(ValueError, match="JSON"):
            zha_core.parse_binding("not json")
        with pytest.raises(ValueError, match="JSON"):
            zha_core.parse_binding("[1,2]")

    def test_int_fields_are_checked(self, client):
        with pytest.raises(ValueError, match="id must be an integer"):
            zha_core.parse_binding('{"name":"x","type":"in","id":"6","endpoint_id":1}')
        with pytest.raises(ValueError, match="endpoint_id"):
            zha_core.parse_binding('{"name":"x","type":"in","id":6,"endpoint_id":true}')


# ── devices ─────────────────────────────────────────────────────────────────


class TestDevices:
    def test_list_devices(self, client):
        client.set_ws("zha/devices", [{"ieee": "00:0d:6f:00:05:7d:2d:34"}])
        assert zha_core.list_devices(client)[0]["ieee"].endswith("34")
        assert _last_ws(client) == {"type": "zha/devices", "payload": None}

    def test_get_device(self, client):
        client.set_ws("zha/device", {"ieee": "00:0d:6f:00:05:7d:2d:34"})
        zha_core.get_device(client, "00:0d:6f:00:05:7d:2d:34")
        assert _last_ws(client)["payload"] == {"ieee": "00:0d:6f:00:05:7d:2d:34"}

    def test_groupable_devices(self, client):
        client.set_ws("zha/devices/groupable", [])
        zha_core.groupable_devices(client)
        assert _last_ws(client)["type"] == "zha/devices/groupable"

    def test_bindable_devices(self, client):
        client.set_ws("zha/devices/bindable", [])
        zha_core.bindable_devices(client, "00:0d:6f:00:05:7d:2d:34")
        assert _last_ws(client)["payload"] == {"ieee": "00:0d:6f:00:05:7d:2d:34"}


# ── groups ──────────────────────────────────────────────────────────────────


class TestGroups:
    def test_list_and_get(self, client):
        client.set_ws("zha/groups", [])
        zha_core.list_groups(client)
        assert _last_ws(client) == {"type": "zha/groups", "payload": None}
        client.set_ws("zha/group", {"group_id": 3})
        zha_core.get_group(client, 7)
        assert _last_ws(client)["payload"] == {"group_id": 7}

    def test_add_group_bare(self, client):
        client.set_ws("zha/group/add", {"name": "Lights"})
        zha_core.add_group(client, "Lights")
        assert _last_ws(client)["payload"] == {"name": "Lights"}

    def test_add_group_with_id_and_members(self, client):
        client.set_ws("zha/group/add", {"name": "Lights"})
        zha_core.add_group(client, "Lights", group_id=5, members=["00:0d:6f:00:05:7d:2d:34:1"])
        assert _last_ws(client)["payload"] == {
            "name": "Lights",
            "group_id": 5,
            "members": [{"ieee": "00:0d:6f:00:05:7d:2d:34", "endpoint_id": 1}],
        }

    def test_add_group_needs_a_name(self, client):
        with pytest.raises(ValueError, match="name"):
            zha_core.add_group(client, "  ")

    def test_remove_groups(self, client):
        client.set_ws("zha/group/remove", [])
        zha_core.remove_groups(client, [1, 2])
        assert _last_ws(client)["payload"] == {"group_ids": [1, 2]}

    def test_remove_groups_needs_one(self, client):
        with pytest.raises(ValueError, match="one group id"):
            zha_core.remove_groups(client, [])

    def test_group_id_must_be_positive(self, client):
        with pytest.raises(ValueError, match="positive"):
            zha_core.get_group(client, 0)
        with pytest.raises(ValueError, match="positive"):
            zha_core.get_group(client, -1)

    def test_member_add_and_remove(self, client):
        client.set_ws("zha/group/members/add", {})
        zha_core.add_group_members(client, 3, ["00:0d:6f:00:05:7d:2d:34:2"])
        assert _last_ws(client)["payload"] == {
            "group_id": 3,
            "members": [{"ieee": "00:0d:6f:00:05:7d:2d:34", "endpoint_id": 2}],
        }
        client.set_ws("zha/group/members/remove", {})
        zha_core.remove_group_members(client, 3, ["00:0d:6f:00:05:7d:2d:34:2"])
        assert _last_ws(client)["type"] == "zha/group/members/remove"

    def test_members_require_at_least_one(self, client):
        with pytest.raises(ValueError, match="--member"):
            zha_core.add_group_members(client, 3, [])


# ── cluster inspection ──────────────────────────────────────────────────────


class TestClusters:
    def test_clusters(self, client):
        client.set_ws("zha/devices/clusters", [])
        zha_core.clusters(client, "00:0d:6f:00:05:7d:2d:34")
        assert _last_ws(client)["payload"] == {"ieee": "00:0d:6f:00:05:7d:2d:34"}

    def test_attributes_and_commands_share_the_tuple(self, client):
        client.set_ws("zha/devices/clusters/attributes", [])
        zha_core.cluster_attributes(
            client, "00:0d:6f:00:05:7d:2d:34", endpoint_id=1, cluster_id=6, cluster_type="in"
        )
        assert _last_ws(client)["payload"] == {
            "ieee": "00:0d:6f:00:05:7d:2d:34",
            "endpoint_id": 1,
            "cluster_id": 6,
            "cluster_type": "in",
        }
        client.set_ws("zha/devices/clusters/commands", [])
        zha_core.cluster_commands(
            client, "00:0d:6f:00:05:7d:2d:34", endpoint_id=1, cluster_id=6, cluster_type="out"
        )
        assert _last_ws(client)["type"] == "zha/devices/clusters/commands"
        assert _last_ws(client)["payload"]["cluster_type"] == "out"

    def test_cluster_tuple_is_validated(self, client):
        base = dict(endpoint_id=1, cluster_id=6, cluster_type="in")
        with pytest.raises(ValueError, match="endpoint"):
            zha_core.cluster_attributes(client, "00:0d:6f:00:05:7d:2d:34", endpoint_id=-1, **{k: v for k, v in base.items() if k != "endpoint_id"})
        with pytest.raises(ValueError, match="cluster id"):
            zha_core.cluster_commands(client, "00:0d:6f:00:05:7d:2d:34", cluster_id=70000, endpoint_id=1, cluster_type="in")
        with pytest.raises(ValueError, match="'in' or 'out'"):
            zha_core.cluster_attributes(client, "00:0d:6f:00:05:7d:2d:34", cluster_type="sideways", endpoint_id=1, cluster_id=6)

    def test_read_attribute(self, client):
        client.set_ws("zha/devices/clusters/attributes/value", "25.5")
        out = zha_core.read_attribute(
            client, "00:0d:6f:00:05:7d:2d:34", endpoint_id=1, cluster_id=0, cluster_type="in", attribute=0
        )
        assert out == "25.5"
        assert _last_ws(client)["payload"]["attribute"] == 0

    def test_read_attribute_manufacturer(self, client):
        client.set_ws("zha/devices/clusters/attributes/value", "1")
        zha_core.read_attribute(
            client, "00:0d:6f:00:05:7d:2d:34", endpoint_id=1, cluster_id=6, cluster_type="in",
            attribute=0, manufacturer=0x115C,
        )
        assert _last_ws(client)["payload"]["manufacturer"] == 4444

    def test_read_attribute_validates(self, client):
        kw = dict(endpoint_id=1, cluster_id=0, cluster_type="in")
        with pytest.raises(ValueError, match="attribute"):
            zha_core.read_attribute(client, "00:0d:6f:00:05:7d:2d:34", attribute=True, **kw)
        with pytest.raises(ValueError, match="attribute"):
            zha_core.read_attribute(client, "00:0d:6f:00:05:7d:2d:34", attribute="0", **kw)
        with pytest.raises(ValueError, match="manufacturer"):
            zha_core.read_attribute(client, "00:0d:6f:00:05:7d:2d:34", attribute=0, manufacturer=-2, **kw)


# ── bindings ────────────────────────────────────────────────────────────────


class TestBindings:
    def test_bind_and_unbind(self, client):
        client.set_ws("zha/devices/bind", None)
        zha_core.bind_devices(client, "00:0d:6f:00:05:7d:2d:34", "00:0a:bf:00:01:10:23:35")
        assert _last_ws(client)["payload"] == {
            "source_ieee": "00:0d:6f:00:05:7d:2d:34",
            "target_ieee": "00:0a:bf:00:01:10:23:35",
        }
        client.set_ws("zha/devices/unbind", None)
        zha_core.unbind_devices(client, "00:0d:6f:00:05:7d:2d:34", "00:0a:bf:00:01:10:23:35")
        assert _last_ws(client)["type"] == "zha/devices/unbind"

    def test_group_bind_and_unbind(self, client):
        binding = '{"name": "0x0006", "type": "in", "id": 6, "endpoint_id": 1}'
        client.set_ws("zha/groups/bind", None)
        zha_core.bind_to_group(client, "00:0d:6f:00:05:7d:2d:34", 9, [binding])
        assert _last_ws(client)["payload"] == {
            "source_ieee": "00:0d:6f:00:05:7d:2d:34",
            "group_id": 9,
            "bindings": [{"name": "0x0006", "type": "in", "id": 6, "endpoint_id": 1}],
        }
        client.set_ws("zha/groups/unbind", None)
        zha_core.unbind_from_group(client, "00:0d:6f:00:05:7d:2d:34", 9, [binding])
        assert _last_ws(client)["type"] == "zha/groups/unbind"

    def test_group_bind_needs_a_binding(self, client):
        with pytest.raises(ValueError, match="--binding"):
            zha_core.bind_to_group(client, "00:0d:6f:00:05:7d:2d:34", 9, [])


# ── configuration / network ─────────────────────────────────────────────────


class TestConfigurationAndNetwork:
    def test_configuration(self, client):
        client.set_ws("zha/configuration", {"schemas": {}})
        zha_core.configuration(client)
        assert _last_ws(client) == {"type": "zha/configuration", "payload": None}

    def test_update_configuration(self, client):
        client.set_ws("zha/configuration/update", True)
        zha_core.update_configuration(client, {"zha_options": {"enable_identify": True}})
        assert _last_ws(client)["payload"] == {"data": {"zha_options": {"enable_identify": True}}}

    def test_update_configuration_needs_a_dict(self, client):
        with pytest.raises(ValueError, match="JSON object"):
            zha_core.update_configuration(client, "x")
        with pytest.raises(ValueError, match="non-empty"):
            zha_core.update_configuration(client, {})

    def test_network_settings_and_backups(self, client):
        client.set_ws("zha/network/settings", {"radio_type": "znp"})
        zha_core.network_settings(client)
        assert _last_ws(client)["type"] == "zha/network/settings"
        client.set_ws("zha/network/backups/list", [{"backup": {}}])
        zha_core.list_network_backups(client)
        assert _last_ws(client)["type"] == "zha/network/backups/list"

    def test_create_backup(self, client):
        client.set_ws("zha/network/backups/create", {"is_complete": True})
        out = zha_core.create_network_backup(client)
        assert out["is_complete"] is True

    def test_restore_backup(self, client):
        client.set_ws("zha/network/backups/restore", None)
        zha_core.restore_network_backup(client, {"network_info": {}})
        assert _last_ws(client)["payload"] == {"backup": {"network_info": {}}}

    def test_restore_backup_ezsp_flag(self, client):
        client.set_ws("zha/network/backups/restore", None)
        zha_core.restore_network_backup(client, {}, ezsp_force_write_eui64=True)
        assert _last_ws(client)["payload"] == {
            "backup": {},
            "ezsp_force_write_eui64": True,
        }

    def test_restore_backup_needs_a_dict(self, client):
        with pytest.raises(ValueError, match="backup"):
            zha_core.restore_network_backup(client, "x")

    def test_change_channel_auto_and_int(self, client):
        client.set_ws("zha/network/change_channel", None)
        zha_core.change_channel(client, "auto")
        assert _last_ws(client)["payload"] == {"new_channel": "auto"}
        zha_core.change_channel(client, 15)
        assert _last_ws(client)["payload"] == {"new_channel": 15}

    def test_change_channel_range(self, client):
        for bad in (10, 27, "11", True):
            with pytest.raises(ValueError, match="channel"):
                zha_core.change_channel(client, bad)


# ── services ────────────────────────────────────────────────────────────────


class TestServices:
    def test_remove(self, client):
        zha_core.remove_device(client, "00:0d:6f:00:05:7d:2d:34")
        assert client.service_calls[-1] == {
            "domain": "zha",
            "service": "remove",
            "service_data": {"ieee": "00:0d:6f:00:05:7d:2d:34"},
        }

    def test_set_attribute_payload_shape(self, client):
        client.set_service("zha", "set_zigbee_cluster_attribute", None)
        zha_core.set_cluster_attribute(
            client, "00:0d:6f:00:05:7d:2d:34", endpoint_id=1, cluster_id=8,
            attribute=16, value="warm", manufacturer=4444,
        )
        assert client.service_calls[-1]["service_data"] == {
            "ieee": "00:0d:6f:00:05:7d:2d:34",
            "endpoint_id": 1,
            "cluster_id": 8,
            "cluster_type": "in",
            "attribute": 16,
            "value": "warm",
            "manufacturer": 4444,
        }

    def test_set_attribute_rejects_float_and_bad_manufacturer(self, client):
        with pytest.raises(ValueError, match="value"):
            zha_core.set_cluster_attribute(client, "00:0d:6f:00:05:7d:2d:34", endpoint_id=1, cluster_id=8, attribute=1, value=1.5)
        with pytest.raises(ValueError, match="manufacturer"):
            zha_core.set_cluster_attribute(client, "00:0d:6f:00:05:7d:2d:34", endpoint_id=1, cluster_id=8, attribute=1, value=1, manufacturer=-3)

    def test_issue_command_params(self, client):
        client.set_service("zha", "issue_zigbee_cluster_command", None)
        zha_core.issue_cluster_command(
            client, "00:0d:6f:00:05:7d:2d:34", endpoint_id=1, cluster_id=6,
            command=0, command_type="server", params={"mode": 1},
        )
        assert client.service_calls[-1]["service_data"]["params"] == {"mode": 1}
        assert client.service_calls[-1]["service_data"]["command_type"] == "server"

    def test_issue_command_args(self, client):
        client.set_service("zha", "issue_zigbee_cluster_command", None)
        zha_core.issue_cluster_command(
            client, "00:0d:6f:00:05:7d:2d:34", endpoint_id=1, cluster_id=6,
            command=0, command_type="client", args=[1, 2],
        )
        assert client.service_calls[-1]["service_data"]["args"] == [1, 2]

    def test_issue_command_args_and_params_are_exclusive(self, client):
        with pytest.raises(ValueError, match="exactly one"):
            zha_core.issue_cluster_command(client, "00:0d:6f:00:05:7d:2d:34", endpoint_id=1, cluster_id=6, command=0, command_type="server")
        with pytest.raises(ValueError, match="exactly one"):
            zha_core.issue_cluster_command(client, "00:0d:6f:00:05:7d:2d:34", endpoint_id=1, cluster_id=6, command=0, command_type="server", args=[], params={})

    def test_issue_command_type_is_validated(self, client):
        with pytest.raises(ValueError, match="client.*server|'client' or 'server'"):
            zha_core.issue_cluster_command(client, "00:0d:6f:00:05:7d:2d:34", endpoint_id=1, cluster_id=6, command=0, command_type="sideways", params={})

    def test_issue_group_command(self, client):
        client.set_service("zha", "issue_zigbee_group_command", None)
        zha_core.issue_group_command(client, 5, cluster_id=6, command=0, args=[1])
        assert client.service_calls[-1]["service_data"] == {
            "group": 5,
            "cluster_id": 6,
            "cluster_type": "in",
            "command": 0,
            "args": [1],
        }

    def test_warning_squawk_defaults_are_has_owns(self, client):
        client.set_service("zha", "warning_device_squawk", None)
        zha_core.warning_squawk(client, "00:0d:6f:00:05:7d:2d:34")
        assert client.service_calls[-1]["service_data"] == {
            "ieee": "00:0d:6f:00:05:7d:2d:34",
            "mode": 0,
            "strobe": 1,
            "level": 2,
        }

    def test_warning_warn_defaults_are_has_owns(self, client):
        client.set_service("zha", "warning_device_warn", None)
        zha_core.warning_warn(client, "00:0d:6f:00:05:7d:2d:34")
        assert client.service_calls[-1]["service_data"] == {
            "ieee": "00:0d:6f:00:05:7d:2d:34",
            "mode": 3,
            "strobe": 1,
            "level": 2,
            "duration": 5,
            "duty_cycle": 0,
            "intensity": 2,
        }

    def test_warning_fields_are_validated(self, client):
        with pytest.raises(ValueError, match="non-negative"):
            zha_core.warning_warn(client, "00:0d:6f:00:05:7d:2d:34", duration=-1)
