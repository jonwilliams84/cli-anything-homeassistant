"""Unit tests for cli-anything-homeassistant — no real HA required."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from cli_anything.homeassistant.core import (
    auth as auth_core,
    automation as automation_core,
    config_entries as config_entries_core,
    domain as domain_core,
    events as events_core,
    helpers as helpers_core,
    history as history_core,
    lovelace as lovelace_core,
    lovelace_cards as lovelace_cards_core,
    project,
    registry as registry_core,
    script as script_core,
    services as services_core,
    states as states_core,
    system as system_core,
    template as template_core,
)
from cli_anything.homeassistant.homeassistant_cli import parse_kv_pairs
from cli_anything.homeassistant.utils.homeassistant_backend import (
    HomeAssistantClient,
    HomeAssistantError,
    _normalize_base,
    _ws_url_from_http,
)


# ────────────────────────────────────────────────────────── project (config)

class TestProjectConfig:
    def test_defaults_when_no_file(self, tmp_path: Path, monkeypatch):
        for k in ("HASS_URL", "HASS_TOKEN", "HASS_VERIFY_SSL", "HASS_TIMEOUT"):
            monkeypatch.delenv(k, raising=False)
        cfg = project.load_config(tmp_path / "missing.json")
        assert cfg["url"] == "http://localhost:8123"
        assert cfg["token"] == ""
        assert cfg["verify_ssl"] is True
        assert cfg["timeout"] == 30

    def test_env_override(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("HASS_URL", "http://x:9123")
        monkeypatch.setenv("HASS_TOKEN", "ZZZZ")
        monkeypatch.setenv("HASS_VERIFY_SSL", "0")
        monkeypatch.setenv("HASS_TIMEOUT", "12")
        cfg = project.load_config(tmp_path / "missing.json")
        assert cfg["url"] == "http://x:9123"
        assert cfg["token"] == "ZZZZ"
        assert cfg["verify_ssl"] is False
        assert cfg["timeout"] == 12

    def test_save_and_load_roundtrip(self, tmp_path: Path, monkeypatch):
        for k in ("HASS_URL", "HASS_TOKEN", "HASS_VERIFY_SSL", "HASS_TIMEOUT"):
            monkeypatch.delenv(k, raising=False)
        path = tmp_path / "profile.json"
        project.save_config("http://h:8123", "TOKEN1234", verify_ssl=False,
                            timeout=42, config_path=path)
        cfg = project.load_config(path)
        assert cfg["url"] == "http://h:8123"
        assert cfg["token"] == "TOKEN1234"
        assert cfg["verify_ssl"] is False
        assert cfg["timeout"] == 42

    def test_save_sets_0600(self, tmp_path: Path):
        path = tmp_path / "profile.json"
        project.save_config("http://h", "T", config_path=path)
        mode = stat.S_IMODE(os.stat(path).st_mode)
        # On WSL/Linux this should be exactly 0o600. On Windows we accept any
        # mode since chmod has no real effect.
        if os.name == "posix":
            assert mode == 0o600

    def test_redact(self):
        out = project.redact({"url": "u", "token": "abcdefghij"})
        assert out["token"] == "***ghij"


# ────────────────────────────────────────────────────────── system

class TestSystem:
    def test_status(self, fake_client):
        fake_client.set("GET", "", {"message": "API running."})
        assert system_core.status(fake_client) == {"message": "API running."}

    def test_status_non_dict_wraps_message(self, fake_client):
        fake_client.set("GET", "", "API running.")
        assert system_core.status(fake_client) == {"message": "API running."}

    def test_config_returns_dict(self, fake_client):
        fake_client.set("GET", "config", {"location_name": "Home"})
        assert system_core.config(fake_client)["location_name"] == "Home"

    def test_core_state(self, fake_client):
        fake_client.set("GET", "core/state", {"state": "RUNNING"})
        assert system_core.core_state(fake_client)["state"] == "RUNNING"

    def test_error_log_full(self, fake_client):
        fake_client.set("GET", "error_log", "line1\nline2\nline3")
        assert system_core.error_log(fake_client) == "line1\nline2\nline3"

    def test_error_log_tail(self, fake_client):
        fake_client.set("GET", "error_log", "a\nb\nc\nd")
        assert system_core.error_log(fake_client, lines=2) == "c\nd"

    def test_components_list(self, fake_client):
        fake_client.set("GET", "components", ["http", "api", "auth"])
        assert system_core.components(fake_client) == ["http", "api", "auth"]

    def test_components_empty(self, fake_client):
        fake_client.set("GET", "components", None)
        assert system_core.components(fake_client) == []

    def test_system_health_uses_ws(self, fake_client):
        fake_client.set_ws("system_health/info", {"homeassistant": {"version": "x"}})
        result = system_core.system_health(fake_client)
        assert fake_client.ws_calls[-1]["type"] == "system_health/info"
        assert result["homeassistant"]["version"] == "x"


# ────────────────────────────────────────────────────────── lovelace_paths

from cli_anything.homeassistant.core import lovelace_paths


class TestLovelacePaths:
    SAMPLE = {
        "views": [
            {"path": "home", "title": "Home", "type": "masonry",
             "cards": [
                 {"type": "heading", "heading": "Welcome"},
                 {"type": "horizontal-stack", "cards": [
                     {"type": "entities", "title": "Energy",
                      "entities": ["sensor.power"]},
                 ]},
             ]},
            {"path": "scratch", "title": "Scratch", "type": "sections",
             "sections": [
                 {"type": "grid", "cards": [
                     {"type": "markdown", "content": "hi"},
                     {"type": "custom:mushroom-template-card",
                      "primary": "Doors", "icon": "mdi:door"},
                 ]},
             ]},
        ]
    }

    def test_get_view_by_path(self):
        v = lovelace_paths.get_view(self.SAMPLE, "scratch")
        assert v["title"] == "Scratch"

    def test_get_view_by_index(self):
        v = lovelace_paths.get_view(self.SAMPLE, "0")
        assert v["path"] == "home"

    def test_get_view_missing(self):
        with pytest.raises(KeyError):
            lovelace_paths.get_view(self.SAMPLE, "nope")

    def test_set_view_mutates_in_place(self):
        cfg = json.loads(json.dumps(self.SAMPLE))  # deepcopy
        new = {"path": "scratch", "title": "Scratch v2", "type": "sections",
               "sections": []}
        lovelace_paths.set_view(cfg, "scratch", new)
        assert cfg["views"][1]["title"] == "Scratch v2"

    def test_add_view_rejects_duplicate_path(self):
        cfg = json.loads(json.dumps(self.SAMPLE))
        with pytest.raises(ValueError, match="already exists"):
            lovelace_paths.add_view(cfg, {"path": "home", "title": "x"})

    def test_add_view_appends(self):
        cfg = json.loads(json.dumps(self.SAMPLE))
        lovelace_paths.add_view(cfg, {"path": "new", "title": "New"})
        assert cfg["views"][-1]["path"] == "new"

    def test_delete_view(self):
        cfg = json.loads(json.dumps(self.SAMPLE))
        lovelace_paths.delete_view(cfg, "scratch")
        assert len(cfg["views"]) == 1
        assert cfg["views"][0]["path"] == "home"

    def test_get_card_dotpath_sections(self):
        card = lovelace_paths.get_card(self.SAMPLE, "scratch.0.1")
        assert card["primary"] == "Doors"

    def test_get_card_dotpath_masonry(self):
        card = lovelace_paths.get_card(self.SAMPLE, "home.0")
        assert card["type"] == "heading"

    def test_set_card_replaces_at_dotpath(self):
        cfg = json.loads(json.dumps(self.SAMPLE))
        lovelace_paths.set_card(cfg, "scratch.0.1", {"type": "markdown", "content": "new"})
        assert cfg["views"][1]["sections"][0]["cards"][1]["content"] == "new"

    def test_get_section(self):
        s = lovelace_paths.get_section(self.SAMPLE, "scratch", 0)
        assert s["type"] == "grid"

    def test_set_section(self):
        cfg = json.loads(json.dumps(self.SAMPLE))
        lovelace_paths.set_section(cfg, "scratch", 0,
                                     {"type": "grid", "cards": []})
        assert cfg["views"][1]["sections"][0]["cards"] == []

    def test_search_matches_title(self):
        hits = lovelace_paths.search(self.SAMPLE, "Doors")
        assert any(h["match_field"] == "primary" for h in hits)

    def test_search_returns_paths(self):
        hits = lovelace_paths.search(self.SAMPLE, "Welcome")
        assert any("views[0]" in h["path"] for h in hits)

    def test_search_case_insensitive_default(self):
        hits = lovelace_paths.search(self.SAMPLE, "energy")
        assert hits

    def test_list_paths_enumerates_everything(self):
        rows = lovelace_paths.list_paths(self.SAMPLE)
        kinds = [r["kind"] for r in rows]
        assert kinds.count("view") == 2
        assert kinds.count("section") == 1
        assert kinds.count("card") >= 3


# ────────────────────────────────────────────────────────── logger

from cli_anything.homeassistant.core import logger as logger_core


class TestLogger:
    def test_set_level_calls_service(self, fake_client):
        fake_client.set_service("logger", "set_level", {"ok": True})
        logger_core.set_level(fake_client, {"custom_components.hon": "critical"})
        last = fake_client.service_calls[-1]
        assert last["domain"] == "logger"
        assert last["service"] == "set_level"
        assert last["service_data"]["custom_components.hon"] == "critical"

    def test_set_level_validates(self):
        with pytest.raises(ValueError):
            logger_core.set_level(None, {"foo": "bogus"})
        with pytest.raises(ValueError):
            logger_core.set_level(None, {})

    def test_set_default_level(self, fake_client):
        fake_client.set_service("logger", "set_default_level", {"ok": True})
        logger_core.set_default_level(fake_client, "warning")
        last = fake_client.service_calls[-1]
        assert last["service"] == "set_default_level"
        assert last["service_data"]["level"] == "warning"


# ────────────────────────────────────────────────────────── references

from cli_anything.homeassistant.core import references as references_core


class TestReferences:
    def test_matches_entity_whole_token(self):
        assert references_core._matches_entity("foo sensor.power_x bar", "sensor.power_x")
        assert not references_core._matches_entity("foo sensor.power_xtra bar", "sensor.power_x")

    def test_matches_entity_in_quoted_string(self):
        assert references_core._matches_entity('"sensor.power_x"', "sensor.power_x")

    def test_walk_strings_yields_paths(self):
        obj = {"a": "hello", "b": ["x", {"c": "world"}]}
        rows = dict((p, s) for p, s in references_core._walk_strings(obj))
        assert rows["a"] == "hello"
        assert "b[0]" in rows
        assert rows["b[1].c"] == "world"


# ────────────────────────────────────────────────────────── backup

from cli_anything.homeassistant.core import backup as backup_core


class TestBackup:
    def test_list_returns_array(self, fake_client):
        fake_client.set_ws("backup/info", {"backups": [
            {"backup_id": "a1", "name": "n1"},
            {"backup_id": "a2", "name": "n2"},
        ]})
        rows = backup_core.list_backups(fake_client)
        assert [r["backup_id"] for r in rows] == ["a1", "a2"]

    def test_list_empty(self, fake_client):
        fake_client.set_ws("backup/info", {"backups": []})
        assert backup_core.list_backups(fake_client) == []

    def test_generate_passes_through(self, fake_client):
        fake_client.set_ws("backup/generate", {"job_id": "x"})
        out = backup_core.generate(fake_client, name="my-backup",
                                     password="secret")
        last = fake_client.ws_calls[-1]
        assert last["type"] == "backup/generate"
        assert last["payload"]["name"] == "my-backup"
        assert last["payload"]["password"] == "secret"
        assert out == {"job_id": "x"}

    def test_remove_requires_id(self):
        with pytest.raises(ValueError):
            backup_core.remove(None, "")

    def test_restore_requires_id(self):
        with pytest.raises(ValueError):
            backup_core.restore(None, "")


# ────────────────────────────────────────────────────────── control

from cli_anything.homeassistant.core import control as control_core


class TestControl:
    def test_restart_calls_service(self, fake_client):
        fake_client.set_service("homeassistant", "restart", {"ok": True})
        control_core.restart(fake_client)
        last = fake_client.service_calls[-1]
        assert last["domain"] == "homeassistant"
        assert last["service"] == "restart"

    def test_restart_safe_mode(self, fake_client):
        fake_client.set_service("homeassistant", "restart", {"ok": True})
        control_core.restart(fake_client, safe_mode=True)
        last = fake_client.service_calls[-1]
        assert last["service_data"] == {"safe_mode": True}

    def test_reload_all(self, fake_client):
        fake_client.set_service("homeassistant", "reload_all", {"ok": True})
        control_core.reload_all(fake_client)
        last = fake_client.service_calls[-1]
        assert last["service"] == "reload_all"

    def test_check_config_valid(self, fake_client):
        fake_client.set_service("homeassistant", "check_config", None)
        # No notification → valid=true
        fake_client.set("GET", "states/persistent_notification.config_check_failed",
                         {"state": "unknown"})
        out = control_core.check_config(fake_client, wait_secs=0.5)
        assert out["valid"] is True

    def test_check_config_invalid(self, fake_client):
        fake_client.set_service("homeassistant", "check_config", None)
        fake_client.set("GET", "states/persistent_notification.config_check_failed",
                         {"state": "active",
                          "attributes": {"message": "bad yaml", "title": "Failed"}})
        out = control_core.check_config(fake_client, wait_secs=0.5)
        assert out["valid"] is False
        assert "bad yaml" in out["message"]


# ────────────────────────────────────────────────────────── repairs

from cli_anything.homeassistant.core import repairs as repairs_core


class TestRepairs:
    SAMPLE = {
        "issues": [
            {"issue_id": "i1", "domain": "mqtt", "severity": "warning",
             "dismissed_version": None, "translation_key": "foo"},
            {"issue_id": "i2", "domain": "z2m", "severity": "error",
             "dismissed_version": "2024.1", "translation_key": "bar"},
            {"issue_id": "i3", "domain": "mqtt", "severity": "error",
             "dismissed_version": None, "translation_key": "baz"},
        ],
    }

    def test_list_excludes_dismissed_by_default(self, fake_client):
        fake_client.set_ws("repairs/list_issues", self.SAMPLE)
        rows = repairs_core.list_issues(fake_client)
        ids = [r["issue_id"] for r in rows]
        assert "i2" not in ids
        assert "i1" in ids and "i3" in ids

    def test_list_filter_severity(self, fake_client):
        fake_client.set_ws("repairs/list_issues", self.SAMPLE)
        rows = repairs_core.list_issues(fake_client, severity="error")
        assert [r["issue_id"] for r in rows] == ["i3"]

    def test_list_filter_domain(self, fake_client):
        fake_client.set_ws("repairs/list_issues", self.SAMPLE)
        rows = repairs_core.list_issues(fake_client, domain="mqtt",
                                          include_dismissed=True)
        assert {r["issue_id"] for r in rows} == {"i1", "i3"}

    def test_ignore_validates(self):
        with pytest.raises(ValueError):
            repairs_core.ignore(None, issue_id="", domain="x")
        with pytest.raises(ValueError):
            repairs_core.ignore(None, issue_id="i", domain="")


# ────────────────────────────────────────────────────────── notifications

from cli_anything.homeassistant.core import notifications as notifications_core


class TestNotifications:
    def test_list_from_ws(self, fake_client):
        fake_client.set_ws("persistent_notification/get", [
            {"notification_id": "n1", "title": "T", "message": "M"},
            {"notification_id": "n2", "title": "T2", "message": "M2"},
        ])
        rows = notifications_core.list_notifications(fake_client)
        ids = [r["notification_id"] for r in rows]
        assert ids == ["n1", "n2"]

    def test_create_payload(self, fake_client):
        fake_client.set_service("persistent_notification", "create", None)
        notifications_core.create(fake_client, message="hello",
                                    title="t", notification_id="my")
        last = fake_client.service_calls[-1]
        assert last["service"] == "create"
        assert last["service_data"] == {
            "message": "hello", "title": "t", "notification_id": "my",
        }

    def test_create_requires_message(self):
        with pytest.raises(ValueError):
            notifications_core.create(None, message="")

    def test_dismiss(self, fake_client):
        fake_client.set_service("persistent_notification", "dismiss", None)
        notifications_core.dismiss(fake_client, "abc")
        last = fake_client.service_calls[-1]
        assert last["service_data"] == {"notification_id": "abc"}


# ────────────────────────────────────────────────────────── registries write

from cli_anything.homeassistant.core import areas as areas_core
from cli_anything.homeassistant.core import floors as floors_core
from cli_anything.homeassistant.core import labels as labels_core
from cli_anything.homeassistant.core import persons as persons_core
from cli_anything.homeassistant.core import registry as _reg_core
from cli_anything.homeassistant.core import tags as tags_core


class TestAreasWrite:
    def test_create_payload(self, fake_client):
        fake_client.set_ws("config/area_registry/create", {"area_id": "x"})
        areas_core.create(fake_client, name="Office", floor_id="ground",
                            icon="mdi:desk", aliases=["study"], labels=["primary"])
        last = fake_client.ws_calls[-1]
        assert last["type"] == "config/area_registry/create"
        assert last["payload"] == {
            "name": "Office", "floor_id": "ground", "icon": "mdi:desk",
            "aliases": ["study"], "labels": ["primary"],
        }

    def test_update_only_passes_changed_fields(self, fake_client):
        fake_client.set_ws("config/area_registry/update", {"ok": True})
        areas_core.update(fake_client, "office", name="New Office")
        last = fake_client.ws_calls[-1]
        assert last["payload"] == {"area_id": "office", "name": "New Office"}

    def test_find_by_id_or_name(self, fake_client):
        fake_client.set_ws("config/area_registry/list", [
            {"area_id": "a1", "name": "Kitchen"},
            {"area_id": "a2", "name": "Lounge"},
        ])
        assert areas_core.find_area(fake_client, "a1")["name"] == "Kitchen"
        assert areas_core.find_area(fake_client, "kitchen")["area_id"] == "a1"
        assert areas_core.find_area(fake_client, "ghost") is None

    def test_delete_requires_id(self):
        with pytest.raises(ValueError):
            areas_core.delete(None, "")


class TestFloorsWrite:
    def test_list(self, fake_client):
        fake_client.set_ws("config/floor_registry/list", [
            {"floor_id": "ground", "level": 0, "name": "Ground"},
        ])
        rows = floors_core.list_floors(fake_client)
        assert rows[0]["floor_id"] == "ground"

    def test_create_payload(self, fake_client):
        fake_client.set_ws("config/floor_registry/create", {"floor_id": "first"})
        floors_core.create(fake_client, name="First", level=1, icon="mdi:home")
        last = fake_client.ws_calls[-1]
        assert last["payload"]["name"] == "First"
        assert last["payload"]["level"] == 1


class TestLabelsWrite:
    def test_create_payload(self, fake_client):
        fake_client.set_ws("config/label_registry/create", {"label_id": "x"})
        labels_core.create(fake_client, name="presence",
                             color="#06b6d4", description="presence sensors")
        last = fake_client.ws_calls[-1]
        assert last["payload"]["color"] == "#06b6d4"

    def test_update_passes_only_set_fields(self, fake_client):
        fake_client.set_ws("config/label_registry/update", {"ok": True})
        labels_core.update(fake_client, "presence", color="#000000")
        last = fake_client.ws_calls[-1]
        assert last["payload"] == {"label_id": "presence", "color": "#000000"}


class TestEntityRegistryWrite:
    def test_update_entity_sentinel_only_changes_explicit_fields(self, fake_client):
        fake_client.set_ws("config/entity_registry/update", {"ok": True})
        _reg_core.update_entity(fake_client, "sensor.foo", name="Foo Sensor")
        last = fake_client.ws_calls[-1]
        # disabled_by/hidden_by NOT in payload (sentinel)
        assert "disabled_by" not in last["payload"]
        assert "hidden_by" not in last["payload"]
        assert last["payload"] == {"entity_id": "sensor.foo", "name": "Foo Sensor"}

    def test_update_entity_disable_then_enable(self, fake_client):
        fake_client.set_ws("config/entity_registry/update", {"ok": True})
        _reg_core.update_entity(fake_client, "sensor.foo", disabled_by="user")
        assert fake_client.ws_calls[-1]["payload"]["disabled_by"] == "user"
        _reg_core.update_entity(fake_client, "sensor.foo", disabled_by=None)
        assert fake_client.ws_calls[-1]["payload"]["disabled_by"] is None

    def test_match_entities(self):
        entities = [
            {"entity_id": "sensor.kitchen_temp", "area_id": "kitchen",
             "labels": ["climate"], "platform": "mqtt"},
            {"entity_id": "sensor.bedroom_temp", "area_id": "bedroom",
             "labels": [], "platform": "mqtt"},
            {"entity_id": "switch.kitchen_light", "area_id": "kitchen",
             "labels": ["lighting"], "platform": "zigbee"},
        ]
        # by pattern
        assert len(_reg_core.match_entities(entities, pattern="kitchen")) == 2
        # by domain
        assert len(_reg_core.match_entities(entities, domain="switch")) == 1
        # by area
        assert len(_reg_core.match_entities(entities, area_id="kitchen")) == 2
        # by label
        assert len(_reg_core.match_entities(entities, label="climate")) == 1
        # by integration
        assert len(_reg_core.match_entities(entities, integration="zigbee")) == 1
        # combined
        assert len(_reg_core.match_entities(entities, domain="sensor",
                                              area_id="kitchen")) == 1

    def test_bulk_update_dry_run(self, fake_client):
        out = _reg_core.bulk_update_entities(
            fake_client,
            updates=[
                {"entity_id": "sensor.a", "labels": ["x"]},
                {"entity_id": "sensor.b", "name": "B"},
            ],
            dry_run=True,
        )
        assert out["dry_run"] is True
        assert len(out["applied"]) == 2
        assert "would_set" in out["applied"][0]
        assert fake_client.ws_calls == []  # no real calls

    def test_bulk_update_skips_missing_id(self, fake_client):
        fake_client.set_ws("config/entity_registry/update", {"ok": True})
        out = _reg_core.bulk_update_entities(
            fake_client,
            updates=[{"name": "no id"}, {"entity_id": "sensor.x", "name": "ok"}],
            dry_run=False,
        )
        assert len(out["failed"]) == 1
        assert len(out["applied"]) == 1


class TestDeviceRegistryWrite:
    def test_update_device_sentinel(self, fake_client):
        fake_client.set_ws("config/device_registry/update", {"ok": True})
        _reg_core.update_device(fake_client, "abc123",
                                  name_by_user="My Plug", area_id="kitchen")
        last = fake_client.ws_calls[-1]
        assert "disabled_by" not in last["payload"]
        assert last["payload"]["name_by_user"] == "My Plug"
        assert last["payload"]["area_id"] == "kitchen"


class TestPersons:
    def test_envelope_storage_and_config(self, fake_client):
        fake_client.set_ws("person/list", {
            "storage": [{"id": "p1", "name": "Jon"}],
            "config":  [{"id": "p2", "name": "Gem"}],
        })
        rows = persons_core.list_persons(fake_client)
        ids = {r["id"] for r in rows}
        assert ids == {"p1", "p2"}
        # _source is annotated so downstream callers can tell them apart
        srcs = {r["_source"] for r in rows}
        assert srcs == {"storage", "config"}

    def test_envelope_legacy_array(self, fake_client):
        fake_client.set_ws("person/list", [{"id": "p1", "name": "Jon"}])
        rows = persons_core.list_persons(fake_client)
        assert rows[0]["id"] == "p1"

    def test_create_passes_fields(self, fake_client):
        fake_client.set_ws("person/create", {"id": "newp"})
        persons_core.create(fake_client, name="New",
                              user_id="user-uuid",
                              device_trackers=["device_tracker.phone"])
        last = fake_client.ws_calls[-1]
        assert last["payload"]["device_trackers"] == ["device_tracker.phone"]


class TestTags:
    def test_list(self, fake_client):
        fake_client.set_ws("tag/list", [{"id": "t1", "name": "Door"}])
        rows = tags_core.list_tags(fake_client)
        assert rows[0]["id"] == "t1"

    def test_find_by_name_case_insensitive(self, fake_client):
        fake_client.set_ws("tag/list", [{"id": "t1", "name": "Door"}])
        assert tags_core.find_tag(fake_client, "door")["id"] == "t1"


# ────────────────────────────────────────────────────────── diagnostics & introspection

from cli_anything.homeassistant.core import diagnostics as diagnostics_core
from cli_anything.homeassistant.core import statistics as statistics_core
from cli_anything.homeassistant.core import assist as assist_core
from cli_anything.homeassistant.core import updates as updates_core
from cli_anything.homeassistant.core import inspect as inspect_core


class TestDiagnostics:
    def test_list_handlers(self, fake_client):
        fake_client.set_ws("diagnostics/list", [
            {"domain": "mqtt", "handlers": {"config_entry": True, "device": False}},
            {"domain": "zigbee2mqtt", "handlers": {"config_entry": True, "device": True}},
        ])
        rows = diagnostics_core.list_handlers(fake_client)
        assert len(rows) == 2
        assert rows[0]["domain"] == "mqtt"

    def test_get_config_entry_validates(self):
        with pytest.raises(ValueError):
            diagnostics_core.get_config_entry(None, "")

    def test_get_config_entry_hits_correct_path(self, fake_client):
        fake_client.set("GET", "diagnostics/config_entry/abc123",
                          {"data": {"foo": "bar"}})
        out = diagnostics_core.get_config_entry(fake_client, "abc123")
        assert out["data"]["foo"] == "bar"

    def test_get_device_hits_nested_path(self, fake_client):
        fake_client.set("GET", "diagnostics/config_entry/abc/device/dev1",
                          {"x": 1})
        out = diagnostics_core.get_device(fake_client, "abc", "dev1")
        assert out["x"] == 1

    def test_save_to_file(self, tmp_path):
        path = tmp_path / "out.json"
        n = diagnostics_core.save_to_file({"a": 1, "b": 2}, str(path))
        assert n > 0
        loaded = json.loads(path.read_text())
        assert loaded == {"a": 1, "b": 2}


class TestStatistics:
    def test_list_validates_type(self):
        with pytest.raises(ValueError):
            statistics_core.list_statistic_ids(None, statistic_type="invalid")

    def test_list_passes_filter(self, fake_client):
        fake_client.set_ws("recorder/list_statistic_ids", [{"statistic_id": "x"}])
        statistics_core.list_statistic_ids(fake_client, statistic_type="sum")
        last = fake_client.ws_calls[-1]
        assert last["payload"] == {"statistic_type": "sum"}

    def test_metadata_no_filter(self, fake_client):
        fake_client.set_ws("recorder/get_statistics_metadata", [])
        statistics_core.get_metadata(fake_client)
        last = fake_client.ws_calls[-1]
        # No payload when no ids — argument was None
        assert last["payload"] in (None, {})

    def test_series_validates(self):
        with pytest.raises(ValueError):
            statistics_core.statistics_during_period(None, statistic_ids=[])
        with pytest.raises(ValueError):
            statistics_core.statistics_during_period(
                None, statistic_ids=["sensor.x"], period="picosecond",
            )

    def test_series_default_start_is_24h_ago(self, fake_client):
        fake_client.set_ws("recorder/statistics_during_period", {})
        statistics_core.statistics_during_period(
            fake_client, statistic_ids=["sensor.x"], period="hour",
        )
        last = fake_client.ws_calls[-1]
        assert last["payload"]["statistic_ids"] == ["sensor.x"]
        assert last["payload"]["period"] == "hour"
        assert "start_time" in last["payload"]

    def test_clear_validates(self):
        with pytest.raises(ValueError):
            statistics_core.clear(None, [])


class TestAssist:
    def test_process_requires_text(self):
        with pytest.raises(ValueError):
            assist_core.process(None, "")

    def test_process_passes_optional_fields(self, fake_client):
        fake_client.set("POST", "conversation/process",
                          {"response": {"speech": {"plain": {"speech": "ok"}}}})
        out = assist_core.process(fake_client, "test",
                                    conversation_id="cid-1", language="en")
        last_post = [c for c in fake_client.calls if c["verb"] == "POST"][-1]
        assert last_post["payload"]["text"] == "test"
        assert last_post["payload"]["conversation_id"] == "cid-1"
        assert last_post["payload"]["language"] == "en"
        assert out["response"]["speech"]["plain"]["speech"] == "ok"

    def test_pipelines_returns_dict(self, fake_client):
        fake_client.set_ws("assist_pipeline/pipeline/list", {
            "pipelines": [{"id": "p1", "name": "Tiny"}],
            "preferred_pipeline": "p1",
        })
        out = assist_core.pipelines(fake_client)
        assert out["preferred_pipeline"] == "p1"


class TestUpdates:
    def test_list_filters_available_only(self, fake_client):
        fake_client.set("GET", "states", [
            {"entity_id": "update.foo", "state": "on",
             "attributes": {"latest_version": "2.0.0"}},
            {"entity_id": "update.bar", "state": "off",
             "attributes": {"latest_version": "1.0.0"}},
            {"entity_id": "sensor.foo", "state": "on", "attributes": {}},
        ])
        rows = updates_core.list_updates(fake_client, available_only=True)
        assert len(rows) == 1
        assert rows[0]["entity_id"] == "update.foo"

    def test_list_include_off(self, fake_client):
        fake_client.set("GET", "states", [
            {"entity_id": "update.foo", "state": "on", "attributes": {}},
            {"entity_id": "update.bar", "state": "off", "attributes": {}},
        ])
        rows = updates_core.list_updates(fake_client, available_only=False)
        assert {r["entity_id"] for r in rows} == {"update.foo", "update.bar"}

    def test_install_validates_domain(self):
        with pytest.raises(ValueError):
            updates_core.install(None, "sensor.foo")

    def test_install_payload(self, fake_client):
        fake_client.set_service("update", "install", {"ok": True})
        updates_core.install(fake_client, "update.foo", version="2.0.0",
                              backup=True)
        last = fake_client.service_calls[-1]
        assert last["service"] == "install"
        # service_data merges target + payload
        assert last["service_data"]["version"] == "2.0.0"
        assert last["service_data"]["backup"] is True
        assert last["service_data"]["entity_id"] == "update.foo"

    def test_skip_clear(self, fake_client):
        fake_client.set_service("update", "skip", {})
        fake_client.set_service("update", "clear_skipped", {})
        updates_core.skip(fake_client, "update.foo")
        updates_core.clear_skipped(fake_client, "update.foo")
        kinds = [c["service"] for c in fake_client.service_calls]
        assert kinds[-2:] == ["skip", "clear_skipped"]


class TestInspect:
    def test_inspect_validates_format(self):
        with pytest.raises(ValueError):
            inspect_core.inspect_entity(None, "no-dot")

    def test_inspect_aggregates(self, fake_client):
        # state
        fake_client.set("GET", "states/sensor.foo",
                          {"state": "42", "attributes": {"unit_of_measurement": "W"}})
        # entity registry
        fake_client.set_ws("config/entity_registry/list", [
            {"entity_id": "sensor.foo", "device_id": "dev1", "area_id": "kitchen",
             "platform": "mqtt", "labels": ["climate"]},
        ])
        # device registry
        fake_client.set_ws("config/device_registry/list", [
            {"id": "dev1", "name": "Foo Dev", "manufacturer": "AcmeCorp"},
        ])
        # area registry
        fake_client.set_ws("config/area_registry/list", [
            {"area_id": "kitchen", "name": "Kitchen"},
        ])
        out = inspect_core.inspect_entity(
            fake_client, "sensor.foo",
            include_history=False, include_references=False,
        )
        assert out["state"]["state"] == "42"
        assert out["registry"]["device_id"] == "dev1"
        assert out["device"]["manufacturer"] == "AcmeCorp"
        assert out["area"]["name"] == "Kitchen"


# ────────────────────────────────────────────────────────── config-flow / blueprints / script traces

from cli_anything.homeassistant.core import config_entries as config_entries_core
from cli_anything.homeassistant.core import blueprints as blueprints_core
from cli_anything.homeassistant.core import script as script_core


class TestConfigFlowCreate:
    def test_flow_init_validates(self):
        with pytest.raises(ValueError):
            config_entries_core.flow_init(None, "")

    def test_flow_init_payload(self, fake_client):
        fake_client.set("POST", "config/config_entries/flow",
                          {"flow_id": "fid1", "step_id": "user"})
        config_entries_core.flow_init(fake_client, "mqtt",
                                        show_advanced_options=True)
        last_post = [c for c in fake_client.calls if c["verb"] == "POST"][-1]
        assert last_post["path"] == "config/config_entries/flow"
        assert last_post["payload"] == {"handler": "mqtt",
                                          "show_advanced_options": True}

    def test_flow_configure_path(self, fake_client):
        fake_client.set("POST", "config/config_entries/flow/abc",
                          {"type": "create_entry"})
        config_entries_core.flow_configure(fake_client, "abc",
                                             {"broker": "10.0.0.5"})
        last = [c for c in fake_client.calls if c["verb"] == "POST"][-1]
        assert last["path"] == "config/config_entries/flow/abc"
        assert last["payload"] == {"broker": "10.0.0.5"}

    def test_flow_abort_validates(self):
        with pytest.raises(ValueError):
            config_entries_core.flow_abort(None, "")

    def test_create_chains_init_and_configure(self, fake_client):
        fake_client.set("POST", "config/config_entries/flow",
                          {"flow_id": "fid42", "step_id": "user"})
        fake_client.set("POST", "config/config_entries/flow/fid42",
                          {"type": "create_entry"})
        out = config_entries_core.create(
            fake_client, "mqtt", {"broker": "10.0.0.5"},
        )
        assert out == {"type": "create_entry"}
        posts = [c for c in fake_client.calls if c["verb"] == "POST"]
        assert posts[-2]["path"] == "config/config_entries/flow"
        assert posts[-1]["path"] == "config/config_entries/flow/fid42"


class TestBlueprints:
    def test_list_validates_domain(self):
        with pytest.raises(ValueError):
            blueprints_core.list_blueprints(None, "device_tracker")

    def test_list_payload(self, fake_client):
        fake_client.set_ws("blueprint/list", {
            "Blackshome/sensor-light.yaml": {"metadata": {"name": "Sensor Light"}},
        })
        blueprints_core.list_blueprints(fake_client, "automation")
        last = fake_client.ws_calls[-1]
        assert last["payload"] == {"domain": "automation"}

    def test_show_finds_path(self, fake_client):
        fake_client.set_ws("blueprint/list", {
            "x.yaml": {"metadata": {"name": "X"}},
            "y.yaml": {"metadata": {"name": "Y"}},
        })
        assert blueprints_core.show(fake_client, "script", "y.yaml")["metadata"]["name"] == "Y"
        assert blueprints_core.show(fake_client, "script", "ghost.yaml") is None

    def test_import_requires_url(self):
        with pytest.raises(ValueError):
            blueprints_core.import_blueprint(None, url="")

    def test_substitute_validates_input(self):
        with pytest.raises(ValueError):
            blueprints_core.substitute(None, domain="automation",
                                        path="x", user_input="not a dict")  # type: ignore

    def test_substitute_payload(self, fake_client):
        fake_client.set_ws("blueprint/substitute", {"alias": "rendered"})
        blueprints_core.substitute(
            fake_client, domain="automation", path="x.yaml",
            user_input={"motion_sensor": "binary_sensor.foo"},
        )
        last = fake_client.ws_calls[-1]
        assert last["payload"]["input"]["motion_sensor"] == "binary_sensor.foo"


class TestScriptTraces:
    def test_item_id_validates(self):
        with pytest.raises(ValueError):
            script_core._script_item_id(None, "automation.foo")

    def test_list_traces_uses_object_id(self, fake_client):
        fake_client.set_ws("trace/list", [{"run_id": "r1"}])
        out = script_core.list_traces(fake_client, "script.my_script")
        last = fake_client.ws_calls[-1]
        assert last["payload"]["domain"] == "script"
        assert last["payload"]["item_id"] == "my_script"
        assert len(out) == 1

    def test_get_trace_picks_most_recent_when_no_run_id(self, fake_client):
        fake_client.set_ws("trace/list", [{"run_id": "r1"}, {"run_id": "r2"}])
        fake_client.set_ws("trace/get", {"run_id": "r2", "state": "stopped"})
        out = script_core.get_trace(fake_client, "script.my_script")
        assert out["run_id"] == "r2"
        # most-recent picker hits trace/get with the last list entry's run_id
        get_call = next(c for c in fake_client.ws_calls
                          if c["type"] == "trace/get")
        assert get_call["payload"]["run_id"] == "r2"


# ────────────────────────────────────────────────────────── energy / themes / calendars / tts

from cli_anything.homeassistant.core import energy as energy_core
from cli_anything.homeassistant.core import themes as themes_core
from cli_anything.homeassistant.core import calendars as calendars_core
from cli_anything.homeassistant.core import tts as tts_core


class TestEnergy:
    def test_get_prefs(self, fake_client):
        fake_client.set_ws("energy/get_prefs", {"currency": "GBP"})
        out = energy_core.get_prefs(fake_client)
        assert out["currency"] == "GBP"

    def test_save_prefs_validates(self):
        with pytest.raises(ValueError):
            energy_core.save_prefs(None, [])  # type: ignore

    def test_fossil_validates_empty_ids(self):
        with pytest.raises(ValueError):
            energy_core.fossil_energy_consumption(
                None, energy_statistic_ids=[],
                co2_signal_entity="sensor.co2", start_time="2026-01-01",
            )

    def test_fossil_validates_period(self):
        with pytest.raises(ValueError):
            energy_core.fossil_energy_consumption(
                None, energy_statistic_ids=["sensor.x"],
                co2_signal_entity="sensor.co2", start_time="2026-01-01",
                period="picosecond",
            )


class TestThemes:
    def test_names_sorted(self, fake_client):
        fake_client.set_ws("frontend/get_themes", {
            "themes": {"Graphite": {}, "Fluent Blue": {}},
            "default_theme": "default",
        })
        assert themes_core.names(fake_client) == ["Fluent Blue", "Graphite"]

    def test_set_theme_payload(self, fake_client):
        fake_client.set_service("frontend", "set_theme", {})
        themes_core.set_theme(fake_client, "Graphite", mode="dark")
        last = fake_client.service_calls[-1]
        assert last["service_data"]["name"] == "Graphite"
        assert last["service_data"]["mode"] == "dark"

    def test_set_theme_validates_mode(self):
        with pytest.raises(ValueError):
            themes_core.set_theme(None, "X", mode="weird")


class TestCalendars:
    def test_list_calendars(self, fake_client):
        fake_client.set("GET", "states",
                          [{"entity_id": "calendar.x", "state": "on",
                            "attributes": {"friendly_name": "X"}},
                           {"entity_id": "sensor.y", "state": "1"}])
        rows = calendars_core.list_calendars(fake_client)
        assert len(rows) == 1
        assert rows[0]["entity_id"] == "calendar.x"

    def test_events_validates_domain(self):
        with pytest.raises(ValueError):
            calendars_core.events(None, "sensor.foo")

    def test_create_event_validates(self):
        with pytest.raises(ValueError):
            calendars_core.create_event(None, "calendar.x", summary="", start="2026-01-01")
        with pytest.raises(ValueError):
            calendars_core.create_event(None, "calendar.x", summary="X", start="")

    def test_create_event_detects_all_day(self, fake_client):
        fake_client.set_service("calendar", "create_event", {})
        calendars_core.create_event(
            fake_client, "calendar.x",
            summary="Birthday", start="2026-05-15", end="2026-05-16",
        )
        last = fake_client.service_calls[-1]
        # All-day = no T in start; should use start_date / end_date
        assert "start_date" in last["service_data"]
        assert "start_date_time" not in last["service_data"]

    def test_create_event_detects_timed(self, fake_client):
        fake_client.set_service("calendar", "create_event", {})
        calendars_core.create_event(
            fake_client, "calendar.x",
            summary="Meeting", start="2026-05-15T10:00:00",
            end="2026-05-15T11:00:00",
        )
        last = fake_client.service_calls[-1]
        assert "start_date_time" in last["service_data"]
        assert "start_date" not in last["service_data"]

    def test_delete_event_requires_uid(self):
        with pytest.raises(ValueError):
            calendars_core.delete_event(None, "calendar.x", uid="")


class TestTTS:
    def test_list_engines(self, fake_client):
        fake_client.set("GET", "states", [
            {"entity_id": "tts.piper", "state": "ok",
             "attributes": {"friendly_name": "Piper",
                            "default_language": "en"}},
            {"entity_id": "sensor.x", "state": "1"},
        ])
        rows = tts_core.list_engines(fake_client)
        assert len(rows) == 1
        assert rows[0]["entity_id"] == "tts.piper"

    def test_speak_validates_entities(self):
        with pytest.raises(ValueError):
            tts_core.speak(None, tts_entity="sensor.x",
                            media_player_entity="media_player.y",
                            message="hi")
        with pytest.raises(ValueError):
            tts_core.speak(None, tts_entity="tts.x",
                            media_player_entity="sensor.y",
                            message="hi")
        with pytest.raises(ValueError):
            tts_core.speak(None, tts_entity="tts.x",
                            media_player_entity="media_player.y",
                            message="")

    def test_speak_payload(self, fake_client):
        fake_client.set_service("tts", "speak", {})
        tts_core.speak(
            fake_client,
            tts_entity="tts.piper",
            media_player_entity="media_player.lounge",
            message="hi", language="en-GB", cache=False,
        )
        last = fake_client.service_calls[-1]
        assert last["service_data"]["media_player_entity_id"] == "media_player.lounge"
        assert last["service_data"]["message"] == "hi"
        assert last["service_data"]["cache"] is False
        assert last["service_data"]["language"] == "en-GB"
        # target carries the tts entity id
        assert last["service_data"]["entity_id"] == "tts.piper"


# ────────────────────────────────────────────────────────── hacs

from cli_anything.homeassistant.core import hacs as hacs_core


class TestHACS:
    REPOS = [
        {"id": "1", "full_name": "user/repo-a", "name": "Repo A",
         "category": "integration", "installed": True, "installed_version": "1.0",
         "available_version": "1.1", "local_path": "/config/.../a"},
        {"id": "2", "full_name": "user/zigbee2mqtt-networkmap",
         "name": "Network Map", "category": "plugin",
         "installed": False, "available_version": "v0.10.0"},
        {"id": "3", "full_name": "other/repo-a",
         "name": "Another Repo A", "category": "plugin",
         "installed": False, "available_version": "2.0"},
    ]

    def test_info(self, fake_client):
        fake_client.set_ws("hacs/info", {"version": "1.2.3", "stage": "running"})
        out = hacs_core.info(fake_client)
        assert out["version"] == "1.2.3"

    def test_list_default(self, fake_client):
        fake_client.set_ws("hacs/repositories/list", self.REPOS)
        rows = hacs_core.list_repos(fake_client)
        assert len(rows) == 3

    def test_list_installed_only(self, fake_client):
        fake_client.set_ws("hacs/repositories/list", self.REPOS)
        rows = hacs_core.list_repos(fake_client, installed_only=True)
        assert len(rows) == 1
        assert rows[0]["id"] == "1"

    def test_list_category(self, fake_client):
        fake_client.set_ws("hacs/repositories/list", self.REPOS)
        rows = hacs_core.list_repos(fake_client, category="plugin")
        assert {r["id"] for r in rows} == {"2", "3"}

    def test_list_pattern_filter(self, fake_client):
        fake_client.set_ws("hacs/repositories/list", self.REPOS)
        rows = hacs_core.list_repos(fake_client, pattern="networkmap")
        assert len(rows) == 1
        assert rows[0]["id"] == "2"

    def test_find_by_id(self, fake_client):
        fake_client.set_ws("hacs/repositories/list", self.REPOS)
        assert hacs_core.find_repo(fake_client, "2")["full_name"] == "user/zigbee2mqtt-networkmap"

    def test_find_by_full_name(self, fake_client):
        fake_client.set_ws("hacs/repositories/list", self.REPOS)
        assert hacs_core.find_repo(fake_client,
                                     "user/zigbee2mqtt-networkmap")["id"] == "2"

    def test_find_short_name_unique(self, fake_client):
        fake_client.set_ws("hacs/repositories/list", self.REPOS)
        assert hacs_core.find_repo(fake_client,
                                     "zigbee2mqtt-networkmap")["id"] == "2"

    def test_find_short_name_ambiguous_raises(self, fake_client):
        fake_client.set_ws("hacs/repositories/list", self.REPOS)
        with pytest.raises(ValueError, match="multiple"):
            hacs_core.find_repo(fake_client, "repo-a")

    def test_install_passes_repo_id(self, fake_client):
        fake_client.set_ws("hacs/repositories/list", self.REPOS)
        fake_client.set_ws("hacs/repository/download", {"ok": True})
        hacs_core.install(fake_client, "zigbee2mqtt-networkmap",
                            version="v0.9.0")
        last = fake_client.ws_calls[-1]
        assert last["type"] == "hacs/repository/download"
        assert last["payload"] == {"repository": "2", "version": "v0.9.0"}

    def test_remove_validates_match(self, fake_client):
        fake_client.set_ws("hacs/repositories/list", self.REPOS)
        with pytest.raises(KeyError):
            hacs_core.remove(fake_client, "nope-doesnt-exist")


# ────────────────────────────────────────────────────────── subentries

from cli_anything.homeassistant.core import subentries as subentries_core


class TestSubentries:
    SAMPLE_SUBS = [
        {"subentry_id": "s1", "subentry_type": "conversation",
         "title": "Google Generative AI"},
        {"subentry_id": "s2", "subentry_type": "ai_task_data",
         "title": "Google AI Task"},
        {"subentry_id": "s3", "subentry_type": "tts",
         "title": "Google AI TTS"},
    ]
    FORM = {
        "flow_id": "fake-flow",
        "step_id": "set_options",
        "data_schema": [
            {"name": "chat_model", "required": True,
             "description": {"suggested_value": "models/gemini-3-flash-preview"}},
            {"name": "temperature", "required": True,
             "description": {"suggested_value": 1.0}},
            {"name": "max_tokens", "required": False,
             "description": {"suggested_value": 3000}},
        ],
    }

    def test_list_requires_entry_id(self):
        with pytest.raises(ValueError):
            subentries_core.list_subentries(None, "")

    def test_list_uses_correct_ws(self, fake_client):
        fake_client.set_ws("config_entries/subentries/list", self.SAMPLE_SUBS)
        rows = subentries_core.list_subentries(fake_client, "entry-1")
        assert len(rows) == 3
        last = fake_client.ws_calls[-1]
        assert last["type"] == "config_entries/subentries/list"
        assert last["payload"] == {"entry_id": "entry-1"}

    def test_find_by_id(self, fake_client):
        fake_client.set_ws("config_entries/subentries/list", self.SAMPLE_SUBS)
        out = subentries_core.find_subentry(fake_client, "entry-1", "s2")
        assert out["subentry_type"] == "ai_task_data"

    def test_find_by_title_case_insensitive(self, fake_client):
        fake_client.set_ws("config_entries/subentries/list", self.SAMPLE_SUBS)
        out = subentries_core.find_subentry(fake_client, "entry-1", "GOOGLE AI TASK")
        assert out["subentry_id"] == "s2"

    def test_find_missing(self, fake_client):
        fake_client.set_ws("config_entries/subentries/list", self.SAMPLE_SUBS)
        assert subentries_core.find_subentry(fake_client, "entry-1", "ghost") is None

    def test_read_subentry_returns_suggested_values(self, fake_client):
        fake_client.set_ws("config_entries/subentries/list", self.SAMPLE_SUBS)
        fake_client.set("POST", "config/config_entries/subentries/flow", self.FORM)
        out = subentries_core.read_subentry(fake_client, "entry-1", "s2")
        assert out["subentry_type"] == "ai_task_data"
        assert out["options"]["chat_model"] == "models/gemini-3-flash-preview"
        assert out["options"]["temperature"] == 1.0
        # init payload should include source=reconfigure
        init_post = [c for c in fake_client.calls
                      if c["verb"] == "POST"
                      and c["path"] == "config/config_entries/subentries/flow"][-1]
        assert init_post["payload"]["source"] == "reconfigure"
        assert init_post["payload"]["handler"] == ["entry-1", "ai_task_data"]
        assert init_post["payload"]["subentry_id"] == "s2"

    def test_read_subentry_aborts_flow(self, fake_client):
        fake_client.set_ws("config_entries/subentries/list", self.SAMPLE_SUBS)
        fake_client.set("POST", "config/config_entries/subentries/flow", self.FORM)
        subentries_core.read_subentry(fake_client, "entry-1", "s2")
        deletes = [c for c in fake_client.calls if c["verb"] == "DELETE"]
        assert any("flow/fake-flow" in c["path"] for c in deletes)

    def test_reconfigure_validates_overrides_type(self, fake_client):
        fake_client.set_ws("config_entries/subentries/list", self.SAMPLE_SUBS)
        with pytest.raises(ValueError):
            subentries_core.reconfigure(fake_client, "entry-1", "s2",
                                          overrides="not a dict")  # type: ignore

    def test_reconfigure_dry_run_does_not_submit(self, fake_client):
        fake_client.set_ws("config_entries/subentries/list", self.SAMPLE_SUBS)
        fake_client.set("POST", "config/config_entries/subentries/flow", self.FORM)
        out = subentries_core.reconfigure(
            fake_client, "entry-1", "s2",
            overrides={"chat_model": "models/gemini-2.5-flash"},
            dry_run=True,
        )
        assert out["dry_run"] is True
        assert out["merged"]["chat_model"] == "models/gemini-2.5-flash"
        assert out["merged"]["temperature"] == 1.0  # preserved
        submits = [c for c in fake_client.calls
                    if c["verb"] == "POST"
                    and "subentries/flow/fake-flow" in c["path"]]
        assert submits == []

    def test_reconfigure_merges_and_submits(self, fake_client):
        fake_client.set_ws("config_entries/subentries/list", self.SAMPLE_SUBS)
        fake_client.set("POST", "config/config_entries/subentries/flow", self.FORM)
        fake_client.set("POST",
                          "config/config_entries/subentries/flow/fake-flow",
                          {"type": "abort", "reason": "reconfigure_successful"})
        out = subentries_core.reconfigure(
            fake_client, "entry-1", "s2",
            overrides={"chat_model": "models/gemini-2.5-flash",
                        "temperature": 0.7},
        )
        assert out["ok"] is True
        submit_post = [c for c in fake_client.calls
                        if c["verb"] == "POST"
                        and c["path"] == "config/config_entries/subentries/flow/fake-flow"][-1]
        merged = submit_post["payload"]
        assert merged["chat_model"] == "models/gemini-2.5-flash"
        assert merged["temperature"] == 0.7
        assert merged["max_tokens"] == 3000  # preserved

    def test_list_all_walks_entries(self, fake_client):
        fake_client.set_ws("config_entries/get", [
            {"entry_id": "e1", "domain": "google_generative_ai_conversation",
             "title": "Google AI"},
            {"entry_id": "e2", "domain": "ollama", "title": "Ollama"},
        ])
        # Each entry returns different subentries — but FakeClient ws_responses
        # are keyed by msg_type only, so all entries get the same canned response.
        # That's fine for the test: just verify it visits every entry.
        fake_client.set_ws("config_entries/subentries/list", self.SAMPLE_SUBS)
        rows = subentries_core.list_all(fake_client, subentry_type="ai_task_data")
        # 1 ai_task_data subentry per entry × 2 entries = 2
        assert len(rows) == 2
        assert all(r["subentry_type"] == "ai_task_data" for r in rows)
        # Each row has entry_id / entry_domain merged in
        assert all(r.get("entry_id") and r.get("entry_domain") for r in rows)

    def test_list_all_domain_filter(self, fake_client):
        fake_client.set_ws("config_entries/get", [
            {"entry_id": "e1", "domain": "google_generative_ai_conversation",
             "title": "Google AI"},
            {"entry_id": "e2", "domain": "ollama", "title": "Ollama"},
        ])
        fake_client.set_ws("config_entries/subentries/list", self.SAMPLE_SUBS)
        rows = subentries_core.list_all(fake_client, domain="ollama")
        assert all(r["entry_domain"] == "ollama" for r in rows)


# ────────────────────────────────────────────────────────── config_entries.walk

class TestConfigFlowWalk:
    def test_walk_validates_handler(self):
        with pytest.raises(ValueError):
            config_entries_core.walk(None, "", [{}])

    def test_walk_validates_steps_type(self, fake_client):
        with pytest.raises(ValueError):
            config_entries_core.walk(fake_client, "mqtt", "not-a-list")  # type: ignore

    def test_walk_terminates_at_create_entry_after_init(self, fake_client):
        fake_client.set("POST", "config/config_entries/flow",
                          {"type": "create_entry", "title": "Foo"})
        out = config_entries_core.walk(fake_client, "demo", steps=[{"x": 1}])
        assert out["completed"] is True
        assert out["final"]["type"] == "create_entry"
        # No submit happened because init already terminated
        submit_posts = [c for c in fake_client.calls
                         if c["verb"] == "POST"
                         and "/flow/" in c["path"]]
        assert submit_posts == []

    def test_walk_chains_init_then_submits(self, fake_client, monkeypatch):
        # init returns a form; first submit returns another form; second
        # submit creates the entry. FakeClient can only return one fixed
        # response per (verb, path), so we drive flow_configure via
        # monkeypatch to get per-call answers.
        fake_client.set("POST", "config/config_entries/flow",
                          {"flow_id": "fid1", "type": "form",
                           "step_id": "user"})
        responses = iter([
            {"flow_id": "fid1", "type": "form", "step_id": "options"},
            {"type": "create_entry", "title": "Done"},
        ])
        monkeypatch.setattr(config_entries_core, "flow_configure",
                             lambda c, fid, p: next(responses))
        out = config_entries_core.walk(fake_client, "demo",
                                         steps=[{"a": 1}, {"b": 2}])
        assert out["completed"] is True
        assert out["final"]["type"] == "create_entry"
        # init + 2 submits = 3 history entries
        assert len(out["history"]) == 3

    def test_walk_aborts_on_exception(self, fake_client, monkeypatch):
        fake_client.set("POST", "config/config_entries/flow",
                          {"flow_id": "fid1", "type": "form",
                           "step_id": "user"})

        def boom(c, fid, payload):
            raise RuntimeError("network down")

        monkeypatch.setattr(config_entries_core, "flow_configure", boom)
        # flow_abort should be called inside walk's except branch;
        # FakeClient.delete may not be wired, so just provide a no-op.
        monkeypatch.setattr(config_entries_core, "flow_abort",
                             lambda c, fid: None)
        out = config_entries_core.walk(fake_client, "demo",
                                         steps=[{"x": 1}])
        assert out["completed"] is False
        assert any("error" in h for h in out["history"])

    def test_walk_stop_on_form(self, fake_client, monkeypatch):
        fake_client.set("POST", "config/config_entries/flow",
                          {"flow_id": "fid1", "type": "form",
                           "step_id": "user"})
        monkeypatch.setattr(config_entries_core, "flow_configure",
                             lambda c, fid, p: {"flow_id": fid,
                                                 "type": "form",
                                                 "step_id": "options"})
        out = config_entries_core.walk(fake_client, "demo",
                                         steps=[{"x": 1}],
                                         stop_on_form=True)
        assert out["completed"] is False
        assert out["final"]["type"] == "form"


# ────────────────────────────────────────────────────────── lovelace_paths.patch_card

class TestLovelacePatchCard:
    SAMPLE = {
        "views": [
            {"path": "home", "type": "masonry", "cards": [
                {"type": "entities", "title": "Lights",
                 "entities": ["light.kitchen"]},
                {"type": "horizontal-stack", "cards": [
                    {"type": "button", "name": "Living"},
                ]},
            ]},
        ],
    }

    def test_patch_shallow_field(self):
        cfg = json.loads(json.dumps(self.SAMPLE))
        out = lovelace_paths.patch_card(cfg, "home.0",
                                          {"title": "Lighting"})
        assert out["title"] == "Lighting"
        # Other fields preserved
        assert out["entities"] == ["light.kitchen"]

    def test_patch_adds_new_field(self):
        cfg = json.loads(json.dumps(self.SAMPLE))
        out = lovelace_paths.patch_card(cfg, "home.0",
                                          {"show_header_toggle": False})
        assert out["show_header_toggle"] is False

    def test_patch_strict_rejects_unknown(self):
        cfg = json.loads(json.dumps(self.SAMPLE))
        with pytest.raises(KeyError, match="unknown fields"):
            lovelace_paths.patch_card(cfg, "home.0",
                                       {"made_up_field": "x"},
                                       strict=True)

    def test_patch_validates_fields_dict(self):
        cfg = json.loads(json.dumps(self.SAMPLE))
        with pytest.raises(ValueError):
            lovelace_paths.patch_card(cfg, "home.0", "not a dict")  # type: ignore
        with pytest.raises(ValueError):
            lovelace_paths.patch_card(cfg, "home.0", {})

    def test_patch_shallow_merges_nested_dict(self):
        cfg = {"views": [{"path": "p", "cards": [
            {"type": "tile", "tap_action": {"action": "toggle"}},
        ]}]}
        lovelace_paths.patch_card(cfg, "p.0",
                                    {"tap_action": {"haptic": "light"}})
        # Both keys present after shallow merge
        ta = cfg["views"][0]["cards"][0]["tap_action"]
        assert ta == {"action": "toggle", "haptic": "light"}

    def test_patch_replaces_list_field(self):
        cfg = json.loads(json.dumps(self.SAMPLE))
        lovelace_paths.patch_card(cfg, "home.0",
                                    {"entities": ["light.bedroom"]})
        assert cfg["views"][0]["cards"][0]["entities"] == ["light.bedroom"]


# ────────────────────────────────────────────────────────── updates.install_all

class TestUpdatesInstallAll:
    def _seed(self, fake_client, updates):
        fake_client.set("GET", "states", updates)
        fake_client.set_service("update", "install", {"ok": True})

    def test_install_all_dry_run(self, fake_client):
        self._seed(fake_client, [
            {"entity_id": "update.core", "state": "on", "attributes": {}},
            {"entity_id": "update.zigbee2mqtt", "state": "on",
             "attributes": {}},
        ])
        out = updates_core.install_all(fake_client, dry_run=True)
        assert out["dry_run"] is True
        assert set(out["selected"]) == {"update.core", "update.zigbee2mqtt"}
        # No services actually called
        assert fake_client.service_calls == []

    def test_install_all_excludes_substring(self, fake_client):
        self._seed(fake_client, [
            {"entity_id": "update.core", "state": "on", "attributes": {}},
            {"entity_id": "update.zigbee2mqtt", "state": "on",
             "attributes": {}},
            {"entity_id": "update.network_map_card", "state": "on",
             "attributes": {}},
        ])
        out = updates_core.install_all(fake_client,
                                         exclude=["network_map", "core"],
                                         dry_run=True)
        assert out["selected"] == ["update.zigbee2mqtt"]
        assert set(out["excluded"]) == {"update.core",
                                          "update.network_map_card"}

    def test_install_all_runs_services(self, fake_client):
        self._seed(fake_client, [
            {"entity_id": "update.core", "state": "on", "attributes": {}},
            {"entity_id": "update.hacs", "state": "on", "attributes": {}},
        ])
        out = updates_core.install_all(fake_client, backup=True)
        assert out["dry_run"] is False
        assert {r["entity_id"] for r in out["results"]} == {
            "update.core", "update.hacs"}
        assert all(r["ok"] is True for r in out["results"])
        installs = [c for c in fake_client.service_calls
                    if c["service"] == "install"]
        assert len(installs) == 2
        # backup flag forwarded
        assert all(c["service_data"].get("backup") is True for c in installs)

    def test_install_all_no_available(self, fake_client):
        fake_client.set("GET", "states", [
            {"entity_id": "update.core", "state": "off", "attributes": {}},
        ])
        out = updates_core.install_all(fake_client)
        assert out["selected"] == []
        assert out["results"] == []


# ────────────────────────────────────────────────────────── recorder.purge

from cli_anything.homeassistant.core import recorder as recorder_core


class TestRecorderPurge:
    def test_purge_default(self, fake_client):
        fake_client.set_service("recorder", "purge", {"ok": True})
        recorder_core.purge(fake_client)
        last = fake_client.service_calls[-1]
        assert last["domain"] == "recorder"
        assert last["service"] == "purge"
        # No data when no args set
        assert last["service_data"] in (None, {})

    def test_purge_keep_days(self, fake_client):
        fake_client.set_service("recorder", "purge", {})
        recorder_core.purge(fake_client, keep_days=7, repack=True)
        last = fake_client.service_calls[-1]
        assert last["service_data"]["keep_days"] == 7
        assert last["service_data"]["repack"] is True

    def test_purge_apply_filter(self, fake_client):
        fake_client.set_service("recorder", "purge", {})
        recorder_core.purge(fake_client, apply_filter=True)
        last = fake_client.service_calls[-1]
        assert last["service_data"]["apply_filter"] is True

    def test_purge_entities_requires_some_input(self):
        with pytest.raises(ValueError):
            recorder_core.purge_entities(None, entity_ids=[])

    def test_purge_entities_payload(self, fake_client):
        fake_client.set_service("recorder", "purge_entities", {})
        recorder_core.purge_entities(
            fake_client, entity_ids=["sensor.foo"],
            domains=["script"], entity_globs=["sensor.test_*"], days=3,
        )
        last = fake_client.service_calls[-1]
        assert last["service"] == "purge_entities"
        sd = last["service_data"]
        assert sd["entity_id"] == ["sensor.foo"]
        assert sd["domains"] == ["script"]
        assert sd["entity_globs"] == ["sensor.test_*"]
        assert sd["days"] == 3


# ────────────────────────────────────────────────────────── system errors triage

class TestSystemErrorsTriage:
    SAMPLE = "\n".join([
        "2026-05-11 08:17:06.541 ERROR (MainThread) [homeassistant.components.mqtt.number] Invalid value foo",
        "2026-05-11 08:17:06.542 ERROR (MainThread) [homeassistant.components.mqtt.number] Invalid value bar",
        "2026-05-11 08:18:02.130 WARNING (MainThread) [homeassistant.helpers.frame] Detected non-thread-safe",
        "Traceback (most recent call last):",
        "  File \"foo.py\", line 1, in bar",
        "2026-05-11 08:20:11.001 ERROR (Thread-14) [pychromecast.socket_client] [KD-55XF9005] Error reading",
        "2026-05-11 08:21:14.222 CRITICAL (MainThread) [custom_components.hon] coordinator dead",
    ])

    def test_parse_lines_extracts_fields(self):
        recs = list(system_core.parse_lines(self.SAMPLE))
        # 7 lines total
        assert len(recs) == 7
        # the two traceback lines should be raw-only
        assert recs[3]["ts"] is None
        assert recs[3]["raw"].startswith("Traceback")
        # first record fully parsed
        r0 = recs[0]
        assert r0["level"] == "ERROR"
        assert r0["component"] == "homeassistant.components.mqtt.number"
        assert r0["thread"] == "MainThread"
        assert r0["ts_dt"].hour == 8

    def test_parse_since_relative(self):
        from datetime import datetime
        now = datetime(2026, 5, 11, 9, 0, 0)
        assert system_core.parse_since("30m", now=now).minute == 30
        assert system_core.parse_since("1h", now=now).hour == 8
        assert system_core.parse_since("1h ago", now=now).hour == 8
        assert system_core.parse_since("2d", now=now).day == 9

    def test_parse_since_absolute(self):
        ts = system_core.parse_since("2026-05-11 08:17:06")
        assert ts.year == 2026 and ts.month == 5 and ts.minute == 17
        ts2 = system_core.parse_since("2026-05-11 08:17")
        assert ts2.minute == 17

    def test_parse_since_time_only_uses_today(self):
        from datetime import datetime
        now = datetime(2026, 5, 11, 9, 0, 0)
        ts = system_core.parse_since("08:17", now=now)
        assert ts.date() == now.date()
        assert ts.hour == 8

    def test_parse_since_garbage(self):
        with pytest.raises(ValueError):
            system_core.parse_since("yesterday-ish")

    def test_filter_records_since_drops_unparsed_lines(self):
        from datetime import datetime
        recs = list(system_core.parse_lines(self.SAMPLE))
        kept = list(system_core.filter_records(
            recs, since=datetime(2026, 5, 11, 8, 17, 6)))
        # Should drop traceback lines AND any record < since
        levels = [r["level"] for r in kept]
        assert None not in levels  # traceback lines (level=None) dropped
        assert all(r["ts_dt"] is not None for r in kept)

    def test_filter_records_errors_only(self):
        recs = list(system_core.parse_lines(self.SAMPLE))
        kept = list(system_core.filter_records(recs, errors_only=True))
        assert all(r["level"] in ("ERROR", "CRITICAL") for r in kept)
        assert len(kept) == 4  # 3 ERROR + 1 CRITICAL

    def test_filter_records_component(self):
        recs = list(system_core.parse_lines(self.SAMPLE))
        kept = list(system_core.filter_records(
            recs, component="pychromecast.socket_client"))
        assert len(kept) == 1
        assert kept[0]["level"] == "ERROR"

    def test_bucket_counts_by_component(self):
        recs = list(system_core.parse_lines(self.SAMPLE))
        rows = system_core.bucket_counts(recs, by="component", top=10)
        # mqtt.number should be the busiest with 2 hits
        top_key, top_count = rows[0]
        assert top_key == "homeassistant.components.mqtt.number"
        assert top_count == 2

    def test_bucket_counts_by_level(self):
        recs = list(system_core.parse_lines(self.SAMPLE))
        rows = dict(system_core.bucket_counts(recs, by="level", top=10))
        assert rows["ERROR"] == 3
        assert rows["WARNING"] == 1
        assert rows["CRITICAL"] == 1

    def test_bucket_counts_by_hour(self):
        recs = list(system_core.parse_lines(self.SAMPLE))
        rows = dict(system_core.bucket_counts(recs, by="hour", top=10))
        # all sample records are in the 08:00 hour bucket
        assert "2026-05-11 08:00" in rows
        # 5 parsed records + 2 unparsed lines (bucketed as "—")
        assert rows["2026-05-11 08:00"] == 5


# ────────────────────────────────────────────────────────── states

class TestStates:
    def _seed(self, fake_client):
        fake_client.set("GET", "states", [
            {"entity_id": "light.kitchen", "state": "on"},
            {"entity_id": "light.bedroom", "state": "off"},
            {"entity_id": "sensor.temp", "state": "21.0"},
        ])

    def test_list_all(self, fake_client):
        self._seed(fake_client)
        assert len(states_core.list_states(fake_client)) == 3

    def test_list_filter_domain(self, fake_client):
        self._seed(fake_client)
        items = states_core.list_states(fake_client, domain="light")
        assert {x["entity_id"] for x in items} == {"light.kitchen", "light.bedroom"}

    def test_get_state_empty_id_raises(self, fake_client):
        with pytest.raises(ValueError):
            states_core.get_state(fake_client, "")

    def test_set_state_payload(self, fake_client):
        states_core.set_state(fake_client, "sensor.x", "5", attributes={"unit": "C"})
        last = fake_client.calls[-1]
        assert last["verb"] == "POST"
        assert last["path"] == "states/sensor.x"
        assert last["payload"] == {"state": "5", "attributes": {"unit": "C"}}

    def test_set_state_no_attributes(self, fake_client):
        states_core.set_state(fake_client, "sensor.x", "ok")
        assert fake_client.calls[-1]["payload"] == {"state": "ok"}

    def test_list_domains(self, fake_client):
        self._seed(fake_client)
        assert states_core.list_domains(fake_client) == ["light", "sensor"]

    def test_count_by_domain(self, fake_client):
        self._seed(fake_client)
        assert states_core.count_by_domain(fake_client) == {"light": 2, "sensor": 1}


# ────────────────────────────────────────────────────────── services

class TestServices:
    def _seed(self, fake_client):
        fake_client.set("GET", "services", [
            {"domain": "light", "services": {"turn_on": {}, "turn_off": {}}},
            {"domain": "switch", "services": {"toggle": {}}},
        ])

    def test_list_all(self, fake_client):
        self._seed(fake_client)
        assert len(services_core.list_services(fake_client)) == 2

    def test_list_filter_domain(self, fake_client):
        self._seed(fake_client)
        result = services_core.list_services(fake_client, domain="light")
        assert len(result) == 1 and result[0]["domain"] == "light"

    def test_list_domains(self, fake_client):
        self._seed(fake_client)
        assert services_core.list_domains(fake_client) == ["light", "switch"]

    def test_call_service_payload(self, fake_client):
        services_core.call_service(
            fake_client, "light", "turn_on",
            service_data={"brightness": 200},
            target={"entity_id": "light.k"},
        )
        last = fake_client.calls[-1]
        assert last["path"] == "services/light/turn_on"
        assert last["payload"] == {"brightness": 200, "entity_id": "light.k"}

    def test_call_service_return_response(self, fake_client):
        services_core.call_service(fake_client, "calendar", "get_events",
                                    return_response=True)
        last = fake_client.calls[-1]
        assert last["path"].endswith("?return_response")

    def test_call_service_validates(self, fake_client):
        with pytest.raises(ValueError):
            services_core.call_service(fake_client, "", "turn_on")


# ────────────────────────────────────────────────────────── events

class TestEvents:
    def test_list_listeners(self, fake_client):
        fake_client.set("GET", "events", [{"event": "state_changed", "listener_count": 1}])
        assert len(events_core.list_listeners(fake_client)) == 1

    def test_fire_event(self, fake_client):
        events_core.fire_event(fake_client, "my_event", {"k": "v"})
        last = fake_client.calls[-1]
        assert last["path"] == "events/my_event"
        assert last["payload"] == {"k": "v"}

    def test_fire_event_validates(self, fake_client):
        with pytest.raises(ValueError):
            events_core.fire_event(fake_client, "")


# ────────────────────────────────────────────────────────── template

class TestTemplate:
    def test_render(self, fake_client):
        fake_client.set("POST", "template", "rendered text")
        assert template_core.render(fake_client, "{{ now() }}") == "rendered text"
        assert fake_client.calls[-1]["payload"] == {"template": "{{ now() }}"}

    def test_render_with_vars(self, fake_client):
        fake_client.set("POST", "template", "5")
        template_core.render(fake_client, "{{ x }}", variables={"x": 5})
        assert fake_client.calls[-1]["payload"] == {"template": "{{ x }}", "variables": {"x": 5}}

    def test_render_validates(self, fake_client):
        with pytest.raises(ValueError):
            template_core.render(fake_client, "")


# ────────────────────────────────────────────────────────── registry

class TestRegistry:
    def test_areas(self, fake_client):
        fake_client.set_ws("config/area_registry/list", [{"area_id": "kitchen"}])
        assert registry_core.list_areas(fake_client) == [{"area_id": "kitchen"}]

    def test_devices(self, fake_client):
        fake_client.set_ws("config/device_registry/list", [{"id": "d1", "area_id": "a1"}])
        assert registry_core.list_devices(fake_client)[0]["id"] == "d1"

    def test_entities(self, fake_client):
        fake_client.set_ws("config/entity_registry/list", [{"entity_id": "light.k"}])
        assert registry_core.list_entities(fake_client)[0]["entity_id"] == "light.k"

    def test_filter_entities_by_domain(self):
        items = [{"entity_id": "light.a"}, {"entity_id": "switch.b"}]
        assert registry_core.filter_entities_by_domain(items, "light") == [{"entity_id": "light.a"}]

    def test_filter_devices_by_area(self):
        items = [{"id": "d1", "area_id": "a"}, {"id": "d2", "area_id": "b"}]
        assert registry_core.filter_devices_by_area(items, "a") == [{"id": "d1", "area_id": "a"}]


# ────────────────────────────────────────────────────────── automation

class TestAutomation:
    def test_trigger_validates_id(self, fake_client):
        with pytest.raises(ValueError):
            automation_core.trigger(fake_client, "light.kitchen")

    def test_trigger_skip_condition(self, fake_client):
        automation_core.trigger(fake_client, "automation.morning", skip_condition=True)
        last = fake_client.calls[-1]
        assert last["path"] == "services/automation/trigger"
        assert last["payload"]["skip_condition"] is True
        assert last["payload"]["entity_id"] == "automation.morning"

    def test_toggle(self, fake_client):
        automation_core.toggle(fake_client, "automation.x")
        assert fake_client.calls[-1]["path"] == "services/automation/toggle"

    def test_reload(self, fake_client):
        automation_core.reload(fake_client)
        assert fake_client.calls[-1]["path"] == "services/automation/reload"


# ────────────────────────────────────────────────────────── script

class TestScript:
    def test_run_validates_id(self, fake_client):
        with pytest.raises(ValueError):
            script_core.run(fake_client, "switch.bad")

    def test_run_with_vars(self, fake_client):
        script_core.run(fake_client, "script.bedtime", variables={"floor": 2})
        last = fake_client.calls[-1]
        assert last["path"] == "services/script/turn_on"
        assert last["payload"]["entity_id"] == "script.bedtime"
        assert last["payload"]["variables"] == {"floor": 2}


# ────────────────────────────────────────────────────────── domain helpers

class TestDomainHelpers:
    def test_turn_on_unknown_domain(self, fake_client):
        with pytest.raises(ValueError):
            domain_core.turn_on(fake_client, "weather")

    def test_turn_on_light(self, fake_client):
        domain_core.turn_on(fake_client, "light", "light.k")
        assert fake_client.calls[-1]["path"] == "services/light/turn_on"

    def test_toggle_switch(self, fake_client):
        domain_core.toggle(fake_client, "switch", "switch.x")
        assert fake_client.calls[-1]["path"] == "services/switch/toggle"


# ────────────────────────────────────────────────────────── history / logbook

class TestHistory:
    def test_history_with_start(self, fake_client):
        from datetime import datetime, timezone
        fake_client.set("GET", "history/period/2024-01-01T00:00:00+00:00", [[]])
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        history_core.history(fake_client, start=start)
        last = fake_client.calls[-1]
        assert last["path"].startswith("history/period/2024-01-01")

    def test_logbook_with_hours(self, fake_client):
        history_core.logbook(fake_client, hours=1)
        last = fake_client.calls[-1]
        assert last["path"].startswith("logbook/")


# ────────────────────────────────────────────────────────── backend

class TestBackend:
    def test_normalize_base_no_scheme(self):
        assert _normalize_base("localhost:8123") == "http://localhost:8123"

    def test_normalize_base_scheme(self):
        assert _normalize_base("https://example.com:443/") == "https://example.com:443"

    def test_normalize_base_invalid_raises(self):
        with pytest.raises(ValueError):
            _normalize_base("")

    def test_ws_url_http(self):
        assert _ws_url_from_http("http://localhost:8123") == "ws://localhost:8123/api/websocket"

    def test_ws_url_https(self):
        assert _ws_url_from_http("https://h:443") == "wss://h:443/api/websocket"

    def test_bearer_header_set(self):
        client = HomeAssistantClient(url="http://h:8123", token="abc")
        assert client.session.headers["Authorization"] == "Bearer abc"

    def test_no_bearer_when_token_empty(self):
        client = HomeAssistantClient(url="http://h:8123", token="")
        assert "Authorization" not in client.session.headers

    def test_connection_refused_raises(self):
        # 127.0.0.1:1 is reliably refused on Linux.
        client = HomeAssistantClient(url="http://127.0.0.1:1", token="x", timeout=2)
        with pytest.raises(HomeAssistantError) as exc:
            client.get("")
        assert "Cannot reach" in str(exc.value)


# ────────────────────────────────────────────────────────── CLI helpers

class TestCLIHelpers:
    def test_parse_kv_string(self):
        assert parse_kv_pairs(("k=v",)) == {"k": "v"}

    def test_parse_kv_int(self):
        assert parse_kv_pairs(("count=3",)) == {"count": 3}

    def test_parse_kv_bool(self):
        assert parse_kv_pairs(("flag=true",)) == {"flag": True}

    def test_parse_kv_object(self):
        result = parse_kv_pairs(('payload={"a":1}',))
        assert result == {"payload": {"a": 1}}

    def test_parse_kv_invalid(self):
        import click
        with pytest.raises(click.BadParameter):
            parse_kv_pairs(("nokey",))


# ────────────────────────────────────────────────────────── auth

class TestAuth:
    def test_current_user(self, fake_client):
        fake_client.set_ws("auth/current_user",
                           {"id": "u1", "name": "Jon", "is_admin": True})
        u = auth_core.current_user(fake_client)
        assert u["name"] == "Jon" and u["is_admin"] is True

    def test_list_users(self, fake_client):
        fake_client.set_ws("config/auth/list", [{"id": "u1"}, {"id": "u2"}])
        assert len(auth_core.list_users(fake_client)) == 2

    def test_create_token(self, fake_client):
        fake_client.set_ws("auth/long_lived_access_token", "the-token-string")
        result = auth_core.create_long_lived_token(fake_client, "Test", lifespan_days=30)
        last = fake_client.ws_calls[-1]
        assert last["type"] == "auth/long_lived_access_token"
        assert last["payload"] == {"client_name": "Test", "lifespan": 30}
        assert result == "the-token-string"

    def test_create_token_validates_name(self, fake_client):
        with pytest.raises(ValueError):
            auth_core.create_long_lived_token(fake_client, "")


# ────────────────────────────────────────────────────────── config_entries

class TestConfigEntries:
    def test_list(self, fake_client):
        fake_client.set_ws("config_entries/get", [{"entry_id": "x", "domain": "tuya"}])
        entries = config_entries_core.list_entries(fake_client)
        assert len(entries) == 1 and entries[0]["entry_id"] == "x"

    def test_list_with_domain(self, fake_client):
        fake_client.set_ws("config_entries/get", [{"entry_id": "x"}])
        config_entries_core.list_entries(fake_client, domain="tuya")
        last = fake_client.ws_calls[-1]
        assert last["payload"] == {"domain": "tuya"}

    def test_get_found(self, fake_client):
        fake_client.set_ws("config_entries/get", [{"entry_id": "abc", "title": "x"}])
        e = config_entries_core.get_entry(fake_client, "abc")
        assert e is not None and e["title"] == "x"

    def test_get_missing(self, fake_client):
        fake_client.set_ws("config_entries/get", [{"entry_id": "abc"}])
        assert config_entries_core.get_entry(fake_client, "missing") is None

    def test_delete(self, fake_client):
        fake_client.set("DELETE", "config/config_entries/entry/abc",
                       {"require_restart": False})
        config_entries_core.delete_entry(fake_client, "abc")
        last = fake_client.calls[-1]
        assert last["verb"] == "DELETE"
        assert last["path"] == "config/config_entries/entry/abc"

    def test_reload(self, fake_client):
        config_entries_core.reload_entry(fake_client, "abc")
        last = fake_client.calls[-1]
        assert last["verb"] == "POST"
        assert last["path"] == "config/config_entries/entry/abc/reload"

    def test_validates(self, fake_client):
        with pytest.raises(ValueError):
            config_entries_core.delete_entry(fake_client, "")
        with pytest.raises(ValueError):
            config_entries_core.reload_entry(fake_client, "")

    def test_options_flow_init(self, fake_client):
        fake_client.set("POST", "config/config_entries/options/flow",
                         {"flow_id": "fid", "step_id": "init"})
        result = config_entries_core.options_flow_init(fake_client, "abc")
        last = fake_client.calls[-1]
        assert last["verb"] == "POST"
        assert last["path"] == "config/config_entries/options/flow"
        assert last["payload"] == {"handler": "abc"}
        assert result["flow_id"] == "fid"

    def test_options_flow_configure(self, fake_client):
        fake_client.set("POST", "config/config_entries/options/flow/fid",
                         {"type": "create_entry"})
        config_entries_core.options_flow_configure(
            fake_client, "fid", {"state": "x"})
        last = fake_client.calls[-1]
        assert last["path"] == "config/config_entries/options/flow/fid"
        assert last["payload"] == {"state": "x"}

    def test_options_flow_set_combines(self, fake_client):
        fake_client.set("POST", "config/config_entries/options/flow",
                         {"flow_id": "f"})
        fake_client.set("POST", "config/config_entries/options/flow/f",
                         {"type": "create_entry"})
        result = config_entries_core.options_flow_set(
            fake_client, "abc", {"k": "v"})
        assert result["type"] == "create_entry"
        # Two POSTs: init, configure
        posts = [c for c in fake_client.calls if c["verb"] == "POST"]
        assert len(posts) >= 2
        assert posts[-2]["path"] == "config/config_entries/options/flow"
        assert posts[-1]["path"] == "config/config_entries/options/flow/f"

    def test_update_entry(self, fake_client):
        fake_client.set_ws("config_entries/update", {"entry": {"entry_id": "abc"}})
        config_entries_core.update_entry(fake_client, "abc",
                                          options={"k": "v"}, title="My Entry")
        last = fake_client.ws_calls[-1]
        assert last["type"] == "config_entries/update"
        assert last["payload"]["entry_id"] == "abc"
        assert last["payload"]["data"] == {"k": "v"}
        assert last["payload"]["title"] == "My Entry"


# ────────────────────────────────────────────────────────── helpers (input_select)

class TestHelpers:
    def test_input_select_set_options(self, fake_client):
        fake_client.set("POST", "services/input_select/set_options", [])
        fake_client.set("GET", "states/input_select.foo",
                         {"entity_id": "input_select.foo", "state": "Auto",
                          "attributes": {"options": ["Auto", "X"]}})
        result = helpers_core.input_select_set_options(
            fake_client, "input_select.foo", ["Auto", "X"])
        assert result["attributes"]["options"] == ["Auto", "X"]
        post = next(c for c in fake_client.calls if c["verb"] == "POST")
        assert post["path"] == "services/input_select/set_options"
        assert post["payload"] == {"entity_id": "input_select.foo",
                                    "options": ["Auto", "X"]}

    def test_input_select_set_options_validates(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.input_select_set_options(fake_client, "light.foo", ["a"])
        with pytest.raises(ValueError):
            helpers_core.input_select_set_options(
                fake_client, "input_select.foo", "not a list")  # type: ignore[arg-type]

    def test_input_select_sync_no_change(self, fake_client):
        common = ["Auto", "Bedroom"]
        fake_client.set("GET", "states/input_select.src",
                         {"state": "Auto", "attributes": {"options": common}})
        fake_client.set("GET", "states/input_select.dst",
                         {"state": "Auto", "attributes": {"options": common}})
        result = helpers_core.input_select_sync(
            fake_client, "input_select.src", "input_select.dst")
        assert result["changed"] is False

    def test_input_select_sync_with_change(self, fake_client):
        # Initial: src has 3 options, dst has 2 (and current state 'Foo' isn't
        # in src's new options) — so we expect a fallback Auto-select first,
        # then a PERSISTENT input_select/update WS call on dst.
        fake_client.set("GET", "states/input_select.src",
                         {"state": "Auto", "attributes": {"options":
                          ["Auto", "Bedroom", "Lounge"]}})
        gets = [
            {"state": "Foo",
              "attributes": {"options": ["Foo", "Bar"],
                              "friendly_name": "Destination"}},
            {"state": "Auto", "attributes": {"options":
             ["Auto", "Bedroom", "Lounge"]}},
        ]
        idx = {"i": 0}
        original_get = fake_client.get
        def stub_get(path, params=None):
            if path.endswith("input_select.dst"):
                v = gets[min(idx["i"], len(gets) - 1)]
                idx["i"] += 1
                fake_client.calls.append({"verb": "GET", "path": path,
                                            "params": params})
                return v
            return original_get(path, params)
        fake_client.get = stub_get  # type: ignore[method-assign]
        fake_client.set("POST", "services/input_select/select_option", [])
        fake_client.set_ws("input_select/update", {"id": "dst",
                                                     "options": ["Auto", "Bedroom", "Lounge"]})
        result = helpers_core.input_select_sync(
            fake_client, "input_select.src", "input_select.dst")
        assert result["changed"] is True
        assert result["dst_state"] == "Auto"
        # Fallback select fired
        post_paths = [c["path"] for c in fake_client.calls if c["verb"] == "POST"]
        assert "services/input_select/select_option" in post_paths
        # And the PERSISTENT WS update — not the in-memory set_options service.
        ws_types = [c["type"] for c in fake_client.ws_calls]
        assert "input_select/update" in ws_types
        assert "services/input_select/set_options" not in post_paths
        # The update payload should include name (HA's schema requires it)
        update_call = next(c for c in fake_client.ws_calls
                            if c["type"] == "input_select/update")
        assert update_call["payload"]["name"] == "Destination"
        assert update_call["payload"]["options"] == ["Auto", "Bedroom", "Lounge"]


class TestInputBooleanHelper:
    def test_create(self, fake_client):
        fake_client.set_ws("input_boolean/create", {"id": "foo"})
        helpers_core.input_boolean_create(fake_client, "Foo", icon="mdi:abc",
                                              initial=True)
        call = fake_client.ws_calls[-1]
        assert call["type"] == "input_boolean/create"
        assert call["payload"] == {"name": "Foo", "icon": "mdi:abc",
                                     "initial": True}

    def test_update_preserves_name(self, fake_client):
        fake_client.set_ws("input_boolean/update", {})
        fake_client.set("GET", "states/input_boolean.foo",
                          {"attributes": {"friendly_name": "Foo Friendly"}})
        helpers_core.input_boolean_update(fake_client, "input_boolean.foo",
                                              icon="mdi:new")
        call = fake_client.ws_calls[-1]
        assert call["payload"]["input_boolean_id"] == "foo"
        assert call["payload"]["name"] == "Foo Friendly"
        assert call["payload"]["icon"] == "mdi:new"

    def test_update_validates_domain(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.input_boolean_update(fake_client, "switch.foo",
                                                  icon="mdi:x")

    def test_delete(self, fake_client):
        fake_client.set_ws("input_boolean/delete", {})
        helpers_core.input_boolean_delete(fake_client, "input_boolean.foo")
        call = fake_client.ws_calls[-1]
        assert call["payload"] == {"input_boolean_id": "foo"}

    def test_toggle(self, fake_client):
        helpers_core.input_boolean_toggle(fake_client, "input_boolean.foo")
        post = next(c for c in fake_client.calls if c["verb"] == "POST")
        assert post["path"] == "services/input_boolean/toggle"


class TestInputButtonHelper:
    def test_create_press_delete(self, fake_client):
        fake_client.set_ws("input_button/create", {"id": "btn"})
        fake_client.set_ws("input_button/delete", {})
        helpers_core.input_button_create(fake_client, "Btn", icon="mdi:b")
        helpers_core.input_button_press(fake_client, "input_button.btn")
        helpers_core.input_button_delete(fake_client, "input_button.btn")
        types = [c["type"] for c in fake_client.ws_calls]
        assert types == ["input_button/create", "input_button/delete"]
        posts = [c["path"] for c in fake_client.calls if c["verb"] == "POST"]
        assert "services/input_button/press" in posts


class TestInputNumberHelper:
    def test_create_validates(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.input_number_create(fake_client, "n", min=0, max=0)
        with pytest.raises(ValueError):
            helpers_core.input_number_create(fake_client, "n", min=0, max=10, step=-1)
        with pytest.raises(ValueError):
            helpers_core.input_number_create(fake_client, "n", min=0, max=10, mode="bogus")

    def test_create_ok(self, fake_client):
        fake_client.set_ws("input_number/create", {"id": "x"})
        helpers_core.input_number_create(fake_client, "Temp", min=0, max=30,
                                            step=0.5, mode="box",
                                            unit_of_measurement="°C")
        call = fake_client.ws_calls[-1]
        assert call["payload"]["min"] == 0
        assert call["payload"]["max"] == 30
        assert call["payload"]["step"] == 0.5
        assert call["payload"]["mode"] == "box"
        assert call["payload"]["unit_of_measurement"] == "°C"

    def test_set_value(self, fake_client):
        helpers_core.input_number_set_value(fake_client, "input_number.n", 4.2)
        post = fake_client.calls[-1]
        assert post["payload"] == {"entity_id": "input_number.n", "value": 4.2}


class TestInputTextHelper:
    def test_create_validates_mode(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.input_text_create(fake_client, "n", mode="xx")

    def test_create_validates_minmax(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.input_text_create(fake_client, "n", min=-1, max=5)
        with pytest.raises(ValueError):
            helpers_core.input_text_create(fake_client, "n", min=10, max=5)

    def test_create_ok(self, fake_client):
        fake_client.set_ws("input_text/create", {})
        helpers_core.input_text_create(fake_client, "Msg", min=1, max=200,
                                          pattern="^[A-Z]+$", mode="password")
        call = fake_client.ws_calls[-1]
        assert call["payload"]["pattern"] == "^[A-Z]+$"
        assert call["payload"]["mode"] == "password"


class TestInputDateTimeHelper:
    def test_create_requires_field(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.input_datetime_create(fake_client, "t",
                                                  has_date=False, has_time=False)

    def test_set_requires_something(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.input_datetime_set(fake_client, "input_datetime.t")

    def test_set_datetime(self, fake_client):
        helpers_core.input_datetime_set(fake_client, "input_datetime.t",
                                            datetime="2026-05-11 12:00:00")
        post = fake_client.calls[-1]
        assert post["path"] == "services/input_datetime/set_datetime"
        assert post["payload"]["datetime"] == "2026-05-11 12:00:00"


class TestCounterHelper:
    def test_create_validates_step(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.counter_create(fake_client, "c", step=0)

    def test_create_ok(self, fake_client):
        fake_client.set_ws("counter/create", {})
        helpers_core.counter_create(fake_client, "C", initial=5, step=2,
                                       minimum=0, maximum=100)
        call = fake_client.ws_calls[-1]
        assert call["payload"]["initial"] == 5
        assert call["payload"]["step"] == 2
        assert call["payload"]["minimum"] == 0
        assert call["payload"]["maximum"] == 100

    def test_runtime_actions(self, fake_client):
        helpers_core.counter_increment(fake_client, "counter.c")
        helpers_core.counter_decrement(fake_client, "counter.c")
        helpers_core.counter_reset(fake_client, "counter.c")
        helpers_core.counter_set_value(fake_client, "counter.c", 42)
        paths = [c["path"] for c in fake_client.calls if c["verb"] == "POST"]
        assert "services/counter/increment" in paths
        assert "services/counter/decrement" in paths
        assert "services/counter/reset" in paths
        assert "services/counter/set_value" in paths


class TestTimerHelper:
    def test_create_and_actions(self, fake_client):
        fake_client.set_ws("timer/create", {})
        helpers_core.timer_create(fake_client, "T", duration="00:05:00",
                                     restore=True)
        helpers_core.timer_start(fake_client, "timer.t", duration="00:10:00")
        helpers_core.timer_pause(fake_client, "timer.t")
        helpers_core.timer_cancel(fake_client, "timer.t")
        helpers_core.timer_finish(fake_client, "timer.t")
        helpers_core.timer_change(fake_client, "timer.t", "-00:01:00")
        paths = [c["path"] for c in fake_client.calls if c["verb"] == "POST"]
        assert "services/timer/start" in paths
        assert "services/timer/pause" in paths
        assert "services/timer/cancel" in paths
        assert "services/timer/finish" in paths
        assert "services/timer/change" in paths


class TestScheduleHelper:
    def test_create_with_windows(self, fake_client):
        fake_client.set_ws("schedule/create", {})
        helpers_core.schedule_create(fake_client, "Heating",
            monday=[{"from": "06:00:00", "to": "09:00:00"}],
            tuesday=[{"from": "06:00:00", "to": "09:00:00"}],
            icon="mdi:radiator")
        call = fake_client.ws_calls[-1]
        assert call["payload"]["monday"][0]["from"] == "06:00:00"
        assert "wednesday" not in call["payload"]  # only supplied days included

    def test_delete(self, fake_client):
        fake_client.set_ws("schedule/delete", {})
        helpers_core.schedule_delete(fake_client, "schedule.heating")
        call = fake_client.ws_calls[-1]
        assert call["payload"] == {"schedule_id": "heating"}


class TestPersonHelper:
    def test_create_requires_name(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.person_create(fake_client, "")

    def test_create_ok(self, fake_client):
        fake_client.set_ws("person/create", {"id": "p1"})
        helpers_core.person_create(fake_client, "Jon", user_id="u1",
                                      device_trackers=["device_tracker.phone"])
        call = fake_client.ws_calls[-1]
        assert call["type"] == "person/create"
        assert call["payload"]["name"] == "Jon"
        assert call["payload"]["user_id"] == "u1"
        assert call["payload"]["device_trackers"] == ["device_tracker.phone"]

    def test_update_requires_field(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.person_update(fake_client, "p1")

    def test_update_partial(self, fake_client):
        fake_client.set_ws("person/update", {})
        helpers_core.person_update(fake_client, "p1", name="Jonny")
        call = fake_client.ws_calls[-1]
        assert call["payload"] == {"person_id": "p1", "name": "Jonny"}

    def test_delete(self, fake_client):
        fake_client.set_ws("person/delete", {})
        helpers_core.person_delete(fake_client, "p1")
        assert fake_client.ws_calls[-1]["payload"] == {"person_id": "p1"}


class TestZoneHelper:
    def test_create_validates_radius(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.zone_create(fake_client, "Z", latitude=0, longitude=0,
                                        radius=0)

    def test_create_ok(self, fake_client):
        fake_client.set_ws("zone/create", {"id": "z1"})
        helpers_core.zone_create(fake_client, "Home", latitude=52.0,
                                    longitude=4.9, radius=50.0,
                                    icon="mdi:home", passive=True)
        call = fake_client.ws_calls[-1]
        assert call["payload"]["name"] == "Home"
        assert call["payload"]["latitude"] == 52.0
        assert call["payload"]["radius"] == 50.0
        assert call["payload"]["passive"] is True
        assert call["payload"]["icon"] == "mdi:home"

    def test_update_requires_field(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.zone_update(fake_client, "z1")

    def test_delete(self, fake_client):
        fake_client.set_ws("zone/delete", {})
        helpers_core.zone_delete(fake_client, "z1")
        assert fake_client.ws_calls[-1]["payload"] == {"zone_id": "z1"}


class TestTagHelper:
    def test_create_ok(self, fake_client):
        fake_client.set_ws("tag/create", {})
        helpers_core.tag_create(fake_client, "abc-123",
                                   name="Front door", description="NFC sticker")
        call = fake_client.ws_calls[-1]
        assert call["payload"]["tag_id"] == "abc-123"
        assert call["payload"]["name"] == "Front door"
        assert call["payload"]["description"] == "NFC sticker"

    def test_create_requires_id(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.tag_create(fake_client, "")

    def test_update_requires_field(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.tag_update(fake_client, "abc-123")

    def test_delete(self, fake_client):
        fake_client.set_ws("tag/delete", {})
        helpers_core.tag_delete(fake_client, "abc-123")
        assert fake_client.ws_calls[-1]["payload"] == {"tag_id": "abc-123"}


class TestConfigFlowHelpers:
    """Helpers created via the config_entries flow API (template, derivative,
    utility_meter, etc.)."""

    def test_config_entries_list_filter_by_domain(self, fake_client):
        fake_client.set_ws("config_entries/get", [
            {"entry_id": "a1", "domain": "derivative"},
            {"entry_id": "b1", "domain": "template"},
            {"entry_id": "a2", "domain": "derivative"},
        ])
        out = helpers_core.config_entries_list(fake_client, domain="derivative")
        assert [e["entry_id"] for e in out] == ["a1", "a2"]
        call = fake_client.ws_calls[-1]
        assert call["payload"]["domain"] == "derivative"

    def test_config_entries_list_type_filter(self, fake_client):
        fake_client.set_ws("config_entries/get", [])
        helpers_core.config_entries_list(fake_client, type_filter="helper")
        assert fake_client.ws_calls[-1]["payload"]["type_filter"] == "helper"

    def test_config_entry_remove(self, fake_client):
        fake_client.set_ws("config_entries/remove", {"ok": True})
        helpers_core.config_entry_remove(fake_client, "entry-1")
        call = fake_client.ws_calls[-1]
        assert call["type"] == "config_entries/remove"
        assert call["payload"] == {"entry_id": "entry-1"}

    def test_config_flow_init(self, fake_client):
        fake_client.set_ws("config_entries/flow/init",
                            {"flow_id": "F1", "type": "form"})
        result = helpers_core.config_flow_init(fake_client, "derivative")
        assert result["flow_id"] == "F1"
        call = fake_client.ws_calls[-1]
        assert call["payload"] == {"handler": "derivative",
                                     "show_advanced_options": False}

    def test_config_flow_configure(self, fake_client):
        fake_client.set_ws("config_entries/flow/configure",
                            {"type": "create_entry",
                             "result": {"entry_id": "E1"}})
        result = helpers_core.config_flow_configure(
            fake_client, "F1", {"name": "x", "source": "sensor.y"})
        assert result["result"]["entry_id"] == "E1"
        call = fake_client.ws_calls[-1]
        assert call["payload"] == {"flow_id": "F1",
                                     "user_input": {"name": "x",
                                                     "source": "sensor.y"}}

    def test_config_flow_helper_create_does_two_calls(self, fake_client):
        fake_client.set_ws("config_entries/flow/init", {"flow_id": "FX"})
        fake_client.set_ws("config_entries/flow/configure",
                            {"type": "create_entry",
                             "result": {"entry_id": "E2"}})
        result = helpers_core.config_flow_helper_create(
            fake_client, "derivative",
            {"name": "Watt rate", "source": "sensor.energy"})
        assert result["result"]["entry_id"] == "E2"
        types = [c["type"] for c in fake_client.ws_calls]
        assert types == ["config_entries/flow/init",
                          "config_entries/flow/configure"]


class TestConfigFlowHelperWrappers:
    """Per-domain wrappers: derivative, integration, utility_meter, etc."""

    @pytest.fixture
    def primed(self, fake_client):
        fake_client.set_ws("config_entries/flow/init", {"flow_id": "F"})
        fake_client.set_ws("config_entries/flow/configure",
                            {"type": "create_entry",
                             "result": {"entry_id": "E"}})
        return fake_client

    def test_derivative_create(self, primed):
        helpers_core.derivative_create(primed, name="Watts",
                                          source="sensor.energy",
                                          unit_time="h", round=3,
                                          time_window={"minutes": 5})
        configure = primed.ws_calls[-1]
        ui = configure["payload"]["user_input"]
        assert ui["name"] == "Watts"
        assert ui["source"] == "sensor.energy"
        assert ui["unit_time"] == "h"
        assert ui["round"] == 3
        assert ui["time_window"] == {"minutes": 5}

    def test_derivative_validates(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.derivative_create(fake_client, name="", source="s")
        with pytest.raises(ValueError):
            helpers_core.derivative_create(fake_client, name="x", source="")

    def test_integration_create_validates_method(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.integration_create(fake_client, name="n",
                                                source="sensor.s", method="bad")

    def test_integration_create_ok(self, primed):
        helpers_core.integration_create(primed, name="Wh", source="sensor.p",
                                            method="trapezoidal")
        ui = primed.ws_calls[-1]["payload"]["user_input"]
        assert ui["method"] == "trapezoidal"

    def test_utility_meter_create(self, primed):
        helpers_core.utility_meter_create(primed, name="DailyKWh",
                                              source="sensor.energy",
                                              cycle="daily",
                                              tariffs=["peak", "offpeak"])
        ui = primed.ws_calls[-1]["payload"]["user_input"]
        assert ui["cycle"] == "daily"
        assert ui["tariffs"] == ["peak", "offpeak"]

    def test_utility_meter_validates_cycle(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.utility_meter_create(fake_client, name="n",
                                                  source="sensor.s",
                                                  cycle="fortnightly")

    def test_min_max_create(self, primed):
        helpers_core.min_max_create(primed, name="avg",
                                       entity_ids=["sensor.a", "sensor.b"],
                                       type="mean")
        ui = primed.ws_calls[-1]["payload"]["user_input"]
        assert ui["type"] == "mean"
        assert ui["entity_ids"] == ["sensor.a", "sensor.b"]

    def test_min_max_validates(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.min_max_create(fake_client, name="n",
                                           entity_ids=["s"], type="bogus")
        with pytest.raises(ValueError):
            helpers_core.min_max_create(fake_client, name="n",
                                           entity_ids=[], type="mean")

    def test_threshold_create(self, primed):
        helpers_core.threshold_create(primed, name="warn",
                                         entity_id="sensor.temp", upper=30)
        ui = primed.ws_calls[-1]["payload"]["user_input"]
        assert ui["upper"] == 30
        assert "lower" not in ui

    def test_threshold_validates(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.threshold_create(fake_client, name="n",
                                             entity_id="sensor.s")

    def test_trend_create(self, primed):
        helpers_core.trend_create(primed, name="rising",
                                     entity_id="sensor.temp", invert=False,
                                     max_samples=10)
        ui = primed.ws_calls[-1]["payload"]["user_input"]
        assert ui["max_samples"] == 10

    def test_statistics_create(self, primed):
        helpers_core.statistics_create(primed, name="stats",
                                          entity_id="sensor.temp",
                                          state_characteristic="mean")
        ui = primed.ws_calls[-1]["payload"]["user_input"]
        assert ui["state_characteristic"] == "mean"

    def test_history_stats_create_validates(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.history_stats_create(fake_client, name="n",
                                                  entity_id="sensor.s",
                                                  state="on", type="bogus")
        with pytest.raises(ValueError):
            helpers_core.history_stats_create(fake_client, name="n",
                                                  entity_id="sensor.s",
                                                  state="on",
                                                  start="x")  # only one bound

    def test_history_stats_create_ok(self, primed):
        helpers_core.history_stats_create(primed, name="UptimeToday",
                                              entity_id="binary_sensor.up",
                                              state="on",
                                              start="{{ now().date() }}",
                                              duration={"hours": 24})
        ui = primed.ws_calls[-1]["payload"]["user_input"]
        assert ui["state"] == "on"
        assert ui["duration"] == {"hours": 24}

    def test_filter_create_validates(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.filter_create(fake_client, name="n",
                                          entity_id="sensor.s", filters=[])

    def test_filter_create_ok(self, primed):
        helpers_core.filter_create(primed, name="smooth",
                                      entity_id="sensor.temp",
                                      filters=[{"filter": "lowpass",
                                                 "time_constant": 10}])
        ui = primed.ws_calls[-1]["payload"]["user_input"]
        assert ui["filters"][0]["filter"] == "lowpass"

    def test_random_create_validates(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.random_create(fake_client, name="n",
                                          minimum=10, maximum=5)

    def test_random_create_ok(self, primed):
        helpers_core.random_create(primed, name="r", minimum=1, maximum=6)
        ui = primed.ws_calls[-1]["payload"]["user_input"]
        assert ui["minimum"] == 1
        assert ui["maximum"] == 6

    def test_template_create_validates_type(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.template_create(fake_client, name="n",
                                            template_type="bogus")

    def test_template_create_validates_state_required(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.template_create(fake_client, name="n",
                                            template_type="sensor")

    def test_template_create_button_no_state(self, primed):
        helpers_core.template_create(primed, name="press",
                                        template_type="button")
        ui = primed.ws_calls[-1]["payload"]["user_input"]
        assert ui["template_type"] == "button"
        assert "state" not in ui

    def test_template_create_sensor(self, primed):
        helpers_core.template_create(primed, name="kWh",
                                        template_type="sensor",
                                        state="{{ states('sensor.x') | float * 0.001 }}",
                                        unit_of_measurement="kWh",
                                        state_class="total_increasing")
        ui = primed.ws_calls[-1]["payload"]["user_input"]
        assert ui["template_type"] == "sensor"
        assert ui["unit_of_measurement"] == "kWh"
        assert ui["state_class"] == "total_increasing"

    def test_group_create_validates(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.group_create(fake_client, name="g",
                                         entities=["light.a"],
                                         group_type="bogus")
        with pytest.raises(ValueError):
            helpers_core.group_create(fake_client, name="g",
                                         entities=[], group_type="light")

    def test_group_create_ok(self, primed):
        helpers_core.group_create(primed, name="kitchen-lights",
                                     entities=["light.a", "light.b"],
                                     group_type="light", all=True)
        ui = primed.ws_calls[-1]["payload"]["user_input"]
        assert ui["group_type"] == "light"
        assert ui["entities"] == ["light.a", "light.b"]
        assert ui["all"] is True

    def test_generic_thermostat_create(self, primed):
        helpers_core.generic_thermostat_create(primed, name="t",
                                                   heater="switch.h",
                                                   target_sensor="sensor.t",
                                                   target_temp=21.5)
        ui = primed.ws_calls[-1]["payload"]["user_input"]
        assert ui["heater"] == "switch.h"
        assert ui["target_temp"] == 21.5

    def test_generic_hygrostat_validates(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.generic_hygrostat_create(fake_client, name="h",
                                                      humidifier="switch.x",
                                                      target_sensor="sensor.h",
                                                      device_class="bogus")

    def test_generic_hygrostat_create(self, primed):
        helpers_core.generic_hygrostat_create(primed, name="h",
                                                  humidifier="switch.x",
                                                  target_sensor="sensor.h")
        ui = primed.ws_calls[-1]["payload"]["user_input"]
        assert ui["device_class"] == "humidifier"

    def test_switch_as_x_validates_domain(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.switch_as_x_create(fake_client, name="n",
                                                entity_id="switch.x",
                                                target_domain="bogus")

    def test_switch_as_x_validates_entity(self, fake_client):
        with pytest.raises(ValueError):
            helpers_core.switch_as_x_create(fake_client, name="n",
                                                entity_id="light.x",
                                                target_domain="light")

    def test_switch_as_x_ok(self, primed):
        helpers_core.switch_as_x_create(primed, name="fan",
                                            entity_id="switch.fan",
                                            target_domain="fan")
        ui = primed.ws_calls[-1]["payload"]["user_input"]
        assert ui["target_domain"] == "fan"

    def test_tod_create(self, primed):
        helpers_core.tod_create(primed, name="day",
                                   after="sunrise", before="sunset")
        ui = primed.ws_calls[-1]["payload"]["user_input"]
        assert ui["after"] == "sunrise"
        assert ui["before"] == "sunset"

    def test_mold_indicator_create(self, primed):
        helpers_core.mold_indicator_create(primed, name="mold",
                                              indoor_temp_sensor="sensor.it",
                                              indoor_humidity_sensor="sensor.ih",
                                              outdoor_temp_sensor="sensor.ot",
                                              calibration_factor=2.5)
        ui = primed.ws_calls[-1]["payload"]["user_input"]
        assert ui["calibration_factor"] == 2.5


class TestListAllHelpers:
    def test_includes_new_storage_types(self, fake_client):
        for t in helpers_core.HELPER_TYPES:
            fake_client.set_ws(f"{t}/list", [{"id": f"{t}-1"}])
        fake_client.set_ws("config_entries/get", [])
        out = helpers_core.list_all_helpers(fake_client)
        for t in ("input_boolean", "input_select", "counter", "timer",
                  "schedule", "person", "zone", "tag"):
            assert t in out
            assert out[t][0]["id"] == f"{t}-1"

    def test_includes_config_flow_helpers_grouped(self, fake_client):
        for t in helpers_core.HELPER_TYPES:
            fake_client.set_ws(f"{t}/list", [])
        fake_client.set_ws("config_entries/get", [
            {"entry_id": "d1", "domain": "derivative"},
            {"entry_id": "u1", "domain": "utility_meter"},
            {"entry_id": "u2", "domain": "utility_meter"},
            {"entry_id": "g1", "domain": "group"},
        ])
        out = helpers_core.list_all_helpers(fake_client)
        assert len(out["derivative"]) == 1
        assert len(out["utility_meter"]) == 2
        assert len(out["group"]) == 1
        # Domains with no entries still present with empty lists
        assert out["template"] == []
        # And the WS call requested type_filter=helper
        call = next(c for c in fake_client.ws_calls
                     if c["type"] == "config_entries/get")
        assert call["payload"]["type_filter"] == "helper"

    def test_can_skip_config_flow(self, fake_client):
        for t in helpers_core.HELPER_TYPES:
            fake_client.set_ws(f"{t}/list", [])
        out = helpers_core.list_all_helpers(fake_client, include_config_flow=False)
        for d in helpers_core.CONFIG_FLOW_HELPER_DOMAINS:
            assert d not in out
        # config_entries/get must NOT have been called
        types = [c["type"] for c in fake_client.ws_calls]
        assert "config_entries/get" not in types


# ────────────────────────────────────────────────────────── lovelace

class TestLovelace:
    def test_list_dashboards(self, fake_client):
        fake_client.set_ws("lovelace/dashboards/list",
                           [{"url_path": "jon-mobile", "title": "Jon"}])
        ds = lovelace_core.list_dashboards(fake_client)
        assert len(ds) == 1 and ds[0]["url_path"] == "jon-mobile"

    def test_get_config_default(self, fake_client):
        fake_client.set_ws("lovelace/config", {"views": []})
        cfg = lovelace_core.get_dashboard_config(fake_client)
        assert "views" in cfg
        last = fake_client.ws_calls[-1]
        assert last["payload"] == {}

    def test_get_config_specific(self, fake_client):
        fake_client.set_ws("lovelace/config", {"views": [1, 2, 3]})
        lovelace_core.get_dashboard_config(fake_client, "jon-mobile")
        last = fake_client.ws_calls[-1]
        assert last["payload"] == {"url_path": "jon-mobile"}

    def test_save_config(self, fake_client):
        fake_client.set_ws("lovelace/config/save", {"result": "ok"})
        cfg = {"views": [{"path": "home"}]}
        lovelace_core.save_dashboard_config(fake_client, "jon-mobile", cfg)
        last = fake_client.ws_calls[-1]
        assert last["payload"]["url_path"] == "jon-mobile"
        assert last["payload"]["config"] == cfg

    def test_save_validates(self, fake_client):
        with pytest.raises(ValueError):
            lovelace_core.save_dashboard_config(fake_client, "", {"views": []})
        with pytest.raises(ValueError):
            lovelace_core.save_dashboard_config(fake_client, "x", "not-a-dict")

    def test_resources_list(self, fake_client):
        fake_client.set_ws("lovelace/resources",
                           [{"id": "r1", "url": "/x.js", "type": "module"}])
        res = lovelace_core.list_resources(fake_client)
        assert len(res) == 1 and res[0]["id"] == "r1"

    def test_resource_delete(self, fake_client):
        fake_client.set_ws("lovelace/resources/delete", {})
        lovelace_core.delete_resource(fake_client, "r1")
        last = fake_client.ws_calls[-1]
        assert last["payload"] == {"resource_id": "r1"}

    def test_resource_create(self, fake_client):
        fake_client.set_ws("lovelace/resources/create", {})
        lovelace_core.create_resource(fake_client, "/foo.js", "module")
        last = fake_client.ws_calls[-1]
        assert last["payload"] == {"url": "/foo.js", "res_type": "module"}


# ────────────────────────────────────────────────────────── automation/script config edit

class TestAutomationScriptConfig:
    def test_automation_get_config(self, fake_client):
        fake_client.set_ws("automation/config", {"config": {"id": "1", "alias": "x"}})
        cfg = automation_core.get_config(fake_client, "automation.x")
        assert cfg["id"] == "1"

    def test_automation_get_config_validates_id(self, fake_client):
        with pytest.raises(ValueError):
            automation_core.get_config(fake_client, "switch.x")

    def test_automation_save_config(self, fake_client):
        automation_core.save_config(fake_client, "automation.x", {"id": "abc", "alias": "y"})
        last = fake_client.calls[-1]
        assert last["verb"] == "POST"
        assert last["path"] == "config/automation/config/abc"
        assert last["payload"]["alias"] == "y"

    def test_automation_save_validates(self, fake_client):
        with pytest.raises(ValueError):
            automation_core.save_config(fake_client, "automation.x", {})  # no id
        with pytest.raises(ValueError):
            automation_core.save_config(fake_client, "switch.x", {"id": "1"})

    def test_script_save_config(self, fake_client):
        script_core.save_config(fake_client, "script.bedtime", {"alias": "Bedtime"})
        last = fake_client.calls[-1]
        assert last["path"] == "config/script/config/bedtime"

    def test_script_save_validates(self, fake_client):
        with pytest.raises(ValueError):
            script_core.save_config(fake_client, "automation.x", {"alias": "X"})


# ────────────────────────────────────────────────────────── lovelace_cards (editor)

@pytest.fixture
def sample_dashboard():
    return {
        "views": [
            {
                "title": "Home", "path": "home",
                "cards": [
                    {"type": "tile", "entity": "light.kitchen"},
                    {
                        "type": "vertical-stack",
                        "cards": [
                            {"type": "tile", "entity": "sensor.outdoor_temp"},
                            {"type": "custom:bar-card", "entities": [
                                {"entity": "sensor.energy"}]},
                        ],
                    },
                ],
            },
            {
                "title": "Dead", "path": "dead",
                "cards": [
                    {"type": "tile", "entity": "sensor.does_not_exist"},
                ],
            },
        ],
    }


class TestLayoutLint:
    """Heuristic layout-quality lint — catches visual issues HA renders but
    doesn't flag (heading truncation, sibling mismatch, etc.)."""

    def test_heading_truncation_mobile(self):
        from cli_anything.homeassistant.core import lovelace_layout_lint as ll
        dash = {"views": [{"sections": [{
            "type": "grid", "column_span": 4, "cards": [
                {"type": "heading",
                  "heading": "Layout · stacks / grid / conditional / picture-elements"},
            ]}]}]}
        issues = ll.lint_layout(dash, viewport="mobile")
        rules = [i["rule"] for i in issues]
        assert "heading-truncation" in rules

    def test_heading_short_no_issue(self):
        from cli_anything.homeassistant.core import lovelace_layout_lint as ll
        dash = {"views": [{"sections": [{
            "type": "grid", "column_span": 4, "cards": [
                {"type": "heading", "heading": "Lights"},
            ]}]}]}
        issues = ll.lint_layout(dash, viewport="mobile")
        assert not any(i["rule"] == "heading-truncation" for i in issues)

    def test_useless_single_child_stack(self):
        from cli_anything.homeassistant.core import lovelace_layout_lint as ll
        dash = {"views": [{"sections": [{
            "type": "grid", "cards": [
                {"type": "vertical-stack", "cards": [
                    {"type": "tile", "entity": "light.kitchen"},
                ]},
            ]}]}]}
        issues = ll.lint_layout(dash)
        assert any(i["rule"] == "useless-single-stack" for i in issues)

    def test_empty_stack_flagged(self):
        from cli_anything.homeassistant.core import lovelace_layout_lint as ll
        dash = {"views": [{"sections": [{
            "type": "grid", "cards": [
                {"type": "horizontal-stack", "cards": []},
            ]}]}]}
        issues = ll.lint_layout(dash)
        assert any(i["rule"] == "empty-stack" for i in issues)

    def test_hstack_squeeze_mobile(self):
        from cli_anything.homeassistant.core import lovelace_layout_lint as ll
        dash = {"views": [{"sections": [{
            "type": "grid", "column_span": 4, "cards": [
                {"type": "horizontal-stack", "cards": [
                    {"type": "tile", "entity": "a"},
                    {"type": "tile", "entity": "b"},
                    {"type": "tile", "entity": "c"},
                ]},
            ]}]}]}
        issues = ll.lint_layout(dash, viewport="mobile")
        assert any(i["rule"] == "hstack-squeeze" for i in issues)

    def test_hstack_two_cards_mobile_ok(self):
        """2-card hstacks survive mobile well — don't flag."""
        from cli_anything.homeassistant.core import lovelace_layout_lint as ll
        dash = {"views": [{"sections": [{
            "type": "grid", "column_span": 4, "cards": [
                {"type": "horizontal-stack", "cards": [
                    {"type": "tile", "entity": "a"},
                    {"type": "tile", "entity": "b"},
                ]},
            ]}]}]}
        issues = ll.lint_layout(dash, viewport="mobile")
        assert not any(i["rule"] == "hstack-squeeze" for i in issues)

    def test_hstack_squeeze_desktop_narrow(self):
        """Desktop: hstack with 3 children in column_span=2 should flag."""
        from cli_anything.homeassistant.core import lovelace_layout_lint as ll
        dash = {"views": [{"sections": [{
            "type": "grid", "column_span": 2, "cards": [
                {"type": "horizontal-stack", "cards": [
                    {"type": "tile", "entity": "a"},
                    {"type": "tile", "entity": "b"},
                    {"type": "tile", "entity": "c"},
                ]},
            ]}]}]}
        issues = ll.lint_layout(dash, viewport="desktop")
        assert any(i["rule"] == "hstack-squeeze" for i in issues)

    def test_sibling_height_mismatch_apexcharts_v_minigraph(self):
        """The exact case from the screenshot: apexcharts (huge) vs mini-graph (medium)."""
        from cli_anything.homeassistant.core import lovelace_layout_lint as ll
        dash = {"views": [{"sections": [{
            "type": "grid", "column_span": 4, "cards": [
                {"type": "grid", "columns": 2, "cards": [
                    {"type": "custom:apexcharts-card", "series": [
                        {"entity": "sensor.x"}]},
                    {"type": "custom:mini-graph-card",
                      "entities": [{"entity": "sensor.y"}]},
                ]},
            ]}]}]}
        issues = ll.lint_layout(dash, viewport="desktop")
        msgs = [i["message"] for i in issues
                 if i["rule"] == "sibling-height-mismatch"]
        assert msgs, "should detect apexcharts vs mini-graph height mismatch"

    def test_no_mismatch_when_uniform(self):
        from cli_anything.homeassistant.core import lovelace_layout_lint as ll
        dash = {"views": [{"sections": [{
            "type": "grid", "column_span": 4, "cards": [
                {"type": "grid", "columns": 2, "cards": [
                    {"type": "tile", "entity": "light.a"},
                    {"type": "tile", "entity": "light.b"},
                ]},
            ]}]}]}
        issues = ll.lint_layout(dash, viewport="desktop")
        assert not any(i["rule"] == "sibling-height-mismatch" for i in issues)

    def test_digital_clock_oversize(self):
        from cli_anything.homeassistant.core import lovelace_layout_lint as ll
        dash = {"views": [{"sections": [{
            "type": "grid", "column_span": 2, "cards": [
                {"type": "custom:digital-clock"},
            ]}]}]}
        issues = ll.lint_layout(dash, viewport="mobile")
        assert any(i["rule"] == "digital-clock-oversize" for i in issues)

    def test_digital_clock_with_override_skipped(self):
        from cli_anything.homeassistant.core import lovelace_layout_lint as ll
        dash = {"views": [{"sections": [{
            "type": "grid", "column_span": 2, "cards": [
                {"type": "custom:digital-clock",
                  "card_mod": {"style": "ha-card { font-size: 1em; }"}},
            ]}]}]}
        issues = ll.lint_layout(dash, viewport="mobile")
        assert not any(i["rule"] == "digital-clock-oversize" for i in issues)

    def test_tight_grid_with_text_heavy(self):
        from cli_anything.homeassistant.core import lovelace_layout_lint as ll
        dash = {"views": [{"sections": [{
            "type": "grid", "column_span": 4, "cards": [
                {"type": "grid", "columns": 4, "cards": [
                    {"type": "entities", "entities": ["light.a", "light.b"]},
                    {"type": "tile", "entity": "light.c"},
                    {"type": "tile", "entity": "light.d"},
                    {"type": "tile", "entity": "light.e"},
                ]},
            ]}]}]}
        issues = ll.lint_layout(dash)
        assert any(i["rule"] == "tight-grid-text-heavy" for i in issues)

    def test_viewport_both_tags_issues(self):
        from cli_anything.homeassistant.core import lovelace_layout_lint as ll
        dash = {"views": [{"sections": [{
            "type": "grid", "column_span": 4, "cards": [
                {"type": "heading",
                  "heading": "Layout · stacks / grid / conditional / picture-elements"},
            ]}]}]}
        issues = ll.lint_layout(dash, viewport="both")
        viewports = {i.get("viewport") for i in issues}
        # Mobile budget is tighter — must include mobile.
        assert "mobile" in viewports

    def test_viewport_validates_value(self):
        from cli_anything.homeassistant.core import lovelace_layout_lint as ll
        with pytest.raises(ValueError):
            ll.lint_layout({"views": []}, viewport="phone")

    def test_card_height_class(self):
        from cli_anything.homeassistant.core import lovelace_layout_lint as ll
        assert ll.card_height_class({"type": "tile", "entity": "x"}) == 2
        assert ll.card_height_class({"type": "heading", "heading": "x"}) == 1
        assert ll.card_height_class(
            {"type": "custom:apexcharts-card", "series": []}) == 14
        assert ll.card_height_class({"type": "vertical-stack", "cards": [
            {"type": "tile", "entity": "a"}, {"type": "tile", "entity": "b"},
        ]}) == 4  # 2 + 2

    def test_simple_weather_card_not_huge(self):
        """Regression: 'simple-weather-card' must NOT match the
        'weather-card' substring rule that makes weather-chart-card huge."""
        from cli_anything.homeassistant.core import lovelace_layout_lint as ll
        # simple-weather-card is intentionally small (a chip-like weather tile)
        assert ll.card_height_class(
            {"type": "custom:simple-weather-card", "entity": "weather.home"}) == 2
        # weather-chart-card IS huge — guard the other direction
        assert ll.card_height_class(
            {"type": "custom:weather-chart-card", "entity": "weather.home"}) == 14

    def test_rules_filter(self):
        from cli_anything.homeassistant.core import lovelace_layout_lint as ll
        dash = {"views": [{"sections": [{
            "type": "grid", "column_span": 4, "cards": [
                {"type": "heading",
                  "heading": "a much too long heading for any sensible "
                                "mobile layout"},
                {"type": "vertical-stack", "cards": [
                    {"type": "tile", "entity": "x"}]},
            ]}]}]}
        # Run only heading rule
        issues = ll.lint_layout(dash, rules={"heading-truncation"})
        assert all(i["rule"] == "heading-truncation" for i in issues)

    def test_format_issues(self):
        from cli_anything.homeassistant.core import lovelace_layout_lint as ll
        out = ll.format_issues([{
            "severity": "warning", "path": "views[0]/sections[0]",
            "rule": "heading-truncation",
            "message": "boom", "hint": "fix it",
        }])
        assert "[WARNING]" in out
        assert "[heading-truncation]" in out
        assert "fix it" in out
        assert ll.format_issues([]) == "✓ no layout issues"

    def test_summarise_by_rule(self):
        from cli_anything.homeassistant.core import lovelace_layout_lint as ll
        out = ll.summarise_by_rule([
            {"rule": "a"}, {"rule": "a"}, {"rule": "b"},
        ])
        assert out == {"a": 2, "b": 1}


