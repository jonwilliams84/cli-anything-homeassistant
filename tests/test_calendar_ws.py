"""Unit tests for cli_anything.homeassistant.core.calendar_ws — WS event CRUD."""

from __future__ import annotations

from datetime import datetime, timedelta, date

import pytest

from cli_anything.homeassistant.core import calendar_ws


ENTITY_ID = "calendar.my_calendar"
BAD_ENTITY = "sensor.temperature"


class TestCalendarWs:
    """Tests for calendar WS event CRUD operations."""

    # ════════════════════════════════════════════════════════════ create_event

    def test_create_event_with_dtend_minimal(self, fake_client):
        """create_event sends minimal payload with summary, start, end."""
        fake_client.set_ws("calendar/event/create", {
            "uid": "abc123",
            "summary": "Dentist",
            "start": "2026-05-20T10:00:00",
            "end": "2026-05-20T11:00:00",
        })
        event = {
            "summary": "Dentist",
            "start": "2026-05-20T10:00:00",
            "end": "2026-05-20T11:00:00",
        }
        result = calendar_ws.create_event(fake_client, entity_id=ENTITY_ID, event=event)

        # Verify WS payload exactness
        assert fake_client.ws_calls == [
            {
                "type": "calendar/event/create",
                "payload": {
                    "entity_id": ENTITY_ID,
                    "event": event,
                },
            }
        ]
        # Verify return shape
        assert isinstance(result, dict)
        assert result.get("uid") == "abc123"
        assert result.get("summary") == "Dentist"

    def test_create_event_with_duration(self, fake_client):
        """create_event accepts duration instead of end."""
        fake_client.set_ws("calendar/event/create", {
            "uid": "def456",
            "summary": "Meeting",
            "start": "2026-05-21T14:00:00",
            "duration": "PT1H",
        })
        event = {
            "summary": "Meeting",
            "start": "2026-05-21T14:00:00",
            "duration": "PT1H",
        }
        result = calendar_ws.create_event(fake_client, entity_id=ENTITY_ID, event=event)

        # Verify WS payload
        assert fake_client.ws_calls[-1] == {
            "type": "calendar/event/create",
            "payload": {
                "entity_id": ENTITY_ID,
                "event": event,
            },
        }
        assert result.get("uid") == "def456"
        assert result.get("summary") == "Meeting"

    def test_create_event_with_optional_fields(self, fake_client):
        """create_event includes description, location, rrule when provided."""
        fake_client.set_ws("calendar/event/create", {"uid": "ghi789"})
        event = {
            "summary": "Weekly Standup",
            "start": "2026-05-22T09:00:00",
            "end": "2026-05-22T09:30:00",
            "description": "Team sync",
            "location": "Conference Room A",
            "rrule": "FREQ=WEEKLY;BYDAY=MO",
        }
        calendar_ws.create_event(fake_client, entity_id=ENTITY_ID, event=event)

        payload = fake_client.ws_calls[-1]["payload"]["event"]
        assert payload["summary"] == "Weekly Standup"
        assert payload["description"] == "Team sync"
        assert payload["location"] == "Conference Room A"
        assert payload["rrule"] == "FREQ=WEEKLY;BYDAY=MO"

    def test_create_event_bad_entity_id(self, fake_client):
        """create_event raises ValueError for non-calendar.* entity_id."""
        with pytest.raises(ValueError, match="expected calendar\\.*"):
            calendar_ws.create_event(
                fake_client,
                entity_id=BAD_ENTITY,
                event={"summary": "x", "start": "2026-05-20", "end": "2026-05-21"},
            )

    def test_create_event_missing_summary(self, fake_client):
        """create_event raises ValueError when summary is missing."""
        with pytest.raises(ValueError, match="event missing required field: summary"):
            calendar_ws.create_event(
                fake_client,
                entity_id=ENTITY_ID,
                event={"start": "2026-05-20", "end": "2026-05-21"},
            )

    def test_create_event_missing_start(self, fake_client):
        """create_event raises ValueError when start is missing."""
        with pytest.raises(ValueError, match="event missing required field: start"):
            calendar_ws.create_event(
                fake_client,
                entity_id=ENTITY_ID,
                event={"summary": "Event", "end": "2026-05-21"},
            )

    def test_create_event_missing_end_and_duration(self, fake_client):
        """create_event raises ValueError when both end and duration are missing."""
        with pytest.raises(ValueError, match="event must have either 'end' or 'duration'"):
            calendar_ws.create_event(
                fake_client,
                entity_id=ENTITY_ID,
                event={"summary": "Event", "start": "2026-05-20"},
            )

    # ════════════════════════════════════════════════════════════ update_event

    def test_update_event_minimal(self, fake_client):
        """update_event sends minimal payload with entity_id, uid, event."""
        fake_client.set_ws("calendar/event/update", {})
        event = {
            "uid": "abc123",
            "summary": "Updated Dentist",
        }
        calendar_ws.update_event(fake_client, entity_id=ENTITY_ID, event=event)

        assert fake_client.ws_calls[-1] == {
            "type": "calendar/event/update",
            "payload": {
                "entity_id": ENTITY_ID,
                "event": event,
            },
        }

    def test_update_event_with_recurrence_id(self, fake_client):
        """update_event includes recurrence_id when provided."""
        fake_client.set_ws("calendar/event/update", {})
        event = {"uid": "abc123", "summary": "Updated"}
        calendar_ws.update_event(
            fake_client,
            entity_id=ENTITY_ID,
            event=event,
            recurrence_id="2026-05-27T10:00:00",
        )

        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["recurrence_id"] == "2026-05-27T10:00:00"
        assert payload["event"]["uid"] == "abc123"

    def test_update_event_with_recurrence_range_thisandfuture(self, fake_client):
        """update_event accepts THISANDFUTURE as recurrence_range."""
        fake_client.set_ws("calendar/event/update", {})
        event = {"uid": "abc123", "summary": "Updated"}
        calendar_ws.update_event(
            fake_client,
            entity_id=ENTITY_ID,
            event=event,
            recurrence_range="THISANDFUTURE",
        )

        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["recurrence_range"] == "THISANDFUTURE"

    def test_update_event_with_recurrence_range_empty_string(self, fake_client):
        """update_event accepts empty string as recurrence_range."""
        fake_client.set_ws("calendar/event/update", {})
        event = {"uid": "abc123", "summary": "Updated"}
        calendar_ws.update_event(
            fake_client,
            entity_id=ENTITY_ID,
            event=event,
            recurrence_range="",
        )

        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["recurrence_range"] == ""

    def test_update_event_with_all_optional_recurrence(self, fake_client):
        """update_event includes both recurrence_id and recurrence_range."""
        fake_client.set_ws("calendar/event/update", {})
        event = {"uid": "abc123", "summary": "Updated"}
        calendar_ws.update_event(
            fake_client,
            entity_id=ENTITY_ID,
            event=event,
            recurrence_id="2026-05-27T10:00:00",
            recurrence_range="THISANDFUTURE",
        )

        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["recurrence_id"] == "2026-05-27T10:00:00"
        assert payload["recurrence_range"] == "THISANDFUTURE"

    def test_update_event_bad_entity_id(self, fake_client):
        """update_event raises ValueError for non-calendar.* entity_id."""
        with pytest.raises(ValueError, match="expected calendar\\.*"):
            calendar_ws.update_event(
                fake_client,
                entity_id=BAD_ENTITY,
                event={"uid": "abc123"},
            )

    def test_update_event_missing_uid(self, fake_client):
        """update_event raises ValueError when event missing uid."""
        with pytest.raises(ValueError, match="event missing required field: uid"):
            calendar_ws.update_event(
                fake_client,
                entity_id=ENTITY_ID,
                event={"summary": "Updated"},
            )

    def test_update_event_bad_recurrence_range(self, fake_client):
        """update_event raises ValueError for invalid recurrence_range."""
        with pytest.raises(ValueError, match="recurrence_range must be"):
            calendar_ws.update_event(
                fake_client,
                entity_id=ENTITY_ID,
                event={"uid": "abc123"},
                recurrence_range="INVALID",
            )

    # ════════════════════════════════════════════════════════════ delete_event

    def test_delete_event_minimal(self, fake_client):
        """delete_event sends minimal payload with entity_id, uid."""
        fake_client.set_ws("calendar/event/delete", {})
        calendar_ws.delete_event(fake_client, entity_id=ENTITY_ID, uid="abc123")

        assert fake_client.ws_calls[-1] == {
            "type": "calendar/event/delete",
            "payload": {
                "entity_id": ENTITY_ID,
                "uid": "abc123",
            },
        }

    def test_delete_event_with_recurrence_id(self, fake_client):
        """delete_event includes recurrence_id when provided."""
        fake_client.set_ws("calendar/event/delete", {})
        calendar_ws.delete_event(
            fake_client,
            entity_id=ENTITY_ID,
            uid="abc123",
            recurrence_id="2026-05-27T10:00:00",
        )

        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["uid"] == "abc123"
        assert payload["recurrence_id"] == "2026-05-27T10:00:00"

    def test_delete_event_with_recurrence_range_thisandfuture(self, fake_client):
        """delete_event accepts THISANDFUTURE as recurrence_range."""
        fake_client.set_ws("calendar/event/delete", {})
        calendar_ws.delete_event(
            fake_client,
            entity_id=ENTITY_ID,
            uid="abc123",
            recurrence_range="THISANDFUTURE",
        )

        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["recurrence_range"] == "THISANDFUTURE"

    def test_delete_event_with_recurrence_range_empty_string(self, fake_client):
        """delete_event accepts empty string as recurrence_range."""
        fake_client.set_ws("calendar/event/delete", {})
        calendar_ws.delete_event(
            fake_client,
            entity_id=ENTITY_ID,
            uid="abc123",
            recurrence_range="",
        )

        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["recurrence_range"] == ""

    def test_delete_event_with_all_optional_recurrence(self, fake_client):
        """delete_event includes both recurrence_id and recurrence_range."""
        fake_client.set_ws("calendar/event/delete", {})
        calendar_ws.delete_event(
            fake_client,
            entity_id=ENTITY_ID,
            uid="abc123",
            recurrence_id="2026-05-27T10:00:00",
            recurrence_range="THISANDFUTURE",
        )

        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["uid"] == "abc123"
        assert payload["recurrence_id"] == "2026-05-27T10:00:00"
        assert payload["recurrence_range"] == "THISANDFUTURE"

    def test_delete_event_bad_entity_id(self, fake_client):
        """delete_event raises ValueError for non-calendar.* entity_id."""
        with pytest.raises(ValueError, match="expected calendar\\.*"):
            calendar_ws.delete_event(
                fake_client,
                entity_id=BAD_ENTITY,
                uid="abc123",
            )

    def test_delete_event_empty_uid(self, fake_client):
        """delete_event raises ValueError when uid is empty."""
        with pytest.raises(ValueError, match="uid must be a non-empty"):
            calendar_ws.delete_event(
                fake_client,
                entity_id=ENTITY_ID,
                uid="",
            )

    def test_delete_event_bad_recurrence_range(self, fake_client):
        """delete_event raises ValueError for invalid recurrence_range."""
        with pytest.raises(ValueError, match="recurrence_range must be"):
            calendar_ws.delete_event(
                fake_client,
                entity_id=ENTITY_ID,
                uid="abc123",
                recurrence_range="INVALID",
            )
