"""Unit tests for `core/helper_integrations.py` — the config-flow helpers.

Every payload asserted here was measured against a real HA 2025.1.4 first
(see `tests/test_helper_integrations_e2e.py`, which drives the same flows
over a socket); these tests pin the shape so a regression is caught without
booting HA.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import helper_integrations as hi
from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

FLOW = "config/config_entries/flow"


def form(step_id, fields, flow_id="F1"):
    """A `type: form` descriptor shaped like HA's REST answer."""
    return {
        "type": "form",
        "flow_id": flow_id,
        "handler": "x",
        "step_id": step_id,
        "data_schema": fields,
    }


def field(name, *, required=False, options=None):
    out = {"name": name, "required": required}
    if options is not None:
        out["selector"] = {"select": {"options": options}}
    return out


def created(entry_id="E1", title="T"):
    return {
        "type": "create_entry",
        "flow_id": "F1",
        "title": title,
        "result": {"entry_id": entry_id, "title": title, "state": "loaded", "domain": "d"},
    }


def prime(client, *forms, entities=None):
    """Queue the init form + one answer per submitted step."""
    client.set_seq("POST", FLOW, forms[0])
    client.set_seq("POST", f"{FLOW}/F1", *forms[1:])
    client.set_ws(
        "config/entity_registry/list",
        entities if entities is not None else [{"entity_id": "sensor.new", "config_entry_id": "E1"}],
    )


def submitted(client):
    """Every user_input POSTed to a flow step, in order."""
    return [
        c["payload"]
        for c in client.calls
        if c["verb"] == "POST" and c["path"].startswith(f"{FLOW}/")
    ]


class TestKindRegistry:
    def test_every_kind_has_a_domain_and_summary(self):
        kinds = hi.list_kinds()
        assert len(kinds) == 16
        for k in kinds:
            assert k["domain"] and k["summary"] and k["steps"]

    def test_riemann_is_has_domain_integration(self):
        assert hi.kind_domain("riemann") == "integration"

    def test_describe_unknown_kind_names_the_alternatives(self):
        with pytest.raises(ValueError, match="derivative"):
            hi.describe_kind("nope")


class TestWalkFlow:
    def test_single_step_posts_init_then_step(self, fake_client):
        prime(fake_client, form("user", [field("name", required=True)]), created())
        out = hi.walk_flow(fake_client, "tod", [{"name": "x"}])
        assert out["type"] == "create_entry"
        assert fake_client.calls[0] == {
            "verb": "POST",
            "path": FLOW,
            "payload": {"handler": "tod"},
        }
        assert fake_client.calls[1]["path"] == f"{FLOW}/F1"

    def test_menu_step_requires_a_known_next_step_id(self, fake_client):
        fake_client.set_seq(
            "POST", FLOW,
            {"type": "menu", "flow_id": "F1", "menu_options": ["sensor", "binary_sensor"]},
        )
        with pytest.raises(ValueError, match="menu flow"):
            hi.walk_flow(fake_client, "random", [{"next_step_id": "climate"}])
        # the flow it opened is aborted, not left dangling
        assert {"verb": "DELETE", "path": f"{FLOW}/F1"} in fake_client.calls

    def test_unknown_field_is_named_before_the_request(self, fake_client):
        prime(fake_client, form("user", [field("entity_id", required=True)]), created())
        with pytest.raises(ValueError, match="no field\\(s\\) name"):
            hi.walk_flow(fake_client, "switch_as_x", [{"entity_id": "switch.a", "name": "no"}])
        assert submitted(fake_client) == []

    def test_missing_required_field_is_named(self, fake_client):
        prime(fake_client, form("user", [field("time_window", required=True)]), created())
        with pytest.raises(ValueError, match="requires time_window"):
            hi.walk_flow(fake_client, "derivative", [{}])

    def test_bad_select_value_lists_the_valid_ones(self, fake_client):
        prime(
            fake_client,
            form("user", [field("cycle", required=True, options=["none", "daily"])]),
            created(),
        )
        with pytest.raises(ValueError, match="valid values: none, daily"):
            hi.walk_flow(fake_client, "utility_meter", [{"cycle": "fortnightly"}])

    def test_flow_that_wants_another_step_is_an_error_not_a_silent_success(self, fake_client):
        prime(
            fake_client,
            form("user", [field("name", required=True)]),
            form("settings", [field("invert")]),
        )
        with pytest.raises(HomeAssistantError, match="more steps are needed"):
            hi.walk_flow(fake_client, "trend", [{"name": "x"}])

    def test_server_error_body_is_translated(self, fake_client):
        fake_client.set_seq("POST", FLOW, form("user", []))
        fake_client.set_rest_error(
            "POST", f"{FLOW}/F1", 400, '{"errors": {"state": "Value should be a list"}}'
        )
        with pytest.raises(HomeAssistantError, match="state: Value should be a list"):
            hi.walk_flow(fake_client, "history_stats", [{}])

    def test_unknown_handler_points_at_config_flow_handlers(self, fake_client):
        fake_client.set_rest_error(
            "POST", FLOW, 404, '{"message": "Invalid handler specified"}'
        )
        with pytest.raises(HomeAssistantError, match="config-flow handlers"):
            hi.walk_flow(fake_client, "filter", [{}])

    def test_validation_can_be_switched_off(self, fake_client):
        prime(fake_client, form("user", [field("known")]), created())
        hi.walk_flow(fake_client, "x", [{"unknown": 1}], validate=False)
        assert submitted(fake_client) == [{"unknown": 1}]


