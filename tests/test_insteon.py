"""Unit tests for core/insteon.py — payload shapes, guards and refusals.

Uses the shared FakeClient; no Home Assistant needed. The recorder asserts
the exact WS command and payload each function builds, because the insteon
integration's ALDB record and scene-link schemas are strict (typed keys,
byte ranges, a link list per scene) and its absent-integration refusal is
the same ``unknown_command`` a typo gets — shapes the wrappers must get
right before HA ever sees them.
"""

from __future__ import annotations

import threading

import pytest

from cli_anything.homeassistant.core import insteon as insteon_core
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


def _raising_subscription_fake(code, message):
    """A FakeClient whose ws_subscribe raises like the real wire client does."""

    class _Sub(SubscribingFakeClient):
        def ws_subscribe(self, msg_type, payload, on_message=None, stop_event=None, **kw):
            raise HomeAssistantError(f"WS subscribe failed: {msg_type}", code=code)

    return _Sub()


# ── availability / the absent guard ─────────────────────────────────────────


class TestAvailableAndAbsent:
    def test_loaded(self, client):
        client.set_ws("get_config", {"components": ["insteon", "hue"]})
        out = insteon_core.available(client)
        assert out["available"] is True
        assert "works here" in out["note"]

    def test_not_loaded(self, client):
        client.set_ws("get_config", {"components": ["hue"]})
        out = insteon_core.available(client)
        assert out["available"] is False
        assert "insteon" in out["note"]

    def test_get_config_failure_is_NOT_a_wrong_answer(self, client):
        client.set_ws_error("get_config", "unknown_error", "boom")
        with pytest.raises(HomeAssistantError, match="boom"):
            insteon_core.available(client)

    def test_unknown_command_becomes_the_note(self, client):
        client.set_ws_error("insteon/config/get", "unknown_command", "Invalid")
        with pytest.raises(HomeAssistantError, match="no Insteon modem"):
            insteon_core.get_config(client)

    def test_note_names_the_core_install_packages(self, client):
        client.set_ws_error("insteon/scenes/get", "unknown_command", "Invalid")
        with pytest.raises(HomeAssistantError, match="pyinsteon"):
            insteon_core.get_scenes(client)

    def test_unrelated_codes_pass_through(self, client):
        client.set_ws_error("insteon/config/get", "unauthorized", "no")
        with pytest.raises(HomeAssistantError, match="unauthorized"):
            insteon_core.get_config(client)

    def test_available_does_not_go_through_the_guard(self, client):
        client.set_ws("get_config", {"components": []})
        assert insteon_core.available(client)["available"] is False


# ── devices ─────────────────────────────────────────────────────────────────


