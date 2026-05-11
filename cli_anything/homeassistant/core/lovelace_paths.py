"""Surgical edits + search for Lovelace configs.

The dashboard config is a deeply nested dict. These helpers let callers
manipulate individual views, sections, and cards without serialising the
entire structure every time.

Path conventions
----------------
- A **view-path** is the view's `path` slug (e.g. `"home"`, `"scratch"`).
- A **dot-path** addresses a card within a view: digit segments are list
  indexes, named segments are dict keys. Examples:
    "0"                              -> views[0]
    "scratch.sections.0.cards.2"     -> the third card in section 0
    "scratch.0.2"                    -> shortcut: integers under a view
                                        traverse `sections[i].cards[j]`
- For YAML-mode dashboards the config you pass in is the dict shape
  `{"views": [...]}` — the same as what `get_dashboard_config` returns.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Iterable


# ---------------------------------------------------------------- view helpers

def _views(config: dict) -> list[dict]:
    views = config.get("views")
    if not isinstance(views, list):
        raise ValueError("config has no `views` list")
    return views


def _find_view_idx(config: dict, view_path: str) -> int:
    if view_path is None:
        raise ValueError("view_path is required")
    if view_path.isdigit():
        i = int(view_path)
        views = _views(config)
        if i < 0 or i >= len(views):
            raise IndexError(f"view index {i} out of range (0..{len(views)-1})")
        return i
    for i, v in enumerate(_views(config)):
        if v.get("path") == view_path:
            return i
    raise KeyError(f"no view with path={view_path!r}")


def get_view(config: dict, view_path: str) -> dict:
    return _views(config)[_find_view_idx(config, view_path)]


def set_view(config: dict, view_path: str, new_view: dict) -> dict:
    """Replace a view by path. Mutates `config` in place and returns it."""
    if not isinstance(new_view, dict):
        raise ValueError("new_view must be a dict")
    i = _find_view_idx(config, view_path)
    _views(config)[i] = new_view
    return config


def add_view(config: dict, new_view: dict, *, index: int | None = None) -> dict:
    """Append (or insert at index) a new view. Mutates `config` in place."""
    if not isinstance(new_view, dict):
        raise ValueError("new_view must be a dict")
    views = _views(config)
    if any(v.get("path") == new_view.get("path") for v in views) and new_view.get("path"):
        raise ValueError(f"a view with path={new_view.get('path')!r} already exists")
    if index is None:
        views.append(new_view)
    else:
        views.insert(index, new_view)
    return config


def delete_view(config: dict, view_path: str) -> dict:
    """Remove a view by path. Mutates `config` in place."""
    i = _find_view_idx(config, view_path)
    del _views(config)[i]
    return config


# ---------------------------------------------------------------- section + card

def _resolve_dotpath(config: dict, dot_path: str) -> tuple[Any, list]:
    """Return (target, walked_path_list) for a dot-path.

    The first segment is treated as a view (numeric index OR `path` slug).
    Subsequent segments traverse the view; bare digits go through
    `sections[i].cards[j]` in alternation when the parent is a view/section,
    otherwise they fall back to list indexing.
    """
    if not dot_path:
        raise ValueError("empty dot_path")
    parts = dot_path.split(".")
    head, *rest = parts
    view = get_view(config, head)
    walked: list[Any] = [("view", head)]
    cur: Any = view

    digit_chain: list[int] = []

    def descend_via_digit_chain():
        nonlocal cur, walked
        if not digit_chain:
            return
        # In sections-layout: digits go sections[i].cards[j].cards[k]...
        if isinstance(cur, dict) and "sections" in cur:
            sec_i = digit_chain[0]
            sections = cur["sections"]
            cur = sections[sec_i]
            walked.append(("sections", sec_i))
            for k in digit_chain[1:]:
                cards = cur.get("cards", [])
                cur = cards[k]
                walked.append(("cards", k))
        else:
            # No sections: digits walk cards[]
            for k in digit_chain:
                cards = cur.get("cards", []) if isinstance(cur, dict) else cur
                cur = cards[k]
                walked.append(("cards", k))
        digit_chain.clear()

    for p in rest:
        if p.isdigit():
            digit_chain.append(int(p))
        else:
            # flush any pending digit chain first
            descend_via_digit_chain()
            if isinstance(cur, dict):
                cur = cur[p]
                walked.append((p, None))
            else:
                raise ValueError(f"can't descend into {type(cur).__name__} with key {p!r}")
    descend_via_digit_chain()
    return cur, walked


def get_card(config: dict, dot_path: str) -> Any:
    """Return the card at a dot-path."""
    target, _ = _resolve_dotpath(config, dot_path)
    return target


def set_card(config: dict, dot_path: str, new_value: Any) -> dict:
    """Replace whatever lives at `dot_path` with `new_value`. Mutates config."""
    # Walk to the parent of the final segment and assign.
    if not dot_path or "." not in dot_path:
        raise ValueError("dot_path must address a non-root location")
    *parent_parts, last = dot_path.split(".")
    parent_dotpath = ".".join(parent_parts)
    parent_target, _ = _resolve_dotpath(config, parent_dotpath) if "." in parent_dotpath else \
        (get_view(config, parent_dotpath), None)
    # If `last` is digit, parent_target should be a list-like (cards or sections)
    if last.isdigit():
        idx = int(last)
        if isinstance(parent_target, dict):
            # Need to figure which list: prefer 'cards', then 'sections'
            if "cards" in parent_target and idx < len(parent_target["cards"]):
                parent_target["cards"][idx] = new_value
                return config
            if "sections" in parent_target and idx < len(parent_target["sections"]):
                parent_target["sections"][idx] = new_value
                return config
            raise IndexError(f"index {idx} not addressable on parent")
        if isinstance(parent_target, list):
            parent_target[idx] = new_value
            return config
        raise ValueError("parent is neither dict nor list")
    # named key
    if isinstance(parent_target, dict):
        parent_target[last] = new_value
        return config
    raise ValueError(f"can't set named key {last!r} on a {type(parent_target).__name__}")


def get_section(config: dict, view_path: str, section_idx: int) -> dict:
    v = get_view(config, view_path)
    sections = v.get("sections", [])
    if section_idx < 0 or section_idx >= len(sections):
        raise IndexError(f"section index {section_idx} out of range (view has {len(sections)})")
    return sections[section_idx]


def set_section(config: dict, view_path: str, section_idx: int, new_section: dict) -> dict:
    v = get_view(config, view_path)
    sections = v.get("sections")
    if not isinstance(sections, list):
        raise ValueError("view has no `sections` list (maybe it's a masonry view?)")
    if section_idx < 0 or section_idx >= len(sections):
        raise IndexError(f"section index out of range")
    sections[section_idx] = new_section
    return config


# ---------------------------------------------------------------- search

def search(config: dict, query: str, *, case_sensitive: bool = False,
            limit: int = 50) -> list[dict]:
    """Search a dashboard config for any field whose value matches `query`.

    Returns up to `limit` rows: {path, type, title, match_field, match_snippet}.
    `path` is a colon-joined breadcrumb (e.g. `views[8].sections[1].cards[16]`).
    """
    q = query if case_sensitive else query.lower()
    results: list[dict] = []

    def matches(value: Any) -> bool:
        if isinstance(value, str):
            return (q in value) if case_sensitive else (q in value.lower())
        if isinstance(value, (int, float, bool)):
            return q == str(value).lower()
        return False

    def title_of(obj: dict) -> str | None:
        for k in ("title", "name", "heading", "primary"):
            v = obj.get(k)
            if isinstance(v, str):
                return v[:60]
        return None

    def walk(obj: Any, path: str):
        if len(results) >= limit:
            return
        if isinstance(obj, dict):
            # Check own fields
            for k, v in obj.items():
                if matches(v):
                    snippet = v if isinstance(v, str) else str(v)
                    if len(snippet) > 80:
                        snippet = snippet[:77] + "..."
                    results.append({
                        "path": path,
                        "type": obj.get("type"),
                        "title": title_of(obj),
                        "match_field": k,
                        "match_snippet": snippet,
                    })
                    if len(results) >= limit:
                        return
                    break  # only one match per node
            # Recurse
            for k, v in obj.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")

    walk(config, "")
    return results


def list_paths(config: dict, *, max_depth: int = 4,
                with_titles: bool = True) -> list[dict]:
    """Enumerate every view/section/card path with its type and title.

    Useful for `lovelace dump-paths <dash>` — the cheapest way to learn the
    structure of a dashboard before doing surgical edits.
    """
    rows: list[dict] = []

    def title_of(o: dict) -> str | None:
        for k in ("title", "name", "heading", "primary"):
            v = o.get(k)
            if isinstance(v, str):
                return v[:60]
        return None

    for vi, view in enumerate(_views(config)):
        rows.append({
            "path": f"views[{vi}]",
            "kind": "view",
            "view_path": view.get("path"),
            "type": view.get("type"),
            "title": view.get("title"),
        })
        if "sections" in view and isinstance(view["sections"], list):
            for si, section in enumerate(view["sections"]):
                rows.append({
                    "path": f"views[{vi}].sections[{si}]",
                    "kind": "section",
                    "view_path": view.get("path"),
                    "type": section.get("type"),
                    "title": title_of(section) if with_titles else None,
                })
                if max_depth >= 4:
                    for ci, card in enumerate(section.get("cards", [])):
                        if isinstance(card, dict):
                            rows.append({
                                "path": f"views[{vi}].sections[{si}].cards[{ci}]",
                                "kind": "card",
                                "view_path": view.get("path"),
                                "type": card.get("type"),
                                "title": title_of(card) if with_titles else None,
                            })
        elif "cards" in view and isinstance(view["cards"], list):
            for ci, card in enumerate(view["cards"]):
                if isinstance(card, dict):
                    rows.append({
                        "path": f"views[{vi}].cards[{ci}]",
                        "kind": "card",
                        "view_path": view.get("path"),
                        "type": card.get("type"),
                        "title": title_of(card) if with_titles else None,
                    })
    return rows