class TestEntityResolution:
    def test_returns_only_this_entry_s_entities(self, fake_client):
        fake_client.set_ws(
            "config/entity_registry/list",
            [
                {"entity_id": "sensor.mine", "config_entry_id": "E1"},
                {"entity_id": "sensor.theirs", "config_entry_id": "E2"},
                {"entity_id": "sensor.orphan", "config_entry_id": None},
            ],
        )
        assert hi.helper_entities(fake_client, "E1", wait=0) == ["sensor.mine"]

    def test_empty_after_deadline_is_not_an_error(self, fake_client):
        fake_client.set_ws("config/entity_registry/list", [])
        assert hi.helper_entities(fake_client, "E1", wait=0) == []

    def test_entry_id_is_required(self, fake_client):
        with pytest.raises(ValueError):
            hi.helper_entities(fake_client, "")


class TestTypedCreators:
    def test_derivative_sends_a_zero_time_window_by_default(self, fake_client):
        prime(
            fake_client,
            form(
                "user",
                [
                    field("name", required=True),
                    field("source", required=True),
                    field("round", required=True),
                    field("time_window", required=True),
                    field("unit_time", required=True, options=["s", "min", "h", "d"]),
                    field("unit_prefix", options=["k", "M"]),
                ],
            ),
            created(),
        )
        out = hi.create_derivative(fake_client, name="W", source="sensor.e", wait=0)
        assert submitted(fake_client) == [
            {
                "name": "W",
                "source": "sensor.e",
                "round": 2,
                "time_window": {"hours": 0, "minutes": 0, "seconds": 0},
                "unit_time": "h",
            }
        ]
        assert out == {
            "created": True,
            "kind": "derivative",
            "domain": "derivative",
            "entry_id": "E1",
            "title": "T",
            "state": "loaded",
            "entities": ["sensor.new"],
        }

    def test_derivative_accepts_a_shorthand_duration(self, fake_client):
        prime(fake_client, form("user", []), created())
        hi.create_derivative(fake_client, name="W", source="sensor.e", time_window=90, wait=0)
        assert submitted(fake_client)[0]["time_window"] == {
            "hours": 0,
            "minutes": 0,
            "seconds": 90,
        }

    def test_derivative_rejects_a_bogus_duration_key(self, fake_client):
        with pytest.raises(ValueError, match="unknown duration key"):
            hi.create_derivative(
                fake_client, name="W", source="sensor.e", time_window={"fortnights": 2}
            )

    def test_riemann_uses_the_integration_domain(self, fake_client):
        prime(fake_client, form("user", []), created())
        hi.create_riemann(fake_client, name="Wh", source="sensor.p", wait=0)
        assert fake_client.calls[0]["payload"] == {"handler": "integration"}
        assert submitted(fake_client)[0]["method"] == "trapezoidal"

    def test_utility_meter_always_sends_the_full_form(self, fake_client):
        prime(fake_client, form("user", []), created())
        hi.create_utility_meter(
            fake_client, name="Daily", source="sensor.e", cycle="daily", tariffs=["peak"], wait=0
        )
        assert submitted(fake_client)[0] == {
            "name": "Daily",
            "source": "sensor.e",
            "cycle": "daily",
            "offset": 0,
            "tariffs": ["peak"],
            "net_consumption": False,
            "delta_values": False,
            "periodically_resetting": True,
        }

    def test_min_max_requires_entities(self, fake_client):
        with pytest.raises(ValueError, match="entity_ids"):
            hi.create_min_max(fake_client, name="n", entity_ids=[])

    def test_threshold_needs_a_bound(self, fake_client):
        with pytest.raises(ValueError, match="lower/upper"):
            hi.create_threshold(fake_client, name="n", entity_id="sensor.t")

    def test_threshold_omits_the_bound_it_was_not_given(self, fake_client):
        prime(fake_client, form("user", []), created())
        hi.create_threshold(fake_client, name="n", entity_id="sensor.t", upper=30, wait=0)
        assert submitted(fake_client)[0] == {
            "name": "n",
            "entity_id": "sensor.t",
            "hysteresis": 0.0,
            "upper": 30,
        }

    def test_trend_is_two_steps_and_no_options_flow_when_untuned(self, fake_client):
        prime(fake_client, form("user", []), form("settings", []), created())
        out = hi.create_trend(fake_client, name="rising", entity_id="sensor.t", wait=0)
        assert submitted(fake_client) == [
            {"name": "rising", "entity_id": "sensor.t"},
            {"invert": False},
        ]
        assert "options_applied" not in out

    def test_trend_tuning_goes_through_the_options_flow(self, fake_client):
        prime(fake_client, form("user", []), form("settings", []), created())
        fake_client.set("POST", "config/config_entries/options/flow", {"flow_id": "O1"})
        fake_client.set(
            "POST", "config/config_entries/options/flow/O1", {"type": "create_entry"}
        )
        out = hi.create_trend(
            fake_client, name="rising", entity_id="sensor.t", max_samples=5, wait=0
        )
        assert out["options_applied"] is True
        options_call = [
            c for c in fake_client.calls if c["path"] == "config/config_entries/options/flow/O1"
        ][0]
        assert options_call["payload"] == {"invert": False, "max_samples": 5}

    def test_statistics_walks_three_steps(self, fake_client):
        prime(
            fake_client,
            form("user", []),
            form("state_characteristic", []),
            form("options", []),
            created(),
        )
        hi.create_statistics(
            fake_client, name="s", entity_id="sensor.t", state_characteristic="median", wait=0
        )
        assert submitted(fake_client) == [
            {"name": "s", "entity_id": "sensor.t"},
            {"state_characteristic": "median"},
            {"sampling_size": 20, "precision": 2},
        ]

    def test_statistics_characteristic_is_checked_against_the_live_form(self, fake_client):
        prime(
            fake_client,
            form("user", []),
            form(
                "state_characteristic",
                [field("state_characteristic", required=True, options=["count_on", "count_off"])],
            ),
            created(),
        )
        with pytest.raises(ValueError, match="count_on, count_off"):
            hi.create_statistics(
                fake_client, name="s", entity_id="binary_sensor.b", state_characteristic="mean"
            )

    def test_history_stats_wraps_a_bare_state_in_a_list(self, fake_client):
        prime(fake_client, form("user", []), form("options", []), created())
        hi.create_history_stats(
            fake_client,
            name="uptime",
            entity_id="binary_sensor.up",
            state="on",
            start="{{ today_at() }}",
            duration={"hours": 24},
            wait=0,
        )
        first, second = submitted(fake_client)
        assert first["state"] == ["on"]
        assert second == {"start": "{{ today_at() }}", "duration": {"hours": 24}}

    def test_history_stats_wants_exactly_two_bounds(self, fake_client):
        with pytest.raises(ValueError, match="exactly two"):
            hi.create_history_stats(
                fake_client, name="n", entity_id="binary_sensor.b", state="on", start="x"
            )

    def test_random_is_a_menu_flow(self, fake_client):
        prime(fake_client, {"type": "menu", "flow_id": "F1", "menu_options": ["sensor"]},
              form("sensor", []), created())
        hi.create_random(fake_client, name="dice", minimum=1, maximum=6, wait=0)
        assert submitted(fake_client) == [
            {"next_step_id": "sensor"},
            {"name": "dice", "minimum": 1, "maximum": 6},
        ]

    def test_random_binary_variant_refuses_sensor_only_fields(self, fake_client):
        with pytest.raises(ValueError, match="variant=sensor only"):
            hi.create_random(fake_client, name="d", variant="binary_sensor", minimum=1)

    def test_random_range_must_be_ordered(self, fake_client):
        with pytest.raises(ValueError, match="greater than minimum"):
            hi.create_random(fake_client, name="d", minimum=6, maximum=1)

    def test_template_variant_fields_pass_through(self, fake_client):
        prime(fake_client, {"type": "menu", "flow_id": "F1", "menu_options": ["number"]},
              form("number", []), created())
        hi.create_template(
            fake_client,
            name="dial",
            variant="number",
            state="{{ 5 }}",
            fields={"min": 0, "max": 10, "step": 1, "set_value": []},
            wait=0,
        )
        assert submitted(fake_client)[1] == {
            "name": "dial",
            "state": "{{ 5 }}",
            "min": 0,
            "max": 10,
            "step": 1,
            "set_value": [],
        }

    def test_template_rejects_an_unknown_variant(self, fake_client):
        with pytest.raises(ValueError, match="variant must be one of"):
            hi.create_template(fake_client, name="x", variant="climate")

    def test_group_all_is_binary_sensor_only(self, fake_client):
        with pytest.raises(ValueError, match="binary_sensor"):
            hi.create_group(fake_client, name="g", entities=["light.a"], variant="light", all=True)

    def test_group_aggregation_is_sensor_only(self, fake_client):
        with pytest.raises(ValueError, match="variant=sensor"):
            hi.create_group(
                fake_client, name="g", entities=["light.a"], variant="light", type="sum"
            )

    def test_group_sends_the_menu_choice_then_the_form(self, fake_client):
        prime(fake_client, {"type": "menu", "flow_id": "F1", "menu_options": ["light"]},
              form("light", []), created())
        hi.create_group(fake_client, name="Kitchen", entities=["light.a", "light.b"], wait=0)
        assert submitted(fake_client) == [
            {"next_step_id": "light"},
            {"name": "Kitchen", "entities": ["light.a", "light.b"], "hide_members": False},
        ]

    def test_generic_thermostat_sends_an_empty_presets_step(self, fake_client):
        prime(fake_client, form("user", []), form("presets", []), created())
        hi.create_generic_thermostat(
            fake_client, name="t", heater="switch.h", target_sensor="sensor.t", wait=0
        )
        assert submitted(fake_client)[1] == {}

    def test_generic_thermostat_presets_are_forwarded(self, fake_client):
        prime(fake_client, form("user", []), form("presets", []), created())
        hi.create_generic_thermostat(
            fake_client,
            name="t",
            heater="switch.h",
            target_sensor="sensor.t",
            presets={"away_temp": 16},
            wait=0,
        )
        assert submitted(fake_client)[1] == {"away_temp": 16}

    def test_switch_as_x_refuses_a_non_switch_source(self, fake_client):
        with pytest.raises(ValueError, match="switch"):
            hi.create_switch_as_x(fake_client, entity_id="light.a", target_domain="fan")

    def test_switch_as_x_payload_has_no_name(self, fake_client):
        prime(fake_client, form("user", []), created())
        hi.create_switch_as_x(
            fake_client, entity_id="switch.a", target_domain="light", wait=0
        )
        assert submitted(fake_client)[0] == {
            "entity_id": "switch.a",
            "target_domain": "light",
            "invert": False,
        }

    def test_tod_uses_after_time_and_before_time(self, fake_client):
        prime(fake_client, form("user", []), created())
        hi.create_tod(fake_client, name="day", after_time="08:00:00", before_time="22:00:00", wait=0)
        assert submitted(fake_client)[0] == {
            "name": "day",
            "after_time": "08:00:00",
            "before_time": "22:00:00",
        }

    def test_mold_indicator_payload(self, fake_client):
        prime(fake_client, form("user", []), created())
        hi.create_mold_indicator(
            fake_client,
            name="m",
            indoor_temp_sensor="sensor.it",
            indoor_humidity_sensor="sensor.ih",
            outdoor_temp_sensor="sensor.ot",
            wait=0,
        )
        assert submitted(fake_client)[0]["calibration_factor"] == 2.0

    def test_create_raw_accepts_any_domain(self, fake_client):
        prime(fake_client, form("user", []), created())
        out = hi.create_raw(fake_client, "filter", [{"name": "f"}], wait=0)
        assert fake_client.calls[0]["payload"] == {"handler": "filter"}
        assert out["domain"] == "filter"

    def test_resolve_can_be_skipped(self, fake_client):
        prime(fake_client, form("user", []), created())
        out = hi.create_tod(
            fake_client, name="d", after_time="1:00:00", before_time="2:00:00", resolve=False
        )
        assert "entities" not in out
        assert fake_client.ws_calls == []