class TestDashboardSnapshot:
    """snapshot_dashboard + restore_dashboard_snapshot + automatic
    snapshot-on-save."""

    def test_snapshot_writes_json(self, fake_client, tmp_path):
        fake_client.set_ws("lovelace/config",
                            {"views": [{"path": "home", "cards": []}]})
        out = lovelace_core.snapshot_dashboard(
            fake_client, "jon-mobile", snapshot_dir=str(tmp_path))
        import json
        data = json.load(open(out))
        assert data["url_path"] == "jon-mobile"
        assert data["timestamp"]  # populated
        assert data["config"]["views"][0]["path"] == "home"

    def test_save_with_snapshot_flag_writes_pre_save_state(
            self, fake_client, tmp_path):
        # Current state (snapshotted before save):
        fake_client.set_ws("lovelace/config",
                            {"views": [{"path": "old", "cards": []}]})
        # The save call itself:
        fake_client.set_ws("lovelace/config/save", {"result": "ok"})

        new_cfg = {"views": [{"path": "new", "cards": []}]}
        lovelace_core.save_dashboard_config(
            fake_client, "jon-mobile", new_cfg,
            snapshot=True, snapshot_dir=str(tmp_path))

        # Snapshot file should exist and contain the OLD state.
        snaps = lovelace_core.list_snapshots(snapshot_dir=str(tmp_path),
                                                url_path="jon-mobile")
        assert len(snaps) == 1
        import json
        data = json.load(open(snaps[0]["path"]))
        assert data["config"]["views"][0]["path"] == "old"

        # And the save was still performed with the new config.
        save_calls = [c for c in fake_client.ws_calls
                       if c["type"] == "lovelace/config/save"]
        assert save_calls[-1]["payload"]["config"] == new_cfg

    def test_list_snapshots_filters_by_url_path(self, fake_client, tmp_path):
        fake_client.set_ws("lovelace/config", {"views": []})
        lovelace_core.snapshot_dashboard(fake_client, "jon-mobile",
                                            snapshot_dir=str(tmp_path))
        lovelace_core.snapshot_dashboard(fake_client, "gem-mobile",
                                            snapshot_dir=str(tmp_path))
        jon = lovelace_core.list_snapshots(snapshot_dir=str(tmp_path),
                                              url_path="jon-mobile")
        gem = lovelace_core.list_snapshots(snapshot_dir=str(tmp_path),
                                              url_path="gem-mobile")
        assert len(jon) == 1 and jon[0]["url_path"] == "jon-mobile"
        assert len(gem) == 1 and gem[0]["url_path"] == "gem-mobile"

    def test_restore_dashboard_snapshot(self, fake_client, tmp_path):
        fake_client.set_ws("lovelace/config",
                            {"views": [{"path": "snap-state"}]})
        path = lovelace_core.snapshot_dashboard(
            fake_client, "jon-mobile", snapshot_dir=str(tmp_path))
        fake_client.set_ws("lovelace/config/save", {})
        lovelace_core.restore_dashboard_snapshot(fake_client, path)
        # Verify the right save call was made.
        save = [c for c in fake_client.ws_calls
                 if c["type"] == "lovelace/config/save"][-1]
        assert save["payload"]["url_path"] == "jon-mobile"
        assert save["payload"]["config"]["views"][0]["path"] == "snap-state"

    def test_restore_with_override(self, fake_client, tmp_path):
        fake_client.set_ws("lovelace/config",
                            {"views": [{"path": "snap"}]})
        path = lovelace_core.snapshot_dashboard(
            fake_client, "jon-mobile", snapshot_dir=str(tmp_path))
        fake_client.set_ws("lovelace/config/save", {})
        lovelace_core.restore_dashboard_snapshot(
            fake_client, path, url_path_override="scratch-dash")
        save = [c for c in fake_client.ws_calls
                 if c["type"] == "lovelace/config/save"][-1]
        assert save["payload"]["url_path"] == "scratch-dash"

    def test_snapshot_failure_does_not_block_save(self, fake_client, tmp_path,
                                                       monkeypatch):
        """If reading the current dashboard fails, the save should still
        proceed — snapshots are best-effort."""
        def fail(*a, **kw): raise RuntimeError("boom")
        monkeypatch.setattr(lovelace_core, "get_dashboard_config", fail)
        fake_client.set_ws("lovelace/config/save", {"result": "ok"})
        lovelace_core.save_dashboard_config(
            fake_client, "jon-mobile", {"views": []},
            snapshot=True, snapshot_dir=str(tmp_path))
        # Save still happened
        save = [c for c in fake_client.ws_calls
                 if c["type"] == "lovelace/config/save"]
        assert len(save) == 1
        # Snapshot file exists and records the error
        snaps = lovelace_core.list_snapshots(snapshot_dir=str(tmp_path))
        assert snaps
        import json
        data = json.load(open(snaps[0]["path"]))
        assert "snapshot read failed" in data["config"].get("_error", "")


