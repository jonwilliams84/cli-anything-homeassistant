"""Label registry — cross-cutting tags for entities/devices/areas.

WS namespace: `config/label_registry/*`. Each label has:
  label_id, name, icon?, color?, description?.
Labels apply ACROSS area boundaries (e.g. "guest_mode", "presence_sensors",
"critical_uptime") and are easier than maintaining many areas.
"""

from __future__ import annotations

from typing import Any, Optional


def list_labels(client) -> list[dict]:
    data = client.ws_call("config/label_registry/list")
    return list(data) if isinstance(data, list) else []


def find_label(client, ident: str) -> Optional[dict]:
    if not ident:
        return None
    ident_l = ident.lower()
    for l in list_labels(client):
        if l.get("label_id") == ident:
            return l
        if (l.get("name") or "").lower() == ident_l:
            return l
    return None


def create(client, *, name: str,
            color: Optional[str] = None,
            icon: Optional[str] = None,
            description: Optional[str] = None) -> dict:
    if not name:
        raise ValueError("name is required")
    payload: dict[str, Any] = {"name": name}
    if color:        payload["color"] = color
    if icon:         payload["icon"] = icon
    if description:  payload["description"] = description
    return client.ws_call("config/label_registry/create", payload) or {}


def update(client, label_id: str, *,
            name: Optional[str] = None,
            color: Optional[str] = None,
            icon: Optional[str] = None,
            description: Optional[str] = None) -> dict:
    if not label_id:
        raise ValueError("label_id is required")
    payload: dict[str, Any] = {"label_id": label_id}
    if name is not None:        payload["name"] = name
    if color is not None:       payload["color"] = color
    if icon is not None:        payload["icon"] = icon
    if description is not None: payload["description"] = description
    return client.ws_call("config/label_registry/update", payload) or {}


def delete(client, label_id: str) -> Any:
    if not label_id:
        raise ValueError("label_id is required")
    return client.ws_call("config/label_registry/delete",
                            {"label_id": label_id})
