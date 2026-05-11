"""System-level Home Assistant operations.

Covers `/api/`, `/api/config`, `/api/core/state`, `/api/error_log`, and
`/api/components`.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Iterable, Iterator

# Lines look like:
#   2026-05-11 08:17:06.542 ERROR (MainThread) [homeassistant.components.mqtt.number] Invalid …
_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+"
    r"(?P<level>CRITICAL|ERROR|WARNING|INFO|DEBUG)\s+"
    r"\((?P<thread>[^)]*)\)\s+"
    r"\[(?P<component>[a-zA-Z0-9_.]+)\]\s+"
    r"(?P<message>.*)$"
)


def parse_lines(text: str) -> Iterator[dict]:
    """Yield parsed records from raw error log text.

    Records have keys: ts (str), ts_dt (datetime|None), level, thread,
    component, message, raw. Non-matching lines are emitted with the structured
    fields set to None and only `raw` populated — so callers can choose to
    keep stack-trace continuation lines associated with the prior record.
    """
    for raw in text.splitlines():
        m = _LINE_RE.match(raw)
        if m:
            ts = m.group("ts")
            try:
                ts_dt: datetime | None = datetime.fromisoformat(ts)
            except ValueError:
                ts_dt = None
            yield {
                "ts": ts,
                "ts_dt": ts_dt,
                "level": m.group("level"),
                "thread": m.group("thread"),
                "component": m.group("component"),
                "message": m.group("message"),
                "raw": raw,
            }
        else:
            yield {"ts": None, "ts_dt": None, "level": None, "thread": None,
                   "component": None, "message": None, "raw": raw}


# Allow "1h", "30m", "15s", "2026-05-11 08:17", "2026-05-11T08:17:00",
# "08:17:00" (today), or bare hours like "08".
def parse_since(value: str, now: datetime | None = None) -> datetime:
    """Parse a --since value into a datetime. Raises ValueError on garbage."""
    if not value:
        raise ValueError("empty --since value")
    now = now or datetime.now()
    s = value.strip()
    # relative durations
    m = re.match(r"^(\d+)\s*([smhd])$", s, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        delta = {"s": timedelta(seconds=n), "m": timedelta(minutes=n),
                 "h": timedelta(hours=n), "d": timedelta(days=n)}[unit]
        return now - delta
    # "ago" suffix (e.g. "1h ago")
    if s.lower().endswith(" ago"):
        return parse_since(s[:-4].strip(), now=now)
    # absolute timestamps
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # time only — assume today
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            t = datetime.strptime(s, fmt).time()
            return datetime.combine(now.date(), t)
        except ValueError:
            continue
    raise ValueError(f"unrecognised --since value: {value!r}")


def filter_records(records: Iterable[dict], *,
                    since: datetime | None = None,
                    errors_only: bool = False,
                    component: str | None = None,
                    level: str | None = None) -> Iterator[dict]:
    """Apply structural filters to parsed records.

    When `since` is set, records with no parseable timestamp (stack-trace
    continuation lines, blanks) are dropped — they can't be located in time
    and would otherwise dominate `--top` buckets.
    """
    for r in records:
        if since:
            ts = r.get("ts_dt")
            if ts is None or ts < since:
                continue
        if errors_only and r.get("level") not in ("ERROR", "CRITICAL"):
            continue
        if component and r.get("component") != component:
            continue
        if level and r.get("level") != level:
            continue
        yield r


def bucket_counts(records: Iterable[dict], *,
                   by: str = "component", top: int = 20) -> list[tuple[str, int]]:
    """Count records bucketed by component / level / hour. Return top N as a list."""
    from collections import Counter
    c: Counter[str] = Counter()
    for r in records:
        if by == "component":
            key = r.get("component") or "—"
        elif by == "level":
            key = r.get("level") or "—"
        elif by == "hour":
            ts = r.get("ts_dt")
            key = ts.strftime("%Y-%m-%d %H:00") if ts else "—"
        else:
            key = r.get(by) or "—"
        c[key] += 1
    return c.most_common(top)


def status(client) -> dict:
    """Return the API status — succeeds when auth is valid."""
    data = client.get("")
    if isinstance(data, dict):
        return data
    return {"message": str(data)}


def config(client) -> dict:
    """Return the server configuration."""
    return client.get("config")


def core_state(client) -> dict:
    """Return Home Assistant core state (running/stopped/etc.)."""
    return client.get("core/state")


def error_log(client, lines: int | None = None) -> str:
    """Return the error log (text). Optionally truncate to last N lines."""
    text = client.get("error_log")
    if not isinstance(text, str):
        text = str(text)
    if lines is not None and lines > 0:
        return "\n".join(text.splitlines()[-lines:])
    return text


def components(client) -> list[str]:
    """Return the loaded components."""
    data = client.get("components")
    return list(data) if isinstance(data, list) else []


def system_health(client) -> Any:
    """Return system_health/info via WebSocket."""
    return client.ws_call("system_health/info")
