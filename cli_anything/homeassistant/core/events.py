"""Event listeners + firing events (/api/events)."""

from __future__ import annotations


def list_listeners(client) -> list[dict]:
    """Return the event listener counts as reported by /api/events."""
    data = client.get("events")
    return list(data) if isinstance(data, list) else []


def fire_event(client, event_type: str, event_data: dict | None = None) -> dict:
    """Fire an event on the Home Assistant event bus."""
    if not event_type:
        raise ValueError("event_type cannot be empty")
    return client.post(f"events/{event_type}", event_data or {})
