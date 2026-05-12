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
                  row_span: int | None = None,
                  header: dict | None = None,
                  visibility: list[dict] | None = None,
                  index: int | None = None) -> dict:
    """Add a new section to a sections view. Returns the section dict.

    `header` — pass a section header dict (use
      ``lovelace_views.section_header(...)``) to attach the modern
      title-bar with badges + layout controls.
    `title` — legacy convenience that inserts a heading card at the top
      of the section. Mutually exclusive with `header` (raises if both
      are given).
    `visibility` — list of visibility condition dicts (e.g. for the
      room-selector pattern).
    """
    v = lovelace_paths.get_view(config, view_path)
    if v.get("type") != "sections":
        raise ValueError(
            f"view {view_path!r} is type={v.get('type')!r}, "
            "not a sections view"
        )
    if title is not None and header is not None:
        raise ValueError("pass `header` OR `title`, not both")
    sections = v.setdefault("sections", [])
    section: dict[str, Any] = {"type": "grid", "cards": list(cards or [])}
    if header is not None:
        if not isinstance(header, dict):
            raise ValueError("header must be a dict — use lovelace_views.section_header()")
        section["header"] = header
    elif title is not None:
        # Legacy: section title rendered as a heading card.
        section["cards"].insert(0, {"type": "heading", "heading": title})
    if column_span is not None:
        section["column_span"] = column_span
    if row_span is not None:
        section["row_span"] = row_span
    if visibility is not None:
        section["visibility"] = visibility
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
