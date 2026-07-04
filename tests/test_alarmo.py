"""Unit tests for the Alarmo module — core functions + CLI wiring.

No real HA required. FakeClient records every REST/WS call.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from cli_anything.homeassistant.core import alarmo as alarmo_core
from cli_anything.homeassistant import homeassistant_cli as cli_mod


# ──────────────────────────────────────────────────────────────── core tests


class TestArm:
    def test_arm_minimal(self, fake_client):
        fake_client.set("POST", "services/alarmo/arm", {"success": True})
        r = alarmo_core.arm(fake_client, "alarm_control_panel.alarmo")
        assert r == {"success": True}
        call = fake_client.calls[-1]
        assert call["verb"] == "POST"
        assert call["path"] == "services/alarmo/arm"
        assert call["payload"] == {"entity_id": "alarm_control_panel.alarmo"}

    def test_arm_with_code_and_mode(self, fake_client):
        alarmo_core.arm(fake_client, "alarm_control_panel.alarmo",
                         code="1234", mode="away")
        p = fake_client.calls[-1]["payload"]
        assert p["entity_id"] == "alarm_control_panel.alarmo"
        assert p["code"] == "1234"
        assert p["mode"] == "away"

    def test_arm_skip_delay_and_force(self, fake_client):
        alarmo_core.arm(fake_client, "alarm_control_panel.alarmo",
                         skip_delay=True, force=True)
        p = fake_client.calls[-1]["payload"]
        assert p["skip_delay"] is True
        assert p["force"] is True

    def test_arm_omits_falsey_flags(self, fake_client):
        alarmo_core.arm(fake_client, "alarm_control_panel.alarmo",
                         skip_delay=False, force=False)
        p = fake_client.calls[-1]["payload"]
        assert "skip_delay" not in p
        assert "force" not in p

    def test_arm_rejects_wrong_domain(self, fake_client):
        with pytest.raises(ValueError, match="alarm_control_panel"):
            alarmo_core.arm(fake_client, "light.kitchen")

    def test_arm_rejects_bad_mode(self, fake_client):
        with pytest.raises(ValueError, match="mode"):
            alarmo_core.arm(fake_client, "alarm_control_panel.alarmo",
                             mode="bogus")

    def test_arm_all_modes_accepted(self, fake_client):
        for mode in alarmo_core.ARM_MODES:
            alarmo_core.arm(fake_client, "alarm_control_panel.alarmo",
                             mode=mode)
            assert fake_client.calls[-1]["payload"]["mode"] == mode


class TestDisarm:
    def test_disarm_minimal(self, fake_client):
        fake_client.set("POST", "services/alarmo/disarm", {"success": True})
        r = alarmo_core.disarm(fake_client, "alarm_control_panel.alarmo")
        assert r == {"success": True}
        p = fake_client.calls[-1]["payload"]
        assert p == {"entity_id": "alarm_control_panel.alarmo"}

    def test_disarm_with_code(self, fake_client):
        alarmo_core.disarm(fake_client, "alarm_control_panel.alarmo",
                           code="9999")
        assert fake_client.calls[-1]["payload"]["code"] == "9999"

    def test_disarm_skip_delay(self, fake_client):
        alarmo_core.disarm(fake_client, "alarm_control_panel.alarmo",
                           skip_delay=True)
        assert fake_client.calls[-1]["payload"]["skip_delay"] is True

    def test_disarm_rejects_wrong_domain(self, fake_client):
        with pytest.raises(ValueError):
            alarmo_core.disarm(fake_client, "switch.x")


class TestEnableDisableUser:
    def test_enable_user(self, fake_client):
        fake_client.set("POST", "services/alarmo/enable_user", {"ok": True})
        r = alarmo_core.enable_user(fake_client, name="Frank")
        assert r == {"ok": True}
        assert fake_client.calls[-1]["payload"] == {"name": "Frank"}

    def test_enable_user_empty_name(self, fake_client):
        with pytest.raises(ValueError, match="name"):
            alarmo_core.enable_user(fake_client, name="")

    def test_disable_user(self, fake_client):
        fake_client.set("POST", "services/alarmo/disable_user", {"ok": True})
        r = alarmo_core.disable_user(fake_client, name="Frank")
        assert r == {"ok": True}
        assert fake_client.calls[-1]["payload"] == {"name": "Frank"}

    def test_disable_user_empty_name(self, fake_client):
        with pytest.raises(ValueError, match="name"):
            alarmo_core.disable_user(fake_client, name="")


class TestConfig:
    def test_get_config(self, fake_client):
        fake_client.set_ws("alarmo/config", {"code_arm_required": True})
        r = alarmo_core.get_config(fake_client)
        assert r == {"code_arm_required": True}
        assert fake_client.ws_calls[-1]["type"] == "alarmo/config"

    def test_get_config_empty(self, fake_client):
        r = alarmo_core.get_config(fake_client)
        assert r == {}

    def test_update_config(self, fake_client):
        fake_client.set("POST", "alarmo/config", {"success": True})
        r = alarmo_core.update_config(fake_client, {"trigger_time": 60})
        assert r == {"success": True}
        call = fake_client.calls[-1]
        assert call["path"] == "alarmo/config"
        assert call["payload"] == {"trigger_time": 60}

    def test_update_config_rejects_empty(self, fake_client):
        with pytest.raises(ValueError, match="empty"):
            alarmo_core.update_config(fake_client, {})

    def test_update_config_rejects_non_dict(self, fake_client):
        with pytest.raises(ValueError, match="dict"):
            alarmo_core.update_config(fake_client, "not a dict")


class TestAreas:
    def test_list_areas(self, fake_client):
        areas = [{"area_id": "a1", "name": "Perimeter"}]
        fake_client.set_ws("alarmo/areas", areas)
        r = alarmo_core.list_areas(fake_client)
        assert r == areas
        assert fake_client.ws_calls[-1]["type"] == "alarmo/areas"

    def test_list_areas_empty(self, fake_client):
        r = alarmo_core.list_areas(fake_client)
        assert r == []

    def test_create_area_minimal(self, fake_client):
        fake_client.set("POST", "alarmo/area", {"success": True})
        r = alarmo_core.create_area(fake_client, name="Perimeter")
        assert r == {"success": True}
        assert fake_client.calls[-1]["payload"] == {"name": "Perimeter"}

    def test_create_area_with_modes(self, fake_client):
        modes = {"away": {"enabled": True, "exit_time": 30, "entry_time": 30}}
        alarmo_core.create_area(fake_client, name="Perimeter", modes=modes)
        p = fake_client.calls[-1]["payload"]
        assert p["name"] == "Perimeter"
        assert p["modes"] == modes

    def test_create_area_rename(self, fake_client):
        alarmo_core.create_area(fake_client, name="New Name",
                                 area_id="a1")
        p = fake_client.calls[-1]["payload"]
        assert p["area_id"] == "a1"

    def test_create_area_empty_name(self, fake_client):
        with pytest.raises(ValueError, match="name"):
            alarmo_core.create_area(fake_client, name="")

    def test_delete_area(self, fake_client):
        fake_client.set("POST", "alarmo/area", {"success": True})
        r = alarmo_core.delete_area(fake_client, "a1")
        assert r == {"success": True}
        assert fake_client.calls[-1]["payload"] == {"area_id": "a1", "remove": True}

    def test_delete_area_empty(self, fake_client):
        with pytest.raises(ValueError, match="area_id"):
            alarmo_core.delete_area(fake_client, "")


class TestListReaders:
    def test_list_sensors(self, fake_client):
        sensors = [{"entity_id": "binary_sensor.door"}]
        fake_client.set_ws("alarmo/sensors", sensors)
        assert alarmo_core.list_sensors(fake_client) == sensors

    def test_list_users(self, fake_client):
        users = [{"name": "Frank", "enabled": True}]
        fake_client.set_ws("alarmo/users", users)
        assert alarmo_core.list_users(fake_client) == users

    def test_list_automations(self, fake_client):
        autos = [{"id": 1, "trigger": "alarm_triggered"}]
        fake_client.set_ws("alarmo/automations", autos)
        assert alarmo_core.list_automations(fake_client) == autos

    def test_list_sensor_groups(self, fake_client):
        groups = [{"group_id": "g1"}]
        fake_client.set_ws("alarmo/sensor_groups", groups)
        assert alarmo_core.list_sensor_groups(fake_client) == groups

    def test_list_entities(self, fake_client):
        entities = [{"entity_id": "alarm_control_panel.alarmo"}]
        fake_client.set_ws("alarmo/entities", entities)
        assert alarmo_core.list_entities(fake_client) == entities

    def test_all_lists_return_empty_on_none(self, fake_client):
        for fn in (alarmo_core.list_sensors, alarmo_core.list_users,
                   alarmo_core.list_automations,
                   alarmo_core.list_sensor_groups, alarmo_core.list_entities):
            assert fn(fake_client) == []


# ──────────────────────────────────────────────────────────────── sensor mutation


class TestSensorShow:
    def test_sensor_show_found(self, fake_client):
        sensor = {"entity_id": "binary_sensor.door", "type": "door"}
        fake_client.set_ws("alarmo/sensors", [sensor])
        r = alarmo_core.sensor_show(fake_client, "binary_sensor.door")
        assert r == sensor

    def test_sensor_show_not_found(self, fake_client):
        fake_client.set_ws("alarmo/sensors", [])
        with pytest.raises(KeyError, match="ghost"):
            alarmo_core.sensor_show(fake_client, "binary_sensor.ghost")

    def test_sensor_show_rejects_wrong_domain(self, fake_client):
        with pytest.raises(ValueError, match="binary_sensor"):
            alarmo_core.sensor_show(fake_client, "light.kitchen")

    def test_sensor_show_rejects_empty(self, fake_client):
        with pytest.raises(ValueError, match="entity_id"):
            alarmo_core.sensor_show(fake_client, "")


class TestSensorRemove:
    def test_sensor_remove(self, fake_client):
        fake_client.set("POST", "alarmo/sensors", {"success": True})
        r = alarmo_core.sensor_remove(fake_client, "binary_sensor.ghost")
        assert r == {"success": True}
        p = fake_client.calls[-1]["payload"]
        assert p == {"entity_id": "binary_sensor.ghost", "remove": True}

    def test_sensor_remove_rejects_wrong_domain(self, fake_client):
        with pytest.raises(ValueError, match="binary_sensor"):
            alarmo_core.sensor_remove(fake_client, "switch.x")

    def test_sensor_remove_rejects_empty(self, fake_client):
        with pytest.raises(ValueError, match="entity_id"):
            alarmo_core.sensor_remove(fake_client, "")


class TestSensorUpdate:
    def test_update_single_field(self, fake_client):
        fake_client.set("POST", "alarmo/sensors", {"success": True})
        r = alarmo_core.sensor_update(fake_client, "binary_sensor.d",
                                        type="door")
        assert r == {"success": True}
        p = fake_client.calls[-1]["payload"]
        assert p == {"entity_id": "binary_sensor.d", "type": "door"}

    def test_update_multiple_fields(self, fake_client):
        fake_client.set("POST", "alarmo/sensors", {"success": True})
        alarmo_core.sensor_update(
            fake_client, "binary_sensor.d",
            type="motion", modes=["armed_away", "armed_home"],
            allow_open=True, area="perimeter",
        )
        p = fake_client.calls[-1]["payload"]
        assert p["type"] == "motion"
        assert p["modes"] == ["armed_away", "armed_home"]
        assert p["allow_open"] is True
        assert p["area"] == "perimeter"

    def test_update_rejects_no_fields(self, fake_client):
        with pytest.raises(ValueError, match="at least one"):
            alarmo_core.sensor_update(fake_client, "binary_sensor.d")

    def test_update_rejects_bad_type(self, fake_client):
        with pytest.raises(ValueError, match="type"):
            alarmo_core.sensor_update(fake_client, "binary_sensor.d",
                                        type="bogus")

    def test_update_rejects_bad_mode(self, fake_client):
        with pytest.raises(ValueError, match="modes entries"):
            alarmo_core.sensor_update(fake_client, "binary_sensor.d",
                                        modes=["bogus_mode"])

    def test_update_rejects_modes_not_list(self, fake_client):
        with pytest.raises(ValueError, match="list"):
            alarmo_core.sensor_update(fake_client, "binary_sensor.d",
                                        modes="armed_away")

    def test_update_rejects_wrong_domain(self, fake_client):
        with pytest.raises(ValueError, match="binary_sensor"):
            alarmo_core.sensor_update(fake_client, "light.k", type="door")

    def test_update_accepts_all_sensor_types(self, fake_client):
        fake_client.set("POST", "alarmo/sensors", {"success": True})
        for t in alarmo_core.SENSOR_TYPES:
            alarmo_core.sensor_update(fake_client, "binary_sensor.d", type=t)
            assert fake_client.calls[-1]["payload"]["type"] == t

    def test_update_accepts_all_arm_modes(self, fake_client):
        fake_client.set("POST", "alarmo/sensors", {"success": True})
        alarmo_core.sensor_update(
            fake_client, "binary_sensor.d",
            modes=list(alarmo_core.SENSOR_ARM_MODES),
        )
        assert fake_client.calls[-1]["payload"]["modes"] == \
            list(alarmo_core.SENSOR_ARM_MODES)

    def test_update_bool_false(self, fake_client):
        """Passing allow_open=False sends it as False, not omits it."""
        fake_client.set("POST", "alarmo/sensors", {"success": True})
        alarmo_core.sensor_update(fake_client, "binary_sensor.d",
                                   allow_open=False)
        p = fake_client.calls[-1]["payload"]
        assert p["allow_open"] is False


# ──────────────────────────────────────────────────────────────── CLI wiring


@pytest.fixture
def runner(monkeypatch, fake_client):
    monkeypatch.setattr(cli_mod, "make_client", lambda ctx: fake_client)
    return CliRunner()


def _invoke(runner, *args, json_out=True):
    full = ["--json"] + list(args) if json_out else list(args)
    return runner.invoke(cli_mod.cli, full,
                         obj={
                             "url": "http://x", "token": "t",
                             "verify_ssl": False, "timeout": 5,
                             "as_json": json_out, "config_path": None,
                         })


class TestAlarmoWiring:
    def test_arm_minimal(self, runner, fake_client):
        r = _invoke(runner, "alarmo", "arm", "alarm_control_panel.alarmo")
        assert r.exit_code == 0, r.output
        s = fake_client.service_calls[-1]
        assert (s["domain"], s["service"]) == ("alarmo", "arm")
        assert s["service_data"] == {"entity_id": "alarm_control_panel.alarmo"}

    def test_arm_all_args(self, runner, fake_client):
        r = _invoke(runner, "alarmo", "arm", "alarm_control_panel.alarmo",
                    "--code", "1234", "--mode", "away",
                    "--skip-delay", "--force")
        assert r.exit_code == 0, r.output
        d = fake_client.service_calls[-1]["service_data"]
        assert d["code"] == "1234"
        assert d["mode"] == "away"
        assert d["skip_delay"] is True
        assert d["force"] is True

    def test_arm_rejects_bad_mode(self, runner, fake_client):
        r = _invoke(runner, "alarmo", "arm", "alarm_control_panel.alarmo",
                    "--mode", "bogus")
        assert r.exit_code != 0

    def test_disarm(self, runner, fake_client):
        r = _invoke(runner, "alarmo", "disarm", "alarm_control_panel.alarmo",
                    "--code", "9999")
        assert r.exit_code == 0, r.output
        s = fake_client.service_calls[-1]
        assert (s["domain"], s["service"]) == ("alarmo", "disarm")
        assert s["service_data"]["code"] == "9999"

    def test_disarm_skip_delay(self, runner, fake_client):
        r = _invoke(runner, "alarmo", "disarm", "alarm_control_panel.alarmo",
                    "--skip-delay")
        assert r.exit_code == 0, r.output
        assert fake_client.service_calls[-1]["service_data"]["skip_delay"] is True

    def test_enable_user(self, runner, fake_client):
        r = _invoke(runner, "alarmo", "enable-user", "Frank")
        assert r.exit_code == 0, r.output
        s = fake_client.service_calls[-1]
        assert s["domain"] == "alarmo"
        assert s["service"] == "enable_user"
        assert s["service_data"] == {"name": "Frank"}

    def test_disable_user(self, runner, fake_client):
        r = _invoke(runner, "alarmo", "disable-user", "Frank")
        assert r.exit_code == 0, r.output
        s = fake_client.service_calls[-1]
        assert s["service"] == "disable_user"

    def test_config(self, runner, fake_client):
        fake_client.set_ws("alarmo/config", {"code_arm_required": True})
        r = _invoke(runner, "alarmo", "config")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["code_arm_required"] is True
        assert fake_client.ws_calls[-1]["type"] == "alarmo/config"

    def test_config_set(self, runner, fake_client):
        fake_client.set("POST", "alarmo/config", {"success": True})
        r = _invoke(runner, "alarmo", "config-set",
                    "--data-json", '{"trigger_time": 60}', "--yes")
        assert r.exit_code == 0, r.output
        call = fake_client.calls[-1]
        assert call["path"] == "alarmo/config"
        assert call["payload"] == {"trigger_time": 60}

    def test_config_set_dry_run(self, runner, fake_client):
        r = _invoke(runner, "alarmo", "config-set",
                    "--data-json", '{"trigger_time": 60}', "--dry-run")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["dry_run"] is True
        assert data["json"] == {"trigger_time": 60}
        posts = [c for c in fake_client.calls
                 if c["verb"] == "POST" and c["path"] == "alarmo/config"]
        assert posts == []

    def test_config_set_unconfirmed_aborts(self, runner, fake_client):
        r = runner.invoke(cli_mod.cli,
                          ["--json", "alarmo", "config-set",
                           "--data-json", '{"trigger_time": 60}'],
                          input="n\n",
                          obj={"url": "http://x", "token": "t",
                               "verify_ssl": False, "timeout": 5,
                               "as_json": True, "config_path": None})
        assert r.exit_code != 0

    def test_config_set_requires_data(self, runner, fake_client):
        r = _invoke(runner, "alarmo", "config-set")
        assert r.exit_code != 0

    def test_config_set_bad_json(self, runner, fake_client):
        r = _invoke(runner, "alarmo", "config-set", "--data-json", "not json")
        assert r.exit_code != 0

    def test_areas(self, runner, fake_client):
        fake_client.set_ws("alarmo/areas", [{"area_id": "a1", "name": "Perim"}])
        r = _invoke(runner, "alarmo", "areas")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data[0]["area_id"] == "a1"

    def test_area_create(self, runner, fake_client):
        fake_client.set("POST", "alarmo/area", {"success": True})
        r = _invoke(runner, "alarmo", "area-create", "--name", "Perimeter")
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["payload"] == {"name": "Perimeter"}

    def test_area_create_with_modes(self, runner, fake_client):
        fake_client.set("POST", "alarmo/area", {"success": True})
        r = _invoke(runner, "alarmo", "area-create", "--name", "Perim",
                    "--modes-json", '{"away": {"enabled": true}}')
        assert r.exit_code == 0, r.output
        p = fake_client.calls[-1]["payload"]
        assert p["modes"] == {"away": {"enabled": True}}

    def test_area_delete_confirmed(self, runner, fake_client):
        fake_client.set("POST", "alarmo/area", {"success": True})
        r = _invoke(runner, "alarmo", "area-delete", "a1", "--yes")
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["payload"] == {"area_id": "a1", "remove": True}

    def test_area_delete_dry_run(self, runner, fake_client):
        r = _invoke(runner, "alarmo", "area-delete", "a1", "--dry-run")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["dry_run"] is True
        assert data["json"] == {"area_id": "a1", "remove": True}
        # No POST should have been made
        posts = [c for c in fake_client.calls
                 if c["verb"] == "POST" and c["path"] == "alarmo/area"]
        assert posts == []

    def test_area_delete_unconfirmed_aborts(self, runner, fake_client):
        r = runner.invoke(cli_mod.cli,
                          ["--json", "alarmo", "area-delete", "a1"],
                          input="n\n",
                          obj={"url": "http://x", "token": "t",
                               "verify_ssl": False, "timeout": 5,
                               "as_json": True, "config_path": None})
        assert r.exit_code != 0

    def test_sensors(self, runner, fake_client):
        fake_client.set_ws("alarmo/sensors", [{"entity_id": "binary_sensor.d"}])
        r = _invoke(runner, "alarmo", "sensors")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)[0]["entity_id"] == "binary_sensor.d"

    # ── sensor-show ───────────────────────────────────────────────────

    def test_sensor_show(self, runner, fake_client):
        sensor = {"entity_id": "binary_sensor.front_door",
                   "type": "door", "modes": ["armed_away"]}
        fake_client.set_ws("alarmo/sensors", [sensor])
        r = _invoke(runner, "alarmo", "sensor-show", "binary_sensor.front_door")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["entity_id"] == "binary_sensor.front_door"
        assert data["type"] == "door"

    def test_sensor_show_not_found(self, runner, fake_client):
        fake_client.set_ws("alarmo/sensors", [])
        r = _invoke(runner, "alarmo", "sensor-show", "binary_sensor.ghost")
        assert r.exit_code != 0

    def test_sensor_show_rejects_wrong_domain(self, runner, fake_client):
        r = _invoke(runner, "alarmo", "sensor-show", "light.kitchen")
        assert r.exit_code != 0

    # ── sensor-remove ──────────────────────────────────────────────────

    def test_sensor_remove_with_yes(self, runner, fake_client):
        fake_client.set("POST", "alarmo/sensors", {"success": True})
        r = _invoke(runner, "alarmo", "sensor-remove",
                    "binary_sensor.ghost", "--yes")
        assert r.exit_code == 0, r.output
        p = fake_client.calls[-1]["payload"]
        assert p == {"entity_id": "binary_sensor.ghost", "remove": True}

    def test_sensor_remove_dry_run(self, runner, fake_client):
        r = _invoke(runner, "alarmo", "sensor-remove",
                    "binary_sensor.ghost", "--dry-run")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["dry_run"] is True
        assert data["json"] == {"entity_id": "binary_sensor.ghost",
                                  "remove": True}
        # No POST should have been made
        posts = [c for c in fake_client.calls
                 if c["verb"] == "POST" and c["path"] == "alarmo/sensors"]
        assert posts == []

    def test_sensor_remove_unconfirmed_aborts(self, runner, fake_client):
        fake_client.set_ws("alarmo/sensors",
                            [{"entity_id": "binary_sensor.ghost"}])
        r = runner.invoke(cli_mod.cli,
                          ["--json", "alarmo", "sensor-remove",
                           "binary_sensor.ghost"],
                          input="n\n",
                          obj={"url": "http://x", "token": "t",
                               "verify_ssl": False, "timeout": 5,
                               "as_json": True, "config_path": None})
        assert r.exit_code != 0
        # No POST should have been made
        posts = [c for c in fake_client.calls
                 if c["verb"] == "POST" and c["path"] == "alarmo/sensors"]
        assert posts == []

    def test_sensor_remove_confirmed(self, runner, fake_client):
        fake_client.set_ws("alarmo/sensors",
                            [{"entity_id": "binary_sensor.ghost"}])
        fake_client.set("POST", "alarmo/sensors", {"success": True})
        r = runner.invoke(cli_mod.cli,
                          ["--json", "alarmo", "sensor-remove",
                           "binary_sensor.ghost"],
                          input="y\n",
                          obj={"url": "http://x", "token": "t",
                               "verify_ssl": False, "timeout": 5,
                               "as_json": True, "config_path": None})
        assert r.exit_code == 0, r.output

    def test_sensor_remove_rejects_wrong_domain(self, runner, fake_client):
        r = _invoke(runner, "alarmo", "sensor-remove", "switch.x", "--yes")
        assert r.exit_code != 0

    # ── sensor-update ─────────────────────────────────────────────────

    def test_sensor_update_single_field(self, runner, fake_client):
        fake_client.set("POST", "alarmo/sensors", {"success": True})
        r = _invoke(runner, "alarmo", "sensor-update",
                    "binary_sensor.door", "--type", "door", "--yes")
        assert r.exit_code == 0, r.output
        p = fake_client.calls[-1]["payload"]
        assert p["entity_id"] == "binary_sensor.door"
        assert p["type"] == "door"
        # Only the field we set should be in the payload
        assert "area" not in p
        assert "modes" not in p

    def test_sensor_update_multiple_fields(self, runner, fake_client):
        fake_client.set("POST", "alarmo/sensors", {"success": True})
        r = _invoke(runner, "alarmo", "sensor-update",
                    "binary_sensor.door",
                    "--type", "motion",
                    "--modes", "armed_away,armed_home",
                    "--allow-open",
                    "--area", "perimeter",
                    "--yes")
        assert r.exit_code == 0, r.output
        p = fake_client.calls[-1]["payload"]
        assert p["type"] == "motion"
        assert p["modes"] == ["armed_away", "armed_home"]
        assert p["allow_open"] is True
        assert p["area"] == "perimeter"

    def test_sensor_update_no_fields_errors(self, runner, fake_client):
        r = _invoke(runner, "alarmo", "sensor-update",
                    "binary_sensor.door", "--yes")
        assert r.exit_code != 0

    def test_sensor_update_dry_run(self, runner, fake_client):
        r = _invoke(runner, "alarmo", "sensor-update",
                    "binary_sensor.door", "--type", "door", "--dry-run")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["dry_run"] is True
        assert data["json"]["entity_id"] == "binary_sensor.door"
        assert data["json"]["type"] == "door"
        # No POST
        posts = [c for c in fake_client.calls
                 if c["verb"] == "POST" and c["path"] == "alarmo/sensors"]
        assert posts == []

    def test_sensor_update_bad_mode(self, runner, fake_client):
        r = _invoke(runner, "alarmo", "sensor-update",
                    "binary_sensor.door",
                    "--modes", "bogus_mode", "--yes")
        assert r.exit_code != 0

    def test_sensor_update_rejects_wrong_domain(self, runner, fake_client):
        r = _invoke(runner, "alarmo", "sensor-update",
                    "light.kitchen", "--type", "door", "--yes")
        assert r.exit_code != 0

    def test_sensor_update_bool_flags(self, runner, fake_client):
        """--no-allow-open sends allow_open: False, not omitting the field."""
        fake_client.set("POST", "alarmo/sensors", {"success": True})
        r = _invoke(runner, "alarmo", "sensor-update",
                    "binary_sensor.door", "--no-allow-open", "--yes")
        assert r.exit_code == 0, r.output
        p = fake_client.calls[-1]["payload"]
        assert p["allow_open"] is False

    def test_sensor_update_unconfirmed_aborts(self, runner, fake_client):
        fake_client.set_ws("alarmo/sensors",
                            [{"entity_id": "binary_sensor.door"}])
        r = runner.invoke(cli_mod.cli,
                          ["--json", "alarmo", "sensor-update",
                           "binary_sensor.door", "--type", "door"],
                          input="n\n",
                          obj={"url": "http://x", "token": "t",
                               "verify_ssl": False, "timeout": 5,
                               "as_json": True, "config_path": None})
        assert r.exit_code != 0
        posts = [c for c in fake_client.calls
                 if c["verb"] == "POST" and c["path"] == "alarmo/sensors"]
        assert posts == []

    def test_sensor_update_confirmed(self, runner, fake_client):
        fake_client.set_ws("alarmo/sensors",
                            [{"entity_id": "binary_sensor.door"}])
        fake_client.set("POST", "alarmo/sensors", {"success": True})
        r = runner.invoke(cli_mod.cli,
                          ["--json", "alarmo", "sensor-update",
                           "binary_sensor.door", "--type", "door"],
                          input="y\n",
                          obj={"url": "http://x", "token": "t",
                               "verify_ssl": False, "timeout": 5,
                               "as_json": True, "config_path": None})
        assert r.exit_code == 0, r.output

    def test_users(self, runner, fake_client):
        fake_client.set_ws("alarmo/users", [{"name": "Frank"}])
        r = _invoke(runner, "alarmo", "users")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)[0]["name"] == "Frank"

    def test_automations(self, runner, fake_client):
        fake_client.set_ws("alarmo/automations", [{"id": 1}])
        r = _invoke(runner, "alarmo", "automations")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)[0]["id"] == 1

    def test_sensor_groups(self, runner, fake_client):
        fake_client.set_ws("alarmo/sensor_groups", [{"group_id": "g1"}])
        r = _invoke(runner, "alarmo", "sensor-groups")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)[0]["group_id"] == "g1"

    def test_entities(self, runner, fake_client):
        fake_client.set_ws("alarmo/entities",
                            [{"entity_id": "alarm_control_panel.alarmo"}])
        r = _invoke(runner, "alarmo", "entities")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data[0]["entity_id"] == "alarm_control_panel.alarmo"

    def test_help_lists_all_commands(self, runner):
        r = _invoke(runner, "alarmo", "--help", json_out=False)
        assert r.exit_code == 0
        for cmd in ("arm", "disarm", "enable-user", "disable-user",
                    "config", "config-set", "areas", "area-create",
                    "area-delete", "sensors", "sensor-show",
                    "sensor-remove", "sensor-update",
                    "users", "automations",
                    "sensor-groups", "entities"):
            assert cmd in r.output, f"missing {cmd} in help output"