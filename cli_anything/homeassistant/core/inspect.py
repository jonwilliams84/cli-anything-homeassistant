"""Combined entity-inspection view — the "tell me everything about this entity" command.

Aggregates from:
  - state machine (current state + attributes + last_changed)
  - entity registry (unique_id, platform, area, device_id, labels, disabled/hidden flags)
  - device registry (the device that owns the entity, if any)
  - history (recent state changes — optional, can be slow)
  - references (which automations / templates / lovelace cards mention it)
"""

from __future__ import annotations

import time
from typing import Any, Optional

from cli_anything.homeassistant.core import (
    history as history_core,
    references as references_core,
    registry as registry_core,
    states as states_core,
)


def inspect_entity(client, entity_id: str, *,
                    include_history: bool = False,
                    history_hours: int = 24,
                    include_references: bool = True,
                    reference_kinds: Optional[list[str]] = None) -> dict:
    """Return a unified record for an entity.

    Always returned:
      - state, attributes, last_changed, last_updated
      - registry row (or None if entity not in registry)
      - device row (or None if entity has no device)
      - area row (or None)

    Optional:
      - history (recent state changes; pass include_history=True)
      - references (where this entity is mentioned across UI-managed config)
    """
    if not entity_id or "." not in entity_id:
        raise ValueError("entity_id must be in 'domain.object' form")

    out: dict[str, Any] = {"entity_id": entity_id}

    # 1) state
    try:
        out["state"] = states_core.get_state(client, entity_id)
    except Exception as exc:
        out["state"] = {"error": str(exc)}

    # 2) registry — pull all and find by id (registry API doesn't have a get-by-id)
    reg_row: Optional[dict] = None
    try:
        for r in registry_core.list_entities(client):
            if r.get("entity_id") == entity_id:
                reg_row = r
                break
    except Exception as exc:
        reg_row = {"error": str(exc)}
    out["registry"] = reg_row

    # 3) device — only if registry row has a device_id
    if isinstance(reg_row, dict) and reg_row.get("device_id"):
        try:
            for d in registry_core.list_devices(client):
                if d.get("id") == reg_row["device_id"]:
                    out["device"] = d
                    break
            else:
                out["device"] = None
        except Exception as exc:
            out["device"] = {"error": str(exc)}
    else:
        out["device"] = None

    # 4) area — derived from registry.area_id OR device.area_id
    area_id = None
    if isinstance(reg_row, dict):
        area_id = reg_row.get("area_id")
    if not area_id and isinstance(out.get("device"), dict):
        area_id = out["device"].get("area_id")
    if area_id:
        try:
            for a in registry_core.list_areas(client):
                if a.get("area_id") == area_id:
                    out["area"] = a
                    break
            else:
                out["area"] = None
        except Exception as exc:
            out["area"] = {"error": str(exc)}
    else:
        out["area"] = None

    # 5) history (opt-in — can be slow on busy entities)
    if include_history:
        try:
            out["history"] = history_core.history(
                client, entity_id=entity_id, hours=history_hours,
            )
        except Exception as exc:
            out["history"] = {"error": str(exc)}

    # 6) references
    if include_references:
        try:
            out["references"] = references_core.find_references(
                client, entity_id,
                include_kinds=set(reference_kinds) if reference_kinds else None,
            )
        except Exception as exc:
            out["references"] = {"error": str(exc)}

    return out
