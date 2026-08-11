"""CLI wiring tests for the frontend/template-ws refine pass.

Covers `template-ws` (render / listeners / uses / validate / watch),
`panel`, the `frontend version|translations|icons` additions,
`system integrations`, `entity convertible-units|numeric-device-classes`
and `state-stream entities|snapshot`.
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
def sub_runner(monkeypatch, subscribing_client):
    monkeypatch.setattr(cli_mod, "make_client", lambda ctx: subscribing_client)
    return CliRunner()


def _invoke(runner, *args, json_out=True):
    full = ["--json"] + list(args) if json_out else list(args)
    return runner.invoke(
        cli_mod.cli,
        full,
        obj={
            "url": "http://x", "token": "t", "verify_ssl": False,
            "timeout": 5, "as_json": json_out, "config_path": None,
        },
    )


LISTENERS = {"all": False, "entities": ["light.kitchen"], "domains": ["light"], "time": False}

PANELS = {
    "lovelace": {"component_name": "lovelace", "title": "Overview", "url_path": "lovelace"},
    "energy": {"component_name": "energy", "title": "Energy", "url_path": "energy"},
}

CATALOG = {
    "core": {
        "integration": {"hue": {"name": "Hue", "config_flow": True, "iot_class": "local_push"}},
        "helper": {},
    },
    "custom": {"integration": {"hacs": {"name": "HACS", "config_flow": True}}, "helper": {}},
}


def _arm_sensor(fake_client, *, device_class="temperature", units=("°C", "°F"), options=None):
    """Wire up the reads `entity set-display` performs before it writes."""
    fake_client.set("GET", "states/sensor.t", {
        "entity_id": "sensor.t",
        "state": "21.0",
        "attributes": {"device_class": device_class} if device_class else {},
    })
    fake_client.set_ws("sensor/device_class_convertible_units", {"units": list(units)})
    fake_client.set_ws(
        "config/entity_registry/get",
        {"entity_entry": {"entity_id": "sensor.t", "options": options or {}}},
    )
    fake_client.set_ws("config/entity_registry/update", {"entity_entry": {"entity_id": "sensor.t"}})
    return fake_client



# ─────────────────────────────────────────────────────────────── template-ws

class TestTemplateWs:
    def test_render_inline(self, sub_runner, subscribing_client):
        subscribing_client.queue_events({"result": 3, "listeners": LISTENERS})
        r = _invoke(sub_runner, "template-ws", "render", "{{ 1 + 2 }}")
        assert r.exit_code == 0, r.output
        out = json.loads(r.output)
        assert out["result"] == 3
        assert out["listeners"]["entities"] == ["light.kitchen"]
        assert subscribing_client.subscribe_calls[-1][0] == "render_template"

    def test_render_value_only_keeps_type(self, sub_runner, subscribing_client):
        subscribing_client.queue_events({"result": 2, "listeners": LISTENERS})
        r = _invoke(sub_runner, "template-ws", "render", "{{ 1 + 1 }}", "--value-only")
        assert json.loads(r.output) == 2

    def test_render_from_file_with_vars(self, sub_runner, subscribing_client, tmp_path):
        subscribing_client.queue_events({"result": "ok", "listeners": LISTENERS})
        path = tmp_path / "t.j2"
        path.write_text("{{ room }}")
        r = _invoke(sub_runner, "template-ws", "render", "--file", str(path), "-V", "room=kitchen")
        assert r.exit_code == 0, r.output
        payload = subscribing_client.subscribe_calls[-1][1]
        assert payload["template"] == "{{ room }}"
        assert payload["variables"] == {"room": "kitchen"}

    def test_render_strict_flag(self, sub_runner, subscribing_client):
        subscribing_client.queue_events({"result": 1, "listeners": LISTENERS})
        _invoke(sub_runner, "template-ws", "render", "{{ 1 }}", "--strict")
        assert subscribing_client.subscribe_calls[-1][1]["strict"] is True

    def test_render_template_error_exits_nonzero(self, sub_runner, subscribing_client):
        subscribing_client.queue_events({"error": "boom", "level": "ERROR"})
        r = _invoke(sub_runner, "template-ws", "render", "{{ nope() }}")
        assert r.exit_code != 0

    def test_listeners(self, sub_runner, subscribing_client):
        subscribing_client.queue_events({"result": 1, "listeners": LISTENERS})
        r = _invoke(sub_runner, "template-ws", "listeners", "{{ 1 }}")
        assert json.loads(r.output)["domains"] == ["light"]

    def test_listeners_entities_only(self, sub_runner, subscribing_client):
        subscribing_client.queue_events({"result": 1, "listeners": LISTENERS})
        r = _invoke(sub_runner, "template-ws", "listeners", "{{ 1 }}", "--entities-only")
        assert json.loads(r.output) == ["light.kitchen"]

    def test_uses_true(self, sub_runner, subscribing_client):
        subscribing_client.queue_events({"result": 1, "listeners": LISTENERS})
        r = _invoke(sub_runner, "template-ws", "uses", "light.kitchen", "{{ 1 }}")
        assert json.loads(r.output)["depends_on"] is True

    def test_uses_exit_code_when_absent(self, sub_runner, subscribing_client):
        subscribing_client.queue_events({"result": 1, "listeners": LISTENERS})
        r = _invoke(
            sub_runner, "template-ws", "uses", "sensor.temp", "{{ 1 }}", "--exit-code"
        )
        assert r.exit_code == 1

    def test_validate_ok(self, sub_runner, subscribing_client):
        subscribing_client.queue_events({"result": "x", "listeners": LISTENERS})
        r = _invoke(sub_runner, "template-ws", "validate", "{{ 1 }}")
        assert r.exit_code == 0
        assert json.loads(r.output)["valid"] is True

    def test_validate_bad_template_exits_nonzero(self, sub_runner, subscribing_client):
        subscribing_client.queue_events({"error": "bad filter", "level": "ERROR"})
        r = _invoke(sub_runner, "template-ws", "validate", "{{ x | nope }}")
        assert r.exit_code != 0
        assert "bad filter" in r.output

    def test_watch_streams_and_stops(self, sub_runner, subscribing_client):
        subscribing_client.queue_events({"result": 1}, {"result": 2})
        r = _invoke(sub_runner, "template-ws", "watch", "{{ 1 }}", "--max-events", "2")
        assert r.exit_code == 0, r.output
        assert '"result": 1' in r.output


# ─────────────────────────────────────────────────────────────────── panel

class TestPanel:
    def test_list(self, runner, fake_client):
        fake_client.set_ws("get_panels", PANELS)
        r = _invoke(runner, "panel", "list")
        assert [p["url_path"] for p in json.loads(r.output)] == ["energy", "lovelace"]

    def test_list_filtered(self, runner, fake_client):
        fake_client.set_ws("get_panels", PANELS)
        r = _invoke(runner, "panel", "list", "-c", "lovelace")
        assert [p["url_path"] for p in json.loads(r.output)] == ["lovelace"]

    def test_list_url_paths_only(self, runner, fake_client):
        fake_client.set_ws("get_panels", PANELS)
        r = _invoke(runner, "panel", "list", "--url-paths-only")
        assert json.loads(r.output) == ["energy", "lovelace"]

    def test_get(self, runner, fake_client):
        fake_client.set_ws("get_panels", PANELS)
        r = _invoke(runner, "panel", "get", "energy")
        assert json.loads(r.output)["title"] == "Energy"

    def test_get_unknown_exits_nonzero(self, runner, fake_client):
        fake_client.set_ws("get_panels", PANELS)
        r = _invoke(runner, "panel", "get", "nope")
        assert r.exit_code != 0

    def test_dashboards(self, runner, fake_client):
        fake_client.set_ws("get_panels", PANELS)
        r = _invoke(runner, "panel", "dashboards")
        assert [p["url_path"] for p in json.loads(r.output)] == ["lovelace"]


# ──────────────────────────────────────────────────────────────── frontend

class TestFrontendMeta:
    def test_version(self, runner, fake_client):
        fake_client.set_ws("frontend/get_version", {"version": "20250109.0"})
        r = _invoke(runner, "frontend", "version")
        assert json.loads(r.output) == {"version": "20250109.0"}

    def test_translations(self, runner, fake_client):
        fake_client.set_ws("frontend/get_translations", {"resources": {"state": {}}})
        r = _invoke(runner, "frontend", "translations", "-c", "state", "-i", "person")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {
            "language": "en",
            "category": "state",
            "integration": ["person"],
        }

    def test_translations_language(self, runner, fake_client):
        fake_client.set_ws("frontend/get_translations", {"resources": {}})
        _invoke(runner, "frontend", "translations", "-l", "de")
        assert fake_client.ws_calls[-1]["payload"]["language"] == "de"

    def test_icons(self, runner, fake_client):
        fake_client.set_ws("frontend/get_icons", {"resources": {"light": {}}})
        r = _invoke(runner, "frontend", "icons", "-c", "entity_component")
        assert json.loads(r.output) == {"light": {}}

    def test_icons_rejects_bad_category(self, runner, fake_client):
        r = _invoke(runner, "frontend", "icons", "-c", "bogus")
        assert r.exit_code != 0


# ─────────────────────────────────────────────────────── system integrations

class TestSystemIntegrations:
    def test_list(self, runner, fake_client):
        fake_client.set_ws("integration/descriptions", CATALOG)
        r = _invoke(runner, "system", "integrations")
        assert [i["domain"] for i in json.loads(r.output)] == ["hacs", "hue"]

    def test_custom_only(self, runner, fake_client):
        fake_client.set_ws("integration/descriptions", CATALOG)
        r = _invoke(runner, "system", "integrations", "--source", "custom", "--domains-only")
        assert json.loads(r.output) == ["hacs"]

    def test_single_domain(self, runner, fake_client):
        fake_client.set_ws("integration/descriptions", CATALOG)
        r = _invoke(runner, "system", "integrations", "--domain", "hue")
        assert json.loads(r.output)["name"] == "Hue"

    def test_unknown_domain_exits_nonzero(self, runner, fake_client):
        fake_client.set_ws("integration/descriptions", CATALOG)
        r = _invoke(runner, "system", "integrations", "--domain", "zwave_js")
        assert r.exit_code != 0


# ──────────────────────────────────────────────────────────── entity units

class TestEntityUnits:
    def test_convertible_units(self, runner, fake_client):
        fake_client.set_ws("sensor/device_class_convertible_units", {"units": ["°C", "°F"]})
        r = _invoke(runner, "entity", "convertible-units", "--device-class", "temperature")
        assert json.loads(r.output) == ["°C", "°F"]

    def test_number_domain(self, runner, fake_client):
        fake_client.set_ws("number/device_class_convertible_units", {"units": ["°C"]})
        r = _invoke(
            runner, "entity", "convertible-units",
            "--device-class", "temperature", "--domain", "number",
        )
        assert json.loads(r.output) == ["°C"]

    def test_unit_check_true(self, runner, fake_client):
        fake_client.set_ws("sensor/device_class_convertible_units", {"units": ["°C", "°F"]})
        r = _invoke(
            runner, "entity", "convertible-units",
            "--device-class", "temperature", "--unit", "°F",
        )
        assert json.loads(r.output)["convertible"] is True

    def test_unit_check_exit_code(self, runner, fake_client):
        fake_client.set_ws("sensor/device_class_convertible_units", {"units": ["°C"]})
        r = _invoke(
            runner, "entity", "convertible-units",
            "--device-class", "temperature", "--unit", "kWh", "--exit-code",
        )
        assert r.exit_code == 1

    def test_numeric_device_classes(self, runner, fake_client):
        fake_client.set_ws(
            "sensor/numeric_device_classes", {"numeric_device_classes": ["power", "battery"]}
        )
        r = _invoke(runner, "entity", "numeric-device-classes")
        assert json.loads(r.output) == ["battery", "power"]

    def test_convertible_units_by_entity(self, runner, fake_client):
        _arm_sensor(fake_client)
        r = _invoke(runner, "entity", "convertible-units", "--entity", "sensor.t")
        out = json.loads(r.output)
        assert out["device_class"] == "temperature"
        assert out["units"] == ["°C", "°F"]

    def test_convertible_units_requires_one_selector(self, runner, fake_client):
        r = _invoke(runner, "entity", "convertible-units")
        assert r.exit_code != 0

    def test_display_options_read(self, runner, fake_client):
        _arm_sensor(fake_client, options={"sensor": {"display_precision": 2}})
        r = _invoke(runner, "entity", "display-options", "sensor.t")
        assert json.loads(r.output) == {"display_precision": 2}

    def test_set_display_merges(self, runner, fake_client):
        _arm_sensor(fake_client, options={"sensor": {"display_precision": 2}})
        r = _invoke(runner, "entity", "set-display", "sensor.t", "--unit", "°F")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["options"] == {
            "display_precision": 2,
            "unit_of_measurement": "°F",
        }

    def test_set_display_replace(self, runner, fake_client):
        _arm_sensor(fake_client, options={"sensor": {"display_precision": 2}})
        r = _invoke(runner, "entity", "set-display", "sensor.t", "--unit", "°F", "--replace")
        assert json.loads(r.output)["options"] == {"unit_of_measurement": "°F"}

    def test_set_display_rejects_bad_unit(self, runner, fake_client):
        _arm_sensor(fake_client, units=("°C",))
        r = _invoke(runner, "entity", "set-display", "sensor.t", "--unit", "kWh")
        assert r.exit_code != 0

    def test_set_display_no_validate(self, runner, fake_client):
        _arm_sensor(fake_client, units=("°C",))
        r = _invoke(
            runner, "entity", "set-display", "sensor.t", "--unit", "kWh", "--no-validate"
        )
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["options"] == {"unit_of_measurement": "kWh"}

    def test_set_display_precision_only(self, runner, fake_client):
        _arm_sensor(fake_client)
        r = _invoke(runner, "entity", "set-display", "sensor.t", "--precision", "1")
        assert json.loads(r.output)["options"] == {"display_precision": 1}


# ───────────────────────────────────────────────────── state-stream entities

class TestStateStreamEntities:
    def test_entities_stream(self, sub_runner, subscribing_client):
        subscribing_client.queue_events({"a": {"light.kitchen": {"s": "on"}}})
        r = _invoke(sub_runner, "state-stream", "entities", "--max-events", "1")
        assert r.exit_code == 0, r.output
        assert subscribing_client.subscribe_calls[-1][0] == "subscribe_entities"

    def test_entities_filter(self, sub_runner, subscribing_client):
        subscribing_client.queue_events({"a": {}})
        _invoke(
            sub_runner, "state-stream", "entities",
            "--entity", "light.kitchen", "--max-events", "1",
        )
        assert subscribing_client.subscribe_calls[-1][1] == {"entity_ids": ["light.kitchen"]}

    def test_snapshot(self, sub_runner, subscribing_client):
        subscribing_client.queue_events({"a": {"light.kitchen": {"s": "on"}}})
        r = _invoke(sub_runner, "state-stream", "snapshot")
        assert json.loads(r.output)["light.kitchen"]["s"] == "on"

    def test_snapshot_ids_only(self, sub_runner, subscribing_client):
        subscribing_client.queue_events(
            {"a": {"light.kitchen": {"s": "on"}, "sensor.temp": {"s": "1"}}}
        )
        r = _invoke(sub_runner, "state-stream", "snapshot", "--ids-only")
        assert json.loads(r.output) == ["light.kitchen", "sensor.temp"]

    def test_snapshot_timeout_exits_nonzero(self, sub_runner, subscribing_client):
        r = _invoke(sub_runner, "state-stream", "snapshot", "--timeout-seconds", "0.2")
        assert r.exit_code != 0


# ────────────────────────────────────────────────────────────── workflows

class TestWorkflows:
    def test_dependency_then_watch_the_entity(self, sub_runner, subscribing_client):
        """`template-ws listeners` names the entity, `state-stream entities` watches it."""
        subscribing_client.queue_events({"result": 1, "listeners": LISTENERS})
        r = _invoke(sub_runner, "template-ws", "listeners", "{{ 1 }}", "--entities-only")
        entity_id = json.loads(r.output)[0]

        subscribing_client.queue_events({"a": {entity_id: {"s": "on"}}})
        r2 = _invoke(
            sub_runner, "state-stream", "entities", "--entity", entity_id, "--max-events", "1"
        )
        assert r2.exit_code == 0
        assert subscribing_client.subscribe_calls[-1][1] == {"entity_ids": [entity_id]}

    def test_convertible_units_gate_then_set_display(self, runner, fake_client):
        """Pre-flight the unit, then write it through `entity set-display`."""
        _arm_sensor(fake_client)
        r = _invoke(
            runner, "entity", "convertible-units",
            "--device-class", "temperature", "--unit", "°F",
        )
        assert json.loads(r.output)["convertible"] is True

        r2 = _invoke(runner, "entity", "set-display", "sensor.t", "--unit", "°F")
        assert r2.exit_code == 0, r2.output
        call = fake_client.ws_calls[-1]
        assert call["type"] == "config/entity_registry/update"
        assert call["payload"]["options_domain"] == "sensor"

    def test_panel_dashboards_match_lovelace_panels(self, runner, fake_client):
        fake_client.set_ws("get_panels", PANELS)
        listed = json.loads(_invoke(runner, "panel", "list", "-c", "lovelace").output)
        dash = json.loads(_invoke(runner, "panel", "dashboards").output)
        assert listed == dash
