"""System log — list, clear, and write HA system log entries.

WS command wrapped:
  system_log/list  — returns the in-memory dedup log store (LIFO list of entries)

Service calls wrapped (REST POST to /api/services/...):
  system_log/clear — flush the log store
  system_log/write — inject a synthetic log message at a chosen level

Log entry shape returned by list_errors (from HA source):
  {name, message, level, source, timestamp, exception, count, first_occurred}
"""

from __future__ import annotations

from typing import Any

_VALID_LEVELS = {"debug", "info", "warning", "error", "critical"}


def list_errors(client) -> list[dict]:
    """Return the current system log as a list of entry dicts.

    WS type: ``system_log/list``

    Each entry contains: name, message, level, source, timestamp,
    exception, count, first_occurred.
    """
    data = client.ws_call("system_log/list")
    return list(data) if isinstance(data, list) else []


def clear(client) -> Any:
    """Clear (flush) the system log store.

    Service call: POST services/system_log/clear with empty payload.
    Returns the raw POST result.
    """
    return client.post("services/system_log/clear", {})


def write(
    client,
    *,
    message: str,
    level: str = "error",
    logger: str | None = None,
) -> Any:
    """Inject a synthetic message into the system log at the chosen level.

    Service call: POST services/system_log/write

    Parameters
    ----------
    message:
        Non-empty log message text.
    level:
        One of ``debug``, ``info``, ``warning``, ``error``, ``critical``.
    logger:
        Optional logger name. Defaults to ``system_log.external`` inside HA.
    """
    if not message:
        raise ValueError("message is required")
    if level not in _VALID_LEVELS:
        raise ValueError(
            f"level must be one of {sorted(_VALID_LEVELS)}, got {level!r}"
        )
    payload: dict[str, Any] = {"message": message, "level": level}
    if logger is not None:
        payload["logger"] = logger
    return client.post("services/system_log/write", payload)
