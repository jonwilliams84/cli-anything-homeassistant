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
    return services_core.call_service(client, "homeassistant", "restart", service_data=data or None)


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
                client,
                "persistent_notification.config_check_failed",
            )
            break
        except Exception:
            time.sleep(0.5)
    if not notification or notification.get("state") in (None, "unknown", "unavailable"):
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
        return {"restarted": False, "reason": "check_config failed", "check": result}
    restart(client)
    return {"restarted": True, "check": result}


def update_entity(client, entity_ids: list[str], *, verify: bool = True) -> dict:
    """`homeassistant.update_entity` — force a poll NOW, and check it happened.

    Two things make the raw service call unsafe to trust:

    * **A typo is a silent success.** The handler builds one
      `async_update_entity()` task per id and gathers them; an id that matches
      no entity produces no task and no complaint. Measured on 2025.1.4,
      `update_entity` for `sensor.does_not_exist` returns HTTP 200 with `[]`,
      exactly like a real refresh.
    * **The REST response is always `[]`.** The service endpoint returns the
      states this call CHANGED, and a refresh that re-reads the same value
      changes nothing — so an empty list means neither success nor failure.

    So `verify` reads each entity's `last_updated` before and after and reports
    per entity: `refreshed` (the timestamp moved), `unchanged` (it did not —
    normal for a non-polling entity, and the honest answer), or `missing`
    (there is no such entity, which the service would have swallowed).

    `entity_id: all` is NOT accepted here — the schema is `cv.entity_ids`, and
    HA answers `Entity ID all is an invalid entity ID` with a bare 400.
    """
    if not entity_ids:
        raise ValueError("at least one entity_id is required")
    ids = [str(e) for e in entity_ids]
    for eid in ids:
        if eid == "all":
            raise ValueError(
                "homeassistant.update_entity does not accept 'all' — its schema is "
                "cv.entity_ids, which rejects it. Pass explicit entity_ids "
                "(`entity list` can produce them)."
            )
        if "." not in eid:
            raise ValueError(f"entity_id must be in 'domain.object' form, got {eid!r}")

    before: dict[str, Any] = {}
    if verify:
        for eid in ids:
            before[eid] = _last_updated(client, eid)

    result = services_core.call_service(
        client, "homeassistant", "update_entity", service_data={"entity_id": ids}
    )
    if not verify:
        return {"requested": ids, "result": result}

    entities = []
    for eid in ids:
        was = before.get(eid)
        now = _last_updated(client, eid)
        if was is None and now is None:
            status = "missing"
        elif was != now:
            status = "refreshed"
        else:
            status = "unchanged"
        entities.append({"entity_id": eid, "status": status, "last_updated": now})
    return {
        "requested": ids,
        "entities": entities,
        "refreshed": sum(1 for e in entities if e["status"] == "refreshed"),
        "unchanged": sum(1 for e in entities if e["status"] == "unchanged"),
        "missing": [e["entity_id"] for e in entities if e["status"] == "missing"],
    }


def _last_updated(client, entity_id: str) -> Any:
    """`last_updated` for an entity, or None when it does not exist."""
    try:
        state = states_core.get_state(client, entity_id)
    except Exception:  # noqa: BLE001 - a missing entity is a 404, not a failure
        return None
    if not isinstance(state, dict):
        return None
    return state.get("last_updated")


def set_location(
    client,
    *,
    latitude: float,
    longitude: float,
    elevation: float | None = None,
) -> Any:
    """`homeassistant.set_location` — move the instance's home coordinates.

    This is not cosmetic: every zone test, `sun.sun`, and every automation
    with a `zone` trigger is evaluated against it. The change is applied via
    `hass.config.async_update()` and persists in `.storage/core.config`,
    overriding `configuration.yaml`.

    Admin-only (`async_register_admin_service`). Elevation is left alone when
    not given, rather than reset.
    """
    if latitude is None or longitude is None:
        raise ValueError("both latitude and longitude are required")
    if not -90 <= float(latitude) <= 90:
        raise ValueError(f"latitude must be between -90 and 90, got {latitude}")
    if not -180 <= float(longitude) <= 180:
        raise ValueError(f"longitude must be between -180 and 180, got {longitude}")
    data: dict[str, Any] = {
        "latitude": float(latitude),
        "longitude": float(longitude),
    }
    if elevation is not None:
        data["elevation"] = float(elevation)
    return services_core.call_service(client, "homeassistant", "set_location", service_data=data)


def reload_custom_templates(client) -> Any:
    """`homeassistant.reload_custom_templates` — re-read `custom_templates/*.jinja`.

    Only the shared Jinja macro files. It does NOT reload template entities —
    that is `reload_all`, or the template integration's own reload.
    """
    return services_core.call_service(client, "homeassistant", "reload_custom_templates")


def save_persistent_states(client) -> Any:
    """`homeassistant.save_persistent_states` — flush restore-state to disk now.

    HA writes `.storage/core.restore_state` on a timer and at shutdown. Call
    this before pulling power on the host, or before taking a backup that has
    to include the current values of `RestoreEntity`-backed entities.
    """
    return services_core.call_service(client, "homeassistant", "save_persistent_states")
