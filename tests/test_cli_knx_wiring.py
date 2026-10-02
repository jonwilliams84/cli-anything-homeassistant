"""CLI wiring tests for the `knx` group (v1.57 refine pass).

Click CliRunner + FakeClient, per the existing wiring-test pattern: the real
Click decorators and option parsing run, the wire client is faked. The
payload each command builds is asserted against knx's entity-store schema —
the platform restriction, the one-of-name/device rule and the destructive
confirmation gates are what HA rejects at the websocket layer (or the CLI
must refuse before the wire) if the wiring is wrong.
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


SWITCH_DATA = '{"ga_switch":{"write":[["1/1/7"]],"state":[["1/1/8"]]}}'


class TestKnxAvailableCli:
    def test_loaded(self, runner, fake_client):
        fake_client.set_ws("get_config", {"components": ["knx"]})
        r = _invoke(runner, "knx", "available")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["available"] is True

    def test_not_loaded(self, runner, fake_client):
        fake_client.set_ws("get_config", {"components": []})
        r = _invoke(runner, "knx", "available")
        assert r.exit_code == 0
        assert json.loads(r.output)["available"] is False

    def test_group_in_root_help(self, runner):
        r = _invoke(runner, "--help")
        assert r.exit_code == 0
        assert "knx" in r.output


class TestKnxInfoCli:
    def test_info(self, runner, fake_client):
        fake_client.set_ws("knx/info", {"connected": True, "version": "2.8.0"})
        r = _invoke(runner, "knx", "info")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["connected"] is True

    def test_group_monitor(self, runner, fake_client):
        fake_client.set_ws("knx/group_monitor_info", {"recent_telegrams": [], "project_loaded": False})
        r = _invoke(runner, "knx", "group-monitor")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["project_loaded"] is False

    def test_group_telegrams(self, runner, fake_client):
        fake_client.set_ws("knx/group_telegrams", [{"destination_address": "1/1/7"}])
        r = _invoke(runner, "knx", "group-telegrams")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)[0]["destination_address"] == "1/1/7"


class TestKnxEntityStoreCli:
    def test_validate_entity_builds_the_shared_payload(self, runner, fake_client):
        fake_client.set_ws("knx/validate_entity", {"success": True})
        r = _invoke(
            runner, "knx", "validate-entity", "switch", SWITCH_DATA, "--name", "Hall Light",
        )
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["success"] is True
        call = fake_client.ws_calls[-1]
        assert call["type"] == "knx/validate_entity"
        assert call["payload"] == {
            "platform": "switch",
            "data": {"ga_switch": {"write": [["1/1/7"]], "state": [["1/1/8"]]}},
            "name": "Hall Light",
        }

    def test_validate_entity_with_device_and_category(self, runner, fake_client):
        fake_client.set_ws("knx/validate_entity", {"success": True})
        r = _invoke(
            runner, "knx", "validate-entity", "light", '{"ga_switch":{"write":[["1/2/9"]]}}',
            "--device", "dev-uuid", "--category", "diagnostic",
        )
        assert r.exit_code == 0, r.output
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["device_info"] == "dev-uuid"
        assert payload["entity_category"] == "diagnostic"

    def test_platform_choice_is_enforced_by_the_cli(self, runner, fake_client):
        r = _invoke(runner, "knx", "validate-entity", "climate", SWITCH_DATA, "--name", "n")
        assert r.exit_code != 0
        assert not fake_client.ws_calls

    def test_name_or_device_required_client_side(self, runner, fake_client):
        r = _invoke(runner, "knx", "validate-entity", "switch", SWITCH_DATA)
        assert r.exit_code != 0
        assert "name" in r.output or "device" in r.output

    def test_bad_json_is_a_click_error_not_a_traceback(self, runner, fake_client):
        r = _invoke(runner, "knx", "validate-entity", "switch", "{oops", "--name", "n")
        assert r.exit_code != 0
        assert "Traceback" not in r.output

    def test_create_entity(self, runner, fake_client):
        fake_client.set_ws("knx/create_entity", {"success": True, "entity_id": "switch.hall"})
        r = _invoke(runner, "knx", "create-entity", "switch", SWITCH_DATA, "--name", "Hall")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["entity_id"] == "switch.hall"

    def test_update_entity_carries_entity_id(self, runner, fake_client):
        fake_client.set_ws("knx/update_entity", {"success": True})
        r = _invoke(runner, "knx", "update-entity", "switch.hall", "switch",
                    SWITCH_DATA, "--name", "Hall")
        assert r.exit_code == 0, r.output
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["entity_id"] == "switch.hall"

    def test_delete_entity_asks_first(self, runner, fake_client):
        fake_client.set_ws("knx/delete_entity", None)
        r = _invoke(runner, "knx", "delete-entity", "switch.hall",
                    input="y\n", json_out=False)
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {"entity_id": "switch.hall"}

    def test_delete_entity_decline_sends_nothing(self, runner, fake_client):
        r = _invoke(runner, "knx", "delete-entity", "switch.hall",
                    input="n\n", json_out=False)
        assert r.exit_code != 0
        assert not fake_client.ws_calls


class TestKnxProjectCli:
    def test_project_process(self, runner, fake_client):
        fake_client.set_ws("knx/project_file_process", None)
        r = _invoke(runner, "knx", "project-process", "file_123",
                    "--password", "hunter2")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {
            "file_id": "file_123",
            "password": "hunter2",
        }

    def test_project_remove_asks_first(self, runner, fake_client):
        fake_client.set_ws("knx/project_file_remove", None)
        r = _invoke(runner, "knx", "project-remove", input="y\n", json_out=False)
        assert r.exit_code == 0, r.output

    def test_entities_list(self, runner, fake_client):
        fake_client.set_ws("knx/get_entity_entries", [{"entity_id": "switch.hall"}])
        r = _invoke(runner, "knx", "entities")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)[0]["entity_id"] == "switch.hall"

    def test_entity_config(self, runner, fake_client):
        fake_client.set_ws("knx/get_entity_config", {"platform": "switch"})
        r = _invoke(runner, "knx", "entity-config", "switch.hall")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {"entity_id": "switch.hall"}


class TestKnxCreateDeviceCli:
    def test_create_device(self, runner, fake_client):
        fake_client.set_ws("knx/create_device", {"id": "d1", "name": "Hall"})
        r = _invoke(runner, "knx", "create-device", "Hall", "--area", "a1")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {"name": "Hall", "area_id": "a1"}

    def test_empty_name_refused_before_the_wire(self, runner, fake_client):
        r = _invoke(runner, "knx", "create-device", "  ")
        assert r.exit_code != 0
        assert not fake_client.ws_calls


class TestKnxSubscribeCli:
    def test_subscribe_prints_each_telegram_then_the_ack(self, monkeypatch):
        from .conftest import SubscribingFakeClient

        sub_client = SubscribingFakeClient()
        sub_client.queue_events({"destination_address": "1/1/7"}, {"destination_address": "1/1/8"})
        monkeypatch.setattr(cli_mod, "make_client", lambda ctx: sub_client)
        runner = CliRunner()
        r = _invoke(runner, "knx", "subscribe-telegrams", "--max-events", "2", json_out=False)
        assert r.exit_code == 0, r.output
        assert '"destination_address": "1/1/7"' in r.output
        assert '"destination_address": "1/1/8"' in r.output
        assert "stopped: True" in r.output.splitlines()[-2]  # ack printed after the events


class TestKnxWorkflow:
    """New commands composed with existing ones — the agent loop."""

    def test_validate_then_create_then_config_round_trip(self, runner, fake_client):
        fake_client.set_ws("knx/validate_entity", {"success": True})
        assert _invoke(runner, "knx", "validate-entity", "switch", SWITCH_DATA,
                       "--name", "Hall").exit_code == 0
        fake_client.set_ws("knx/create_entity", {"success": True, "entity_id": "switch.hall"})
        assert _invoke(runner, "knx", "create-entity", "switch", SWITCH_DATA,
                       "--name", "Hall").exit_code == 0
        created = fake_client.ws_calls[-1]
        fake_client.set_ws("knx/get_entity_config", {"platform": "switch", "data": {"x": 1}})
        assert _invoke(runner, "knx", "entity-config", created["payload"] and "switch.hall").exit_code == 0
        types = [c["type"] for c in fake_client.ws_calls]
        assert types == ["knx/validate_entity", "knx/create_entity", "knx/get_entity_config"]

    def test_device_then_attached_entity(self, runner, fake_client):
        fake_client.set_ws("knx/create_device", {"id": "d1"})
        assert _invoke(runner, "knx", "create-device", "Hall Unit").exit_code == 0
        fake_client.set_ws("knx/create_entity", {"success": True, "entity_id": "light.h1"})
        light_data = '{"ga_switch":{"write":[["1/2/9"]]}}'
        assert _invoke(runner, "knx", "create-entity", "light", light_data,
                       "--device", "d1").exit_code == 0
        assert fake_client.ws_calls[-1]["payload"]["device_info"] == "d1"
