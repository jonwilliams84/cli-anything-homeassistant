"""Integration diagnostics — the "Download diagnostics" JSON every supported
integration produces, available as both REST and WS in modern HA.

Two flavours:
  - config_entry diagnostics (the integration as a whole)
  - device diagnostics (one device managed by an integration)
"""

from __future__ import annotations

import json
from typing import Any, Optional


def list_handlers(client) -> list[dict]:
    """Return one row per integration that exposes diagnostics.

    Each row: {domain, handlers: {config_entry, device}}.
    """
    data = client.ws_call("diagnostics/list")
    return list(data) if isinstance(data, list) else []


def get_config_entry(client, entry_id: str) -> Any:
    """Download config-entry-level diagnostics. Hits the REST endpoint the
    UI's "Download diagnostics" link uses; returns the parsed JSON."""
    if not entry_id:
        raise ValueError("entry_id is required")
    # The endpoint returns either JSON (auto-parsed) or a downloadable file.
    return client.get(f"diagnostics/config_entry/{entry_id}")


def get_device(client, entry_id: str, device_id: str) -> Any:
    """Download device-level diagnostics scoped to a specific config entry."""
    if not entry_id:
        raise ValueError("entry_id is required")
    if not device_id:
        raise ValueError("device_id is required")
    return client.get(
        f"diagnostics/config_entry/{entry_id}/device/{device_id}"
    )


def save_to_file(data: Any, path: str) -> int:
    """Pretty-write diagnostics JSON to `path` and return the byte count."""
    text = json.dumps(data, indent=2, default=str)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return len(text.encode("utf-8"))
