"""History and Logbook WebSocket API wrappers.

Home Assistant exposes two complementary historical data APIs via WebSocket:

1. **History API** — state change snapshots for entities over a period:
   - ``history_during_period()`` — fetch complete history for a time range
   - ``history_stream()`` — subscribe to live state changes (SUBSCRIBE)

2. **Logbook API** — structured events (state changes, automations, etc.):
   - ``logbook_get_events()`` — fetch logbook events for a time range
   - ``logbook_event_stream()`` — subscribe to live logbook events (SUBSCRIBE)

Public API
----------
* :func:`history_during_period`
* :func:`history_stream`
* :func:`logbook_get_events`
* :func:`logbook_event_stream`
"""

from __future__ import annotations


def _validate_nonempty_str(value: str | None, name: str) -> None:
    """Raise ValueError if value is None or empty whitespace."""
    if not value or not str(value).strip():
        raise ValueError(f"{name} is required and must be non-empty")


def _validate_entity_ids_nonempty(entity_ids: list[str]) -> None:
    """Raise ValueError if entity_ids is empty."""
    if not entity_ids:
        raise ValueError("entity_ids must be a non-empty list")


def _build_payload(
    *,
    start_time: str,
    end_time: str | None = None,
    entity_ids: list[str] | None = None,
    device_ids: list[str] | None = None,
    context_id: str | None = None,
    minimal_response: bool = False,
    no_attributes: bool = False,
    significant_changes_only: bool = True,
) -> dict:
    """Build a payload dict, excluding None/False defaults.

    Omits boolean flags when they match HA's defaults:
    - minimal_response (default False)
    - no_attributes (default False)
    - significant_changes_only (default True)
    """
    payload: dict = {"start_time": start_time}
    if end_time is not None:
        payload["end_time"] = end_time
    if entity_ids is not None and entity_ids:
        payload["entity_ids"] = entity_ids
    if device_ids is not None and device_ids:
        payload["device_ids"] = device_ids
    if context_id is not None:
        payload["context_id"] = context_id
    # Only include boolean flags if they differ from HA defaults
    if minimal_response:
        payload["minimal_response"] = True
    if no_attributes:
        payload["no_attributes"] = True
    if not significant_changes_only:
        payload["significant_changes_only"] = False
    return payload


# ════════════════════════════════════════════════════════════════════════════
# History API
# ════════════════════════════════════════════════════════════════════════════


def history_during_period(
    client,
    *,
    start_time: str,
    end_time: str | None = None,
    entity_ids: list[str],
    minimal_response: bool = False,
    no_attributes: bool = False,
    significant_changes_only: bool = True,
) -> dict:
    """Fetch complete history (state snapshots) for entities during a period.

    Wraps the ``history/history_during_period`` WS command (one-shot request,
    not a subscription).

    Parameters
    ----------
    client:
        Home Assistant client instance exposing ``ws_call``.
    start_time:
        RFC 3339 datetime string (e.g. ``"2024-01-01T00:00:00Z"``).
        Required, non-empty.
    end_time:
        RFC 3339 datetime string, or None (open-ended). When None, omitted
        from the payload.
    entity_ids:
        List of entity IDs to fetch history for. Must be non-empty.
    minimal_response:
        If True, response omits some metadata to reduce payload size.
    no_attributes:
        If True, state dicts exclude the ``attributes`` key.
    significant_changes_only:
        If True (default), returns only "significant" state changes
        (e.g. state transitions, not attribute-only updates).

    Returns
    -------
    dict
        History data keyed by entity_id; each value is a list of state
        change snapshots. Example: ``{"light.kitchen": [...], ...}``

    Raises
    ------
    ValueError
        If ``start_time`` or ``entity_ids`` is empty.
    """
    _validate_nonempty_str(start_time, "start_time")
    _validate_entity_ids_nonempty(entity_ids)

    payload = _build_payload(
        start_time=start_time,
        end_time=end_time,
        entity_ids=entity_ids,
        minimal_response=minimal_response,
        no_attributes=no_attributes,
        significant_changes_only=significant_changes_only,
    )

    return client.ws_call("history/history_during_period", payload)