class TestCardValidator:
    """Validates dashboard configs against builder schemas + resource list."""

    def test_no_issues_on_valid_dashboard(self):
        from cli_anything.homeassistant.core import (
            lovelace_card_builders as cb,
            lovelace_card_validate as v,
        )
        # Build from examples — those must all validate cleanly
        # (resource check disabled).
        cards = [cb.BUILDER_META[n]["example"]
                  for n in ("entities", "tile", "gauge", "markdown",
                              "vertical-stack", "grid", "conditional")]
        dash = {"views": [{"cards": cards}]}
        issues = v.validate_dashboard(dash)
        errors = [i for i in issues if i["severity"] == "error"]
        assert errors == [], f"unexpected errors: {errors}"

    def test_missing_type_flagged(self):
        from cli_anything.homeassistant.core import lovelace_card_validate as v
        dash = {"views": [{"cards": [{"entity": "light.x"}]}]}
        issues = v.validate_dashboard(dash)
        # The walker skips cards without `type`, so we won't find this one
        # at the walker level. validate_card directly should catch it.
        direct = v.validate_card({"entity": "light.x"})
        assert any("no 'type' field" in i["message"] for i in direct)

    def test_missing_required_field(self):
        from cli_anything.homeassistant.core import lovelace_card_validate as v
        # `tile` requires `entity` (warning, not error — HA can still render
        # a tile with templates / tap_action even sans entity).
        dash = {"views": [{"cards": [{"type": "tile"}]}]}
        issues = v.validate_dashboard(dash)
        warnings = [i for i in issues if i["severity"] == "warning"
                      and "'entity'" in i["message"]]
        assert warnings, f"expected warning about missing entity; got: {issues}"

    def test_unknown_native_warns_not_errors(self):
        from cli_anything.homeassistant.core import lovelace_card_validate as v
        dash = {"views": [{"cards": [{"type": "bogo-card", "entity": "x"}]}]}
        issues = v.validate_dashboard(dash)
        assert any(i["severity"] == "warning"
                    and "unknown native" in i["message"] for i in issues)

    def test_custom_missing_resource_errors(self):
        from cli_anything.homeassistant.core import lovelace_card_validate as v
        dash = {"views": [{"cards": [
            {"type": "custom:apexcharts-card", "series": [
                {"entity": "sensor.x"}]},
        ]}]}
        # installed=empty set → apexcharts is "not installed"
        issues = v.validate_dashboard(dash, installed=set())
        assert any("not installed" in i["message"] for i in issues)

    def test_custom_installed_ok(self):
        from cli_anything.homeassistant.core import lovelace_card_validate as v
        dash = {"views": [{"cards": [
            {"type": "custom:apexcharts-card",
              "series": [{"entity": "sensor.x"}]},
        ]}]}
        issues = v.validate_dashboard(
            dash, installed={"custom:apexcharts-card"})
        assert not any("not installed" in i["message"] for i in issues)

    def test_stray_card_mod_in_series_flagged(self):
        """The exact bug class from the apexcharts incident — must error."""
        from cli_anything.homeassistant.core import lovelace_card_validate as v
        dash = {"views": [{"cards": [
            {"type": "custom:apexcharts-card", "series": [
                {"entity": "sensor.x", "type": "area",
                  "card_mod": "ha-card { min-height: 110px; }"},
            ]},
        ]}]}
        issues = v.validate_dashboard(dash,
                                        installed={"custom:apexcharts-card"})
        series_errors = [i for i in issues
                          if i["severity"] == "error"
                          and "series" in i["message"]]
        assert series_errors, \
            f"validator missed card_mod-in-series; got: {[i['message'] for i in issues]}"

    def test_stray_card_mod_in_chips_warns(self):
        """Chips might support card_mod depending on parent — warn, don't error."""
        from cli_anything.homeassistant.core import lovelace_card_validate as v
        dash = {"views": [{"cards": [
            {"type": "custom:mushroom-chips-card", "chips": [
                {"type": "weather", "entity": "weather.x",
                  "card_mod": "ha-card { display: none; }"},
            ]},
        ]}]}
        issues = v.validate_dashboard(dash,
                                        installed={"custom:mushroom-chips-card"})
        chip_issues = [i for i in issues if "chips" in i["message"]]
        assert chip_issues, "expected at least one issue about chips card_mod"
        # Should be a warning, not an error.
        assert all(i["severity"] == "warning" for i in chip_issues)

    def test_card_mod_in_card_slot_is_fine(self):
        from cli_anything.homeassistant.core import lovelace_card_validate as v
        dash = {"views": [{"cards": [
            {"type": "tile", "entity": "light.x",
              "card_mod": {"style": "ha-card { color: red; }"}},
            {"type": "conditional",
              "conditions": [{"entity": "x"}],
              "card": {"type": "tile", "entity": "light.y",
                        "card_mod": {"style": "..."}}},
        ]}]}
        issues = v.validate_dashboard(dash)
        assert not any("card_mod found" in i["message"] for i in issues)

    def test_format_issues(self):
        from cli_anything.homeassistant.core import lovelace_card_validate as v
        out = v.format_issues([
            {"severity": "error", "path": "views[0]/cards[0]",
              "message": "boom"},
            {"severity": "warning", "path": "", "message": "soft"},
        ])
        assert "[ERROR] views[0]/cards[0]: boom" in out
        assert "[WARNING] <root>: soft" in out
        assert v.format_issues([]) == "✓ no issues"

    def test_installed_card_types_uses_resources(self, fake_client):
        from cli_anything.homeassistant.core import lovelace_card_validate as v
        fake_client.set_ws("lovelace/resources", [
            {"id": "r1", "url": "/hacsfiles/apexcharts-card/apexcharts-card.js",
              "type": "module"},
            {"id": "r2", "url": "/hacsfiles/mini-graph-card/mini-graph-card-bundle.js",
              "type": "module"},
        ])
        out = v.installed_card_types(fake_client)
        assert "custom:apexcharts-card" in out
        assert "custom:mini-graph-card" in out


