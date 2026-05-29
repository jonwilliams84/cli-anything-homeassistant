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
    no_attributes: bool = False,
    significant_changes_only: bool = False,
) -> list[list[dict]]:
    """Return historical state changes from /api/history/period.

    ``no_attributes`` (default False) — when True, omits the per-sample
    ``attributes`` blob from each entry. Massive speed/size win on installs
    with heavy entities (96k+ entries on big homes); the default keeps
    backwards compatibility.

    ``significant_changes_only`` (default False) — when True, HA only
    returns samples that represent a meaningful state change rather than
    every recorded sample. Cuts response size dramatically for noisy
    sensors (sgv/power/temperature). Trades off resolution for size.
    """
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
    if no_attributes:
        params["no_attributes"] = ""
    if significant_changes_only:
        params["significant_changes_only"] = ""
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
