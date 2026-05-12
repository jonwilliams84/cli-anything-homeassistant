"""Shopping list CRUD operations for Home Assistant.

Home Assistant exposes shopping list operations via WebSocket commands:
   - ``shopping_list/items``         — list items in the shopping list
   - ``shopping_list/items/add``     — create a new shopping list item
   - ``shopping_list/items/update``  — rename/complete an item
   - ``shopping_list/items/remove``  — delete an item by id
   - ``shopping_list/items/clear``   — bulk-delete all completed items
   - ``shopping_list/items/reorder`` — reorder items in the list

Items in the list response each contain: id, name, complete.
"""

from __future__ import annotations


# ════════════════════════════════════════════════════════════════════════
# list_items — WS shopping_list/items
# ════════════════════════════════════════════════════════════════════════

def list_items(client) -> list[dict]:
    """Return the list of items in the shopping list.

    Each item is a dict with keys: id, name, complete.
    Uses WS command ``shopping_list/items``.
    """
    result = client.ws_call("shopping_list/items")
    # HA returns a list directly; unwrap gracefully.
    if isinstance(result, list):
        return result
    return []


# ════════════════════════════════════════════════════════════════════════
# add_item — WS shopping_list/items/add
# ════════════════════════════════════════════════════════════════════════

def add_item(client, *, name: str) -> dict:
    """Add a new item to the shopping list.

    ``name`` — the item's display text (required, non-empty).

    Uses WS command ``shopping_list/items/add``.
    """
    if not name:
        raise ValueError("name must be a non-empty string")
    payload: dict = {"name": name}
    return client.ws_call("shopping_list/items/add", payload)


# ════════════════════════════════════════════════════════════════════════
# update_item — WS shopping_list/items/update
# ════════════════════════════════════════════════════════════════════════

def update_item(client, *,
                item_id: str,
                name: str | None = None,
                complete: bool | None = None) -> dict:
    """Update an existing shopping list item.

    ``item_id`` — the id of the item to update (required, non-empty).
    ``name``    — new name text, optional.
    ``complete`` — new completion status (True/False), optional.

    At least one of name/complete must be supplied.
    Uses WS command ``shopping_list/items/update``.
    """
    if not item_id:
        raise ValueError("item_id must be a non-empty string")
    if name is None and complete is None:
        raise ValueError("at least one of name/complete must be supplied")
    payload: dict = {"item_id": item_id}
    if name is not None:
        payload["name"] = name
    if complete is not None:
        payload["complete"] = complete
    return client.ws_call("shopping_list/items/update", payload)


# ════════════════════════════════════════════════════════════════════════
# remove_item — WS shopping_list/items/remove
# ════════════════════════════════════════════════════════════════════════

def remove_item(client, *, item_id: str) -> dict:
    """Remove an item from the shopping list.

    ``item_id`` — the id of the item to remove (required, non-empty).
    Uses WS command ``shopping_list/items/remove``.
    """
    if not item_id:
        raise ValueError("item_id must be a non-empty string")
    payload: dict = {"item_id": item_id}
    return client.ws_call("shopping_list/items/remove", payload)


# ════════════════════════════════════════════════════════════════════════
# clear_completed — WS shopping_list/items/clear
# ════════════════════════════════════════════════════════════════════════

def clear_completed(client) -> dict:
    """Clear all completed items from the shopping list.

    Uses WS command ``shopping_list/items/clear``.
    """
    return client.ws_call("shopping_list/items/clear")


# ════════════════════════════════════════════════════════════════════════
# reorder_items — WS shopping_list/items/reorder
# ════════════════════════════════════════════════════════════════════════

def reorder_items(client, *, item_ids: list[str]) -> dict:
    """Reorder items in the shopping list.

    ``item_ids`` — list of item ids in the desired order
                   (required, non-empty list of non-empty strings).

    Uses WS command ``shopping_list/items/reorder``.
    """
    if not item_ids:
        raise ValueError("item_ids must be a non-empty list")
    if not all(isinstance(item_id, str) and item_id for item_id in item_ids):
        raise ValueError("item_ids must contain only non-empty strings")
    payload: dict = {"item_ids": item_ids}
    return client.ws_call("shopping_list/items/reorder", payload)