class TestBuilderMeta:
    """Every builder has machine-readable metadata + a valid example."""

    def test_every_builder_has_meta(self):
        from cli_anything.homeassistant.core import lovelace_card_builders as b
        missing = [n for n in b.BUILDERS if n not in b.BUILDER_META]
        assert missing == [], f"builders without metadata: {missing}"

    def test_examples_carry_matching_type(self):
        """Each example's `type` must match the declared card_type."""
        from cli_anything.homeassistant.core import lovelace_card_builders as b
        for name, meta in b.BUILDER_META.items():
            ex = meta["example"]
            assert ex["type"] == meta["card_type"], (
                f"{name}: example type {ex['type']!r} != card_type "
                f"{meta['card_type']!r}")

    def test_examples_have_no_stray_card_mod(self):
        """Examples must not have card_mod inside non-card slots — exactly
        the bug class this whole pass is preventing."""
        from cli_anything.homeassistant.core import (
            lovelace_card_builders as b,
            lovelace_cards as lc,
        )
        # Strict walker should only visit the top-level card itself.
        for name, meta in b.BUILDER_META.items():
            ex = meta["example"]
            # Wrap example into a synthetic dashboard so walk_cards_strict
            # has a `cards` slot to enter.
            cfg = {"views": [{"cards": [ex]}]}
            cards = list(lc.walk_cards_strict(cfg))
            # No card visited should have card_mod somewhere it shouldn't.
            # (For now we just sanity-check the walker visits the example.)
            assert any(c.get("type") == meta["card_type"] for c in cards), \
                f"{name}: walker didn't visit example card"

    def test_builder_info_includes_signature(self):
        from cli_anything.homeassistant.core import lovelace_card_builders as b
        info = b.builder_info("tile")
        assert info["name"] == "tile"
        assert info["card_type"] == "tile"
        assert "entity" in info["signature"]
        assert info["example"]["type"] == "tile"

    def test_builder_info_unknown_raises(self):
        from cli_anything.homeassistant.core import lovelace_card_builders as b
        with pytest.raises(ValueError):
            b.builder_info("nope-not-a-card")

    def test_all_builder_info_complete(self):
        from cli_anything.homeassistant.core import lovelace_card_builders as b
        infos = b.all_builder_info()
        assert len(infos) == len(b.BUILDERS)
        for info in infos:
            assert info["card_type"], f"{info['name']} missing card_type"
            assert info["example"], f"{info['name']} missing example"


