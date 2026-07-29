"""Tests for watch.py — callback error logging, until_state stop,
non-dict rejection, and event_type filtering.

These exercise the error-handling and stop-condition branches that
were previously uncovered.
"""

from __future__ import annotations

import logging
import threading

import pytest

from cli_anything.homeassistant.core import watch as watch_core


class TestSubscribeEventsCallback:
    def test_callback_receives_events(self, subscribing_client):
        """A user-supplied callback is invoked for each event."""
        received = []
        subscribing_client.queue_events(
            {"event_type": "state_changed", "data": {"entity_id": "sensor.a"}},
        )
        watch_core.subscribe_events(
            subscribing_client,
            event_type="state_changed",
            duration=0.5,
            callback=received.append,
        )
        assert len(received) == 1
        assert received[0]["data"]["entity_id"] == "sensor.a"

    def test_callback_exception_logged_not_raised(self, subscribing_client, caplog):
        """A callback that raises must not abort the watch — it logs a warning."""
        def bad_callback(event):
            raise RuntimeError("callback exploded")

        subscribing_client.queue_events(
            {"event_type": "state_changed", "data": {"entity_id": "sensor.a"}},
        )
        with caplog.at_level(logging.WARNING, logger="cli_anything.homeassistant.core.watch"):
            result = watch_core.subscribe_events(
                subscribing_client,
                event_type="state_changed",
                duration=0.5,
                callback=bad_callback,
            )
        # The event was still collected despite the callback error
        assert len(result) == 1
        # A warning was logged
        assert any("callback failed" in r.message for r in caplog.records)

    def test_non_dict_event_ignored(self, subscribing_client):
        """Non-dict events are silently dropped, not collected."""
        subscribing_client.queue_events(
            "not-a-dict",
            42,
            {"event_type": "state_changed", "data": {}},
        )
        result = watch_core.subscribe_events(
            subscribing_client,
            duration=0.5,
        )
        assert len(result) == 1

    def test_limit_stops_collection(self, subscribing_client):
        """When limit is reached, collection stops early."""
        subscribing_client.queue_events(
            {"event_type": "x", "data": {}},
            {"event_type": "x", "data": {}},
            {"event_type": "x", "data": {}},
        )
        result = watch_core.subscribe_events(
            subscribing_client,
            limit=2,
            duration=0.5,
        )
        assert len(result) == 2

    def test_no_event_type_subscribes_to_all(self, subscribing_client):
        """When event_type is None, payload is empty (subscribe to all)."""
        subscribing_client.queue_events({"event_type": "any", "data": {}})
        watch_core.subscribe_events(subscribing_client, duration=0.5)
        # The ws_subscribe call should have been made with empty/None payload
        assert len(subscribing_client.subscribe_calls) == 1
        msg_type, payload = subscribing_client.subscribe_calls[0]
        assert msg_type == "subscribe_events"
        assert payload is None or payload == {}


class TestWatchStateUntilState:
    def test_until_state_stops_collection(self, subscribing_client):
        """When until_state is matched, collection stops."""
        subscribing_client.queue_events(
            {"data": {"entity_id": "light.a", "new_state": {"state": "on"}}},
            {"data": {"entity_id": "light.a", "new_state": {"state": "off"}}},
            {"data": {"entity_id": "light.a", "new_state": {"state": "on"}}},
        )
        result = watch_core.watch_state(
            subscribing_client,
            entity_id="light.a",
            until_state="off",
            duration=0.5,
        )
        # Should stop after seeing "off" — the third event is not collected
        assert len(result) == 2
        assert result[1]["data"]["new_state"]["state"] == "off"

    def test_until_state_not_matched_collects_all(self, subscribing_client):
        """When until_state never matches, all matching events are collected."""
        subscribing_client.queue_events(
            {"data": {"entity_id": "light.a", "new_state": {"state": "on"}}},
            {"data": {"entity_id": "light.a", "new_state": {"state": "on"}}},
        )
        result = watch_core.watch_state(
            subscribing_client,
            entity_id="light.a",
            until_state="off",
            duration=0.5,
        )
        assert len(result) == 2

    def test_callback_exception_logged(self, subscribing_client, caplog):
        """A broken callback in watch_state logs a warning, doesn't abort."""
        def bad_cb(event):
            raise ValueError("broken")

        subscribing_client.queue_events(
            {"data": {"entity_id": "light.a", "new_state": {"state": "on"}}},
        )
        with caplog.at_level(logging.WARNING, logger="cli_anything.homeassistant.core.watch"):
            result = watch_core.watch_state(
                subscribing_client,
                entity_id="light.a",
                duration=0.5,
                callback=bad_cb,
            )
        assert len(result) == 1
        assert any("callback failed" in r.message for r in caplog.records)

    def test_non_dict_event_ignored(self, subscribing_client):
        """Non-dict events are dropped in watch_state too."""
        subscribing_client.queue_events(
            "garbage",
            {"data": {"entity_id": "light.a", "new_state": {"state": "on"}}},
        )
        result = watch_core.watch_state(
            subscribing_client,
            entity_id="light.a",
            duration=0.5,
        )
        assert len(result) == 1

    def test_wrong_entity_filtered_out(self, subscribing_client):
        """Events for other entities are not collected."""
        subscribing_client.queue_events(
            {"data": {"entity_id": "light.b", "new_state": {"state": "on"}}},
            {"data": {"entity_id": "light.a", "new_state": {"state": "on"}}},
        )
        result = watch_core.watch_state(
            subscribing_client,
            entity_id="light.a",
            duration=0.5,
        )
        assert len(result) == 1
        assert result[0]["data"]["entity_id"] == "light.a"

    def test_until_state_with_missing_new_state(self, subscribing_client):
        """When new_state is absent, until_state comparison doesn't crash."""
        subscribing_client.queue_events(
            {"data": {"entity_id": "light.a"}},  # no new_state key
            {"data": {"entity_id": "light.a", "new_state": {"state": "on"}}},
        )
        result = watch_core.watch_state(
            subscribing_client,
            entity_id="light.a",
            until_state="on",
            duration=0.5,
        )
        # First event has no new_state so doesn't match; second matches and stops
        assert len(result) == 2
