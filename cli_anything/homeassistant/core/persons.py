"""Person registry — list / create / update / delete.

WS namespace: `person/*`. A person ties one or more `device_tracker.*` entities
together with a profile picture and user account.
"""

from __future__ import annotations

from typing import Any, Optional


def _envelope(data: Any) -> list[dict]:
    """`person/list` returns {storage_collection: [...], config_collection: [...]} —
    merge both lists into a flat one."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # New shape: {storage: [...], config: [...]} or storage_collection/config_collection
        for k in ("storage", "storage_collection", "config", "config_collection"):
            v = data.get(k)
            if isinstance(v, list):
                # storage and config can both exist; concat preserving source
                pass
        out: list[dict] = []
        for k in ("storage", "storage_collection"):
            v = data.get(k)
            if isinstance(v, list):
                out.extend({**p, "_source": "storage"} for p in v)
        for k in ("config", "config_collection"):
            v = data.get(k)
            if isinstance(v, list):
                out.extend({**p, "_source": "config"} for p in v)
        if out:
            return out
        # Fallback: maybe { persons: [...] }
        if isinstance(data.get("persons"), list):
            return list(data["persons"])
    return []


def list_persons(client) -> list[dict]:
    return _envelope(client.ws_call("person/list"))


def find_person(client, ident: str) -> Optional[dict]:
    if not ident:
        return None
    ident_l = ident.lower()
    for p in list_persons(client):
        if p.get("id") == ident:
            return p
        if (p.get("name") or "").lower() == ident_l:
            return p
    return None


def create(client, *, name: str,
            user_id: Optional[str] = None,
            device_trackers: Optional[list[str]] = None,
            picture: Optional[str] = None) -> dict:
    if not name:
        raise ValueError("name is required")
    payload: dict[str, Any] = {"name": name}
    if user_id:               payload["user_id"] = user_id
    if device_trackers is not None: payload["device_trackers"] = device_trackers
    if picture:               payload["picture"] = picture
    return client.ws_call("person/create", payload) or {}


def update(client, person_id: str, *,
            name: Optional[str] = None,
            user_id: Optional[str] = None,
            device_trackers: Optional[list[str]] = None,
            picture: Optional[str] = None) -> dict:
    if not person_id:
        raise ValueError("person_id is required")
    payload: dict[str, Any] = {"person_id": person_id}
    if name is not None:               payload["name"] = name
    if user_id is not None:            payload["user_id"] = user_id
    if device_trackers is not None:    payload["device_trackers"] = device_trackers
    if picture is not None:            payload["picture"] = picture
    return client.ws_call("person/update", payload) or {}


def delete(client, person_id: str) -> Any:
    if not person_id:
        raise ValueError("person_id is required")
    return client.ws_call("person/delete", {"person_id": person_id})
