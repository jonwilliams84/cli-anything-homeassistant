"""Unit tests for cli_anything.homeassistant.core.calendars — REST/service CRUD.

Covers the uncovered paths in calendars.py: list_calendars filtering,
events() service-response unwrapping + REST fallback, create/update/delete
service-data shaping, and all validation error paths.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import calendars


ENTITY = "calendar.work"
BAD_ENTITY = "sensor.temp"


# ── list_calendars ───────────────────────────────────────────────────────────


class TestListCalendars:
    def test_filters_non_calendar_entities(self, fake_client):
        """Only calendar.* entities appear in the result."""
        fake_client.set("GET", "states", [
            {"entity_id": "calendar.work", "state": "off",
             "attributes": {"friendly_name": "Work Calendar"}},
            {"entity_id": "sensor.temp", "state": "23.5",
             "attributes": {"friendly_name": "Temperature"}},
            {"entity_id": "calendar.home", "state": "on",
             "attributes": {"friendly_name": "Home"}},
        ])
        rows = calendars.list_calendars(fake_client)
        ids = [r["entity_id"] for r in rows]
        assert ids == ["calendar.work", "calendar.home"]
        assert rows[0]["name"] == "Work Calendar"
        assert rows[0]["state"] == "off"
        assert rows[0]["attributes"] == {"friendly_name": "Work Calendar"}

    def test_handles_missing_attributes(self, fake_client):
        """Entities with no attributes dict still produce a row."""
        fake_client.set("GET", "states", [
            {"entity_id": "calendar.bare", "state": "off"},
        ])
        rows = calendars.list_calendars(fake_client)
        assert len(rows) == 1
        assert rows[0]["name"] is None
        assert rows[0]["attributes"] is None

    def test_empty_states_returns_empty(self, fake_client):
        fake_client.set("GET", "states", [])
        assert calendars.list_calendars(fake_client) == []


# ── events ───────────────────────────────────────────────────────────────────


class TestEvents:
    def test_service_response_unwrap(self, fake_client):
        """When calendar.get_events returns {service_response: {entity: {events: [...]}}}
        the events list is extracted."""
        fake_client.set_service("calendar", "get_events", {
            "service_response": {
                ENTITY: {"events": [{"summary": "Meeting"}]},
            },
        })
        evs = calendars.events(fake_client, ENTITY,
                               start="2026-01-01T00:00:00",
                               end="2026-01-02T00:00:00")
        assert evs == [{"summary": "Meeting"}]

    def test_service_response_flat_dict(self, fake_client):
        """When the response is a flat dict keyed by entity_id, events are extracted."""
        fake_client.set_service("calendar", "get_events", {
            ENTITY: {"events": [{"summary": "Lunch"}]},
        })
        evs = calendars.events(fake_client, ENTITY,
                               start="2026-01-01T00:00:00",
                               end="2026-01-02T00:00:00")
        assert evs == [{"summary": "Lunch"}]

    def test_service_response_events_not_list(self, fake_client):
        """If the 'events' key exists but isn't a list, return empty list."""
        fake_client.set_service("calendar", "get_events", {
            ENTITY: {"events": "not a list"},
        })
        evs = calendars.events(fake_client, ENTITY,
                               start="2026-01-01T00:00:00",
                               end="2026-01-02T00:00:00")
        assert evs == []

    def test_service_response_no_entry_falls_back_to_rest(self, fake_client):
        """When the service response has no entry for this entity, fall back to REST."""
        fake_client.set_service("calendar", "get_events", {})
        fake_client.set("GET", f"calendars/{ENTITY}", [{"summary": "REST event"}])
        evs = calendars.events(fake_client, ENTITY,
                               start="2026-01-01T00:00:00",
                               end="2026-01-02T00:00:00")
        assert evs == [{"summary": "REST event"}]

    def test_rest_fallback_includes_params(self, fake_client):
        """REST fallback passes start and end as query params."""
        fake_client.set_service("calendar", "get_events", {})
        fake_client.set("GET", f"calendars/{ENTITY}", [])
        calendars.events(fake_client, ENTITY,
                         start="2026-03-01T00:00:00",
                         end="2026-03-02T00:00:00")
        rest_call = [c for c in fake_client.calls if c["verb"] == "GET" and "calendars/" in c["path"]]
        assert len(rest_call) == 1
        assert rest_call[0]["params"] == {"start": "2026-03-01T00:00:00",
                                          "end": "2026-03-02T00:00:00"}

    def test_duration_param_sent_to_service(self, fake_client):
        """When duration is given, it's included in the service data and end is omitted."""
        fake_client.set_service("calendar", "get_events", {})
        calendars.events(fake_client, ENTITY,
                         start="2026-01-01T00:00:00",
                         duration="PT2H")
        svc_call = [c for c in fake_client.service_calls
                    if c["domain"] == "calendar" and c["service"] == "get_events"]
        assert len(svc_call) == 1
        data = svc_call[0]["service_data"]
        assert data["duration"] == "PT2H"
        assert "end_date_time" not in data

    def test_bad_entity_raises(self, fake_client):
        with pytest.raises(ValueError, match="expected calendar"):
            calendars.events(fake_client, BAD_ENTITY)

    def test_defaults_applied_when_no_start_end(self, fake_client):
        """When start/end are not given, defaults are generated (now / +7d)."""
        fake_client.set_service("calendar", "get_events", {})
        calendars.events(fake_client, ENTITY)
        svc_call = [c for c in fake_client.service_calls
                    if c["domain"] == "calendar" and c["service"] == "get_events"]
        assert len(svc_call) == 1
        data = svc_call[0]["service_data"]
        assert "start_date_time" in data
        assert "end_date_time" in data


