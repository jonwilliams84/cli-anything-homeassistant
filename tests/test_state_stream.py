"""Unit tests for cli_anything.homeassistant.core.state_stream.

FakeClient (from conftest) does not implement ws_subscribe. This module
defines SubscribingFakeClient — a tiny subclass that shims ws_subscribe to:

1. Record each call as (msg_type, payload) in ``subscribe_calls``.
2. Immediately deliver a queue of pre-set event dicts to on_message.
3. Then set the stop_event so the subscription terminates cleanly.

This allows all four state_stream functions to be exercised without a real
WebSocket connection.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from tests.conftest import FakeClient
from cli_anything.homeassistant.core.state_stream import (
    collect_events,
    subscribe_events,
    subscribe_state_changed,
    subscribe_trigger,
)


# ────────────────────────────────────────────────────────────────────────────
# SubscribingFakeClient — ws_subscribe shim
# ────────────────────────────────────────────────────────────────────────────

class SubscribingFakeClient(FakeClient):
    """FakeClient subclass that supports ws_subscribe.

    Attributes
    ----------
    subscribe_calls:
        List of ``(msg_type, payload)`` tuples recorded for each
        ws_subscribe invocation.
    queued_events:
        Events to deliver synchronously before returning. Populated by
        tests via ``queue_events()``.
    """

    def __init__(self) -> None:
        super().__init__()
        self.subscribe_calls: list[tuple[str, Any]] = []
        self.queued_events: list[Any] = []

    def queue_events(self, *events: Any) -> None:
        """Pre-load events to be delivered by the next ws_subscribe call."""
        self.queued_events.extend(events)

    def ws_subscribe(
        self,
        msg_type: str,
        payload: dict | None,
        on_message,
        stop_event: threading.Event,
    ) -> None:
        """Shim: record the call, deliver queued events, then stop."""
        self.subscribe_calls.append((msg_type, payload))
        for event in self.queued_events:
            if stop_event.is_set():
                break
            on_message(event)
        self.queued_events.clear()
        # Signal stop so callers that block on the event loop can return.
        stop_event.set()


# ────────────────────────────────────────────────────────────────────────────
# Fixture
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def subscribing_client() -> SubscribingFakeClient:
    return SubscribingFakeClient()


# ────────────────────────────────────────────────────────────────────────────
# Tests
# ────────────────────────────────────────────────────────────────────────────

class TestStateStream:

    # ── subscribe_events ────────────────────────────────────────────────────

    def test_subscribe_events_happy_path(self, subscribing_client):
        """subscribe_events sends the correct WS command and delivers events."""
        ev = {"event_type": "test_event", "data": {}}
        subscribing_client.queue_events(ev)

        received: list = []
        stop = threading.Event()
        subscribe_events(
            subscribing_client,
            event_type="test_event",
            on_event=received.append,
            stop_event=stop,
        )

        assert len(subscribing_client.subscribe_calls) == 1
        msg_type, payload = subscribing_client.subscribe_calls[0]
        assert msg_type == "subscribe_events"
        assert payload == {"event_type": "test_event"}
        assert received == [ev]

    def test_subscribe_events_no_event_type(self, subscribing_client):
        """subscribe_events without event_type sends an empty (None) payload."""
        subscribing_client.queue_events({"data": {}})
        received: list = []
        stop = threading.Event()
        subscribe_events(
            subscribing_client,
            on_event=received.append,
            stop_event=stop,
        )
        _, payload = subscribing_client.subscribe_calls[0]
        assert payload is None  # no event_type → payload is falsy / None
        assert len(received) == 1

    def test_subscribe_events_max_events_auto_stop(self, subscribing_client):
        """subscribe_events with max_events stops after receiving that many."""
        ev1 = {"n": 1}
        ev2 = {"n": 2}
        subscribing_client.queue_events(ev1, ev2)

        received: list = []
        subscribe_events(
            subscribing_client,
            on_event=received.append,
            max_events=2,
        )
        assert received == [ev1, ev2]

    def test_subscribe_events_raises_without_stop_or_max(self, subscribing_client):
        with pytest.raises(ValueError, match="must supply stop_event or max_events"):
            subscribe_events(
                subscribing_client,
                on_event=lambda e: None,
            )

    def test_subscribe_events_raises_on_empty_event_type(self, subscribing_client):
        with pytest.raises(ValueError, match="event_type must be non-empty"):
            subscribe_events(
                subscribing_client,
                event_type="",
                on_event=lambda e: None,
                max_events=1,
            )

    def test_subscribe_events_raises_on_non_callable_on_event(self, subscribing_client):
        with pytest.raises(ValueError, match="on_event must be callable"):
            subscribe_events(
                subscribing_client,
                on_event="not_callable",  # type: ignore[arg-type]
                max_events=1,
            )

    # ── subscribe_state_changed ─────────────────────────────────────────────

    def test_subscribe_state_changed_happy_path(self, subscribing_client):
        """subscribe_state_changed uses subscribe_events with state_changed."""
        ev = {"data": {"entity_id": "light.kitchen", "new_state": {"state": "on"}}}
        subscribing_client.queue_events(ev)

        received: list = []
        stop = threading.Event()
        subscribe_state_changed(
            subscribing_client,
            on_change=received.append,
            stop_event=stop,
        )

        assert len(subscribing_client.subscribe_calls) == 1
        msg_type, payload = subscribing_client.subscribe_calls[0]
        assert msg_type == "subscribe_events"
        assert payload == {"event_type": "state_changed"}
        assert received == [ev]

    def test_subscribe_state_changed_filters_by_entity_id(self, subscribing_client):
        """Only events matching entity_ids are forwarded to on_change."""
        ev_match = {"data": {"entity_id": "light.kitchen"}}
        ev_skip = {"data": {"entity_id": "switch.garage"}}
        subscribing_client.queue_events(ev_match, ev_skip)

        received: list = []
        stop = threading.Event()
        subscribe_state_changed(
            subscribing_client,
            entity_ids=["light.kitchen"],
            on_change=received.append,
            stop_event=stop,
        )

        assert received == [ev_match]

    def test_subscribe_state_changed_entity_ids_empty_filter(self, subscribing_client):
        """entity_ids=None means no filtering — all state_changed events pass."""
        ev1 = {"data": {"entity_id": "sensor.temp"}}
        ev2 = {"data": {"entity_id": "sensor.humidity"}}
        subscribing_client.queue_events(ev1, ev2)

        received: list = []
        stop = threading.Event()
        subscribe_state_changed(
            subscribing_client,
            entity_ids=None,
            on_change=received.append,
            stop_event=stop,
        )

        assert received == [ev1, ev2]

    def test_subscribe_state_changed_max_events_with_filter(self, subscribing_client):
        """max_events counts only passed-through (filtered) events."""
        ev_match = {"data": {"entity_id": "light.kitchen"}}
        ev_skip = {"data": {"entity_id": "switch.garage"}}
        subscribing_client.queue_events(ev_skip, ev_match)

        received: list = []
        subscribe_state_changed(
            subscribing_client,
            entity_ids=["light.kitchen"],
            on_change=received.append,
            max_events=1,
        )
        assert received == [ev_match]

    def test_subscribe_state_changed_raises_without_stop_or_max(self, subscribing_client):
        with pytest.raises(ValueError, match="must supply stop_event or max_events"):
            subscribe_state_changed(
                subscribing_client,
                on_change=lambda e: None,
            )

    def test_subscribe_state_changed_raises_on_non_callable(self, subscribing_client):
        with pytest.raises(ValueError, match="on_change must be callable"):
            subscribe_state_changed(
                subscribing_client,
                on_change=42,  # type: ignore[arg-type]
                max_events=1,
            )

    # ── subscribe_trigger ───────────────────────────────────────────────────

    def test_subscribe_trigger_happy_path(self, subscribing_client):
        """subscribe_trigger sends the subscribe_trigger WS command."""
        trigger_def = {"platform": "state", "entity_id": "binary_sensor.motion"}
        ev = {"trigger": trigger_def, "description": "triggered"}
        subscribing_client.queue_events(ev)

        received: list = []
        stop = threading.Event()
        subscribe_trigger(
            subscribing_client,
            trigger=trigger_def,
            on_trigger=received.append,
            stop_event=stop,
        )

        assert len(subscribing_client.subscribe_calls) == 1
        msg_type, payload = subscribing_client.subscribe_calls[0]
        assert msg_type == "subscribe_trigger"
        assert payload["trigger"] == trigger_def
        assert "variables" not in payload
        assert received == [ev]

    def test_subscribe_trigger_with_variables(self, subscribing_client):
        """variables are included in the WS payload when supplied."""
        trigger_def = {"platform": "time", "at": "07:00:00"}
        variables = {"zone": "home"}
        subscribing_client.queue_events({"data": {}})

        stop = threading.Event()
        subscribe_trigger(
            subscribing_client,
            trigger=trigger_def,
            variables=variables,
            on_trigger=lambda e: None,
            stop_event=stop,
        )

        _, payload = subscribing_client.subscribe_calls[0]
        assert payload["variables"] == variables

    def test_subscribe_trigger_raises_on_empty_trigger(self, subscribing_client):
        with pytest.raises(ValueError, match="trigger must be a non-empty dict"):
            subscribe_trigger(
                subscribing_client,
                trigger={},
                on_trigger=lambda e: None,
                max_events=1,
            )

    def test_subscribe_trigger_raises_on_non_dict_trigger(self, subscribing_client):
        with pytest.raises(ValueError, match="trigger must be a non-empty dict"):
            subscribe_trigger(
                subscribing_client,
                trigger="state",  # type: ignore[arg-type]
                on_trigger=lambda e: None,
                max_events=1,
            )

    def test_subscribe_trigger_raises_without_stop_or_max(self, subscribing_client):
        with pytest.raises(ValueError, match="must supply stop_event or max_events"):
            subscribe_trigger(
                subscribing_client,
                trigger={"platform": "state", "entity_id": "x"},
                on_trigger=lambda e: None,
            )

    def test_subscribe_trigger_raises_on_non_callable(self, subscribing_client):
        with pytest.raises(ValueError, match="on_trigger must be callable"):
            subscribe_trigger(
                subscribing_client,
                trigger={"platform": "state", "entity_id": "x"},
                on_trigger=None,  # type: ignore[arg-type]
                max_events=1,
            )

    # ── collect_events ──────────────────────────────────────────────────────

    def test_collect_events_returns_count_events(self, subscribing_client):
        """collect_events returns exactly count events."""
        ev1 = {"n": 1}
        ev2 = {"n": 2}
        subscribing_client.queue_events(ev1, ev2)

        result = collect_events(subscribing_client, count=2, timeout_seconds=5.0)

        assert result == [ev1, ev2]

    def test_collect_events_single_event(self, subscribing_client):
        """collect_events(count=1) returns a one-element list."""
        ev = {"type": "ping"}
        subscribing_client.queue_events(ev)
        result = collect_events(subscribing_client, count=1)
        assert result == [ev]

    def test_collect_events_with_event_type_filter(self, subscribing_client):
        """event_type is forwarded to the WS subscription."""
        ev = {"event_type": "custom", "data": {}}
        subscribing_client.queue_events(ev)

        result = collect_events(
            subscribing_client,
            event_type="custom",
            count=1,
            timeout_seconds=5.0,
        )

        assert result == [ev]
        _, payload = subscribing_client.subscribe_calls[0]
        assert payload == {"event_type": "custom"}

    def test_collect_events_timeout_raises(self):
        """collect_events raises TimeoutError when events never arrive."""
        # A client whose ws_subscribe blocks briefly but yields no events.
        class SlowClient(SubscribingFakeClient):
            def ws_subscribe(self, msg_type, payload, on_message, stop_event):
                self.subscribe_calls.append((msg_type, payload))
                # deliver no events; just wait for stop_event
                stop_event.wait(timeout=0.05)

        client = SlowClient()
        with pytest.raises(TimeoutError, match="collect_events"):
            collect_events(client, count=1, timeout_seconds=0.1)

    def test_collect_events_raises_on_invalid_count(self, subscribing_client):
        with pytest.raises(ValueError, match="count must be >= 1"):
            collect_events(subscribing_client, count=0)

    def test_collect_events_raises_on_invalid_timeout(self, subscribing_client):
        with pytest.raises(ValueError, match="timeout_seconds must be > 0"):
            collect_events(subscribing_client, count=1, timeout_seconds=0.0)

    def test_collect_events_raises_on_empty_event_type(self, subscribing_client):
        with pytest.raises(ValueError, match="event_type must be non-empty"):
            collect_events(subscribing_client, event_type="", count=1)
