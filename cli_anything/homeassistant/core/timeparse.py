"""Shared ``--start``/``--end`` time parsing for the CLI layer.

Issue #50: ``history-ext with-stats-fallback`` crashed with
``TypeError: can't compare offset-naive and offset-aware datetimes`` when
``--start`` was given without a timezone and ``--end`` was left at its
aware default (``now()``). The ``history`` command already treats naive
times as UTC, but each command parsed its own ISO-8601 strings inline, so
the behaviour drifted.

Every command that accepts ``--start``/``--end`` as ISO-8601 strings now
shares :func:`parse_time_arg`, so:

* naive times are treated as **UTC** (matching what ``history`` has always
  done via its ``_iso`` helper) instead of exploding at a comparison,
* an explicit ``Z`` / ``z`` suffix (RFC 3339) is accepted everywhere,
* offsets like ``+02:00`` are preserved, and
* unparseable input fails fast with a message that names the offending
  option.

Public API
----------
* :func:`parse_time_arg`
* :func:`parse_time_range`
"""

from __future__ import annotations

from datetime import datetime, timezone


def parse_time_arg(
    raw: str | None,
    *,
    field: str = "time",
    default: datetime | None = None,
) -> datetime | None:
    """Parse an ISO-8601 / RFC 3339 datetime argument into an aware datetime.

    Parameters
    ----------
    raw:
        The raw CLI string (or an already-parsed ``datetime``, which is
        passed through untouched apart from tz-normalisation). ``None`` or
        an empty/whitespace string yields ``default``.
    field:
        Option name used in error messages, e.g. ``"--start"``.
    default:
        Value returned when ``raw`` is None/empty (e.g. ``now()`` for an
        open-ended ``--end``).

    Returns
    -------
    datetime
        Always timezone-aware; naive input is treated as UTC so it can be
        compared with aware defaults without crashing (the issue #50 crash).

    Raises
    ------
    ValueError
        If ``raw`` is a non-empty string that is not valid ISO-8601.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return default
    if isinstance(raw, datetime):
        dt = raw
    else:
        text = str(raw).strip().replace("Z", "+00:00").replace("z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            raise ValueError(f"invalid {field} (ISO-8601 datetime expected): {raw!r}") from None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def parse_time_range(
    start_raw: str | None,
    end_raw: str | None,
    *,
    default_end: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Parse a ``--start``/``--end`` pair and validate the ordering.

    Naive and aware input may be mixed freely — both sides are normalised
    to aware datetimes (naive → UTC) *before* the comparison, so a naive
    ``--start`` next to an aware default ``--end`` never raises the
    offset-naive/aware ``TypeError`` from issue #50.
    """
    start = parse_time_arg(start_raw, field="--start")
    if start is None:
        raise ValueError("--start is required")
    end = parse_time_arg(end_raw, field="--end", default=default_end)
    if end is not None and start > end:
        raise ValueError("--start must be before --end")
    if end is None:
        end = datetime.now(timezone.utc)
    return start, end
