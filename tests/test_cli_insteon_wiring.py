"""CLI wiring tests for the `insteon` group (v1.58 refine pass).

Click CliRunner + FakeClient, per the existing wiring-test pattern: the real
Click decorators and option parsing run, the wire client is faked. The
payloads asserted are what HA's `insteon/…` handlers validate at the
websocket layer — the ALDB record and scene-link schemas, the X10 housecode
clamps and the destructive confirmation gates.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from cli_anything.homeassistant import homeassistant_cli as cli_mod


@pytest.fixture
def runner(monkeypatch, fake_client):
    monkeypatch.setattr(cli_mod, "make_client", lambda ctx: fake_client)
    return CliRunner()


@pytest.fixture
def sub_runner(monkeypatch):
    from .conftest import SubscribingFakeClient

    client = SubscribingFakeClient()
    monkeypatch.setattr(cli_mod, "make_client", lambda ctx: client)
    return CliRunner(), client


def _invoke(runner, *args, json_out=True, input=None):
    full = ["--json", *list(args)] if json_out else list(args)
    return runner.invoke(
        cli_mod.cli,
        full,
        obj={
            "url": "http://x",
            "token": "t",
            "verify_ssl": False,
            "timeout": 5,
            "as_json": json_out,
            "config_path": None,
        },
        input=input,
    )


RECORD = (
    '{"mem_addr": 4095, "in_use": true, "group": 1, "is_controller": true,'
    ' "target": "44.45.55", "data1": 0, "data2": 0, "data3": 255}'
)
LINKS = '[{"address": "1a.2b.3c", "data1": 0, "data2": 0, "data3": 255}]'


class TestInsteonAvailableCli:
    def test_loaded(self, runner, fake_client):
        fake_client.set_ws("get_config", {"components": ["insteon"]})
        r = _invoke(runner, "insteon", "available")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["available"] is True

    def test_not_loaded(self, runner, fake_client):
        fake_client.set_ws("get_config", {"components": []})
        r = _invoke(runner, "insteon", "available")
        assert r.exit_code == 0
        assert json.loads(r.output)["available"] is False

    def test_group_in_root_help(self, runner):
        r = _invoke(runner, "--help")
        assert r.exit_code == 0
        assert "insteon" in r.output


class TestDevicesCli:
    def test_device(self, runner, fake_client):
        fake_client.set_ws("config/entity_registry/get", {"device_id": "dev-9"})
        fake_client.set_ws("insteon/device/get", {"address": "1a.2b.3c", "is_battery": False})
        r = _invoke(runner, "insteon", "device", "light.hall")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["address"] == "1a.2b.3c"

    def test_device_add(self, runner, fake_client):
        fake_client.set_run_events({"type": "linking_stopped", "address": ""})
        r = _invoke(runner, "insteon", "device-add", "--timeout-flag-unused")
        assert r.exit_code != 0  # unknown options are refused, not swallowed

        fake_client.set_run_events({"type": "linking_stopped", "address": ""})
        r = _invoke(runner, "insteon", "device-add", "--multiple")
        assert r.exit_code == 0, r.output
        out = json.loads(r.output)
        assert out["added"] == []
        assert fake_client.run_event_calls[-1]["payload"] == {"multiple": True}

    def test_device_add_cancel(self, runner, fake_client):
        r = _invoke(runner, "insteon", "device-add-cancel")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["type"] == "insteon/device/add/cancel"

    def test_device_remove_confirmation_gate(self, runner, fake_client):
        r = _invoke(runner, "insteon", "device-remove", "1a.2b.3c", json_out=False, input="n\n")
        assert r.exit_code != 0  # declined
        r = _invoke(runner, "insteon", "device-remove", "1a.2b.3c", "--yes", "--remove-all-refs")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"]["remove_all_refs"] is True

    def test_add_x10_choices_enforced_by_click(self, runner, fake_client):
        r = _invoke(runner, "insteon", "add-x10", "z", "3", "light")
        assert r.exit_code != 0
        r = _invoke(runner, "insteon", "add-x10", "c", "3", "fan")
        assert r.exit_code != 0
        r = _invoke(runner, "insteon", "add-x10", "c", "3", "light", "--dim-steps", "22")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"]["x10_device"]["dim_steps"] == 22


class TestAldbCli:
    def test_aldb(self, runner, fake_client):
        fake_client.set_ws("insteon/aldb/get", [{"mem_addr": 4095, "dirty": False}])
        r = _invoke(runner, "insteon", "aldb", "1a.2b.3c")
        assert r.exit_code == 0
        assert json.loads(r.output)[0]["mem_addr"] == 4095

    def test_aldb_add_and_change(self, runner, fake_client):
        r = _invoke(runner, "insteon", "aldb-add", "1a.2b.3c", RECORD)
        assert r.exit_code == 0, r.output
        fake_client.ws_calls.clear()
        r = _invoke(runner, "insteon", "aldb-change", "1a.2b.3c", RECORD)
        assert r.exit_code == 0
        assert fake_client.ws_calls[-1]["type"] == "insteon/aldb/change"

    def test_aldb_add_bad_record_is_a_click_error(self, runner, fake_client):
        r = _invoke(runner, "insteon", "aldb-add", "1a.2b.3c", '{"mem_addr": 1}')
        assert r.exit_code == 1
        assert "data" in r.output  # the missing-key refusal names the fields

    def test_aldb_add_not_json(self, runner, fake_client):
        r = _invoke(runner, "insteon", "aldb-add", "1a.2b.3c", "nonsense")
        assert r.exit_code == 1
        assert "valid JSON" in r.output

    def test_aldb_write_load(self, runner, fake_client):
        for cmd, msg_type in (("aldb-write", "insteon/aldb/write"), ("aldb-load", "insteon/aldb/load")):
            r = _invoke(runner, "insteon", cmd, "1a.2b.3c")
            assert r.exit_code == 0
            assert fake_client.ws_calls[-1]["type"] == msg_type

    def test_aldb_reset_confirmation(self, runner, fake_client):
        r = _invoke(runner, "insteon", "aldb-reset", "1a.2b.3c", json_out=False, input="n\n")
        assert r.exit_code != 0
        r = _invoke(runner, "insteon", "aldb-reset", "1a.2b.3c", "--yes")
        assert r.exit_code == 0
        assert fake_client.ws_calls[-1]["type"] == "insteon/aldb/reset"

    def test_aldb_default_links_confirmation(self, runner, fake_client):
        r = _invoke(runner, "insteon", "aldb-default-links", "1a.2b.3c", json_out=False, input="n\n")
        assert r.exit_code != 0
        r = _invoke(runner, "insteon", "aldb-default-links", "1a.2b.3c", "--yes")
        assert r.exit_code == 0

    def test_aldb_watch(self, sub_runner):
        runner, client = sub_runner
        client.queue_events({"type": "record_loaded"}, {"type": "record_loaded"})
        r = _invoke(runner, "insteon", "aldb-watch", "1a.2b.3c", "--max-events", "2", json_out=False)
        assert r.exit_code == 0, r.output
        assert '"type": "record_loaded"' in r.output
        assert client.subscribe_calls[-1] == (
            "insteon/aldb/notify",
            {"device_address": "1a.2b.3c"},
        )

    def test_aldb_watch_all(self, sub_runner):
        runner, client = sub_runner
        client.queue_events({"type": "status", "is_loading": False})
        r = _invoke(runner, "insteon", "aldb-watch-all", "--max-events", "1", json_out=False)
        assert r.exit_code == 0, r.output
        assert client.subscribe_calls[-1] == ("insteon/aldb/notify_all", {})


class TestPropertiesCli:
    def test_properties(self, runner, fake_client):
        fake_client.set_ws("insteon/properties/get", {"properties": [], "schema": {}})
        r = _invoke(runner, "insteon", "properties", "1a.2b.3c", "--advanced")
        assert r.exit_code == 0
        assert fake_client.ws_calls[-1]["payload"]["show_advanced"] is True

    def test_property_set_parses_json_scalars_then_strings(self, runner, fake_client):
        _invoke(runner, "insteon", "property-set", "1a.2b.3c", "on_level", "255")
        assert fake_client.ws_calls[-1]["payload"]["value"] == 255
        _invoke(runner, "insteon", "property-set", "1a.2b.3c", "led", "true")
        assert fake_client.ws_calls[-1]["payload"]["value"] is True
        _invoke(runner, "insteon", "property-set", "1a.2b.3c", "toggle", "on_off")
        assert fake_client.ws_calls[-1]["payload"]["value"] == "on_off"

    def test_write_load_reset(self, runner, fake_client):
        r = _invoke(runner, "insteon", "properties-write", "1a.2b.3c")
        assert r.exit_code == 0
        r = _invoke(runner, "insteon", "properties-load", "1a.2b.3c")
        assert r.exit_code == 0
        r = _invoke(runner, "insteon", "properties-reset", "1a.2b.3c", json_out=False, input="n\n")
        assert r.exit_code != 0
        r = _invoke(runner, "insteon", "properties-reset", "1a.2b.3c", "--yes")
        assert r.exit_code == 0
        assert fake_client.ws_calls[-1]["type"] == "insteon/properties/reset"


class TestConfigCli:
    def test_config_and_modem_schema(self, runner, fake_client):
        fake_client.set_ws("insteon/config/get", {"modem_config": {"device": "/dev/ttyUSB0"}})
        r = _invoke(runner, "insteon", "config")
        assert json.loads(r.output)["modem_config"]["device"] == "/dev/ttyUSB0"
        fake_client.set_ws("insteon/config/get_modem_schema", [{"name": "device"}])
        assert _invoke(runner, "insteon", "modem-schema").exit_code == 0

    def test_modem_config_set_confirmation(self, runner, fake_client):
        cfg = '{"port": "/dev/ttyUSB0"}'
        r = _invoke(runner, "insteon", "modem-config-set", cfg, json_out=False, input="n\n")
        assert r.exit_code != 0
        r = _invoke(runner, "insteon", "modem-config-set", cfg, "--yes")
        assert r.exit_code == 0
        assert fake_client.ws_calls[-1]["payload"]["config"] == {"port": "/dev/ttyUSB0"}

    def test_modem_config_set_empty_object_refused(self, runner, fake_client):
        r = _invoke(runner, "insteon", "modem-config-set", "{}", "--yes")
        assert r.exit_code == 1
        assert "non-empty" in r.output

    def test_overrides(self, runner, fake_client):
        r = _invoke(runner, "insteon", "override-add", "1a.2b.3c", "--cat", "01")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"]["override"]["cat"] == "01"
        r = _invoke(runner, "insteon", "override-remove", "1a.2b.3c")
        assert r.exit_code == 0

    def test_broken_links_and_unknown_devices(self, runner, fake_client):
        fake_client.set_ws("insteon/config/get_broken_links", [{"address": "1a.2b.3c"}])
        r = _invoke(runner, "insteon", "broken-links")
        assert json.loads(r.output)[0]["address"] == "1a.2b.3c"
        fake_client.set_ws("insteon/config/get_unknown_devices", ["2a.2b.2c"])
        r = _invoke(runner, "insteon", "unknown-devices")
        assert json.loads(r.output) == ["2a.2b.2c"]

    def test_absent_integration_is_one_clean_sentence(self, runner, fake_client):
        fake_client.set_ws_error("insteon/config/get", "unknown_command", "Invalid")
        r = _invoke(runner, "insteon", "config")
        assert r.exit_code == 1
        assert "no Insteon modem" in r.output
        assert "unknown_command" not in r.output


class TestScenesCli:
    def test_scenes_and_scene(self, runner, fake_client):
        fake_client.set_ws("insteon/scenes/get", {"1": {"name": "movie"}})
        r = _invoke(runner, "insteon", "scenes")
        assert json.loads(r.output)["1"]["name"] == "movie"
        fake_client.set_ws("insteon/scene/get", {"name": "movie"})
        assert _invoke(runner, "insteon", "scene", "7").exit_code == 0

    def test_scene_save(self, runner, fake_client):
        fake_client.set_ws("insteon/scene/save", {"scene_id": 7, "result": True})
        r = _invoke(runner, "insteon", "scene-save", "7", "movie", LINKS)
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["scene_id"] == 7

    def test_scene_save_bad_links(self, runner, fake_client):
        r = _invoke(runner, "insteon", "scene-save", "7", "movie", "[{}]")
        assert r.exit_code == 1
        assert "missing required key" in r.output

    def test_scene_delete_confirmation(self, runner, fake_client):
        r = _invoke(runner, "insteon", "scene-delete", "7", json_out=False, input="n\n")
        assert r.exit_code != 0
        r = _invoke(runner, "insteon", "scene-delete", "7", "--yes")
        assert r.exit_code == 0
        assert fake_client.ws_calls[-1]["type"] == "insteon/scene/delete"


class TestInsteonWorkflow:
    """New commands composed with existing ones — the agent loop."""

    def test_link_record_change_then_write_then_read_back(self, runner, fake_client):
        fake_client.set_ws("insteon/aldb/get", [{"mem_addr": 4095, "in_use": True, "dirty": False}])
        assert _invoke(runner, "insteon", "aldb", "1a.2b.3c").exit_code == 0
        assert _invoke(runner, "insteon", "aldb-change", "1a.2b.3c", RECORD).exit_code == 0
        assert _invoke(runner, "insteon", "aldb-write", "1a.2b.3c").exit_code == 0
        types = [c["type"] for c in fake_client.ws_calls]
        assert types == ["insteon/aldb/get", "insteon/aldb/change", "insteon/aldb/write"]

    def test_property_set_then_write_then_reload(self, runner, fake_client):
        assert _invoke(runner, "insteon", "property-set", "1a.2b.3c", "on_level", "255").exit_code == 0
        assert _invoke(runner, "insteon", "properties-write", "1a.2b.3c").exit_code == 0
        assert _invoke(runner, "insteon", "properties-load", "1a.2b.3c").exit_code == 0
        types = [c["type"] for c in fake_client.ws_calls]
        assert types == [
            "insteon/properties/change",
            "insteon/properties/write",
            "insteon/properties/load",
        ]

    def test_broken_links_then_remove_with_refs(self, runner, fake_client):
        fake_client.set_ws(
            "insteon/config/get_broken_links",
            [{"address": "9c.9d.9e", "target_name": "dead switch"}],
        )
        assert _invoke(runner, "insteon", "broken-links").exit_code == 0
        assert _invoke(
            runner, "insteon", "device-remove", "9c.9d.9e", "--yes", "--remove-all-refs"
        ).exit_code == 0
        types = [c["type"] for c in fake_client.ws_calls]
        assert types == ["insteon/config/get_broken_links", "insteon/device/remove"]