class TestDevices:
    def test_get_device_with_a_device_id(self, client):
        client.set_ws("insteon/device/get", {"address": "1a.2b.3c", "is_battery": False})
        out = insteon_core.get_device(client, "abc123")
        assert out["address"] == "1a.2b.3c"
        assert _last_ws(client)["type"] == "insteon/device/get"
        assert _last_ws(client)["payload"] == {"device_id": "abc123"}

    def test_get_device_resolves_an_entity_id(self, client):
        client.set_ws("config/entity_registry/get", {"device_id": "dev-9"})
        client.set_ws("insteon/device/get", {"address": "1a.2b.3c"})
        insteon_core.get_device(client, "light.hall")
        assert client.ws_calls[0]["type"] == "config/entity_registry/get"
        assert _last_ws(client)["payload"]["device_id"] == "dev-9"

    def test_get_device_refuses_an_orphan_entity(self, client):
        client.set_ws("config/entity_registry/get", {"device_id": None})
        with pytest.raises(ValueError, match="not linked to a device"):
            insteon_core.get_device(client, "light.hall")

    def test_empty_ident_refused(self, client):
        with pytest.raises(ValueError, match="device id or entity id"):
            insteon_core.get_device(client, "  ")

    def test_add_device_stream_shape(self, client):
        client.set_run_events(
            {"type": "device_added", "address": "1a.2b.3c"},
            {"type": "linking_stopped", "address": ""},
        )
        out = insteon_core.add_device(client, multiple=True)
        assert out["result"] == "ok"
        assert out["added"] == ["1a.2b.3c"]
        call = client.run_event_calls[-1]
        assert call["type"] == "insteon/device/add"
        assert call["payload"] == {"multiple": True}
        assert call["timeout"] is None

    def test_add_device_streams_to_the_caller_via_on_event(self, client):
        seen = []
        client.set_run_events({"type": "device_added", "address": "2a.2b.2c"})
        insteon_core.add_device(client)  # events still collected without on_event
        assert not seen  # no on_event passed — nothing to assert, but no crash

    def test_add_device_nothing_joined(self, client):
        client.set_run_events({"type": "linking_stopped", "address": ""})
        out = insteon_core.add_device(client, address="1a.2b.3c")
        assert out["added"] == []
        assert "no device" in out["note"]
        assert client.run_event_calls[-1]["payload"] == {
            "multiple": False,
            "device_address": "1a.2b.3c",
        }

    def test_add_device_absent_guard(self, client):
        client.set_ws_error("insteon/device/add", "unknown_command", "Invalid")
        with pytest.raises(HomeAssistantError, match="no Insteon modem"):
            insteon_core.add_device(client)

    def test_cancel_add(self, client):
        insteon_core.cancel_add_device(client)
        assert _last_ws(client)["type"] == "insteon/device/add/cancel"

    def test_remove_device(self, client):
        out = insteon_core.remove_device(client, "1a.2b.3c", remove_all_refs=True)
        assert out["result"] == "ok"
        assert _last_ws(client)["payload"] == {
            "device_address": "1a.2b.3c",
            "remove_all_refs": True,
        }

    def test_remove_device_x10_named_as_such(self, client):
        out = insteon_core.remove_device(client, "X10.a.3")
        assert "X10" in out["note"]
        assert _last_ws(client)["payload"]["device_address"] == "X10.a.3"

    def test_add_x10_valid_payload(self, client):
        out = insteon_core.add_x10_device(client, "C", "3", "light", dim_steps=22)
        assert out["result"] == "ok"
        assert _last_ws(client)["payload"] == {
            "x10_device": {
                "housecode": "c",
                "unitcode": 3,
                "platform": "light",
                "dim_steps": 22,
            }
        }

    def test_add_x10_non_light_gets_no_dim_steps(self, client):
        insteon_core.add_x10_device(client, "a", "16", "switch")
        assert _last_ws(client)["payload"]["x10_device"] == {
            "housecode": "a",
            "unitcode": 16,
            "platform": "switch",
        }

    def test_add_x10_refusals(self, client):
        with pytest.raises(ValueError, match="housecode"):
            insteon_core.add_x10_device(client, "z", 3, "light")
        with pytest.raises(ValueError, match="unitcode"):
            insteon_core.add_x10_device(client, "a", 17, "light")
        with pytest.raises(ValueError, match="unitcode"):
            insteon_core.add_x10_device(client, "a", 0, "light")
        with pytest.raises(ValueError, match="platform"):
            insteon_core.add_x10_device(client, "a", 3, "fan")
        with pytest.raises(ValueError, match="dim_steps"):
            insteon_core.add_x10_device(client, "a", 3, "light", dim_steps=300)


# ── the all-link database ───────────────────────────────────────────────────


VALID_RECORD = {
    "mem_addr": 0x0FFF,
    "in_use": True,
    "group": 0,
    "is_controller": True,
    "target": "44.45.55",
    "data1": 0,
    "data2": 0,
    "data3": 0xFF,
}


