"""Calendar entities — list / events / create / update / delete.

REST + service surfaces:
  - GET /api/calendars                        — inventory of calendar.* entities
  - GET /api/calendars/<entity>?start&end     — events in a range
  - calendar.get_events  (service, modern)    — same as REST but service-shaped
  - calendar.create_event / update_event / delete_event

Events have shape:
  {summary, start: {dateTime|date}, end: {dateTime|date}, description?,
   location?, uid?, recurrence_id?, rrule?}
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from cli_anything.homeassistant.core import services as services_core
from cli_anything.homeassistant.core import states as states_core


def list_calendars(client) -> list[dict]:
    """Return every calendar entity (`calendar.*`) HA knows about.

    Each row: {entity_id, name, state, attributes}. `state` is 'on' when an
    event is currently active, 'off' otherwise.
    """
    rows = []
    for s in states_core.list_states(client, domain="calendar"):
        eid = s.get("entity_id", "")
        if not eid.startswith("calendar."):
            continue
        rows.append({
            "entity_id": eid,
            "name": (s.get("attributes") or {}).get("friendly_name"),
            "state": s.get("state"),
            "attributes": s.get("attributes"),
        })
    return rows


def events(client, entity_id: str, *,
            start: Optional[str] = None,
            end: Optional[str] = None,
            duration: Optional[str] = None) -> list[dict]:
    """List events for one calendar entity in a date range.

    Defaults:  start = now, end = +7d. Use ISO-8601 strings throughout.
    Returns a list of event dicts.
    """
    if not entity_id.startswith("calendar."):
        raise ValueError(f"expected calendar.* entity_id, got {entity_id!r}")
    if not start:
        start = datetime.now(timezone.utc).isoformat()
    if not end and not duration:
        end = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    data: dict[str, Any] = {"entity_id": entity_id, "start_date_time": start}
    if end:      data["end_date_time"] = end
    if duration: data["duration"] = duration
    # Modern path: calendar.get_events service with return_response=True
    resp = services_core.call_service(
        client, "calendar", "get_events",
        service_data=data, return_response=True,
    ) or {}
    response = resp.get("service_response") if isinstance(resp, dict) else None
    response = response or resp
    entry = response.get(entity_id) if isinstance(response, dict) else None
    if isinstance(entry, dict):
        evs = entry.get("events")
        return evs if isinstance(evs, list) else []
    # Fallback: REST endpoint
    params = {"start": start}
    if end: params["end"] = end
    return client.get(f"calendars/{entity_id}", params=params) or []


def create_event(client, entity_id: str, *,
                  summary: str,
                  start: str,
                  end: Optional[str] = None,
                  description: Optional[str] = None,
                  location: Optional[str] = None,
                  rrule: Optional[str] = None) -> Any:
    """Add an event to a calendar.

    `start`/`end` are ISO-8601 strings. All-day events use `start_date` /
    `end_date` (YYYY-MM-DD); timed events use `start_date_time` /
    `end_date_time`. We auto-detect by string format.
    """
    if not entity_id.startswith("calendar."):
        raise ValueError(f"expected calendar.* entity_id, got {entity_id!r}")
    if not summary:
        raise ValueError("summary is required")
    if not start:
        raise ValueError("start is required")
    data: dict[str, Any] = {"summary": summary}
    if "T" in start:
        data["start_date_time"] = start
        if end:
            data["end_date_time"] = end
    else:
        data["start_date"] = start
        if end:
            data["end_date"] = end
    if description: data["description"] = description
    if location:    data["location"] = location
    if rrule:       data["rrule"] = rrule
    return services_core.call_service(
        client, "calendar", "create_event",
        service_data=data,
        target={"entity_id": entity_id},
    )


def delete_event(client, entity_id: str, *,
                  uid: Optional[str] = None,
                  recurrence_id: Optional[str] = None,
                  recurrence_range: Optional[str] = None) -> Any:
    """Delete one event (or a recurrence instance) by uid."""
    if not entity_id.startswith("calendar."):
        raise ValueError(f"expected calendar.* entity_id, got {entity_id!r}")
    if not uid:
        raise ValueError("uid is required")
    data: dict[str, Any] = {"uid": uid}
    if recurrence_id:    data["recurrence_id"] = recurrence_id
    if recurrence_range: data["recurrence_range"] = recurrence_range
    return services_core.call_service(
        client, "calendar", "delete_event",
        service_data=data,
        target={"entity_id": entity_id},
    )


def update_event(client, entity_id: str, *,
                  uid: str,
                  summary: Optional[str] = None,
                  start: Optional[str] = None,
                  end: Optional[str] = None,
                  description: Optional[str] = None,
                  location: Optional[str] = None,
                  rrule: Optional[str] = None,
                  recurrence_id: Optional[str] = None,
                  recurrence_range: Optional[str] = None) -> Any:
    """Patch an existing event by uid. Pass only fields to change."""
    if not entity_id.startswith("calendar."):
        raise ValueError(f"expected calendar.* entity_id, got {entity_id!r}")
    if not uid:
        raise ValueError("uid is required")
    data: dict[str, Any] = {"uid": uid}
    if summary is not None:      data["summary"] = summary
    if start is not None:
        if "T" in start: data["start_date_time"] = start
        else:            data["start_date"] = start
    if end is not None:
        if "T" in end: data["end_date_time"] = end
        else:          data["end_date"] = end
    if description is not None:  data["description"] = description
    if location is not None:     data["location"] = location
    if rrule is not None:        data["rrule"] = rrule
    if recurrence_id:    data["recurrence_id"] = recurrence_id
    if recurrence_range: data["recurrence_range"] = recurrence_range
    return services_core.call_service(
        client, "calendar", "update_event",
        service_data=data,
        target={"entity_id": entity_id},
    )
