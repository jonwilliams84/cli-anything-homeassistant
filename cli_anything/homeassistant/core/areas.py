"""Area registry — list / create / update / delete.

WS namespace: `config/area_registry/*`. Each area has:
  area_id, name, floor_id?, icon?, picture?, aliases[], labels[].
"""

from __future__ import annotations

from typing import Any, Optional


def list_areas(client) -> list[dict]:
    data = client.ws_call("config/area_registry/list")
    return list(data) if isinstance(data, list) else []


def find_area(client, ident: str) -> Optional[dict]:
    """Find an area by area_id OR by case-insensitive name match."""
    if not ident:
        return None
    ident_l = ident.lower()
    for a in list_areas(client):
        if a.get("area_id") == ident:
            return a
        if (a.get("name") or "").lower() == ident_l:
            return a
    return None


def create(client, *, name: str,
            floor_id: Optional[str] = None,
            icon: Optional[str] = None,
            picture: Optional[str] = None,
            aliases: Optional[list[str]] = None,
            labels: Optional[list[str]] = None) -> dict:
    if not name:
        raise ValueError("name is required")
    payload: dict[str, Any] = {"name": name}
    if floor_id: payload["floor_id"] = floor_id
    if icon:     payload["icon"] = icon
    if picture:  payload["picture"] = picture
    if aliases is not None: payload["aliases"] = aliases
    if labels is not None:  payload["labels"] = labels
    return client.ws_call("config/area_registry/create", payload) or {}


def update(client, area_id: str, *,
            name: Optional[str] = None,
            floor_id: Optional[str] = None,
            icon: Optional[str] = None,
            picture: Optional[str] = None,
            aliases: Optional[list[str]] = None,
            labels: Optional[list[str]] = None) -> dict:
    if not area_id:
        raise ValueError("area_id is required")
    payload: dict[str, Any] = {"area_id": area_id}
    if name is not None:     payload["name"] = name
    if floor_id is not None: payload["floor_id"] = floor_id
    if icon is not None:     payload["icon"] = icon
    if picture is not None:  payload["picture"] = picture
    if aliases is not None:  payload["aliases"] = aliases
    if labels is not None:   payload["labels"] = labels
    return client.ws_call("config/area_registry/update", payload) or {}


def delete(client, area_id: str) -> Any:
    if not area_id:
        raise ValueError("area_id is required")
    return client.ws_call("config/area_registry/delete",
                            {"area_id": area_id})
