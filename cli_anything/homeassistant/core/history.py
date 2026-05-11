"""History + logbook endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def history(
    client,
    entity_ids: list[str] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    minimal_response: bool = True,
) -> list[list[dict]]:
    """Return historical state changes from /api/history/period."""
    path = "history/period"
    if start is not None:
        path = f"history/period/{_iso(start)}"
    params: dict[str, str] = {}
    if entity_ids:
        params["filter_entity_id"] = ",".join(entity_ids)
    if end is not None:
        params["end_time"] = _iso(end)
    if minimal_response:
        params["minimal_response"] = ""
    data = client.get(path, params=params or None)
    return data if isinstance(data, list) else []


def logbook(
    client,
    entity_id: str | None = None,
    hours: float | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict]:
    """Return logbook entries from /api/logbook."""
    if start is None and hours is not None:
        start = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
    path = "logbook"
    if start is not None:
        path = f"logbook/{_iso(start)}"
    params: dict[str, str] = {}
    if entity_id:
        params["entity"] = entity_id
    if end is not None:
        params["end_time"] = _iso(end)
    data = client.get(path, params=params or None)
    return data if isinstance(data, list) else []
