"""CLI wiring tests for the `zwave` group (v1.54 refine pass).

Click CliRunner + FakeClient, per the existing wiring-test pattern: the real
Click decorators and option parsing run, the wire client is faked. The
payload each command builds is asserted against zwave_js's schemas —
entry-vs-device exclusivity and int/bitmask values are what HA rejects at
the websocket layer if the wiring is wrong.
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


class TestZwaveAvailableCli:
    def test_loaded(self, runner, fake_client):
        fake_client.set_ws("get_config", {"components": ["zwave_js"]})
        r = _invoke(runner, "zwave", "available")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["available"] is True

    def test_not_loaded(self, runner, fake_client):
        fake_client.set_ws("get_config", {"components": []})
        r = _invoke(runner, "zwave", "available")
        assert r.exit_code == 0
        assert json.loads(r.output)["available"] is False


class TestZwaveStatusCli:
    def test_by_entry(self, runner, fake_client):
        fake_client.set_ws("zwave_js/network_status", {"home_id": 1})
        r = _invoke(runner, "zwave", "status", "--entry", "e1")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["home_id"] == 1
        assert fake_client.ws_calls[-1]["payload"] == {"entry_id": "e1"}

    def test_requires_one_identifier(self, runner, fake_client):
        r = _invoke(runner, "zwave", "status")
        assert r.exit_code != 0
        assert "exactly one" in r.output

    def test_json_flag_after_the_subcommand_is_hoisted_by_main(self, runner, fake_client):
        """`main()` hoists --json from any position; verify the hoist order works."""
        hoisted = cli_mod.hoist_global_flags(["cli", "zwave", "status", "--entry", "e1", "--json"])
        assert hoisted[1] == "--json"
        fake_client.set_ws("zwave_js/network_status", {"home_id": 2})
        result = runner.invoke(
            cli_mod.cli,
            hoisted[1:],
            obj={
                "url": "http://x",
                "token": "t",
                "verify_ssl": False,
                "timeout": 5,
                "as_json": False,
                "config_path": None,
            },
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["home_id"] == 2


class TestZwaveNodesCli:
    def test_list(self, runner, fake_client):
        fake_client.set_ws(
            "config/device_registry/list",
            [{"id": "d1", "name": "Front door", "identifiers": [["zwave_js", "1-2"]]}],
        )
        r = _invoke(runner, "zwave", "nodes")
        assert r.exit_code == 0, r.output
        rows = json.loads(r.output)
        assert rows[0]["node_id"] == "2"

    def test_pattern_passes_through(self, runner, fake_client):
        fake_client.set_ws("config/device_registry/list", [])
        r = _invoke(runner, "zwave", "nodes", "--pattern", "door")
        assert r.exit_code == 0


class TestZwaveNodeCli:
    def test_entity_id_resolved(self, runner, fake_client):
        fake_client.set_ws("config/entity_registry/get", {"device_id": "dev-1"})
        fake_client.set_ws("zwave_js/node_status", {"status": "Ready"})
        r = _invoke(runner, "zwave", "node", "lock.front")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["status"] == "Ready"
        assert fake_client.ws_calls[-1]["payload"] == {"device_id": "dev-1"}


class TestZwaveConfigCli:
    def test_get(self, runner, fake_client):
        fake_client.set_ws("zwave_js/get_config_parameters", {"21-112-0-1": {"property": 1}})
        r = _invoke(runner, "zwave", "config", "dev-1")
        assert r.exit_code == 0, r.output
        assert "21-112-0-1" in json.loads(r.output)

    def test_set_integer(self, runner, fake_client):
        r = _invoke(runner, "zwave", "config-set", "dev-1", "3", "1")
        assert r.exit_code == 0, r.output
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload == {"device_id": "dev-1", "property": 3, "endpoint": 0, "value": 1}

    def test_set_hex(self, runner, fake_client):
        r = _invoke(runner, "zwave", "config-set", "dev-1", "3", "0x2a")
        assert r.exit_code == 0
        assert fake_client.ws_calls[-1]["payload"]["value"] == 42

    def test_set_bitmask_json(self, runner, fake_client):
        r = _invoke(runner, "zwave", "config-set", "dev-1", "3", '{"1": true, "4": true}')
        assert r.exit_code == 0
        assert fake_client.ws_calls[-1]["payload"]["value"] == {"1": True, "4": True}

    def test_set_property_key_and_endpoint(self, runner, fake_client):
        r = _invoke(
            runner,
            "zwave",
            "config-set",
            "dev-1",
            "3",
            "1",
            "--property-key",
            "2",
            "--endpoint",
            "4",
        )
        assert r.exit_code == 0
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["property_key"] == 2
        assert payload["endpoint"] == 4

    def test_set_garbage_value_refused(self, runner, fake_client):
        r = _invoke(runner, "zwave", "config-set", "dev-1", "3", "maybe")
        assert r.exit_code != 0
        assert "bitmask" in r.output


class TestZwaveWritesCli:
    def test_begin_and_stop_rebuild(self, runner, fake_client):
        r = _invoke(runner, "zwave", "begin-rebuild-routes", "e1")
        assert r.exit_code == 0, r.output
        r = _invoke(runner, "zwave", "stop-rebuild-routes", "e1")
        assert r.exit_code == 0

    def test_log_config_set_partial(self, runner, fake_client):
        r = _invoke(runner, "zwave", "log-config-set", "e1", "--level", "debug")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {
            "entry_id": "e1",
            "config": {"level": "debug"},
        }

    def test_data_collection_opt_in(self, runner, fake_client):
        r = _invoke(runner, "zwave", "data-collection-opt", "e1", "--in")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {"entry_id": "e1", "opted_in": True}

    def test_data_collection_opt_out(self, runner, fake_client):
        r = _invoke(runner, "zwave", "data-collection-opt", "e1", "--out")
        assert r.exit_code == 0
        assert fake_client.ws_calls[-1]["payload"]["opted_in"] is False

    def test_config_updates_install_needs_confirmation(self, runner, fake_client):
        r = _invoke(runner, "zwave", "config-updates-install", "e1", input="n\n")
        assert r.exit_code != 0
        assert fake_client.ws_calls == []

    def test_hard_reset_needs_confirmation(self, runner, fake_client):
        r = _invoke(runner, "zwave", "hard-reset", "e1", input="n\n")
        assert r.exit_code != 0
        assert "REM" in r.output or "factory" in r.output.lower()

    def test_hard_reset_confirmed(self, runner, fake_client):
        r = _invoke(runner, "zwave", "hard-reset", "e1", input="y\n")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["type"] == "zwave_js/hard_reset_controller"


class TestZwaveServicesCli:
    def test_ping(self, runner, fake_client):
        r = _invoke(runner, "zwave", "ping", "sensor.door")
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["path"] == "services/zwave_js/ping"
        assert fake_client.calls[-1]["payload"] == {"entity_id": "sensor.door"}

    def test_lock_usercode(self, runner, fake_client):
        r = _invoke(runner, "zwave", "lock-usercode", "lock.front", "3", "1234")
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["payload"] == {
            "entity_id": "lock.front",
            "code_slot": 3,
            "usercode": "1234",
        }

    def test_lock_clear_usercode(self, runner, fake_client):
        r = _invoke(runner, "zwave", "lock-clear-usercode", "lock.front", "3")
        assert r.exit_code == 0

    def test_lock_configuration(self, runner, fake_client):
        r = _invoke(
            runner,
            "zwave",
            "lock-configuration",
            "lock.front",
            "--operation-type",
            "timed",
            "--timeout",
            "30",
        )
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["payload"] == {
            "entity_id": "lock.front",
            "operation_type": "timed",
            "lock_timeout": 30,
        }

    def test_lock_configuration_rejects_bad_operation(self, runner, fake_client):
        r = _invoke(
            runner, "zwave", "lock-configuration", "lock.front", "--operation-type", "whenever"
        )
        assert r.exit_code != 0


class TestZwaveAbsentIntegrationCli:
    """unknown_command must surface as the integration explanation, cleanly."""

    def _wire_absent(self, fake_client):
        fake_client.set_ws_error("zwave_js/node_status", "unknown_command", "Invalid")

    def test_error_message_names_the_integration(self, runner, fake_client):
        self._wire_absent(fake_client)
        r = _invoke(runner, "zwave", "node", "dev-1")
        assert r.exit_code != 0
        assert "no Z-Wave controller" in r.output
        assert "unknown_command" not in r.output

    def test_available_cli_is_the_branch_point(self, runner, fake_client):
        fake_client.set_ws("get_config", {"components": ["hue"]})
        r = _invoke(runner, "zwave", "available")
        assert json.loads(r.output)["available"] is False
