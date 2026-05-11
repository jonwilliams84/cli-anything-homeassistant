"""Recorder introspection — find entities with no recorded history,
audit excluded entities, etc.

Use case: an apex/mini-graph card stuck on "Loading…" usually means the
underlying sensor isn't being recorded. ``recorder_stats(client, eid)``
fetches a 24h sample and tells you whether the entity is producing
historic data.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def entity_stats(client, entity_id: str, *, hours: float = 24) -> dict:
    """Return a small fact-sheet about a single entity's recorder state.

    Output:
        {
          "entity_id": ...,
          "live_state": ...,
          "live_last_changed": "...",
          "history_points_24h": N,
          "history_first": "...",
          "history_last": "...",
          "history_span_hours": float,
          "is_recorded": bool,
        }
    """
    if not entity_id:
        raise ValueError("entity_id is required")

    # Live state
    try:
        live = client.get(f"states/{entity_id}")
    except Exception:
        live = None

    # History — request a small window. HA's API returns at most ~24h
    # of points per call regardless of `end_time`, so we ask for the
    # most recent `hours`.
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(hours=hours)
    raw = client.get(
        f"history/period/{_iso(start)}",
        params={
            "filter_entity_id": entity_id,
            "end_time": _iso(end),
            "minimal_response": "true",
        },
    )
    points: list = []
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        points = raw[0]

    first_iso = points[0].get("last_changed") if points else None
    last_iso  = points[-1].get("last_changed") if points else None
    span_h: float | None = None
    if first_iso and last_iso:
        try:
            t0 = datetime.fromisoformat(first_iso.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
            span_h = (t1 - t0).total_seconds() / 3600.0
        except Exception:
            span_h = None

    return {
        "entity_id": entity_id,
        "live_state": live.get("state") if isinstance(live, dict) else None,
        "live_last_changed":
            live.get("last_changed") if isinstance(live, dict) else None,
        "history_points_24h": len(points),
        "history_first": first_iso,
        "history_last":  last_iso,
        "history_span_hours": span_h,
        "is_recorded": len(points) > 0,
    }


def batch_stats(client, entity_ids: Iterable[str], *,
                  hours: float = 24) -> list[dict]:
    """Run `entity_stats` over a list and return the results."""
    return [entity_stats(client, e, hours=hours) for e in entity_ids]


def find_unrecorded(client, entity_ids: Iterable[str], *,
                     hours: float = 24) -> list[str]:
    """Return entity_ids that have ZERO points in the last `hours`.

    Useful for finding entities your dashboards depend on but the
    recorder is excluding.
    """
    return [s["entity_id"] for s in batch_stats(client, entity_ids,
                                                  hours=hours)
            if s["history_points_24h"] == 0]
