"""Additional coverage tests targeting low-coverage modules with real logic.

Focuses on error paths, edge cases, and branches that existing tests miss.
Every test asserts behaviour, not source text.
"""

from __future__ import annotations

import json
import threading
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from cli_anything.homeassistant.core import (
    floors as floors_core,
    labels as labels_core,
    mqtt_discovery as mqtt_core,
    persons as persons_core,
)
from cli_anything.homeassistant.core import lovelace_cards as cards_core
from cli_anything.homeassistant.core import lovelace_mirror as mirror_core
from cli_anything.homeassistant.core import lovelace_card_types as card_types_core
from cli_anything.homeassistant.core import inspect as inspect_core


# ═══════════════════════════════════════════════════════════════════════════
# lovelace_cards.prune and helpers
# ═══════════════════════════════════════════════════════════════════════════

class TestPrune:
    """Tests for prune() and its internal helpers."""

    def test_prune_by_type_drops_matching_cards(self):
        cfg = {
            "views": [
                {
                    "path": "main",
                    "cards": [
                        {"type": "markdown", "content": "hello"},
                        {"type": "entities", "entities": ["light.kitchen"]},
                    ],
                }
            ]
        }
        result, counters = cards_core.prune(cfg, types={"markdown"})
        cards = result["views"][0]["cards"]
        assert len(cards) == 1
        assert cards[0]["type"] == "entities"
        assert counters["dropped_cards"] == 1

    def test_prune_by_entity_prefix_drops_card_with_matching_entity(self):
        cfg = {
            "views": [
                {
                    "cards": [
                        {"type": "entity", "entity": "sensor.old_temp"},
                        {"type": "entity", "entity": "sensor.new_temp"},
                    ],
                }
            ]
        }
        result, counters = cards_core.prune(cfg, entity_prefixes={"sensor.old_"})
        cards = result["views"][0]["cards"]
        assert len(cards) == 1
        assert cards[0]["entity"] == "sensor.new_temp"
        assert counters["dropped_cards"] == 1

    def test_prune_by_entity_prefix_checks_entities_list(self):
        cfg = {
            "views": [
                {
                    "cards": [
                        {
                            "type": "entities",
                            "entities": [
                                "sensor.old_1",
                                "sensor.new_1",
                            ],
                        },
                    ],
                }
            ]
        }
        result, counters = cards_core.prune(cfg, entity_prefixes={"sensor.old_"})
        assert counters["dropped_cards"] == 1
        assert result["views"][0]["cards"] == []

    def test_prune_by_entity_prefix_handles_dict_entities(self):
        cfg = {
            "views": [
                {
                    "cards": [
                        {
                            "type": "entities",
                            "entities": [
                                {"entity": "sensor.old_1", "name": "Old"},
                                {"entity": "sensor.new_1", "name": "New"},
                            ],
                        },
                    ],
                }
            ]
        }
        result, counters = cards_core.prune(cfg, entity_prefixes={"sensor.old_"})
        assert counters["dropped_cards"] == 1

    def test_prune_by_markdown_contains(self):
        cfg = {
            "views": [
                {
                    "cards": [
                        {"type": "markdown", "content": "## TODO: fix this"},
                        {"type": "markdown", "content": "## Done"},
                    ],
                }
            ]
        }
        result, counters = cards_core.prune(cfg, markdown_contains={"TODO"})
        cards = result["views"][0]["cards"]
        assert len(cards) == 1
        assert cards[0]["content"] == "## Done"
        assert counters["dropped_cards"] == 1

    def test_prune_markdown_contains_ignores_non_markdown_cards(self):
        cfg = {
            "views": [
                {
                    "cards": [
                        {"type": "entities", "content": "TODO: fix"},
                    ],
                }
            ]
        }
        result, counters = cards_core.prune(cfg, markdown_contains={"TODO"})
        assert counters["dropped_cards"] == 0
        assert len(result["views"][0]["cards"]) == 1

    def test_prune_drops_empty_stacks(self):
        cfg = {
            "views": [
                {
                    "cards": [
                        {
                            "type": "horizontal-stack",
                            "cards": [
                                {"type": "markdown", "content": "TODO"},
                            ],
                        },
                    ],
                }
            ]
        }
        result, counters = cards_core.prune(cfg, markdown_contains={"TODO"})
        assert counters["dropped_cards"] == 1
        assert counters["dropped_empty_stacks"] == 1
        assert result["views"][0]["cards"] == []

    def test_prune_blocked_subheadings_drops_heading_and_following_cards(self):
        cfg = {
            "views": [
                {
                    "cards": [
                        {"type": "heading", "heading": "Old Section"},
                        {"type": "markdown", "content": "card under old"},
                        {"type": "markdown", "content": "another under old"},
                        {"type": "heading", "heading": "Keep Section"},
                        {"type": "markdown", "content": "card under keep"},
                    ],
                }
            ]
        }
        result, counters = cards_core.prune(cfg, blocked_subheadings={"Old Section"})
        cards = result["views"][0]["cards"]
        # Should keep "Keep Section" heading and its card
        assert len(cards) == 2
        assert cards[0]["heading"] == "Keep Section"
        assert cards[1]["content"] == "card under keep"
        assert counters["dropped_subheading_groups"] == 1

    def test_prune_blocked_subheadings_at_end_of_list(self):
        """Heading at the very end with no following cards should still work."""
        cfg = {
            "views": [
                {
                    "cards": [
                        {"type": "markdown", "content": "keep me"},
                        {"type": "heading", "heading": "Trailing"},
                    ],
                }
            ]
        }
        result, counters = cards_core.prune(cfg, blocked_subheadings={"Trailing"})
        cards = result["views"][0]["cards"]
        assert len(cards) == 1
        assert cards[0]["content"] == "keep me"

    def test_prune_no_filters_returns_config_unchanged(self):
        cfg = {"views": [{"cards": [{"type": "markdown", "content": "hi"}]}]}
        result, counters = cards_core.prune(cfg)
        # With no filters, prune returns the config unchanged with empty counters
        assert result["views"][0]["cards"][0]["content"] == "hi"
        assert counters.get("dropped_cards", 0) == 0

    def test_prune_preserves_non_dict_cards(self):
        cfg = {"views": [{"cards": ["not-a-dict", {"type": "markdown", "content": "TODO"}]}]}
        result, counters = cards_core.prune(cfg, markdown_contains={"TODO"})
        # Non-dict card should be preserved
        assert "not-a-dict" in result["views"][0]["cards"]
        assert counters["dropped_cards"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# lovelace_cards.set_at_pointer / delete_at_pointer / insert_card
# ═══════════════════════════════════════════════════════════════════════════

class TestPointerOps:
    def test_set_at_pointer_simple_dict_key(self):
        cfg = {"views": [{"title": "old"}]}
        cards_core.set_at_pointer(cfg, "views[0]/title", "new")
        assert cfg["views"][0]["title"] == "new"

    def test_set_at_pointer_creates_missing_key(self):
        cfg = {"views": [{"title": "v"}]}
        cards_core.set_at_pointer(cfg, "views[0]/new_key", "val")
        assert cfg["views"][0]["new_key"] == "val"

    def test_set_at_pointer_nested_list(self):
        cfg = {"views": [{"cards": [{"type": "x"}, {"type": "y"}]}]}
        cards_core.set_at_pointer(cfg, "views[0]/cards[1]/type", "z")
        assert cfg["views"][0]["cards"][1]["type"] == "z"

    def test_delete_at_pointer_dict_key(self):
        cfg = {"views": [{"title": "v", "path": "p"}]}
        cards_core.delete_at_pointer(cfg, "views[0]/title")
        assert "title" not in cfg["views"][0]
        assert cfg["views"][0]["path"] == "p"

    def test_delete_at_pointer_list_element(self):
        cfg = {"views": [{"cards": [{"type": "a"}, {"type": "b"}, {"type": "c"}]}]}
        cards_core.delete_at_pointer(cfg, "views[0]/cards[1]")
        assert len(cfg["views"][0]["cards"]) == 2
        assert cfg["views"][0]["cards"][1]["type"] == "c"

    def test_set_at_pointer_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            cards_core.set_at_pointer({}, "", "x")

    def test_resolve_mixed_missing_key_raises(self):
        # views[0] is out of range for empty list
        with pytest.raises(IndexError):
            cards_core.set_at_pointer({"views": []}, "views[0]/missing/deep", "x")

    def test_resolve_mixed_index_out_of_range_raises(self):
        with pytest.raises(IndexError):
            cards_core.set_at_pointer({"views": [{"cards": []}]}, "views[0]/cards[5]/type", "x")

    def test_resolve_mixed_key_not_a_list_raises(self):
        with pytest.raises(KeyError, match="not a list"):
            cards_core.set_at_pointer({"views": [{"cards": "string"}]}, "views[0]/cards[0]/type", "x")


# ═══════════════════════════════════════════════════════════════════════════
# lovelace_cards.insert_card
# ═══════════════════════════════════════════════════════════════════════════

class TestInsertCard:
    def test_insert_card_appends_by_default(self):
        cfg = {"views": [{"cards": [{"type": "existing"}]}]}
        new_card = {"type": "markdown", "content": "new"}
        cards_core.insert_card(cfg, "views[0]", new_card)
        assert len(cfg["views"][0]["cards"]) == 2
        assert cfg["views"][0]["cards"][1] == new_card

    def test_insert_card_at_position(self):
        cfg = {"views": [{"cards": [{"type": "a"}, {"type": "c"}]}]}
        cards_core.insert_card(cfg, "views[0]", {"type": "b"}, position=1)
        assert [c["type"] for c in cfg["views"][0]["cards"]] == ["a", "b", "c"]

    def test_insert_card_position_beyond_end_appends(self):
        cfg = {"views": [{"cards": [{"type": "a"}]}]}
        cards_core.insert_card(cfg, "views[0]", {"type": "b"}, position=99)
        assert len(cfg["views"][0]["cards"]) == 2
        assert cfg["views"][0]["cards"][1]["type"] == "b"

    def test_insert_card_negative_position_clamped_to_zero(self):
        cfg = {"views": [{"cards": [{"type": "a"}, {"type": "b"}]}]}
        cards_core.insert_card(cfg, "views[0]", {"type": "x"}, position=-5)
        assert cfg["views"][0]["cards"][0]["type"] == "x"

    def test_insert_card_creates_cards_array_if_missing(self):
        cfg = {"views": [{"title": "v"}]}
        cards_core.insert_card(cfg, "views[0]", {"type": "markdown"})
        assert "cards" in cfg["views"][0]
        assert len(cfg["views"][0]["cards"]) == 1

    def test_insert_card_rejects_non_dict(self):
        with pytest.raises(ValueError, match="must be a dict"):
            cards_core.insert_card({}, "views[0]", "not-a-dict")


# ═══════════════════════════════════════════════════════════════════════════
# lovelace_cards.validate_templates
# ═══════════════════════════════════════════════════════════════════════════

class TestValidateTemplates:
    def test_validate_templates_no_templates(self):
        cfg = {"views": [{"cards": [{"type": "entities"}]}]}
        result = cards_core.validate_templates(MagicMock(), cfg)
        assert result["total_templates"] == 0
        assert result["failures"] == []

    def test_validate_templates_finds_jinja_strings(self):
        cfg = {
            "views": [
                {
                    "cards": [
                        {"type": "markdown", "content": "{{ states('sensor.temp') }}"},
                    ],
                }
            ]
        }
        mock_client = MagicMock()
        # Simulate successful render (no exception)
        with patch("cli_anything.homeassistant.core.template.render") as mock_render:
            mock_render.return_value = "23.5"
            result = cards_core.validate_templates(mock_client, cfg)
        assert result["total_templates"] == 1
        assert result["failures"] == []

    def test_validate_templates_records_failures(self):
        cfg = {
            "views": [
                {
                    "cards": [
                        {"type": "markdown", "content": "{{ bad_jinja }}"},
                    ],
                }
            ]
        }
        with patch("cli_anything.homeassistant.core.template.render", side_effect=RuntimeError("Template error")):
            result = cards_core.validate_templates(MagicMock(), cfg)
        assert result["total_templates"] == 1
        assert len(result["failures"]) == 1
        assert "Template error" in result["failures"][0]["error"]
        assert result["failures"][0]["field"] == "content"

    def test_validate_templates_skip_paths(self):
        cfg = {
            "views": [
                {
                    "cards": [
                        {"type": "markdown", "content": "{{ states('sensor.x') }}"},
                    ],
                }
            ]
        }
        with patch("cli_anything.homeassistant.core.template.render") as mock_render:
            result = cards_core.validate_templates(MagicMock(), cfg, skip_paths=("views[0]",))
        assert result["total_templates"] == 0
        mock_render.assert_not_called()

    def test_validate_templates_walks_nested_structures(self):
        cfg = {
            "views": [
                {
                    "cards": [
                        {
                            "type": "horizontal-stack",
                            "cards": [
                                {"type": "markdown", "content": "{{ 1 }}"},
                                {"type": "markdown", "content": "{{ 2 }}"},
                            ],
                        },
                    ],
                }
            ]
        }
        with patch("cli_anything.homeassistant.core.template.render") as mock_render:
            result = cards_core.validate_templates(MagicMock(), cfg)
        assert result["total_templates"] == 2
        assert mock_render.call_count == 2


# ═══════════════════════════════════════════════════════════════════════════
# lovelace_cards.lint_with_navigation / _validate_navigation_path
# ═══════════════════════════════════════════════════════════════════════════

class TestNavigationLint:
    def test_validate_navigation_path_valid_single_segment(self):
        result = cards_core._validate_navigation_path("/living_room", "my_dash", {"living_room", "kitchen"})
        assert result is None

    def test_validate_navigation_path_unknown_view(self):
        result = cards_core._validate_navigation_path("/nonexistent", "my_dash", {"living_room"})
        assert "unknown view path" in result

    def test_validate_navigation_path_must_start_with_slash(self):
        result = cards_core._validate_navigation_path("living_room", "my_dash", {"living_room"})
        assert "must start with /" in result

    def test_validate_navigation_path_empty(self):
        result = cards_core._validate_navigation_path("", "my_dash", {"living_room"})
        assert "must start with /" in result

    def test_validate_navigation_path_just_slash(self):
        result = cards_core._validate_navigation_path("/", "my_dash", {"living_room"})
        assert "empty" in result

    def test_validate_navigation_path_wrong_dashboard_prefix(self):
        result = cards_core._validate_navigation_path("/other_dash/living_room", "my_dash", {"living_room"})
        assert "dashboard prefix" in result

    def test_validate_navigation_path_correct_dashboard_prefix_valid_view(self):
        result = cards_core._validate_navigation_path("/my_dash/living_room", "my_dash", {"living_room"})
        assert result is None

    def test_validate_navigation_path_correct_dashboard_prefix_unknown_view(self):
        result = cards_core._validate_navigation_path("/my_dash/unknown", "my_dash", {"living_room"})
        assert "unknown view path" in result

    def test_lint_with_navigation_flags_bad_path(self):
        cfg = {
            "views": [
                {
                    "path": "main",
                    "cards": [
                        {
                            "type": "button",
                            "tap_action": {
                                "action": "navigate",
                                "navigation_path": "/nonexistent",
                            },
                        },
                    ],
                }
            ]
        }
        result = cards_core.lint_with_navigation(
            cfg,
            all_entity_ids=set(),
            dashboard_url_path="my_dash",
            known_view_paths={"main"},
        )
        assert "bad_navigation_paths" in result
        assert len(result["bad_navigation_paths"]) == 1
        assert result["bad_navigation_paths"][0]["navigation_path"] == "/nonexistent"

    def test_lint_with_navigation_no_bad_paths(self):
        cfg = {
            "views": [
                {
                    "path": "main",
                    "cards": [
                        {
                            "type": "button",
                            "tap_action": {
                                "action": "navigate",
                                "navigation_path": "/main",
                            },
                        },
                    ],
                }
            ]
        }
        result = cards_core.lint_with_navigation(
            cfg,
            all_entity_ids=set(),
            dashboard_url_path="my_dash",
            known_view_paths={"main"},
        )
        assert result.get("bad_navigation_paths", []) == []


# ═══════════════════════════════════════════════════════════════════════════
# lovelace_cards.lint — dead entities
# ═══════════════════════════════════════════════════════════════════════════

class TestLintDeadEntities:
    def test_lint_flags_dead_entity(self):
        cfg = {
            "views": [
                {
                    "cards": [
                        {"type": "entity", "entity": "light.nonexistent"},
                    ],
                }
            ]
        }
        result = cards_core.lint(cfg, all_entity_ids={"light.kitchen"})
        assert len(result["dead_entities"]) == 1
        assert result["dead_entities"][0]["entity"] == "light.nonexistent"

    def test_lint_skips_non_entity_looking_strings(self):
        cfg = {
            "views": [
                {
                    "cards": [
                        {"type": "button", "service": "not_an_entity"},
                    ],
                }
            ]
        }
        result = cards_core.lint(cfg, all_entity_ids=set())
        # "not_an_entity" doesn't match the entity_id regex, so it's not flagged
        assert result["dead_entities"] == []

    def test_lint_unknown_card_types(self):
        cfg = {
            "views": [
                {
                    "cards": [
                        {"type": "custom:unknown-card"},
                        {"type": "entities"},
                    ],
                }
            ]
        }
        result = cards_core.lint(cfg, all_entity_ids=set(), known_card_types={"entities"})
        assert len(result["unknown_card_types"]) == 1
        assert result["unknown_card_types"][0]["card_type"] == "custom:unknown-card"

    def test_lint_no_known_card_types_skips_check(self):
        cfg = {"views": [{"cards": [{"type": "custom:unknown"}]}]}
        result = cards_core.lint(cfg, all_entity_ids=set())
        assert result["unknown_card_types"] == []

    def test_lint_entity_in_entities_list(self):
        cfg = {
            "views": [
                {
                    "cards": [
                        {
                            "type": "entities",
                            "entities": [
                                "light.exists",
                                "light.dead",
                            ],
                        },
                    ],
                }
            ]
        }
        result = cards_core.lint(cfg, all_entity_ids={"light.exists"})
        dead = [d["entity"] for d in result["dead_entities"]]
        assert "light.dead" in dead
        assert "light.exists" not in dead


# ═══════════════════════════════════════════════════════════════════════════
# lovelace_mirror.mirror
# ═══════════════════════════════════════════════════════════════════════════

class TestMirror:
    def test_mirror_dry_run_does_not_save(self):
        src_cfg = {"views": [{"path": "main", "title": "Main", "cards": []}]}
        client = MagicMock()
        with patch("cli_anything.homeassistant.core.lovelace.get_dashboard_config", return_value=src_cfg), \
             patch("cli_anything.homeassistant.core.lovelace.save_dashboard_config") as mock_save:
            result = mirror_core.mirror(
                client,
                source_url_path="src",
                dest_url_path="dest",
                dry_run=True,
            )
        assert result["saved"] is False
        assert result["dry_run"] is True
        assert result["mirrored_views"] == 1
        mock_save.assert_not_called()

    def test_mirror_saves_when_not_dry_run(self):
        src_cfg = {"views": [{"path": "main", "title": "Main", "cards": []}]}
        client = MagicMock()
        with patch("cli_anything.homeassistant.core.lovelace.get_dashboard_config", return_value=src_cfg), \
             patch("cli_anything.homeassistant.core.lovelace.save_dashboard_config") as mock_save:
            result = mirror_core.mirror(
                client,
                source_url_path="src",
                dest_url_path="dest",
                dry_run=False,
            )
        assert result["saved"] is True
        mock_save.assert_called_once()

    def test_mirror_keep_views_filters(self):
        src_cfg = {
            "views": [
                {"path": "main", "title": "Main", "cards": []},
                {"path": "other", "title": "Other", "cards": []},
            ]
        }
        client = MagicMock()
        with patch("cli_anything.homeassistant.core.lovelace.get_dashboard_config", return_value=src_cfg), \
             patch("cli_anything.homeassistant.core.lovelace.save_dashboard_config"):
            result = mirror_core.mirror(
                client,
                source_url_path="src",
                dest_url_path="dest",
                keep_views={"main"},
                dry_run=True,
            )
        assert result["mirrored_views"] == 1
        assert result["preview_cfg_views_titles"] == ["main"]

    def test_mirror_skip_views_filters(self):
        src_cfg = {
            "views": [
                {"path": "main", "title": "Main", "cards": []},
                {"path": "other", "title": "Other", "cards": []},
            ]
        }
        client = MagicMock()
        with patch("cli_anything.homeassistant.core.lovelace.get_dashboard_config", return_value=src_cfg), \
             patch("cli_anything.homeassistant.core.lovelace.save_dashboard_config"):
            result = mirror_core.mirror(
                client,
                source_url_path="src",
                dest_url_path="dest",
                skip_views={"other"},
                dry_run=True,
            )
        assert result["mirrored_views"] == 1
        assert "main" in result["preview_cfg_views_titles"]

    def test_mirror_substitutions_applied(self):
        src_cfg = {
            "views": [
                {
                    "path": "main",
                    "cards": [
                        {"type": "entity", "entity": "sensor.old_temp"},
                    ],
                }
            ]
        }
        client = MagicMock()
        saved_cfgs = []
        def capture_save(c, url, cfg, **kw):
            saved_cfgs.append(cfg)
        with patch("cli_anything.homeassistant.core.lovelace.get_dashboard_config", return_value=src_cfg), \
             patch("cli_anything.homeassistant.core.lovelace.save_dashboard_config", side_effect=capture_save):
            result = mirror_core.mirror(
                client,
                source_url_path="src",
                dest_url_path="dest",
                substitutions=[("sensor.old_", "sensor.new_")],
            )
        assert result["substitutions_applied"] == 1
        assert saved_cfgs[0]["views"][0]["cards"][0]["entity"] == "sensor.new_temp"

    def test_mirror_prune_blocked_card_types(self):
        src_cfg = {
            "views": [
                {
                    "path": "main",
                    "cards": [
                        {"type": "markdown", "content": "drop"},
                        {"type": "entities", "entities": []},
                    ],
                }
            ]
        }
        client = MagicMock()
        with patch("cli_anything.homeassistant.core.lovelace.get_dashboard_config", return_value=src_cfg), \
             patch("cli_anything.homeassistant.core.lovelace.save_dashboard_config"):
            result = mirror_core.mirror(
                client,
                source_url_path="src",
                dest_url_path="dest",
                blocked_card_types={"markdown"},
                dry_run=True,
            )
        assert result["dropped_cards"] == 1

    def test_mirror_allowed_rooms_filters_rooms_view(self):
        src_cfg = {
            "views": [
                {
                    "title": "Rooms",
                    "sections": [
                        {
                            "type": "grid",
                            "visibility": [
                                {
                                    "condition": "state",
                                    "entity": "room_selector_kitchen",
                                    "state": "kitchen",
                                },
                            ],
                        },
                        {
                            "type": "grid",
                            "visibility": [
                                {
                                    "condition": "state",
                                    "entity": "room_selector_bedroom",
                                    "state": "bedroom",
                                },
                            ],
                        },
                    ],
                }
            ]
        }
        client = MagicMock()
        with patch("cli_anything.homeassistant.core.lovelace.get_dashboard_config", return_value=src_cfg), \
             patch("cli_anything.homeassistant.core.lovelace.save_dashboard_config"):
            result = mirror_core.mirror(
                client,
                source_url_path="src",
                dest_url_path="dest",
                allowed_rooms={"kitchen"},
                dry_run=True,
            )
        assert result["mirrored_views"] == 1

    def test_substitute_replaces_in_strings(self):
        obj = {"a": "hello world", "b": ["foo", "bar"]}
        result = mirror_core._substitute(obj, [("world", "universe")])
        assert result["a"] == "hello universe"
        assert result["b"] == ["foo", "bar"]

    def test_substitute_handles_nested_structures(self):
        obj = {"a": {"b": {"c": "replace_me"}}}
        result = mirror_core._substitute(obj, [("replace_me", "done")])
        assert result["a"]["b"]["c"] == "done"

    def test_substitute_preserves_non_strings(self):
        obj = {"a": 42, "b": True, "c": None}
        result = mirror_core._substitute(obj, [("x", "y")])
        assert result == obj

    def test_section_room_keys_extracts_states(self):
        section = {
            "visibility": [
                {
                    "condition": "state",
                    "entity": "room_selector_kitchen",
                    "state": "kitchen",
                },
            ],
        }
        keys = list(mirror_core._section_room_keys(section))
        assert "kitchen" in keys

    def test_section_room_keys_ignores_non_room_selectors(self):
        section = {
            "visibility": [
                {
                    "condition": "state",
                    "entity": "sensor.temperature",
                    "state": "hot",
                },
            ],
        }
        keys = list(mirror_core._section_room_keys(section))
        assert "hot" not in keys

    def test_filter_rooms_view_non_rooms_view_unchanged(self):
        view = {"title": "Not Rooms", "sections": [{"type": "grid"}]}
        result = mirror_core._filter_rooms_view(view, {"kitchen"})
        assert result == view

    def test_filter_rooms_view_no_sections_unchanged(self):
        view = {"title": "Rooms"}
        result = mirror_core._filter_rooms_view(view, {"kitchen"})
        assert result == view


# ═══════════════════════════════════════════════════════════════════════════
# mqtt_discovery
# ═══════════════════════════════════════════════════════════════════════════

class TestMqttDiscovery:
    def test_norm_prefix_strips_trailing_slash(self):
        assert mqtt_core._norm_prefix("homeassistant/") == "homeassistant"
        assert mqtt_core._norm_prefix("homeassistant") == "homeassistant"
        assert mqtt_core._norm_prefix("homeassistant///") == "homeassistant"

    def test_list_discovered_five_part_topic(self):
        """Topic: homeassistant/<component>/<node_id>/<object_id>/config"""
        client = MagicMock()
        events = [
            {
                "topic": "homeassistant/sensor/my_node/temp_sensor/config",
                "payload": json.dumps({"name": "Temp", "unique_id": "t1"}),
            }
        ]
        with patch.object(mqtt_core, "_subscribe_collect", return_value=events):
            result = mqtt_core.list_discovered(client)
        assert len(result) == 1
        assert result[0]["component"] == "sensor"
        assert result[0]["node_id"] == "my_node"
        assert result[0]["object_id"] == "temp_sensor"
        assert result[0]["name"] == "Temp"
        assert result[0]["unique_id"] == "t1"

    def test_list_discovered_four_part_topic(self):
        """Topic: homeassistant/<component>/<object_id>/config"""
        client = MagicMock()
        events = [
            {
                "topic": "homeassistant/sensor/temp_sensor/config",
                "payload": json.dumps({"name": "Temp", "uniq_id": "t1"}),
            }
        ]
        with patch.object(mqtt_core, "_subscribe_collect", return_value=events):
            result = mqtt_core.list_discovered(client)
        assert len(result) == 1
        assert result[0]["component"] == "sensor"
        assert result[0]["node_id"] is None
        assert result[0]["object_id"] == "temp_sensor"
        assert result[0]["unique_id"] == "t1"

    def test_list_discovered_skips_malformed_topic(self):
        client = MagicMock()
        events = [
            {"topic": "homeassistant/sensor/config", "payload": "{}"},
            {"topic": "homeassistant/a/b/c/d/e/config", "payload": "{}"},
        ]
        with patch.object(mqtt_core, "_subscribe_collect", return_value=events):
            result = mqtt_core.list_discovered(client)
        assert result == []

    def test_list_discovered_handles_invalid_json_payload(self):
        client = MagicMock()
        events = [
            {
                "topic": "homeassistant/sensor/temp/config",
                "payload": "not-json",
            }
        ]
        with patch.object(mqtt_core, "_subscribe_collect", return_value=events):
            result = mqtt_core.list_discovered(client)
        assert len(result) == 1
        assert result[0]["name"] is None
        assert result[0]["unique_id"] is None

    def test_list_discovered_handles_empty_payload(self):
        client = MagicMock()
        events = [
            {
                "topic": "homeassistant/sensor/temp/config",
                "payload": "",
            }
        ]
        with patch.object(mqtt_core, "_subscribe_collect", return_value=events):
            result = mqtt_core.list_discovered(client)
        assert len(result) == 1
        assert result[0]["name"] is None

    def test_list_discovered_extracts_device_name(self):
        client = MagicMock()
        events = [
            {
                "topic": "homeassistant/sensor/temp/config",
                "payload": json.dumps({"device": {"name": "My Device"}}),
            }
        ]
        with patch.object(mqtt_core, "_subscribe_collect", return_value=events):
            result = mqtt_core.list_discovered(client)
        assert result[0]["device"] == "My Device"

    def test_show_returns_parsed_payload(self):
        client = MagicMock()
        events = [{"topic": "homeassistant/sensor/temp/config", "payload": json.dumps({"name": "T"})}]
        with patch.object(mqtt_core, "_subscribe_collect", return_value=events):
            result = mqtt_core.show(client, "homeassistant/sensor/temp/config")
        assert result == {"name": "T"}

    def test_show_returns_none_when_no_messages(self):
        client = MagicMock()
        with patch.object(mqtt_core, "_subscribe_collect", return_value=[]):
            result = mqtt_core.show(client, "homeassistant/sensor/temp/config")
        assert result is None

    def test_show_returns_raw_on_invalid_json(self):
        client = MagicMock()
        events = [{"topic": "t", "payload": "not-json"}]
        with patch.object(mqtt_core, "_subscribe_collect", return_value=events):
            result = mqtt_core.show(client, "t")
        assert result == {"raw": "not-json"}

    def test_delete_publishes_empty_retained_payload(self):
        client = MagicMock()
        client.post.return_value = {}
        mqtt_core.delete(client, "homeassistant/sensor/temp/config")
        client.post.assert_called_once()
        call_args = client.post.call_args
        path = call_args[0][0]
        payload = call_args[0][1]
        assert "services/mqtt/publish" in path
        assert payload["payload"] == ""
        assert payload["retain"] is True
        assert payload["topic"] == "homeassistant/sensor/temp/config"

    def test_republish_calls_mqtt_reload(self):
        client = MagicMock()
        client.post.return_value = {}
        mqtt_core.republish(client)
        client.post.assert_called_once()
        path = client.post.call_args[0][0]
        assert "services/mqtt/reload" in path

    def test_subscribe_collect_delivers_events(self):
        """Test _subscribe_collect with a fake client that has ws_subscribe."""
        from tests.conftest import SubscribingFakeClient

        client = SubscribingFakeClient()
        client.queue_events(
            {"topic": "homeassistant/sensor/temp/config", "payload": "{}"},
        )
        result = mqtt_core._subscribe_collect(
            client, "homeassistant/+/+/+/config", timeout=1.0
        )
        assert len(result) == 1
        assert result[0]["topic"] == "homeassistant/sensor/temp/config"

    def test_subscribe_collect_ignores_non_dict_events(self):
        from tests.conftest import SubscribingFakeClient

        client = SubscribingFakeClient()
        client.queue_events(
            "not-a-dict",
            {"topic": "t", "payload": "p"},
        )
        result = mqtt_core._subscribe_collect(client, "t", timeout=1.0)
        assert len(result) == 1
        assert result[0]["topic"] == "t"


# ═══════════════════════════════════════════════════════════════════════════
# floors
# ═══════════════════════════════════════════════════════════════════════════

class TestFloors:
    def test_list_floors_returns_list(self):
        client = MagicMock()
        client.ws_call.return_value = [{"floor_id": "f1", "name": "Ground"}]
        result = floors_core.list_floors(client)
        assert len(result) == 1
        assert result[0]["floor_id"] == "f1"

    def test_list_floors_non_list_returns_empty(self):
        client = MagicMock()
        client.ws_call.return_value = {"not": "a list"}
        assert floors_core.list_floors(client) == []

    def test_find_floor_by_id(self):
        client = MagicMock()
        client.ws_call.return_value = [{"floor_id": "f1", "name": "Ground"}, {"floor_id": "f2", "name": "First"}]
        result = floors_core.find_floor(client, "f2")
        assert result["name"] == "First"

    def test_find_floor_by_name_case_insensitive(self):
        client = MagicMock()
        client.ws_call.return_value = [{"floor_id": "f1", "name": "Ground Floor"}]
        result = floors_core.find_floor(client, "ground floor")
        assert result["floor_id"] == "f1"

    def test_find_floor_empty_ident_returns_none(self):
        client = MagicMock()
        assert floors_core.find_floor(client, "") is None

    def test_find_floor_not_found_returns_none(self):
        client = MagicMock()
        client.ws_call.return_value = [{"floor_id": "f1", "name": "Ground"}]
        assert floors_core.find_floor(client, "nonexistent") is None

    def test_create_requires_name(self):
        with pytest.raises(ValueError, match="name is required"):
            floors_core.create(MagicMock(), name="")

    def test_create_with_all_fields(self):
        client = MagicMock()
        client.ws_call.return_value = {"floor_id": "f1"}
        result = floors_core.create(
            client, name="Ground", level=0, icon="mdi:home", aliases=["g"]
        )
        assert result["floor_id"] == "f1"
        payload = client.ws_call.call_args[0][1]
        assert payload["name"] == "Ground"
        assert payload["level"] == 0
        assert payload["icon"] == "mdi:home"
        assert payload["aliases"] == ["g"]

    def test_create_minimal(self):
        client = MagicMock()
        client.ws_call.return_value = {"floor_id": "f1"}
        floors_core.create(client, name="Ground")
        payload = client.ws_call.call_args[0][1]
        assert payload == {"name": "Ground"}

    def test_create_returns_empty_dict_on_none(self):
        client = MagicMock()
        client.ws_call.return_value = None
        result = floors_core.create(client, name="Ground")
        assert result == {}

    def test_update_requires_floor_id(self):
        with pytest.raises(ValueError, match="floor_id is required"):
            floors_core.update(MagicMock(), floor_id="")

    def test_update_with_all_fields(self):
        client = MagicMock()
        client.ws_call.return_value = {"floor_id": "f1"}
        floors_core.update(
            client, "f1", name="New", level=1, icon="mdi:home", aliases=["a"]
        )
        payload = client.ws_call.call_args[0][1]
        assert payload["floor_id"] == "f1"
        assert payload["name"] == "New"
        assert payload["level"] == 1
        assert payload["icon"] == "mdi:home"
        assert payload["aliases"] == ["a"]

    def test_update_returns_empty_dict_on_none(self):
        client = MagicMock()
        client.ws_call.return_value = None
        result = floors_core.update(client, "f1", name="New")
        assert result == {}

    def test_delete_requires_floor_id(self):
        with pytest.raises(ValueError, match="floor_id is required"):
            floors_core.delete(MagicMock(), floor_id="")

    def test_delete_calls_ws(self):
        client = MagicMock()
        client.ws_call.return_value = {"ok": True}
        result = floors_core.delete(client, "f1")
        assert result == {"ok": True}
        payload = client.ws_call.call_args[0][1]
        assert payload == {"floor_id": "f1"}


# ═══════════════════════════════════════════════════════════════════════════
# labels
# ═══════════════════════════════════════════════════════════════════════════

class TestLabels:
    def test_list_labels_returns_list(self):
        client = MagicMock()
        client.ws_call.return_value = [{"label_id": "l1", "name": "Guest"}]
        result = labels_core.list_labels(client)
        assert len(result) == 1

    def test_list_labels_non_list_returns_empty(self):
        client = MagicMock()
        client.ws_call.return_value = "not a list"
        assert labels_core.list_labels(client) == []

    def test_find_label_by_id(self):
        client = MagicMock()
        client.ws_call.return_value = [{"label_id": "l1", "name": "Guest"}, {"label_id": "l2", "name": "VIP"}]
        result = labels_core.find_label(client, "l2")
        assert result["name"] == "VIP"

    def test_find_label_by_name_case_insensitive(self):
        client = MagicMock()
        client.ws_call.return_value = [{"label_id": "l1", "name": "Guest Mode"}]
        result = labels_core.find_label(client, "guest mode")
        assert result["label_id"] == "l1"

    def test_find_label_empty_returns_none(self):
        assert labels_core.find_label(MagicMock(), "") is None

    def test_find_label_not_found(self):
        client = MagicMock()
        client.ws_call.return_value = [{"label_id": "l1", "name": "Guest"}]
        assert labels_core.find_label(client, "nonexistent") is None

    def test_create_requires_name(self):
        with pytest.raises(ValueError, match="name is required"):
            labels_core.create(MagicMock(), name="")

    def test_create_with_all_fields(self):
        client = MagicMock()
        client.ws_call.return_value = {"label_id": "l1"}
        labels_core.create(client, name="Guest", color="red", icon="mdi:tag", description="desc")
        payload = client.ws_call.call_args[0][1]
        assert payload == {"name": "Guest", "color": "red", "icon": "mdi:tag", "description": "desc"}

    def test_create_minimal(self):
        client = MagicMock()
        client.ws_call.return_value = {"label_id": "l1"}
        labels_core.create(client, name="Guest")
        payload = client.ws_call.call_args[0][1]
        assert payload == {"name": "Guest"}

    def test_create_returns_empty_dict_on_none(self):
        client = MagicMock()
        client.ws_call.return_value = None
        assert labels_core.create(client, name="Guest") == {}

    def test_update_requires_label_id(self):
        with pytest.raises(ValueError, match="label_id is required"):
            labels_core.update(MagicMock(), label_id="")

    def test_update_with_all_fields(self):
        client = MagicMock()
        client.ws_call.return_value = {"label_id": "l1"}
        labels_core.update(client, "l1", name="New", color="blue", icon="mdi:x", description="d")
        payload = client.ws_call.call_args[0][1]
        assert payload["label_id"] == "l1"
        assert payload["name"] == "New"
        assert payload["color"] == "blue"

    def test_update_returns_empty_dict_on_none(self):
        client = MagicMock()
        client.ws_call.return_value = None
        assert labels_core.update(client, "l1", name="New") == {}

    def test_delete_requires_label_id(self):
        with pytest.raises(ValueError, match="label_id is required"):
            labels_core.delete(MagicMock(), label_id="")

    def test_delete_calls_ws(self):
        client = MagicMock()
        client.ws_call.return_value = {"ok": True}
        result = labels_core.delete(client, "l1")
        assert result == {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# persons
# ═══════════════════════════════════════════════════════════════════════════

class TestPersons:
    def test_envelope_plain_list(self):
        data = [{"id": "p1", "name": "Alice"}]
        result = persons_core._envelope(data)
        assert len(result) == 1
        assert result[0]["name"] == "Alice"

    def test_envelope_storage_config_collections(self):
        data = {
            "storage_collection": [{"id": "p1", "name": "Alice"}],
            "config_collection": [{"id": "p2", "name": "Bob"}],
        }
        result = persons_core._envelope(data)
        assert len(result) == 2
        sources = {p["_source"] for p in result}
        assert sources == {"storage", "config"}

    def test_envelope_new_shape_storage_config(self):
        data = {
            "storage": [{"id": "p1", "name": "Alice"}],
            "config": [{"id": "p2", "name": "Bob"}],
        }
        result = persons_core._envelope(data)
        assert len(result) == 2

    def test_envelope_persons_fallback(self):
        data = {"persons": [{"id": "p1", "name": "Alice"}]}
        result = persons_core._envelope(data)
        assert len(result) == 1
        assert result[0]["name"] == "Alice"

    def test_envelope_empty_dict(self):
        assert persons_core._envelope({}) == []

    def test_envelope_non_dict_non_list(self):
        assert persons_core._envelope("string") == []
        assert persons_core._envelope(42) == []
        assert persons_core._envelope(None) == []

    def test_list_persons(self):
        client = MagicMock()
        client.ws_call.return_value = [{"id": "p1", "name": "Alice"}]
        result = persons_core.list_persons(client)
        assert len(result) == 1

    def test_find_person_by_id(self):
        client = MagicMock()
        client.ws_call.return_value = [{"id": "p1", "name": "Alice"}, {"id": "p2", "name": "Bob"}]
        result = persons_core.find_person(client, "p2")
        assert result["name"] == "Bob"

    def test_find_person_by_name_case_insensitive(self):
        client = MagicMock()
        client.ws_call.return_value = [{"id": "p1", "name": "Alice"}]
        result = persons_core.find_person(client, "alice")
        assert result["id"] == "p1"

    def test_find_person_empty_returns_none(self):
        assert persons_core.find_person(MagicMock(), "") is None

    def test_find_person_not_found(self):
        client = MagicMock()
        client.ws_call.return_value = [{"id": "p1", "name": "Alice"}]
        assert persons_core.find_person(client, "nonexistent") is None

    def test_create_requires_name(self):
        with pytest.raises(ValueError, match="name is required"):
            persons_core.create(MagicMock(), name="")

    def test_create_with_all_fields(self):
        client = MagicMock()
        client.ws_call.return_value = {"id": "p1"}
        persons_core.create(
            client, name="Alice", user_id="u1", device_trackers=["dt1"], picture="/pic.jpg"
        )
        payload = client.ws_call.call_args[0][1]
        assert payload["name"] == "Alice"
        assert payload["user_id"] == "u1"
        assert payload["device_trackers"] == ["dt1"]
        assert payload["picture"] == "/pic.jpg"

    def test_create_minimal(self):
        client = MagicMock()
        client.ws_call.return_value = {"id": "p1"}
        persons_core.create(client, name="Alice")
        payload = client.ws_call.call_args[0][1]
        assert payload == {"name": "Alice"}

    def test_create_returns_empty_dict_on_none(self):
        client = MagicMock()
        client.ws_call.return_value = None
        assert persons_core.create(client, name="Alice") == {}

    def test_update_requires_person_id(self):
        with pytest.raises(ValueError, match="person_id is required"):
            persons_core.update(MagicMock(), person_id="")

    def test_update_with_all_fields(self):
        client = MagicMock()
        client.ws_call.return_value = {"id": "p1"}
        persons_core.update(client, "p1", name="New", user_id="u2", device_trackers=["dt2"], picture="/p.jpg")
        payload = client.ws_call.call_args[0][1]
        assert payload["person_id"] == "p1"
        assert payload["name"] == "New"
        assert payload["user_id"] == "u2"

    def test_update_returns_empty_dict_on_none(self):
        client = MagicMock()
        client.ws_call.return_value = None
        assert persons_core.update(client, "p1", name="New") == {}

    def test_delete_requires_person_id(self):
        with pytest.raises(ValueError, match="person_id is required"):
            persons_core.delete(MagicMock(), person_id="")

    def test_delete_calls_ws(self):
        client = MagicMock()
        client.ws_call.return_value = {"ok": True}
        result = persons_core.delete(client, "p1")
        assert result == {"ok": True}
        payload = client.ws_call.call_args[0][1]
        assert payload == {"person_id": "p1"}


# ═══════════════════════════════════════════════════════════════════════════
# lovelace_card_types
# ═══════════════════════════════════════════════════════════════════════════

class TestCardTypes:
    def test_card_types_in_use_counts_types(self):
        cfg = {
            "views": [
                {
                    "cards": [
                        {"type": "markdown"},
                        {"type": "markdown"},
                        {"type": "entities"},
                    ],
                }
            ]
        }
        result = card_types_core.card_types_in_use(cfg)
        assert result == {"markdown": 2, "entities": 1}

    def test_card_types_in_use_empty_config(self):
        assert card_types_core.card_types_in_use({}) == {}

    def test_card_types_in_use_nested_stacks(self):
        cfg = {
            "views": [
                {
                    "cards": [
                        {
                            "type": "horizontal-stack",
                            "cards": [
                                {"type": "markdown"},
                                {"type": "button"},
                            ],
                        },
                    ],
                }
            ]
        }
        result = card_types_core.card_types_in_use(cfg)
        assert result["horizontal-stack"] == 1
        assert result["markdown"] == 1
        assert result["button"] == 1

    def test_card_types_in_use_skips_cards_without_type(self):
        cfg = {"views": [{"cards": [{"content": "no type"}]}]}
        result = card_types_core.card_types_in_use(cfg)
        assert result == {}

    def test_custom_types_only_filters_custom_prefix(self):
        types = ["custom:my-card", "entities", "custom:other-card", "markdown"]
        result = card_types_core.custom_types_only(types)
        assert result == ["custom:my-card", "custom:other-card"]

    def test_custom_types_only_empty(self):
        assert card_types_core.custom_types_only([]) == []

    def test_cross_reference_hacs_matches_by_token_overlap(self):
        client = MagicMock()
        with patch("cli_anything.homeassistant.core.hacs.list_repos") as mock_hacs:
            mock_hacs.return_value = [
                {
                    "id": "1",
                    "full_name": "hacs/lovelace-clock-card",
                    "name": "Clock Card",
                    "installed": True,
                },
            ]
            result = card_types_core.cross_reference_hacs(client, ["custom:clock-card"])
        assert "custom:clock-card" in result
        entry = result["custom:clock-card"]
        assert entry["plugin"] is not None
        assert entry["installed"] is True
        assert entry["score"] >= 1

    def test_cross_reference_hacs_no_match_returns_none_plugin(self):
        client = MagicMock()
        with patch("cli_anything.homeassistant.core.hacs.list_repos") as mock_hacs:
            mock_hacs.return_value = [
                {
                    "id": "1",
                    "full_name": "hacs/something-unrelated",
                    "name": "Unrelated",
                    "installed": True,
                },
            ]
            result = card_types_core.cross_reference_hacs(client, ["custom:totally-different"])
        entry = result["custom:totally-different"]
        assert entry["plugin"] is None
        assert entry["installed"] is False

    def test_cross_reference_hacs_handles_hacs_error(self):
        client = MagicMock()
        with patch("cli_anything.homeassistant.core.hacs.list_repos", side_effect=RuntimeError("HA error")):
            result = card_types_core.cross_reference_hacs(client, ["custom:clock-card"])
        assert "_error" in result
        assert "HA error" in result["_error"]

    def test_cross_reference_hacs_skips_non_custom_types(self):
        client = MagicMock()
        with patch("cli_anything.homeassistant.core.hacs.list_repos") as mock_hacs:
            mock_hacs.return_value = []
            result = card_types_core.cross_reference_hacs(client, ["entities", "custom:my-card"])
        # Only custom:my-card should be in the output
        assert "custom:my-card" in result
        assert "entities" not in result

    def test_types_across_dashboards(self):
        client = MagicMock()
        # list_dashboards returns storage dashboards
        client.ws_call.return_value = []
        # get_dashboard_config returns config with cards
        client.get.return_value = {
            "views": [{"cards": [{"type": "markdown"}, {"type": "entities"}]}]
        }
        with patch("cli_anything.homeassistant.core.lovelace.list_dashboards") as mock_list, \
             patch("cli_anything.homeassistant.core.lovelace.get_dashboard_config") as mock_get:
            mock_list.return_value = [{"url_path": "dash1"}, {"url_path": "dash1"}]
            mock_get.return_value = {"views": [{"cards": [{"type": "markdown"}]}]}
            result = card_types_core.types_across_dashboards(client)
        # dash1 should appear (deduped), plus default
        assert "dash1" in result
        assert "(default)" in result


# ═══════════════════════════════════════════════════════════════════════════
# inspect_entity
# ═══════════════════════════════════════════════════════════════════════════

class TestInspectEntity:
    def test_inspect_entity_invalid_id_raises(self):
        with pytest.raises(ValueError, match="domain.object"):
            inspect_core.inspect_entity(MagicMock(), "invalid")

    def test_inspect_entity_empty_id_raises(self):
        with pytest.raises(ValueError, match="domain.object"):
            inspect_core.inspect_entity(MagicMock(), "")

    def test_inspect_entity_basic(self):
        client = MagicMock()
        client.get.return_value = {"state": "on", "attributes": {}}
        with patch("cli_anything.homeassistant.core.states.get_state", return_value={"state": "on"}), \
             patch("cli_anything.homeassistant.core.registry.list_entities", return_value=[]), \
             patch("cli_anything.homeassistant.core.registry.list_devices", return_value=[]), \
             patch("cli_anything.homeassistant.core.registry.list_areas", return_value=[]), \
             patch("cli_anything.homeassistant.core.references.find_references", return_value={"cards": []}):
            result = inspect_core.inspect_entity(client, "light.kitchen")
        assert result["entity_id"] == "light.kitchen"
        assert result["state"] == {"state": "on"}
        assert result["registry"] is None
        assert result["device"] is None
        assert result["area"] is None
        assert result["references"] == {"cards": []}

    def test_inspect_entity_with_registry_and_device(self):
        client = MagicMock()
        reg_row = {"entity_id": "light.kitchen", "device_id": "dev1", "area_id": "area1"}
        device_row = {"id": "dev1", "name": "Kitchen Device", "area_id": "area1"}
        area_row = {"area_id": "area1", "name": "Kitchen"}
        with patch("cli_anything.homeassistant.core.states.get_state", return_value={"state": "on"}), \
             patch("cli_anything.homeassistant.core.registry.list_entities", return_value=[reg_row]), \
             patch("cli_anything.homeassistant.core.registry.list_devices", return_value=[device_row]), \
             patch("cli_anything.homeassistant.core.registry.list_areas", return_value=[area_row]), \
             patch("cli_anything.homeassistant.core.references.find_references", return_value={}):
            result = inspect_core.inspect_entity(client, "light.kitchen")
        assert result["registry"]["entity_id"] == "light.kitchen"
        assert result["device"]["id"] == "dev1"
        assert result["area"]["name"] == "Kitchen"

    def test_inspect_entity_with_history(self):
        client = MagicMock()
        with patch("cli_anything.homeassistant.core.states.get_state", return_value={"state": "on"}), \
             patch("cli_anything.homeassistant.core.registry.list_entities", return_value=[]), \
             patch("cli_anything.homeassistant.core.registry.list_devices", return_value=[]), \
             patch("cli_anything.homeassistant.core.registry.list_areas", return_value=[]), \
             patch("cli_anything.homeassistant.core.history.history", return_value=[{"state": "on"}]), \
             patch("cli_anything.homeassistant.core.references.find_references", return_value={}):
            result = inspect_core.inspect_entity(
                client, "light.kitchen", include_history=True, history_hours=12
            )
        assert result["history"] == [{"state": "on"}]

    def test_inspect_entity_state_error_captured(self):
        client = MagicMock()
        with patch("cli_anything.homeassistant.core.states.get_state", side_effect=RuntimeError("HA down")), \
             patch("cli_anything.homeassistant.core.registry.list_entities", return_value=[]), \
             patch("cli_anything.homeassistant.core.registry.list_devices", return_value=[]), \
             patch("cli_anything.homeassistant.core.registry.list_areas", return_value=[]), \
             patch("cli_anything.homeassistant.core.references.find_references", return_value={}):
            result = inspect_core.inspect_entity(client, "light.kitchen")
        assert "error" in result["state"]
        assert "HA down" in result["state"]["error"]

    def test_inspect_entity_references_error_captured(self):
        client = MagicMock()
        with patch("cli_anything.homeassistant.core.states.get_state", return_value={"state": "on"}), \
             patch("cli_anything.homeassistant.core.registry.list_entities", return_value=[]), \
             patch("cli_anything.homeassistant.core.registry.list_devices", return_value=[]), \
             patch("cli_anything.homeassistant.core.registry.list_areas", return_value=[]), \
             patch("cli_anything.homeassistant.core.references.find_references", side_effect=RuntimeError("ref error")):
            result = inspect_core.inspect_entity(client, "light.kitchen")
        assert "error" in result["references"]
        assert "ref error" in result["references"]["error"]

    def test_inspect_entity_device_from_device_area_id(self):
        """When registry has no area_id but device does, area should come from device."""
        client = MagicMock()
        reg_row = {"entity_id": "light.kitchen", "device_id": "dev1", "area_id": None}
        device_row = {"id": "dev1", "name": "Kitchen Device", "area_id": "area1"}
        area_row = {"area_id": "area1", "name": "Kitchen"}
        with patch("cli_anything.homeassistant.core.states.get_state", return_value={"state": "on"}), \
             patch("cli_anything.homeassistant.core.registry.list_entities", return_value=[reg_row]), \
             patch("cli_anything.homeassistant.core.registry.list_devices", return_value=[device_row]), \
             patch("cli_anything.homeassistant.core.registry.list_areas", return_value=[area_row]), \
             patch("cli_anything.homeassistant.core.references.find_references", return_value={}):
            result = inspect_core.inspect_entity(client, "light.kitchen")
        assert result["area"]["name"] == "Kitchen"

    def test_inspect_entity_skip_references(self):
        client = MagicMock()
        with patch("cli_anything.homeassistant.core.states.get_state", return_value={"state": "on"}), \
             patch("cli_anything.homeassistant.core.registry.list_entities", return_value=[]), \
             patch("cli_anything.homeassistant.core.registry.list_devices", return_value=[]), \
             patch("cli_anything.homeassistant.core.registry.list_areas", return_value=[]), \
             patch("cli_anything.homeassistant.core.references.find_references") as mock_refs:
            result = inspect_core.inspect_entity(
                client, "light.kitchen", include_references=False
            )
        mock_refs.assert_not_called()
        assert "references" not in result
