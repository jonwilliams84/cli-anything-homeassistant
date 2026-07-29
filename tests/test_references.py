"""Unit tests for cli_anything.homeassistant.core.references.

Covers the entity cross-search logic: _walk_strings, _matches_entity,
_snippet, _ui_configs, _template_helper_entries, _lovelace_configs,
and the public find_references() across all kinds.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core.references import (
    _lovelace_configs,
    _matches_entity,
    _snippet,
    _template_helper_entries,
    _ui_configs,
    _walk_strings,
    find_references,
)


ENTITY = "sensor.temperature"


# ── _walk_strings ────────────────────────────────────────────────────────────


class TestWalkStrings:
    def test_walks_nested_dict(self):
        result = list(_walk_strings({"a": {"b": "hello"}}))
        assert ("a.b", "hello") in result

    def test_walks_list(self):
        result = list(_walk_strings({"items": ["x", "y"]}))
        assert ("items[0]", "x") in result
        assert ("items[1]", "y") in result

    def test_walks_top_level_string(self):
        result = list(_walk_strings("just a string"))
        assert result == [("", "just a string")]

    def test_skips_non_strings(self):
        result = list(_walk_strings({"n": 42, "b": True, "f": 3.14}))
        assert result == []

    def test_empty_dict(self):
        assert list(_walk_strings({})) == []


# ── _matches_entity ─────────────────────────────────────────────────────────


class TestMatchesEntity:
    def test_exact_match(self):
        assert _matches_entity("sensor.temperature is high", ENTITY) is True

    def test_no_match_different_entity(self):
        assert _matches_entity("sensor.humidity is high", ENTITY) is False

    def test_word_boundary_prevents_partial_match(self):
        """sensor.temperature should NOT match sensor.temperature_extra."""
        assert _matches_entity("sensor.temperature_extra", ENTITY) is False

    def test_word_boundary_prevents_prefix_match(self):
        assert _matches_entity("mysensor.temperature", ENTITY) is False

    def test_match_at_start_of_string(self):
        assert _matches_entity("sensor.temperature", ENTITY) is True

    def test_match_at_end_of_string(self):
        assert _matches_entity("value: sensor.temperature", ENTITY) is True

    def test_unique_id_match(self):
        assert _matches_entity("the id is temp_42", ENTITY,
                               also_match_unique_id="temp_42") is True

    def test_unique_id_no_match(self):
        assert _matches_entity("nothing here", ENTITY,
                               also_match_unique_id="temp_42") is False

    def test_no_unique_id_provided(self):
        assert _matches_entity("nothing here", ENTITY) is False


# ── _snippet ─────────────────────────────────────────────────────────────────


class TestSnippet:
    def test_snippet_around_match(self):
        text = "The value of sensor.temperature is 23.5 degrees right now"
        snip = _snippet(text, ENTITY)
        assert "sensor.temperature" in snip

    def test_snippet_truncates_with_ellipsis(self):
        long_text = "x" * 100 + " sensor.temperature " + "y" * 100
        snip = _snippet(long_text, ENTITY, span=10)
        assert snip.startswith("…")
        assert snip.endswith("…")

    def test_snippet_no_match_returns_prefix(self):
        text = "this text does not contain the entity"
        snip = _snippet(text, ENTITY)
        assert snip == text[:80]

    def test_snippet_replaces_newlines(self):
        text = "line1\nsensor.temperature\nline3"
        snip = _snippet(text, ENTITY)
        assert "\n" not in snip


# ── _ui_configs ──────────────────────────────────────────────────────────────


class TestUiConfigs:
    def test_automation_uses_attributes_id(self, fake_client):
        """For automations, the config id comes from attributes.id."""
        fake_client.set("GET", "states", [
            {"entity_id": "automation.turn_on_lights",
             "attributes": {"id": "auto-123"}},
        ])
        fake_client.set("GET", "config/automation/config/auto-123",
                        {"alias": "Turn On Lights", "trigger": []})
        result = _ui_configs(fake_client, "automation")
        assert len(result) == 1
        assert result[0][0] == "automation.turn_on_lights"
        assert result[0][1]["alias"] == "Turn On Lights"

    def test_script_uses_object_id(self, fake_client):
        """For scripts/scenes, the config id is the entity_id suffix."""
        fake_client.set("GET", "states", [
            {"entity_id": "script.my_script", "attributes": {}},
        ])
        fake_client.set("GET", "config/script/config/my_script",
                        {"alias": "My Script"})
        result = _ui_configs(fake_client, "script")
        assert len(result) == 1
        assert result[0][1]["alias"] == "My Script"

    def test_skips_non_matching_domain(self, fake_client):
        fake_client.set("GET", "states", [
            {"entity_id": "sensor.temp", "attributes": {}},
        ])
        result = _ui_configs(fake_client, "automation")
        assert result == []

    def test_config_fetch_failure_skipped(self, fake_client):
        """If config fetch returns non-dict, the entry is skipped."""
        fake_client.set("GET", "states", [
            {"entity_id": "automation.x", "attributes": {"id": "x"}},
        ])
        # Return a non-dict (list) — should be skipped
        fake_client.set("GET", "config/automation/config/x", [])
        result = _ui_configs(fake_client, "automation")
        assert result == []


# ── _template_helper_entries ─────────────────────────────────────────────────


class TestTemplateHelperEntries:
    def test_reads_options_from_schema(self, fake_client):
        fake_client.set_ws("config_entries/get", [
            {"entry_id": "entry-1", "title": "My Sensor", "domain": "template"},
        ])
        fake_client.set("POST", "config/config_entries/options/flow", {
            "flow_id": "flow-1",
            "data_schema": [
                {"name": "state", "description": {"suggested_value": "{{ 1 }}"}},
                {"name": "name", "description": {"suggested_value": "My Sensor"}},
            ],
        })
        fake_client.set("DELETE", "config/config_entries/options/flow/flow-1", {})

        entries = _template_helper_entries(fake_client)
        assert len(entries) == 1
        assert entries[0]["entry_id"] == "entry-1"
        assert entries[0]["title"] == "My Sensor"
        assert entries[0]["options"]["state"] == "{{ 1 }}"
        assert entries[0]["options"]["name"] == "My Sensor"

    def test_skips_entries_without_entry_id(self, fake_client):
        fake_client.set_ws("config_entries/get", [
            {"entry_id": None, "title": "Bad"},
            {"entry_id": "entry-2", "title": "Good", "domain": "template"},
        ])
        fake_client.set("POST", "config/config_entries/options/flow", {
            "flow_id": "f2", "data_schema": [],
        })
        fake_client.set("DELETE", "config/config_entries/options/flow/f2", {})

        entries = _template_helper_entries(fake_client)
        assert len(entries) == 1
        assert entries[0]["entry_id"] == "entry-2"


# ── _lovelace_configs ────────────────────────────────────────────────────────


class TestLovelaceConfigs:
    def test_main_dashboard_and_extra_boards(self, fake_client):
        fake_client.set_ws("lovelace/dashboards/list", [
            {"url_path": "dashboard2"},
            {"url_path": "dashboard3"},
        ])
        fake_client.set_ws("lovelace/config", {"title": "main", "cards": []})

        configs = _lovelace_configs(fake_client)
        urls = [c[0] for c in configs]
        assert "lovelace" in urls

    def test_skips_boards_without_url(self, fake_client):
        fake_client.set_ws("lovelace/dashboards/list", [
            {"url_path": ""},
            {"url_path": "good"},
        ])
        fake_client.set_ws("lovelace/config", {"title": "main"})

        configs = _lovelace_configs(fake_client)
        urls = [c[0] for c in configs]
        assert "lovelace" in urls


# ── find_references ──────────────────────────────────────────────────────────


class TestFindReferences:
    def test_invalid_entity_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="entity_id must be in 'domain.object' form"):
            find_references(fake_client, "no_dot_here")

    def test_empty_entity_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="entity_id must be in 'domain.object' form"):
            find_references(fake_client, "")

    def test_finds_reference_in_automation(self, fake_client):
        """An automation that mentions the entity produces a hit."""
        fake_client.set("GET", "states", [
            {"entity_id": "automation.my_auto", "attributes": {"id": "a1"}},
        ])
        fake_client.set("GET", "config/automation/config/a1", {
            "alias": "My Auto",
            "trigger": [{"entity_id": ENTITY, "platform": "state"}],
        })
        # No template helpers or lovelace
        fake_client.set_ws("config_entries/get", [])
        fake_client.set_ws("lovelace/dashboards/list", [])
        fake_client.set_ws("lovelace/config", {})

        hits = find_references(fake_client, ENTITY)
        auto_hits = [h for h in hits if h["kind"] == "automation"]
        assert len(auto_hits) == 1
        assert auto_hits[0]["entity_id"] == "automation.my_auto"
        assert auto_hits[0]["name"] == "My Auto"
        assert ENTITY in auto_hits[0]["snippet"]

    def test_finds_reference_in_lovelace_card(self, fake_client):
        fake_client.set("GET", "states", [])
        fake_client.set_ws("config_entries/get", [])
        fake_client.set_ws("lovelace/dashboards/list", [])
        fake_client.set_ws("lovelace/config", {
            "cards": [{"entity": ENTITY, "type": "sensor"}],
        })

        hits = find_references(fake_client, ENTITY)
        lovelace_hits = [h for h in hits if h["kind"] == "lovelace"]
        assert len(lovelace_hits) == 1
        assert lovelace_hits[0]["dashboard"] == "lovelace"
        assert ENTITY in lovelace_hits[0]["snippet"]

    def test_include_kinds_filter(self, fake_client):
        """When include_kinds limits to one kind, other kinds are not searched."""
        fake_client.set("GET", "states", [
            {"entity_id": "automation.my_auto", "attributes": {"id": "a1"}},
        ])
        fake_client.set("GET", "config/automation/config/a1", {
            "alias": "My Auto",
            "trigger": [{"entity_id": ENTITY}],
        })
        fake_client.set_ws("config_entries/get", [
            {"entry_id": "e1", "title": "T", "domain": "template"},
        ])
        fake_client.set("POST", "config/config_entries/options/flow", {
            "flow_id": "f1", "data_schema": [
                {"name": "state", "description": {"suggested_value": "{{ states('" + ENTITY + "') }}"}},
            ],
        })
        fake_client.set("DELETE", "config/config_entries/options/flow/f1", {})
        fake_client.set_ws("lovelace/dashboards/list", [])
        fake_client.set_ws("lovelace/config", {})

        # Only search automations
        hits = find_references(fake_client, ENTITY, include_kinds={"automation"})
        kinds = {h["kind"] for h in hits}
        assert kinds == {"automation"}

    def test_no_references_returns_empty(self, fake_client):
        fake_client.set("GET", "states", [])
        fake_client.set_ws("config_entries/get", [])
        fake_client.set_ws("lovelace/dashboards/list", [])
        fake_client.set_ws("lovelace/config", {})

        hits = find_references(fake_client, ENTITY)
        assert hits == []

    def test_max_hits_per_kind_limit(self, fake_client):
        """The max_hits_per_kind parameter caps results per kind."""
        # Create multiple automations all referencing the entity
        states = []
        for i in range(5):
            states.append({
                "entity_id": f"automation.auto_{i}",
                "attributes": {"id": f"a{i}"},
            })
        fake_client.set("GET", "states", states)
        for i in range(5):
            fake_client.set("GET", f"config/automation/config/a{i}", {
                "alias": f"Auto {i}",
                "trigger": [{"entity_id": ENTITY}],
            })
        fake_client.set_ws("config_entries/get", [])
        fake_client.set_ws("lovelace/dashboards/list", [])
        fake_client.set_ws("lovelace/config", {})

        hits = find_references(fake_client, ENTITY, max_hits_per_kind=2)
        auto_hits = [h for h in hits if h["kind"] == "automation"]
        assert len(auto_hits) == 2


# ── find_references: template_helper kind ────────────────────────────────────


class TestFindReferencesTemplateHelper:
    def test_finds_reference_in_template_helper(self, fake_client):
        """A template helper whose state template references the entity produces a hit."""
        fake_client.set("GET", "states", [])
        fake_client.set_ws("config_entries/get", [
            {"entry_id": "e1", "title": "Derived Sensor", "domain": "template"},
        ])
        fake_client.set("POST", "config/config_entries/options/flow", {
            "flow_id": "f1",
            "data_schema": [
                {"name": "state", "description": {"suggested_value": "{{ states('" + ENTITY + "') }}"}},
                {"name": "name", "description": {"suggested_value": "Derived Sensor"}},
            ],
        })
        fake_client.set("DELETE", "config/config_entries/options/flow/f1", {})
        fake_client.set_ws("lovelace/dashboards/list", [])
        fake_client.set_ws("lovelace/config", {})

        hits = find_references(fake_client, ENTITY)
        th_hits = [h for h in hits if h["kind"] == "template_helper"]
        assert len(th_hits) == 1
        assert th_hits[0]["entry_id"] == "e1"
        assert th_hits[0]["name"] == "Derived Sensor"
        assert ENTITY in th_hits[0]["snippet"]

    def test_template_helper_no_match_not_in_hits(self, fake_client):
        """A template helper that doesn't reference the entity produces no hit."""
        fake_client.set("GET", "states", [])
        fake_client.set_ws("config_entries/get", [
            {"entry_id": "e1", "title": "Unrelated", "domain": "template"},
        ])
        fake_client.set("POST", "config/config_entries/options/flow", {
            "flow_id": "f1",
            "data_schema": [
                {"name": "state", "description": {"suggested_value": "{{ states('sensor.other') }}"}},
            ],
        })
        fake_client.set("DELETE", "config/config_entries/options/flow/f1", {})
        fake_client.set_ws("lovelace/dashboards/list", [])
        fake_client.set_ws("lovelace/config", {})

        hits = find_references(fake_client, ENTITY)
        assert [h for h in hits if h["kind"] == "template_helper"] == []


# ── find_references: scene kind ──────────────────────────────────────────────


class TestFindReferencesScene:
    def test_finds_reference_in_scene(self, fake_client):
        fake_client.set("GET", "states", [
            {"entity_id": "scene.cozy", "attributes": {}},
        ])
        fake_client.set("GET", "config/scene/config/cozy", {
            "alias": "Cozy",
            "entities": {ENTITY: {"state": "on"}},
        })
        fake_client.set_ws("config_entries/get", [])
        fake_client.set_ws("lovelace/dashboards/list", [])
        fake_client.set_ws("lovelace/config", {})

        hits = find_references(fake_client, ENTITY)
        scene_hits = [h for h in hits if h["kind"] == "scene"]
        assert len(scene_hits) == 1
        assert scene_hits[0]["entity_id"] == "scene.cozy"
        assert scene_hits[0]["name"] == "Cozy"
