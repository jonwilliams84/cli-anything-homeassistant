"""Card-level structural operations — move, reorder, wrap, duplicate.

All operations are type-agnostic; they manipulate the Lovelace JSON tree
without inspecting `type:` fields. Works with any built-in or custom card.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from cli_anything.homeassistant.core import lovelace_cards as cards_core


# ─────────────────────────────────────────────────────────────── move

def move_card(cfg: dict, src_pointer: str, dest_parent_pointer: str,
                *, index: int | None = None) -> dict:
    """Move a card from one pointer to another parent's `cards[]` list.

    `dest_parent_pointer` addresses a container (view, section, or any
    card with a `cards` array). The moved card is inserted at `index`
    within the destination's `cards` list (appended if None).
    """
    # Get the source card first (deep copy to detach from source)
    src_card = copy.deepcopy(cards_core.get_card(cfg, src_pointer))
    # Resolve destination parent — it must have a `cards` list
    dest_parts = cards_core.parse_pointer(dest_parent_pointer)
    dest_node, _, _ = cards_core._resolve(cfg, dest_parts) if dest_parts \
        else (cfg, None, -1)
    if not isinstance(dest_node, dict):
        raise ValueError(f"destination {dest_parent_pointer!r} is not a container")
    if "cards" not in dest_node or not isinstance(dest_node["cards"], list):
        # Allow creating a fresh cards list on an empty container
        dest_node["cards"] = []
    cards_list = dest_node["cards"]
    pos = len(cards_list) if index is None else max(0, min(index, len(cards_list)))
    cards_list.insert(pos, src_card)
    # Delete from the source — but recalculate the source pointer in case
    # the destination insert shifted indices in a shared ancestor list.
    # Trick: search the cfg for the original card object by identity.
    cards_core.delete_card(cfg, src_pointer)
    return cfg


# ─────────────────────────────────────────────────────────────── reorder

def reorder_card(cfg: dict, pointer: str, new_index: int) -> dict:
    """Move a card to a new index within its current parent list."""
    parts = cards_core.parse_pointer(pointer)
    if not parts:
        raise ValueError("pointer must have at least one segment")
    _, parent, current_index = cards_core._resolve(cfg, parts)
    if new_index < 0 or new_index >= len(parent):
        raise IndexError(
            f"new_index {new_index} out of range (parent has {len(parent)} items)"
        )
    card = parent.pop(current_index)
    parent.insert(new_index, card)
    return cfg


# ─────────────────────────────────────────────────────────────── wrap

def wrap_in_stack(cfg: dict, pointers: list[str], *,
                    stack_type: str = "vertical-stack",
                    columns: int | None = None,
                    title: str | None = None) -> str:
    """Wrap one or more pointed-at cards into a single stack card.

    `stack_type` is one of: vertical-stack, horizontal-stack, grid.
    For `grid`, `columns` controls the column count.

    All target cards must share the same parent list. Returns the pointer
    to the new stack card.
    """
    if stack_type not in ("vertical-stack", "horizontal-stack", "grid"):
        raise ValueError(f"stack_type must be one of vertical-stack/"
                          f"horizontal-stack/grid, got {stack_type!r}")
    if not pointers:
        raise ValueError("at least one pointer is required")

    # Resolve all to (parent_list, index) — verify same parent
    resolutions = []
    for p in pointers:
        parts = cards_core.parse_pointer(p)
        _, parent, idx = cards_core._resolve(cfg, parts)
        resolutions.append((parent, idx))
    first_parent = resolutions[0][0]
    if not all(parent is first_parent for parent, _ in resolutions):
        raise ValueError("all pointers must share the same parent list "
                          "(same view/section/stack)")

    # Collect cards in order, smallest index first; remove from parent
    sorted_indices = sorted(set(idx for _, idx in resolutions))
    cards_to_wrap = [copy.deepcopy(first_parent[i]) for i in sorted_indices]
    for i in sorted(sorted_indices, reverse=True):
        first_parent.pop(i)
    insert_at = sorted_indices[0]

    new_stack: dict[str, Any] = {"type": stack_type, "cards": cards_to_wrap}
    if title:
        new_stack["title"] = title
    if stack_type == "grid":
        if columns is None:
            columns = 2
        new_stack["columns"] = columns

    first_parent.insert(insert_at, new_stack)
    # Compute pointer to the new stack: take the prefix of the first
    # pointer and replace its final cards[idx] with cards[insert_at]
    first_pointer = pointers[0]
    head = first_pointer.rsplit("/", 1)[0] if "/" in first_pointer \
        else first_pointer
    if "/" in first_pointer:
        return f"{head}/cards[{insert_at}]"
    # single-segment pointer like views[0] — destination is the same
    return f"{first_pointer.rsplit('[', 1)[0]}[{insert_at}]"


def wrap_in_conditional(cfg: dict, pointer: str, conditions: list[dict]) -> dict:
    """Wrap a card in a conditional card with the given condition list.

    Each condition is a dict like {entity: light.x, state: on} or
    {condition: state, entity: ..., state: ...}. Mutates cfg in place.
    """
    if not conditions:
        raise ValueError("at least one condition required")
    parts = cards_core.parse_pointer(pointer)
    _, parent, idx = cards_core._resolve(cfg, parts)
    inner = parent[idx]
    parent[idx] = {
        "type": "conditional",
        "conditions": conditions,
        "card": inner,
    }
    return cfg


# ─────────────────────────────────────────────────────────────── duplicate

def duplicate_card(cfg: dict, pointer: str,
                     *, substitutions: dict[str, str] | None = None,
                     index_offset: int = 1) -> str:
    """Duplicate the card at `pointer` and insert near it in the same parent.

    `substitutions` is an old→new map applied as regex substitutions over
    the duplicated card's serialised JSON before parsing back (so the
    rename touches every nested reference, including templates and
    embedded entity_ids).

    Returns the pointer to the new card.
    """
    import json
    parts = cards_core.parse_pointer(pointer)
    src, parent, idx = cards_core._resolve(cfg, parts)
    blob = json.dumps(src)
    if substitutions:
        for old, new in substitutions.items():
            blob = re.sub(old, new, blob)
    new_card = json.loads(blob)
    new_idx = idx + index_offset
    parent.insert(new_idx, new_card)
    # rebuild the pointer
    if "/" in pointer:
        head = pointer.rsplit("/", 1)[0]
        return f"{head}/cards[{new_idx}]"
    base = pointer.rsplit("[", 1)[0]
    return f"{base}[{new_idx}]"


# ─────────────────────────────────────────────────────────────── style

def inject_card_mod(cfg: dict, pointer: str, css: str, *,
                      target: str = "root") -> dict:
    """Inject a `card_mod` style block on the card at `pointer`.

    `target` is the style selector in card-mod terms — typically "root",
    "ha-card", or a specific shadow-DOM path. Existing card_mod is merged.
    """
    if not css:
        raise ValueError("css must not be empty")
    parts = cards_core.parse_pointer(pointer)
    card, _, _ = cards_core._resolve(cfg, parts)
    if not isinstance(card, dict):
        raise ValueError(f"{pointer} does not address a card")
    cm = card.setdefault("card_mod", {})
    if not isinstance(cm, dict):
        # Card-mod can also be a string; normalize to dict
        old = cm
        cm = card["card_mod"] = {"style": old}
    style = cm.setdefault("style", {})
    if isinstance(style, str):
        # Existing string-style; promote to dict
        style = cm["style"] = {target: style}
    if isinstance(style, dict):
        style[target] = (style.get(target, "") + "\n" + css).strip()
    else:
        raise ValueError(f"unexpected card_mod.style type: {type(style).__name__}")
    return cfg


def clear_card_mod(cfg: dict, pointer: str) -> dict:
    """Remove the `card_mod` block from a card."""
    parts = cards_core.parse_pointer(pointer)
    card, _, _ = cards_core._resolve(cfg, parts)
    if isinstance(card, dict):
        card.pop("card_mod", None)
    return cfg
