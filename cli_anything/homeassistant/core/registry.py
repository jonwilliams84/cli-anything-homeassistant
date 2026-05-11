"""Area / device / entity / config-entry registries (WebSocket)."""

from __future__ import annotations

from typing import Any


def list_areas(client) -> list[dict]:
    data = client.ws_call("config/area_registry/list")
    return list(data) if isinstance(data, list) else []


def list_devices(client) -> list[dict]:
    data = client.ws_call("config/device_registry/list")
    return list(data) if isinstance(data, list) else []


def list_entities(client) -> list[dict]:
    data = client.ws_call("config/entity_registry/list")
    return list(data) if isinstance(data, list) else []


def list_config_entries(client) -> list[dict]:
    data = client.ws_call("config_entries/get")
    return list(data) if isinstance(data, list) else []


def filter_entities_by_domain(entities: list[dict], domain: str) -> list[dict]:
    return [
        e for e in entities
        if str(e.get("entity_id", "")).startswith(f"{domain}.")
    ]


def filter_devices_by_area(devices: list[dict], area_id: str) -> list[dict]:
    return [d for d in devices if d.get("area_id") == area_id]


def system_health(client) -> Any:
    return client.ws_call("system_health/info")


# ─── entity registry write ops ───────────────────────────────────────────────

_SENTINEL = "__unset__"


def update_entity(client, entity_id: str, *,
                   new_entity_id: str | None = None,
                   name: str | None = None,
                   icon: str | None = None,
                   area_id: str | None = None,
                   labels: list[str] | None = None,
                   aliases: list[str] | None = None,
                   disabled_by: Any = _SENTINEL,
                   hidden_by: Any = _SENTINEL,
                   options: dict | None = None,
                   ) -> dict:
    """Mutate one entity's registry record.

    Pass any field to change; omit to leave alone.

    `disabled_by` / `hidden_by` accept three states:
      - "user"   — disable/hide-by-user
      - None     — clear (enable/un-hide)
      - the default sentinel means "don't touch"
    """
    if not entity_id:
        raise ValueError("entity_id is required")
    payload: dict[str, Any] = {"entity_id": entity_id}
    if new_entity_id is not None: payload["new_entity_id"] = new_entity_id
    if name is not None:          payload["name"] = name
    if icon is not None:          payload["icon"] = icon
    if area_id is not None:       payload["area_id"] = area_id
    if labels is not None:        payload["labels"] = labels
    if aliases is not None:       payload["aliases"] = aliases
    if disabled_by is not _SENTINEL: payload["disabled_by"] = disabled_by
    if hidden_by   is not _SENTINEL: payload["hidden_by"]   = hidden_by
    if options is not None:       payload["options"]      = options
    return client.ws_call("config/entity_registry/update", payload) or {}


def bulk_update_entities(client, *,
                          updates: list[dict],
                          dry_run: bool = False) -> dict:
    """Apply a list of `{entity_id, **fields}` updates.

    Returns {applied: [...], failed: [...], dry_run}.
    """
    applied: list[dict] = []
    failed: list[dict] = []
    for u in updates:
        eid = u.get("entity_id")
        if not eid:
            failed.append({"entity_id": None, "error": "missing entity_id",
                            "fields": u})
            continue
        fields = {k: v for k, v in u.items() if k != "entity_id"}
        if dry_run:
            applied.append({"entity_id": eid, "would_set": fields})
            continue
        try:
            res = update_entity(client, eid, **fields)
            applied.append({"entity_id": eid, "result": res})
        except Exception as exc:
            failed.append({"entity_id": eid, "error": str(exc), "fields": fields})
    return {"applied": applied, "failed": failed, "dry_run": dry_run}


def match_entities(entities: list[dict], *,
                    pattern: str | None = None,
                    domain: str | None = None,
                    area_id: str | None = None,
                    label: str | None = None,
                    integration: str | None = None) -> list[dict]:
    """Filter the entity registry by one or more criteria.

    `pattern` is a regex applied to `entity_id`.
    """
    import re
    rx = re.compile(pattern) if pattern else None
    out: list[dict] = []
    for e in entities:
        eid = e.get("entity_id", "")
        if rx and not rx.search(eid):
            continue
        if domain and not eid.startswith(domain + "."):
            continue
        if area_id and e.get("area_id") != area_id:
            continue
        if label and label not in (e.get("labels") or []):
            continue
        if integration and (e.get("platform") != integration):
            continue
        out.append(e)
    return out


# ─── device registry write ops ───────────────────────────────────────────────

def update_device(client, device_id: str, *,
                   name_by_user: str | None = None,
                   area_id: str | None = None,
                   labels: list[str] | None = None,
                   disabled_by: Any = _SENTINEL,
                   name: str | None = None,
                   ) -> dict:
    """Mutate one device's registry record.

    `name_by_user` is the user-set override; `name` is read-only manufacturer
    metadata for most integrations.
    """
    if not device_id:
        raise ValueError("device_id is required")
    payload: dict[str, Any] = {"device_id": device_id}
    if name_by_user is not None: payload["name_by_user"] = name_by_user
    if name is not None:         payload["name"]         = name
    if area_id is not None:      payload["area_id"]      = area_id
    if labels is not None:       payload["labels"]       = labels
    if disabled_by is not _SENTINEL: payload["disabled_by"] = disabled_by
    return client.ws_call("config/device_registry/update", payload) or {}
