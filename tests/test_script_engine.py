"""Unit tests for `core/script_engine.py`.

Covers the four script-engine WS commands (`execute_script`,
`validate_config`, `test_condition`, `entity/source`) plus the composite
pre-flight helpers built on top of them.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import script_engine as se


# ──────────────────────────────────────────────────────────────── execute_script

class TestExecuteScript:
    def test_wraps_single_mapping_into_sequence(self, fake_client):
        fake_client.set_ws("execute_script", {"context": {"id": "c1"}, "response": None})
        result = se.execute_script(fake_client, {"action": "light.turn_on"})
        assert result["context"]["id"] == "c1"
        call = fake_client.ws_calls[-1]
        assert call["type"] == "execute_script"
        assert call["payload"] == {"sequence": [{"action": "light.turn_on"}]}

    def test_passes_list_through(self, fake_client):
        fake_client.set_ws("execute_script", {"context": {}, "response": None})
        seq = [{"delay": {"seconds": 1}}, {"action": "light.turn_off"}]
        se.execute_script(fake_client, seq)
        assert fake_client.ws_calls[-1]["payload"]["sequence"] == seq

    def test_variables_included_when_supplied(self, fake_client):
        fake_client.set_ws("execute_script", {})
        se.execute_script(fake_client, [{"action": "a.b"}], variables={"room": "kitchen"})
        assert fake_client.ws_calls[-1]["payload"]["variables"] == {"room": "kitchen"}

    def test_empty_variables_omitted(self, fake_client):
        fake_client.set_ws("execute_script", {})
        se.execute_script(fake_client, [{"action": "a.b"}], variables={})
        assert "variables" not in fake_client.ws_calls[-1]["payload"]

    def test_returns_empty_dict_when_ha_returns_nothing(self, fake_client):
        fake_client.set_ws("execute_script", None)
        assert se.execute_script(fake_client, [{"action": "a.b"}]) == {}

    def test_response_variable_payload_surfaces(self, fake_client):
        fake_client.set_ws(
            "execute_script",
            {"context": {"id": "c"}, "response": {"agenda": {"events": []}}},
        )
        out = se.execute_script(fake_client, [{"action": "calendar.get_events"}])
        assert out["response"] == {"agenda": {"events": []}}

    @pytest.mark.parametrize("bad", [[], "nope", 3, None])
    def test_rejects_bad_sequence(self, fake_client, bad):
        with pytest.raises(ValueError):
            se.execute_script(fake_client, bad)

    def test_rejects_non_mapping_step(self, fake_client):
        with pytest.raises(ValueError, match=r"sequence\[1\]"):
            se.execute_script(fake_client, [{"action": "a.b"}, "oops"])

    def test_rejects_non_mapping_variables(self, fake_client):
        with pytest.raises(ValueError, match="variables must be a mapping"):
            se.execute_script(fake_client, [{"action": "a.b"}], variables=["x"])


class TestBuildServiceAction:
    def test_minimal(self):
        assert se.build_service_action("light.turn_on") == {"action": "light.turn_on"}

    def test_full(self):
        step = se.build_service_action(
            "calendar.get_events",
            data={"duration": {"hours": 24}},
            target={"entity_id": "calendar.home"},
            response_variable="agenda",
        )
        assert step == {
            "action": "calendar.get_events",
            "target": {"entity_id": "calendar.home"},
            "data": {"duration": {"hours": 24}},
            "response_variable": "agenda",
        }

    @pytest.mark.parametrize("bad", ["light", "light.turn.on", ".turn_on", "light.", 7])
    def test_rejects_bad_action_name(self, bad):
        with pytest.raises(ValueError, match="domain.service"):
            se.build_service_action(bad)

    def test_rejects_bad_data(self):
        with pytest.raises(ValueError, match="data must be a mapping"):
            se.build_service_action("a.b", data=["x"])

    def test_rejects_bad_target(self):
        with pytest.raises(ValueError, match="target must be a mapping"):
            se.build_service_action("a.b", target="light.x")

    def test_rejects_blank_response_variable(self):
        with pytest.raises(ValueError, match="response_variable"):
            se.build_service_action("a.b", response_variable="   ")

    def test_empty_data_and_target_omitted(self):
        assert se.build_service_action("a.b", data={}, target={}) == {"action": "a.b"}


class TestRunServiceAction:
    def test_builds_and_executes(self, fake_client):
        fake_client.set_ws("execute_script", {"context": {"id": "c"}, "response": None})
        se.run_service_action(
            fake_client,
            "light.turn_on",
            target={"entity_id": "light.kitchen"},
            data={"brightness": 200},
            variables={"who": "jon"},
        )
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["sequence"] == [
            {
                "action": "light.turn_on",
                "target": {"entity_id": "light.kitchen"},
                "data": {"brightness": 200},
            }
        ]
        assert payload["variables"] == {"who": "jon"}


# ─────────────────────────────────────────────────────────────── validate_config

class TestValidateConfig:
    def test_single_block(self, fake_client):
        fake_client.set_ws("validate_config", {"actions": {"valid": True, "error": None}})
        out = se.validate_config(fake_client, actions=[{"action": "light.turn_on"}])
        assert out["actions"]["valid"] is True
        assert fake_client.ws_calls[-1]["type"] == "validate_config"
        assert set(fake_client.ws_calls[-1]["payload"]) == {"actions"}

    def test_all_three_blocks(self, fake_client):
        fake_client.set_ws("validate_config", {})
        se.validate_config(
            fake_client,
            triggers=[{"trigger": "state", "entity_id": "sun.sun"}],
            conditions=[{"condition": "sun", "after": "sunset"}],
            actions=[{"action": "light.turn_on"}],
        )
        assert set(fake_client.ws_calls[-1]["payload"]) == {
            "triggers", "conditions", "actions",
        }

    def test_requires_at_least_one_block(self, fake_client):
        with pytest.raises(ValueError, match="at least one"):
            se.validate_config(fake_client)

    def test_empty_list_block_is_still_sent(self, fake_client):
        """An explicitly empty block is meaningful — it must not be dropped."""
        fake_client.set_ws("validate_config", {})
        se.validate_config(fake_client, conditions=[])
        assert fake_client.ws_calls[-1]["payload"] == {"conditions": []}


class TestNormalizeAutomationConfig:
    def test_plural_keys(self):
        cfg = {"triggers": [1], "conditions": [2], "actions": [3], "alias": "x"}
        assert se.normalize_automation_config(cfg) == {
            "triggers": [1], "conditions": [2], "actions": [3],
        }

    def test_legacy_singular_keys_upgraded(self):
        cfg = {"trigger": [1], "condition": [2], "action": [3]}
        assert se.normalize_automation_config(cfg) == {
            "triggers": [1], "conditions": [2], "actions": [3],
        }

    def test_plural_wins_over_legacy(self):
        cfg = {"trigger": ["old"], "triggers": ["new"]}
        assert se.normalize_automation_config(cfg) == {"triggers": ["new"]}

    def test_missing_blocks_omitted(self):
        assert se.normalize_automation_config({"action": [3]}) == {"actions": [3]}

    def test_rejects_non_mapping(self):
        with pytest.raises(ValueError, match="config must be a mapping"):
            se.normalize_automation_config([1, 2])


class TestValidateAutomationConfig:
    def test_valid_config(self, fake_client):
        fake_client.set_ws(
            "validate_config",
            {
                "triggers": {"valid": True, "error": None},
                "actions": {"valid": True, "error": None},
            },
        )
        out = se.validate_automation_config(
            fake_client,
            {"trigger": [{"trigger": "state"}], "action": [{"action": "light.turn_on"}]},
        )
        assert out["valid"] is True
        assert out["checked"] == ["actions", "triggers"]
        assert out["errors"] == []

    def test_invalid_block_reported(self, fake_client):
        fake_client.set_ws(
            "validate_config",
            {
                "triggers": {"valid": False, "error": "Invalid trigger 'stat'"},
                "actions": {"valid": True, "error": None},
            },
        )
        out = se.validate_automation_config(
            fake_client, {"triggers": [{"trigger": "stat"}], "actions": []}
        )
        assert out["valid"] is False
        assert out["errors"] == [{"block": "triggers", "error": "Invalid trigger 'stat'"}]

    def test_invalid_block_without_error_text(self, fake_client):
        fake_client.set_ws("validate_config", {"actions": {"valid": False}})
        out = se.validate_automation_config(fake_client, {"actions": []})
        assert out["errors"] == [{"block": "actions", "error": "invalid"}]

    def test_rejects_config_with_no_blocks(self, fake_client):
        with pytest.raises(ValueError, match="no triggers/conditions/actions"):
            se.validate_automation_config(fake_client, {"alias": "just a name"})


class TestValidateScriptConfig:
    def test_sequence_from_mapping(self, fake_client):
        fake_client.set_ws("validate_config", {"actions": {"valid": True, "error": None}})
        out = se.validate_script_config(
            fake_client, {"alias": "Bedtime", "sequence": [{"action": "light.turn_off"}]}
        )
        assert out["valid"] is True
        assert fake_client.ws_calls[-1]["payload"] == {
            "actions": [{"action": "light.turn_off"}]
        }

    def test_bare_list_accepted(self, fake_client):
        fake_client.set_ws("validate_config", {"actions": {"valid": True, "error": None}})
        assert se.validate_script_config(fake_client, [{"action": "a.b"}])["valid"] is True

    def test_rejects_mapping_without_sequence(self, fake_client):
        with pytest.raises(ValueError, match="no 'sequence' block"):
            se.validate_script_config(fake_client, {"alias": "x"})

    def test_rejects_scalar(self, fake_client):
        with pytest.raises(ValueError, match="config must be a mapping"):
            se.validate_script_config(fake_client, "sequence")


# ──────────────────────────────────────────────────────────────── test_condition

class TestTestCondition:
    def test_returns_raw_result(self, fake_client):
        fake_client.set_ws("test_condition", {"result": True})
        cond = {"condition": "state", "entity_id": "sun.sun", "state": "above_horizon"}
        assert se.test_condition(fake_client, cond) == {"result": True}
        assert fake_client.ws_calls[-1] == {
            "type": "test_condition", "payload": {"condition": cond},
        }

    def test_template_shorthand_string(self, fake_client):
        fake_client.set_ws("test_condition", {"result": False})
        se.test_condition(fake_client, "{{ 1 == 2 }}")
        assert fake_client.ws_calls[-1]["payload"]["condition"] == "{{ 1 == 2 }}"

    def test_variables_forwarded(self, fake_client):
        fake_client.set_ws("test_condition", {"result": True})
        se.test_condition(fake_client, {"condition": "template"}, variables={"x": 1})
        assert fake_client.ws_calls[-1]["payload"]["variables"] == {"x": 1}

    def test_condition_holds_true(self, fake_client):
        fake_client.set_ws("test_condition", {"result": True})
        assert se.condition_holds(fake_client, {"condition": "sun"}) is True

    def test_condition_holds_false(self, fake_client):
        fake_client.set_ws("test_condition", {"result": False})
        assert se.condition_holds(fake_client, {"condition": "sun"}) is False

    def test_condition_holds_missing_result_is_false(self, fake_client):
        fake_client.set_ws("test_condition", {})
        assert se.condition_holds(fake_client, {"condition": "sun"}) is False

    @pytest.mark.parametrize("bad", ["", "   ", {}, 5, None, []])
    def test_rejects_bad_condition(self, fake_client, bad):
        with pytest.raises(ValueError):
            se.test_condition(fake_client, bad)


class TestTestConditions:
    def test_batch_results(self, fake_client):
        fake_client.set_ws("test_condition", {"result": True})
        out = se.test_conditions(
            fake_client, [{"condition": "sun"}, {"condition": "state"}]
        )
        assert [r["index"] for r in out] == [0, 1]
        assert all(r["result"] is True and r["error"] is None for r in out)
        assert len(fake_client.ws_calls) == 2

    def test_single_mapping_is_wrapped(self, fake_client):
        fake_client.set_ws("test_condition", {"result": False})
        out = se.test_conditions(fake_client, {"condition": "sun"})
        assert len(out) == 1 and out[0]["result"] is False

    def test_error_tolerance_per_item(self, fake_client, monkeypatch):
        calls = {"n": 0}

        def flaky(msg_type, payload=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("WS command test_condition failed: invalid_format")
            return {"result": True}

        monkeypatch.setattr(fake_client, "ws_call", flaky)
        out = se.test_conditions(fake_client, [{"condition": "bogus"}, {"condition": "sun"}])
        assert out[0]["result"] is None
        assert "invalid_format" in out[0]["error"]
        assert out[1]["result"] is True

    def test_string_treated_as_template_shorthand(self, fake_client):
        fake_client.set_ws("test_condition", {"result": True})
        out = se.test_conditions(fake_client, "{{ true }}")
        assert len(out) == 1 and out[0]["result"] is True

    @pytest.mark.parametrize("bad", [[], 3, None])
    def test_rejects_bad_input(self, fake_client, bad):
        with pytest.raises(ValueError):
            se.test_conditions(fake_client, bad)


# ───────────────────────────────────────────────────────────────── entity/source

SOURCES = {
    "light.kitchen": {"domain": "hue"},
    "light.hall": {"domain": "hue"},
    "sun.sun": {"domain": "sun"},
    "sensor.weird": {},
}


class TestEntitySource:
    def test_full_map(self, fake_client):
        fake_client.set_ws("entity/source", SOURCES)
        assert se.entity_source(fake_client) == SOURCES
        assert fake_client.ws_calls[-1] == {"type": "entity/source", "payload": {}}

    def test_empty_result_normalized(self, fake_client):
        fake_client.set_ws("entity/source", None)
        assert se.entity_source(fake_client) == {}

    def test_source_for_entity(self, fake_client):
        fake_client.set_ws("entity/source", SOURCES)
        assert se.entity_source_for(fake_client, "sun.sun") == {"domain": "sun"}

    def test_source_for_unknown_entity_is_none(self, fake_client):
        fake_client.set_ws("entity/source", SOURCES)
        assert se.entity_source_for(fake_client, "light.ghost") is None

    @pytest.mark.parametrize("bad", ["kitchen", "", 5])
    def test_source_for_rejects_bad_entity_id(self, fake_client, bad):
        with pytest.raises(ValueError, match="entity_id"):
            se.entity_source_for(fake_client, bad)

    def test_grouped_by_integration(self, fake_client):
        fake_client.set_ws("entity/source", SOURCES)
        assert se.sources_by_integration(fake_client) == {
            "hue": ["light.hall", "light.kitchen"],
            "sun": ["sun.sun"],
            "unknown": ["sensor.weird"],
        }

    def test_grouped_filtered(self, fake_client):
        fake_client.set_ws("entity/source", SOURCES)
        assert se.sources_by_integration(fake_client, integration="hue") == {
            "hue": ["light.hall", "light.kitchen"]
        }

    def test_grouped_filter_miss_is_empty(self, fake_client):
        fake_client.set_ws("entity/source", SOURCES)
        assert se.sources_by_integration(fake_client, integration="zwave") == {}

    def test_grouped_tolerates_non_mapping_source(self, fake_client):
        fake_client.set_ws("entity/source", {"a.b": "hue"})
        assert se.sources_by_integration(fake_client) == {"unknown": ["a.b"]}
