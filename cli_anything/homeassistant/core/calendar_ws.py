"""Calendar event CRUD via WebSocket — create/update/delete events.

The HA calendar component exposes three WebSocket commands for event management:
  - calendar/event/create  {entity_id, event}
  - calendar/event/update  {entity_id, event, uid, recurrence_id?, recurrence_range?}
  - calendar/event/delete  {entity_id, uid, recurrence_id?, recurrence_range?}

Events use RFC 5545 format (iCalendar). The `event` dict requires:
  - summary: str
  - start: datetime.date | datetime.datetime (ISO 8601 strings or Python objects)
  - end: datetime.date | datetime.datetime | duration: timedelta (one of end or duration)
  - description, location, rrule: optional

For recurring events, recurrence_range ∈ {"", "THISANDFUTURE"} controls scope.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


def create_event(client, *, entity_id: str, event: dict) -> dict:
    """Create a NEW calendar event via WS.

    Args:
        client: HA WebSocket client.
        entity_id: Calendar entity (must start with "calendar.").
        event: Event dict with required {summary, start, end|duration} and
               optional {description, location, rrule}.

    Returns:
        The created event dict as returned by HA.

    Raises:
        ValueError: If entity_id doesn't match domain or event is malformed.
    """
    if not entity_id.startswith("calendar."):
        raise ValueError(f"expected calendar.* entity_id, got {entity_id!r}")

    if not isinstance(event, dict):
        raise ValueError("event must be a dict")

    # Validate required fields: summary + dtstart + (dtend or duration)
    if "summary" not in event:
        raise ValueError("event missing required field: summary")

    if "start" not in event:
        raise ValueError("event missing required field: start")

    has_end = "end" in event
    has_duration = "duration" in event
    if not (has_end or has_duration):
        raise ValueError("event must have either 'end' or 'duration'")

    payload = {
        "entity_id": entity_id,
        "event": event,
    }
    return client.ws_call("calendar/event/create", payload)


def update_event(client, *, entity_id: str, event: dict,
                 recurrence_id: str | None = None,
                 recurrence_range: str | None = None) -> dict:
    """Update an existing calendar event via WS.

    Args:
        client: HA WebSocket client.
        entity_id: Calendar entity (must start with "calendar.").
        event: Updated event dict (must include uid, partial updates OK).
        recurrence_id: ISO 8601 datetime for a recurring event instance.
        recurrence_range: "" or "THISANDFUTURE" to control scope.

    Returns:
        The updated event dict as returned by HA.

    Raises:
        ValueError: If entity_id doesn't match domain, event is missing uid,
                   or recurrence_range is invalid.
    """
    if not entity_id.startswith("calendar."):
        raise ValueError(f"expected calendar.* entity_id, got {entity_id!r}")

    if not isinstance(event, dict):
        raise ValueError("event must be a dict")

    if "uid" not in event:
        raise ValueError("event missing required field: uid")

    if recurrence_range is not None and recurrence_range not in ("", "THISANDFUTURE"):
        raise ValueError(
            f"recurrence_range must be '' or 'THISANDFUTURE', got {recurrence_range!r}"
        )

    payload: dict[str, Any] = {
        "entity_id": entity_id,
        "event": event,
    }
    if recurrence_id is not None:
        payload["recurrence_id"] = recurrence_id
    if recurrence_range is not None:
        payload["recurrence_range"] = recurrence_range

    return client.ws_call("calendar/event/update", payload)


def delete_event(client, *, entity_id: str, uid: str,
                 recurrence_id: str | None = None,
                 recurrence_range: str | None = None) -> dict:
    """Delete a calendar event via WS.

    Args:
        client: HA WebSocket client.
        entity_id: Calendar entity (must start with "calendar.").
        uid: Event UID (unique identifier); must be non-empty.
        recurrence_id: ISO 8601 datetime for a recurring event instance.
        recurrence_range: "" or "THISANDFUTURE" to control scope.

    Returns:
        Empty dict {} on success.

    Raises:
        ValueError: If entity_id doesn't match domain, uid is empty,
                   or recurrence_range is invalid.
    """
    if not entity_id.startswith("calendar."):
        raise ValueError(f"expected calendar.* entity_id, got {entity_id!r}")

    if not uid:
        raise ValueError("uid must be a non-empty string")

    if recurrence_range is not None and recurrence_range not in ("", "THISANDFUTURE"):
        raise ValueError(
            f"recurrence_range must be '' or 'THISANDFUTURE', got {recurrence_range!r}"
        )

    payload: dict[str, Any] = {
        "entity_id": entity_id,
        "uid": uid,
    }
    if recurrence_id is not None:
        payload["recurrence_id"] = recurrence_id
    if recurrence_range is not None:
        payload["recurrence_range"] = recurrence_range

    return client.ws_call("calendar/event/delete", payload)
