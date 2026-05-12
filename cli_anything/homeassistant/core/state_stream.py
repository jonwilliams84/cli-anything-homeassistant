"""Live WebSocket event subscriptions.

Provides thin wrappers around the Home Assistant WebSocket subscription
commands, enabling streaming state-change events and arbitrary trigger
subscriptions without polling.

WS commands wrapped
-------------------
* ``subscribe_events``   — subscribe to any HA event bus event type
* ``subscribe_trigger``  — subscribe to HA trigger evaluations

Public API
----------
* :func:`subscribe_events`
* :func:`subscribe_state_changed`
* :func:`subscribe_trigger`
* :func:`collect_events`
"""

from __future__ import annotations

import threading
from typing import Callable

from cli_anything.homeassistant.core._ws_subscribe_utils import (
    resolve_stop_event as _resolve_stop_event,
    wrap_with_max_events as _wrap_with_max_events,
    validate_callable as _validate_callable_util,
)


# ────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ────────────────────────────────────────────────────────────────────────────

def _make_stop_event() -> threading.Event:
    return threading.Event()


def _validate_event_type(event_type: str | None) -> None:
    if event_type is not None and not event_type.strip():
        raise ValueError("event_type must be non-empty when supplied")


def _validate_callable(fn: object, name: str = "on_event") -> None:
    if not callable(fn):
        raise ValueError(f"{name} must be callable")


def _validate_count(count: int) -> None:
    if count < 1:
        raise ValueError("count must be >= 1")


def _validate_timeout(timeout_seconds: float) -> None:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be > 0")


# ────────────────────────────────────────────────────────────────────────────
# Public functions
# ────────────────────────────────────────────────────────────────────────────

def subscribe_events(
    client,
    *,
    event_type: str | None = None,
    on_event: Callable,
    stop_event: threading.Event | None = None,
    max_events: int | None = None,
) -> None:
    """Subscribe to Home Assistant events on the WebSocket bus.

    Wraps the ``subscribe_events`` WS command. Blocks until ``stop_event``
    is set (or ``max_events`` have been received when only that is supplied).

    Parameters
    ----------
    client:
        Home Assistant client instance exposing ``ws_subscribe``.
    event_type:
        Optional HA event type string (e.g. ``"state_changed"``). When
        omitted, all events are received.
    on_event:
        Callable invoked with each event dict received from HA.
    stop_event:
        :class:`threading.Event` whose set-state terminates the loop. At
        least one of ``stop_event`` or ``max_events`` must be supplied.
    max_events:
        Stop automatically after this many events. Ignored when
        ``stop_event`` is also supplied (the caller controls lifetime).

    Raises
    ------
    ValueError
        If neither ``stop_event`` nor ``max_events`` is provided, or if
        ``event_type`` is an empty string, or if ``on_event`` is not callable.
    """
    _validate_callable(on_event, "on_event")
    _validate_event_type(event_type)
    stop, owns_stop = _resolve_stop_event(stop_event, max_events)

    payload: dict = {}
    if event_type is not None:
        payload["event_type"] = event_type

    wrapper = _wrap_with_max_events(on_event, stop, owns_stop, max_events)
    client.ws_subscribe("subscribe_events", payload or None, wrapper, stop)


