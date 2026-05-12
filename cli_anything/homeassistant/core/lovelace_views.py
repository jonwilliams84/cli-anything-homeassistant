"""View-type-aware builders + config helpers for Lovelace views.

A *view* is a top-level page inside a dashboard. HA supports six view-type
families, each with different layout semantics and config options:

  Native:
    - ``sections``   (modern, supports max_columns 1-4, dense_section_placement)
    - ``masonry``    (legacy default — single masonry-packed column)
    - ``panel``      (single card fills the viewport)
    - ``sidebar``    (2-col with sidebar — deprecated but still works)

  From layout-card (HACS plugin):
    - ``custom:grid-layout``     (CSS-grid via grid-template-columns, areas, etc.)
    - ``custom:masonry-layout``  (masonry packing with column-based breakpoints)
    - ``custom:vertical-layout``
    - ``custom:horizontal-layout``

Common view options (all types):
  title, path, icon, theme, badges, subview, back_path, visible, show_in_sidebar

Sections-view-specific:
  max_columns (1-4)                — viewport-breakpoint cap on columns
  dense_section_placement (bool)   — pack sections by size instead of order
  top_margin (bool)
  sections[]                       — list of section grids

Layout-card view options (when type starts with custom:...-layout):
  layout: {width, max_cols, max_width, min_width, mediaquery, ...}
  view_layout (per-card): {grid-column, grid-row, grid-area, place-self, ...}

This module never reaches out to HA — it builds and mutates view dicts.
Pair it with ``lovelace.save_dashboard_config`` to persist.
"""

from __future__ import annotations

from typing import Any


# Valid native view types
_NATIVE_VIEW_TYPES = {"sections", "masonry", "panel", "sidebar"}

# Valid layout-card view types
_LAYOUT_CARD_VIEW_TYPES = {
    "custom:grid-layout", "custom:masonry-layout",
    "custom:vertical-layout", "custom:horizontal-layout",
}

VALID_VIEW_TYPES = _NATIVE_VIEW_TYPES | _LAYOUT_CARD_VIEW_TYPES


# ────────────────────────────────────────────────────────────── builders

def _common(*, title: str, path: str | None = None,
              icon: str | None = None,
              theme: str | None = None,
              subview: bool = False,
              back_path: str | None = None,
              visible: list[dict] | bool | None = None,
              show_in_sidebar: bool | None = None,
              badges: list[Any] | None = None) -> dict:
    """Shared base for all view builders."""
    if not title:
        raise ValueError("title is required")
    view: dict[str, Any] = {"title": title}
    if path is not None: view["path"] = path
    if icon is not None: view["icon"] = icon
    if theme is not None: view["theme"] = theme
    if subview:
        view["subview"] = True
        if back_path is not None: view["back_path"] = back_path
    elif back_path is not None:
        raise ValueError("back_path only valid on subviews — pass subview=True")
    if visible is not None:
        view["visible"] = visible
    if show_in_sidebar is not None:
        view["show_in_sidebar"] = show_in_sidebar
    if badges is not None:
        view["badges"] = list(badges)
    return view


def view_sections(*, title: str, path: str | None = None,
                    sections: list[dict] | None = None,
                    max_columns: int = 4,
                    dense_section_placement: bool | None = None,
                    top_margin: bool | None = None,
                    icon: str | None = None,
                    theme: str | None = None,
                    subview: bool = False,
                    back_path: str | None = None,
                    visible: list[dict] | bool | None = None,
                    show_in_sidebar: bool | None = None,
                    badges: list[Any] | None = None) -> dict:
    """Build a `sections`-type view (the modern HA layout).

    `max_columns` — viewport-breakpoint cap (1-4). Mobile always collapses
    to 1; desktop fills up to max_columns based on container width.

    `dense_section_placement` — pack sections to fill empty grid cells
    instead of strict order. Useful when sections have varying heights.
    """
    if max_columns not in (1, 2, 3, 4):
        raise ValueError(f"max_columns must be 1-4, got {max_columns}")
    view = _common(title=title, path=path, icon=icon, theme=theme,
                     subview=subview, back_path=back_path, visible=visible,
                     show_in_sidebar=show_in_sidebar, badges=badges)
    view["type"] = "sections"
    view["max_columns"] = max_columns
    view["sections"] = list(sections or [])
    if dense_section_placement is not None:
        view["dense_section_placement"] = dense_section_placement
    if top_margin is not None:
        view["top_margin"] = top_margin
    return view


