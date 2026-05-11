"""Live subscriptions — event bus + state-change watching.

Two flavours:
  - `subscribe_events(event_type=None, duration=None, callback=...)` —
    raw HA event bus tail. event_type=None = ALL events.
  - `watch_state(entity_id, until_state=None, duration=None, callback=...)`
    — convenience: subscribes to `state_changed`, filters to one entity,
    optionally stops as soon as the target state appears.

Both block (or callback-stream) until `duration` elapses or `KeyboardInterrupt`
is raised. Returns the list of records collected during the watch.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional


def subscribe_events(client, *,
                      event_type: Optional[str] = None,
                      duration: Optional[float] = None,
                      limit: Optional[int] = None,
                      callback: Optional[Callable[[dict], None]] = None) -> list[dict]:
    """Tail the HA event bus for `duration` seconds.

    Returns a list of `{event_type, data, time_fired, origin, context}` records.
    """
    collected: list[dict] = []
    stop = threading.Event()
    payload: dict[str, Any] = {}
    if event_type:
        payload["event_type"] = event_type

    def on_msg(event: Any) -> None:
        if not isinstance(event, dict):
            return
        collected.append(event)
        if callback:
            try:
                callback(event)
            except Exception:
                pass
        if limit and len(collected) >= limit:
            stop.set()

    th = threading.Thread(target=client.ws_subscribe, args=(
        "subscribe_events", payload or None, on_msg, stop,
    ), daemon=True)
    th.start()
    try:
        if duration is None:
            th.join()
        else:
            th.join(timeout=duration)
            stop.set()
            th.join(timeout=2.0)
    except KeyboardInterrupt:
        stop.set()
        th.join(timeout=2.0)
    return collected


def watch_state(client, entity_id: str, *,
                 until_state: Optional[str] = None,
                 duration: Optional[float] = None,
                 callback: Optional[Callable[[dict], None]] = None) -> list[dict]:
    """Watch one entity's state changes.

    Returns each `state_changed` event whose `data.entity_id` matches.
    If `until_state` is set, stops as soon as the new state matches.
    """
    if not entity_id:
        raise ValueError("entity_id is required")

    collected: list[dict] = []
    stop = threading.Event()

    def on_msg(event: Any) -> None:
        if not isinstance(event, dict):
            return
        data = event.get("data") or {}
        if data.get("entity_id") != entity_id:
            return
        collected.append(event)
        if callback:
            try:
                callback(event)
            except Exception:
                pass
        if until_state is not None:
            new = (data.get("new_state") or {}).get("state")
            if new == until_state:
                stop.set()

    th = threading.Thread(target=client.ws_subscribe, args=(
        "subscribe_events", {"event_type": "state_changed"}, on_msg, stop,
    ), daemon=True)
    th.start()
    try:
        if duration is None:
            th.join()
        else:
            th.join(timeout=duration)
            stop.set()
            th.join(timeout=2.0)
    except KeyboardInterrupt:
        stop.set()
        th.join(timeout=2.0)
    return collected
