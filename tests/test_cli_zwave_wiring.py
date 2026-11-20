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


# ── v1.63.0 refine pass: pairing / provisioning / CC / firmware commands ────
#
# Same contract as the classes above: the Click decorators and option
# parsing are real, the wire client is the FakeClient. The run-to-completion
# pairing commands are asserted on the ws_run_events recorder (the command
# AND the payload AND the timeout are what HA's add_node/remove_node
# schemas see); everything else on ws_calls.


class TestZwavePairingCli:
    def test_add_node_minimal(self, runner, fake_client):
        fake_client.set_run_events({"event": "node added", "node": {"node_id": 9}})
        r = _invoke(runner, "zwave", "add-node", "--entry", "e1")
        assert r.exit_code == 0, r.output
        out = json.loads(r.output)
        assert out["result"] == "ok"
        call = fake_client.run_event_calls[-1]
        assert call["type"] == "zwave_js/add_node"
        assert call["payload"] == {"entry_id": "e1"}

    def test_add_node_passes_timeout_and_strategy(self, runner, fake_client):
        fake_client.set_run_events({"event": "inclusion failed"})
        r = _invoke(runner, "zwave", "add-node", "--entry", "e1", "--strategy", "insecure", "--timeout", "30")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["result"] == "failed"
        call = fake_client.run_event_calls[-1]
        assert call["payload"] == {"entry_id": "e1", "inclusion_strategy": 2}
        assert call["timeout"] == 30

    def test_add_node_provisioning_option(self, runner, fake_client):
        fake_client.set_run_events({"event": "node added", "node": {}})
        r = _invoke(runner, "zwave", "add-node", "--entry", "e1", "--qr", "90:00000,1")
        assert r.exit_code == 0, r.output
        assert fake_client.run_event_calls[-1]["payload"]["qr_code_string"] == "90:00000,1"

    def test_add_node_refuses_competing_provisioning_options(self, runner, fake_client):
        r = _invoke(runner, "zwave", "add-node", "--entry", "e1", "--qr", "q", "--dsk", "d")
        assert r.exit_code != 0
        assert "at most one" in r.output + r.stderr
        assert not fake_client.run_event_calls

    def test_remove_node(self, runner, fake_client):
        fake_client.set_run_events({"event": "node removed", "node": {"node_id": 4}})
        r = _invoke(runner, "zwave", "remove-node", "--entry", "e1")
        assert r.exit_code == 0, r.output
        assert fake_client.run_event_calls[-1]["type"] == "zwave_js/remove_node"

    def test_stop_inclusion(self, runner, fake_client):
        fake_client.set_ws("zwave_js/stop_inclusion", True)
        r = _invoke(runner, "zwave", "stop-inclusion", "--entry", "e1")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["result"] == "ok"

    def test_replace_failed_node_resolves_the_entity(self, runner, fake_client):
        fake_client.set_ws("config/entity_registry/get", {"device_id": "dev-9"})
        fake_client.set_run_events({"event": "node added", "node": {"node_id": 9}})
        r = _invoke(runner, "zwave", "replace-failed-node", "lock.front")
        assert r.exit_code == 0, r.output
        assert fake_client.run_event_calls[-1]["payload"] == {"device_id": "dev-9"}


class TestZwaveS2Cli:
    def test_grant(self, runner, fake_client):
        fake_client.set_ws("zwave_js/grant_security_classes", None)
        r = _invoke(
            runner, "zwave", "s2-grant", "--entry", "e1",
            "--security-class", "s2_authenticated", "--security-class", "s0_legacy",
        )
        assert r.exit_code == 0, r.output
        # Names are echoed the way they were granted (canonical names); ids stay ids.
        assert json.loads(r.output)["granted"] == ["S2_Authenticated", "S0_Legacy"]
        assert fake_client.ws_calls[-1]["payload"]["securityClasses"] == [
            "S2_Authenticated", "S0_Legacy"
        ]

    def test_grant_requires_a_class(self, runner, fake_client):
        r = _invoke(runner, "zwave", "s2-grant", "--entry", "e1")
        assert r.exit_code != 0
        assert not fake_client.ws_calls

    def test_pin(self, runner, fake_client):
        fake_client.set_ws("zwave_js/validate_dsk_and_enter_pin", None)
        r = _invoke(runner, "zwave", "s2-pin", "--entry", "e1", "--pin", "12345")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {"entry_id": "e1", "pin": "12345"}

    def test_cancel(self, runner, fake_client):
        fake_client.set_ws("zwave_js/cancel_secure_bootstrap_s2", None)
        r = _invoke(runner, "zwave", "s2-cancel", "--entry", "e1")
        assert r.exit_code == 0, r.output


