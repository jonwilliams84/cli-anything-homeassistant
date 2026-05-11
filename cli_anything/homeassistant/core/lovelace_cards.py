"""Surgical card-level editing of Lovelace dashboards.

Pointer addressing: ``views[N]/cards[M]/cards[X]`` walks the config tree.

* ``views[N]`` — the Nth view (top-level tab)
* ``cards[M]`` — the Mth card at the current level
* Repeat for nested stacks (``vertical-stack``, ``horizontal-stack``, ``grid``,
  any card with a ``cards: []`` array)

Examples::

    views[8]/cards[0]/cards[4]/cards[0]   # the simple-thermostat from earlier
    views[0]/cards[2]                     # third top-level card on the first view

Most commands operate on a *parent + index* pair internally so you can also
add/remove/insert at a position.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

_TOKEN = re.compile(r"^([a-zA-Z_]+)\[(-?\d+)\]$")


def parse_pointer(pointer: str) -> list[tuple[str, int]]:
    """Split ``views[N]/cards[M]/cards[X]`` into ``[("views",N), ("cards",M), …]``."""
    if not pointer:
        return []
    parts = []
    for raw in pointer.strip("/").split("/"):
        m = _TOKEN.match(raw)
        if not m:
            raise ValueError(
                f"invalid pointer segment: {raw!r}. "
                "Expected segments like 'views[2]' or 'cards[0]'."
            )
        parts.append((m.group(1), int(m.group(2))))
    return parts


def _resolve(cfg: dict, parts: list[tuple[str, int]]) -> tuple[Any, list[Any], int]:
    """Walk a Lovelace config to a pointer.

    Returns a tuple ``(node, parent_list, index)`` where ``node`` is the
    addressed value, ``parent_list`` is the containing list, and ``index`` is
    the position in that list. Raises ``IndexError`` / ``KeyError`` for bad paths.
    """
    if not parts:
        raise ValueError("pointer must have at least one segment")
    node: Any = cfg
    parent_list: list[Any] | None = None
    index = -1
    for key, idx in parts:
        if not isinstance(node, dict):
            raise KeyError(f"cannot descend into non-dict at {key}[{idx}]")
        if key not in node:
            raise KeyError(f"missing key {key!r} in {list(node.keys())}")
        if not isinstance(node[key], list):
            raise KeyError(f"{key!r} is not a list")
        parent_list = node[key]
        if idx < 0 or idx >= len(parent_list):
            raise IndexError(
                f"{key}[{idx}] out of range (size={len(parent_list)})"
            )
        index = idx
        node = parent_list[idx]
    return node, parent_list, index  # type: ignore[return-value]


def _walk(node: Any, path: str = ""):
    """Yield ``(pointer, card)`` tuples for every card in the config tree."""
    if isinstance(node, dict):
        if "type" in node:
            yield path or "<root>", node
        for k in ("views", "cards", "sections"):
            if isinstance(node.get(k), list):
                for i, child in enumerate(node[k]):
                    sub = f"{path}/{k}[{i}]" if path else f"{k}[{i}]"
                    yield from _walk(child, sub)
    elif isinstance(node, list):
        for i, child in enumerate(node):
            yield from _walk(child, f"{path}[{i}]")


def all_cards(cfg: dict) -> list[tuple[str, dict]]:
    """Return every (pointer, card) in a dashboard config."""
    return [(p, c) for p, c in _walk(cfg) if isinstance(c, dict) and "type" in c]


def find_cards(
    cfg: dict,
    *,
    card_type: str | None = None,
    entity: str | None = None,
    contains: str | None = None,
) -> list[tuple[str, dict]]:
    """Filter cards by type, entity reference, or substring search.

    Filters AND together. ``contains`` is a case-sensitive substring match
    against the card's serialised JSON (so it works for any field).
    """
    import json
    out = []
    for p, c in all_cards(cfg):
        if card_type and c.get("type") != card_type:
            continue
        if entity:
            blob = json.dumps(c)
            if f'"{entity}"' not in blob:
                continue
        if contains and contains not in json.dumps(c):
            continue
        out.append((p, c))
    return out


# ---------------------------------------------------------------- editors

def get_card(cfg: dict, pointer: str) -> dict:
    """Return the card at ``pointer`` (a copy is NOT made — modify with care)."""
    node, _, _ = _resolve(cfg, parse_pointer(pointer))
    if not isinstance(node, dict):
        raise ValueError(f"{pointer} does not address a card")
    return node


def replace_card(cfg: dict, pointer: str, new_card: dict) -> dict:
    """Replace the card at ``pointer`` with ``new_card``. Mutates cfg in-place."""
    if not isinstance(new_card, dict):
        raise ValueError("new_card must be a dict")
    parts = parse_pointer(pointer)
    _, parent, index = _resolve(cfg, parts)
    parent[index] = new_card
    return cfg


def delete_card(cfg: dict, pointer: str) -> dict:
    """Delete the card at ``pointer``. Mutates cfg in-place."""
    parts = parse_pointer(pointer)
    _, parent, index = _resolve(cfg, parts)
    parent.pop(index)
    return cfg


def _resolve_mixed(cfg: dict, pointer: str):
    """Walk a mixed pointer like ``views[8]/cards[0]/grid_options/rows``
    where some segments are ``name[idx]`` (list) and some are bare ``name``
    (dict key). Returns ``(parent, key_or_idx)`` where assigning to
    ``parent[key_or_idx]`` updates the leaf.
    """
    if not pointer:
        raise ValueError("pointer must not be empty")
    segments = pointer.strip("/").split("/")
    if not segments:
        raise ValueError("pointer must have at least one segment")
    node: Any = cfg
    parent: Any = None
    last_key: Any = None
    for seg in segments:
        m = _TOKEN.match(seg)
        if m:
            # name[idx] — descend into a list
            key, idx_s = m.group(1), m.group(2)
            idx = int(idx_s)
            if not isinstance(node, dict) or key not in node:
                raise KeyError(f"missing key {key!r} at {seg}")
            lst = node[key]
            if not isinstance(lst, list):
                raise KeyError(f"{key!r} is not a list at {seg}")
            if idx < 0 or idx >= len(lst):
                raise IndexError(f"{seg} out of range (size={len(lst)})")
            parent = lst
            last_key = idx
            node = lst[idx]
        else:
            # bare name — descend into a dict
            if not isinstance(node, dict):
                raise KeyError(f"cannot descend into non-dict at {seg!r}")
            if seg not in node:
                # leaf set: allow creating a new key, but only at the last seg
                # (we'll detect that on assignment by leaving parent=node)
                pass
            parent = node
            last_key = seg
            node = node.get(seg) if isinstance(node, dict) else None
    return parent, last_key


def set_at_pointer(cfg: dict, pointer: str, value) -> dict:
    """Set an arbitrary JSON value at ``pointer``. Supports mixed list-and-
    dict paths (e.g. ``views[8]/cards[0]/grid_options/rows``). Creates the
    leaf dict key if missing.
    """
    parent, key = _resolve_mixed(cfg, pointer)
    parent[key] = value
    return cfg


def delete_at_pointer(cfg: dict, pointer: str) -> dict:
    """Delete the value at ``pointer``. Works for both list elements and
    dict keys.
    """
    parent, key = _resolve_mixed(cfg, pointer)
    if isinstance(parent, list):
        if not isinstance(key, int):
            raise ValueError("list parent requires integer index")
        parent.pop(key)
    elif isinstance(parent, dict):
        parent.pop(key, None)
    else:
        raise ValueError(f"cannot delete from {type(parent).__name__}")
    return cfg


def insert_card(cfg: dict, parent_pointer: str, new_card: dict, *,
                position: int | None = None) -> dict:
    """Insert ``new_card`` into ``parent_pointer`` (which must address a card with
    a ``cards:`` array, OR a view). ``position=None`` appends.
    """
    if not isinstance(new_card, dict):
        raise ValueError("new_card must be a dict")

    # Handle root-level views[N] — the parent is the view, target list is its cards
    parts = parse_pointer(parent_pointer)
    parent, _, _ = _resolve(cfg, parts)
    if not isinstance(parent, dict):
        raise ValueError(f"{parent_pointer} does not address a container")
    if "cards" not in parent or not isinstance(parent["cards"], list):
        # auto-create a cards array on a view if missing
        parent["cards"] = []
    target_list = parent["cards"]
    if position is None or position >= len(target_list):
        target_list.append(new_card)
    else:
        target_list.insert(max(0, position), new_card)
    return cfg


# ---------------------------------------------------------------- linting

_NESTED_CARDS_KEYS = {"cards", "sections", "card", "elements"}


def _entity_references(node: Any) -> Iterable[str]:
    """Yield every value that looks like an entity_id (\"<domain>.<object>\")
    within a single card's OWN fields. Stops at nested ``cards``/``sections``
    so child cards are reported only once, at their own level.
    """
    if isinstance(node, dict):
        for k, v in node.items():
            # Don't descend into nested card containers — those are separate
            # cards walked by all_cards() and will be linted in their own right.
            if k in _NESTED_CARDS_KEYS:
                continue
            # Common Lovelace fields that carry entity ids
            # NOTE: 'service' fields hold "<domain>.<action>" strings (e.g.
            # "light.turn_on") which look identical to entity ids but are NOT
            # — never flag them as dead. Only true entity references go here.
            if k in ("entity", "entity_id") and isinstance(v, str):
                yield v
            elif k == "entities" and isinstance(v, list):
                for item in v:
                    if isinstance(item, str):
                        yield item
                    elif isinstance(item, dict) and "entity" in item:
                        yield item["entity"]
            else:
                yield from _entity_references(v)
    elif isinstance(node, list):
        for v in node:
            yield from _entity_references(v)


_ENTITY_RE = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z0-9_]+$")


def lint(cfg: dict, all_entity_ids: set[str], known_card_types: set[str] | None = None) -> dict:
    """Validate a dashboard against live entity ids and (optionally) known card types.

    Returns a dict with three lists:

    * ``dead_entities`` — cards referencing entity_ids that don't exist
    * ``unknown_card_types`` — cards whose ``type`` isn't in ``known_card_types``
                              (only checked if the set is provided)
    * ``cards`` — total card count for context
    """
    dead = []
    unknown_types = []
    bad_nav: list = []
    cards = all_cards(cfg)
    for pointer, card in cards:
        for ref in _entity_references(card):
            if not isinstance(ref, str):
                continue
            # Service strings like "homeassistant.restart" look like entity ids;
            # skip anything not in the registry rather than flagging false positives.
            if not _ENTITY_RE.match(ref):
                continue
            if ref not in all_entity_ids:
                dead.append({"pointer": pointer, "entity": ref,
                             "card_type": card.get("type")})
        if known_card_types is not None:
            t = card.get("type")
            if t and t not in known_card_types:
                unknown_types.append({"pointer": pointer, "card_type": t})
        if _LINT_CTX.get("dashboard_url_path") and _LINT_CTX.get("known_view_paths") is not None:
            for nav in _navigation_paths(card):
                problem = _validate_navigation_path(
                    nav, _LINT_CTX["dashboard_url_path"],
                    _LINT_CTX["known_view_paths"])
                if problem:
                    bad_nav.append({"pointer": pointer,
                                     "navigation_path": nav,
                                     "problem": problem,
                                     "card_type": card.get("type")})
    result = {
        "cards": len(cards),
        "dead_entities": dead,
        "unknown_card_types": unknown_types,
    }
    if _LINT_CTX.get("dashboard_url_path") and _LINT_CTX.get("known_view_paths") is not None:
        result["bad_navigation_paths"] = bad_nav
    return result


_LINT_CTX: dict = {}


def lint_with_navigation(cfg: dict, all_entity_ids: set[str],
                          dashboard_url_path: str,
                          known_view_paths: set[str],
                          known_card_types: set[str] | None = None) -> dict:
    """Lint variant that also validates navigation_path references.

    `dashboard_url_path` is the current dashboard's `url_path`
    (e.g. "jon-mobile"); `known_view_paths` is the set of view paths
    available on it. Both are needed to flag tap_actions like
    `navigation_path: /lovelace/foo` when the dashboard is actually
    `/jon-mobile/foo`.
    """
    _LINT_CTX["dashboard_url_path"] = dashboard_url_path
    _LINT_CTX["known_view_paths"] = known_view_paths
    try:
        return lint(cfg, all_entity_ids, known_card_types)
    finally:
        _LINT_CTX.clear()


def _navigation_paths(node):
    """Yield every navigation_path string found anywhere inside a card."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "navigation_path" and isinstance(v, str):
                yield v
            elif isinstance(v, (dict, list)):
                yield from _navigation_paths(v)
    elif isinstance(node, list):
        for v in node:
            yield from _navigation_paths(v)


def _validate_navigation_path(path: str, dashboard_url_path: str,
                                known_view_paths: set[str]) -> str | None:
    """Return None if `path` resolves to a valid view, else a reason."""
    if not path or not path.startswith("/"):
        return "navigation_path must start with /"
    parts = [p for p in path.split("/") if p]
    if not parts:
        return "empty navigation_path"
    if len(parts) == 1:
        return None if parts[0] in known_view_paths else \
               f"unknown view path {parts[0]!r}"
    if parts[0] != dashboard_url_path:
        return (f"dashboard prefix {parts[0]!r} != current "
                f"{dashboard_url_path!r}")
    if parts[1] not in known_view_paths:
        return f"unknown view path {parts[1]!r} on dashboard {parts[0]!r}"
    return None


# ─── template validation ────────────────────────────────────────────

_JINJA_MARKER = "{{"


def _walk_template_strings(node, path=""):
    """Yield (pointer, field_name, template_string) for every string
    field that contains a Jinja2 ``{{`` marker."""
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str) and _JINJA_MARKER in v:
                yield path, k, v
            elif isinstance(v, (dict, list)):
                yield from _walk_template_strings(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_template_strings(v, f"{path}[{i}]")


def validate_templates(client, cfg: dict, *,
                         skip_paths: tuple[str, ...] = ()) -> dict:
    """Render every Jinja template in ``cfg`` against the live state and
    return a list of failures.

    Uses HA's REST template-render endpoint (one POST per template).
    Slow on big dashboards (~1 POST per Jinja string), so only invoke
    on-demand. Returns:

      {
        "total_templates": N,
        "failures": [{"pointer": ..., "field": ..., "template": ..., "error": ...}],
      }
    """
    # template_core.render does POST /api/template; import lazily to avoid cycles
    from cli_anything.homeassistant.core import template as template_core

    failures: list[dict] = []
    total = 0
    for pointer, field, tpl in _walk_template_strings(cfg):
        if any(s in pointer for s in skip_paths):
            continue
        total += 1
        try:
            template_core.render(client, tpl)
        except Exception as exc:  # noqa: BLE001
            failures.append({
                "pointer": pointer,
                "field": field,
                "template": tpl[:200],
                "error": str(exc)[:300],
            })
    return {"total_templates": total, "failures": failures}


# ─── prune — recursive bulk-drop of cards ────────────────────────────

def _card_matches_block(card: dict,
                          types: set[str] | None,
                          entity_prefixes: set[str] | None,
                          markdown_contains: set[str] | None) -> bool:
    if types and card.get("type") in types:
        return True
    if entity_prefixes:
        eid = card.get("entity")
        if isinstance(eid, str) and any(eid.startswith(p) for p in entity_prefixes):
            return True
        ents = card.get("entities")
        if isinstance(ents, list):
            for e in ents:
                eid = e if isinstance(e, str) else (
                    e.get("entity") if isinstance(e, dict) else None)
                if isinstance(eid, str) and any(eid.startswith(p)
                                                  for p in entity_prefixes):
                    return True
    if markdown_contains and card.get("type") == "markdown":
        content = card.get("content", "") or ""
        if any(s in content for s in markdown_contains):
            return True
    return False


def _prune_cards_list(cards, types, entity_prefixes, markdown_contains,
                       counters):
    if not isinstance(cards, list):
        return cards
    out = []
    for c in cards:
        if not isinstance(c, dict):
            out.append(c)
            continue
        if _card_matches_block(c, types, entity_prefixes, markdown_contains):
            counters["dropped_cards"] += 1
            continue
        new = dict(c)
        for key in ("cards", "sections"):
            if key in new and isinstance(new[key], list):
                new[key] = _prune_cards_list(new[key], types, entity_prefixes,
                                                markdown_contains, counters)
        # If a container lost all its children, prune it too
        if (new.get("type") in ("horizontal-stack", "vertical-stack", "grid")
                and not new.get("cards")):
            counters["dropped_empty_stacks"] += 1
            continue
        out.append(new)
    return out


def _strip_blocked_subheadings(cards, blocked):
    """Drop a heading card matching ``blocked`` and every following card
    up until the next heading. Returns a new list.
    """
    out = []
    i = 0
    while i < len(cards):
        c = cards[i]
        if (isinstance(c, dict) and c.get("type") == "heading"
                and c.get("heading", "") in blocked):
            i += 1
            while i < len(cards):
                nxt = cards[i]
                if isinstance(nxt, dict) and nxt.get("type") == "heading":
                    break
                i += 1
            continue
        out.append(c)
        i += 1
    return out


def prune(cfg: dict, *,
            types: set[str] | None = None,
            entity_prefixes: set[str] | None = None,
            markdown_contains: set[str] | None = None,
            blocked_subheadings: set[str] | None = None) -> tuple[dict, dict]:
    """Recursively remove cards from ``cfg``. Returns (new_cfg, stats).

    Pass any combination of:
      - ``types``: drop every card whose ``type`` is in the set
      - ``entity_prefixes``: drop every card whose ``entity`` or any
        ``entities[*].entity`` starts with one of these prefixes (e.g.
        ``{"climate."}`` drops all thermostat-style cards)
      - ``markdown_contains``: drop every ``markdown`` card whose
        ``content`` contains any of these substrings
      - ``blocked_subheadings``: in every section's flat cards list,
        drop any heading card whose ``heading`` matches one of these
        AND every following card until the next heading

    Recurses through nested ``cards``/``sections`` arrays. Empty stacks
    left behind are also dropped.
    """
    counters = {"dropped_cards": 0, "dropped_empty_stacks": 0,
                 "dropped_subheading_groups": 0}
    new_cfg = dict(cfg)
    new_views = []
    for view in cfg.get("views", []):
        v = dict(view)
        # First: blocked_subheadings (acts on each section's flat cards list)
        if blocked_subheadings:
            if "sections" in v:
                new_secs = []
                for sec in v.get("sections", []):
                    before = len(sec.get("cards", []))
                    new_sec = {**sec,
                                "cards": _strip_blocked_subheadings(
                                    sec.get("cards", []), blocked_subheadings)}
                    if len(new_sec["cards"]) != before:
                        counters["dropped_subheading_groups"] += 1
                    new_secs.append(new_sec)
                v["sections"] = new_secs
            elif "cards" in v:
                before = len(v.get("cards", []))
                v["cards"] = _strip_blocked_subheadings(
                    v.get("cards", []), blocked_subheadings)
                if len(v["cards"]) != before:
                    counters["dropped_subheading_groups"] += 1

        # Then: recursive type/entity/markdown prune
        if types or entity_prefixes or markdown_contains:
            if "sections" in v:
                v["sections"] = [
                    {**sec, "cards": _prune_cards_list(
                        sec.get("cards", []), types, entity_prefixes,
                        markdown_contains, counters)}
                    for sec in v.get("sections", [])
                ]
            if "cards" in v:
                v["cards"] = _prune_cards_list(
                    v.get("cards", []), types, entity_prefixes,
                    markdown_contains, counters)
        new_views.append(v)
    new_cfg["views"] = new_views
    return new_cfg, counters