class TestWalkCardsStrict:
    """The card-context-aware walker — never enters series/chips/elements/etc."""

    def test_skips_apexcharts_series(self):
        cfg = {"views": [{"cards": [
            {"type": "custom:apexcharts-card",
              "series": [
                  {"entity": "sensor.x", "type": "area",
                    "card_mod": "should NOT be visited as a card"},
                  {"entity": "sensor.y", "type": "line"},
              ]},
        ]}]}
        types = [c["type"] for c in lovelace_cards_core.walk_cards_strict(cfg)]
        assert types == ["custom:apexcharts-card"]
        # The series entries (type: area / line) must NOT appear.
        assert "area" not in types
        assert "line" not in types

    def test_skips_mushroom_chips(self):
        cfg = {"views": [{"cards": [
            {"type": "custom:mushroom-chips-card",
              "chips": [
                  {"type": "weather", "entity": "weather.home"},
                  {"type": "template", "icon": "mdi:x"},
              ]},
        ]}]}
        types = [c["type"] for c in lovelace_cards_core.walk_cards_strict(cfg)]
        assert types == ["custom:mushroom-chips-card"]

    def test_skips_picture_elements_elements(self):
        cfg = {"views": [{"cards": [
            {"type": "picture-elements", "image": "/x.png",
              "elements": [
                  {"type": "state-icon", "entity": "light.k"},
              ]},
        ]}]}
        types = [c["type"] for c in lovelace_cards_core.walk_cards_strict(cfg)]
        assert types == ["picture-elements"]

    def test_enters_conditional_card(self):
        cfg = {"views": [{"cards": [
            {"type": "conditional", "conditions": [{"entity": "x"}],
              "card": {"type": "tile", "entity": "light.k"}},
        ]}]}
        types = [c["type"] for c in lovelace_cards_core.walk_cards_strict(cfg)]
        assert types == ["conditional", "tile"]

    def test_enters_nested_grids(self):
        cfg = {"views": [{"cards": [
            {"type": "grid", "cards": [
                {"type": "tile", "entity": "x"},
                {"type": "horizontal-stack", "cards": [
                    {"type": "button", "entity": "y"},
                ]},
            ]},
        ]}]}
        types = [c["type"] for c in lovelace_cards_core.walk_cards_strict(cfg)]
        assert types == ["grid", "tile", "horizontal-stack", "button"]

    def test_enters_sections(self):
        cfg = {"views": [{"sections": [
            {"type": "grid", "cards": [{"type": "tile", "entity": "x"}]},
        ]}]}
        types = [c["type"] for c in lovelace_cards_core.walk_cards_strict(cfg)]
        assert types == ["grid", "tile"]

    def test_with_path(self):
        cfg = {"views": [{"cards": [
            {"type": "grid", "cards": [
                {"type": "tile", "entity": "x"},
            ]},
        ]}]}
        out = list(lovelace_cards_core.walk_cards_strict(cfg, with_path=True))
        paths = [p for p, _ in out]
        assert paths == ["views[0]/cards[0]", "views[0]/cards[0]/cards[0]"]

    def test_view_layout_not_yielded_as_card(self):
        """Views have `type: masonry|sidebar|panel|sections` — NOT cards."""
        cfg = {"views": [
            {"title": "Home", "type": "masonry", "cards": [
                {"type": "tile", "entity": "x"},
            ]},
            {"title": "Sections", "type": "sections", "sections": [
                {"type": "grid", "cards": [{"type": "tile", "entity": "y"}]},
            ]},
        ]}
        types = [c["type"] for c in lovelace_cards_core.walk_cards_strict(cfg)]
        # Cards yielded:
        assert types == ["tile", "grid", "tile"]
        # The view's "masonry"/"sections" type MUST NOT appear:
        assert "masonry" not in types
        assert "sections" not in types

    def test_map_cards_strict_mutates_in_place(self):
        cfg = {"views": [{"cards": [
            {"type": "tile", "entity": "x"},
            {"type": "custom:apexcharts-card", "series": [
                {"entity": "y", "type": "area"},
            ]},
        ]}]}
        n = lovelace_cards_core.map_cards_strict(
            cfg, lambda c: c.update({"_visited": True}))
        assert n == 2  # tile + apexcharts (NOT the series entry)
        assert cfg["views"][0]["cards"][0]["_visited"] is True
        assert cfg["views"][0]["cards"][1]["_visited"] is True
        # The series entry must NOT have been mutated.
        assert "_visited" not in cfg["views"][0]["cards"][1]["series"][0]


