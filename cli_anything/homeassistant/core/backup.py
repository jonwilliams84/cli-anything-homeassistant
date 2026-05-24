"""Backup API — snapshot create / list / restore / delete via WebSocket.

HA's backup feature lives behind the WS `backup/*` namespace. The exact set
of message types has evolved (info / details / generate / remove / restore
were added in 2024.x). We use the names current as of 2024.6+; older HA may
require small adjustments.

(`info()` is also exported as `backup_info` for unambiguous `from X import` usage.)
"""

from __future__ import annotations

from typing import Any, Optional


def _enrich(b: dict) -> dict:
    """Promote per-agent `size` / `protected` to top-level fields.

    HA stores ``size`` and ``protected`` inside ``agents[agent_id]`` because
    the same logical backup can live on multiple agents (local, network,
    cloud) at independent sizes. For most callers — list views, audit
    scripts — the top-level summary is what's actually wanted. This adds:

      * ``size_bytes`` — sum of every agent's size (None when no agent has
        a known size yet)
      * ``agent_ids``  — list of agents holding this backup
      * ``protected``  — True if any agent reports protected
    """
    if not isinstance(b, dict):
        return b
    agents = b.get("agents") or {}
    sizes = [a.get("size") for a in agents.values() if a.get("size") is not None]
    out = dict(b)
    out["size_bytes"] = sum(sizes) if sizes else None
    out["agent_ids"] = list(agents.keys())
    out["protected"] = any(a.get("protected") for a in agents.values())
    return out


def info(client) -> dict:
    """Return overall backup state: list of backups, in-flight job, last completed.

    Each backup in ``backups`` is enriched with top-level ``size_bytes``,
    ``agent_ids``, and ``protected`` for the common case (HA only exposes
    these per-agent in the raw payload).
    """
    data = client.ws_call("backup/info") or {}
    if not isinstance(data, dict):
        return {"raw": data}
    if isinstance(data.get("backups"), list):
        data = dict(data)
        data["backups"] = [_enrich(b) for b in data["backups"]]
    return data


def list_backups(client) -> list[dict]:
    """Flatten `info()['backups']` for table display (enriched)."""
    data = info(client)
    backups = data.get("backups") if isinstance(data, dict) else None
    return backups if isinstance(backups, list) else []


def details(client, backup_id: str) -> dict:
    """Full record for one backup (agents it lives on, size, content, etc.).

    Enriched the same way as :func:`info` — top-level ``size_bytes``,
    ``agent_ids``, and ``protected`` are promoted from the per-agent dict.
    """
    if not backup_id:
        raise ValueError("backup_id is required")
    # Newer HA: backup/details takes backup_id; older took slug
    try:
        d = client.ws_call("backup/details", {"backup_id": backup_id}) or {}
    except Exception:
        d = client.ws_call("backup/details", {"slug": backup_id}) or {}
    # `backup/details` returns {backup: {...}} on some HA versions, a
    # flat dict on others. Enrich whichever shape is returned.
    if isinstance(d, dict) and "backup" in d and isinstance(d["backup"], dict):
        d = dict(d)
        d["backup"] = _enrich(d["backup"])
        return d
    return _enrich(d)


def generate(client, *, name: Optional[str] = None,
              password: Optional[str] = None,
              addons_included: Optional[list[str]] = None,
              folders_included: Optional[list[str]] = None,
              database_included: bool = True,
              agent_ids: Optional[list[str]] = None) -> dict:
    """Trigger a backup. Returns the job descriptor.

    `agent_ids` is for HA 2024.7+'s multi-agent backups (local, network, etc.).
    Older HA installs can leave it unset.
    """
    payload: dict[str, Any] = {}
    if name:                payload["name"] = name
    if password:            payload["password"] = password
    if addons_included is not None:   payload["addons_included"] = addons_included
    if folders_included is not None:  payload["folders_included"] = folders_included
    if not database_included:         payload["database_included"] = False
    if agent_ids:           payload["agent_ids"] = agent_ids
    return client.ws_call("backup/generate", payload) or {}


def remove(client, backup_id: str, *,
            agent_ids: Optional[list[str]] = None) -> dict:
    """Delete a backup. With `agent_ids` deletes only those agent copies."""
    if not backup_id:
        raise ValueError("backup_id is required")
    payload: dict[str, Any] = {"backup_id": backup_id}
    if agent_ids:
        payload["agent_ids"] = agent_ids
    # Newer HA uses backup/delete; some versions are backup/remove.
    for msg_type in ("backup/delete", "backup/remove"):
        try:
            return client.ws_call(msg_type, payload) or {}
        except Exception:
            continue
    raise RuntimeError("backup delete is not supported by this HA version")


def restore(client, backup_id: str, *,
             password: Optional[str] = None,
             restore_database: bool = True,
             restore_folders: Optional[list[str]] = None,
             restore_addons: Optional[list[str]] = None,
             agent_id: Optional[str] = None) -> dict:
    """Restore from a backup. HA will restart afterwards. **Destructive.**"""
    if not backup_id:
        raise ValueError("backup_id is required")
    payload: dict[str, Any] = {"backup_id": backup_id}
    if password:                payload["password"] = password
    if not restore_database:    payload["restore_database"] = False
    if restore_folders is not None: payload["restore_folders"] = restore_folders
    if restore_addons is not None:  payload["restore_addons"] = restore_addons
    if agent_id:                payload["agent_id"] = agent_id
    return client.ws_call("backup/restore", payload) or {}


def agents_info(client) -> list[dict]:
    """List the configured backup storage agents (local, cloud, network, …)."""
    data = client.ws_call("backup/agents/info") or {}
    agents = data.get("agents") if isinstance(data, dict) else None
    return agents if isinstance(agents, list) else []


def config_info(client) -> dict:
    """Read the backup automation/schedule configuration."""
    return client.ws_call("backup/config/info") or {}


backup_info = info
