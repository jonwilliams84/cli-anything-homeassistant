"""Update entity management — install / skip / clear-skipped.

Each upgradeable thing in HA (Core, add-ons, integrations, devices, custom
components) becomes an `update.*` entity. Its state is `on` when an update
is available, `off` otherwise. Three services drive the lifecycle:

  - `update.install`         — install a specific or latest version
  - `update.skip`            — mark a version as deliberately skipped
  - `update.clear_skipped`   — un-skip (re-show the update as pending)
"""

from __future__ import annotations

from typing import Any, Optional

from cli_anything.homeassistant.core import services as services_core
from cli_anything.homeassistant.core import states as states_core


def list_updates(client, *, available_only: bool = True) -> list[dict]:
    """Return one row per update.* entity with key attributes.

    Each row: {entity_id, state, title, installed_version, latest_version,
                in_progress, release_summary, skipped_version}.
    """
    rows = []
    for s in states_core.list_states(client, domain="update"):
        eid = s.get("entity_id", "")
        if not eid.startswith("update."):
            continue
        state = s.get("state")
        if available_only and state != "on":
            continue
        attrs = s.get("attributes", {}) or {}
        rows.append({
            "entity_id": eid,
            "state": state,
            "title": attrs.get("title"),
            "installed_version": attrs.get("installed_version"),
            "latest_version": attrs.get("latest_version"),
            "in_progress": attrs.get("in_progress"),
            "skipped_version": attrs.get("skipped_version"),
            "release_summary": attrs.get("release_summary"),
            "release_url": attrs.get("release_url"),
        })
    return rows


def install(client, entity_id: str, *,
            version: Optional[str] = None,
            backup: bool = False) -> Any:
    """Install an update on one update.* entity. `version=None` installs latest."""
    if not entity_id.startswith("update."):
        raise ValueError(f"expected update.* entity_id, got {entity_id!r}")
    data: dict[str, Any] = {}
    if version: data["version"] = version
    if backup:  data["backup"] = True
    return services_core.call_service(
        client, "update", "install",
        service_data=data or None,
        target={"entity_id": entity_id},
    )


def skip(client, entity_id: str) -> Any:
    """Mark the current available version as skipped."""
    if not entity_id.startswith("update."):
        raise ValueError(f"expected update.* entity_id, got {entity_id!r}")
    return services_core.call_service(
        client, "update", "skip",
        target={"entity_id": entity_id},
    )


def clear_skipped(client, entity_id: str) -> Any:
    """Un-skip a previously skipped update."""
    if not entity_id.startswith("update."):
        raise ValueError(f"expected update.* entity_id, got {entity_id!r}")
    return services_core.call_service(
        client, "update", "clear_skipped",
        target={"entity_id": entity_id},
    )
