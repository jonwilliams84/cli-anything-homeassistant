"""Scene operations for Home Assistant.

Scenes capture a set of entity states and re-apply them on demand. HA
exposes scene control through the standard service API:

   - POST services/scene/turn_on   — activate a stored scene (the usual case)
   - POST services/scene/apply     — apply an ad-hoc dict of entity states
                                     without persisting it as a scene
   - POST services/scene/create    — persist a new scene from current state
                                     or from a literal entity-state dict
   - POST services/scene/reload    — reload scenes from configuration.yaml

Listing reuses the existing /api/states endpoint (filtered to the scene
domain). There is no dedicated scene-registry WebSocket command in HA core.
"""

from __future__ import annotations

from typing import Any


def list_scenes(client) -> list[dict]:
    """Return every scene currently registered (scene.* entities).

    Each row contains the usual state dict keys (entity_id, state,
    attributes — friendly_name lives under attributes).
    """
    states = client.get("states")
    if not isinstance(states, list):
        return []
    return [s for s in states if isinstance(s, dict)
            and (s.get("entity_id") or "").startswith("scene.")]


def activate(client, entity_id: str, *,
             transition: float | None = None) -> dict:
    """Activate a stored scene — POST services/scene/turn_on.

    ``transition`` — optional fade time in seconds (lights/covers respect it).
    """
    if not entity_id.startswith("scene."):
        raise ValueError(f"expected scene.* entity_id, got {entity_id!r}")

    payload: dict[str, Any] = {"entity_id": entity_id}
    if transition is not None:
        if transition < 0:
            raise ValueError(f"transition must be >= 0, got {transition!r}")
        payload["transition"] = transition

    return client.post("services/scene/turn_on", payload)


def apply(client, *, entities: dict[str, Any],
          transition: float | None = None) -> dict:
    """Apply an ad-hoc set of entity states without persisting a scene.

    ``entities`` — mapping of entity_id → state or {state, attributes...}.
                   At least one entry is required.

    POST services/scene/apply.
    """
    if not entities:
        raise ValueError("entities is required and must be non-empty")
    if not isinstance(entities, dict):
        raise ValueError("entities must be a dict of entity_id → state")

    payload: dict[str, Any] = {"entities": entities}
    if transition is not None:
        if transition < 0:
            raise ValueError(f"transition must be >= 0, got {transition!r}")
        payload["transition"] = transition

    return client.post("services/scene/apply", payload)


def create(client, *, scene_id: str,
           entities: dict[str, Any] | None = None,
           snapshot_entities: list[str] | None = None) -> dict:
    """Persist a new scene — POST services/scene/create.

    ``scene_id`` — the suffix (no ``scene.`` prefix) e.g. ``my_movie_night``.
    ``entities`` — explicit entity_id → state mapping (optional).
    ``snapshot_entities`` — list of entity_ids whose CURRENT state will be
                            captured into the scene (optional).

    At least one of ``entities`` / ``snapshot_entities`` must be provided.
    """
    if not scene_id:
        raise ValueError("scene_id is required and must be non-empty")
    if scene_id.startswith("scene."):
        raise ValueError(
            "scene_id is the suffix only (no 'scene.' prefix); "
            f"got {scene_id!r}"
        )
    if not entities and not snapshot_entities:
        raise ValueError(
            "provide entities=… or snapshot_entities=… (or both)"
        )

    payload: dict[str, Any] = {"scene_id": scene_id}
    if entities:
        payload["entities"] = entities
    if snapshot_entities:
        payload["snapshot_entities"] = list(snapshot_entities)
    return client.post("services/scene/create", payload)


def reload(client) -> dict:
    """Reload scenes from configuration.yaml — POST services/scene/reload."""
    return client.post("services/scene/reload", {})
