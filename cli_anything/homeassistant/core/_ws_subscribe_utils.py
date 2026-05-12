"""Shared utilities for WebSocket subscribe wrappers.

Extracted from state_stream, singletons, and hardware_info to eliminate
duplicate _resolve_stop_event and count-box closure patterns.

Public API
----------
* :func:`resolve_stop_event`
* :func:`wrap_with_max_events`
* :func:`validate_callable`
* :func:`validate_count_or_stop`
"""

from __future__ import annotations

import threading
from typing import Callable


def resolve_stop_event(
    stop_event: threading.Event | None,
    max_events: int | None,
) -> tuple[threading.Event, bool]:
    """Return ``(stop_event, caller_owns_it)``.

    *caller_owns_it* is ``True`` when this function created the event
    internally, meaning the subscription loop should set it after
    ``max_events`` have arrived.

    Raises
    ------
    ValueError
        If both ``stop_event`` and ``max_events`` are ``None``.
    """
    if stop_event is None and max_events is None:
        raise ValueError("must supply stop_event or max_events")
    if stop_event is None:
        return threading.Event(), True
    return stop_event, False


def wrap_with_max_events(
    callback: Callable,
    stop_event: threading.Event,
    owns_stop: bool,
    max_events: int | None,
) -> Callable:
    """Return a wrapped callback that stops after *max_events* calls.

    When *owns_stop* is ``True`` and *max_events* is not ``None``, the
    wrapper increments an internal counter on each invocation and sets
    *stop_event* once the counter reaches *max_events*.

    When *owns_stop* is ``False`` (caller supplied *stop_event*), the
    wrapper calls *callback* unconditionally — lifetime is entirely
    controlled by the caller.

    Parameters
    ----------
    callback:
        The original event-handler callable.
    stop_event:
        The :class:`threading.Event` that terminates the subscription loop.
    owns_stop:
        ``True`` iff this module created *stop_event* (returned by
        :func:`resolve_stop_event` with ``owns=True``).
    max_events:
        Maximum number of events before auto-stop.  ``None`` means no limit.

    Returns
    -------
    Callable
        Wrapped version of *callback*.
    """
    count_box = [0]

    def wrapper(event: object) -> None:
        callback(event)
        if owns_stop and max_events is not None:
            count_box[0] += 1
            if count_box[0] >= max_events:
                stop_event.set()

    return wrapper


def validate_callable(fn: object, name: str = "callback") -> None:
    """Raise :exc:`ValueError` if *fn* is not callable."""
    if not callable(fn):
        raise ValueError(f"{name} must be callable")


def validate_count_or_stop(
    stop_event: threading.Event | None,
    max_events: int | None,
) -> None:
    """Raise :exc:`ValueError` if both *stop_event* and *max_events* are ``None``.

    Convenience alias for the validation step of :func:`resolve_stop_event`
    when you want to validate before constructing.
    """
    if stop_event is None and max_events is None:
        raise ValueError("must supply stop_event or max_events")
