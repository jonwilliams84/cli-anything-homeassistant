"""Home Assistant's own HTTP server configuration (the `http` integration).

HA lets the user manage the web server's bind address, TLS and proxy
settings at runtime. The state lives in the `http` integration's store and
is edited over the websocket:

  - ``http/config``            — read the current state:
                                  ``stable`` (the confirmed-working config),
                                  ``pending`` (an unconfirmed config waiting
                                  for ``http/config/promote``, or None),
                                  ``default`` (the built-in default) and
                                  ``active_config_type``.
  - ``http/config/configure``  — store a NEW PENDING config and restart HA
                                  to apply it. The payload is
                                  ``{"config": {...}}``; sending ``null``
                                  clears the pending config. HA validates the
                                  config (and can refuse to bind it) BEFORE
                                  it restarts.
  - ``http/config/promote``    — promote the pending config to stable, i.e.
                                  accept it as the good one (it is the
                                  config the recovery mode falls back to).

A pending config that was not promoted is reverted automatically after a
few minutes, so the usual flow is: ``http set`` → check HA is up → ``http
promote``.
"""

from __future__ import annotations

import re
from typing import Any, Optional

#: The keys HA's HTTP storage schema accepts. Anything else (including the
#: store's own bookkeeping keys) is refused before the request is sent.
ALLOWED_KEYS = (
    "server_host",
    "server_port",
    "ssl_certificate",
    "ssl_peer_certificate",
    "ssl_key",
    "cors_allowed_origins",
    "use_x_forwarded_for",
    "trusted_proxies",
    "login_attempts_threshold",
    "ip_ban_enabled",
    "ssl_profile",
    "use_x_frame_options",
)

#: Keys whose value is a LIST in HA's schema. A single string is accepted
#: and wrapped, so `server_host=0.0.0.0` does the obvious thing.
LIST_KEYS = ("server_host", "cors_allowed_origins", "trusted_proxies")

#: Keys the store keeps for its own bookkeeping. They are not part of the
#: schema and must not be sent back.
META_KEYS = ("created_at", "error", "error_message")


def get_config(client) -> dict:
    """Read the HTTP server configuration (stable / pending / default)."""
    return client.ws_call("http/config") or {}


def _clean(config: dict) -> dict:
    """Drop the store's own bookkeeping keys.

    They are not part of HA's schema and are refused as extra keys.
    """
    return {k: v for k, v in config.items() if k not in META_KEYS}


def _offending_key(message: str) -> Optional[str]:
    """Pull the key out of HA's "extra keys not allowed @ data['key']"."""
    match = re.search(r"data\['([^']+)'\]", message)
    return match.group(1) if match else None


def set_config(client, updates: dict) -> dict:
    """Store a new PENDING HTTP config and restart HA to apply it.

    `updates` are merged onto the config HA is currently running with
    (the pending one when there is one, else the stable one), so a single
    key can be changed without restating the rest. HA answers
    ``{"restart": bool}`` — the restart only happens when the pending slot
    actually changed.
    """
    if not isinstance(updates, dict) or not updates:
        raise ValueError("at least one config key is required")
    unknown = [k for k in updates if k not in ALLOWED_KEYS]
    if unknown:
        raise ValueError(
            f"unknown HTTP config key(s): {', '.join(sorted(unknown))}. "
            f"Valid keys: {', '.join(ALLOWED_KEYS)}"
        )
    current = get_config(client)
    base = current.get("pending") or current.get("stable") or {}
    merged = _clean({**base, **updates})
    # HA validates the WHOLE config, so a key this HA does not know (a
    # config written by a newer/older version) is refused. Drop the key
    # HA named and try again rather than failing the whole change.
    for _ in range(5):
        try:
            return client.ws_call("http/config/configure", {"config": merged}) or {}
        except Exception as exc:  # noqa: BLE001 — re-raised unless it is a schema mismatch
            message = str(exc)
            if "extra keys not allowed" not in message:
                raise
            key = _offending_key(message)
            if not key or key not in merged:
                raise
            merged.pop(key, None)
    return client.ws_call("http/config/configure", {"config": merged}) or {}


def promote(client) -> dict:
    """Promote the pending HTTP config to stable.

    Only do this once HA is confirmed to be serving correctly with the new
    config: the stable config is the one recovery mode falls back to.
    """
    return client.ws_call("http/config/promote") or {}


def describe(client) -> dict:
    """A flattened summary of the HTTP config for table output."""
    data = get_config(client)
    stable = data.get("stable") or {}
    pending = data.get("pending")
    return {
        "active_config_type": data.get("active_config_type"),
        "stable": stable,
        "pending": pending,
        "pending_keys": sorted(k for k in pending) if isinstance(pending, dict) else [],
        "revert_at": data.get("revert_at"),
        "default": data.get("default"),
    }


def coerce_value(key: str, value: Any) -> Any:
    """Coerce a CLI-supplied value into the shape HA's schema wants.

    A single string for a list-valued key becomes a one-item list; every
    other value is passed through as parsed.
    """
    if key in LIST_KEYS and isinstance(value, str):
        return [value]
    if key in LIST_KEYS and isinstance(value, (list, tuple)):
        return list(value)
    return value


def set_config_from_pairs(client, pairs: dict) -> dict:
    """Apply `key=value` pairs to the HTTP config (see :func:`set_config`)."""
    updates: dict[str, Any] = {}
    for key, value in pairs.items():
        if key not in ALLOWED_KEYS:
            raise ValueError(
                f"unknown HTTP config key {key!r}. Valid keys: {', '.join(ALLOWED_KEYS)}"
            )
        updates[key] = coerce_value(key, value)
    return set_config(client, updates)
