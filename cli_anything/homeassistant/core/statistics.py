"""Long-term statistics — extends the basic recorder helpers.

HA's recorder keeps two streams of data:
  - states (granular, retained `purge_keep_days`)
  - statistics (compacted, retained much longer)

This module exposes:
  - list / metadata lookups
  - statistics_during_period (the chart-data endpoint)
  - update_metadata (fix unit changes after the fact)

(`info()` is also exported as `statistics_info` for unambiguous `from X import` usage.)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

VALID_PERIODS = ("5minute", "hour", "day", "week", "month")
VALID_TYPES = ("change", "last_reset", "max", "mean", "min", "state", "sum")


def list_statistic_ids(client, *,
                        statistic_type: Optional[str] = None,
                        ) -> list[dict]:
    """List every statistic the recorder has metadata for.

    Each row carries `statistic_id`, `source`, `unit_of_measurement`,
    `has_mean`, `has_sum`, `name?`, `statistics_unit_of_measurement`.
    `statistic_type` (when set) filters to ids that have that field
    (e.g. `sum` for cumulative meters).
    """
    payload: dict[str, Any] = {}
    if statistic_type:
        if statistic_type not in ("mean", "sum"):
            raise ValueError("statistic_type must be 'mean' or 'sum'")
        payload["statistic_type"] = statistic_type
    data = client.ws_call("recorder/list_statistic_ids", payload or None)
    return list(data) if isinstance(data, list) else []


def get_metadata(client, statistic_ids: Optional[list[str]] = None) -> list[dict]:
    """Read recorder metadata for a subset of statistic ids (or all)."""
    payload: dict[str, Any] = {}
    if statistic_ids:
        payload["statistic_ids"] = list(statistic_ids)
    data = client.ws_call("recorder/get_statistics_metadata", payload or None)
    return list(data) if isinstance(data, list) else []


def statistics_during_period(
        client, *,
        statistic_ids: list[str],
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        period: str = "hour",
        types: Optional[Iterable[str]] = None,
        units: Optional[dict[str, str]] = None,
) -> dict:
    """Fetch chart data for one or more statistic ids.

    Time arguments accept ISO-8601 strings; if `start_time` is None we
    default to 24h ago (UTC). `types` is the subset of value kinds to
    pull (`change`, `mean`, `min`, `max`, `state`, `sum`, `last_reset`).
    `units` is `{"sensor.foo": "kWh"}` for explicit unit conversion.
    """
    if not statistic_ids:
        raise ValueError("statistic_ids must not be empty")
    if period not in VALID_PERIODS:
        raise ValueError(f"period must be one of {VALID_PERIODS}")
    if not start_time:
        start_time = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    payload: dict[str, Any] = {
        "statistic_ids": list(statistic_ids),
        "start_time": start_time,
        "period": period,
    }
    if end_time:        payload["end_time"] = end_time
    if types:           payload["types"] = list(types)
    if units:           payload["units"] = units
    return client.ws_call("recorder/statistics_during_period", payload) or {}


def update_metadata(client, *, statistic_id: str,
                     unit_of_measurement: Optional[str] = None) -> Any:
    """Mutate recorder metadata after a sensor's unit changes upstream.

    HA blocks new statistic rows when the incoming unit doesn't match the
    one already recorded. This call lets you tell the recorder "the new
    unit is correct; treat older rows as the same series".
    """
    if not statistic_id:
        raise ValueError("statistic_id is required")
    payload: dict[str, Any] = {"statistic_id": statistic_id}
    if unit_of_measurement is not None:
        payload["unit_of_measurement"] = unit_of_measurement
    return client.ws_call("recorder/update_statistics_metadata", payload)


def clear(client, statistic_ids: list[str]) -> Any:
    """Clear statistics for the listed ids (destructive)."""
    if not statistic_ids:
        raise ValueError("statistic_ids must not be empty")
    return client.ws_call("recorder/clear_statistics",
                            {"statistic_ids": list(statistic_ids)})


def info(client) -> dict:
    """Overall recorder info: backlog, migration state, recording flag, etc."""
    return client.ws_call("recorder/info") or {}


statistics_info = info
