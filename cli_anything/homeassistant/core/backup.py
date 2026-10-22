"""Backup API — snapshot create / list / restore / delete via WebSocket.

HA's backup feature lives behind the WS `backup/*` namespace. The exact set
of message types has evolved (info / details / generate / remove / restore
were added in 2024.x). We use the names current as of 2024.6+; older HA may
require small adjustments.

(`info()` is also exported as `backup_info` for unambiguous `from X import` usage.)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

_LOGGER = logging.getLogger(__name__)


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


def list_agent_ids(client) -> list[str]:
    """Return the id of every configured backup agent (e.g. ``backup.local``).

    HA answers ``backup/agents/info`` with ``{"agents": [{"agent_id": ...}]}``
    on current versions and with plain strings on some older ones, so both
    shapes are accepted. The order is HA's own.
    """
    data = client.ws_call("backup/agents/info") or {}
    agents = data.get("agents") if isinstance(data, dict) else data
    if not isinstance(agents, list):
        return []
    out: list[str] = []
    for agent in agents:
        if isinstance(agent, str):
            out.append(agent)
        elif isinstance(agent, dict):
            aid = agent.get("agent_id") or agent.get("id")
            if aid:
                out.append(str(aid))
    return out


def generate(
    client,
    *,
    name: Optional[str] = None,
    password: Optional[str] = None,
    addons_included: Optional[list[str]] = None,
    folders_included: Optional[list[str]] = None,
    database_included: bool = True,
    agent_ids: Optional[list[str]] = None,
) -> dict:
    """Trigger a backup. Returns the job descriptor.

    HA's ``backup/generate`` schema (2025.1 onwards, unchanged in 2026.10):

      * ``agent_ids`` is REQUIRED — a list of agent ids such as
        ``["backup.local"]``. Omitting it is answered with
        ``required key not provided @ data['agent_ids']``.
      * the recorder database is included/excluded with ``include_database``
        (NOT ``database_included`` — HA rejects the old name as an extra
        key).
      * the addons/folders selections are ``include_addons`` /
        ``include_folders``.

    When ``agent_ids`` is not given, EVERY configured agent is used, which is
    what the HA UI does for a plain "create backup".
    """
    payload: dict[str, Any] = {}
    selected = list(agent_ids) if agent_ids else list_agent_ids(client)
    if not selected:
        raise ValueError(
            "no backup agents are available — HA requires at least one "
            "agent id for backup/generate. Check `backup agents`."
        )
    payload["agent_ids"] = selected
    payload["include_database"] = bool(database_included)
    if addons_included is not None:
        payload["include_addons"] = list(addons_included)
    if folders_included is not None:
        payload["include_folders"] = list(folders_included)
    if name:
        payload["name"] = name
    if password:
        payload["password"] = password
    try:
        return client.ws_call("backup/generate", payload) or {}
    except Exception as exc:  # noqa: BLE001 — re-raised unless it is a schema mismatch
        # HA older than 2025.1 knows neither `agent_ids` nor `include_database`
        # and answers "extra keys not allowed @ data['…']". Retry with the
        # pre-2025 field names for those installs.
        msg = str(exc)
        if "extra keys not allowed" not in msg:
            raise
        legacy = {
            k: v
            for k, v in payload.items()
            if k not in ("agent_ids", "include_database", "include_addons", "include_folders")
        }
        if not database_included:
            legacy["database_included"] = False
        if addons_included is not None:
            legacy["addons_included"] = list(addons_included)
        if folders_included is not None:
            legacy["folders_included"] = list(folders_included)
        _LOGGER.debug(
            "backup/generate rejected the current schema (%s); retrying with %s", msg, legacy
        )
        return client.ws_call("backup/generate", legacy) or {}
        raise


def remove(client, backup_id: str, *, agent_ids: Optional[list[str]] = None) -> dict:
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
        except Exception as exc:  # noqa: BLE001 — try the next msg type
            _LOGGER.debug("backup delete via %s failed: %s", msg_type, exc)
            continue
    raise RuntimeError("backup delete is not supported by this HA version")


def restore(
    client,
    backup_id: str,
    *,
    password: Optional[str] = None,
    restore_database: bool = True,
    restore_folders: Optional[list[str]] = None,
    restore_addons: Optional[list[str]] = None,
    agent_id: Optional[str] = None,
) -> dict:
    """Restore from a backup. HA will restart afterwards. **Destructive.**"""
    if not backup_id:
        raise ValueError("backup_id is required")
    payload: dict[str, Any] = {"backup_id": backup_id}
    if password:
        payload["password"] = password
    if not restore_database:
        payload["restore_database"] = False
    if restore_folders is not None:
        payload["restore_folders"] = restore_folders
    if restore_addons is not None:
        payload["restore_addons"] = restore_addons
    if agent_id:
        payload["agent_id"] = agent_id
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