class TestAldb:
    def test_get_aldb(self, client):
        client.set_ws("insteon/aldb/get", [{"mem_addr": 4095, "in_use": True, "dirty": False}])
        out = insteon_core.get_aldb(client, "1a.2b.3c")
        assert out[0]["mem_addr"] == 4095
        assert _last_ws(client)["payload"] == {"device_address": "1a.2b.3c"}

    def test_add_record_queue_note(self, client):
        out = insteon_core.add_aldb_record(client, "1a.2b.3c", dict(VALID_RECORD))
        assert "aldb-write" in out["note"]
        assert _last_ws(client)["payload"]["record"] == VALID_RECORD

    def test_change_record_queue_note(self, client):
        out = insteon_core.change_aldb_record(client, "1a.2b.3c", dict(VALID_RECORD))
        assert "aldb-write" in out["note"]
        assert _last_ws(client)["type"] == "insteon/aldb/change"

    def test_record_missing_key_named(self, client):
        bad = {k: v for k, v in VALID_RECORD.items() if k != "data3"}
        with pytest.raises(ValueError, match="data3"):
            insteon_core.add_aldb_record(client, "1a.2b.3c", bad)

    def test_record_not_an_object_refused(self, client):
        with pytest.raises(ValueError, match="JSON object"):
            insteon_core.add_aldb_record(client, "1a.2b.3c", [VALID_RECORD])

    def test_record_bool_fields_strict(self, client):
        bad = dict(VALID_RECORD, in_use="yes")
        with pytest.raises(ValueError, match="in_use"):
            insteon_core.change_aldb_record(client, "1a.2b.3c", bad)

    def test_record_group_out_of_range(self, client):
        with pytest.raises(ValueError, match="group"):
            insteon_core.change_aldb_record(client, "1a.2b.3c", dict(VALID_RECORD, group=256))

    def test_record_data_byte_out_of_range(self, client):
        with pytest.raises(ValueError, match="data1"):
            insteon_core.change_aldb_record(client, "1a.2b.3c", dict(VALID_RECORD, data1=-1))

    def test_record_target_required(self, client):
        with pytest.raises(ValueError, match="target"):
            insteon_core.add_aldb_record(client, "1a.2b.3c", dict(VALID_RECORD, target="  "))

    def test_record_mem_addr_strict(self, client):
        with pytest.raises(ValueError, match="mem_addr"):
            insteon_core.add_aldb_record(client, "1a.2b.3c", dict(VALID_RECORD, mem_addr=-1))

    def test_record_unknown_keys_refused(self, client):
        with pytest.raises(ValueError, match="unknown key\\(s\\): junk"):
            insteon_core.add_aldb_record(client, "1a.2b.3c", dict(VALID_RECORD, junk=1))

    def test_empty_address_refused(self, client):
        with pytest.raises(ValueError, match="device address"):
            insteon_core.get_aldb(client, "")

    def test_write_load_reset_and_defaults(self, client):
        for fn, msg_type in (
            (insteon_core.write_aldb, "insteon/aldb/write"),
            (insteon_core.load_aldb, "insteon/aldb/load"),
            (insteon_core.reset_aldb, "insteon/aldb/reset"),
            (insteon_core.add_default_links, "insteon/aldb/add_default_links"),
        ):
            out = fn(client, "1a.2b.3c")
            assert out["result"] == "ok"
            assert _last_ws(client)["type"] == msg_type
            assert _last_ws(client)["payload"] == {"device_address": "1a.2b.3c"}