def view_masonry(*, title: str, path: str | None = None,
                   cards: list[dict] | None = None,
                   icon: str | None = None,
                   theme: str | None = None,
                   subview: bool = False,
                   back_path: str | None = None,
                   visible: list[dict] | bool | None = None,
                   show_in_sidebar: bool | None = None,
                   badges: list[Any] | None = None) -> dict:
    """Build a `masonry`-type view (legacy default — single column packed)."""
    view = _common(title=title, path=path, icon=icon, theme=theme,
                     subview=subview, back_path=back_path, visible=visible,
                     show_in_sidebar=show_in_sidebar, badges=badges)
    view["type"] = "masonry"
    view["cards"] = list(cards or [])
    return view


def view_panel(*, title: str, card: dict,
                 path: str | None = None,
                 icon: str | None = None,
                 theme: str | None = None,
                 subview: bool = False,
                 back_path: str | None = None,
                 visible: list[dict] | bool | None = None,
                 show_in_sidebar: bool | None = None) -> dict:
    """Build a `panel`-type view — one card fills the viewport.

    Panel views can hold only ONE card. If you need multiple, wrap them in
    a stack and pass that as `card`.
    """
    if not isinstance(card, dict) or "type" not in card:
        raise ValueError("panel view requires a single card dict with `type`")
    view = _common(title=title, path=path, icon=icon, theme=theme,
                     subview=subview, back_path=back_path, visible=visible,
                     show_in_sidebar=show_in_sidebar)
    view["type"] = "panel"
    view["cards"] = [card]
    return view


def view_sidebar(*, title: str, path: str | None = None,
                   cards: list[dict] | None = None,
                   icon: str | None = None,
                   theme: str | None = None,
                   subview: bool = False,
                   back_path: str | None = None,
                   visible: list[dict] | bool | None = None,
                   show_in_sidebar: bool | None = None,
                   badges: list[Any] | None = None) -> dict:
    """Build a `sidebar`-type view (deprecated but functional). Two
    columns: main + sidebar. Each card carries a `view_layout: {position}`
    of "main" or "sidebar"."""
    view = _common(title=title, path=path, icon=icon, theme=theme,
                     subview=subview, back_path=back_path, visible=visible,
                     show_in_sidebar=show_in_sidebar, badges=badges)
    view["type"] = "sidebar"
    view["cards"] = list(cards or [])
    return view


def view_grid_layout(*, title: str, path: str | None = None,
                       cards: list[dict] | None = None,
                       grid_template_columns: str | None = None,
                       grid_template_rows: str | None = None,
                       grid_template_areas: str | None = None,
                       grid_gap: str | None = None,
                       max_cols: int | None = None,
                       max_width: int | None = None,
                       min_width: int | None = None,
                       mediaquery: dict | None = None,
                       icon: str | None = None,
                       theme: str | None = None,
                       subview: bool = False,
                       back_path: str | None = None,
                       visible: list[dict] | bool | None = None,
                       show_in_sidebar: bool | None = None,
                       badges: list[Any] | None = None) -> dict:
    """Build a `custom:grid-layout` view (layout-card plugin).

    Use `grid_template_columns` for CSS-grid column sizing (e.g. ``"1fr 2fr"``),
    `grid_template_areas` for named regions, or pass `mediaquery` for
    breakpoint-specific overrides.
    """
    view = _common(title=title, path=path, icon=icon, theme=theme,
                     subview=subview, back_path=back_path, visible=visible,
                     show_in_sidebar=show_in_sidebar, badges=badges)
    view["type"] = "custom:grid-layout"
    view["cards"] = list(cards or [])
    layout: dict[str, Any] = {}
    if grid_template_columns is not None:
        layout["grid-template-columns"] = grid_template_columns
    if grid_template_rows is not None:
        layout["grid-template-rows"] = grid_template_rows
    if grid_template_areas is not None:
        layout["grid-template-areas"] = grid_template_areas
    if grid_gap is not None:
        layout["grid-gap"] = grid_gap
    if max_cols is not None: layout["max_cols"] = max_cols
    if max_width is not None: layout["max_width"] = max_width
    if min_width is not None: layout["min_width"] = min_width
    if mediaquery is not None: layout["mediaquery"] = mediaquery
    if layout:
        view["layout"] = layout
    return view


def view_masonry_layout(*, title: str, path: str | None = None,
                          cards: list[dict] | None = None,
                          width: int | None = None,
                          max_cols: int | None = None,
                          max_width: int | None = None,
                          mediaquery: dict | None = None,
                          icon: str | None = None,
                          theme: str | None = None,
                          subview: bool = False,
                          back_path: str | None = None,
                          visible: list[dict] | bool | None = None,
                          show_in_sidebar: bool | None = None,
                          badges: list[Any] | None = None) -> dict:
    """Build a `custom:masonry-layout` view (layout-card plugin).

    `width` — target card width in px (default 300); columns calculated
    from viewport / width.
    `max_cols` — hard cap on columns.
    """
    view = _common(title=title, path=path, icon=icon, theme=theme,
                     subview=subview, back_path=back_path, visible=visible,
                     show_in_sidebar=show_in_sidebar, badges=badges)
    view["type"] = "custom:masonry-layout"
    view["cards"] = list(cards or [])
    layout: dict[str, Any] = {}
    if width is not None: layout["width"] = width
    if max_cols is not None: layout["max_cols"] = max_cols
    if max_width is not None: layout["max_width"] = max_width
    if mediaquery is not None: layout["mediaquery"] = mediaquery
    if layout:
        view["layout"] = layout
    return view


