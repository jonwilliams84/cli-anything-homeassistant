"""Alarmo — custom integration alarm system management.

Alarmo (https://github.com/nielsfaber/alarmo) is a HACS custom integration
that adds a rich alarm panel to Home Assistant. It exposes two API surfaces:

1. **Services** (the ``alarmo`` domain) — arm, disarm, enable/disable users.
   These go through the standard HA service-call path.

2. **REST + WebSocket** — Alarmo's own HTTP views under ``/api/alarmo/*`` for
   configuration writes, and WS commands (``alarmo/config``, ``alarmo/areas``,
   ``alarmo/sensors``, ``alarmo/users``, ``alarmo/automations``,
   ``alarmo/sensor_groups``, ``alarmo/entities``) for reads.

This module mirrors the HACS exemplar: pure function-per-operation, callable
from Python directly or via the Click wrappers in ``homeassistant_cli.py``.
All functions take a ``client`` (the wire client) as their first argument.

Service surface:
  - ``arm(entity_id, *, code, mode, skip_delay, force)``
  - ``disarm(entity_id, *, code)``
  - ``enable_user(name)``
  - ``disable_user(name)``

Config surface (WS reads + REST writes):
  - ``get_config()`` / ``update_config(partial)``
  - ``list_areas()`` / ``create_area(name, modes)``
  - ``list_sensors()`` / ``list_users()`` / ``list_automations()``
  - ``list_sensor_groups()`` / ``list_entities()``
"""

from __future__ import annotations

from typing import Any, Optional

ALARMO_DOMAIN = "alarmo"

# Alarmo arm modes (matches services.yaml).
ARM_MODES = ("away", "night", "home", "vacation", "custom")

# Sensor types accepted by Alarmo's /api/alarmo/sensors REST view
# (sensors.py SENSOR_TYPES).
SENSOR_TYPES = ("door", "window", "motion", "tamper", "environmental", "other")

# Mode identifiers for the `modes` field on sensor updates — these are
# Alarmo's internal armed-state names, not the service-level arm modes.
SENSOR_ARM_MODES = (
    "armed_away", "armed_home", "armed_night",
    "armed_vacation", "armed_custom_bypass",
)

# The entity domains Alarmo accepts as sensors.
_SENSOR_DOMAINS = ("binary_sensor.", "sensor.")


def _validate_sensor_entity_id(entity_id: str) -> None:
    """Validate that entity_id is a binary_sensor.* or sensor.* entity."""
    if not entity_id:
        raise ValueError("entity_id is required")
    if not entity_id.startswith(_SENSOR_DOMAINS):
        raise ValueError(
            f"expected binary_sensor.* or sensor.* entity_id, got {entity_id!r}")


# ── services ────────────────────────────────────────────────────────────────

def arm(client, entity_id: str, *, code: Optional[str] = None,
        mode: Optional[str] = None, skip_delay: bool = False,
        force: bool = False) -> dict:
    """Arm an Alarmo alarm panel.

    Calls the ``alarmo/arm`` service. ``mode`` is one of away/night/home/
    vacation/custom (default: the panel's configured default, usually away).
    ``skip_delay`` skips the exit delay; ``force`` arms even if a sensor
    is open (bypassing the safety check).
    """
    if not entity_id.startswith("alarm_control_panel."):
        raise ValueError(
            f"expected alarm_control_panel.* entity_id, got {entity_id!r}")
    if mode is not None and mode not in ARM_MODES:
        raise ValueError(
            f"mode must be one of {', '.join(ARM_MODES)}, got {mode!r}")

    payload: dict[str, Any] = {"entity_id": entity_id}
    if code is not None:
        payload["code"] = code
    if mode is not None:
        payload["mode"] = mode
    if skip_delay:
        payload["skip_delay"] = True
    if force:
        payload["force"] = True
    return client.post("services/alarmo/arm", payload)


def disarm(client, entity_id: str, *, code: Optional[str] = None,
           skip_delay: bool = False) -> dict:
    """Disarm an Alarmo alarm panel.

    Calls the ``alarmo/disarm`` service. ``skip_delay`` is supported per
    Alarmo's services.yaml (skip the entry delay countdown).
    """
    if not entity_id.startswith("alarm_control_panel."):
        raise ValueError(
            f"expected alarm_control_panel.* entity_id, got {entity_id!r}")

    payload: dict[str, Any] = {"entity_id": entity_id}
    if code is not None:
        payload["code"] = code
    if skip_delay:
        payload["skip_delay"] = True
    return client.post("services/alarmo/disarm", payload)


def enable_user(client, *, name: str) -> dict:
    """Enable an Alarmo user (re-grant arm/disarm permissions).

    Calls ``alarmo/enable_user``. ``name`` must match an existing Alarmo
    user configured in the Alarmo UI.
    """
    if not name:
        raise ValueError("name is required")
    return client.post("services/alarmo/enable_user", {"name": name})


def disable_user(client, *, name: str) -> dict:
    """Disable an Alarmo user (revoke arm/disarm permissions).

    Calls ``alarmo/disable_user``. ``name`` must match an existing Alarmo
    user configured in the Alarmo UI.
    """
    if not name:
        raise ValueError("name is required")
    return client.post("services/alarmo/disable_user", {"name": name})


# ── config (WS read + REST write) ───────────────────────────────────────────

def get_config(client) -> dict:
    """Return Alarmo's global config (code requirements, MQTT, master, ...).

    Uses the ``alarmo/config`` WS command.
    """
    return client.ws_call("alarmo/config") or {}