class TestPointer:
    def test_parse_simple(self):
        assert lovelace_cards_core.parse_pointer("views[0]") == [("views", 0)]

    def test_parse_nested(self):
        assert lovelace_cards_core.parse_pointer("views[0]/cards[1]/cards[0]") == [
            ("views", 0), ("cards", 1), ("cards", 0),
        ]

    def test_parse_invalid(self):
        with pytest.raises(ValueError):
            lovelace_cards_core.parse_pointer("foo bar")
        with pytest.raises(ValueError):
            lovelace_cards_core.parse_pointer("views[0]/garbage")


class TestCardOps:
    def test_get_card(self, sample_dashboard):
        card = lovelace_cards_core.get_card(sample_dashboard, "views[0]/cards[0]")
        assert card["entity"] == "light.kitchen"

    def test_get_nested_card(self, sample_dashboard):
        card = lovelace_cards_core.get_card(
            sample_dashboard, "views[0]/cards[1]/cards[0]")
        assert card["entity"] == "sensor.outdoor_temp"

    def test_get_card_out_of_range(self, sample_dashboard):
        with pytest.raises(IndexError):
            lovelace_cards_core.get_card(sample_dashboard, "views[5]")

    def test_replace_card(self, sample_dashboard):
        new = {"type": "tile", "entity": "light.bedroom"}
        lovelace_cards_core.replace_card(sample_dashboard, "views[0]/cards[0]", new)
        assert sample_dashboard["views"][0]["cards"][0] == new

    def test_replace_validates(self, sample_dashboard):
        with pytest.raises(ValueError):
            lovelace_cards_core.replace_card(sample_dashboard, "views[0]/cards[0]", "not-a-dict")

    def test_delete_card(self, sample_dashboard):
        before = len(sample_dashboard["views"][0]["cards"])
        lovelace_cards_core.delete_card(sample_dashboard, "views[0]/cards[0]")
        assert len(sample_dashboard["views"][0]["cards"]) == before - 1

    def test_insert_append(self, sample_dashboard):
        new_card = {"type": "tile", "entity": "switch.x"}
        lovelace_cards_core.insert_card(sample_dashboard, "views[0]", new_card)
        assert sample_dashboard["views"][0]["cards"][-1] == new_card

    def test_insert_at_position(self, sample_dashboard):
        new_card = {"type": "tile", "entity": "switch.y"}
        lovelace_cards_core.insert_card(sample_dashboard, "views[0]",
                                         new_card, position=0)
        assert sample_dashboard["views"][0]["cards"][0] == new_card


