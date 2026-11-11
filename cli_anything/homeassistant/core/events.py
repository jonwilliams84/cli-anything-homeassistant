"""Event listeners + firing + live streaming (/api/events, /api/stream)."""

from __future__ import annotations

import time
from typing import Callable


def list_listeners(client) -> list[dict]:
    """Return the event listener counts as reported by /api/events."""
    data = client.get("events")
    return list(data) if isinstance(data, list) else []


def fire_event(client, event_type: str, event_data: dict | None = None) -> dict:
    """Fire an event on the Home Assistant event bus."""
    if not event_type:
        raise ValueError("event_type cannot be empty")
    return client.post(f"events/{event_type}", event_data or {})


def _validate_stream_types(types: list[str] | None) -> None:
    if types is None:
        return
    for event_type in types:
        if not isinstance(event_type, str) or not event_type.strip():
            raise ValueError("event types must be non-empty strings")
        if "," in event_type:
            # The types ride to HA as ONE comma-joined `restrict` query
            # parameter, so a comma inside a type would silently widen the
            # filter into "a list". Refuse it instead.
            raise ValueError(
                f"event type {event_type!r} must not contain a comma — "
                "restrict is a comma-joined list on the wire"
            )


def stream_events(
    client,
    *,
    types: list[str] | None = None,
    duration_seconds: float = 10.0,
    max_events: int | None = None,
    on_event: Callable | None = None,
) -> dict:
    """Follow the REST event stream (``GET /api/stream``, SSE) for a while.

    The REST twin of the WS ``subscribe_events`` surface: the same event
    dicts (``event_type`` / ``data`` / ``origin`` / ``time_fired`` /
    ``context``) over plain HTTP, for the cases where only HTTP can get
    through — the websocket is proxied away, or a shell script wants a
    one-liner. Streaming is server-side filtered when ``types`` is given
    (HA's `restrict` query parameter; HA already folds the
    ``homeassistant_stop`` event into the filter itself, so a stop is never
    lost to it). The stream ends on whichever comes first:

    * ``max_events`` events have been fetched,
    * the NEXT event arrives after ``duration_seconds`` elapsed, or
    * ``duration_seconds`` pass with NOTHING arriving (the SSE read
      times out and the silence is treated as an end, not an error —
      HA pings an idle stream only every 50 s, so silence is the
      normal state of an undisturbed bus).

    ``on_event(event)`` fires for each event as it lands (before any
    return), so a caller can print or process while streaming.
    """
    _validate_stream_types(types)
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be > 0")
    if max_events is not None and max_events < 1:
        raise ValueError("max_events must be >= 1 (None means unlimited)")
    if on_event is not None and not callable(on_event):
        raise ValueError("on_event must be callable")

    params = {"restrict": ",".join(types)} if types else None
    event_stream = client.event_stream("stream", params=params, read_timeout=duration_seconds)

    collected: list[dict] = []
    deadline = time.monotonic() + duration_seconds
    for event in event_stream:
        collected.append(event)
        if on_event is not None:
            on_event(event)
        if max_events is not None and len(collected) >= max_events:
            return _summary(collected, types, "max_events")
        if time.monotonic() >= deadline:
            return _summary(collected, types, "duration")

    # The connection ended on its own (remote close, read timeout on a
    # silent bus) — a graceful end, not an error.
    return _summary(collected, types, "ended")


def _summary(events: list[dict], types: list[str] | None, stopped_reason: str) -> dict:
    return {
        "count": len(events),
        "restrict": list(types) if types else None,
        "stopped_reason": stopped_reason,
        "events": events,
    }
