"""CLI wiring tests for the `matter` group (v1.56 refine pass).

Click CliRunner + FakeClient, per the existing wiring-test pattern: the real
Click decorators and option parsing run, the wire client is faked. The
payload each command builds is asserted against matter's schemas — the
admin/destructive confirmation gates and the pin/fabric-index validation are
what HA rejects at the websocket layer if the wiring is wrong.
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


class TestMatterAvailableCli:
    def test_loaded(self, runner, fake_client):
        fake_client.set_ws("get_config", {"components": ["matter"]})
        r = _invoke(runner, "matter", "available")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["available"] is True

    def test_not_loaded(self, runner, fake_client):
        fake_client.set_ws("get_config", {"components": []})
        r = _invoke(runner, "matter", "available")
        assert r.exit_code == 0
        assert json.loads(r.output)["available"] is False

    def test_group_in_root_help(self, runner):
        r = _invoke(runner, "--help")
        assert r.exit_code == 0
        assert "matter" in r.output


class TestMatterNodesCli:
    DEVICES = [
        {"id": "d1", "name": "Hall Switch",
         "identifiers": [["matter", "deviceid_0000000000000001-0000000000000064-MatterNodeDevice"]]},
    ]

    def test_lists_with_extracted_node_id(self, runner, fake_client):
        fake_client.set_ws("config/device_registry/list", self.DEVICES)
        r = _invoke(runner, "matter", "nodes")
        assert r.exit_code == 0, r.output
        out = json.loads(r.output)
        assert out[0]["node_id"] == 0x64

    def test_json_output_everywhere(self, runner, fake_client):
        fake_client.set_ws("config/device_registry/list", self.DEVICES)
        r = _invoke(runner, "matter", "nodes")
        json.loads(r.output)  # must parse


class TestMatterCommissionCli:
    def test_default_network_only(self, runner, fake_client):
        r = _invoke(runner, "matter", "commission", "MT:abcd")
        assert r.exit_code == 0, r.output
        call = fake_client.ws_calls[-1]
        assert call["type"] == "matter/commission"
        assert call["payload"] == {"code": "MT:abcd", "network_only": True}

    def test_opt_out(self, runner, fake_client):
        _invoke(runner, "matter", "commission", "MT:abcdefgh", "--no-network-only")
        assert fake_client.ws_calls[-1]["payload"]["network_only"] is False


class TestMatterCommissionOnNetworkCli:
    def test_wiring(self, runner, fake_client):
        r = _invoke(runner, "matter", "commission-on-network", "12345678", "--ip", "10.0.0.9")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {
            "pin": 12345678,
            "ip_addr": "10.0.0.9",
        }

    def test_non_int_pin_refused_by_click(self, runner, fake_client):
        r = _invoke(runner, "matter", "commission-on-network", "MT:code")
        assert r.exit_code != 0
        assert fake_client.ws_calls == []


class TestMatterSetWifiCli:
    def test_password_prompted_and_hidden(self, runner, fake_client):
        r = _invoke(runner, "matter", "set-wifi", "home", input="hunter2\n")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {
            "network_name": "home",
            "password": "hunter2",
        }
        # the prompt must not echo the password into the transcript
        assert "hunter2" not in r.output


class TestMatterSetThreadCli:
    def test_wiring(self, runner, fake_client):
        r = _invoke(runner, "matter", "set-thread", "1af303")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {"thread_operation_dataset": "1af303"}


class TestMatterNodeCommandsCli:
    @pytest.mark.parametrize(
        ("args", "ws_type"),
        [
            (("node-diagnostics", "dev-1"), "matter/node_diagnostics"),
            (("ping", "dev-1"), "matter/ping_node"),
            (("interview", "dev-1"), "matter/interview_node"),
            (("open-commissioning-window", "dev-1"), "matter/open_commissioning_window"),
        ],
    )
    def test_wiring(self, runner, fake_client, args, ws_type):
        r = _invoke(runner, "matter", *args)
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["type"] == ws_type
        assert fake_client.ws_calls[-1]["payload"] == {"device_id": "dev-1"}


class TestMatterRemoveFabricCli:
    def test_confirmation_gated(self, runner, fake_client):
        fake_client.ws_calls.clear()
        r = _invoke(runner, "matter", "remove-fabric", "dev-1", "2")
        assert r.exit_code != 0  # aborted at the prompt
        assert fake_client.ws_calls == []

    def test_confirmed_send(self, runner, fake_client):
        r = _invoke(runner, "matter", "remove-fabric", "dev-1", "2", input="y\n")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {
            "device_id": "dev-1",
            "fabric_index": 2,
        }

    def test_declined_aborts_cleanly(self, runner, fake_client):
        r = _invoke(runner, "matter", "remove-fabric", "dev-1", "2", input="n\n")
        assert r.exit_code != 0
        assert fake_client.ws_calls == []


class TestMatterAbsentCli:
    """An unloaded integration must read as one clean sentence, not a code."""

    def test_ping_error_message(self, runner, fake_client):
        fake_client.set_ws_error("matter/ping_node", "unknown_command", "Invalid")
        r = _invoke(runner, "matter", "ping", "dev-1")
        assert r.exit_code == 1
        assert "no Matter controller" in r.stderr or "no Matter controller" in r.output

    def test_ping_no_traceback(self, runner, fake_client):
        fake_client.set_ws_error("matter/ping_node", "unknown_command", "Invalid")
        r = _invoke(runner, "matter", "ping", "dev-1")
        assert "Traceback" not in r.output
