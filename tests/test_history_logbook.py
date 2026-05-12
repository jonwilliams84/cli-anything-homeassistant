"""Unit tests for cli_anything.homeassistant.core.history_logbook."""

from __future__ import annotations

import pytest

from tests.conftest import FakeClient
from cli_anything.homeassistant.core.history_logbook import (
    history_during_period,
    history_stream,
    logbook_get_events,
    logbook_event_stream,
)


# ────────────────────────────────────────────────────────────────────────────
# Test fixtures
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def fake_client() -> FakeClient:
    return FakeClient()


class TestHistoryLogbook:
    """Tests for history and logbook WebSocket API wrappers."""

    # ── history_during_period ───────────────────────────────────────────────

    def test_history_during_period_happy_path(self, fake_client):
        """history_during_period sends correct WS payload with required fields."""
        response = {"light.kitchen": [{"state": "on"}]}
        fake_client.set_ws("history/history_during_period", response)

        result = history_during_period(
            fake_client,
            start_time="2024-01-01T00:00:00Z",
            entity_ids=["light.kitchen", "light.bedroom"],
        )

        assert result == response
        assert len(fake_client.ws_calls) == 1
        call = fake_client.ws_calls[0]
        assert call["type"] == "history/history_during_period"
        payload = call["payload"]
        assert payload == {
            "start_time": "2024-01-01T00:00:00Z",
            "entity_ids": ["light.kitchen", "light.bedroom"],
        }

    def test_history_during_period_with_end_time(self, fake_client):
        """end_time is included when provided."""
        fake_client.set_ws("history/history_during_period", {})

        history_during_period(
            fake_client,
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-01-02T00:00:00Z",
            entity_ids=["sensor.temp"],
        )

        payload = fake_client.ws_calls[0]["payload"]
        assert payload["end_time"] == "2024-01-02T00:00:00Z"

    def test_history_during_period_with_flags(self, fake_client):
        """Optional flags are included when True."""
        fake_client.set_ws("history/history_during_period", {})

        history_during_period(
            fake_client,
            start_time="2024-01-01T00:00:00Z",
            entity_ids=["light.kitchen"],
            minimal_response=True,
            no_attributes=True,
            significant_changes_only=False,
        )

        payload = fake_client.ws_calls[0]["payload"]
        assert payload["minimal_response"] is True
        assert payload["no_attributes"] is True
        assert payload["significant_changes_only"] is False

    def test_history_during_period_raises_empty_start_time(self, fake_client):
        """Raises ValueError when start_time is empty."""
        with pytest.raises(ValueError, match="start_time is required"):
            history_during_period(
                fake_client,
                start_time="",
                entity_ids=["light.kitchen"],
            )

    def test_history_during_period_raises_none_start_time(self, fake_client):
        """Raises ValueError when start_time is None."""
        with pytest.raises(ValueError, match="start_time is required"):
            history_during_period(
                fake_client,
                start_time=None,  # type: ignore[arg-type]
                entity_ids=["light.kitchen"],
            )

    def test_history_during_period_raises_empty_entity_ids(self, fake_client):
        """Raises ValueError when entity_ids is empty."""
        with pytest.raises(ValueError, match="entity_ids must be a non-empty list"):
            history_during_period(
                fake_client,
                start_time="2024-01-01T00:00:00Z",
                entity_ids=[],
            )

    # ── history_stream ──────────────────────────────────────────────────────

    def test_history_stream_happy_path(self, fake_client):
        """history_stream sends correct WS payload with required fields."""
        response = {"subscription": "history/stream"}
        fake_client.set_ws("history/stream", response)

        result = history_stream(
            fake_client,
            entity_ids=["light.kitchen"],
            start_time="2024-01-01T00:00:00Z",
        )

        assert result == response
        assert len(fake_client.ws_calls) == 1
        call = fake_client.ws_calls[0]
        assert call["type"] == "history/stream"
        payload = call["payload"]
        assert payload == {
            "entity_ids": ["light.kitchen"],
            "start_time": "2024-01-01T00:00:00Z",
        }

    def test_history_stream_with_end_time(self, fake_client):
        """end_time is included when provided."""
        fake_client.set_ws("history/stream", {})

        history_stream(
            fake_client,
            entity_ids=["sensor.temp"],
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-01-02T00:00:00Z",
        )

        payload = fake_client.ws_calls[0]["payload"]
        assert payload["end_time"] == "2024-01-02T00:00:00Z"

    def test_history_stream_with_flags(self, fake_client):
        """Optional flags are included when True."""
        fake_client.set_ws("history/stream", {})

        history_stream(
            fake_client,
            entity_ids=["light.kitchen"],
            start_time="2024-01-01T00:00:00Z",
            minimal_response=True,
            no_attributes=True,
            significant_changes_only=False,
        )

        payload = fake_client.ws_calls[0]["payload"]
        assert payload["minimal_response"] is True
        assert payload["no_attributes"] is True
        assert payload["significant_changes_only"] is False

    def test_history_stream_raises_empty_entity_ids(self, fake_client):
        """Raises ValueError when entity_ids is empty."""
        with pytest.raises(ValueError, match="entity_ids must be a non-empty list"):
            history_stream(
                fake_client,
                entity_ids=[],
                start_time="2024-01-01T00:00:00Z",
            )

    def test_history_stream_raises_empty_start_time(self, fake_client):
        """Raises ValueError when start_time is empty."""
        with pytest.raises(ValueError, match="start_time is required"):
            history_stream(
                fake_client,
                entity_ids=["light.kitchen"],
                start_time="",
            )

    # ── logbook_get_events ──────────────────────────────────────────────────

    def test_logbook_get_events_happy_path(self, fake_client):
        """logbook_get_events sends correct WS payload with required field."""
        response = {"events": [{"entity_id": "light.kitchen", "state": "on"}]}
        fake_client.set_ws("logbook/get_events", response)

        result = logbook_get_events(
            fake_client,
            start_time="2024-01-01T00:00:00Z",
        )

        assert result == response
        assert len(fake_client.ws_calls) == 1
        call = fake_client.ws_calls[0]
        assert call["type"] == "logbook/get_events"
        payload = call["payload"]
        assert payload == {"start_time": "2024-01-01T00:00:00Z"}

    def test_logbook_get_events_with_all_filters(self, fake_client):
        """All optional filters are included when provided."""
        fake_client.set_ws("logbook/get_events", {})

        logbook_get_events(
            fake_client,
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-01-02T00:00:00Z",
            entity_ids=["light.kitchen", "switch.garage"],
            device_ids=["device_1", "device_2"],
            context_id="ctx_123",
        )

        payload = fake_client.ws_calls[0]["payload"]
        assert payload["end_time"] == "2024-01-02T00:00:00Z"
        assert payload["entity_ids"] == ["light.kitchen", "switch.garage"]
        assert payload["device_ids"] == ["device_1", "device_2"]
        assert payload["context_id"] == "ctx_123"

    def test_logbook_get_events_empty_filters_omitted(self, fake_client):
        """Empty lists for entity_ids/device_ids are omitted from payload."""
        fake_client.set_ws("logbook/get_events", {})

        logbook_get_events(
            fake_client,
            start_time="2024-01-01T00:00:00Z",
            entity_ids=[],
            device_ids=[],
        )

        payload = fake_client.ws_calls[0]["payload"]
        assert "entity_ids" not in payload
        assert "device_ids" not in payload

    def test_logbook_get_events_raises_empty_start_time(self, fake_client):
        """Raises ValueError when start_time is empty."""
        with pytest.raises(ValueError, match="start_time is required"):
            logbook_get_events(
                fake_client,
                start_time="",
            )

    def test_logbook_get_events_raises_none_start_time(self, fake_client):
        """Raises ValueError when start_time is None."""
        with pytest.raises(ValueError, match="start_time is required"):
            logbook_get_events(
                fake_client,
                start_time=None,  # type: ignore[arg-type]
            )

    # ── logbook_event_stream ────────────────────────────────────────────────

    def test_logbook_event_stream_happy_path(self, fake_client):
        """logbook_event_stream sends correct WS payload with required field."""
        response = {"subscription": "logbook/event_stream"}
        fake_client.set_ws("logbook/event_stream", response)

        result = logbook_event_stream(
            fake_client,
            start_time="2024-01-01T00:00:00Z",
        )

        assert result == response
        assert len(fake_client.ws_calls) == 1
        call = fake_client.ws_calls[0]
        assert call["type"] == "logbook/event_stream"
        payload = call["payload"]
        assert payload == {"start_time": "2024-01-01T00:00:00Z"}

    def test_logbook_event_stream_with_filters(self, fake_client):
        """Optional filters are included when provided."""
        fake_client.set_ws("logbook/event_stream", {})

        logbook_event_stream(
            fake_client,
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-01-02T00:00:00Z",
            entity_ids=["light.kitchen"],
            device_ids=["device_1"],
        )

        payload = fake_client.ws_calls[0]["payload"]
        assert payload["end_time"] == "2024-01-02T00:00:00Z"
        assert payload["entity_ids"] == ["light.kitchen"]
        assert payload["device_ids"] == ["device_1"]

    def test_logbook_event_stream_empty_filters_omitted(self, fake_client):
        """Empty lists for entity_ids/device_ids are omitted from payload."""
        fake_client.set_ws("logbook/event_stream", {})

        logbook_event_stream(
            fake_client,
            start_time="2024-01-01T00:00:00Z",
            entity_ids=[],
            device_ids=[],
        )

        payload = fake_client.ws_calls[0]["payload"]
        assert "entity_ids" not in payload
        assert "device_ids" not in payload

    def test_logbook_event_stream_raises_empty_start_time(self, fake_client):
        """Raises ValueError when start_time is empty."""
        with pytest.raises(ValueError, match="start_time is required"):
            logbook_event_stream(
                fake_client,
                start_time="",
            )

    def test_logbook_event_stream_raises_none_start_time(self, fake_client):
        """Raises ValueError when start_time is None."""
        with pytest.raises(ValueError, match="start_time is required"):
            logbook_event_stream(
                fake_client,
                start_time=None,  # type: ignore[arg-type]
            )

    # ── Return-shape tests (non-streaming functions) ─────────────────────────

    def test_history_during_period_return_shape(self, fake_client):
        """history_during_period returns the response dict unchanged."""
        expected = {
            "light.kitchen": [
                {"state": "on", "last_changed": "2024-01-01T00:00:00Z"},
                {"state": "off", "last_changed": "2024-01-01T06:00:00Z"},
            ],
            "light.bedroom": [
                {"state": "on", "last_changed": "2024-01-01T02:00:00Z"},
            ],
        }
        fake_client.set_ws("history/history_during_period", expected)

        result = history_during_period(
            fake_client,
            start_time="2024-01-01T00:00:00Z",
            entity_ids=["light.kitchen", "light.bedroom"],
        )

        assert result == expected
        assert isinstance(result, dict)

    def test_logbook_get_events_return_shape(self, fake_client):
        """logbook_get_events returns the response dict unchanged."""
        expected = {
            "events": [
                {
                    "entity_id": "light.kitchen",
                    "state": "on",
                    "context_user_id": "user_123",
                },
                {
                    "entity_id": "automation.night_mode",
                    "context_user_id": "automation",
                },
            ]
        }
        fake_client.set_ws("logbook/get_events", expected)

        result = logbook_get_events(
            fake_client,
            start_time="2024-01-01T00:00:00Z",
        )

        assert result == expected
        assert isinstance(result, dict)
