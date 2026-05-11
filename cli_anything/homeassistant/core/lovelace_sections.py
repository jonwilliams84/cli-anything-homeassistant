"""Section CRUD for the modern `sections` view type.

A section is a single column/group inside a sections view. Each section
has its own `cards` array. This module adds/deletes/moves sections,
complementing the existing get/set on `lovelace_paths`.
"""

from __future__ import annotations

from typing import Any

from cli_anything.homeassistant.core import lovelace_paths


def list_sections(config: dict, view_path: str) -> list[dict]:
    v = lovelace_paths.get_view(config, view_path)
    return list(v.get("sections", []))


def add_section(config: dict, view_path: str, *,
                  title: str | None = None,
                  cards: list[dict] | None = None,
                  column_span: int | None = None,
                  index: int | None = None) -> dict:
    """Add a new section to a sections view. Returns the section dict."""
    v = lovelace_paths.get_view(config, view_path)
    if v.get("type") != "sections":
        raise ValueError(
            f"view {view_path!r} is type={v.get('type')!r}, "
            "not a sections view"
        )
    sections = v.setdefault("sections", [])
    section: dict[str, Any] = {"type": "grid", "cards": list(cards or [])}
    if title is not None:
        # Section title is rendered as a heading card in the cards array
        section["cards"].insert(0, {"type": "heading", "heading": title})
    if column_span is not None:
        section["column_span"] = column_span
    pos = len(sections) if index is None else max(0, min(index, len(sections)))
    sections.insert(pos, section)
    return section


def delete_section(config: dict, view_path: str, section_idx: int) -> dict:
    v = lovelace_paths.get_view(config, view_path)
    sections = v.get("sections")
    if not isinstance(sections, list):
        raise ValueError(f"view {view_path!r} has no sections list")
    if section_idx < 0 or section_idx >= len(sections):
        raise IndexError(f"section index {section_idx} out of range "
                          f"(view has {len(sections)} sections)")
    sections.pop(section_idx)
    return config


def move_section(config: dict, view_path: str, section_idx: int,
                   new_index: int) -> dict:
    v = lovelace_paths.get_view(config, view_path)
    sections = v.get("sections")
    if not isinstance(sections, list):
        raise ValueError(f"view {view_path!r} has no sections list")
    if section_idx < 0 or section_idx >= len(sections):
        raise IndexError(f"section index {section_idx} out of range")
    if new_index < 0 or new_index >= len(sections):
        raise IndexError(f"new_index {new_index} out of range")
    s = sections.pop(section_idx)
    sections.insert(new_index, s)
    return config
