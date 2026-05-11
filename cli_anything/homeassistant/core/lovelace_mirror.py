"""Lovelace mirror — copy one dashboard to another with substitutions,
view filtering, and per-card pruning.

Subsumes the bespoke ``mirror_dashboard.py`` pattern: given a source
dashboard, produce a downstream copy with optional transformations
applied (rename entity_ids, drop specific views, strip cards by type
or entity prefix, drop sections inside the Rooms view by selector
state, etc.).
"""

from __future__ import annotations

from typing import Any, Iterable

from cli_anything.homeassistant.core import lovelace as lovelace_core
from cli_anything.homeassistant.core import lovelace_cards as lovelace_cards_core


def _substitute(obj, rules: list[tuple[str, str]]):
    if isinstance(obj, dict):
        return {k: _substitute(v, rules) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute(v, rules) for v in obj]
    if isinstance(obj, str):
        for old, new in rules:
            obj = obj.replace(old, new)
        return obj
    return obj


def _section_room_keys(section: dict) -> Iterable[str]:
    """Yield every `state` value referenced via a `room_selector_*` entity
    inside a section's `visibility` predicates.
    """
    def walk(node):
        if isinstance(node, dict):
            ent = node.get("entity", "")
            if (node.get("condition") == "state"
                    and isinstance(ent, str)
                    and "room_selector_" in ent):
                state = node.get("state")
                if isinstance(state, str):
                    yield state
            for v in node.values():
                yield from walk(v)
        elif isinstance(node, list):
            for v in node:
                yield from walk(v)
    yield from walk(section.get("visibility", []))


def _filter_rooms_view(view: dict, allowed: set[str]) -> dict:
    """If ``view`` is the Rooms view, drop sections whose room-selector
    visibility refers ONLY to room names outside ``allowed``.
    """
    if view.get("title") != "Rooms" or "sections" not in view:
        return view
    out = []
    for sec in view.get("sections", []):
        keys = list(_section_room_keys(sec))
        if not keys or any(k in allowed for k in keys):
            out.append(sec)
    return {**view, "sections": out}


def mirror(client, *, source_url_path: str, dest_url_path: str,
            substitutions: list[tuple[str, str]] | None = None,
            keep_views: set[str] | None = None,
            skip_views: set[str] | None = None,
            allowed_rooms: set[str] | None = None,
            blocked_subheadings: set[str] | None = None,
            blocked_card_types: set[str] | None = None,
            blocked_entity_prefixes: set[str] | None = None,
            blocked_markdown_contains: set[str] | None = None,
            dry_run: bool = False) -> dict:
    """Mirror ``source_url_path`` → ``dest_url_path`` with optional
    filtering and substitutions. Returns a summary dict.

    Args:
      substitutions: list of (old, new) string replacements applied
        recursively to every string value in the mirror.
      keep_views: if provided, only views whose ``path`` OR ``title``
        is in this set are mirrored. Otherwise all views are mirrored
        minus ``skip_views``.
      skip_views: ignored when ``keep_views`` is set; otherwise these
        views are dropped from the mirror.
      allowed_rooms: in the Rooms view (title=='Rooms'), drop any
        section whose visibility selector value isn't in this set.
      blocked_subheadings / blocked_card_types / blocked_entity_prefixes
      / blocked_markdown_contains: passed to ``lovelace_cards.prune``.
      dry_run: produce the new config but don't save it.
    """
    src_cfg = lovelace_core.get_dashboard_config(client, source_url_path)
    n_src = len(src_cfg.get("views", []))

    # View filter
    views = src_cfg.get("views", [])
    if keep_views is not None:
        views = [v for v in views
                 if (v.get("path") or v.get("title")) in keep_views]
    elif skip_views:
        views = [v for v in views
                 if (v.get("path") or v.get("title")) not in skip_views]

    new_cfg = {**src_cfg, "views": views}

    # Per-target room filter (Rooms view section pruning)
    if allowed_rooms:
        new_cfg["views"] = [_filter_rooms_view(v, allowed_rooms)
                              for v in new_cfg["views"]]

    # Substitutions
    if substitutions:
        new_cfg = _substitute(new_cfg, list(substitutions))

    # Card pruning
    counters = {}
    if (blocked_card_types or blocked_entity_prefixes
            or blocked_markdown_contains or blocked_subheadings):
        new_cfg, counters = lovelace_cards_core.prune(
            new_cfg,
            types=set(blocked_card_types) if blocked_card_types else None,
            entity_prefixes=set(blocked_entity_prefixes) if blocked_entity_prefixes else None,
            markdown_contains=set(blocked_markdown_contains) if blocked_markdown_contains else None,
            blocked_subheadings=set(blocked_subheadings) if blocked_subheadings else None,
        )

    summary = {
        "source": source_url_path,
        "dest": dest_url_path,
        "source_views": n_src,
        "mirrored_views": len(new_cfg["views"]),
        "substitutions_applied": len(substitutions or []),
        "dropped_cards": counters.get("dropped_cards", 0),
        "dropped_empty_stacks": counters.get("dropped_empty_stacks", 0),
        "dropped_subheading_groups": counters.get("dropped_subheading_groups", 0),
        "dry_run": dry_run,
    }
    if not dry_run:
        lovelace_core.save_dashboard_config(client, dest_url_path, new_cfg)
        summary["saved"] = True
    else:
        summary["saved"] = False
        summary["preview_cfg_views_titles"] = [
            v.get("path") or v.get("title") for v in new_cfg["views"]
        ]
    return summary
