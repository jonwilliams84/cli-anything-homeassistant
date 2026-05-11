"""Floor registry — multi-storey topology above areas.

WS namespace: `config/floor_registry/*`. Each floor has:
  floor_id, name, level (int, lower = lower storey), icon?, aliases[].
"""

from __future__ import annotations

from typing import Any, Optional


def list_floors(client) -> list[dict]:
    data = client.ws_call("config/floor_registry/list")
    return list(data) if isinstance(data, list) else []


def find_floor(client, ident: str) -> Optional[dict]:
    if not ident:
        return None
    ident_l = ident.lower()
    for f in list_floors(client):
        if f.get("floor_id") == ident:
            return f
        if (f.get("name") or "").lower() == ident_l:
            return f
    return None


def create(client, *, name: str,
            level: Optional[int] = None,
            icon: Optional[str] = None,
            aliases: Optional[list[str]] = None) -> dict:
    if not name:
        raise ValueError("name is required")
    payload: dict[str, Any] = {"name": name}
    if level is not None:    payload["level"] = level
    if icon:                 payload["icon"] = icon
    if aliases is not None:  payload["aliases"] = aliases
    return client.ws_call("config/floor_registry/create", payload) or {}


def update(client, floor_id: str, *,
            name: Optional[str] = None,
            level: Optional[int] = None,
            icon: Optional[str] = None,
            aliases: Optional[list[str]] = None) -> dict:
    if not floor_id:
        raise ValueError("floor_id is required")
    payload: dict[str, Any] = {"floor_id": floor_id}
    if name is not None:     payload["name"] = name
    if level is not None:    payload["level"] = level
    if icon is not None:     payload["icon"] = icon
    if aliases is not None:  payload["aliases"] = aliases
    return client.ws_call("config/floor_registry/update", payload) or {}


def delete(client, floor_id: str) -> Any:
    if not floor_id:
        raise ValueError("floor_id is required")
    return client.ws_call("config/floor_registry/delete",
                            {"floor_id": floor_id})
