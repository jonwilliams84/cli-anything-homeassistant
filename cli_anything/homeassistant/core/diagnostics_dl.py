"""Diagnostics download — bundle download endpoints for config entries and devices.

Two REST GET endpoints are wrapped here:
  - config_entry diagnostics: /api/diagnostics/config_entry/{domain}/{entry_id}
  - device diagnostics:       /api/diagnostics/config_entry/{domain}/{entry_id}/device/{device_id}

A file-save helper is also provided for persisting the returned JSON to disk.
"""

from __future__ import annotations

import json
from typing import Any


def download_config_entry_diagnostics(client, *, domain: str, entry_id: str) -> Any:
    """Download diagnostics bundle for a config entry.

    REST GET /api/diagnostics/config_entry/{domain}/{entry_id}

    Returns the parsed diagnostics JSON for the integration config entry
    identified by `domain` and `entry_id`.
    """
    if not domain:
        raise ValueError("domain is required")
    if not entry_id:
        raise ValueError("entry_id is required")
    return client.get(f"diagnostics/config_entry/{domain}/{entry_id}")


def download_device_diagnostics(
    client, *, domain: str, entry_id: str, device_id: str
) -> Any:
    """Download diagnostics bundle for a specific device within a config entry.

    REST GET /api/diagnostics/config_entry/{domain}/{entry_id}/device/{device_id}

    Returns the parsed diagnostics JSON scoped to `device_id` within the
    integration config entry identified by `domain` and `entry_id`.
    """
    if not domain:
        raise ValueError("domain is required")
    if not entry_id:
        raise ValueError("entry_id is required")
    if not device_id:
        raise ValueError("device_id is required")
    return client.get(
        f"diagnostics/config_entry/{domain}/{entry_id}/device/{device_id}"
    )


def save_diagnostics_to_file(data: Any, path: str) -> int:
    """Pretty-write diagnostics JSON to `path` and return the byte count.

    `path` must be a non-empty string pointing to a writable location.
    Returns the number of bytes written.
    """
    if not path:
        raise ValueError("path is required")
    text = json.dumps(data, indent=2, default=str)
    encoded = text.encode("utf-8")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return len(encoded)
