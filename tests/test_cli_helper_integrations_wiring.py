"""CLI wiring for `helpers create/kinds/entries/show/entities/set-options/delete`.

CliRunner + FakeClient, so the real Click decorators, option parsing and
duration shorthands are exercised without booting Home Assistant.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from cli_anything.homeassistant import homeassistant_cli as cli_mod

FLOW = "config/config_entries/flow"


@pytest.fixture
def runner(monkeypatch, fake_client):
    monkeypatch.setattr(cli_mod, "make_client", lambda ctx: fake_client)
    return CliRunner()


def _invoke(runner, *args, json_out=True):
    full = ["--json"] + list(args) if json_out else list(args)
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
    )


def prime(client, *forms):
    client.set_seq("POST", FLOW, forms[0])
    if len(forms) > 1:
        client.set_seq("POST", f"{FLOW}/F1", *forms[1:])
    client.set_ws(
        "config/entity_registry/list",
        [{"entity_id": "sensor.new", "config_entry_id": "E1"}],
    )


def form(step_id="user", fields=None, flow_id="F1"):
    return {
        "type": "form",
        "flow_id": flow_id,
        "step_id": step_id,
        "data_schema": fields or [],
    }


def menu(options, flow_id="F1"):
    return {"type": "menu", "flow_id": flow_id, "menu_options": list(options)}


def created(entry_id="E1"):
    return {
        "type": "create_entry",
        "title": "New helper",
        "result": {"entry_id": entry_id, "state": "loaded"},
    }


def steps(client):
    return [
        c["payload"]
        for c in client.calls
        if c["verb"] == "POST" and c["path"].startswith(f"{FLOW}/")
    ]


class TestCatalogue:
    def test_kinds_lists_all_sixteen(self, runner, fake_client):
        r = _invoke(runner, "helpers", "kinds")
        assert r.exit_code == 0, r.output
        assert len(json.loads(r.output)["kinds"]) == 16

    def test_kinds_can_describe_one(self, runner, fake_client):
        r = _invoke(runner, "helpers", "kinds", "riemann")
        assert json.loads(r.output)["domain"] == "integration"

    def test_unknown_kind_is_a_clean_error(self, runner, fake_client):
        r = _invoke(runner, "helpers", "kinds", "nope")
        assert r.exit_code != 0
        assert "unknown helper kind" in r.output


class TestCreateCommands:
    def test_derivative_shorthand_duration(self, runner, fake_client):
        prime(fake_client, form(), created())
        r = _invoke(
            runner,
            "helpers", "create", "derivative",
            "--name", "Power", "--source", "sensor.energy",
            "--time-window", "5m", "--unit-time", "min", "--wait", "0",
        )
        assert r.exit_code == 0, r.output
        assert steps(fake_client)[0]["time_window"] == {"minutes": 5}
        assert steps(fake_client)[0]["unit_time"] == "min"
        assert json.loads(r.output)["entities"] == ["sensor.new"]

    def test_derivative_hhmmss_duration(self, runner, fake_client):
        prime(fake_client, form(), created())
        _invoke(
            runner, "helpers", "create", "derivative",
            "--name", "P", "--source", "sensor.e", "--time-window", "00:02:30", "--wait", "0",
        )
        assert steps(fake_client)[0]["time_window"] == {"hours": 0, "minutes": 2, "seconds": 30}

    def test_bad_duration_is_rejected_by_click(self, runner, fake_client):
        r = _invoke(
            runner, "helpers", "create", "derivative",
            "--name", "P", "--source", "sensor.e", "--time-window", "next tuesday",
        )
        assert r.exit_code != 0
        assert "--time-window" in r.output

    def test_riemann_targets_the_integration_domain(self, runner, fake_client):
        prime(fake_client, form(), created())
        r = _invoke(
            runner, "helpers", "create", "riemann",
            "--name", "Wh", "--source", "sensor.p", "--unit-prefix", "k", "--wait", "0",
        )
        assert r.exit_code == 0, r.output
        assert fake_client.calls[0]["payload"] == {"handler": "integration"}

    def test_utility_meter_repeatable_tariffs(self, runner, fake_client):
        prime(fake_client, form(), created())
        r = _invoke(
            runner, "helpers", "create", "utility-meter",
            "--name", "Daily", "--source", "sensor.e", "--cycle", "daily",
            "--tariff", "peak", "--tariff", "offpeak", "--wait", "0",
        )
        assert r.exit_code == 0, r.output
        assert steps(fake_client)[0]["tariffs"] == ["peak", "offpeak"]

    def test_utility_meter_rejects_an_unknown_cycle(self, runner, fake_client):
        r = _invoke(
            runner, "helpers", "create", "utility-meter",
            "--name", "n", "--source", "sensor.e", "--cycle", "fortnightly",
        )
        assert r.exit_code != 0

    def test_min_max_repeatable_entities(self, runner, fake_client):
        prime(fake_client, form(), created())
        _invoke(
            runner, "helpers", "create", "min-max",
            "--name", "avg", "--entity", "sensor.a", "--entity", "sensor.b",
            "--type", "median", "--wait", "0",
        )
        assert steps(fake_client)[0]["entity_ids"] == ["sensor.a", "sensor.b"]
        assert steps(fake_client)[0]["type"] == "median"

    def test_threshold_requires_a_bound(self, runner, fake_client):
        prime(fake_client, form(), created())
        r = _invoke(
            runner, "helpers", "create", "threshold",
            "--name", "hot", "--entity-id", "sensor.t", "--wait", "0",
        )
        assert r.exit_code != 0
        assert "lower/upper" in r.output

    def test_trend_tuning_triggers_the_options_flow(self, runner, fake_client):
        prime(fake_client, form(), form("settings"), created())
        fake_client.set("POST", "config/config_entries/options/flow", {"flow_id": "O1"})
        fake_client.set(
            "POST", "config/config_entries/options/flow/O1", {"type": "create_entry"}
        )
        r = _invoke(
            runner, "helpers", "create", "trend",
            "--name", "rising", "--entity-id", "sensor.t",
            "--max-samples", "5", "--sample-duration", "300", "--wait", "0",
        )
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["options_applied"] is True

    def test_statistics_max_age_shorthand(self, runner, fake_client):
        prime(fake_client, form(), form("state_characteristic"), form("options"), created())
        _invoke(
            runner, "helpers", "create", "statistics",
            "--name", "s", "--entity-id", "sensor.t", "--characteristic", "median",
            "--max-age", "24h", "--wait", "0",
        )
        assert steps(fake_client)[2]["max_age"] == {"hours": 24}

    def test_history_stats_states_are_a_list(self, runner, fake_client):
        prime(fake_client, form(), form("options"), created())
        _invoke(
            runner, "helpers", "create", "history-stats",
            "--name", "up", "--entity-id", "binary_sensor.b", "--state", "on",
            "--start", "{{ today_at() }}", "--duration", "24h", "--wait", "0",
        )
        assert steps(fake_client)[0]["state"] == ["on"]
        assert steps(fake_client)[1]["duration"] == {"hours": 24}

    def test_random_menu_choice(self, runner, fake_client):
        prime(fake_client, menu(["sensor", "binary_sensor"]), form("sensor"), created())
        _invoke(
            runner, "helpers", "create", "random",
            "--name", "dice", "--minimum", "1", "--maximum", "6", "--wait", "0",
        )
        assert steps(fake_client)[0] == {"next_step_id": "sensor"}

    def test_template_extra_fields_via_set(self, runner, fake_client):
        prime(fake_client, menu(["number"]), form("number"), created())
        _invoke(
            runner, "helpers", "create", "template",
            "--name", "dial", "--variant", "number", "--state", "{{ 5 }}",
            "--set", "min=0", "--set", "max=10", "--wait", "0",
        )
        assert steps(fake_client)[1]["min"] == 0
        assert steps(fake_client)[1]["max"] == 10

    def test_group_all_flag_on_the_wrong_variant(self, runner, fake_client):
        prime(fake_client, menu(["light"]), form("light"), created())
        r = _invoke(
            runner, "helpers", "create", "group",
            "--name", "g", "--entity", "light.a", "--variant", "light", "--all", "--wait", "0",
        )
        assert r.exit_code != 0
        assert "binary_sensor" in r.output

    def test_group_light(self, runner, fake_client):
        prime(fake_client, menu(["light"]), form("light"), created())
        r = _invoke(
            runner, "helpers", "create", "group",
            "--name", "Kitchen", "--entity", "light.a", "--entity", "light.b", "--wait", "0",
        )
        assert r.exit_code == 0, r.output
        assert steps(fake_client)[1]["entities"] == ["light.a", "light.b"]

    def test_generic_thermostat_presets_get_the_temp_suffix(self, runner, fake_client):
        prime(fake_client, form(), form("presets"), created())
        _invoke(
            runner, "helpers", "create", "generic-thermostat",
            "--name", "t", "--heater", "switch.h", "--target-sensor", "sensor.t",
            "--preset", "away=16", "--preset", "comfort_temp=21", "--wait", "0",
        )
        assert steps(fake_client)[1] == {"away_temp": 16, "comfort_temp": 21}

    def test_generic_hygrostat(self, runner, fake_client):
        prime(fake_client, form(), created())
        r = _invoke(
            runner, "helpers", "create", "generic-hygrostat",
            "--name", "h", "--humidifier", "switch.h", "--target-sensor", "sensor.hum",
            "--min-cycle-duration", "5m", "--wait", "0",
        )
        assert r.exit_code == 0, r.output
        assert steps(fake_client)[0]["min_cycle_duration"] == {"minutes": 5}

    def test_switch_as_x_has_no_name_option(self, runner, fake_client):
        r = _invoke(
            runner, "helpers", "create", "switch-as-x",
            "--entity-id", "switch.a", "--target-domain", "light", "--name", "nope",
        )
        assert r.exit_code != 0
        assert "no such option" in r.output.lower()

    def test_switch_as_x(self, runner, fake_client):
        prime(fake_client, form(), created())
        r = _invoke(
            runner, "helpers", "create", "switch-as-x",
            "--entity-id", "switch.a", "--target-domain", "light", "--wait", "0",
        )
        assert r.exit_code == 0, r.output
        assert steps(fake_client)[0] == {
            "entity_id": "switch.a",
            "target_domain": "light",
            "invert": False,
        }

    def test_tod(self, runner, fake_client):
        prime(fake_client, form(), created())
        _invoke(
            runner, "helpers", "create", "tod",
            "--name", "day", "--after", "08:00:00", "--before", "22:00:00", "--wait", "0",
        )
        assert steps(fake_client)[0]["after_time"] == "08:00:00"

    def test_mold_indicator(self, runner, fake_client):
        prime(fake_client, form(), created())
        r = _invoke(
            runner, "helpers", "create", "mold-indicator",
            "--name", "m", "--indoor-temp-sensor", "sensor.it",
            "--indoor-humidity-sensor", "sensor.ih", "--outdoor-temp-sensor", "sensor.ot",
            "--calibration-factor", "2.5", "--wait", "0",
        )
        assert r.exit_code == 0, r.output
        assert steps(fake_client)[0]["calibration_factor"] == 2.5

    def test_raw_steps(self, runner, fake_client):
        prime(fake_client, menu(["sensor"]), form("sensor"), created())
        r = _invoke(
            runner, "helpers", "create", "raw",
            "--domain", "filter",
            "--step", '{"next_step_id": "sensor"}',
            "--step", '{"name": "smooth"}',
            "--wait", "0",
        )
        assert r.exit_code == 0, r.output
        assert fake_client.calls[0]["payload"] == {"handler": "filter"}

    def test_raw_rejects_non_json(self, runner, fake_client):
        r = _invoke(runner, "helpers", "create", "raw", "--domain", "x", "--step", "name=foo")
        assert r.exit_code != 0
        assert "valid JSON" in r.output

    def test_no_resolve_skips_the_registry_read(self, runner, fake_client):
        prime(fake_client, form(), created())
        r = _invoke(
            runner, "helpers", "create", "tod",
            "--name", "d", "--after", "01:00:00", "--before", "02:00:00", "--no-resolve",
        )
        assert r.exit_code == 0, r.output
        assert "entities" not in json.loads(r.output)
        assert fake_client.ws_calls == []


class TestLifecycleCli:
    def test_entries(self, runner, fake_client):
        fake_client.set_ws(
            "config_entries/get", [{"entry_id": "E1", "domain": "tod", "title": "Day"}]
        )
        r = _invoke(runner, "helpers", "entries", "--domain", "tod")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["entry_id"] == "E1"

    def test_show_includes_entities(self, runner, fake_client):
        fake_client.set_ws("config_entries/get", [{"entry_id": "E1", "domain": "tod"}])
        fake_client.set_ws(
            "config/entity_registry/list",
            [{"entity_id": "binary_sensor.day", "config_entry_id": "E1"}],
        )
        r = _invoke(runner, "helpers", "show", "E1")
        assert json.loads(r.output)["entities"] == ["binary_sensor.day"]

    def test_show_missing_entry(self, runner, fake_client):
        fake_client.set_ws("config_entries/get", [])
        r = _invoke(runner, "helpers", "show", "nope")
        assert r.exit_code != 0
        assert "no helper config entry" in r.output

    def test_entities_command(self, runner, fake_client):
        fake_client.set_ws(
            "config/entity_registry/list",
            [{"entity_id": "sensor.x", "config_entry_id": "E1"}],
        )
        r = _invoke(runner, "helpers", "entities", "E1")
        assert json.loads(r.output) == {"entry_id": "E1", "entities": ["sensor.x"]}

    def test_set_options(self, runner, fake_client):
        fake_client.set("POST", "config/config_entries/options/flow", {"flow_id": "O1"})
        fake_client.set(
            "POST", "config/config_entries/options/flow/O1", {"type": "create_entry"}
        )
        r = _invoke(
            runner, "helpers", "set-options", "E1", "--set", "target_humidity=55"
        )
        assert r.exit_code == 0, r.output
        assert fake_client.calls[1]["payload"] == {"target_humidity": 55}

    def test_set_options_needs_input(self, runner, fake_client):
        r = _invoke(runner, "helpers", "set-options", "E1")
        assert r.exit_code != 0

    def test_delete_requires_confirmation(self, runner, fake_client):
        r = _invoke(runner, "helpers", "delete", "E1")
        assert r.exit_code == 0
        assert "aborted" in r.output
        assert fake_client.calls == []

    def test_delete_with_yes(self, runner, fake_client):
        fake_client.set("DELETE", "config/config_entries/entry/E1", {"require_restart": False})
        r = _invoke(runner, "helpers", "delete", "E1", "--yes")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["deleted"] == "E1"
        assert fake_client.calls[-1]["verb"] == "DELETE"