def subscribe_state_changed(
    client,
    *,
    entity_ids: list[str] | None = None,
    on_change: Callable,
    stop_event: threading.Event | None = None,
    max_events: int | None = None,
) -> None:
    """Subscribe to ``state_changed`` events, optionally filtered by entity.

    Convenience wrapper around :func:`subscribe_events` that fixes
    ``event_type="state_changed"`` and optionally filters by entity ID.

    Parameters
    ----------
    client:
        Home Assistant client.
    entity_ids:
        When given, only events whose ``data.entity_id`` is in this list
        are forwarded to ``on_change``.
    on_change:
        Callable invoked with each (optionally filtered) event dict.
    stop_event:
        See :func:`subscribe_events`.
    max_events:
        See :func:`subscribe_events`. Counts only *passed-through* events
        (after entity_id filtering).

    Raises
    ------
    ValueError
        See :func:`subscribe_events`.
    """
    _validate_callable(on_change, "on_change")
    stop, owns_stop = _resolve_stop_event(stop_event, max_events)

    id_set = set(entity_ids) if entity_ids else None
    # Build a counting wrapper for the entity-filtered callback.
    # We can't use wrap_with_max_events directly because entity filtering
    # means the count must only increment for events that pass the filter.
    count_box = [0]

    def filtered_handler(event: object) -> None:
        if id_set is not None:
            data = event.get("data", {}) if isinstance(event, dict) else {}
            if data.get("entity_id") not in id_set:
                return
        on_change(event)
        if owns_stop and max_events is not None:
            count_box[0] += 1
            if count_box[0] >= max_events:
                stop.set()

    payload: dict = {"event_type": "state_changed"}
    client.ws_subscribe("subscribe_events", payload, filtered_handler, stop)


def subscribe_trigger(
    client,
    *,
    trigger: dict,
    on_trigger: Callable,
    variables: dict | None = None,
    stop_event: threading.Event | None = None,
    max_events: int | None = None,
) -> None:
    """Subscribe to Home Assistant trigger evaluations.

    Uses the ``subscribe_trigger`` WS command which fires whenever the
    given trigger platform fires (e.g. a time pattern, template, or state
    trigger).

    Parameters
    ----------
    client:
        Home Assistant client.
    trigger:
        Trigger descriptor dict (e.g.
        ``{"platform": "state", "entity_id": "binary_sensor.motion"}``).
    on_trigger:
        Callable invoked with each trigger event dict.
    variables:
        Optional variables dict forwarded to HA alongside the trigger.
    stop_event:
        See :func:`subscribe_events`.
    max_events:
        See :func:`subscribe_events`.

    Raises
    ------
    ValueError
        If ``trigger`` is not a non-empty dict, or neither ``stop_event``
        nor ``max_events`` is provided, or if ``on_trigger`` is not callable.
    """
    _validate_callable(on_trigger, "on_trigger")
    if not isinstance(trigger, dict) or not trigger:
        raise ValueError("trigger must be a non-empty dict")
    stop, owns_stop = _resolve_stop_event(stop_event, max_events)

    payload: dict = {"trigger": trigger}
    if variables is not None:
        payload["variables"] = variables

    wrapper = _wrap_with_max_events(on_trigger, stop, owns_stop, max_events)
    client.ws_subscribe("subscribe_trigger", payload, wrapper, stop)


def collect_events(
    client,
    *,
    event_type: str | None = None,
    count: int = 1,
    timeout_seconds: float = 10.0,
) -> list:
    """Synchronously collect ``count`` events and return them as a list.

    Opens a subscription in a background thread, accumulates events until
    ``count`` is reached, then stops and returns. Raises :exc:`TimeoutError`
    if fewer than ``count`` events arrive within ``timeout_seconds``.

    Parameters
    ----------
    client:
        Home Assistant client.
    event_type:
        Optional HA event type filter (see :func:`subscribe_events`).
    count:
        Number of events to collect. Must be >= 1.
    timeout_seconds:
        Maximum seconds to wait. Must be > 0.

    Returns
    -------
    list
        List of event dicts, length == ``count``.

    Raises
    ------
    TimeoutError
        If ``count`` events are not received within ``timeout_seconds``.
    ValueError
        If ``count < 1`` or ``timeout_seconds <= 0``.
    """
    _validate_count(count)
    _validate_timeout(timeout_seconds)
    _validate_event_type(event_type)

    collected: list = []
    stop = _make_stop_event()

    def on_event(event: object) -> None:
        collected.append(event)
        if len(collected) >= count:
            stop.set()

    def _run() -> None:
        subscribe_events(
            client,
            event_type=event_type,
            on_event=on_event,
            stop_event=stop,
        )

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)

    if len(collected) < count:
        stop.set()
        raise TimeoutError(
            f"collect_events: expected {count} event(s) but only received "
            f"{len(collected)} within {timeout_seconds}s"
        )
    return collected
