"""Hardware information and system-status subscription.

Wraps the Home Assistant ``hardware`` WebSocket API, giving callers a
thin Python layer over two WS command types:

* ``hardware/info``                  — detected hardware inventory
* ``hardware/subscribe_system_status`` — live CPU/memory telemetry stream

WS commands wrapped
-------------------
* ``hardware/info``
* ``hardware/subscribe_system_status``

Public API
----------
* :func:`info`
* :func:`board_info`
* :func:`cpu_info`
* :func:`subscribe_system_status`
"""

from __future__ import annotations

import threading
from typing import Callable


# ────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ────────────────────────────────────────────────────────────────────────────

def _validate_callable(fn: object, name: str = "on_status") -> None:
    if not callable(fn):
        raise ValueError(f"{name} must be callable")


def _validate_max_events(max_events: int | None) -> None:
    if max_events is not None and max_events < 1:
        raise ValueError("max_events must be > 0 when supplied")


def _resolve_stop_event(
    stop_event: threading.Event | None,
    max_events: int | None,
) -> tuple[threading.Event, bool]:
    """Return (stop_event, caller_owns_it).

    *caller_owns_it* is True when we created the event internally so that
    the subscription loop should set it after max_events have arrived.
    """
    if stop_event is None and max_events is None:
        raise ValueError("must supply stop_event or max_events (or both)")
    if stop_event is None:
        return threading.Event(), True
    return stop_event, False


# ────────────────────────────────────────────────────────────────────────────
# Public functions
# ────────────────────────────────────────────────────────────────────────────

def info(client) -> dict:
    """Return the full hardware info dict from Home Assistant.

    Sends the ``hardware/info`` WS command and returns the result, which
    has the shape ``{"hardware": [...]}``.

    Parameters
    ----------
    client:
        Home Assistant client instance exposing ``ws_call``.

    Returns
    -------
    dict
        Raw HA result, typically ``{"hardware": [<hw-record>, ...]}``.
    """
    return client.ws_call("hardware/info", {})


def board_info(client) -> list[dict]:
    """Return only the board-level hardware records.

    Convenience wrapper around :func:`info` that extracts the ``hardware``
    list and filters to entries whose ``board`` key is present (i.e.
    board-specific hardware descriptors).

    Parameters
    ----------
    client:
        Home Assistant client instance.

    Returns
    -------
    list[dict]
        Hardware records that contain a ``"board"`` key.
    """
    result = info(client)
    hardware: list[dict] = result.get("hardware", []) if isinstance(result, dict) else []
    return [hw for hw in hardware if "board" in hw]


def cpu_info(client) -> list[dict]:
    """Return only the CPU-related hardware records.

    Convenience wrapper around :func:`info` that extracts entries whose
    ``"cpu_info"`` key is present in the hardware record.

    Parameters
    ----------
    client:
        Home Assistant client instance.

    Returns
    -------
    list[dict]
        Hardware records that contain a ``"cpu_info"`` key.
    """
    result = info(client)
    hardware: list[dict] = result.get("hardware", []) if isinstance(result, dict) else []
    return [hw for hw in hardware if "cpu_info" in hw]


def subscribe_system_status(
    client,
    *,
    on_status: Callable,
    stop_event: threading.Event | None = None,
    max_events: int | None = None,
) -> None:
    """Subscribe to live CPU/memory system-status updates from Home Assistant.

    Wraps the ``hardware/subscribe_system_status`` WS subscription command.
    Blocks until ``stop_event`` is set or ``max_events`` have been received.

    Parameters
    ----------
    client:
        Home Assistant client instance exposing ``ws_subscribe``.
    on_status:
        Callable invoked with each status event dict received from HA.
        Events typically contain ``cpu_percent``, ``memory_used_percent``,
        ``memory_used_mb``, ``memory_free_mb``, and ``timestamp``.
    stop_event:
        :class:`threading.Event` whose set-state terminates the loop.
        At least one of ``stop_event`` or ``max_events`` must be supplied.
    max_events:
        Stop automatically after this many events. Ignored when
        ``stop_event`` is also supplied (the caller controls lifetime).

    Raises
    ------
    ValueError
        If neither ``stop_event`` nor ``max_events`` is provided, if
        ``max_events`` is not > 0, or if ``on_status`` is not callable.
    """
    _validate_callable(on_status, "on_status")
    _validate_max_events(max_events)
    stop, owns_stop = _resolve_stop_event(stop_event, max_events)

    count_box = [0]

    def wrapper(event: object) -> None:
        on_status(event)
        if owns_stop and max_events is not None:
            count_box[0] += 1
            if count_box[0] >= max_events:
                stop.set()

    client.ws_subscribe("hardware/subscribe_system_status", {}, on_message=wrapper, stop_event=stop)
