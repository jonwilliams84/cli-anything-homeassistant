"""v6 — coverage tests for previously-untested core modules.

Modules covered:
  * core/groups.py
  * core/lovelace_mirror.py (pure-Python paths)
  * core/mqtt_discovery.py
  * core/template_helpers.py (validation paths only — full flow needs e2e)
  * core/watch.py
  * core/_ws_subscribe_utils.py
"""

from __future__ import annotations

import threading

import pytest

from cli_anything.homeassistant.core import (
    _ws_subscribe_utils as ws_utils,
    groups as groups_core,
    lovelace_mirror as mirror_core,
    mqtt_discovery as mqtt_discovery_core,
    template_helpers as template_helpers_core,
    watch as watch_core,
)


# ─── groups (template-render based) ───────────────────────────────────────

class TestGroups:
    def test_expand_parses_rendered_pipe_format(self, fake_client):
        from cli_anything.homeassistant.core import template as template_core
        from unittest import mock
        rendered = (
            "light.a|||on|||Light A\n"
            "light.b|||off|||\n"
        )
        with mock.patch.object(template_core, "render", return_value=rendered):
            rows = groups_core.expand(fake_client, "group.lights")
        assert [r["entity_id"] for r in rows] == ["light.a", "light.b"]
        assert rows[0]["state"] == "on"
        assert rows[0]["friendly_name"] == "Light A"
        assert "friendly_name" not in rows[1]

    def test_expand_requires_domain_dot_object(self, fake_client):
        with pytest.raises(ValueError):
            groups_core.expand(fake_client, "no-dot")

    def test_deep_expand_returns_ids_only(self, fake_client):
        from cli_anything.homeassistant.core import template as template_core
        from unittest import mock
        rendered = "light.x|||on|||\nlight.y|||off|||\n"
        with mock.patch.object(template_core, "render", return_value=rendered):
            out = groups_core.deep_expand(fake_client, "group.x")
        assert out == ["light.x", "light.y"]


# ─── lovelace_mirror (pure-Python paths) ──────────────────────────────────

class TestLovelaceMirror:
    def test_substitute_string_rules(self):
        # Substitution is literal/case-sensitive; supply the exact tokens.
        rules = [("Kitchen", "Lounge"), ("upstairs", "downstairs")]
        out = mirror_core._substitute(
            {"title": "Kitchen Lights", "tap_action": {
                "entity_id": "light.upstairs_main"}},
            rules,
        )
        assert out["title"] == "Lounge Lights"
        assert out["tap_action"]["entity_id"] == "light.downstairs_main"

    def test_substitute_walks_lists(self):
        rules = [("a", "b")]
        out = mirror_core._substitute(["aa", {"x": "a"}, ["a", "c"]], rules)
        assert out == ["bb", {"x": "b"}, ["b", "c"]]

    def test_substitute_does_not_mutate_input(self):
        original = {"title": "Old"}
        out = mirror_core._substitute(original, [("Old", "New")])
        assert out["title"] == "New"
        assert original["title"] == "Old"

    def test_section_room_keys_picks_up_room_selector_visibility(self):
        section = {
            "type": "grid",
            "visibility": [
                {"condition": "state", "entity": "input_select.room_selector_a",
                  "state": "Kitchen"},
                {"condition": "state", "entity": "input_select.room_selector_a",
                  "state": "Lounge"},
                {"condition": "state", "entity": "input_select.unrelated",
                  "state": "Other"},
            ],
        }
        keys = set(mirror_core._section_room_keys(section))
        assert keys == {"Kitchen", "Lounge"}


# ─── mqtt_discovery ───────────────────────────────────────────────────────

class TestMqttDiscovery:
    def test_delete_publishes_empty_retained_payload(self, fake_client):
        fake_client.set_service("mqtt", "publish", {"ok": True})
        mqtt_discovery_core.delete(fake_client, "homeassistant/sensor/foo/config")
        last = [c for c in fake_client.service_calls
                 if c["domain"] == "mqtt" and c["service"] == "publish"][-1]
        assert last["service_data"]["topic"] == "homeassistant/sensor/foo/config"
        assert last["service_data"].get("retain") is True
        assert last["service_data"].get("payload", "") == ""

    def test_republish_calls_mqtt_reload(self, fake_client):
        fake_client.set_service("mqtt", "reload", {"ok": True})
        mqtt_discovery_core.republish(fake_client)
        pairs = [(c["domain"], c["service"]) for c in fake_client.service_calls]
        assert ("mqtt", "reload") in pairs


