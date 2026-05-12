"""Todo list CRUD operations for Home Assistant.

Home Assistant exposes todo list operations via two mechanisms:

1. **WebSocket commands** — used for read/query/reorder operations:
   - ``todo/item/list``  — list items in a todo list
   - ``todo/item/move``  — reorder an item within a list

2. **Service calls** — used for mutations (POST services/<domain>/<service>):
   - ``todo/add_item``               — create a new todo item
   - ``todo/update_item``            — rename/reschedule/complete an item
   - ``todo/remove_item``            — delete one or more items by uid or summary
   - ``todo/remove_completed_items`` — bulk-delete all completed items

Items in the list response each contain: uid, summary, status, due, description.
The ``status`` field takes values ``needs_action`` or ``completed`` (RFC 5545 VTODO).
"""

from __future__ import annotations

_VALID_STATUSES = {"needs_action", "completed"}


def _check_entity_id(entity_id: str) -> None:
    """Validate that entity_id belongs to the todo domain."""
    if not entity_id.startswith("todo."):
        raise ValueError(
            f"expected todo.* entity_id, got {entity_id!r}"
        )


# ════════════════════════════════════════════════════════════════════════
# list_items — WS todo/item/list
# ════════════════════════════════════════════════════════════════════════

def list_items(client, entity_id: str) -> list[dict]:
    """Return the list of items in a todo list entity.

    Each item is a dict with keys: uid, summary, status, due, description.
    Uses WS command ``todo/item/list``.
    """
    _check_entity_id(entity_id)
    result = client.ws_call("todo/item/list", {"entity_id": entity_id})
    # HA returns {"items": [...]}; unwrap gracefully.
    if isinstance(result, dict) and "items" in result:
        return result["items"]
    if isinstance(result, list):
        return result
    return []


# ════════════════════════════════════════════════════════════════════════
# add_item — service todo/add_item
# ════════════════════════════════════════════════════════════════════════

def add_item(client, entity_id: str, *,
             summary: str,
             due: str | None = None,
             description: str | None = None) -> dict:
    """Add a new item to a todo list.

    ``summary`` — the item's display text (required, non-empty).
    ``due``     — ISO date string (YYYY-MM-DD) or datetime, optional.
    ``description`` — free-text note, optional.

    Uses service call POST services/todo/add_item.
    """
    _check_entity_id(entity_id)
    if not summary:
        raise ValueError("summary must be a non-empty string")
    payload: dict = {"entity_id": entity_id, "item": summary}
    if due is not None:
        payload["due"] = due
    if description is not None:
        payload["description"] = description
    return client.post("services/todo/add_item", payload)


# ════════════════════════════════════════════════════════════════════════
# update_item — service todo/update_item
# ════════════════════════════════════════════════════════════════════════

def update_item(client, entity_id: str, *,
                item: str,
                rename: str | None = None,
                status: str | None = None,
                due: str | None = None,
                description: str | None = None) -> dict:
    """Update an existing todo item.

    ``item``   — current summary text OR uid that identifies the item.
    ``rename`` — new summary text, optional.
    ``status`` — ``needs_action`` or ``completed``, optional.
    ``due``    — new due date/datetime string, optional.
    ``description`` — new note text, optional.

    At least one of rename/status/due/description must be supplied.
    Uses service call POST services/todo/update_item.
    """
    _check_entity_id(entity_id)
    if not item:
        raise ValueError("item (current summary or uid) must be non-empty")
    if status is not None and status not in _VALID_STATUSES:
        raise ValueError(
            f"status must be one of {sorted(_VALID_STATUSES)}, got {status!r}"
        )
    if rename is None and status is None and due is None and description is None:
        raise ValueError(
            "at least one of rename/status/due/description must be supplied"
        )
    payload: dict = {"entity_id": entity_id, "item": item}
    if rename is not None:
        payload["rename"] = rename
    if status is not None:
        payload["status"] = status
    if due is not None:
        payload["due"] = due
    if description is not None:
        payload["description"] = description
    return client.post("services/todo/update_item", payload)


# ════════════════════════════════════════════════════════════════════════
# remove_item — service todo/remove_item
# ════════════════════════════════════════════════════════════════════════

def remove_item(client, entity_id: str, *,
                item: str | list[str]) -> dict:
    """Remove one or more items from a todo list.

    ``item`` — a single uid/summary string, or a list of such strings.
    Uses service call POST services/todo/remove_item.
    """
    _check_entity_id(entity_id)
    if not item:
        raise ValueError("item must be a non-empty string or list")
    if isinstance(item, list) and not all(isinstance(i, str) and i for i in item):
        raise ValueError("item list must contain non-empty strings")
    return client.post("services/todo/remove_item",
                       {"entity_id": entity_id, "item": item})


# ════════════════════════════════════════════════════════════════════════
# move_item — WS todo/item/move
# ════════════════════════════════════════════════════════════════════════

def move_item(client, entity_id: str, *,
              uid: str,
              previous_uid: str | None = None) -> dict:
    """Move a todo item to a new position in the list.

    ``uid``          — the uid of the item to move (required).
    ``previous_uid`` — uid of the item that will precede the moved item.
                       Pass None (default) to move the item to the top.

    Uses WS command ``todo/item/move``.
    """
    _check_entity_id(entity_id)
    if not uid:
        raise ValueError("uid must be a non-empty string")
    payload: dict = {"entity_id": entity_id, "uid": uid}
    if previous_uid is not None:
        payload["previous_uid"] = previous_uid
    return client.ws_call("todo/item/move", payload)


# ════════════════════════════════════════════════════════════════════════
# remove_completed_items — service todo/remove_completed_items
# ════════════════════════════════════════════════════════════════════════

def remove_completed_items(client, entity_id: str) -> dict:
    """Remove all completed items from a todo list.

    Uses service call POST services/todo/remove_completed_items.
    """
    _check_entity_id(entity_id)
    return client.post("services/todo/remove_completed_items",
                       {"entity_id": entity_id})