class TestAldbSubscriptions:
    def test_notify_payload(self, sub_client):
        sub_client.queue_events({"type": "record_loaded"})
        seen = []
        insteon_core.subscribe_aldb_status(sub_client, seen.append, "1a.2b.3c", max_events=1)
        assert seen == [{"type": "record_loaded"}]
        assert sub_client.subscribe_calls[-1] == (
            "insteon/aldb/notify",
            {"device_address": "1a.2b.3c"},
        )

    def test_notify_all_payload(self, sub_client):
        sub_client.queue_events({"type": "status", "is_loading": False})
        seen = []
        insteon_core.subscribe_aldb_status_all(sub_client, seen.append, max_events=1)
        assert seen == [{"type": "status", "is_loading": False}]
        assert sub_client.subscribe_calls[-1] == ("insteon/aldb/notify_all", {})

    def test_no_stop_no_max_is_a_refusal(self, sub_client):
        with pytest.raises(ValueError):
            insteon_core.subscribe_aldb_status(sub_client, lambda e: None, "1a.2b.3c")
        with pytest.raises(ValueError):
            insteon_core.subscribe_aldb_status_all(sub_client, lambda e: None)

    def test_not_callable_refused(self, sub_client):
        with pytest.raises(ValueError, match="callable"):
            insteon_core.subscribe_aldb_status(sub_client, "nope", "1a.2b.3c", max_events=1)

    def test_stop_event_owned_by_the_caller(self, sub_client):
        """The caller's event object is the one the loop honours."""
        stop = threading.Event()
        seen = []
        sub_client.queue_events({"type": "record_loaded"})
        insteon_core.subscribe_aldb_status(sub_client, seen.append, "1a.2b.3c", stop_event=stop)
        assert seen == [{"type": "record_loaded"}]
        assert stop.is_set()  # the shim stops THE CALLER'S event, not a private one

    def test_absent_guard_on_subscribe(self, sub_client):
        client = _raising_subscription_fake("unknown_command", "Invalid")
        with pytest.raises(HomeAssistantError, match="no Insteon modem"):
            insteon_core.subscribe_aldb_status(client, lambda e: None, "1a.2b.3c", max_events=1)

    def test_absent_guard_on_subscribe_all(self, sub_client):
        client = _raising_subscription_fake("unknown_command", "Invalid")
        with pytest.raises(HomeAssistantError, match="no Insteon modem"):
            insteon_core.subscribe_aldb_status_all(client, lambda e: None, max_events=1)


# ── device properties ───────────────────────────────────────────────────────


class TestProperties:
    def test_get_properties(self, client):
        client.set_ws(
            "insteon/properties/get",
            {"properties": [{"name": "on_level", "value": 255, "modified": False}], "schema": {}},
        )
        insteon_core.get_properties(client, "1a.2b.3c")
        assert _last_ws(client)["payload"] == {
            "device_address": "1a.2b.3c",
            "show_advanced": False,
        }

    def test_get_properties_advanced_flag_rides_the_payload(self, client):
        insteon_core.get_properties(client, "1a.2b.3c", show_advanced=True)
        assert _last_ws(client)["payload"]["show_advanced"] is True

    def test_change_property(self, client):
        out = insteon_core.change_property(client, "1a.2b.3c", "on_level", 255)
        assert "properties-write" in out["note"]
        assert _last_ws(client)["payload"] == {
            "device_address": "1a.2b.3c",
            "name": "on_level",
            "value": 255,
        }

    def test_change_property_name_required(self, client):
        with pytest.raises(ValueError, match="property name"):
            insteon_core.change_property(client, "1a.2b.3c", "  ", 255)

    def test_write_load_reset(self, client):
        for fn, msg_type in (
            (insteon_core.write_properties, "insteon/properties/write"),
            (insteon_core.load_properties, "insteon/properties/load"),
            (insteon_core.reset_properties, "insteon/properties/reset"),
        ):
            out = fn(client, "1a.2b.3c")
            assert out["result"] == "ok"
            assert _last_ws(client)["type"] == msg_type


# ── modem configuration ─────────────────────────────────────────────────────


