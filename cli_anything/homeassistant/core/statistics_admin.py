"""Statistics admin — recorder management via WebSocket commands.

Wraps the six recorder admin WS commands that manage the long-term
statistics database:  adjust sums, change units, validate, update issue
metadata, update stored metadata, and bulk-import external statistics.

All functions raise ``ValueError`` for obviously wrong inputs so callers
get a clear message before any network call is made.
"""

from __future__ import annotations

from typing import Any


def adjust_sum_statistics(
    client,
    *,
    statistic_id: str,
    start_time: str,
    adjustment: float,
    adjustment_unit_of_measurement: str | None = None,
) -> Any:
    """Adjust the sum value of a statistic series from a given point in time.

    WS message type: ``recorder/adjust_sum_statistics``

    ``statistic_id``  — the recorder statistic id (e.g. ``sensor.energy_meter``).
    ``start_time``    — ISO-8601 UTC string; the adjustment applies from this
                        point forward.
    ``adjustment``    — signed float to add to the stored sum.
    ``adjustment_unit_of_measurement`` — the unit the adjustment is expressed
                        in; may be ``None`` to use the stored unit.
    """
    if not statistic_id:
        raise ValueError("statistic_id must not be empty")
    if not start_time:
        raise ValueError("start_time must not be empty")
    payload: dict[str, Any] = {
        "statistic_id": statistic_id,
        "start_time": start_time,
        "adjustment": float(adjustment),
        "adjustment_unit_of_measurement": adjustment_unit_of_measurement,
    }
    return client.ws_call("recorder/adjust_sum_statistics", payload)


def change_statistics_unit(
    client,
    *,
    statistic_id: str,
    new_unit_of_measurement: str,
    old_unit_of_measurement: str,
) -> Any:
    """Convert all stored statistics for a series to a new unit.

    WS message type: ``recorder/change_statistics_unit``

    HA converts every historical row from ``old_unit_of_measurement`` to
    ``new_unit_of_measurement`` and updates the stored metadata.  Both
    units must be non-empty strings (they cannot be ``None`` for this
    command; use ``update_statistics_metadata`` to clear a unit instead).
    """
    if not statistic_id:
        raise ValueError("statistic_id must not be empty")
    if not new_unit_of_measurement:
        raise ValueError("new_unit_of_measurement must not be empty")
    if not old_unit_of_measurement:
        raise ValueError("old_unit_of_measurement must not be empty")
    payload: dict[str, Any] = {
        "statistic_id": statistic_id,
        "new_unit_of_measurement": new_unit_of_measurement,
        "old_unit_of_measurement": old_unit_of_measurement,
    }
    return client.ws_call("recorder/change_statistics_unit", payload)


def validate_statistics(client) -> dict:
    """Run recorder validation and return a mapping of statistic_id → issues.

    WS message type: ``recorder/validate_statistics``

    Returns a dict where each key is a ``statistic_id`` and the value is a
    list of issue dicts as reported by the recorder (e.g. wrong unit,
    unsupported state class, entity missing, etc.).  An empty dict means
    no issues were found.
    """
    result = client.ws_call("recorder/validate_statistics", None)
    if isinstance(result, dict):
        return result
    return {}


def update_statistics_issues(
    client,
    *,
    type: str,
    statistic_id: str,
) -> Any:
    """Acknowledge or clear a specific statistics issue for a statistic id.

    WS message type: ``recorder/update_statistics_issues``

    ``type``         — the issue type string, e.g. ``"unsupported_state_class"``
                       or ``"units_changed"``.
    ``statistic_id`` — the recorder statistic id the issue belongs to.
    """
    if not statistic_id:
        raise ValueError("statistic_id must not be empty")
    if not type:
        raise ValueError("type must not be empty")
    payload: dict[str, Any] = {
        "statistic_id": statistic_id,
        "type": type,
    }
    return client.ws_call("recorder/update_statistics_issues", payload)


def update_statistics_metadata(
    client,
    *,
    statistic_id: str,
    unit_of_measurement: str | None,
) -> Any:
    """Update the stored unit of measurement for a statistic id.

    WS message type: ``recorder/update_statistics_metadata``

    Pass ``unit_of_measurement=None`` to clear the stored unit.  This is
    useful after a sensor's device class changes and historical rows should
    be treated as dimensionless.

    Only the normalised unit field is writable via this command; use
    ``change_statistics_unit`` to convert existing values between units.
    """
    if not statistic_id:
        raise ValueError("statistic_id must not be empty")
    payload: dict[str, Any] = {
        "statistic_id": statistic_id,
        "unit_of_measurement": unit_of_measurement,
    }
    return client.ws_call("recorder/update_statistics_metadata", payload)


def import_statistics(
    client,
    *,
    metadata: dict,
    stats: list[dict],
) -> Any:
    """Import external or internal statistics into the recorder database.

    WS message type: ``recorder/import_statistics``

    ``metadata`` must contain:
      - ``statistic_id``       — the recorder id (``<domain>:<object>`` for
                                 external, ``sensor.<name>`` for internal).
      - ``source``             — the integration that owns these statistics.
      - ``name``               — human-readable name (may be ``None``).
      - ``unit_of_measurement``— physical unit (may be ``None``).
      - ``has_mean``           — bool; whether rows carry a mean value.
      - ``has_sum``            — bool; whether rows carry a cumulative sum.

    Each entry in ``stats`` must have a ``start`` key (ISO-8601 string) and
    may carry any subset of: ``mean``, ``min``, ``max``, ``last_reset``,
    ``state``, ``sum``.

    ``stats`` must be non-empty.
    """
    if not metadata.get("statistic_id"):
        raise ValueError("metadata['statistic_id'] must not be empty")
    if not stats:
        raise ValueError("stats must be a non-empty list")
    payload: dict[str, Any] = {
        "metadata": metadata,
        "stats": stats,
    }
    return client.ws_call("recorder/import_statistics", payload)