# ──────────────────────────────────────────────────────── per-card view_layout

def with_view_layout(card: dict, *,
                       grid_column: str | None = None,
                       grid_row: str | None = None,
                       grid_area: str | None = None,
                       place_self: str | None = None,
                       column: int | None = None,
                       show: dict | None = None) -> dict:
    """Return `card` with a `view_layout:` field set (in-place mutation
    AND returned for chaining).

    Use inside a layout-card view to position cards on the CSS grid:
      - `grid_column="1 / span 2"` → card spans 2 columns starting at 1
      - `grid_row="2"`            → card lives in row 2
      - `grid_area="hero"`        → card maps to a named area
      - `place_self="center"`     → alignment within its cell

    `column` is the sidebar-view positional (1 or 2).
    `show` controls breakpoint visibility, e.g.
      ``{"mediaquery": "(max-width: 600px)"}``
    """
    vl = card.setdefault("view_layout", {})
    if not isinstance(vl, dict):
        raise ValueError("card.view_layout exists and is not a dict")
    if grid_column is not None: vl["grid-column"] = grid_column
    if grid_row is not None:    vl["grid-row"] = grid_row
    if grid_area is not None:   vl["grid-area"] = grid_area
    if place_self is not None:  vl["place-self"] = place_self
    if column is not None:      vl["column"] = column
    if show is not None:        vl["show"] = show
    return card


# ──────────────────────────────────────────────────────── view config mutators

def set_max_columns(view: dict, n: int) -> dict:
    """Set max_columns on a sections view. Raises if view isn't sections."""
    if view.get("type") != "sections":
        raise ValueError(
            f"max_columns only valid on sections views, got type="
            f"{view.get('type')!r}")
    if n not in (1, 2, 3, 4):
        raise ValueError(f"max_columns must be 1-4, got {n}")
    view["max_columns"] = n
    return view


def set_subview(view: dict, subview: bool, *,
                  back_path: str | None = None) -> dict:
    """Mark `view` as a subview (hidden from main tabs, has back button)."""
    if subview:
        view["subview"] = True
        if back_path is not None:
            view["back_path"] = back_path
    else:
        view.pop("subview", None)
        view.pop("back_path", None)
    return view


def set_visibility(view: dict, conditions: list[dict] | bool | None) -> dict:
    """Set `visible:` on a view.

    Pass:
      - True / None       — visible to everyone (default)
      - False             — hidden from everyone
      - list of {user: <user_id>} dicts — visible only to those users
      - list of {condition: ...} dicts — conditional visibility
    """
    if conditions is None or conditions is True:
        view.pop("visible", None)
    else:
        view["visible"] = conditions
    return view


def set_dense_section_placement(view: dict, dense: bool) -> dict:
    if view.get("type") != "sections":
        raise ValueError("dense_section_placement only valid on sections views")
    view["dense_section_placement"] = dense
    return view


# ──────────────────────────────────────────────────────── inspection

# ──────────────────────────────────────────────────────── section headers
# Sections-view sections gained a per-section `header` field that holds a
# title card + badges with layout controls. From the UI's Header Settings
# dialog:
#
#   Layout:             Responsive | Left aligned | Centred
#   Badges position:    Top | Bottom (default)
#   Badges behaviour:   Wrap | Scroll
#
# The YAML keys (matching HA's frontend conventions) are:
#   layout: responsive | start | center
#   badges_position: top | bottom
#   badges_wrap: wrap | scroll

_HEADER_LAYOUTS = {"responsive", "start", "center"}
_BADGES_POSITIONS = {"top", "bottom"}
_BADGES_WRAPS = {"wrap", "scroll"}


