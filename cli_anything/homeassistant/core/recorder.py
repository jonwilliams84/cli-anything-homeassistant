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


def purge(client, *, keep_days: int | None = None,
           repack: bool = False, apply_filter: bool = False) -> dict:
    """Trigger the recorder's general purge (recorder.purge service).

    `keep_days`     — how many days of history to keep (default: recorder's own)
    `repack`        — VACUUM the DB after purge (slow; off by default)
    `apply_filter`  — apply the include/exclude filter from configuration.yaml
                       to existing rows (rare but useful for cleanup)
    """
    from cli_anything.homeassistant.core import services as services_core
    data: dict = {}
    if keep_days is not None: data["keep_days"] = keep_days
    if repack:                data["repack"] = True
    if apply_filter:          data["apply_filter"] = True
    return services_core.call_service(client, "recorder", "purge",
                                       service_data=data or None)


def purge_entities(client, entity_ids: list[str], *,
                    domains: list[str] | None = None,
                    entity_globs: list[str] | None = None,
                    days: int | None = None) -> dict:
    """Purge history for specific entities / domains / globs.

    `entity_ids`    — exact ids to wipe
    `domains`       — wipe every entity in these domains
    `entity_globs`  — wildcard patterns (e.g. ``sensor.test_*``)
    `days`          — keep this many days; older rows go away
    """
    from cli_anything.homeassistant.core import services as services_core
    data: dict = {}
    if entity_ids:    data["entity_id"] = list(entity_ids)
    if domains:       data["domains"] = list(domains)
    if entity_globs:  data["entity_globs"] = list(entity_globs)
    if days is not None: data["days"] = days
    if not data:
        raise ValueError("provide at least one of entity_ids / domains / entity_globs")
    return services_core.call_service(client, "recorder", "purge_entities",
                                       service_data=data)
