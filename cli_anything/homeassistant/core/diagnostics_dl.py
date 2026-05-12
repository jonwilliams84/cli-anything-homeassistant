"""Diagnostics download — bundle download endpoints for config entries and devices.

Two REST GET endpoints are wrapped here:
  - config_entry diagnostics: /api/diagnostics/config_entry/{entry_id}
  - device diagnostics:       /api/diagnostics/config_entry/{entry_id}/device/{device_id}

A file-save helper is also provided for persisting the returned JSON to disk.

Note: the route does NOT include the integration `domain` segment. Older
versions of this module (≤ v1.25.2) wrongly emitted
``/api/diagnostics/config_entry/{domain}/{entry_id}`` and got 404s. The
`domain` kwarg is retained for backward compat but is ignored in URL
construction.
"""

from __future__ import annotations

import json
import warnings
from typing import Any


def download_config_entry_diagnostics(
    client, *, entry_id: str, domain: str | None = None,
) -> Any:
    """Download diagnostics bundle for a config entry.

    REST GET /api/diagnostics/config_entry/{entry_id}

    `entry_id` — the config entry's id (required).
    `domain`   — accepted for back-compat but unused in URL construction.
                 If you supply it, you'll get a DeprecationWarning. Drop it.

    Returns the parsed diagnostics JSON for the integration config entry.
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    if domain is not None:
        warnings.warn(
            "download_config_entry_diagnostics: `domain` is no longer used "
            "in URL construction (HA's route is "
            "/api/diagnostics/config_entry/{entry_id} with no domain "
            "segment). Drop the kwarg.",
            DeprecationWarning, stacklevel=2,
        )
    return client.get(f"diagnostics/config_entry/{entry_id}")


def download_device_diagnostics(
    client, *, entry_id: str, device_id: str, domain: str | None = None,
) -> Any:
    """Download diagnostics bundle for a specific device within a config entry.

    REST GET /api/diagnostics/config_entry/{entry_id}/device/{device_id}

    `entry_id` and `device_id` are required. `domain` is back-compat only,
    ignored, deprecated.
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    if not device_id:
        raise ValueError("device_id is required")
    if domain is not None:
        warnings.warn(
            "download_device_diagnostics: `domain` is no longer used in URL "
            "construction. Drop the kwarg.",
            DeprecationWarning, stacklevel=2,
        )
    return client.get(f"diagnostics/config_entry/{entry_id}/device/{device_id}")


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
