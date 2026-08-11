"""Unit tests for `target` — what a target resolves to, and what it can do.

All tests run against FakeClient — no live Home Assistant required. The
expected shapes were taken from a real 2026.8.1 instance and from
`homeassistant/components/websocket_api/commands.py` in the running source.

WS message types covered:
  extract_from_target         — targets.extract
  get_services_for_target     — targets.services_for
  get_triggers_for_target     — targets.triggers_for
  get_conditions_for_target   — targets.conditions_for
  slugify                     — targets.slugify

NOT covered here: `validate_config` / `test_condition` / `execute_script` /
`entity/source` landed on main as the `action` group and `entity source` while
this was being written. `tests/test_script_engine.py` owns them.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import targets


class TestBuildTarget:
    def test_only_populated_fields_are_included(self):
        assert targets.build_target(area_id=["kitchen"], entity_id=[]) == {
            "area_id": ["kitchen"]
        }

    def test_an_empty_target_names_every_option(self):
        with pytest.raises(ValueError) as exc:
            targets.build_target()
        for field in targets.TARGET_FIELDS:
            assert f"--{field.replace('_', '-')}" in str(exc.value)

    def test_an_unknown_field_is_rejected_before_the_call(self, fake_client):
        """HA's own error names the wrapper key, not the mistake."""
        with pytest.raises(ValueError, match="Not a target field"):
            targets.extract(fake_client, {"selector": {"entity": {}}})
        assert fake_client.ws_calls == []


class TestExtract:
    def test_missing_ids_are_surfaced(self, fake_client):
        """A label HA cannot resolve contributes nothing to a real call."""
        fake_client.set_ws(
            "extract_from_target",
            {
                "referenced_entities": [],
                "referenced_devices": [],
                "referenced_areas": [],
                "missing_labels": ["nope"],
                "missing_devices": [],
                "missing_areas": [],
                "missing_floors": [],
            },
        )
        got = targets.extract(fake_client, {"label_id": ["nope"]})
        assert got["missing_labels"] == ["nope"]
        assert got["has_missing"] is True
        assert got["resolves_to_nothing"] is True

    def test_expand_group_default_is_has_own(self, fake_client):
        """FALSE for extract, TRUE for the *_for_target trio. HA's asymmetry."""
        fake_client.set_ws("extract_from_target", {"referenced_entities": ["light.a"]})
        targets.extract(fake_client, {"area_id": ["kitchen"]})
        assert fake_client.ws_calls[-1]["payload"]["expand_group"] is False

        fake_client.set_ws("get_services_for_target", [])
        targets.services_for(fake_client, {"area_id": ["kitchen"]})
        assert fake_client.ws_calls[-1]["payload"]["expand_group"] is True

    def test_entity_count_counts_entities(self, fake_client):
        fake_client.set_ws(
            "extract_from_target", {"referenced_entities": ["light.a", "light.b"]}
        )
        got = targets.extract(fake_client, {"area_id": ["kitchen"]})
        assert got["entity_count"] == 2
        assert got["resolves_to_nothing"] is False


class TestForTarget:
    @pytest.mark.parametrize(
        ("fn", "command", "key"),
        [
            (targets.services_for, "get_services_for_target", "services"),
            (targets.triggers_for, "get_triggers_for_target", "triggers"),
            (targets.conditions_for, "get_conditions_for_target", "conditions"),
        ],
    )
    def test_each_sends_its_own_command(self, fake_client, fn, command, key):
        fake_client.set_ws(command, ["homeassistant.turn_on"])
        got = fn(fake_client, {"entity_id": ["sun.sun"]})
        assert fake_client.ws_calls[-1]["type"] == command
        assert got[key] == ["homeassistant.turn_on"]
        assert got["count"] == 1

    def test_an_empty_list_is_a_real_answer(self, fake_client):
        """sun.sun genuinely has no trigger platform; that is not a failure."""
        fake_client.set_ws("get_triggers_for_target", [])
        got = targets.triggers_for(fake_client, {"entity_id": ["sun.sun"]})
        assert got["triggers"] == []
        assert got["count"] == 0


class TestSlugify:
    def test_it_asks_ha_rather_than_reimplementing(self, fake_client):
        fake_client.set_ws("slugify", {"slug": "living_room_lamp_2"})
        got = targets.slugify(fake_client, "Living Room — Lamp #2")
        assert got["slug"] == "living_room_lamp_2"
        assert fake_client.ws_calls[-1]["payload"] == {"text": "Living Room — Lamp #2"}