def update_config(client, config: dict) -> dict:
    """Update Alarmo's global config. ``config`` is a partial dict; Alarmo's
    server-side schema validates and merges it (only the fields you pass are
    changed).

    Posts to the REST view ``/api/alarmo/config``.
    """
    if not isinstance(config, dict):
        raise ValueError("config must be a dict")
    if not config:
        raise ValueError("config is empty — nothing to update")
    return client.post("alarmo/config", config)


# ── areas ───────────────────────────────────────────────────────────────────

def list_areas(client) -> list[dict]:
    """Return all Alarmo areas (each with mode-specific timing config).

    Uses the ``alarmo/areas`` WS command.
    """
    data = client.ws_call("alarmo/areas")
    return list(data) if isinstance(data, list) else []


def create_area(client, *, name: str, area_id: Optional[str] = None,
                modes: Optional[dict] = None) -> dict:
    """Create or rename an Alarmo area.

    ``name`` is the display name. ``area_id`` is omitted when creating a
    new area; pass it to rename an existing one. ``modes`` is the per-mode
    timing config dict (enabled, exit_time, entry_time, trigger_time) keyed
    by mode name (away/home/night/custom/vacation).
    """
    if not name:
        raise ValueError("name is required")
    payload: dict[str, Any] = {"name": name}
    if area_id is not None:
        payload["area_id"] = area_id
    if modes is not None:
        payload["modes"] = modes
    return client.post("alarmo/area", payload)


def delete_area(client, area_id: str) -> dict:
    """Delete an Alarmo area by id."""
    if not area_id:
        raise ValueError("area_id is required")
    return client.post("alarmo/area",
                        {"area_id": area_id, "remove": True})


# ── sensors / users / automations / sensor_groups / entities ────────────────

def list_sensors(client) -> list[dict]:
    """Return all sensors registered with Alarmo.

    Uses the ``alarmo/sensors`` WS command.
    """
    data = client.ws_call("alarmo/sensors")
    return list(data) if isinstance(data, list) else []


def sensor_show(client, entity_id: str) -> dict:
    """Return one sensor's full Alarmo config dict.

    Pulls the full sensor list via the ``alarmo/sensors`` WS command and
    filters by ``entity_id``. Raises ``KeyError`` if the sensor is not
    registered with Alarmo.
    """
    _validate_sensor_entity_id(entity_id)
    for s in list_sensors(client):
        if s.get("entity_id") == entity_id:
            return s
    raise KeyError(f"no Alarmo sensor matching {entity_id!r}")


def sensor_remove(client, entity_id: str) -> dict:
    """Remove a sensor from Alarmo.

    Posts ``{"entity_id": ..., "remove": True}`` to the REST view
    ``/api/alarmo/sensors``. Once removed the sensor will no longer trigger
    the alarm or block arming — this is a destructive operation on a home
    security system.
    """
    _validate_sensor_entity_id(entity_id)
    return client.post("alarmo/sensors",
                        {"entity_id": entity_id, "remove": True})


def sensor_update(client, entity_id: str, **fields: Any) -> dict:
    """Update one or more fields on an Alarmo sensor.

    Only the fields you pass are sent — Alarmo's server-side schema merges
    them into the existing config. Accepted field names match Alarmo's
    ``AlarmoSensorView`` schema:

    - ``type`` (door/window/motion/tamper/environmental/other)
    - ``modes`` (list of armed_away/armed_home/armed_night/armed_vacation/
      armed_custom_bypass)
    - ``allow_open`` (bool)
    - ``always_on`` (bool)
    - ``auto_bypass`` (bool)
    - ``trigger_unavailable`` (bool)
    - ``arm_on_close`` (bool)
    - ``use_exit_delay`` (bool)
    - ``use_entry_delay`` (bool)
    - ``area`` (str)
    - ``enabled`` (bool)
    - ``group`` (str or None)
    """
    _validate_sensor_entity_id(entity_id)
    if not fields:
        raise ValueError("at least one field to update is required")
    # Validate type / modes here so the caller gets a clean error before
    # hitting the wire.
    if "type" in fields and fields["type"] is not None:
        if fields["type"] not in SENSOR_TYPES:
            raise ValueError(
                f"type must be one of {', '.join(SENSOR_TYPES)}, "
                f"got {fields['type']!r}")
    if "modes" in fields and fields["modes"] is not None:
        modes = fields["modes"]
        if not isinstance(modes, (list, tuple)):
            raise ValueError("modes must be a list")
        for m in modes:
            if m not in SENSOR_ARM_MODES:
                raise ValueError(
                    f"modes entries must be one of "
                    f"{', '.join(SENSOR_ARM_MODES)}, got {m!r}")
    payload: dict[str, Any] = {"entity_id": entity_id, **fields}
    return client.post("alarmo/sensors", payload)


def list_users(client) -> list[dict]:
    """Return all Alarmo users.

    Uses the ``alarmo/users`` WS command.
    """
    data = client.ws_call("alarmo/users")
    return list(data) if isinstance(data, list) else []


def list_automations(client) -> list[dict]:
    """Return Alarmo's internal automations (notifications/notifications on
    alarm events — NOT HA automations).

    Uses the ``alarmo/automations`` WS command.
    """
    data = client.ws_call("alarmo/automations")
    return list(data) if isinstance(data, list) else []


def list_sensor_groups(client) -> list[dict]:
    """Return Alarmo sensor groups (sub-areas / mode-based sensor sets).

    Uses the ``alarmo/sensor_groups`` WS command.
    """
    data = client.ws_call("alarmo/sensor_groups")
    return list(data) if isinstance(data, list) else []


def list_entities(client) -> list[dict]:
    """Return the list of all alarm_control_panel entities managed by Alarmo.

    Uses the ``alarmo/entities`` WS command.
    """
    data = client.ws_call("alarmo/entities")
    return list(data) if isinstance(data, list) else []