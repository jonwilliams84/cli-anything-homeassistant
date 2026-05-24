"""Zone registry — geographic regions used for presence + location automations.

Zones live in Home Assistant in two places:

1. **Storage zones** (the "Zones" UI panel under Settings → Areas & Zones) are
   editable via the ``config/zone/*`` WebSocket namespace and persist to
   ``.storage/zone``. Every CRUD method on this module targets that namespace.
2. **YAML zones** declared in ``configuration.yaml`` under ``zone:`` are
   read-only from the API. They show up via ``state list --domain zone`` but
   ``update``/``delete`` will refuse them with a clear error.

WS message shape::

    config/zone/list     → list[dict]
    config/zone/create   → dict (the new zone)
    config/zone/update   → dict (the merged zone)
    config/zone/delete   → null
"""

from __future__ import annotations

from typing import Any, Optional


# ─────────────────────────────────────────────────────────────────── list

def list_zones(client) -> list[dict]:
    """Return every storage-defined zone (does not include YAML zones).

    YAML zones are exposed only as entity states (`zone.*`) and have no
    registry record; use ``state list --domain zone`` to see them.
    """
    data = client.ws_call("config/zone/list")
    return list(data) if isinstance(data, list) else []


def find_zone(client, ident: str) -> Optional[dict]:
    """Look up a zone by id or by case-insensitive name."""
    if not ident:
        return None
    ident_l = ident.lower()
    for z in list_zones(client):
        if z.get("id") == ident:
            return z
        if (z.get("name") or "").lower() == ident_l:
            return z
    return None


# ─────────────────────────────────────────────────────────────── create

def create(
    client,
    *,
    name: str,
    latitude: float,
    longitude: float,
    radius: Optional[float] = None,
    icon: Optional[str] = None,
    passive: Optional[bool] = None,
) -> dict:
    """Create a new storage zone.

    *name* / *latitude* / *longitude* are required (HA rejects partial zones).
    *radius* defaults to ``100`` metres on the server side when omitted.
    *passive* marks the zone as informational only — it is excluded from
    state-based ``zone.entity`` resolution but still shows up in maps.
    """
    if not name:
        raise ValueError("name is required")
    if latitude is None or longitude is None:
        raise ValueError("latitude and longitude are required")

    payload: dict[str, Any] = {
        "name": name,
        "latitude": float(latitude),
        "longitude": float(longitude),
    }
    if radius is not None:
        payload["radius"] = float(radius)
    if icon is not None:
        payload["icon"] = icon
    if passive is not None:
        payload["passive"] = bool(passive)
    return client.ws_call("config/zone/create", payload) or {}


# ─────────────────────────────────────────────────────────────── update

def update(
    client,
    zone_id: str,
    *,
    name: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    radius: Optional[float] = None,
    icon: Optional[str] = None,
    passive: Optional[bool] = None,
) -> dict:
    """Patch a storage zone. Only fields you pass are sent."""
    if not zone_id:
        raise ValueError("zone_id is required")

    payload: dict[str, Any] = {"zone_id": zone_id}
    if name is not None:       payload["name"] = name
    if latitude is not None:   payload["latitude"] = float(latitude)
    if longitude is not None:  payload["longitude"] = float(longitude)
    if radius is not None:     payload["radius"] = float(radius)
    if icon is not None:       payload["icon"] = icon
    if passive is not None:    payload["passive"] = bool(passive)
    return client.ws_call("config/zone/update", payload) or {}


# ─────────────────────────────────────────────────────────────── delete

def delete(client, zone_id: str) -> Any:
    """Delete a storage zone. YAML-declared zones cannot be removed via API."""
    if not zone_id:
        raise ValueError("zone_id is required")
    return client.ws_call("config/zone/delete", {"zone_id": zone_id})


# ──────────────────────────────────────────────────────────── derived helpers

def list_state_zones(client) -> list[dict]:
    """List every ``zone.*`` entity state (storage + YAML zones combined).

    Useful when an agent only cares about *which zones exist right now*, not
    where they came from. Returns the raw entity-state dicts.
    """
    data = client.get("states") or []
    return [s for s in data
            if isinstance(s, dict)
            and isinstance(s.get("entity_id"), str)
            and s["entity_id"].startswith("zone.")]


def entities_in_zone(client, zone_id_or_entity: str) -> list[dict]:
    """Return every entity state whose ``state`` matches the given zone name.

    Pass either the entity_id (``zone.home``) or the friendly name. Looks
    through all device_tracker / person states and yields those currently
    "inside" the zone (HA stores the zone's friendly_name as the state value).
    """
    if not zone_id_or_entity:
        raise ValueError("zone identifier is required")

    target_name: Optional[str] = None
    target_id = zone_id_or_entity
    if zone_id_or_entity.startswith("zone."):
        target_id = zone_id_or_entity
        # Resolve to friendly name via /api/states/<entity_id>
        try:
            st = client.get(f"states/{zone_id_or_entity}")
            if isinstance(st, dict):
                attrs = st.get("attributes") or {}
                target_name = attrs.get("friendly_name") or st.get("state")
        except Exception:
            target_name = None
    else:
        # ident is a zone name; find its entity_id by scanning zone states
        for z in list_state_zones(client):
            attrs = z.get("attributes") or {}
            if (attrs.get("friendly_name") or "").lower() == zone_id_or_entity.lower():
                target_name = attrs.get("friendly_name")
                target_id = z.get("entity_id", target_id)
                break

    name_l = (target_name or "").lower() if target_name else None
    out: list[dict] = []
    for s in client.get("states") or []:
        if not isinstance(s, dict):
            continue
        eid = s.get("entity_id") or ""
        if not (eid.startswith("person.") or eid.startswith("device_tracker.")):
            continue
        state = (s.get("state") or "").lower()
        if name_l and state == name_l:
            out.append(s)
        elif state == target_id.lower():
            out.append(s)
    return out