# ─── template_helpers (validation only — full flow needs e2e) ────────────

class TestTemplateHelpersValidation:
    def test_create_rejects_invalid_template_type(self, fake_client):
        with pytest.raises(ValueError, match="template_type"):
            template_helpers_core.create(
                fake_client, name="x", state_template="{{ 1 }}",
                template_type="not-a-real-type",
            )

    def test_create_requires_name(self, fake_client):
        with pytest.raises(ValueError, match="name"):
            template_helpers_core.create(
                fake_client, name="", state_template="{{ 1 }}",
            )

    def test_create_requires_state_template(self, fake_client):
        with pytest.raises(ValueError, match="state_template"):
            template_helpers_core.create(
                fake_client, name="x", state_template="",
            )

    def test_update_requires_entry_id(self, fake_client):
        with pytest.raises(ValueError, match="entry_id"):
            template_helpers_core.update(fake_client, "")


# ─── watch ────────────────────────────────────────────────────────────────

class TestWatch:
    def test_subscribe_events_returns_collected(self, subscribing_client):
        subscribing_client.queue_events(
            {"event_type": "state_changed", "data": {"entity_id": "sensor.a"}},
            {"event_type": "state_changed", "data": {"entity_id": "sensor.b"}},
        )
        out = watch_core.subscribe_events(
            subscribing_client, event_type="state_changed", limit=10,
        )
        assert isinstance(out, list)
        # SubscribingFakeClient delivers all queued events
        assert len(out) == 2

    def test_watch_state_filters_to_entity(self, subscribing_client):
        subscribing_client.queue_events(
            {"data": {"entity_id": "light.a"}},
            {"data": {"entity_id": "light.b"}},  # ignored
            {"data": {"entity_id": "light.a"}},
        )
        out = watch_core.watch_state(
            subscribing_client, entity_id="light.a", duration=0.5,
        )
        assert isinstance(out, list)
        for ev in out:
            assert ev["data"]["entity_id"] == "light.a"

    def test_watch_state_empty_entity_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="entity_id"):
            watch_core.watch_state(fake_client, entity_id="")


# ─── _ws_subscribe_utils ─────────────────────────────────────────────────

class TestWsSubscribeUtils:
    def test_resolve_stop_event_creates_when_none(self):
        # When stop_event is None and max_events is supplied, we get a new
        # event back with caller_owns_it=True.
        stop, owns = ws_utils.resolve_stop_event(None, max_events=5)
        assert isinstance(stop, threading.Event)
        assert owns is True
        assert not stop.is_set()

    def test_resolve_stop_event_returns_caller_event(self):
        existing = threading.Event()
        stop, owns = ws_utils.resolve_stop_event(existing, max_events=None)
        assert stop is existing
        assert owns is False

    def test_resolve_stop_event_requires_one_of_them(self):
        with pytest.raises(ValueError):
            ws_utils.resolve_stop_event(None, None)

    def test_validate_callable_accepts_callable(self):
        def cb(_e): pass
        ws_utils.validate_callable(cb)  # no raise

    def test_validate_callable_rejects_non_callable(self):
        # Implementation raises ValueError (not TypeError)
        with pytest.raises(ValueError):
            ws_utils.validate_callable("not a function")

    def test_validate_count_or_stop_requires_one(self):
        with pytest.raises(ValueError):
            ws_utils.validate_count_or_stop(None, None)

    def test_validate_count_or_stop_accepts_max_events(self):
        ws_utils.validate_count_or_stop(None, 5)

    def test_validate_count_or_stop_accepts_stop_event(self):
        ws_utils.validate_count_or_stop(threading.Event(), None)

    def test_wrap_with_max_events_increments_and_stops(self):
        stop = threading.Event()
        seen: list[int] = []
        wrapped = ws_utils.wrap_with_max_events(
            lambda e: seen.append(e),
            stop_event=stop, owns_stop=True, max_events=2,
        )
        wrapped("a")
        assert not stop.is_set()
        wrapped("b")
        assert stop.is_set()
        # And the calls still landed
        assert seen == ["a", "b"]

    def test_wrap_with_max_events_passes_through_when_not_owning(self):
        stop = threading.Event()
        wrapped = ws_utils.wrap_with_max_events(
            lambda _: None,
            stop_event=stop, owns_stop=False, max_events=2,
        )
        # Many calls; stop never set (because owner is the caller)
        for _ in range(10):
            wrapped("x")
        assert not stop.is_set()