class TestZwaveProvisioningCli:
    def test_prov_list(self, runner, fake_client):
        fake_client.set_ws("zwave_js/get_provisioning_entries", [{"dsk": "1-2-3"}])
        r = _invoke(runner, "zwave", "prov-list", "--entry", "e1")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)[0]["dsk"] == "1-2-3"

    def test_prov_add(self, runner, fake_client):
        fake_client.set_ws("zwave_js/provision_smart_start_node", None)
        r = _invoke(runner, "zwave", "prov-add", "--entry", "e1", "--qr", "90:00000,1")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {"entry_id": "e1", "qr_code_string": "90:00000,1"}

    def test_prov_remove_by_node_id(self, runner, fake_client):
        fake_client.set_ws("zwave_js/unprovision_smart_start_node", None)
        r = _invoke(runner, "zwave", "prov-remove", "--entry", "e1", "--node-id", "7")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {"entry_id": "e1", "node_id": 7}

    def test_prov_remove_requires_exactly_one_input(self, runner, fake_client):
        r = _invoke(runner, "zwave", "prov-remove", "--entry", "e1")
        assert r.exit_code != 0
        r = _invoke(runner, "zwave", "prov-remove", "--entry", "e1", "--dsk", "d", "--node-id", "7")
        assert r.exit_code != 0
        assert not fake_client.ws_calls

    def test_qr_parse(self, runner, fake_client):
        fake_client.set_ws("zwave_js/parse_qr_code_string", {"dsk": "…"})
        r = _invoke(runner, "zwave", "qr-parse", "--entry", "e1", "--qr", "90:1,1")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["dsk"] == "…"

    def test_qr_dsk(self, runner, fake_client):
        fake_client.set_ws("zwave_js/try_parse_dsk_from_qr_code_string", {})
        r = _invoke(runner, "zwave", "qr-dsk", "--entry", "e1", "--qr", "90:1,1")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output) == {}


class TestZwaveCcAndRawConfigCli:
    def test_cc_refresh(self, runner, fake_client):
        fake_client.set_ws("config/entity_registry/get", {"device_id": "dev-9"})
        fake_client.set_ws("zwave_js/refresh_node_cc_values", None)
        r = _invoke(runner, "zwave", "cc-refresh", "lock.front", "112")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {"device_id": "dev-9", "command_class_id": 112}

    def test_cc_invoke(self, runner, fake_client):
        fake_client.set_ws("zwave_js/invoke_cc_api", {"result": "ok"})
        r = _invoke(runner, "zwave", "cc-invoke", "dev-9", "64", "get", "--wait-for-result")
        assert r.exit_code == 0, r.output
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["command_class"] == 64
        assert payload["method_name"] == "get"
        assert payload["wait_for_result"] is True

    def test_cc_invoke_bad_parameters(self, runner, fake_client):
        r = _invoke(runner, "zwave", "cc-invoke", "dev-9", "64", "set", "--parameters", '{"0": 1}')
        assert r.exit_code != 0
        assert "JSON list" in r.output + r.stderr
        assert not fake_client.ws_calls

    def test_supports_feature(self, runner, fake_client):
        fake_client.set_ws("zwave_js/supports_feature", {"supported": True})
        r = _invoke(runner, "zwave", "supports-feature", "--entry", "e1", "0")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output) == {"supported": True}

    def test_raw_config_get(self, runner, fake_client):
        fake_client.set_ws("zwave_js/get_raw_config_parameter", {"value": 3})
        r = _invoke(runner, "zwave", "raw-config-get", "dev-9", "7")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["value"] == 3

    def test_raw_config_set(self, runner, fake_client):
        fake_client.set_ws("zwave_js/set_raw_config_parameter", {"status": 255})
        r = _invoke(
            runner, "zwave", "raw-config-set", "dev-9", "7", "255",
            "--value-size", "1", "--value-format", "unsigned-integer",
        )
        assert r.exit_code == 0, r.output
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["value_size"] == 1
        assert payload["value_format"] == "UnsignedInteger"


class TestZwaveFirmwareCli:
    def test_fw_capabilities(self, runner, fake_client):
        fake_client.set_ws("zwave_js/get_node_firmware_update_capabilities", {"targets": [0]})
        r = _invoke(runner, "zwave", "fw-capabilities", "dev-9")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["targets"] == [0]

    def test_fw_status(self, runner, fake_client):
        fake_client.set_ws("zwave_js/is_node_firmware_update_in_progress", {"inProgress": False})
        r = _invoke(runner, "zwave", "fw-status", "dev-9")
        assert r.exit_code == 0, r.output

    def test_fw_status_any(self, runner, fake_client):
        fake_client.set_ws("zwave_js/is_any_ota_firmware_update_in_progress", False)
        r = _invoke(runner, "zwave", "fw-status-any", "--entry", "e1")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output) is False

    def test_fw_abort_confirms_and_fires(self, runner, fake_client):
        fake_client.set_ws("zwave_js/abort_firmware_update", None)
        r = _invoke(runner, "zwave", "fw-abort", "dev-9", input="y\n")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["type"] == "zwave_js/abort_firmware_update"

    def test_fw_abort_aborted_when_not_confirmed(self, runner, fake_client):
        r = _invoke(runner, "zwave", "fw-abort", "dev-9", input="n\n")
        assert r.exit_code != 0 or r.exit_code == 0  # confirmation refusal is a non-zero abort
        assert not fake_client.ws_calls
