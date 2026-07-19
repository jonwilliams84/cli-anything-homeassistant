"""CLI wiring tests for the new groups added in the refine pass:
scene, weather, shopping-list, todo, lock, alarm, search, entity expose.

These tests use Click's CliRunner with a FakeClient injected via
homeassistant_cli.make_client, so they exercise the real Click decorators
and option parsing without booting Home Assistant.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from cli_anything.homeassistant import homeassistant_cli as cli_mod


@pytest.fixture
def runner(monkeypatch, fake_client):
    """CliRunner that swaps make_client for a FakeClient."""
    monkeypatch.setattr(cli_mod, "make_client", lambda ctx: fake_client)
    return CliRunner()


def _invoke(runner, *args, json_out=True):
    full = ["--json"] + list(args) if json_out else list(args)
    return runner.invoke(cli_mod.cli, full, obj={
        "url": "http://x", "token": "t", "verify_ssl": False,
        "timeout": 5, "as_json": json_out, "config_path": None,
    })


# ──────────────────────────────────────────────────────────────────── scene

class TestSceneCli:
    def test_list(self, runner, fake_client):
        fake_client.set("GET", "states", [
            {"entity_id": "scene.morning"}, {"entity_id": "light.x"},
        ])
        r = _invoke(runner, "scene", "list")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert len(data) == 1
        assert data[0]["entity_id"] == "scene.morning"

    def test_activate(self, runner, fake_client):
        r = _invoke(runner, "scene", "activate", "scene.morning")
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["path"] == "services/scene/turn_on"
        assert fake_client.calls[-1]["payload"] == {"entity_id": "scene.morning"}

    def test_activate_with_transition(self, runner, fake_client):
        r = _invoke(runner, "scene", "activate", "scene.morning",
                    "--transition", "2.5")
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["payload"]["transition"] == 2.5

    def test_apply(self, runner, fake_client):
        r = _invoke(runner, "scene", "apply",
                    "--entity", "light.kitchen=on")
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["path"] == "services/scene/apply"
        assert fake_client.calls[-1]["payload"]["entities"] == {
            "light.kitchen": "on",
        }

    def test_apply_with_json_value(self, runner, fake_client):
        r = _invoke(runner, "scene", "apply",
                    "--entity", 'light.lamp={"state":"on","brightness":120}')
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["payload"]["entities"] == {
            "light.lamp": {"state": "on", "brightness": 120},
        }

    def test_create_with_snapshot(self, runner, fake_client):
        r = _invoke(runner, "scene", "create", "movie",
                    "--snapshot", "light.a",
                    "--snapshot", "light.b")
        assert r.exit_code == 0, r.output
        payload = fake_client.calls[-1]["payload"]
        assert payload["scene_id"] == "movie"
        assert payload["snapshot_entities"] == ["light.a", "light.b"]

    def test_create_requires_at_least_one_source(self, runner, fake_client):
        r = _invoke(runner, "scene", "create", "empty")
        assert r.exit_code != 0
        assert "--entity" in r.output

    def test_reload(self, runner, fake_client):
        r = _invoke(runner, "scene", "reload")
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["path"] == "services/scene/reload"


# ──────────────────────────────────────────────────────────────────── service call

class TestServiceCallCli:
    """`service call` result handling — particularly the empty-result
    fallback. HA's REST response for many stateless service calls (e.g.
    rest_command/shell_command — anything that changes no entity state) is
    literally `[]`. Plain mode must not silently print nothing on success,
    since that's indistinguishable from a hang or a swallowed error.
    """

    def test_empty_list_result_prints_fallback_in_plain_mode(self, runner, fake_client):
        fake_client.set_service("rest_command", "foo", [])
        r = _invoke(runner, "service", "call", "rest_command", "foo",
                    json_out=False)
        assert r.exit_code == 0, r.output
        assert r.output.strip() != ""
        assert "rest_command.foo" in r.output

    def test_empty_list_result_prints_fallback_in_json_mode(self, runner, fake_client):
        fake_client.set_service("rest_command", "foo", [])
        r = _invoke(runner, "service", "call", "rest_command", "foo",
                    json_out=True)
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data == {"called": "rest_command.foo"}

    def test_meaningful_result_passes_through(self, runner, fake_client):
        fake_client.set_service("light", "turn_on",
                                 [{"entity_id": "light.kitchen", "state": "on"}])
        r = _invoke(runner, "service", "call", "light", "turn_on",
                    "-T", "entity_id=light.kitchen", json_out=True)
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data == [{"entity_id": "light.kitchen", "state": "on"}]


# ──────────────────────────────────────────────────────────────────── weather

class TestWeatherCli:
    def test_list_filters_to_weather_domain(self, runner, fake_client):
        fake_client.set("GET", "states", [
            {"entity_id": "weather.home"},
            {"entity_id": "sensor.outdoor_temp"},
            {"entity_id": "weather.office"},
        ])
        r = _invoke(runner, "weather", "list")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert {x["entity_id"] for x in data} == {"weather.home", "weather.office"}

    def test_units(self, runner, fake_client):
        fake_client.set_ws("weather/convertible_units",
                           {"units": {"temperature": ["°C", "°F"]}})
        r = _invoke(runner, "weather", "units")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["temperature"] == ["°C", "°F"]

    def test_forecast_subscribe(self, runner, fake_client):
        fake_client.set_ws("weather/subscribe_forecast", {"subscription": 1})
        r = _invoke(runner, "weather", "forecast-subscribe", "weather.home",
                    "--type", "hourly")
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert last["type"] == "weather/subscribe_forecast"
        assert last["payload"] == {
            "entity_id": "weather.home", "forecast_type": "hourly",
        }


# ──────────────────────────────────────────────────────────────────── shopping-list

class TestShoppingListCli:
    def test_list(self, runner, fake_client):
        fake_client.set_ws("shopping_list/items",
                           [{"id": "a", "name": "Milk", "complete": False}])
        r = _invoke(runner, "shopping-list", "list")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data[0]["name"] == "Milk"

    def test_add(self, runner, fake_client):
        fake_client.set_ws("shopping_list/items/add",
                           {"id": "n", "name": "Bread", "complete": False})
        r = _invoke(runner, "shopping-list", "add", "Bread")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {"name": "Bread"}

    def test_update_needs_at_least_one_flag(self, runner, fake_client):
        r = _invoke(runner, "shopping-list", "update", "abc123")
        assert r.exit_code != 0
        assert "--name" in r.output

    def test_update_complete(self, runner, fake_client):
        fake_client.set_ws("shopping_list/items/update",
                           {"id": "abc", "complete": True})
        r = _invoke(runner, "shopping-list", "update", "abc", "--complete")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {
            "item_id": "abc", "complete": True,
        }

    def test_clear_completed(self, runner, fake_client):
        fake_client.set_ws("shopping_list/items/clear", {"ok": True})
        r = _invoke(runner, "shopping-list", "clear-completed", "--yes")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["type"] == "shopping_list/items/clear"

    def test_reorder(self, runner, fake_client):
        fake_client.set_ws("shopping_list/items/reorder", {"ok": True})
        r = _invoke(runner, "shopping-list", "reorder", "a", "b", "c")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {
            "item_ids": ["a", "b", "c"],
        }


# ──────────────────────────────────────────────────────────────────── todo

class TestTodoCli:
    def test_list(self, runner, fake_client):
        fake_client.set_ws("todo/item/list",
                           {"items": [{"uid": "u1", "summary": "Buy milk",
                                       "status": "needs_action"}]})
        r = _invoke(runner, "todo", "list", "todo.groceries")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data[0]["summary"] == "Buy milk"

    def test_add(self, runner, fake_client):
        r = _invoke(runner, "todo", "add", "todo.groceries", "Bread",
                    "--due", "2026-06-01")
        assert r.exit_code == 0, r.output
        payload = fake_client.calls[-1]["payload"]
        assert payload["entity_id"] == "todo.groceries"
        assert payload["item"] == "Bread"
        assert payload["due"] == "2026-06-01"

    def test_complete(self, runner, fake_client):
        r = _invoke(runner, "todo", "complete", "todo.groceries", "Bread")
        assert r.exit_code == 0, r.output
        payload = fake_client.calls[-1]["payload"]
        assert payload["status"] == "completed"
        assert payload["item"] == "Bread"

    def test_remove_single(self, runner, fake_client):
        r = _invoke(runner, "todo", "remove", "todo.groceries", "Bread", "--yes")
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["payload"]["item"] == "Bread"

    def test_remove_multi(self, runner, fake_client):
        r = _invoke(runner, "todo", "remove", "todo.groceries", "Bread", "Milk", "--yes")
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["payload"]["item"] == ["Bread", "Milk"]

    def test_move(self, runner, fake_client):
        fake_client.set_ws("todo/item/move", {"ok": True})
        r = _invoke(runner, "todo", "move", "todo.groceries", "u-target",
                    "--after", "u-prev")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {
            "entity_id": "todo.groceries",
            "uid": "u-target",
            "previous_uid": "u-prev",
        }


# ──────────────────────────────────────────────────────────────────── lock

class TestLockCli:
    def test_lock(self, runner, fake_client):
        r = _invoke(runner, "lock", "lock", "lock.front")
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["path"] == "services/lock/lock"

    def test_unlock_with_code(self, runner, fake_client):
        r = _invoke(runner, "lock", "unlock", "lock.front", "--code", "1234")
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["payload"] == {
            "entity_id": "lock.front", "code": "1234",
        }

    def test_open(self, runner, fake_client):
        r = _invoke(runner, "lock", "open", "lock.garage")
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["path"] == "services/lock/open"

    def test_wrong_domain_errors(self, runner, fake_client):
        # HomeAssistantError isn't raised here because fake_client doesn't
        # validate — but the core function does (ValueError → non-zero exit).
        r = _invoke(runner, "lock", "lock", "light.kitchen")
        assert r.exit_code != 0


# ──────────────────────────────────────────────────────────────────── alarm

class TestAlarmCli:
    @pytest.mark.parametrize("subcmd,svc", [
        ("arm-away", "alarm_arm_away"),
        ("arm-home", "alarm_arm_home"),
        ("arm-night", "alarm_arm_night"),
        ("arm-vacation", "alarm_arm_vacation"),
        ("disarm", "alarm_disarm"),
    ])
    def test_each_mode(self, runner, fake_client, subcmd, svc):
        r = _invoke(runner, "alarm", subcmd, "alarm_control_panel.home")
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["path"] == f"services/alarm_control_panel/{svc}"
        assert fake_client.calls[-1]["payload"] == {
            "entity_id": "alarm_control_panel.home",
        }

    def test_with_code(self, runner, fake_client):
        r = _invoke(runner, "alarm", "disarm",
                    "alarm_control_panel.home", "--code", "9999")
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["payload"] == {
            "entity_id": "alarm_control_panel.home", "code": "9999",
        }


# ──────────────────────────────────────────────────────────────────── search

class TestSearchCli:
    def test_search_entity(self, runner, fake_client):
        fake_client.set_ws("search/related", {"automation": ["a.1"]})
        r = _invoke(runner, "search", "entity", "light.kitchen")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["type"] == "search/related"
        assert fake_client.ws_calls[-1]["payload"] == {
            "item_type": "entity", "item_id": "light.kitchen",
        }

    def test_invalid_item_type(self, runner, fake_client):
        r = _invoke(runner, "search", "bogus_type", "x")
        assert r.exit_code != 0


# ──────────────────────────────────────────────────────────────────── entity expose

class TestEntityExposeCli:
    def test_list(self, runner, fake_client):
        fake_client.set_ws("homeassistant/expose_entity/list",
                           {"exposed_entities": {
                               "light.kitchen": {"cloud.alexa": True},
                           }})
        r = _invoke(runner, "entity", "expose", "list")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["light.kitchen"] == {"cloud.alexa": True}

    def test_list_filter_assistant(self, runner, fake_client):
        fake_client.set_ws("homeassistant/expose_entity/list",
                           {"exposed_entities": {
                               "light.kitchen": {
                                   "cloud.alexa": True,
                                   "cloud.google_assistant": False,
                               },
                           }})
        r = _invoke(runner, "entity", "expose", "list",
                    "--assistant", "cloud.alexa")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data == {"light.kitchen": {"cloud.alexa": True}}

    def test_set_expose(self, runner, fake_client):
        fake_client.set_ws("homeassistant/expose_entity", {"ok": True})
        r = _invoke(runner, "entity", "expose", "set",
                    "--assistant", "cloud.alexa",
                    "--entity", "light.kitchen",
                    "--entity", "light.lamp")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {
            "assistants": ["cloud.alexa"],
            "entity_ids": ["light.kitchen", "light.lamp"],
            "should_expose": True,
        }

    def test_set_hide(self, runner, fake_client):
        fake_client.set_ws("homeassistant/expose_entity", {"ok": True})
        r = _invoke(runner, "entity", "expose", "set",
                    "--assistant", "cloud.alexa",
                    "--entity", "light.kitchen",
                    "--hide")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"]["should_expose"] is False

    def test_new_default_get(self, runner, fake_client):
        fake_client.set_ws("homeassistant/expose_new_entities/get",
                           {"expose_new": True})
        r = _invoke(runner, "entity", "expose", "new-default-get", "cloud.alexa")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["expose_new"] is True
        assert data["assistant"] == "cloud.alexa"

    def test_new_default_set(self, runner, fake_client):
        fake_client.set_ws("homeassistant/expose_new_entities/set", {"ok": True})
        r = _invoke(runner, "entity", "expose", "new-default-set",
                    "cloud.alexa", "--no-expose")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {
            "assistant": "cloud.alexa", "expose_new": False,
        }
