"""Helper builders for polishing sections-view sections (grid-type).

A *section* within a sections-view is a `type: grid` container holding:
  - optional `header` (title card + badges)
  - a list of cards in a grid layout
  - optional `column_span` and `row_span` for positioning in the view's grid
  - optional `heading_style` and `top_margin` for visual polish

This module provides convenience builders and in-place mutators for sections,
focused on layout polish: hero sections, spacers, dividers, and option setters.

All functions operate on dicts only — no HA client or network calls.
"""

from __future__ import annotations

from typing import Any


# ────────────────────────────────────────────────────────── section mutators

def with_section_options(section: dict, *,
                         heading_style: str | None = None,
                         top_margin: bool | None = None,
                         column_span: int | None = None,
                         row_span: int | None = None) -> dict:
    """Mutate a section dict in-place, setting option fields.

    Validates and sets only the options passed (non-None). Returns the
    mutated section for chaining.

    `heading_style` — ``"title"``, ``"subtitle"``, or ``"default"``.
    `top_margin` — add vertical spacing above the section.
    `column_span` — 1-4, how many columns the section spans.
    `row_span` — > 0, how many rows the section spans.
    """
    if not isinstance(section, dict):
        raise ValueError("section must be a dict")

    if heading_style is not None:
        if heading_style not in ("title", "subtitle", "default"):
            raise ValueError(
                f"heading_style must be 'title', 'subtitle', or 'default', "
                f"got {heading_style!r}")
        section["heading_style"] = heading_style

    if top_margin is not None:
        section["top_margin"] = top_margin

    if column_span is not None:
        if column_span not in (1, 2, 3, 4):
            raise ValueError(
                f"column_span must be 1-4, got {column_span}")
        section["column_span"] = column_span

    if row_span is not None:
        if not isinstance(row_span, int) or row_span <= 0:
            raise ValueError(
                f"row_span must be > 0, got {row_span}")
        section["row_span"] = row_span

    return section


# ────────────────────────────────────────────────────────── section builders

def hero_section(*,
                 card: dict,
                 column_span: int = 4,
                 heading_style: str = "title",
                 top_margin: bool = False) -> dict:
    """Build a hero section: a single-card grid with polish options.

    A hero section typically contains one prominent card (heading, big media,
    etc.) and spans the full width (column_span=4 by default).

    `card` — a dict with a `type` field (e.g., heading, custom:button-card).
    `column_span` — how many columns wide (1-4, default 4).
    `heading_style` — "title", "subtitle", or "default" (default "title").
    `top_margin` — add spacing above (default False).

    Returns a `type: grid` section containing the card.
    """
    if not isinstance(card, dict) or "type" not in card:
        raise ValueError("card must be a dict with a `type` field")
    if column_span not in (1, 2, 3, 4):
        raise ValueError(f"column_span must be 1-4, got {column_span}")
    if heading_style not in ("title", "subtitle", "default"):
        raise ValueError(
            f"heading_style must be 'title', 'subtitle', or 'default', "
            f"got {heading_style!r}")

    section: dict[str, Any] = {
        "type": "grid",
        "cards": [card],
        "heading_style": heading_style,
        "column_span": column_span,
        "top_margin": top_margin,
    }
    return section


def spacer_section(*, column_span: int = 4) -> dict:
    """Build a blank section used for visual spacing.

    A spacer is a `type: grid` section with no cards — useful for breaking
    up dense layouts or adding breathing room between sections.

    `column_span` — how many columns wide (1-4, default 4).

    Returns a section with empty `cards: []`.
    """
    if column_span not in (1, 2, 3, 4):
        raise ValueError(f"column_span must be 1-4, got {column_span}")

    section: dict[str, Any] = {
        "type": "grid",
        "cards": [],
        "column_span": column_span,
    }
    return section


def divider_section(*, label: str, column_span: int = 4) -> dict:
    """Build a divider section containing only a heading card.

    A divider is a visual separator with a label. It creates a section
    holding a single `type: heading` card with the given label.

    `label` — non-empty string for the heading.
    `column_span` — how many columns wide (1-4, default 4).

    Returns a section with a heading card.
    """
    if not isinstance(label, str) or not label.strip():
        raise ValueError("label must be a non-empty string")
    if column_span not in (1, 2, 3, 4):
        raise ValueError(f"column_span must be 1-4, got {column_span}")

    heading_card: dict[str, Any] = {
        "type": "heading",
        "heading": label,
    }
    section: dict[str, Any] = {
        "type": "grid",
        "cards": [heading_card],
        "column_span": column_span,
    }
    return section