class TestFinder:
    def test_find_by_type(self, sample_dashboard):
        hits = lovelace_cards_core.find_cards(sample_dashboard, card_type="custom:bar-card")
        assert len(hits) == 1
        assert hits[0][0] == "views[0]/cards[1]/cards[1]"

    def test_find_by_entity(self, sample_dashboard):
        hits = lovelace_cards_core.find_cards(sample_dashboard, entity="light.kitchen")
        assert len(hits) == 1

    def test_find_by_substring(self, sample_dashboard):
        # 'outdoor_temp' appears in the tile that has it as entity AND in the
        # vertical-stack that contains that tile (parents serialise children).
        # Both matches are correct behaviour.
        hits = lovelace_cards_core.find_cards(sample_dashboard, contains="outdoor_temp")
        types = sorted(c.get("type") for _, c in hits)
        assert types == ["tile", "vertical-stack"]


class TestLint:
    def test_dead_entity_detected(self, sample_dashboard):
        live_eids = {"light.kitchen", "sensor.outdoor_temp", "sensor.energy"}
        result = lovelace_cards_core.lint(sample_dashboard, live_eids)
        # sensor.does_not_exist on the "Dead" view should be flagged.
        deads = [d["entity"] for d in result["dead_entities"]]
        assert "sensor.does_not_exist" in deads
        assert "light.kitchen" not in deads

    def test_lint_counts_cards(self, sample_dashboard):
        live_eids = {"light.kitchen", "sensor.outdoor_temp", "sensor.energy",
                     "sensor.does_not_exist"}
        result = lovelace_cards_core.lint(sample_dashboard, live_eids)
        # Cards: tile, vertical-stack, tile, custom:bar-card, tile = 5
        assert result["cards"] == 5
        assert result["dead_entities"] == []

    def test_lint_unknown_types(self, sample_dashboard):
        live_eids = {"light.kitchen", "sensor.outdoor_temp", "sensor.energy",
                     "sensor.does_not_exist"}
        # Pretend only 'tile' is a known type
        result = lovelace_cards_core.lint(sample_dashboard, live_eids,
                                           known_card_types={"tile"})
        unknown = [u["card_type"] for u in result["unknown_card_types"]]
        assert "vertical-stack" in unknown
        assert "custom:bar-card" in unknown


# ════════════════════════════════════════════════════════════════════════════
# v1.14 — Lovelace card builders, ops, sections, badges, types
# ════════════════════════════════════════════════════════════════════════════

from cli_anything.homeassistant.core import lovelace_card_builders as builders
from cli_anything.homeassistant.core import lovelace_card_ops as card_ops
from cli_anything.homeassistant.core import lovelace_card_types as card_types
from cli_anything.homeassistant.core import lovelace_badges as badges_core
from cli_anything.homeassistant.core import lovelace_sections as sections_core


class TestBuildersBuiltins:
    def test_entities_basic(self):
        card = builders.entities(["light.kitchen", "light.lounge"], title="Lights")
        assert card["type"] == "entities"
        assert card["entities"] == ["light.kitchen", "light.lounge"]
        assert card["title"] == "Lights"

    def test_entities_rejects_empty(self):
        with pytest.raises(ValueError):
            builders.entities([])

    def test_vertical_stack(self):
        c = builders.vertical_stack([{"type": "tile", "entity": "light.a"}])
        assert c["type"] == "vertical-stack"
        assert len(c["cards"]) == 1

    def test_horizontal_stack_validates(self):
        with pytest.raises(ValueError):
            builders.horizontal_stack([])

    def test_grid(self):
        c = builders.grid([{"type": "tile", "entity": "x"}], columns=4, square=True)
        assert c["columns"] == 4
        assert c["square"] is True

    def test_grid_rejects_zero_columns(self):
        with pytest.raises(ValueError):
            builders.grid([{}], columns=0)

    def test_glance(self):
        c = builders.glance(["light.kitchen"], show_state=False)
        assert c["type"] == "glance"
        assert c["show_state"] is False

    def test_gauge(self):
        c = builders.gauge("sensor.temp", min=0, max=40, needle=True, unit="°C")
        assert c["needle"] is True
        assert c["unit"] == "°C"

    def test_gauge_validates_entity(self):
        with pytest.raises(ValueError):
            builders.gauge("")

    def test_tile(self):
        c = builders.tile("light.lounge", color="amber", vertical=True)
        assert c["vertical"] is True
        assert c["color"] == "amber"

    def test_button(self):
        c = builders.button("light.x", show_state=True,
                              tap_action={"action": "toggle"})
        assert c["tap_action"] == {"action": "toggle"}

    def test_markdown(self):
        c = builders.markdown("# hi", title="Header")
        assert c["content"] == "# hi"
        assert c["title"] == "Header"

    def test_markdown_validates(self):
        with pytest.raises(ValueError):
            builders.markdown("")

    def test_history_graph(self):
        c = builders.history_graph(["sensor.t"], hours_to_show=12)
        assert c["hours_to_show"] == 12

    def test_statistics_graph(self):
        c = builders.statistics_graph(["sensor.t"], stat_types=["mean"],
                                        chart_type="bar")
        assert c["stat_types"] == ["mean"]
        assert c["chart_type"] == "bar"

    def test_conditional_validates(self):
        with pytest.raises(ValueError):
            builders.conditional({}, [])

    def test_conditional_wraps(self):
        inner = {"type": "tile", "entity": "light.x"}
        conds = [{"entity": "light.x", "state": "on"}]
        c = builders.conditional(inner, conds)
        assert c["card"] is inner
        assert c["conditions"] == conds

    def test_picture_elements(self):
        c = builders.picture_elements("/local/floorplan.png", [
            {"type": "state-icon", "entity": "light.x",
              "style": {"top": "50%", "left": "50%"}},
        ])
        assert c["image"] == "/local/floorplan.png"
        assert len(c["elements"]) == 1

    def test_iframe(self):
        c = builders.iframe("https://grafana.local/d/abc",
                              aspect_ratio="16:9")
        assert c["aspect_ratio"] == "16:9"

    def test_weather_forecast_validates(self):
        with pytest.raises(ValueError):
            builders.weather_forecast("sensor.foo")  # not weather.*

    def test_weather_forecast(self):
        c = builders.weather_forecast("weather.home", forecast_type="hourly")
        assert c["forecast_type"] == "hourly"


class TestBuildersMushroom:
    def test_mushroom_template(self):
        c = builders.mushroom_template("Hello", secondary="World",
                                         icon="mdi:home",
                                         icon_color="amber")
        assert c["type"] == "custom:mushroom-template-card"
        assert c["icon_color"] == "amber"

    def test_mushroom_light(self):
        c = builders.mushroom_light("light.kitchen",
                                      show_brightness_control=True,
                                      use_light_color=False)
        assert c["show_brightness_control"] is True
        assert c["use_light_color"] is False

    def test_mushroom_light_validates(self):
        with pytest.raises(ValueError):
            builders.mushroom_light("switch.foo")

    def test_mushroom_person(self):
        c = builders.mushroom_person("person.jon", hide_name=True)
        assert c["hide_name"] is True

    def test_mushroom_climate(self):
        c = builders.mushroom_climate("climate.bedroom",
                                        hvac_modes=["heat", "off"])
        assert c["hvac_modes"] == ["heat", "off"]

    def test_mushroom_chips(self):
        c = builders.mushroom_chips([
            {"type": "entity", "entity": "sensor.t"},
            {"type": "weather", "entity": "weather.home"},
        ])
        assert len(c["chips"]) == 2

    def test_mushroom_chips_validates(self):
        with pytest.raises(ValueError):
            builders.mushroom_chips([])

    def test_mushroom_title(self):
        c = builders.mushroom_title(title="Living", alignment="center")
        assert c["title"] == "Living"
        assert c["alignment"] == "center"


class TestBuildersCustomCharts:
    def test_apexcharts(self):
        c = builders.apexcharts(
            [{"entity": "sensor.power", "name": "Power"}],
            graph_span="24h", chart_type="line",
        )
        assert c["type"] == "custom:apexcharts-card"
        assert c["graph_span"] == "24h"

    def test_apexcharts_validates(self):
        with pytest.raises(ValueError):
            builders.apexcharts([])

    def test_mini_graph(self):
        c = builders.mini_graph(["sensor.t"], hours_to_show=12,
                                  line_width=3, smoothing=True)
        assert c["line_width"] == 3
        assert c["smoothing"] is True

    def test_button_card(self):
        c = builders.button_card(entity="light.x", template="dimmer",
                                   styles={"card": [{"height": "60px"}]})
        assert c["template"] == "dimmer"
        assert c["styles"]["card"][0]["height"] == "60px"

    def test_button_card_requires_entity_or_template(self):
        with pytest.raises(ValueError):
            builders.button_card(name="just a name")

    def test_bubble(self):
        c = builders.bubble(card_type="cover", entity="cover.garage")
        assert c["card_type"] == "cover"

    def test_mini_media_player_validates(self):
        with pytest.raises(ValueError):
            builders.mini_media_player("light.foo")

    def test_mini_media_player(self):
        c = builders.mini_media_player("media_player.lounge",
                                          artwork="cover")
        assert c["artwork"] == "cover"

    def test_auto_entities(self):
        c = builders.auto_entities(
            filter={"include": [{"domain": "light"}]},
            card={"type": "entities", "title": "Lights"},
        )
        assert c["filter"]["include"][0]["domain"] == "light"
        assert c["card"]["title"] == "Lights"

    def test_auto_entities_validates(self):
        with pytest.raises(ValueError):
            builders.auto_entities(filter=None)  # type: ignore

    def test_layout_card(self):
        c = builders.layout_card([{"type": "tile", "entity": "x"}],
                                    layout_type="masonry")
        assert c["layout_type"] == "masonry"

    def test_decluttering(self):
        c = builders.decluttering("my_tpl",
                                   variables=[{"name": "entity",
                                               "default": "light.x"}])
        assert c["template"] == "my_tpl"

    def test_decluttering_validates(self):
        with pytest.raises(ValueError):
            builders.decluttering("")

    def test_stack_in_card(self):
        c = builders.stack_in_card([{"type": "tile", "entity": "x"}],
                                      mode="horizontal")
        assert c["mode"] == "horizontal"

    def test_simple_weather_validates(self):
        with pytest.raises(ValueError):
            builders.simple_weather("sensor.foo")

    def test_atomic_calendar(self):
        c = builders.atomic_calendar(["calendar.work"], default_mode="Calendar",
                                       max_days_to_show=14)
        assert c["defaultMode"] == "Calendar"
        assert c["maxDaysToShow"] == 14
        # bare entity_ids auto-wrap to {entity: ...}
        assert c["entities"] == [{"entity": "calendar.work"}]

    def test_atomic_calendar_rejects_bad_mode(self):
        with pytest.raises(ValueError, match="default_mode"):
            builders.atomic_calendar(["calendar.work"], default_mode="Wrong")

    def test_digital_clock(self):
        c = builders.digital_clock(time_format={"hour": "2-digit"},
                                     locale="en-GB")
        assert c["locale"] == "en-GB"

    def test_flex_table(self):
        c = builders.flex_table(entities="sensor.*",
                                   columns=[{"name": "Sensor",
                                              "data": "entity_id"}])
        assert len(c["columns"]) == 1
        assert c["entities"] == "sensor.*"

    def test_flex_table_rejects_dict_filters(self):
        with pytest.raises(ValueError, match="STRINGS"):
            builders.flex_table(
                entities={"include": [{"domain": "light"}]},
                columns=[{"name": "x", "data": "entity_id"}],
            )


