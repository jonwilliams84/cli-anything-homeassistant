"""Unit tests for the `subscribe_entities` additions to `core/state_stream.py`.

Covers the compressed-state subscription (snapshot + diffs) and the
one-shot `entities_snapshot` helper.
"""

from __future__ import annotations

import threading

import pytest

from cli_anything.homeassistant.core import state_stream as ss


SNAPSHOT = {
    "a": {
        "light.kitchen": {"s": "on", "a": {"brightness": 200}},
        "sensor.temp": {"s": "21.5", "a": {"unit_of_measurement": "°C"}},
    }
}
DIFF = {"c": {"light.kitchen": {"+": {"s": "off"}}}}


class TestSubscribeEntities:
    def test_uses_subscribe_entities_command(self, subscribing_client):
        subscribing_client.queue_events(SNAPSHOT)
        ss.subscribe_entities(subscribing_client, on_message=lambda e: None, max_events=1)
        assert subscribing_client.subscribe_calls[-1] == ("subscribe_entities", None)

    def test_entity_filter_is_server_side(self, subscribing_client):
        subscribing_client.queue_events(SNAPSHOT)
        ss.subscribe_entities(
            subscribing_client,
            entity_ids=["light.kitchen"],
            on_message=lambda e: None,
            max_events=1,
        )
        assert subscribing_client.subscribe_calls[-1][1] == {"entity_ids": ["light.kitchen"]}

    def test_events_reach_callback(self, subscribing_client):
        subscribing_client.queue_events(SNAPSHOT, DIFF)
        seen = []
        ss.subscribe_entities(subscribing_client, on_message=seen.append, max_events=2)
        assert seen == [SNAPSHOT, DIFF]

    def test_caller_stop_event_accepted(self, subscribing_client):
        subscribing_client.queue_events(SNAPSHOT)
        stop = threading.Event()
        ss.subscribe_entities(subscribing_client, on_message=lambda e: None, stop_event=stop)
        assert subscribing_client.subscribe_calls

    def test_requires_callable(self, subscribing_client):
        with pytest.raises(ValueError, match="on_message"):
            ss.subscribe_entities(subscribing_client, on_message=None, max_events=1)

    def test_requires_stop_or_max(self, subscribing_client):
        with pytest.raises(ValueError, match="stop_event or max_events"):
            ss.subscribe_entities(subscribing_client, on_message=lambda e: None)

    def test_rejects_malformed_entity_id(self, subscribing_client):
        with pytest.raises(ValueError, match="domain.object_id"):
            ss.subscribe_entities(
                subscribing_client, entity_ids=["nodot"], on_message=lambda e: None, max_events=1
            )

    def test_rejects_non_list_entity_ids(self, subscribing_client):
        with pytest.raises(ValueError, match="entity_ids must be a list"):
            ss.subscribe_entities(
                subscribing_client, entity_ids="light.a", on_message=lambda e: None, max_events=1
            )


class TestEntitiesSnapshot:
    def test_returns_initial_states(self, subscribing_client):
        subscribing_client.queue_events(SNAPSHOT)
        snap = ss.entities_snapshot(subscribing_client)
        assert snap["light.kitchen"]["s"] == "on"
        assert set(snap) == {"light.kitchen", "sensor.temp"}

    def test_ignores_diff_only_events(self, subscribing_client):
        subscribing_client.queue_events(DIFF, SNAPSHOT)
        assert set(ss.entities_snapshot(subscribing_client)) == {"light.kitchen", "sensor.temp"}

    def test_entity_filter_forwarded(self, subscribing_client):
        subscribing_client.queue_events(SNAPSHOT)
        ss.entities_snapshot(subscribing_client, entity_ids=["light.kitchen"])
        assert subscribing_client.subscribe_calls[-1][1] == {"entity_ids": ["light.kitchen"]}

    def test_timeout_when_no_snapshot(self, subscribing_client):
        with pytest.raises(TimeoutError, match="no state snapshot"):
            ss.entities_snapshot(subscribing_client, timeout_seconds=0.2)

    def test_subscribe_error_propagates(self, subscribing_client):
        def boom(*args, **kwargs):
            raise RuntimeError("socket closed")

        subscribing_client.ws_subscribe = boom
        with pytest.raises(RuntimeError, match="socket closed"):
            ss.entities_snapshot(subscribing_client, timeout_seconds=1)

    def test_rejects_non_positive_timeout(self, subscribing_client):
        with pytest.raises(ValueError, match="timeout_seconds must be"):
            ss.entities_snapshot(subscribing_client, timeout_seconds=0)