def history_stream(
    client,
    *,
    entity_ids: list[str],
    start_time: str,
    end_time: str | None = None,
    minimal_response: bool = False,
    no_attributes: bool = False,
    significant_changes_only: bool = True,
) -> dict:
    """Subscribe to live state changes (streaming history).

    Wraps the ``history/stream`` WS SUBSCRIBE command. This is a streaming
    subscription that begins with a backfill from ``start_time`` (or all
    available history) and then delivers live state updates.

    Note: This function wraps the subscription as a one-shot ``ws_call`` so
    it can be recorded in ``ws_calls`` for testing. In production, the client
    would need to support ``ws_subscribe`` for a true event loop.

    Parameters
    ----------
    client:
        Home Assistant client instance.
    entity_ids:
        List of entity IDs to stream. Must be non-empty.
    start_time:
        RFC 3339 datetime string. History before this time may not be
        included in the initial backfill.
    end_time:
        RFC 3339 datetime string, or None (stream indefinitely).
    minimal_response:
        If True, response omits metadata.
    no_attributes:
        If True, state dicts exclude ``attributes``.
    significant_changes_only:
        If True (default), skip attribute-only updates.

    Returns
    -------
    dict
        Stream subscription confirmation (or initial history backfill).
        Production code using ``ws_subscribe`` would handle events via
        the callback, not the return value.

    Raises
    ------
    ValueError
        If ``entity_ids`` or ``start_time`` is empty.
    """
    _validate_entity_ids_nonempty(entity_ids)
    _validate_nonempty_str(start_time, "start_time")

    payload = _build_payload(
        start_time=start_time,
        end_time=end_time,
        entity_ids=entity_ids,
        minimal_response=minimal_response,
        no_attributes=no_attributes,
        significant_changes_only=significant_changes_only,
    )

    return client.ws_call("history/stream", payload)


# ════════════════════════════════════════════════════════════════════════════
# Logbook API
# ════════════════════════════════════════════════════════════════════════════


def logbook_get_events(
    client,
    *,
    start_time: str,
    end_time: str | None = None,
    entity_ids: list[str] | None = None,
    device_ids: list[str] | None = None,
    context_id: str | None = None,
) -> dict:
    """Fetch logbook events (state changes, automations, etc.) for a period.

    Wraps the ``logbook/get_events`` WS command (one-shot request, not
    a subscription).

    Parameters
    ----------
    client:
        Home Assistant client instance.
    start_time:
        RFC 3339 datetime string. Required, non-empty.
    end_time:
        RFC 3339 datetime string, or None. When None, omitted from payload.
    entity_ids:
        Filter by these entity IDs. When None or empty, omitted (all events).
    device_ids:
        Filter by these device IDs. When None or empty, omitted.
    context_id:
        Filter by a specific context (e.g. a single automation trigger).
        When None, omitted.

    Returns
    -------
    dict
        Logbook data, typically ``{"events": [...]}``.

    Raises
    ------
    ValueError
        If ``start_time`` is empty.
    """
    _validate_nonempty_str(start_time, "start_time")

    payload = _build_payload(
        start_time=start_time,
        end_time=end_time,
        entity_ids=entity_ids,
        device_ids=device_ids,
        context_id=context_id,
    )

    return client.ws_call("logbook/get_events", payload)


def logbook_event_stream(
    client,
    *,
    start_time: str,
    end_time: str | None = None,
    entity_ids: list[str] | None = None,
    device_ids: list[str] | None = None,
) -> dict:
    """Subscribe to live logbook events (streaming).

    Wraps the ``logbook/event_stream`` WS SUBSCRIBE command. Like
    ``history_stream``, this is documented as a subscription; this wrapper
    records it as a one-shot ``ws_call`` for testing.

    Parameters
    ----------
    client:
        Home Assistant client instance.
    start_time:
        RFC 3339 datetime string. Required. Backfill before this time may
        not be included.
    end_time:
        RFC 3339 datetime string, or None (stream indefinitely).
    entity_ids:
        Filter by entity IDs. When None or empty, omitted.
    device_ids:
        Filter by device IDs. When None or empty, omitted.

    Returns
    -------
    dict
        Stream subscription confirmation (or initial backfill).

    Raises
    ------
    ValueError
        If ``start_time`` is empty.
    """
    _validate_nonempty_str(start_time, "start_time")

    payload = _build_payload(
        start_time=start_time,
        end_time=end_time,
        entity_ids=entity_ids,
        device_ids=device_ids,
    )

    return client.ws_call("logbook/event_stream", payload)
