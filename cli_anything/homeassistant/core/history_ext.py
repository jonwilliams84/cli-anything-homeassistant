"""Long-history fallback — recorder states → long-term statistics.

Home Assistant retains data in two streams with very different timeframes:

* **Recorder states** (``/api/history/period``) — every state change, kept
  for ``purge_keep_days`` (default 10, often raised to 30 by users).
  Granular but short.
* **Long-term statistics** (``recorder/statistics_during_period``) —
  5-minute / hourly / daily aggregates (mean, min, max, sum), kept
  indefinitely. Useful for trends going back months/years but coarser.

For numeric sensors, you usually want "give me the history of this entity
back to date X, regardless of which storage layer it's in". This module
provides:

* :func:`history_with_stats_fallback` — fetches recorder states for the
  window, detects the recorder's start cutoff, and back-fills the older
  portion from statistics. Returns a single chronological list of
  ``{when, value, source}`` rows so callers don't need to know which
  storage layer each came from.

* :func:`statistics_to_samples` — converts the recorder/statistics
  return shape (nested dict, epoch-ms timestamps, separate mean/min/max
  fields) into a flat sample list compatible with the history shape.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Literal

from . import history as _history
from . import statistics as _statistics

StatField = Literal["mean", "min", "max", "state", "sum", "change"]
Period = Literal["5minute", "hour", "day", "week", "month"]


def _epoch_ms_to_dt(ms: int | float) -> datetime:
    return datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc)


def _parse_dt(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, (int, float)):
        try:
            return _epoch_ms_to_dt(raw)
        except (OSError, OverflowError, ValueError):
            return None
    if isinstance(raw, str) and raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                return datetime.fromisoformat(raw[:19]).replace(tzinfo=timezone.utc)
            except ValueError:
                return None
    return None


def statistics_to_samples(
    stats_response: dict[str, list[dict]],
    *,
    statistic_id: str,
    value_field: StatField = "mean",
) -> list[dict[str, Any]]:
    """Convert ``recorder/statistics_during_period`` output to flat samples.

    Input shape (HA returns):
        {"sensor.foo": [{"start": <epoch_ms>, "end": <epoch_ms>,
                          "mean": float, "min": float, "max": float, ...}, ...]}

    Output:
        [{"when": <datetime>, "value": float, "source": "statistics"}, ...]

    ``value_field`` selects which bucket field to use as the canonical value.
    Defaults to ``mean``; pass ``"max"`` for "the highest the sensor reached
    in that bucket" (useful for detecting transient spikes that the mean
    smooths over).
    """
    if not statistic_id:
        raise ValueError("statistic_id is required")
    if value_field not in ("mean", "min", "max", "state", "sum", "change"):
        raise ValueError(f"invalid value_field: {value_field!r}")
    buckets = (stats_response or {}).get(statistic_id, [])
    out: list[dict[str, Any]] = []
    for b in buckets:
        ts = _parse_dt(b.get("start"))
        v = b.get(value_field)
        if ts is None or v is None:
            continue
        try:
            v_f = float(v)
        except (TypeError, ValueError):
            continue
        out.append({"when": ts, "value": v_f, "source": "statistics"})
    return out


def _states_to_samples(
    states_response: list[list[dict]],
    *,
    entity_id: str,
) -> list[dict[str, Any]]:
    """Convert ``/api/history/period`` output to flat samples.

    HA returns ``[[state, state, ...]]`` — one inner list per filtered
    entity. We flatten and coerce ``state`` to a float, skipping anything
    non-numeric (``unknown`` / ``unavailable`` / strings).
    """
    if not states_response:
        return []
    inner = states_response[0] if states_response else []
    out: list[dict[str, Any]] = []
    for p in inner:
        ts = _parse_dt(p.get("last_changed") or p.get("last_updated"))
        if ts is None:
            continue
        raw = p.get("state")
        if raw in (None, "unknown", "unavailable"):
            continue
        try:
            v = float(raw)
        except (TypeError, ValueError):
            continue
        out.append({"when": ts, "value": v, "source": "recorder"})
    return out


def history_with_stats_fallback(
    client,
    *,
    entity_id: str,
    start: datetime,
    end: datetime | None = None,
    period: Period = "hour",
    value_field: StatField = "mean",
) -> list[dict[str, Any]]:
    """Return one chronological sample list covering ``start`` → ``end``.

    Uses the recorder for whatever portion of the window it still holds
    (typically the most recent ``purge_keep_days``); back-fills the older
    portion from long-term statistics at the chosen ``period`` resolution.

    Sample shape: ``{when: datetime, value: float, source: "recorder"|"statistics"}``.

    The recorder vs statistics handoff happens at the recorder's earliest
    sample — anything before it comes from statistics. The two halves are
    merged and sorted chronologically; there's no overlap by construction
    (statistics are filtered to ``end_time`` = recorder's first sample).

    Use :func:`statistics_to_samples` directly if you ONLY want stats.
    Use :func:`cli_anything.homeassistant.core.history.history` if you
    ONLY want raw states (no fallback).
    """
    if not entity_id:
        raise ValueError("entity_id is required")
    if end is None:
        end = datetime.now(timezone.utc)
    if start >= end:
        raise ValueError("start must be before end")
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    # 1. Try recorder first — it gives the precise values
    states_resp = _history.history(
        client, entity_ids=[entity_id], start=start, end=end,
    )
    recorder_samples = _states_to_samples(states_resp, entity_id=entity_id)

    # 2. Determine the recorder's earliest sample (= statistics ceiling)
    recorder_earliest: datetime | None = None
    if recorder_samples:
        recorder_earliest = min(s["when"] for s in recorder_samples)

    # 3. If the recorder window covers our `start`, we're done.
    #    Otherwise back-fill statistics from `start` to recorder_earliest
    #    (or to `end` if recorder returned nothing).
    stats_samples: list[dict[str, Any]] = []
    stats_end = recorder_earliest or end
    needs_stats = (recorder_earliest is None) or (recorder_earliest > start + timedelta(minutes=5))
    if needs_stats:
        stats_resp = _statistics.statistics_during_period(
            client,
            statistic_ids=[entity_id],
            start_time=start.isoformat(),
            end_time=stats_end.isoformat(),
            period=period,
            types=[value_field],
        )
        stats_samples = statistics_to_samples(
            stats_resp, statistic_id=entity_id, value_field=value_field,
        )

    merged = stats_samples + recorder_samples
    merged.sort(key=lambda s: s["when"])
    return merged


def recorder_retention_estimate(
    client,
    *,
    entity_id: str,
    probe_days: int = 60,
) -> dict[str, Any]:
    """Estimate how far back the recorder retains states for ``entity_id``.

    Issues a single history-period query covering the last ``probe_days``
    days; returns ``{first_sample, sample_count, retention_days, probe_days}``.
    Useful for diagnostics — surfaces whether a ``purge_keep_days`` config
    mismatches reality.
    """
    if not entity_id:
        raise ValueError("entity_id is required")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=max(probe_days, 1))
    states_resp = _history.history(client, entity_ids=[entity_id], start=start, end=end)
    samples = _states_to_samples(states_resp, entity_id=entity_id)
    if not samples:
        return {"first_sample": None, "sample_count": 0,
                "retention_days": 0.0, "probe_days": probe_days}
    first = min(s["when"] for s in samples)
    age_days = (end - first).total_seconds() / 86400
    return {
        "first_sample": first.isoformat(),
        "sample_count": len(samples),
        "retention_days": round(age_days, 2),
        "probe_days": probe_days,
    }
