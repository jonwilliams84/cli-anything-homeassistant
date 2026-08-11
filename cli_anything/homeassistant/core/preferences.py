"""Instance-level preferences nothing could read: AI Task, HTTP config,
entity-id naming, and per-entity recorder options.

WHY THESE FOUR TOGETHER
    They are all small `get`/`set` pairs on stored preferences that shape how
    the rest of Home Assistant behaves, and every one of them was invisible to
    this harness. They are grouped by that shape rather than by subject,
    because each alone is two functions and a module per pair would be noise.

WHAT EACH ONE EXPLAINS

    ai_task/preferences  — which AI Task entity serves `ai_task.generate_data`
        and `ai_task.generate_image` when a call does not name one. A call that
        "went to the wrong model" is nearly always this, and there was no way
        to read it.

    http/config          — HA's stored HTTP configuration, and it has a
        STABLE/PENDING split: `active_config_type` says which is live, and a
        pending config exists until it is promoted. A CORS or trusted-proxy
        change that "did not take" is visible here and nowhere else.

    config/entity_registry/settings — `entity_id_parts`: the rule HA uses to
        build an automatic entity id from device and entity name. `None` means
        the default. Paired with `get_automatic_entity_ids`, which answers what
        HA WOULD call an entity — the check to run before renaming anything.

    recorder/entity_options — per-entity `recording_disabled_by`. An entity
        excluded from the recorder has no history and no statistics, and every
        history command in this harness would report that as simply "no data".
        Measured on a live instance: `sun.sun` comes back
        `{"recording_disabled_by": "user"}` — which is the correct explanation
        for an empty history that otherwise looks like a bug.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

_LOGGER = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────── AI Task

def ai_task_get(client) -> dict:
    """Which AI Task entity serves data generation and image generation."""
    data = client.ws_call("ai_task/preferences/get") or {}
    return {
        "gen_data_entity_id": data.get("gen_data_entity_id"),
        "gen_image_entity_id": data.get("gen_image_entity_id"),
        "note": (
            "These are the defaults used when an ai_task.* service call names no "
            "entity. A job that reached the wrong model is usually this."
        ),
    }


def ai_task_set(
    client,
    *,
    gen_data_entity_id: Optional[str] = None,
    gen_image_entity_id: Optional[str] = None,
) -> dict:
    """Set one or both AI Task defaults.

    Only the keys given are sent: HA's schema marks both optional and omitting
    one leaves it alone, so passing `None` explicitly would be a different
    operation (clearing it) than not passing it at all.
    """
    payload: dict[str, Any] = {}
    if gen_data_entity_id is not None:
        payload["gen_data_entity_id"] = gen_data_entity_id
    if gen_image_entity_id is not None:
        payload["gen_image_entity_id"] = gen_image_entity_id
    if not payload:
        raise ValueError(
            "Nothing to set. Pass --gen-data and/or --gen-image. (To CLEAR one, "
            "pass the empty string.)"
        )
    before = ai_task_get(client)
    client.ws_call("ai_task/preferences/set", payload)
    after = ai_task_get(client)
    return {"before": before, "after": after, "sent": payload}


# ─────────────────────────────────────────────────────────────── HTTP config

def http_config(client) -> dict:
    """HA's stored HTTP configuration, stable and pending.

    `active_config_type` is the field to read: a pending config is stored and
    NOT in force until promoted, so a setting that "did not take" is usually
    sitting in `pending`.
    """
    data = client.ws_call("http/config") or {}
    active = data.get("active_config_type")
    return {
        "active_config_type": active,
        "active": data.get(active) if active else None,
        "stable": data.get("stable"),
        "pending": data.get("pending"),
        "default": data.get("default"),
        "has_pending": bool(data.get("pending")),
        "raw": data,
    }


# ──────────────────────────────────────────────────── entity-id naming rules

def entity_id_settings(client) -> dict:
    """The registry's `entity_id_parts` rule. `None` means HA's default."""
    data = client.ws_call("config/entity_registry/settings/get") or {}
    parts = data.get("entity_id_parts")
    return {
        "entity_id_parts": parts,
        "is_default": parts is None,
        "meaning": (
            "Which name parts HA joins to build an automatic entity_id. None is "
            "the built-in default; a list must contain both 'device' and 'entity'."
        ),
    }


def set_entity_id_settings(client, entity_id_parts: Optional[list[str]]) -> dict:
    """Change the automatic entity-id naming rule instance-wide.

    HA's own schema requires the list to contain BOTH `device` and `entity`, and
    to have no duplicates; that is checked server-side and the error is clear,
    so it is not duplicated here. `None` restores the default.
    """
    before = entity_id_settings(client)
    result = client.ws_call(
        "config/entity_registry/settings/update", {"entity_id_parts": entity_id_parts}
    )
    return {
        "before": before.get("entity_id_parts"),
        "after": (result or {}).get("entity_id_parts"),
        "scope": "instance-wide; affects entity_ids HA generates from now on",
    }


def automatic_entity_ids(client, entity_ids: list[str]) -> dict:
    """What HA WOULD call these entities, by its own naming rules.

    Run this before a rename: a `None` answer means HA has no automatic id for
    that entity — typically because it is not in the registry, or its
    integration supplies no name to build one from. Measured: `sun.sun` -> None.
    """
    if not entity_ids:
        raise ValueError("Pass at least one entity_id.")
    result = client.ws_call(
        "config/entity_registry/get_automatic_entity_ids", {"entity_ids": entity_ids}
    ) or {}
    rows = []
    for eid in entity_ids:
        suggested = result.get(eid)
        rows.append(
            {
                "entity_id": eid,
                "automatic_entity_id": suggested,
                "matches_current": suggested == eid,
                # None is an ANSWER, not a lookup failure.
                "has_automatic_id": suggested is not None,
            }
        )
    return {"count": len(rows), "entities": rows}


# ────────────────────────────────────────────────────── recorder per-entity

def recorder_entity_options(client, entity_id: str) -> dict:
    """Whether the recorder is storing this entity at all.

    `recording_disabled_by` non-null means there is NO history and NO long-term
    statistics for it — which every history command in this harness would
    otherwise report as an empty result indistinguishable from a quiet entity.
    """
    data = client.ws_call("recorder/entity_options/get", {"entity_id": entity_id}) or {}
    disabled_by = data.get("recording_disabled_by")
    return {
        "entity_id": entity_id,
        "recording_disabled_by": disabled_by,
        "is_recorded": disabled_by is None,
        "explains_empty_history": disabled_by is not None,
    }
