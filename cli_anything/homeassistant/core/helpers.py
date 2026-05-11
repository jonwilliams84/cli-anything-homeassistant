"""Input-helper convenience routines.

`input_select.set_options` updates in-memory state but in some HA versions
doesn't reliably flush to `.storage/input_select` — so a restart loses the
change. These helpers expose a small, idempotent layer:

  - `input_select_set_options(client, entity_id, options)` — calls the
    service and reads back the in-memory result.
  - `input_select_sync(client, src, dst)` — copy the options list from
    one input_select to another (state stays per-helper).

For durable storage edits, the build script directly patches
`.storage/input_select` on the host; this module focuses on the runtime
side of things.
"""

from __future__ import annotations


def _get_state(client, entity_id: str) -> dict:
    states = client.get(f"states/{entity_id}")
    if not isinstance(states, dict) or "attributes" not in states:
        raise ValueError(f"entity {entity_id!r} not found or missing attributes")
    return states


def input_select_set_options(client, entity_id: str, options: list[str]) -> dict:
    """Set the options list on an input_select via service call.

    Returns the entity's state dict after the change.
    """
    if not entity_id.startswith("input_select."):
        raise ValueError(f"expected input_select.* entity_id, got {entity_id!r}")
    if not isinstance(options, list) or not all(isinstance(o, str) for o in options):
        raise ValueError("options must be a list of strings")
    client.post("services/input_select/set_options", {
        "entity_id": entity_id,
        "options": options,
    })
    return _get_state(client, entity_id)


def input_select_select(client, entity_id: str, option: str) -> dict:
    """Set the current selection on an input_select."""
    client.post("services/input_select/select_option", {
        "entity_id": entity_id,
        "option": option,
    })
    return _get_state(client, entity_id)


def input_select_create(client, name: str, options: list[str], *,
                          icon: str | None = None,
                          initial: str | None = None) -> dict:
    """Create a NEW input_select helper at runtime.

    Uses HA's storage-collection WS command (``input_select/create``).
    The new helper is registered in `.storage/input_select` immediately
    and survives restart — so this is the right thing to call when
    provisioning a new helper from a script.

    Returns the created helper's record (with ``id``).
    """
    if not name:
        raise ValueError("name is required")
    if not isinstance(options, list) or not options:
        raise ValueError("options must be a non-empty list")
    payload: dict = {"name": name, "options": list(options)}
    if icon:
        payload["icon"] = icon
    if initial:
        payload["initial"] = initial
    return client.ws_call("input_select/create", payload)


def input_select_sync(client, src_entity_id: str, dst_entity_id: str,
                       *, fallback: str = "Auto") -> dict:
    """Copy the OPTIONS list from src to dst input_select. State is left alone.

    If the destination's current state isn't in the new options list,
    selects ``fallback`` first (or the first option if ``fallback`` is
    missing) so the helper isn't stranded in an unknown value.

    Returns ``{"changed": bool, "src_options": [...], "dst_state": "..."}``.
    """
    src = _get_state(client, src_entity_id)
    dst = _get_state(client, dst_entity_id)
    src_opts = src["attributes"].get("options", [])
    dst_opts = dst["attributes"].get("options", [])
    if src_opts == dst_opts:
        return {"changed": False, "src_options": src_opts,
                "dst_state": dst.get("state")}
    dst_state = dst.get("state")
    if dst_state not in src_opts:
        choose = fallback if fallback in src_opts else (src_opts[0] if src_opts else None)
        if choose is not None:
            input_select_select(client, dst_entity_id, choose)
    input_select_set_options(client, dst_entity_id, src_opts)
    after = _get_state(client, dst_entity_id)
    return {
        "changed": True,
        "src_options": src_opts,
        "dst_state": after.get("state"),
    }