# ── create_event ─────────────────────────────────────────────────────────────


class TestCreateEvent:
    def test_timed_event_uses_datetime_keys(self, fake_client):
        """Start with 'T' → start_date_time / end_date_time."""
        fake_client.set_service("calendar", "create_event", {})
        calendars.create_event(fake_client, ENTITY,
                               summary="Dentist",
                               start="2026-05-20T10:00:00",
                               end="2026-05-20T11:00:00")
        data = fake_client.service_calls[-1]["service_data"]
        assert data["summary"] == "Dentist"
        assert data["start_date_time"] == "2026-05-20T10:00:00"
        assert data["end_date_time"] == "2026-05-20T11:00:00"
        assert "start_date" not in data

    def test_all_day_event_uses_date_keys(self, fake_client):
        """Start without 'T' → start_date / end_date."""
        fake_client.set_service("calendar", "create_event", {})
        calendars.create_event(fake_client, ENTITY,
                               summary="Holiday",
                               start="2026-05-20",
                               end="2026-05-21")
        data = fake_client.service_calls[-1]["service_data"]
        assert data["start_date"] == "2026-05-20"
        assert data["end_date"] == "2026-05-21"
        assert "start_date_time" not in data

    def test_optional_fields_included(self, fake_client):
        fake_client.set_service("calendar", "create_event", {})
        calendars.create_event(fake_client, ENTITY,
                               summary="Conf",
                               start="2026-05-20T10:00:00",
                               description="Yearly review",
                               location="Room 42",
                               rrule="FREQ=YEARLY")
        data = fake_client.service_calls[-1]["service_data"]
        assert data["description"] == "Yearly review"
        assert data["location"] == "Room 42"
        assert data["rrule"] == "FREQ=YEARLY"

    def test_no_end_omits_end_key(self, fake_client):
        fake_client.set_service("calendar", "create_event", {})
        calendars.create_event(fake_client, ENTITY,
                               summary="No end",
                               start="2026-05-20T10:00:00")
        data = fake_client.service_calls[-1]["service_data"]
        assert "end_date_time" not in data
        assert "end_date" not in data

    def test_target_entity_id_in_payload(self, fake_client):
        """The entity_id is folded into the service payload via target."""
        fake_client.set_service("calendar", "create_event", {})
        calendars.create_event(fake_client, ENTITY,
                               summary="X", start="2026-05-20T10:00:00")
        data = fake_client.service_calls[-1]["service_data"]
        assert data["entity_id"] == ENTITY

    def test_bad_entity_raises(self, fake_client):
        with pytest.raises(ValueError, match="expected calendar"):
            calendars.create_event(fake_client, BAD_ENTITY,
                                   summary="X", start="2026-05-20")

    def test_empty_summary_raises(self, fake_client):
        with pytest.raises(ValueError, match="summary is required"):
            calendars.create_event(fake_client, ENTITY,
                                   summary="", start="2026-05-20")

    def test_empty_start_raises(self, fake_client):
        with pytest.raises(ValueError, match="start is required"):
            calendars.create_event(fake_client, ENTITY,
                                   summary="X", start="")