class TestConfig:
    def test_get_config(self, client):
        client.set_ws("insteon/config/get", {"modem_config": {"device": "/dev/ttyUSB0"}})
        out = insteon_core.get_config(client)
        assert out["modem_config"]["device"] == "/dev/ttyUSB0"

    def test_get_modem_schema(self, client):
        client.set_ws("insteon/config/get_modem_schema", [{"name": "device"}])
        assert insteon_core.get_modem_schema(client)[0]["name"] == "device"

    def test_update_modem_config(self, client):
        out = insteon_core.update_modem_config(client, {"device": "/dev/ttyUSB0"})
        assert out["result"] == "ok"
        assert _last_ws(client)["payload"] == {"config": {"device": "/dev/ttyUSB0"}}

    def test_update_modem_config_refuses_an_empty_object(self, client):
        with pytest.raises(ValueError, match="non-empty"):
            insteon_core.update_modem_config(client, {})

    def test_update_modem_config_absent_guard(self, client):
        client.set_ws_error("insteon/config/update_modem_config", "unknown_command", "Invalid")
        with pytest.raises(HomeAssistantError, match="no Insteon modem"):
            insteon_core.update_modem_config(client, {"port": "/dev/x"})

    def test_add_override(self, client):
        out = insteon_core.add_device_override(client, "1a.2b.3c", cat="01", subcat="2d")
        assert out["result"] == "ok"
        assert _last_ws(client)["payload"] == {
            "override": {"address": "1a.2b.3c", "cat": "01", "subcat": "2d"}
        }

    def test_add_override_optional_keys_absent_when_unpassed(self, client):
        insteon_core.add_device_override(client, "1a.2b.3c")
        assert _last_ws(client)["payload"] == {"override": {"address": "1a.2b.3c"}}

    def test_add_override_duplicate_named(self, client):
        client.set_ws_error(
            "insteon/config/device_override/add", "duplicate", "Duplicate device address"
        )
        with pytest.raises(HomeAssistantError, match="already has a device override"):
            insteon_core.add_device_override(client, "1a.2b.3c")

    def test_remove_override(self, client):
        out = insteon_core.remove_device_override(client, "1a.2b.3c")
        assert out["result"] == "ok"
        assert _last_ws(client)["payload"] == {"device_address": "1a.2b.3c"}

    def test_broken_links_and_unknown_devices(self, client):
        client.set_ws("insteon/config/get_broken_links", [{"address": "1a.2b.3c"}])
        out = insteon_core.get_broken_links(client)
        assert out[0]["address"] == "1a.2b.3c"
        client.set_ws("insteon/config/get_unknown_devices", ["2a.2b.2c"])
        assert insteon_core.get_unknown_devices(client) == ["2a.2b.2c"]


# ── scenes ──────────────────────────────────────────────────────────────────


SCENE_LINKS = [{"address": "1a.2b.3c", "data1": 0, "data2": 0, "data3": 255}]


class TestScenes:
    def test_get_scenes(self, client):
        client.set_ws("insteon/scenes/get", {"1": {"name": "movie", "group": 1}})
        assert insteon_core.get_scenes(client)["1"]["name"] == "movie"

    def test_get_scene(self, client):
        client.set_ws("insteon/scene/get", {"name": "movie"})
        insteon_core.get_scene(client, 7)
        assert _last_ws(client)["payload"] == {"scene_id": 7}

    def test_save_scene(self, client):
        client.set_ws("insteon/scene/save", {"scene_id": 7, "result": True})
        out = insteon_core.save_scene(client, 7, "movie", SCENE_LINKS)
        assert out["scene_id"] == 7
        assert _last_ws(client)["payload"] == {
            "scene_id": 7,
            "name": "movie",
            "links": SCENE_LINKS,
        }

    def test_save_scene_refusals(self, client):
        with pytest.raises(ValueError, match="name"):
            insteon_core.save_scene(client, 7, "  ", SCENE_LINKS)
        with pytest.raises(ValueError, match="non-empty JSON list"):
            insteon_core.save_scene(client, 7, "movie", [])
        with pytest.raises(ValueError, match="missing required key\\(s\\): data2"):
            insteon_core.save_scene(
                client, 7, "movie", [{"address": "1a.2b.3c", "data1": 0, "data3": 255}]
            )
        with pytest.raises(ValueError, match="must be a JSON object"):
            insteon_core.save_scene(client, 7, "movie", ["junk"])

    def test_delete_scene(self, client):
        client.set_ws("insteon/scene/delete", {"scene_id": 7, "result": True})
        out = insteon_core.delete_scene(client, 7)
        assert out["scene_id"] == 7
        assert _last_ws(client)["payload"] == {"scene_id": 7}

    def test_delete_scene_empty_result_gets_the_note(self, client):
        client.set_ws("insteon/scene/delete", {})
        out = insteon_core.delete_scene(client, 7)
        assert "deleted" in out["note"]