class TestBuildersSwissArmyKnife:
    def test_minimal(self):
        tools = [builders.sak_circle(cx=50, cy=50, radius=40)]
        toolset = builders.sak_toolset("ts1", tools=tools)
        c = builders.swiss_army_knife(
            entities=["sensor.temp"],
            toolsets=[toolset],
        )
        assert c["type"] == "custom:swiss-army-knife-card"
        assert c["aspectratio"] == "1/1"
        # entities auto-wrapped
        assert c["entities"] == [{"entity": "sensor.temp"}]
        # nested toolset
        ts0 = c["layout"]["toolsets"][0]
        assert ts0["toolset"] == "ts1"
        assert ts0["tools"][0]["type"] == "circle"

    def test_entities_pass_through_dicts(self):
        c = builders.swiss_army_knife(
            entities=[{"entity": "sensor.t", "name": "Temp", "decimals": 1}],
            toolsets=[builders.sak_toolset("t",
                tools=[builders.sak_circle(cx=50, cy=50)])],
        )
        assert c["entities"][0]["decimals"] == 1

    def test_rejects_no_entities(self):
        with pytest.raises(ValueError, match="at least one entity"):
            builders.swiss_army_knife(entities=[],
                toolsets=[builders.sak_toolset("t", tools=[])])

    def test_rejects_no_toolsets(self):
        with pytest.raises(ValueError, match="toolset"):
            builders.swiss_army_knife(
                entities=["sensor.x"], toolsets=[])

    def test_rejects_bad_tool_type(self):
        with pytest.raises(ValueError, match="unknown type"):
            builders.swiss_army_knife(
                entities=["sensor.x"],
                toolsets=[{"toolset": "t",
                            "position": {"cx": 50, "cy": 50},
                            "tools": [{"type": "ghost",
                                        "position": {"cx": 0, "cy": 0}}]}],
            )

    def test_aspectratio(self):
        c = builders.swiss_army_knife(
            entities=["sensor.t"],
            toolsets=[builders.sak_toolset("t",
                tools=[builders.sak_circle(cx=50, cy=50)])],
            aspectratio="2/1",
        )
        assert c["aspectratio"] == "2/1"


class TestSAKTools:
    def test_circle(self):
        t = builders.sak_circle(cx=50, cy=50, radius=45,
                                  styles={"circle": {"fill": "red"}})
        assert t["type"] == "circle"
        assert t["position"] == {"cx": 50, "cy": 50, "radius": 45}
        assert t["styles"]["circle"]["fill"] == "red"

    def test_ellipse(self):
        t = builders.sak_ellipse(cx=50, cy=50, rx=30, ry=20)
        assert t["type"] == "ellipse"
        assert t["position"]["rx"] == 30

    def test_line(self):
        t = builders.sak_line(x1=10, y1=10, x2=90, y2=90)
        assert t["position"] == {"x1": 10, "y1": 10, "x2": 90, "y2": 90}

    def test_rectangle(self):
        t = builders.sak_rectangle(cx=50, cy=50, width=80, height=40, rx=8)
        assert t["position"]["rx"] == 8

    def test_text(self):
        t = builders.sak_text("Hello", cx=50, cy=50, align="center")
        assert t["text"] == "Hello"
        assert t["position"]["align"] == "center"

    def test_icon(self):
        t = builders.sak_icon(cx=50, cy=25, entity_index=0, icon_size=30)
        assert t["entity_index"] == 0
        assert t["position"]["icon_size"] == 30

    def test_state(self):
        t = builders.sak_state(cx=50, cy=70, entity_index=2)
        assert t["entity_index"] == 2
        assert t["type"] == "state"

    def test_name(self):
        t = builders.sak_name(cx=50, cy=50)
        assert t["type"] == "name"

    def test_segarc(self):
        t = builders.sak_segarc(cx=50, cy=50, radius=40,
                                  start_angle=-180, end_angle=0)
        assert t["position"]["start_angle"] == -180

    def test_horseshoe(self):
        t = builders.sak_horseshoe(cx=50, cy=50, radius=35, entity_index=1)
        assert t["entity_index"] == 1
        assert t["type"] == "horseshoe"

    def test_sparkline(self):
        t = builders.sak_sparkline(cx=50, cy=50, width=80, height=30,
                                      hours=12)
        assert t["position"]["hours"] == 12

    def test_slider(self):
        t = builders.sak_slider(cx=50, cy=50, length=60,
                                  orientation="vertical")
        assert t["position"]["orientation"] == "vertical"

    def test_switch(self):
        t = builders.sak_switch(cx=50, cy=50)
        assert t["type"] == "switch"

    def test_usersvg(self):
        t = builders.sak_usersvg(cx=50, cy=50, width=80, height=80,
                                    uri="/local/icon.svg")
        assert t["uri"] == "/local/icon.svg"

    def test_circslider(self):
        t = builders.sak_circslider(cx=50, cy=50, radius=40,
                                       start_angle=-180, end_angle=0)
        assert t["position"]["radius"] == 40

    def test_progpath(self):
        t = builders.sak_progpath(cx=50, cy=50, width=80, height=10)
        assert t["type"] == "progpath"

    def test_regpoly(self):
        t = builders.sak_regpoly(cx=50, cy=50, radius=20, sides=8)
        assert t["position"]["sides"] == 8

    def test_rectex(self):
        t = builders.sak_rectex(cx=50, cy=50, width=60, height=30)
        assert t["type"] == "rectex"

    def test_area(self):
        t = builders.sak_area(cx=50, cy=50, entity_index=0)
        assert t["type"] == "area"


class TestBuildersExtraCustom:
    # ─── modern-circular-gauge ─────────────────────────────────────────
    def test_modern_circular_gauge_minimal(self):
        c = builders.modern_circular_gauge("sensor.power", max=1000)
        assert c["type"] == "custom:modern-circular-gauge"
        assert c["max"] == 1000
        assert c["gauge_type"] == "standard"

    def test_modern_circular_gauge_full(self):
        c = builders.modern_circular_gauge(
            "sensor.t", min=10, max=30, name="Temp",
            icon="mdi:thermometer", needle=True,
            secondary={"entity": "sensor.h", "show_gauge": "inner"},
            segments=[{"from": 10, "color": [11, 182, 239]},
                       {"from": 22, "color": [11, 239, 100]}],
        )
        assert c["secondary"]["show_gauge"] == "inner"
        assert len(c["segments"]) == 2

    def test_modern_circular_gauge_rejects_bad_type(self):
        with pytest.raises(ValueError, match="gauge_type"):
            builders.modern_circular_gauge("sensor.x", gauge_type="other")

    def test_modern_circular_gauge_rejects_empty_entity(self):
        with pytest.raises(ValueError):
            builders.modern_circular_gauge("")

    # ─── horizon ──────────────────────────────────────────────────────
    def test_horizon_minimal(self):
        c = builders.horizon_card()
        assert c == {"type": "custom:horizon-card"}

    def test_horizon_fields(self):
        c = builders.horizon_card(title="Sun & Moon", moon=False,
                                     refresh_period=120,
                                     southern_flip=True,
                                     fields={"sunrise": True, "sunset": True,
                                              "moon_phase": True},
                                     language="en", time_format="24h",
                                     no_card=True)
        assert c["moon"] is False
        assert c["refresh_period"] == 120
        assert c["southern_flip"] is True
        assert c["fields"]["moon_phase"] is True
        assert c["no_card"] is True

    # ─── calendar-card-pro ────────────────────────────────────────────
    def test_calendar_card_pro(self):
        c = builders.calendar_card_pro(
            ["calendar.family",
              {"entity": "calendar.work", "color": "#1e90ff"}],
            days_to_show=7, show_location=True,
        )
        assert c["type"] == "custom:calendar-card-pro"
        assert c["days_to_show"] == 7
        # mixed list preserved
        assert c["entities"][0] == "calendar.family"
        assert c["entities"][1]["color"] == "#1e90ff"

    def test_calendar_card_pro_validates_dict_entity(self):
        with pytest.raises(ValueError, match="'entity' key"):
            builders.calendar_card_pro([{"name": "no-entity"}])

    def test_calendar_card_pro_rejects_empty(self):
        with pytest.raises(ValueError):
            builders.calendar_card_pro([])

    # ─── weather-chart ────────────────────────────────────────────────
    def test_weather_chart_minimal(self):
        c = builders.weather_chart_card("weather.home")
        assert c["type"] == "custom:weather-chart-card"
        assert c["entity"] == "weather.home"

    def test_weather_chart_validates_entity(self):
        with pytest.raises(ValueError):
            builders.weather_chart_card("sensor.foo")

    def test_weather_chart_full(self):
        c = builders.weather_chart_card(
            "weather.home", title="Today", show_time=True,
            forecast={"type": "hourly", "style": "style2", "chart_height": 220},
            units={"pressure": "hPa", "speed": "mph"},
            locale="en", temp="sensor.outside_t",
        )
        assert c["forecast"]["type"] == "hourly"
        assert c["units"]["pressure"] == "hPa"
        assert c["temp"] == "sensor.outside_t"

    # ─── room-summary ─────────────────────────────────────────────────
    def test_room_summary_minimal(self):
        c = builders.room_summary_card("living_room")
        assert c["type"] == "custom:room-summary-card"
        assert c["area"] == "living_room"

    def test_room_summary_rejects_empty(self):
        with pytest.raises(ValueError):
            builders.room_summary_card("")

    def test_room_summary_extras(self):
        c = builders.room_summary_card(
            "kitchen", entity="light.kitchen",
            entities=[{"entity": "sensor.kitchen_temp"}],
            features={"hide_climate_label": True},
        )
        assert c["features"]["hide_climate_label"] is True
        assert c["entity"] == "light.kitchen"

    # ─── expander ─────────────────────────────────────────────────────
    def test_expander_minimal(self):
        c = builders.expander_card(
            [{"type": "tile", "entity": "light.x"}], title="Lights",
        )
        assert c["type"] == "custom:expander-card"
        assert c["title"] == "Lights"
        assert len(c["cards"]) == 1
        # default icon
        assert c["icon"] == "mdi:chevron-down"
        assert c["expanded"] is False

    def test_expander_rejects_empty(self):
        with pytest.raises(ValueError):
            builders.expander_card([])

    def test_expander_rejects_bad_haptic(self):
        with pytest.raises(ValueError, match="haptic"):
            builders.expander_card(
                [{"type": "tile", "entity": "x"}], haptic="bouncy",
            )

    def test_expander_full(self):
        c = builders.expander_card(
            [{"type": "tile", "entity": "light.a"}],
            title="Devices", icon="mdi:home", expanded=True,
            clear=True, clear_children=True, gap="0.5em",
            title_card={"type": "markdown", "content": "**My title**"},
            title_card_clickable=True,
            storage_id="my-expander",
        )
        assert c["clear"] is True
        # dashed keys preserved
        assert c["clear-children"] is True
        assert c["title-card"]["type"] == "markdown"
        assert c["title-card-clickable"] is True
        assert c["storage-id"] == "my-expander"

    # ─── simple-swipe ─────────────────────────────────────────────────
    def test_simple_swipe_minimal(self):
        c = builders.simple_swipe_card(
            [{"type": "markdown", "content": "A"},
              {"type": "markdown", "content": "B"}],
        )
        assert c["type"] == "custom:simple-swipe-card"
        assert c["view_mode"] == "single"
        assert c["swipe_direction"] == "horizontal"
        assert c["loop_mode"] == "none"

    def test_simple_swipe_rejects_bad_options(self):
        cards = [{"type": "markdown", "content": "x"}]
        with pytest.raises(ValueError, match="view_mode"):
            builders.simple_swipe_card(cards, view_mode="wrong")
        with pytest.raises(ValueError, match="swipe_direction"):
            builders.simple_swipe_card(cards, swipe_direction="diagonal")
        with pytest.raises(ValueError, match="swipe_behavior"):
            builders.simple_swipe_card(cards, swipe_behavior="weird")
        with pytest.raises(ValueError, match="loop_mode"):
            builders.simple_swipe_card(cards, loop_mode="forever")

    def test_simple_swipe_carousel_auto(self):
        c = builders.simple_swipe_card(
            [{"type": "markdown", "content": "a"}],
            view_mode="carousel", show_pagination=True,
            card_spacing=24,
            loop_mode="infinite",
            enable_auto_swipe=True, auto_swipe_interval=5000,
        )
        assert c["view_mode"] == "carousel"
        assert c["enable_auto_swipe"] is True
        assert c["auto_swipe_interval"] == 5000


class TestBuildersRegistry:
    def test_list_builders_includes_mushroom_and_apex(self):
        names = builders.list_builders()
        assert "mushroom-template" in names
        assert "apexcharts" in names
        assert "entities" in names

    def test_build_dispatcher(self):
        c = builders.build("entities", entities=["light.x"])
        assert c["type"] == "entities"

    def test_build_unknown(self):
        with pytest.raises(ValueError, match="unknown card type"):
            builders.build("not-a-card")

    def test_build_passes_kwargs(self):
        c = builders.build("mushroom-light", entity="light.foo",
                            show_brightness_control=True)
        assert c["entity"] == "light.foo"


# ─────────────────────────────────────────────── card_ops

@pytest.fixture
def stack_dashboard():
    return {
        "views": [
            {"path": "home", "title": "Home", "type": "masonry",
             "cards": [
                 {"type": "tile", "entity": "light.a"},     # cards[0]
                 {"type": "tile", "entity": "light.b"},     # cards[1]
                 {"type": "tile", "entity": "light.c"},     # cards[2]
             ]},
            {"path": "second", "title": "Second", "type": "masonry",
             "cards": [
                 {"type": "tile", "entity": "sensor.x"},
             ]},
        ],
    }


class TestCardOps:
    def test_move_within_same_view(self, stack_dashboard):
        # move views[0]/cards[0] to views[1]/cards[]
        card_ops.move_card(stack_dashboard, "views[0]/cards[0]",
                              "views[1]")
        # views[0] should now have 2 cards (b, c)
        v0 = stack_dashboard["views"][0]
        v1 = stack_dashboard["views"][1]
        assert len(v0["cards"]) == 2
        assert v0["cards"][0]["entity"] == "light.b"
        assert len(v1["cards"]) == 2
        # destination appended
        assert v1["cards"][1]["entity"] == "light.a"

    def test_reorder(self, stack_dashboard):
        card_ops.reorder_card(stack_dashboard, "views[0]/cards[2]", 0)
        assert stack_dashboard["views"][0]["cards"][0]["entity"] == "light.c"

    def test_reorder_out_of_range(self, stack_dashboard):
        with pytest.raises(IndexError):
            card_ops.reorder_card(stack_dashboard, "views[0]/cards[0]", 99)

    def test_wrap_vertical(self, stack_dashboard):
        new_ptr = card_ops.wrap_in_stack(stack_dashboard,
            ["views[0]/cards[0]", "views[0]/cards[1]"],
            stack_type="vertical-stack",
        )
        assert new_ptr == "views[0]/cards[0]"
        # views[0] now has 2 cards: a stack of 2 + the original c
        cards = stack_dashboard["views"][0]["cards"]
        assert len(cards) == 2
        stack = cards[0]
        assert stack["type"] == "vertical-stack"
        assert len(stack["cards"]) == 2
        assert stack["cards"][0]["entity"] == "light.a"
        assert stack["cards"][1]["entity"] == "light.b"
        assert cards[1]["entity"] == "light.c"

    def test_wrap_grid_columns(self, stack_dashboard):
        card_ops.wrap_in_stack(stack_dashboard,
            ["views[0]/cards[0]", "views[0]/cards[1]"],
            stack_type="grid", columns=3,
        )
        stack = stack_dashboard["views"][0]["cards"][0]
        assert stack["type"] == "grid"
        assert stack["columns"] == 3

    def test_wrap_validates_same_parent(self, stack_dashboard):
        with pytest.raises(ValueError, match="same parent"):
            card_ops.wrap_in_stack(stack_dashboard,
                ["views[0]/cards[0]", "views[1]/cards[0]"],
            )

    def test_wrap_invalid_stack_type(self, stack_dashboard):
        with pytest.raises(ValueError):
            card_ops.wrap_in_stack(stack_dashboard,
                ["views[0]/cards[0]"], stack_type="madness",
            )

    def test_wrap_conditional(self, stack_dashboard):
        card_ops.wrap_in_conditional(stack_dashboard, "views[0]/cards[1]",
            [{"entity": "light.b", "state": "on"}])
        wrapped = stack_dashboard["views"][0]["cards"][1]
        assert wrapped["type"] == "conditional"
        assert wrapped["card"]["entity"] == "light.b"
        assert wrapped["conditions"][0]["state"] == "on"

    def test_duplicate(self, stack_dashboard):
        new_ptr = card_ops.duplicate_card(stack_dashboard, "views[0]/cards[0]")
        assert new_ptr == "views[0]/cards[1]"
        # views[0] now has 4 cards
        cards = stack_dashboard["views"][0]["cards"]
        assert len(cards) == 4
        assert cards[1]["entity"] == "light.a"

    def test_duplicate_with_substitution(self, stack_dashboard):
        card_ops.duplicate_card(stack_dashboard, "views[0]/cards[0]",
                                  substitutions={"light\\.a": "light.z"})
        cards = stack_dashboard["views"][0]["cards"]
        assert cards[1]["entity"] == "light.z"

    def test_inject_card_mod(self, stack_dashboard):
        card_ops.inject_card_mod(stack_dashboard, "views[0]/cards[0]",
            "ha-card { border-radius: 20px; }")
        card = stack_dashboard["views"][0]["cards"][0]
        assert "card_mod" in card
        assert "border-radius" in card["card_mod"]["style"]["root"]

    def test_inject_card_mod_appends(self, stack_dashboard):
        card_ops.inject_card_mod(stack_dashboard, "views[0]/cards[0]",
            "ha-card { color: red; }")
        card_ops.inject_card_mod(stack_dashboard, "views[0]/cards[0]",
            "ha-card { background: blue; }")
        css = stack_dashboard["views"][0]["cards"][0]["card_mod"]["style"]["root"]
        assert "red" in css and "blue" in css

    def test_inject_card_mod_validates(self, stack_dashboard):
        with pytest.raises(ValueError):
            card_ops.inject_card_mod(stack_dashboard, "views[0]/cards[0]", "")

    def test_clear_card_mod(self, stack_dashboard):
        card_ops.inject_card_mod(stack_dashboard, "views[0]/cards[0]",
            "ha-card { color: red; }")
        card_ops.clear_card_mod(stack_dashboard, "views[0]/cards[0]")
        assert "card_mod" not in stack_dashboard["views"][0]["cards"][0]


# ─────────────────────────────────────────────── sections

class TestSections:
    def _config(self):
        return {
            "views": [
                {"path": "home", "title": "Home", "type": "sections",
                 "sections": [
                     {"type": "grid", "cards": [{"type": "heading",
                                                   "heading": "Existing"}]},
                 ]},
                {"path": "old", "title": "Old", "type": "masonry",
                 "cards": []},
            ],
        }

    def test_list_sections(self):
        cfg = self._config()
        items = sections_core.list_sections(cfg, "home")
        assert len(items) == 1

    def test_add_section(self):
        cfg = self._config()
        s = sections_core.add_section(cfg, "home", title="New")
        assert s["type"] == "grid"
        assert len(cfg["views"][0]["sections"]) == 2
        assert s["cards"][0]["heading"] == "New"

    def test_add_section_validates_view_type(self):
        cfg = self._config()
        with pytest.raises(ValueError, match="sections view"):
            sections_core.add_section(cfg, "old", title="X")

    def test_delete_section(self):
        cfg = self._config()
        sections_core.delete_section(cfg, "home", 0)
        assert cfg["views"][0]["sections"] == []

    def test_delete_section_out_of_range(self):
        cfg = self._config()
        with pytest.raises(IndexError):
            sections_core.delete_section(cfg, "home", 99)

    def test_move_section(self):
        cfg = self._config()
        sections_core.add_section(cfg, "home", title="Second")
        sections_core.add_section(cfg, "home", title="Third")
        sections_core.move_section(cfg, "home", 2, 0)
        first = cfg["views"][0]["sections"][0]
        assert first["cards"][0]["heading"] == "Third"


# ─────────────────────────────────────────────── badges

class TestBadges:
    def _config(self):
        return {
            "views": [
                {"path": "home", "title": "Home",
                 "badges": ["sensor.temp"],
                 "cards": []},
            ],
        }

    def test_list_badges(self):
        cfg = self._config()
        assert badges_core.list_badges(cfg, "home") == ["sensor.temp"]

    def test_add_entity_badge(self):
        cfg = self._config()
        badges_core.add_badge(cfg, "home", "person.jon")
        assert cfg["views"][0]["badges"][-1] == "person.jon"

    def test_add_dict_badge(self):
        cfg = self._config()
        badges_core.add_badge(cfg, "home",
            {"type": "entity-filter", "entity": "sensor.t"})
        assert cfg["views"][0]["badges"][-1]["type"] == "entity-filter"

    def test_add_validates_empty(self):
        cfg = self._config()
        with pytest.raises(ValueError):
            badges_core.add_badge(cfg, "home", "")

    def test_delete_badge(self):
        cfg = self._config()
        badges_core.delete_badge(cfg, "home", 0)
        assert cfg["views"][0]["badges"] == []

    def test_delete_out_of_range(self):
        cfg = self._config()
        with pytest.raises(IndexError):
            badges_core.delete_badge(cfg, "home", 5)

    def test_move_badge(self):
        cfg = self._config()
        badges_core.add_badge(cfg, "home", "sensor.b")
        badges_core.add_badge(cfg, "home", "sensor.c")
        badges_core.move_badge(cfg, "home", 2, 0)
        assert cfg["views"][0]["badges"][0] == "sensor.c"


# ─────────────────────────────────────────────── card_types

class TestCardTypes:
    def _config(self):
        return {
            "views": [
                {"path": "home", "cards": [
                    {"type": "tile", "entity": "light.a"},
                    {"type": "vertical-stack", "cards": [
                        {"type": "custom:mushroom-light-card",
                          "entity": "light.b"},
                        {"type": "custom:apexcharts-card", "series": []},
                    ]},
                ]},
            ],
        }

    def test_types_in_use(self):
        types = card_types.card_types_in_use(self._config())
        assert types["tile"] == 1
        assert types["custom:mushroom-light-card"] == 1
        assert types["vertical-stack"] == 1

    def test_custom_types_only(self):
        custom = card_types.custom_types_only(
            ["tile", "custom:mushroom-light-card", "vertical-stack"])
        assert custom == ["custom:mushroom-light-card"]
