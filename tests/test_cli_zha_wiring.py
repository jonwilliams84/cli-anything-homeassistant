"""CLI wiring tests for the `zha` group (v1.55 refine pass).

Click CliRunner + FakeClient, per the existing wiring-test pattern: the real
Click decorators and option parsing run, the wire client is faked. The
payload each command builds is asserted against zha's schemas — IEEE shape,
ieee:endpoint members, JSON-only bindings, the 11–26 channel range and the
args/params exclusivity are what HA rejects at the websocket layer if the
wiring is wrong.
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


IEEE = "00:0d:6f:00:05:7d:2d:34"


class TestZhaAvailableCli:
    def test_loaded(self, runner, fake_client):
        fake_client.set_ws("get_config", {"components": ["zha"]})
        r = _invoke(runner, "zha", "available")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["available"] is True

    def test_not_loaded(self, runner, fake_client):
        fake_client.set_ws("get_config", {"components": []})
        r = _invoke(runner, "zha", "available")
        assert r.exit_code == 0
        assert json.loads(r.output)["available"] is False


class TestZhaDeviceCli:
    def test_device(self, runner, fake_client):
        fake_client.set_ws("zha/device", {"ieee": IEEE})
        r = _invoke(runner, "zha", "device", IEEE)
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["ieee"] == IEEE
        assert fake_client.ws_calls[-1]["payload"] == {"ieee": IEEE}

    def test_bad_ieee_is_refused_up_front(self, runner, fake_client):
        r = _invoke(runner, "zha", "device", "nope")
        assert r.exit_code != 0
        assert "IEEE" in r.output
        assert fake_client.ws_calls == []


class TestZhaGroupCli:
    def test_add_with_members(self, runner, fake_client):
        fake_client.set_ws("zha/group/add", {"name": "Lights"})
        r = _invoke(runner, "zha", "group-add", "Lights", "--group-id", "5", "-m", f"{IEEE}:1")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {
            "name": "Lights",
            "group_id": 5,
            "members": [{"ieee": IEEE, "endpoint_id": 1}],
        }

    def test_remove_takes_several_ids(self, runner, fake_client):
        fake_client.set_ws("zha/group/remove", [])
        r = _invoke(runner, "zha", "group-remove", "1", "2")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {"group_ids": [1, 2]}

    def test_members_add(self, runner, fake_client):
        fake_client.set_ws("zha/group/members/add", {})
        r = _invoke(runner, "zha", "group-members-add", "3", "-m", f"{IEEE}:2")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {
            "group_id": 3,
            "members": [{"ieee": IEEE, "endpoint_id": 2}],
        }

    def test_members_add_requires_a_member(self, runner, fake_client):
        r = _invoke(runner, "zha", "group-members-add", "3")
        assert r.exit_code != 0


class TestZhaClustersCli:
    def _common(self, runner, fake_client, cmd, ws_type):
        fake_client.set_ws(ws_type, [])
        r = _invoke(runner, "zha", cmd, IEEE, "-e", "1", "-c", "6", "-t", "in")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {
            "ieee": IEEE,
            "endpoint_id": 1,
            "cluster_id": 6,
            "cluster_type": "in",
        }

    def test_cluster_attributes(self, runner, fake_client):
        self._common(runner, fake_client, "cluster-attributes", "zha/devices/clusters/attributes")

    def test_cluster_commands(self, runner, fake_client):
        self._common(runner, fake_client, "cluster-commands", "zha/devices/clusters/commands")

    def test_read_attribute(self, runner, fake_client):
        fake_client.set_ws("zha/devices/clusters/attributes/value", "25")
        r = _invoke(runner, "zha", "read-attribute", IEEE, "-e", "1", "-c", "0", "-a", "0")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output) == "25"


class TestZhaBindingCli:
    BINDING = '{"name": "0x0006", "type": "in", "id": 6, "endpoint_id": 1}'

    def test_bind(self, runner, fake_client):
        fake_client.set_ws("zha/devices/bind", None)
        r = _invoke(runner, "zha", "bind", IEEE, "00:0a:bf:00:01:10:23:35")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {
            "source_ieee": IEEE,
            "target_ieee": "00:0a:bf:00:01:10:23:35",
        }

    def test_groups_bind(self, runner, fake_client):
        fake_client.set_ws("zha/groups/bind", None)
        r = _invoke(runner, "zha", "groups-bind", IEEE, "9", "-b", self.BINDING)
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"]["bindings"] == [
            {"name": "0x0006", "type": "in", "id": 6, "endpoint_id": 1}
        ]

    def test_groups_bind_requires_a_binding(self, runner, fake_client):
        r = _invoke(runner, "zha", "groups-bind", IEEE, "9")
        assert r.exit_code != 0


class TestZhaNetworkCli:
    def test_network_settings(self, runner, fake_client):
        fake_client.set_ws("zha/network/settings", {"radio_type": "znp"})
        r = _invoke(runner, "zha", "network-settings")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["radio_type"] == "znp"

    def test_backups(self, runner, fake_client):
        fake_client.set_ws("zha/network/backups/list", [{"backup": {}}])
        r = _invoke(runner, "zha", "network-backups")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)[0]["backup"] == {}

    def test_backup_restore_is_confirmation_gated(self, runner, fake_client):
        fake_client.set_ws("zha/network/backups/restore", None)
        r = _invoke(runner, "zha", "network-backup-restore", '{"backup": {}}', input="n\n")
        assert r.exit_code != 0
        assert fake_client.ws_calls == []
        r = _invoke(runner, "zha", "network-backup-restore", '{"backup": {}}', input="y\n")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {"backup": {}}

    def test_channel_change_is_confirmation_gated(self, runner, fake_client):
        fake_client.set_ws("zha/network/change_channel", None)
        r = _invoke(runner, "zha", "channel-change", "15", input="n\n")
        assert r.exit_code != 0
        assert fake_client.ws_calls == []
        r = _invoke(runner, "zha", "channel-change", "auto", input="y\n")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {"new_channel": "auto"}

    def test_channel_change_rejects_out_of_range(self, runner, fake_client):
        r = _invoke(runner, "zha", "channel-change", "10")
        assert r.exit_code != 0
        assert "11" in r.output


class TestZhaConfigurationCli:
    def test_configuration_update_is_gated_and_shape_checked(self, runner, fake_client):
        fake_client.set_ws("zha/configuration/update", True)
        r = _invoke(runner, "zha", "configuration-update", '{"zha_options": {}}', input="n\n")
        assert r.exit_code != 0
        r = _invoke(runner, "zha", "configuration-update", '{"zha_options": {}}', input="y\n")
        assert r.exit_code == 0, r.output

    def test_configuration_update_rejects_non_object(self, runner, fake_client):
        r = _invoke(runner, "zha", "configuration-update", "[1]")
        assert r.exit_code != 0


class TestZhaRemoveCli:
    def test_is_confirmation_gated(self, runner, fake_client):
        fake_client.set_ws("get_config", {"components": ["zha"]})
        r = _invoke(runner, "zha", "remove", IEEE, input="n\n")
        assert r.exit_code != 0
        assert fake_client.service_calls == []
        r = _invoke(runner, "zha", "remove", IEEE, input="y\n")
        assert r.exit_code == 0, r.output
        assert fake_client.service_calls[-1]["service"] == "remove"


class TestZhaServiceCli:
    def test_set_attribute_value_types(self, runner, fake_client):
        fake_client.set_service("zha", "set_zigbee_cluster_attribute", None)
        r = _invoke(runner, "zha", "set-attribute", IEEE, "-e", "1", "-c", "8", "-a", "16", "-v", "200")
        assert r.exit_code == 0, r.output
        assert fake_client.service_calls[-1]["service_data"]["value"] == 200
        r = _invoke(runner, "zha", "set-attribute", IEEE, "-e", "1", "-c", "8", "-a", "16", "-v", "true")
        assert fake_client.service_calls[-1]["service_data"]["value"] is True
        r = _invoke(runner, "zha", "set-attribute", IEEE, "-e", "1", "-c", "8", "-a", "16", "-v", "warm")
        assert fake_client.service_calls[-1]["service_data"]["value"] == "warm"

    def test_issue_command(self, runner, fake_client):
        fake_client.set_service("zha", "issue_zigbee_cluster_command", None)
        r = _invoke(
            runner, "zha", "issue-command", IEEE, "-e", "1", "-c", "6",
            "--command", "0", "--command-type", "server", "--params", '{"mode": 1}',
        )
        assert r.exit_code == 0, r.output
        data = fake_client.service_calls[-1]["service_data"]
        assert data["params"] == {"mode": 1}
        assert data["command_type"] == "server"

    def test_issue_command_demands_args_or_params(self, runner, fake_client):
        r = _invoke(runner, "zha", "issue-command", IEEE, "-e", "1", "-c", "6", "--command", "0", "--command-type", "server")
        assert r.exit_code != 0
        r = _invoke(runner, "zha", "issue-command", IEEE, "-e", "1", "-c", "6", "--command", "0", "--command-type", "server", "--params", "{}", "--args", "[]")
        assert r.exit_code != 0

    def test_issue_group_command(self, runner, fake_client):
        fake_client.set_service("zha", "issue_zigbee_group_command", None)
        r = _invoke(runner, "zha", "issue-group-command", "5", "-c", "6", "--command", "0", "--args", "[1]")
        assert r.exit_code == 0, r.output
        assert fake_client.service_calls[-1]["service_data"]["args"] == [1]

    def test_warning_squawk(self, runner, fake_client):
        fake_client.set_service("zha", "warning_device_squawk", None)
        r = _invoke(runner, "zha", "warning-squawk", IEEE)
        assert r.exit_code == 0, r.output
        assert fake_client.service_calls[-1]["service_data"] == {
            "ieee": IEEE, "mode": 0, "strobe": 1, "level": 2,
        }

    def test_warning_warn(self, runner, fake_client):
        fake_client.set_service("zha", "warning_device_warn", None)
        r = _invoke(runner, "zha", "warning-warn", IEEE, "--duration", "10")
        assert r.exit_code == 0, r.output
        assert fake_client.service_calls[-1]["service_data"]["duration"] == 10


class TestZhaGroupRegistered:
    def test_every_command_is_registered(self):
        names = {c.name for c in cli_mod.zha.commands.values()}
        assert {
            "available", "devices", "device", "devices-groupable", "bindable",
            "groups", "group", "group-add", "group-remove", "group-members-add",
            "group-members-remove", "clusters", "cluster-attributes",
            "cluster-commands", "read-attribute", "bind", "unbind",
            "groups-bind", "groups-unbind", "configuration",
            "configuration-update", "network-settings", "network-backups",
            "network-backup-create", "network-backup-restore", "channel-change",
            "remove", "set-attribute", "issue-command", "issue-group-command",
            "warning-squawk", "warning-warn",
        } == names

    def test_every_command_carries_a_docstring(self):
        for c in cli_mod.zha.commands.values():
            assert c.help, f"zha {c.name} ships without --help text"

    def test_every_command_supports_json(self, runner, fake_client):
        """Spot-check: --json works from the group, not just the subcommand."""
        fake_client.set_ws("get_config", {"components": []})
        r = _invoke(runner, "zha", "available")
        assert r.exit_code == 0
        assert isinstance(json.loads(r.output), dict)
