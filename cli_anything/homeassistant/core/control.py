"""Core HA lifecycle — restart / stop / check-config / reload-core-config.

These all map to public services under the `homeassistant` domain. Call them
the same way the UI's "Server Controls" page does.

`check_config` is the safety-net before a restart: HA will write a persistent
notification with any errors found. We surface that notification back so the
caller doesn't have to poll separately.
"""

from __future__ import annotations

import time
from typing import Any

from cli_anything.homeassistant.core import services as services_core
from cli_anything.homeassistant.core import states as states_core


def restart(client, *, safe_mode: bool = False) -> Any:
    """Restart Home Assistant. The WS connection drops; reconnect after ~20-60s."""
    data: dict[str, Any] = {}
    if safe_mode:
        data["safe_mode"] = True
    return services_core.call_service(client, "homeassistant", "restart",
                                       service_data=data or None)


def stop(client) -> Any:
    """Stop Home Assistant. **HA will not auto-restart unless the container does.**"""
    return services_core.call_service(client, "homeassistant", "stop")


def reload_core_config(client) -> Any:
    """Reload configuration.yaml without restarting the process."""
    return services_core.call_service(client, "homeassistant", "reload_core_config")


def reload_config_entry(client, entry_id: str) -> Any:
    """Reload a specific integration's config entry (`config_entry/reload`)."""
    if not entry_id:
        raise ValueError("entry_id is required")
    return client.ws_call("config_entries/reload", {"entry_id": entry_id})


def reload_all(client) -> dict:
    """Reload the universe of reloadable domains.

    Calls homeassistant.reload_all, which reloads automations, scripts,
    scenes, groups, template entities, helpers, and customize.yaml. Quicker
    than a full restart for most config tweaks.
    """
    return services_core.call_service(client, "homeassistant", "reload_all")


def check_config(client, *, wait_secs: float = 8.0) -> dict:
    """Run a config check and return the resulting status.

    HA's `homeassistant.check_config` service writes a persistent notification
    named `config_check_failed` (on failure) or just removes it (on success).
    We:
      1) trigger the service,
      2) wait briefly for HA to write the notification,
      3) read the `persistent_notification.config_check_failed` state (if any),
      4) report `valid` / `errors`.
    """
    services_core.call_service(client, "homeassistant", "check_config")
    deadline = time.time() + max(0.1, wait_secs)
    notification = None
    while time.time() < deadline:
        try:
            notification = states_core.get_state(
                client, "persistent_notification.config_check_failed",
            )
            break
        except Exception:
            time.sleep(0.5)
    if not notification or notification.get("state") in (None, "unknown",
                                                          "unavailable"):
        return {"valid": True, "errors": None}
    attrs = notification.get("attributes") or {}
    return {
        "valid": False,
        "message": attrs.get("message"),
        "title": attrs.get("title") or "Config Check Failed",
        "created_at": attrs.get("created_at"),
    }


def safe_restart(client, *, wait_check_secs: float = 8.0) -> dict:
    """Belt-and-braces: check-config first; only restart on a clean result."""
    result = check_config(client, wait_secs=wait_check_secs)
    if not result.get("valid"):
        return {"restarted": False, "reason": "check_config failed",
                "check": result}
    restart(client)
    return {"restarted": True, "check": result}
