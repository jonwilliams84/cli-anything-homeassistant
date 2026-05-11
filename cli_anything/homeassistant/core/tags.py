"""Tag registry — NFC tags + Home Assistant tag IDs.

WS namespace: `tag/list`, `tag/update`. Tags are scanned by HA companion apps
to fire `tag_scanned` events; users typically bind them to scripts/automations.

Tag entities:
  tag_id, name?, description?, last_scanned, last_scanned_by_device_id?.
"""

from __future__ import annotations

from typing import Any, Optional


def list_tags(client) -> list[dict]:
    data = client.ws_call("tag/list")
    return list(data) if isinstance(data, list) else []


def find_tag(client, ident: str) -> Optional[dict]:
    if not ident:
        return None
    ident_l = ident.lower()
    for t in list_tags(client):
        if t.get("id") == ident or t.get("tag_id") == ident:
            return t
        if (t.get("name") or "").lower() == ident_l:
            return t
    return None


def update(client, tag_id: str, *,
            name: Optional[str] = None,
            description: Optional[str] = None) -> dict:
    if not tag_id:
        raise ValueError("tag_id is required")
    payload: dict[str, Any] = {"tag_id": tag_id}
    if name is not None:        payload["name"] = name
    if description is not None: payload["description"] = description
    return client.ws_call("tag/update", payload) or {}