def section_header(*, card: dict | None = None,
                     title: str | None = None,
                     subtitle: str | None = None,
                     badges: list[dict] | None = None,
                     layout: str = "responsive",
                     badges_position: str = "bottom",
                     badges_wrap: str = "wrap") -> dict:
    """Build a section header config (the new sections-view feature with
    title + subtitle + badges + layout controls).

    Pass either:
      - `card` — a full heading/markdown card dict for the header
      - `title` / `subtitle` — convenience to build a heading card
        ({"type": "heading", "heading": title, "heading_style": "title"})

    `layout` — ``"responsive"`` (default, stacks on mobile),
                ``"start"`` (always left-aligned),
                ``"center"`` (always centred)
    `badges_position` — ``"top"`` or ``"bottom"`` (default)
    `badges_wrap` — ``"wrap"`` (default, wraps to multiple rows) or
                     ``"scroll"`` (touch-friendly horizontal scroll)
    """
    if layout not in _HEADER_LAYOUTS:
        raise ValueError(f"layout must be one of {sorted(_HEADER_LAYOUTS)}")
    if badges_position not in _BADGES_POSITIONS:
        raise ValueError(f"badges_position must be one of {sorted(_BADGES_POSITIONS)}")
    if badges_wrap not in _BADGES_WRAPS:
        raise ValueError(f"badges_wrap must be one of {sorted(_BADGES_WRAPS)}")

    if card is None and not title and not subtitle:
        raise ValueError("pass `card`, or at least one of title/subtitle")

    header: dict[str, Any] = {
        "layout": layout,
        "badges_position": badges_position,
        "badges_wrap": badges_wrap,
    }
    if card is None:
        heading_card: dict[str, Any] = {"type": "heading",
                                           "heading_style": "title"}
        if title is not None: heading_card["heading"] = title
        if subtitle is not None: heading_card["badges"] = []  # heading uses badges differently — keep simple
        # Subtitle is best rendered as part of the heading; use a markdown
        # card when a real subtitle is required.
        if subtitle is not None:
            heading_card = {"type": "markdown",
                              "content": f"## {title or ''}\n{subtitle}"}
        header["card"] = heading_card
    else:
        if not isinstance(card, dict) or "type" not in card:
            raise ValueError("card must be a dict with a `type` field")
        header["card"] = card
    if badges is not None:
        header["badges"] = list(badges)
    return header


def view_section(*, header: dict | None = None,
                   cards: list[dict] | None = None,
                   column_span: int | None = None,
                   row_span: int | None = None,
                   visibility: list[dict] | None = None) -> dict:
    """Build a single section for a sections-view.

    `header` — pass the result of `section_header(...)`.
    `cards`  — list of cards inside the section's grid.
    `column_span` / `row_span` — how many columns/rows the section spans
      in the view's grid layout (capped by the view's max_columns).
    `visibility` — list of visibility condition dicts.
    """
    section: dict[str, Any] = {"type": "grid", "cards": list(cards or [])}
    if header is not None:
        if not isinstance(header, dict):
            raise ValueError("header must be a dict — use section_header()")
        section["header"] = header
    if column_span is not None: section["column_span"] = column_span
    if row_span is not None: section["row_span"] = row_span
    if visibility is not None: section["visibility"] = visibility
    return section


# Convenience badge builders — badges in a section header use the same
# schema as Lovelace badges (slimmer than card chips).

def badge_entity(entity: str, *,
                   name: str | None = None,
                   icon: str | None = None,
                   color: str | None = None,
                   show_name: bool | None = None,
                   show_state: bool | None = None,
                   show_icon: bool | None = None,
                   tap_action: dict | None = None) -> dict:
    """Build an `entity` badge (the most common type)."""
    b: dict[str, Any] = {"type": "entity", "entity": entity}
    if name is not None: b["name"] = name
    if icon is not None: b["icon"] = icon
    if color is not None: b["color"] = color
    if show_name is not None: b["show_name"] = show_name
    if show_state is not None: b["show_state"] = show_state
    if show_icon is not None: b["show_icon"] = show_icon
    if tap_action is not None: b["tap_action"] = tap_action
    return b


def badge_template(*,
                     content: str,
                     icon: str | None = None,
                     color: str | None = None,
                     entity: str | None = None,
                     tap_action: dict | None = None) -> dict:
    """Build a `template` (Jinja-driven) badge."""
    b: dict[str, Any] = {"type": "entity", "content": content}
    if icon is not None: b["icon"] = icon
    if color is not None: b["color"] = color
    if entity is not None: b["entity"] = entity
    if tap_action is not None: b["tap_action"] = tap_action
    return b


def view_summary(view: dict) -> dict:
    """Return a compact summary of a view's config — useful for inspection
    and the SKILL.md table."""
    t = view.get("type") or "masonry"
    out: dict[str, Any] = {
        "title": view.get("title", "<untitled>"),
        "path": view.get("path", ""),
        "type": t,
        "is_subview": bool(view.get("subview")),
    }
    if t == "sections":
        out["max_columns"] = view.get("max_columns", 4)
        out["sections"] = len(view.get("sections") or [])
        if view.get("dense_section_placement"):
            out["dense_section_placement"] = True
    else:
        out["cards"] = len(view.get("cards") or [])
    if "layout" in view:
        out["layout_keys"] = list(view["layout"].keys())
    if "visible" in view:
        out["visibility"] = view["visible"]
    return out


def list_view_summaries(dash: dict) -> list[dict]:
    return [view_summary(v) for v in (dash.get("views") or [])]
