"""Tests for low-coverage core modules with real logic.

Covers error paths, edge cases, and branches in:
  - hacs.py (repo resolution, validation, CRUD)
  - domain.py (controllable-domain validation, service call wiring)
  - lovelace_sections.py (section CRUD, validation, index clamping)
  - lovelace_badges.py (badge CRUD, validation, index clamping)
  - themes.py (theme listing, set with mode validation)
  - groups.py (template-based expansion, parsing)
  - diagnostics.py (handler listing, file saving)
  - history.py (param building, timezone handling)
  - inspect.py (entity inspection aggregation, error handling)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from cli_anything.homeassistant.core import (
    diagnostics,
    domain,
    groups,
    hacs,
    history,
    inspect,
    lovelace_badges,
    lovelace_sections,
    themes,
)


# ──────────────────────────────────────────────────────────────  hacs.py


class TestHacsInfo:
    def test_info_returns_dict(self, fake_client):
        fake_client.set_ws("hacs/info", {"version": "2.0", "stage": "running"})
        result = hacs.info(fake_client)
        assert result["version"] == "2.0"

    def test_info_returns_empty_dict_when_no_response(self, fake_client):
        result = hacs.info(fake_client)
        assert result == {}

    def test_hacs_info_alias(self, fake_client):
        """hacs_info should be the same callable as info."""
        assert hacs.hacs_info is hacs.info


class TestHacsListRepos:
    def test_list_all(self, fake_client):
        fake_client.set_ws(
            "hacs/repositories/list",
            [
                {"id": 1, "full_name": "a/b", "installed": True, "category": "integration"},
                {"id": 2, "full_name": "c/d", "installed": False, "category": "plugin"},
            ],
        )
        result = hacs.list_repos(fake_client)
        assert len(result) == 2

    def test_list_installed_only(self, fake_client):
        fake_client.set_ws(
            "hacs/repositories/list",
            [
                {"id": 1, "full_name": "a/b", "installed": True},
                {"id": 2, "full_name": "c/d", "installed": False},
            ],
        )
        result = hacs.list_repos(fake_client, installed_only=True)
        assert len(result) == 1
        assert result[0]["full_name"] == "a/b"

    def test_list_by_category(self, fake_client):
        fake_client.set_ws(
            "hacs/repositories/list",
            [
                {"id": 1, "full_name": "a/b", "category": "integration"},
                {"id": 2, "full_name": "c/d", "category": "plugin"},
            ],
        )
        result = hacs.list_repos(fake_client, category="plugin")
        assert len(result) == 1
        assert result[0]["full_name"] == "c/d"

    def test_list_by_pattern(self, fake_client):
        fake_client.set_ws(
            "hacs/repositories/list",
            [
                {"id": 1, "full_name": "hacs/integration", "name": "HACS"},
                {"id": 2, "full_name": "other/repo", "name": "Other"},
            ],
        )
        result = hacs.list_repos(fake_client, pattern="hacs")
        assert len(result) == 1
        assert result[0]["full_name"] == "hacs/integration"

    def test_list_returns_empty_when_non_list_response(self, fake_client):
        fake_client.set_ws("hacs/repositories/list", {"not": "a list"})
        result = hacs.list_repos(fake_client)
        assert result == []


class TestHacsFindRepo:
    def test_find_by_id(self, fake_client):
        fake_client.set_ws(
            "hacs/repositories/list",
            [
                {"id": 42, "full_name": "a/b"},
                {"id": 99, "full_name": "c/d"},
            ],
        )
        result = hacs.find_repo(fake_client, "42")
        assert result["full_name"] == "a/b"

    def test_find_by_full_name_case_insensitive(self, fake_client):
        fake_client.set_ws(
            "hacs/repositories/list",
            [
                {"id": 1, "full_name": "User/Repo"},
            ],
        )
        result = hacs.find_repo(fake_client, "user/repo")
        assert result["id"] == 1

    def test_find_by_short_name_unique(self, fake_client):
        fake_client.set_ws(
            "hacs/repositories/list",
            [
                {"id": 1, "full_name": "user/myrepo"},
                {"id": 2, "full_name": "other/different"},
            ],
        )
        result = hacs.find_repo(fake_client, "myrepo")
        assert result["id"] == 1

    def test_find_by_short_name_ambiguous_raises(self, fake_client):
        fake_client.set_ws(
            "hacs/repositories/list",
            [
                {"id": 1, "full_name": "user/myrepo"},
                {"id": 2, "full_name": "other/myrepo"},
            ],
        )
        with pytest.raises(ValueError, match="matches multiple repos"):
            hacs.find_repo(fake_client, "myrepo")

    def test_find_by_substring_installed_unique(self, fake_client):
        fake_client.set_ws(
            "hacs/repositories/list",
            [
                {"id": 1, "full_name": "user/special-repo", "installed": True},
                {"id": 2, "full_name": "other/normal", "installed": True},
            ],
        )
        result = hacs.find_repo(fake_client, "special")
        assert result["id"] == 1

    def test_find_returns_none_for_empty_ident(self, fake_client):
        result = hacs.find_repo(fake_client, "")
        assert result is None

    def test_find_returns_none_when_no_match(self, fake_client):
        fake_client.set_ws(
            "hacs/repositories/list",
            [
                {"id": 1, "full_name": "a/b", "installed": True},
            ],
        )
        result = hacs.find_repo(fake_client, "nonexistent")
        assert result is None

    def test_find_returns_none_when_response_not_list(self, fake_client):
        fake_client.set_ws("hacs/repositories/list", {"bad": True})
        result = hacs.find_repo(fake_client, "anything")
        assert result is None

    def test_find_substring_ambiguous_returns_none(self, fake_client):
        """When substring matches multiple installed repos, return None (not raise)."""
        fake_client.set_ws(
            "hacs/repositories/list",
            [
                {"id": 1, "full_name": "user/special-a", "installed": True},
                {"id": 2, "full_name": "other/special-b", "installed": True},
            ],
        )
        result = hacs.find_repo(fake_client, "special")
        assert result is None


class TestHacsAddRepo:
    def test_add_valid_repo(self, fake_client):
        fake_client.set_ws("hacs/repositories/add", {"ok": True})
        result = hacs.add_repo(fake_client, "owner/repo", category="integration")
        assert result == {"ok": True}
        assert fake_client.ws_calls[-1]["payload"] == {
            "repository": "owner/repo",
            "category": "integration",
        }

    def test_add_repo_invalid_slug_no_slash(self, fake_client):
        with pytest.raises(ValueError, match="owner/repo"):
            hacs.add_repo(fake_client, "noslash")

    def test_add_repo_invalid_slug_two_slashes(self, fake_client):
        with pytest.raises(ValueError, match="owner/repo"):
            hacs.add_repo(fake_client, "a/b/c")

    def test_add_repo_invalid_slug_leading_slash(self, fake_client):
        with pytest.raises(ValueError, match="owner/repo"):
            hacs.add_repo(fake_client, "/leading")

    def test_add_repo_invalid_slug_trailing_slash(self, fake_client):
        with pytest.raises(ValueError, match="owner/repo"):
            hacs.add_repo(fake_client, "trailing/")

    def test_add_repo_invalid_category(self, fake_client):
        with pytest.raises(ValueError, match="category must be one of"):
            hacs.add_repo(fake_client, "owner/repo", category="bogus")


class TestHacsShowInstallRemoveRefresh:
    def test_show_returns_repo(self, fake_client):
        fake_client.set_ws(
            "hacs/repositories/list",
            [
                {"id": 1, "full_name": "a/b"},
            ],
        )
        result = hacs.show(fake_client, "a/b")
        assert result["id"] == 1

    def test_show_raises_keyerror_when_not_found(self, fake_client):
        fake_client.set_ws("hacs/repositories/list", [])
        with pytest.raises(KeyError, match="no HACS repo"):
            hacs.show(fake_client, "nonexistent")

    def test_install_sends_download_with_id(self, fake_client):
        fake_client.set_ws(
            "hacs/repositories/list",
            [
                {"id": 42, "full_name": "a/b"},
            ],
        )
        fake_client.set_ws("hacs/repository/download", {"ok": True})
        result = hacs.install(fake_client, "a/b")
        assert result == {"ok": True}
        assert fake_client.ws_calls[-1]["payload"] == {"repository": "42"}

    def test_install_with_version(self, fake_client):
        fake_client.set_ws(
            "hacs/repositories/list",
            [
                {"id": 42, "full_name": "a/b"},
            ],
        )
        fake_client.set_ws("hacs/repository/download", {"ok": True})
        hacs.install(fake_client, "a/b", version="1.0.0")
        assert fake_client.ws_calls[-1]["payload"] == {"repository": "42", "version": "1.0.0"}

    def test_install_raises_keyerror_when_not_found(self, fake_client):
        fake_client.set_ws("hacs/repositories/list", [])
        with pytest.raises(KeyError):
            hacs.install(fake_client, "nonexistent")

    def test_remove_sends_remove_with_id(self, fake_client):
        fake_client.set_ws(
            "hacs/repositories/list",
            [
                {"id": 42, "full_name": "a/b"},
            ],
        )
        fake_client.set_ws("hacs/repository/remove", {"ok": True})
        result = hacs.remove(fake_client, "a/b")
        assert result == {"ok": True}
        assert fake_client.ws_calls[-1]["payload"] == {"repository": "42"}

    def test_refresh_sends_refresh_with_id(self, fake_client):
        fake_client.set_ws(
            "hacs/repositories/list",
            [
                {"id": 42, "full_name": "a/b"},
            ],
        )
        fake_client.set_ws("hacs/repository/refresh", {"ok": True})
        result = hacs.refresh(fake_client, "a/b")
        assert result == {"ok": True}
        assert fake_client.ws_calls[-1]["payload"] == {"repository": "42"}


# ──────────────────────────────────────────────────────────────  domain.py


class TestDomain:
    def test_turn_on_valid_domain(self, fake_client):
        fake_client.set_service("light", "turn_on", {"ok": True})
        result = domain.turn_on(fake_client, "light", "light.lamp")
        assert result == {"ok": True}
        assert fake_client.service_calls[-1]["domain"] == "light"
        assert fake_client.service_calls[-1]["service"] == "turn_on"

    def test_turn_on_invalid_domain_raises(self, fake_client):
        with pytest.raises(ValueError, match="not a known controllable domain"):
            domain.turn_on(fake_client, "bogus_domain", "bogus.x")

    def test_turn_off_valid_domain(self, fake_client):
        fake_client.set_service("switch", "turn_off", {"ok": True})
        result = domain.turn_off(fake_client, "switch", "switch.outlet")
        assert result == {"ok": True}

    def test_turn_off_invalid_domain_raises(self, fake_client):
        with pytest.raises(ValueError, match="not a known controllable domain"):
            domain.turn_off(fake_client, "sensor", "sensor.temp")

    def test_toggle_valid_domain(self, fake_client):
        fake_client.set_service("fan", "toggle", {"ok": True})
        result = domain.toggle(fake_client, "fan", "fan.ceiling")
        assert result == {"ok": True}

    def test_toggle_invalid_domain_raises(self, fake_client):
        with pytest.raises(ValueError, match="not a known controllable domain"):
            domain.toggle(fake_client, "zone", "zone.x")

    def test_turn_on_without_entity_id(self, fake_client):
        """When entity_id is None, target should be None."""
        fake_client.set_service("light", "turn_on", {"ok": True})
        domain.turn_on(fake_client, "light")
        # The service call should have been made with no target
        assert fake_client.service_calls[-1]["domain"] == "light"

    def test_turn_on_with_extra_data(self, fake_client):
        fake_client.set_service("light", "turn_on", {"ok": True})
        domain.turn_on(fake_client, "light", "light.lamp", extra={"brightness": 128})
        assert fake_client.service_calls[-1]["service_data"]["brightness"] == 128

    def test_list_entities(self, fake_client):
        fake_client.set(
            "GET",
            "states",
            [
                {"entity_id": "light.lamp", "state": "on"},
                {"entity_id": "switch.outlet", "state": "off"},
            ],
        )
        result = domain.list_entities(fake_client, "light")
        assert len(result) == 1
        assert result[0]["entity_id"] == "light.lamp"


# ──────────────────────────────────────────────────────────────  lovelace_sections.py


def _sections_config():
    return {
        "views": [
            {
                "path": "home",
                "type": "sections",
                "sections": [
                    {"type": "grid", "cards": [{"type": "entities"}]},
                    {"type": "grid", "cards": [{"type": "markdown"}]},
                ],
            },
            {"path": "masonry", "type": "masonry", "cards": []},
        ]
    }


class TestLovelaceSections:
    def test_list_sections(self):
        config = _sections_config()
        result = lovelace_sections.list_sections(config, "home")
        assert len(result) == 2

    def test_list_sections_empty(self):
        config = {"views": [{"path": "home", "type": "sections", "sections": []}]}
        assert lovelace_sections.list_sections(config, "home") == []

    def test_add_section_basic(self):
        config = _sections_config()
        section = lovelace_sections.add_section(config, "home")
        assert section["type"] == "grid"
        assert section["cards"] == []
        assert len(config["views"][0]["sections"]) == 3

    def test_add_section_with_cards(self):
        config = _sections_config()
        cards = [{"type": "entities"}, {"type": "markdown"}]
        section = lovelace_sections.add_section(config, "home", cards=cards)
        assert len(section["cards"]) == 2

    def test_add_section_with_header(self):
        config = _sections_config()
        header = {"title": "My Section"}
        section = lovelace_sections.add_section(config, "home", header=header)
        assert section["header"] == header

    def test_add_section_with_title_creates_heading_card(self):
        config = _sections_config()
        section = lovelace_sections.add_section(config, "home", title="Hello")
        assert section["cards"][0]["type"] == "heading"
        assert section["cards"][0]["heading"] == "Hello"

    def test_add_section_title_and_header_mutually_exclusive(self):
        config = _sections_config()
        with pytest.raises(ValueError, match="not both"):
            lovelace_sections.add_section(config, "home", title="X", header={})

    def test_add_section_header_not_dict_raises(self):
        config = _sections_config()
        with pytest.raises(ValueError, match="header must be a dict"):
            lovelace_sections.add_section(config, "home", header="not a dict")

    def test_add_section_non_sections_view_raises(self):
        config = _sections_config()
        with pytest.raises(ValueError, match="not a sections view"):
            lovelace_sections.add_section(config, "masonry")

    def test_add_section_with_column_span(self):
        config = _sections_config()
        section = lovelace_sections.add_section(config, "home", column_span=2)
        assert section["column_span"] == 2

    def test_add_section_with_row_span(self):
        config = _sections_config()
        section = lovelace_sections.add_section(config, "home", row_span=3)
        assert section["row_span"] == 3

    def test_add_section_with_visibility(self):
        config = _sections_config()
        vis = [{"condition": "state", "entity": "input_boolean.show"}]
        section = lovelace_sections.add_section(config, "home", visibility=vis)
        assert section["visibility"] == vis

    def test_add_section_at_index(self):
        config = _sections_config()
        lovelace_sections.add_section(config, "home", index=0)
        assert len(config["views"][0]["sections"]) == 3
        # New section should be at index 0
        assert config["views"][0]["sections"][0]["cards"] == []

    def test_add_section_index_clamped(self):
        """Index beyond the end should be clamped to the end."""
        config = _sections_config()
        lovelace_sections.add_section(config, "home", index=999)
        assert len(config["views"][0]["sections"]) == 3
        # New section should be at the end
        assert config["views"][0]["sections"][-1]["cards"] == []

    def test_delete_section(self):
        config = _sections_config()
        lovelace_sections.delete_section(config, "home", 0)
        assert len(config["views"][0]["sections"]) == 1
        # The remaining section should be the markdown one
        assert config["views"][0]["sections"][0]["cards"][0]["type"] == "markdown"

    def test_delete_section_out_of_range_raises(self):
        config = _sections_config()
        with pytest.raises(IndexError, match="out of range"):
            lovelace_sections.delete_section(config, "home", 99)

    def test_delete_section_negative_raises(self):
        config = _sections_config()
        with pytest.raises(IndexError, match="out of range"):
            lovelace_sections.delete_section(config, "home", -1)

    def test_delete_section_no_sections_list_raises(self):
        config = {"views": [{"path": "home", "type": "sections"}]}
        with pytest.raises(ValueError, match="no sections list"):
            lovelace_sections.delete_section(config, "home", 0)

    def test_move_section(self):
        config = _sections_config()
        lovelace_sections.move_section(config, "home", 0, 1)
        # The first section should now be the markdown one
        assert config["views"][0]["sections"][0]["cards"][0]["type"] == "markdown"
        assert config["views"][0]["sections"][1]["cards"][0]["type"] == "entities"

    def test_move_section_out_of_range_raises(self):
        config = _sections_config()
        with pytest.raises(IndexError, match="out of range"):
            lovelace_sections.move_section(config, "home", 0, 99)

    def test_move_section_negative_new_index_raises(self):
        config = _sections_config()
        with pytest.raises(IndexError, match="out of range"):
            lovelace_sections.move_section(config, "home", 0, -1)

    def test_move_section_no_sections_list_raises(self):
        config = {"views": [{"path": "home", "type": "sections"}]}
        with pytest.raises(ValueError, match="no sections list"):
            lovelace_sections.move_section(config, "home", 0, 0)


# ──────────────────────────────────────────────────────────────  lovelace_badges.py


def _badges_config():
    return {
        "views": [
            {"path": "home", "badges": ["sensor.temp", "sensor.humidity"]},
            {"path": "other", "badges": []},
        ]
    }


class TestLovelaceBadges:
    def test_list_badges(self):
        config = _badges_config()
        result = lovelace_badges.list_badges(config, "home")
        assert len(result) == 2

    def test_list_badges_empty(self):
        config = _badges_config()
        assert lovelace_badges.list_badges(config, "other") == []

    def test_add_badge_string(self):
        config = _badges_config()
        result = lovelace_badges.add_badge(config, "home", "sensor.co2")
        assert result == "sensor.co2"
        assert len(config["views"][0]["badges"]) == 3

    def test_add_badge_dict(self):
        config = _badges_config()
        badge = {"type": "entity-filter", "entity": "sensor.temp"}
        result = lovelace_badges.add_badge(config, "home", badge)
        assert result == badge
        assert len(config["views"][0]["badges"]) == 3

    def test_add_badge_empty_raises(self):
        config = _badges_config()
        with pytest.raises(ValueError, match="badge required"):
            lovelace_badges.add_badge(config, "home", "")

    def test_add_badge_at_index(self):
        config = _badges_config()
        lovelace_badges.add_badge(config, "home", "sensor.new", index=0)
        assert config["views"][0]["badges"][0] == "sensor.new"

    def test_add_badge_index_clamped(self):
        config = _badges_config()
        lovelace_badges.add_badge(config, "home", "sensor.new", index=999)
        assert config["views"][0]["badges"][-1] == "sensor.new"

    def test_add_badge_creates_badges_list_if_missing(self):
        config = {"views": [{"path": "home"}]}
        lovelace_badges.add_badge(config, "home", "sensor.temp")
        assert config["views"][0]["badges"] == ["sensor.temp"]

    def test_delete_badge(self):
        config = _badges_config()
        lovelace_badges.delete_badge(config, "home", 0)
        assert len(config["views"][0]["badges"]) == 1
        assert config["views"][0]["badges"][0] == "sensor.humidity"

    def test_delete_badge_out_of_range_raises(self):
        config = _badges_config()
        with pytest.raises(IndexError, match="out of range"):
            lovelace_badges.delete_badge(config, "home", 99)

    def test_delete_badge_no_badges_list_raises(self):
        config = {"views": [{"path": "home"}]}
        with pytest.raises(ValueError, match="no badges list"):
            lovelace_badges.delete_badge(config, "home", 0)

    def test_move_badge(self):
        config = _badges_config()
        lovelace_badges.move_badge(config, "home", 0, 1)
        assert config["views"][0]["badges"][0] == "sensor.humidity"
        assert config["views"][0]["badges"][1] == "sensor.temp"

    def test_move_badge_out_of_range_raises(self):
        config = _badges_config()
        with pytest.raises(IndexError, match="out of range"):
            lovelace_badges.move_badge(config, "home", 0, 99)

    def test_move_badge_no_badges_list_raises(self):
        config = {"views": [{"path": "home"}]}
        with pytest.raises(ValueError, match="no badges list"):
            lovelace_badges.move_badge(config, "home", 0, 0)


# ──────────────────────────────────────────────────────────────  themes.py


class TestThemes:
    def test_list_themes(self, fake_client):
        fake_client.set_ws(
            "frontend/get_themes",
            {
                "themes": {"default": {}, "dark_blue": {"primary-color": "#0000ff"}},
                "default_theme": "default",
                "default_dark_theme": "dark_blue",
            },
        )
        result = themes.list_themes(fake_client)
        assert result["default_theme"] == "default"

    def test_list_themes_empty_when_no_response(self, fake_client):
        assert themes.list_themes(fake_client) == {}

    def test_names_sorted(self, fake_client):
        fake_client.set_ws(
            "frontend/get_themes",
            {
                "themes": {"zebra": {}, "apple": {}, "mango": {}},
            },
        )
        result = themes.names(fake_client)
        assert result == ["apple", "mango", "zebra"]

    def test_names_empty_when_no_themes(self, fake_client):
        fake_client.set_ws("frontend/get_themes", {"themes": {}})
        assert themes.names(fake_client) == []

    def test_names_empty_when_response_not_dict(self, fake_client):
        fake_client.set_ws("frontend/get_themes", "not a dict")
        assert themes.names(fake_client) == []

    def test_set_theme(self, fake_client):
        fake_client.set_service("frontend", "set_theme", {"ok": True})
        result = themes.set_theme(fake_client, "dark_blue")
        assert result == {"ok": True}
        assert fake_client.service_calls[-1]["service_data"] == {"name": "dark_blue"}

    def test_set_theme_empty_name_raises(self, fake_client):
        with pytest.raises(ValueError, match="name is required"):
            themes.set_theme(fake_client, "")

    def test_set_theme_with_mode_dark(self, fake_client):
        fake_client.set_service("frontend", "set_theme", {"ok": True})
        themes.set_theme(fake_client, "dark_blue", mode="dark")
        assert fake_client.service_calls[-1]["service_data"] == {
            "name": "dark_blue",
            "mode": "dark",
        }

    def test_set_theme_with_invalid_mode_raises(self, fake_client):
        with pytest.raises(ValueError, match="mode must be 'dark' or 'light'"):
            themes.set_theme(fake_client, "dark_blue", mode="bogus")

    def test_reload(self, fake_client):
        fake_client.set_service("frontend", "reload_themes", {"ok": True})
        result = themes.reload(fake_client)
        assert result == {"ok": True}

    def test_themes_reload_alias(self, fake_client):
        assert themes.themes_reload is themes.reload


# ──────────────────────────────────────────────────────────────  groups.py


class TestGroups:
    def test_expand_parses_template_output(self, fake_client):
        fake_client.set("POST", "template", "light.lamp|||on|||Lamp\nlight.bulb|||off|||Bulb\n")
        result = groups.expand(fake_client, "light.group1")
        assert len(result) == 2
        assert result[0]["entity_id"] == "light.lamp"
        assert result[0]["state"] == "on"
        assert result[0]["friendly_name"] == "Lamp"
        assert result[1]["entity_id"] == "light.bulb"
        assert result[1]["state"] == "off"

    def test_expand_without_state(self, fake_client):
        fake_client.set("POST", "template", "light.lamp|||on|||Lamp\n")
        result = groups.expand(fake_client, "light.group1", include_state=False)
        assert "state" not in result[0]
        assert result[0]["entity_id"] == "light.lamp"
        assert result[0]["friendly_name"] == "Lamp"

    def test_expand_skips_empty_lines(self, fake_client):
        fake_client.set("POST", "template", "light.lamp|||on|||Lamp\n\n\n")
        result = groups.expand(fake_client, "light.group1")
        assert len(result) == 1

    def test_expand_without_friendly_name(self, fake_client):
        fake_client.set("POST", "template", "light.lamp|||on|||\n")
        result = groups.expand(fake_client, "light.group1")
        assert "friendly_name" not in result[0]

    def test_expand_invalid_entity_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="domain.object"):
            groups.expand(fake_client, "invalid")

    def test_deep_expand_returns_entity_ids_only(self, fake_client):
        fake_client.set("POST", "template", "light.lamp|||on|||Lamp\nlight.bulb|||off|||Bulb\n")
        result = groups.deep_expand(fake_client, "light.group1")
        assert result == ["light.lamp", "light.bulb"]


# ──────────────────────────────────────────────────────────────  diagnostics.py


class TestDiagnostics:
    def test_list_handlers(self, fake_client):
        fake_client.set_ws(
            "diagnostics/list",
            [
                {"domain": "hue", "handlers": {"config_entry": True, "device": True}},
            ],
        )
        result = diagnostics.list_handlers(fake_client)
        assert len(result) == 1
        assert result[0]["domain"] == "hue"

    def test_list_handlers_empty_when_not_list(self, fake_client):
        fake_client.set_ws("diagnostics/list", {"not": "a list"})
        assert diagnostics.list_handlers(fake_client) == []

    def test_get_config_entry(self, fake_client):
        fake_client.set("GET", "diagnostics/config_entry/abc123", {"data": "diag"})
        result = diagnostics.get_config_entry(fake_client, "abc123")
        assert result == {"data": "diag"}

    def test_get_config_entry_empty_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="entry_id is required"):
            diagnostics.get_config_entry(fake_client, "")

    def test_get_device(self, fake_client):
        fake_client.set("GET", "diagnostics/config_entry/abc/device/dev1", {"data": "diag"})
        result = diagnostics.get_device(fake_client, "abc", "dev1")
        assert result == {"data": "diag"}

    def test_get_device_empty_entry_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="entry_id is required"):
            diagnostics.get_device(fake_client, "", "dev1")

    def test_get_device_empty_device_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="device_id is required"):
            diagnostics.get_device(fake_client, "abc", "")

    def test_save_to_file_writes_json(self, tmp_path):
        data = {"key": "value", "nested": {"n": 1}}
        path = str(tmp_path / "diag.json")
        byte_count = diagnostics.save_to_file(data, path)
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == data
        assert byte_count == len(json.dumps(data, indent=2, default=str).encode("utf-8"))


# ──────────────────────────────────────────────────────────────  history.py


class TestHistory:
    def test_history_basic(self, fake_client):
        fake_client.set("GET", "history/period", [[{"state": "on"}]])
        result = history.history(fake_client)
        assert len(result) == 1
        assert result[0][0]["state"] == "on"

    def test_history_with_entity_filter(self, fake_client):
        fake_client.set("GET", "history/period", [[{"state": "on"}]])
        history.history(fake_client, entity_ids=["sensor.temp"])
        call = fake_client.calls[-1]
        assert call["params"]["filter_entity_id"] == "sensor.temp"

    def test_history_with_start_time(self, fake_client):
        fake_client.set("GET", "history/period", [[{"state": "on"}]])
        start = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        history.history(fake_client, start=start)
        call = fake_client.calls[-1]
        assert "2026-01-01T12:00:00+00:00" in call["path"]

    def test_history_with_naive_start_gets_utc(self, fake_client):
        """A naive datetime should be treated as UTC."""
        fake_client.set("GET", "history/period", [[{"state": "on"}]])
        start = datetime(2026, 1, 1, 12, 0)  # naive, intentionally no tz  # noqa: DTZ001
        history.history(fake_client, start=start)
        call = fake_client.calls[-1]
        assert "+00:00" in call["path"]

    def test_history_with_end_time(self, fake_client):
        fake_client.set("GET", "history/period", [[{"state": "on"}]])
        end = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
        history.history(fake_client, end=end)
        call = fake_client.calls[-1]
        assert call["params"]["end_time"] == "2026-01-02T12:00:00+00:00"

    def test_history_minimal_response_default(self, fake_client):
        fake_client.set("GET", "history/period", [[{"state": "on"}]])
        history.history(fake_client)
        call = fake_client.calls[-1]
        assert "minimal_response" in call["params"]

    def test_history_no_attributes(self, fake_client):
        fake_client.set("GET", "history/period", [[{"state": "on"}]])
        history.history(fake_client, no_attributes=True)
        call = fake_client.calls[-1]
        assert "no_attributes" in call["params"]

    def test_history_significant_changes_only(self, fake_client):
        fake_client.set("GET", "history/period", [[{"state": "on"}]])
        history.history(fake_client, significant_changes_only=True)
        call = fake_client.calls[-1]
        assert "significant_changes_only" in call["params"]

    def test_history_returns_empty_when_non_list(self, fake_client):
        fake_client.set("GET", "history/period", {"not": "a list"})
        assert history.history(fake_client) == []

    def test_logbook_basic(self, fake_client):
        fake_client.set("GET", "logbook", [{"name": "event"}])
        result = history.logbook(fake_client)
        assert len(result) == 1

    def test_logbook_with_entity(self, fake_client):
        fake_client.set("GET", "logbook", [{"name": "event"}])
        history.logbook(fake_client, entity_id="sensor.temp")
        call = fake_client.calls[-1]
        assert call["params"]["entity"] == "sensor.temp"

    def test_logbook_with_hours(self, fake_client):
        fake_client.set("GET", "logbook", [{"name": "event"}])
        history.logbook(fake_client, hours=6)
        call = fake_client.calls[-1]
        # The path should include a timestamp (start = now - 6h)
        assert "logbook/" in call["path"]

    def test_logbook_with_start(self, fake_client):
        fake_client.set("GET", "logbook", [{"name": "event"}])
        start = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        history.logbook(fake_client, start=start)
        call = fake_client.calls[-1]
        assert "2026-01-01T12:00:00+00:00" in call["path"]

    def test_logbook_with_end(self, fake_client):
        fake_client.set("GET", "logbook", [{"name": "event"}])
        end = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
        history.logbook(fake_client, end=end)
        call = fake_client.calls[-1]
        assert call["params"]["end_time"] == "2026-01-02T12:00:00+00:00"

    def test_logbook_returns_empty_when_non_list(self, fake_client):
        fake_client.set("GET", "logbook", {"not": "a list"})
        assert history.logbook(fake_client) == []


# ──────────────────────────────────────────────────────────────  inspect.py


class TestInspectEntity:
    def test_inspect_invalid_entity_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="domain.object"):
            inspect.inspect_entity(fake_client, "invalid")

    def test_inspect_empty_entity_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="domain.object"):
            inspect.inspect_entity(fake_client, "")

    def test_inspect_basic(self, fake_client):
        fake_client.set("GET", "states/light.lamp", {"state": "on", "attributes": {}})
        fake_client.set_ws("config/entity_registry/list", [])
        fake_client.set_ws("config/device_registry/list", [])
        fake_client.set_ws("config/area_registry/list", [])
        result = inspect.inspect_entity(fake_client, "light.lamp")
        assert result["entity_id"] == "light.lamp"
        assert result["state"]["state"] == "on"
        assert result["registry"] is None
        assert result["device"] is None
        assert result["area"] is None

    def test_inspect_with_registry_and_device(self, fake_client):
        fake_client.set("GET", "states/light.lamp", {"state": "on"})
        fake_client.set_ws(
            "config/entity_registry/list",
            [
                {"entity_id": "light.lamp", "device_id": "dev1", "area_id": "area1"},
            ],
        )
        fake_client.set_ws(
            "config/device_registry/list",
            [
                {"id": "dev1", "name": "My Device", "area_id": "area1"},
            ],
        )
        fake_client.set_ws(
            "config/area_registry/list",
            [
                {"area_id": "area1", "name": "Living Room"},
            ],
        )
        result = inspect.inspect_entity(fake_client, "light.lamp")
        assert result["registry"]["device_id"] == "dev1"
        assert result["device"]["name"] == "My Device"
        assert result["area"]["name"] == "Living Room"

    def test_inspect_state_error_captured(self, fake_client, monkeypatch):
        """When the state API raises, the error is captured in the result."""
        from cli_anything.homeassistant.core import states as states_core

        def boom(client, entity_id):
            raise RuntimeError("connection refused")

        monkeypatch.setattr(states_core, "get_state", boom)
        fake_client.set_ws("config/entity_registry/list", [])
        fake_client.set_ws("config/device_registry/list", [])
        fake_client.set_ws("config/area_registry/list", [])
        result = inspect.inspect_entity(fake_client, "light.lamp")
        assert "error" in result["state"]
        assert "connection refused" in result["state"]["error"]

    def test_inspect_with_history(self, fake_client):
        fake_client.set("GET", "states/light.lamp", {"state": "on"})
        fake_client.set("GET", "history/period", [[{"state": "on"}, {"state": "off"}]])
        fake_client.set_ws("config/entity_registry/list", [])
        fake_client.set_ws("config/device_registry/list", [])
        fake_client.set_ws("config/area_registry/list", [])
        result = inspect.inspect_entity(
            fake_client,
            "light.lamp",
            include_history=True,
            history_hours=12,
        )
        assert "history" in result
        assert len(result["history"]) == 1  # one entity's history list

    def test_inspect_without_references(self, fake_client):
        fake_client.set("GET", "states/light.lamp", {"state": "on"})
        fake_client.set_ws("config/entity_registry/list", [])
        fake_client.set_ws("config/device_registry/list", [])
        fake_client.set_ws("config/area_registry/list", [])
        result = inspect.inspect_entity(
            fake_client,
            "light.lamp",
            include_references=False,
        )
        assert "references" not in result

    def test_inspect_device_area_from_device(self, fake_client):
        """When registry has no area_id but device does, area comes from device."""
        fake_client.set("GET", "states/light.lamp", {"state": "on"})
        fake_client.set_ws(
            "config/entity_registry/list",
            [
                {"entity_id": "light.lamp", "device_id": "dev1"},  # no area_id
            ],
        )
        fake_client.set_ws(
            "config/device_registry/list",
            [
                {"id": "dev1", "area_id": "area1"},
            ],
        )
        fake_client.set_ws(
            "config/area_registry/list",
            [
                {"area_id": "area1", "name": "Kitchen"},
            ],
        )
        result = inspect.inspect_entity(fake_client, "light.lamp")
        assert result["area"]["name"] == "Kitchen"