# ── delete_event ─────────────────────────────────────────────────────────────


class TestDeleteEvent:
    def test_minimal_payload(self, fake_client):
        fake_client.set_service("calendar", "delete_event", {})
        calendars.delete_event(fake_client, ENTITY, uid="evt-123")
        data = fake_client.service_calls[-1]["service_data"]
        assert data["uid"] == "evt-123"
        assert data["entity_id"] == ENTITY
        assert "recurrence_id" not in data
        assert "recurrence_range" not in data

    def test_recurrence_fields_included(self, fake_client):
        fake_client.set_service("calendar", "delete_event", {})
        calendars.delete_event(fake_client, ENTITY,
                               uid="evt-123",
                               recurrence_id="2026-05-20T10:00:00",
                               recurrence_range="ALL")
        data = fake_client.service_calls[-1]["service_data"]
        assert data["recurrence_id"] == "2026-05-20T10:00:00"
        assert data["recurrence_range"] == "ALL"

    def test_bad_entity_raises(self, fake_client):
        with pytest.raises(ValueError, match="expected calendar"):
            calendars.delete_event(fake_client, BAD_ENTITY, uid="x")

    def test_empty_uid_raises(self, fake_client):
        with pytest.raises(ValueError, match="uid is required"):
            calendars.delete_event(fake_client, ENTITY, uid="")


# ── update_event ─────────────────────────────────────────────────────────────


class TestUpdateEvent:
    def test_timed_start_end(self, fake_client):
        fake_client.set_service("calendar", "update_event", {})
        calendars.update_event(fake_client, ENTITY,
                               uid="evt-1",
                               summary="Updated",
                               start="2026-06-01T09:00:00",
                               end="2026-06-01T10:00:00")
        data = fake_client.service_calls[-1]["service_data"]
        assert data["uid"] == "evt-1"
        assert data["summary"] == "Updated"
        assert data["start_date_time"] == "2026-06-01T09:00:00"
        assert data["end_date_time"] == "2026-06-01T10:00:00"

    def test_all_day_start_end(self, fake_client):
        fake_client.set_service("calendar", "update_event", {})
        calendars.update_event(fake_client, ENTITY,
                               uid="evt-1",
                               start="2026-06-01",
                               end="2026-06-02")
        data = fake_client.service_calls[-1]["service_data"]
        assert data["start_date"] == "2026-06-01"
        assert data["end_date"] == "2026-06-02"
        assert "start_date_time" not in data

    def test_optional_fields(self, fake_client):
        fake_client.set_service("calendar", "update_event", {})
        calendars.update_event(fake_client, ENTITY,
                               uid="evt-1",
                               description="New desc",
                               location="New loc",
                               rrule="FREQ=DAILY",
                               recurrence_id="2026-06-01",
                               recurrence_range="SINGLE")
        data = fake_client.service_calls[-1]["service_data"]
        assert data["description"] == "New desc"
        assert data["location"] == "New loc"
        assert data["rrule"] == "FREQ=DAILY"
        assert data["recurrence_id"] == "2026-06-01"
        assert data["recurrence_range"] == "SINGLE"

    def test_only_uid_sent_when_no_overrides(self, fake_client):
        """When no optional fields are given, only uid + entity_id are in the payload."""
        fake_client.set_service("calendar", "update_event", {})
        calendars.update_event(fake_client, ENTITY, uid="evt-1")
        data = fake_client.service_calls[-1]["service_data"]
        assert data["uid"] == "evt-1"
        assert data["entity_id"] == ENTITY
        # No other keys should be present besides uid and entity_id
        assert set(data.keys()) == {"uid", "entity_id"}

    def test_bad_entity_raises(self, fake_client):
        with pytest.raises(ValueError, match="expected calendar"):
            calendars.update_event(fake_client, BAD_ENTITY, uid="x")

    def test_empty_uid_raises(self, fake_client):
        with pytest.raises(ValueError, match="uid is required"):
            calendars.update_event(fake_client, ENTITY, uid="")
