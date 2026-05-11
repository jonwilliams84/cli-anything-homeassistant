"""Badge CRUD on Lovelace views.

Badges are the chip-like indicators shown at the top of a view. Each
view has a `badges` array. Each badge is either a simple entity_id
string or a dict like `{type: "entity-filter", entity: ..., color: ...}`.
"""

from __future__ import annotations

from typing import Any

from cli_anything.homeassistant.core import lovelace_paths


def list_badges(config: dict, view_path: str) -> list:
    v = lovelace_paths.get_view(config, view_path)
    return list(v.get("badges", []))


def add_badge(config: dict, view_path: str, badge: str | dict,
                *, index: int | None = None) -> Any:
    """Add a badge to a view. `badge` is an entity_id string or a dict."""
    if not badge:
        raise ValueError("badge required (entity_id or config dict)")
    v = lovelace_paths.get_view(config, view_path)
    badges = v.setdefault("badges", [])
    pos = len(badges) if index is None else max(0, min(index, len(badges)))
    badges.insert(pos, badge)
    return badge


def delete_badge(config: dict, view_path: str, badge_idx: int) -> dict:
    v = lovelace_paths.get_view(config, view_path)
    badges = v.get("badges")
    if not isinstance(badges, list):
        raise ValueError(f"view {view_path!r} has no badges list")
    if badge_idx < 0 or badge_idx >= len(badges):
        raise IndexError(f"badge index {badge_idx} out of range "
                          f"(view has {len(badges)} badges)")
    badges.pop(badge_idx)
    return config


def move_badge(config: dict, view_path: str, badge_idx: int,
                 new_index: int) -> dict:
    v = lovelace_paths.get_view(config, view_path)
    badges = v.get("badges")
    if not isinstance(badges, list):
        raise ValueError(f"view {view_path!r} has no badges list")
    if badge_idx < 0 or badge_idx >= len(badges):
        raise IndexError(f"badge_idx {badge_idx} out of range")
    if new_index < 0 or new_index >= len(badges):
        raise IndexError(f"new_index {new_index} out of range")
    b = badges.pop(badge_idx)
    badges.insert(new_index, b)
    return config
