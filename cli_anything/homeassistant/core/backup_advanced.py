"""Backup advanced — multi-agent, config, and restore helpers via WebSocket.

Complements ``cli_anything.homeassistant.core.backup`` (which covers
``backup/info``, ``backup/generate``, ``backup/remove``, and basic
``backup/restore``).  This module exposes keyword-only signatures aligned with
the HA 2024.7+ WS API and adds config management + decrypt-capability checks.

WS commands wrapped here
------------------------
backup/details
backup/delete
backup/restore
backup/generate_with_automatic_settings
backup/agents/info
backup/config/info
backup/config/update
backup/can_decrypt_on_download
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _require_nonempty(value: str, name: str) -> None:
    """Raise ValueError when *value* is falsy (None or empty string)."""
    if not value:
        raise ValueError(f"{name} must be a non-empty string")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def details(client, *, backup_id: str) -> dict:
    """Return full metadata for one backup including per-agent availability.

    Args:
        client:    HA WebSocket client.
        backup_id: Unique backup identifier.

    Returns:
        dict with ``backup`` (metadata) and ``agent_errors`` keys.

    Raises:
        ValueError: if *backup_id* is empty.
    """
    _require_nonempty(backup_id, "backup_id")
    result = client.ws_call("backup/details", {"backup_id": backup_id})
    return result if isinstance(result, dict) else {}


def delete(client, *, backup_id: str) -> dict:
    """Delete a backup across all agents.

    Unlike ``backup.remove`` this function only uses the canonical
    ``backup/delete`` message type introduced in HA 2024.6 and does not fall
    back to ``backup/remove``.

    Args:
        client:    HA WebSocket client.
        backup_id: Unique backup identifier.

    Returns:
        dict with an ``agent_errors`` key (empty on full success).

    Raises:
        ValueError: if *backup_id* is empty.
    """
    _require_nonempty(backup_id, "backup_id")
    result = client.ws_call("backup/delete", {"backup_id": backup_id})
    return result if isinstance(result, dict) else {}


def restore(
    client,
    *,
    backup_id: str,
    agent_id: str,
    password: str | None = None,
    restore_addons: list[str] | None = None,
    restore_database: bool = True,
    restore_folders: list[str] | None = None,
    restore_homeassistant: bool = True,
) -> dict:
    """Restore Home Assistant from a backup.  **Destructive — HA will restart.**

    Args:
        client:               HA WebSocket client.
        backup_id:            Unique backup identifier.
        agent_id:             Storage agent that holds the backup file.
        password:             Decryption password (omit if unencrypted).
        restore_addons:       Subset of add-ons to restore; ``None`` = all.
        restore_database:     Whether to restore the database (default True).
        restore_folders:      Subset of folders to restore; ``None`` = all.
        restore_homeassistant: Whether to restore the HA core (default True).

    Returns:
        Empty dict on success (HA sends no payload for this command).

    Raises:
        ValueError: if *backup_id* or *agent_id* is empty.
    """
    _require_nonempty(backup_id, "backup_id")
    _require_nonempty(agent_id, "agent_id")

    payload: dict[str, Any] = {
        "backup_id": backup_id,
        "agent_id": agent_id,
        "restore_database": restore_database,
        "restore_homeassistant": restore_homeassistant,
    }
    if password is not None:
        payload["password"] = password
    if restore_addons is not None:
        payload["restore_addons"] = restore_addons
    if restore_folders is not None:
        payload["restore_folders"] = restore_folders

    result = client.ws_call("backup/restore", payload)
    return result if isinstance(result, dict) else {}


def generate_with_automatic_settings(client) -> dict:
    """Trigger a backup using the stored automatic-backup configuration.

    HA uses the schedule/agent/inclusion settings persisted via
    ``backup/config/update`` to decide what to back up and where.

    Args:
        client: HA WebSocket client.

    Returns:
        dict describing the initiated backup job.
    """
    result = client.ws_call("backup/generate_with_automatic_settings")
    return result if isinstance(result, dict) else {}


def list_agents(client) -> list[dict]:
    """Return the list of available backup agents (local, cloud, network, …).

    Args:
        client: HA WebSocket client.

    Returns:
        List of agent dicts, each containing at least ``agent_id``.
    """
    data = client.ws_call("backup/agents/info")
    if isinstance(data, dict):
        agents = data.get("agents")
        return agents if isinstance(agents, list) else []
    return []


def get_config(client) -> dict:
    """Return the current backup automation / schedule configuration.

    Args:
        client: HA WebSocket client.

    Returns:
        dict with a ``config`` key containing the full configuration blob.
    """
    result = client.ws_call("backup/config/info")
    return result if isinstance(result, dict) else {}


def update_config(
    client,
    *,
    create_backup: dict | None = None,
    retention: dict | None = None,
    schedule: dict | None = None,
    last_attempted_automatic_backup: str | None = None,
    last_completed_automatic_backup: str | None = None,
    automatic_backups_configured: bool | None = None,
) -> dict:
    """Update the backup automation configuration.

    At least one keyword argument must be supplied.

    Args:
        client:                            HA WebSocket client.
        create_backup:                     Dict of backup-creation settings
                                           (agent_ids, include_*, name, password).
        retention:                         Dict with ``copies`` and/or ``days``.
        schedule:                          Dict with ``state`` key (e.g. ``daily``).
        last_attempted_automatic_backup:   ISO-8601 timestamp string.
        last_completed_automatic_backup:   ISO-8601 timestamp string.
        automatic_backups_configured:      Whether automatic backups are enabled.

    Returns:
        Empty dict on success.

    Raises:
        ValueError: if no keyword arguments are provided.
    """
    payload: dict[str, Any] = {}
    if create_backup is not None:
        payload["create_backup"] = create_backup
    if retention is not None:
        payload["retention"] = retention
    if schedule is not None:
        payload["schedule"] = schedule
    if last_attempted_automatic_backup is not None:
        payload["last_attempted_automatic_backup"] = last_attempted_automatic_backup
    if last_completed_automatic_backup is not None:
        payload["last_completed_automatic_backup"] = last_completed_automatic_backup
    if automatic_backups_configured is not None:
        payload["automatic_backups_configured"] = automatic_backups_configured

    if not payload:
        raise ValueError(
            "update_config requires at least one field to update"
        )

    result = client.ws_call("backup/config/update", payload)
    return result if isinstance(result, dict) else {}


def can_decrypt_on_download(
    client,
    *,
    backup_id: str,
    agent_id: str,
    password: str,
) -> dict:
    """Check whether a password-protected backup can be decrypted on download.

    Args:
        client:    HA WebSocket client.
        backup_id: Unique backup identifier.
        agent_id:  Storage agent that holds the backup file.
        password:  Candidate decryption password.

    Returns:
        dict with a ``can_decrypt`` boolean key.

    Raises:
        ValueError: if any of *backup_id*, *agent_id*, or *password* is empty.
    """
    _require_nonempty(backup_id, "backup_id")
    _require_nonempty(agent_id, "agent_id")
    _require_nonempty(password, "password")

    result = client.ws_call(
        "backup/can_decrypt_on_download",
        {"backup_id": backup_id, "agent_id": agent_id, "password": password},
    )
    return result if isinstance(result, dict) else {}