class TestLifecycle:
    def test_list_helpers_filters_server_side_and_locally(self, fake_client):
        fake_client.set_ws(
            "config_entries/get",
            [
                {"entry_id": "a", "domain": "derivative"},
                {"entry_id": "b", "domain": "template"},
            ],
        )
        out = hi.list_helpers(fake_client, domain="derivative")
        assert [e["entry_id"] for e in out] == ["a"]
        assert fake_client.ws_calls[-1]["payload"] == {
            "type_filter": "helper",
            "domain": "derivative",
        }

    def test_get_helper_returns_none_when_absent(self, fake_client):
        fake_client.set_ws("config_entries/get", [{"entry_id": "a", "domain": "tod"}])
        assert hi.get_helper(fake_client, "zzz") is None
        assert hi.get_helper(fake_client, "a")["domain"] == "tod"

    def test_delete_uses_rest_not_websocket(self, fake_client):
        fake_client.set("DELETE", "config/config_entries/entry/E9", {"require_restart": False})
        assert hi.delete_helper(fake_client, "E9") == {"require_restart": False}
        assert fake_client.ws_calls == []
        assert fake_client.calls[-1]["path"] == "config/config_entries/entry/E9"

    def test_delete_requires_an_entry_id(self, fake_client):
        with pytest.raises(ValueError):
            hi.delete_helper(fake_client, "")

    def test_set_options_inits_then_configures(self, fake_client):
        fake_client.set("POST", "config/config_entries/options/flow", {"flow_id": "O2"})
        fake_client.set(
            "POST", "config/config_entries/options/flow/O2", {"type": "create_entry"}
        )
        out = hi.set_helper_options(fake_client, "E1", {"target_humidity": 55})
        assert out["type"] == "create_entry"
        assert fake_client.calls[0]["payload"] == {"handler": "E1"}
        assert fake_client.calls[1]["payload"] == {"target_humidity": 55}

    def test_set_options_needs_input(self, fake_client):
        with pytest.raises(ValueError, match="non-empty dict"):
            hi.set_helper_options(fake_client, "E1", {})

    def test_set_options_translates_and_aborts_on_failure(self, fake_client):
        fake_client.set("POST", "config/config_entries/options/flow", {"flow_id": "O3"})
        fake_client.set_rest_error(
            "POST",
            "config/config_entries/options/flow/O3",
            400,
            '{"errors": {"base": ["extra keys not allowed @ data[\'nope\']"]}}',
        )
        with pytest.raises(HomeAssistantError, match="extra keys not allowed"):
            hi.set_helper_options(fake_client, "E1", {"nope": 1})
        assert {"verb": "DELETE", "path": "config/config_entries/options/flow/O3"} in (
            fake_client.calls
        )
