"""Layout-quality lint for Lovelace dashboards.

Distinct from `lovelace_card_validate` which catches *broken* configs. This
module catches *predictably ugly* layouts — headings that will truncate,
sibling cards with wildly different heights, useless single-child stacks,
horizontal stacks that collapse on mobile, etc.

All rules are heuristic. They produce ``info`` or ``warning`` issues, never
``error`` — a dashboard can pass with warnings and still render fine; the
fixes are about polish.

Usage:

    from cli_anything.homeassistant.core import lovelace_layout_lint as ll
    issues = ll.lint_layout(dash)
    print(ll.format_issues(issues))

Each issue has: ``severity``, ``path``, ``rule``, ``message``, ``hint``.
"""

from __future__ import annotations

from typing import Any


# ─────────────────────────────────────────────── height-class heuristics
# Estimate the "natural height" of a card as a small integer "weight"
# (rows of content at default styling). Used to detect sibling mismatch.

_TINY = 1      # chip, mushroom-title, heading
_SHORT = 2     # tile, button, gauge, glance, weather-chip, single-row
_MEDIUM = 4    # mushroom cards (most), card-mod styled, single-graph
_TALL = 8      # entities list, history-graph, calendar agenda, flex-table
_HUGE = 14     # apexcharts, weather-chart, atomic-calendar, picture-elements


def card_height_class(card: dict) -> int:
    """Return a relative height weight for `card`. Pure heuristic — assumes
    default styling. Returns 0 if the card is unrecognised."""
    if not isinstance(card, dict): return 0
    t = card.get("type", "")
    if t == "heading": return _TINY
    if t == "markdown":
        # Roughly 1 weight per line of content.
        content = card.get("content", "")
        return max(_SHORT, min(_TALL, content.count("\n") + 1))
    if t in ("tile", "button", "gauge"): return _SHORT
    if t == "glance": return _SHORT
    if t in ("entities", "logbook", "todo-list", "shopping-list"):
        n = len(card.get("entities") or []) or 5
        return min(_HUGE, max(_TALL, n))
    if t in ("history-graph", "statistics-graph", "weather-forecast",
              "media-control"):
        return _TALL
    if t in ("light", "thermostat", "media-control",
              "alarm-panel", "picture", "picture-entity", "picture-glance",
              "picture-elements", "map", "calendar"):
        return _TALL
    if t == "iframe":
        return _HUGE  # iframe sizes are user-specified; treat as huge
    if t == "vertical-stack":
        return sum(card_height_class(c) for c in (card.get("cards") or []))
    if t == "horizontal-stack":
        return max((card_height_class(c) for c in (card.get("cards") or [])),
                     default=_SHORT)
    if t == "grid":
        cards = card.get("cards") or []
        cols = max(1, int(card.get("columns") or 2))
        rows = (len(cards) + cols - 1) // cols
        if not cards: return _TINY
        max_per_row = max((card_height_class(c) for c in cards), default=_SHORT)
        return rows * max_per_row
    if t == "conditional":
        return card_height_class(card.get("card") or {})
    if t.startswith("custom:"):
        bare = t[len("custom:"):]
        # Match simple-weather-card FIRST (it's small despite "weather"
        # appearing in the name). Same trap for any future custom card
        # whose name happens to substring-match a heavier category.
        if bare == "simple-weather-card":
            return _SHORT
        if "apexcharts" in bare or "weather-chart" in bare \
                or "atomic-calendar" in bare or "calendar-card-pro" in bare \
                or "flex-table" in bare or "horizon-card" in bare \
                or "weather-card" in bare:
            return _HUGE
        if "mini-graph" in bare or "mini-media-player" in bare \
                or "modern-circular-gauge" in bare or "button-card" in bare \
                or "bubble-card" in bare:
            return _MEDIUM
        if "mushroom-chips" in bare or "mushroom-title" in bare:
            return _TINY
        if bare.startswith("mushroom-"):
            return _SHORT  # all mushroom entity cards are ~1 tile tall
        if "auto-entities" in bare:
            inner = card.get("card") or {}
            return card_height_class(inner) or _TALL
        if "stack-in-card" in bare or "expander-card" in bare \
                or "layout-card" in bare or "decluttering-card" in bare \
                or "simple-swipe-card" in bare:
            cards = card.get("cards") or []
            return sum(card_height_class(c) for c in cards) or _MEDIUM
        if "digital-clock" in bare:
            # Default font is huge — ~3 tile heights worth.
            return _TALL
        if "simple-weather-card" in bare:
            return _SHORT
        if "room-summary" in bare:
            return _MEDIUM
        if "swiss-army-knife" in bare:
            return _MEDIUM
    return _MEDIUM  # default for unknown


def _heading_text_width(card: dict) -> int:
    """Approximate display width of a heading text in characters."""
    t = card.get("heading") or card.get("title") or ""
    # Rough: heading_style h1 ≈ 0.75x density, h2 ≈ 1x, default ≈ 1x
    style = card.get("heading_style", "h2")
    factor = 0.75 if style == "h1" else 1.0
    return int(len(t) * factor)


# ────────────────────────────────────────────────────────── lint rules

def _check_heading_truncation(card: dict, path: str,
                                  column_span: int, viewport: str) -> list[dict]:
    """A heading wider than its column will truncate.
    Mobile: sections collapse to 1 col → fixed ~30 char budget.
    Desktop: ~35 chars per column_span."""
    if card.get("type") != "heading":
        return []
    width = _heading_text_width(card)
    if viewport == "mobile":
        budget = 30
        ctx = "mobile (sections collapse to 1 column)"
    else:
        budget = column_span * 35
        ctx = f"desktop column_span={column_span}"
    if width <= budget:
        return []
    return [{
        "severity": "warning", "path": path, "rule": "heading-truncation",
        "message": (f"heading {width} chars exceeds {ctx} budget ({budget} "
                      f"chars) — will truncate with ellipsis"),
        "hint": ("shorten the heading, drop heading_style to default, or "
                   "split into multiple sections"),
    }]


def _check_useless_single_child_stack(card: dict, path: str) -> list[dict]:
    """A vertical/horizontal-stack with one child renders identical to the
    bare child — but adds padding/margin chrome around it."""
    if card.get("type") not in ("vertical-stack", "horizontal-stack",
                                  "custom:stack-in-card"):
        return []
    cards = card.get("cards") or []
    if len(cards) == 1:
        return [{
            "severity": "info", "path": path, "rule": "useless-single-stack",
            "message": (f"{card['type']!r} contains only one child — adds "
                          f"chrome with no layout benefit"),
            "hint": "replace the stack with its inner card",
        }]
    if len(cards) == 0:
        return [{
            "severity": "warning", "path": path, "rule": "empty-stack",
            "message": f"{card['type']!r} has no children — renders nothing",
            "hint": "remove this card, or populate cards[]",
        }]
    return []


def _check_horizontal_stack_squeeze(card: dict, path: str,
                                        column_span: int,
                                        viewport: str) -> list[dict]:
    """Horizontal-stack squeeze rules:
      - Mobile: any horizontal-stack with 3+ children will collapse to a
        ragged vertical pile (sections-mode always collapses on mobile).
      - Desktop: only flag when column_span < N children.
    """
    if card.get("type") != "horizontal-stack":
        return []
    children = card.get("cards") or []
    if len(children) < 2:
        return []
    if viewport == "mobile":
        if len(children) >= 3:
            return [{
                "severity": "warning", "path": path, "rule": "hstack-squeeze",
                "message": (f"horizontal-stack with {len(children)} children "
                              f"will collapse to a vertical pile on mobile"),
                "hint": ("on mobile-first dashboards, prefer 2-card hstacks "
                           "or use a grid with explicit columns"),
            }]
        return []
    # Desktop
    needed = len(children)
    if column_span < needed:
        return [{
            "severity": "warning", "path": path, "rule": "hstack-squeeze",
            "message": (f"horizontal-stack with {len(children)} children "
                          f"inside column_span={column_span} — collapses "
                          f"vertically"),
            "hint": (f"widen the section to column_span={needed}+ OR replace "
                       f"with a 2-column grid"),
        }]
    return []


def _check_sibling_height_mismatch(card: dict, path: str,
                                        viewport: str) -> list[dict]:
    """For a grid/horizontal-stack, estimate each child's height-class. If
    max/min > 3x, sibling alignment will look off. On mobile, hstack
    collapses so this is only a desktop concern for hstacks; grids
    survive on mobile with their own per-row layout."""
    if card.get("type") not in ("grid", "horizontal-stack",
                                  "custom:layout-card"):
        return []
    if viewport == "mobile" and card.get("type") == "horizontal-stack":
        return []  # collapses anyway — alignment doesn't apply
    children = card.get("cards") or []
    if len(children) < 2:
        return []
    # Skip if grid has many rows — height mismatch only matters per-row.
    cols = max(1, int(card.get("columns") or len(children)))
    if cols < 2:
        return []
    # Compare each row of children.
    issues = []
    for row_start in range(0, len(children), cols):
        row = children[row_start:row_start + cols]
        if len(row) < 2:
            continue
        weights = [card_height_class(c) for c in row]
        weights = [w for w in weights if w > 0]
        if len(weights) < 2:
            continue
        lo, hi = min(weights), max(weights)
        if hi == 0 or lo == 0:
            continue
        if hi / lo >= 3.0:
            types = [c.get("type", "?") for c in row]
            issues.append({
                "severity": "warning", "path": path,
                "rule": "sibling-height-mismatch",
                "message": (f"row of {len(row)} sibling cards has uneven "
                              f"heights (weights {weights}, types {types}) — "
                              f"will look ragged"),
                "hint": ("group small cards into a vertical-stack so each "
                           "column has roughly equal content"),
            })
    return issues


def _check_default_digital_clock(card: dict, path: str,
                                       column_span: int,
                                       viewport: str) -> list[dict]:
    """Digital-clock defaults to a HUGE font; in tight columns or on mobile
    it overflows. Skip when card_mod / style override is present."""
    t = card.get("type", "")
    if "digital-clock" not in t:
        return []
    # On mobile, always too big without override. On desktop, only flag when
    # column_span < 3.
    if viewport == "desktop" and column_span >= 3:
        return []
    has_override = bool(card.get("style") or card.get("card_mod"))
    if has_override:
        return []
    return [{
        "severity": "info", "path": path,
        "rule": "digital-clock-oversize",
        "message": (f"digital-clock without font-size override will dwarf "
                      f"siblings on {viewport}"),
        "hint": ("add card_mod with `--ha-card-header-font-size: 1.5em` "
                   "or similar"),
    }]


def _check_tight_grid_with_text_heavy(card: dict, path: str) -> list[dict]:
    """A grid with >2 columns containing text-heavy cards (entities,
    markdown, calendars) will truncate content. Recommend wider columns or
    fewer cards per row."""
    if card.get("type") != "grid":
        return []
    cols = int(card.get("columns") or 2)
    if cols < 3:
        return []
    children = card.get("cards") or []
    TEXT_HEAVY = ("entities", "markdown", "logbook", "todo-list",
                    "custom:atomic-calendar-revive",
                    "custom:calendar-card-pro",
                    "custom:flex-table-card",
                    "custom:auto-entities")
    heavy = [c for c in children
              if isinstance(c, dict) and c.get("type") in TEXT_HEAVY]
    if heavy:
        return [{
            "severity": "warning", "path": path,
            "rule": "tight-grid-text-heavy",
            "message": (f"grid with columns={cols} contains {len(heavy)} "
                          f"text-heavy card(s) "
                          f"({[c.get('type') for c in heavy]}) — text will "
                          f"truncate in narrow columns"),
            "hint": (f"reduce to columns=2 or move text-heavy cards out into "
                       f"their own row"),
        }]
    return []


# ──────────────────────────────────────────────────────────── orchestrator

def _walk_with_column_span(node: Any, path: str = "",
                                column_span: int = 4):
    """Like walk_cards_strict but tracks the *enclosing* section's
    column_span so per-card width-budget rules can fire correctly."""
    if isinstance(node, dict):
        # Update column_span when descending into a section.
        local_span = column_span
        if path.endswith("]") and ("/sections[" in path or path.startswith("sections[")):
            local_span = int(node.get("column_span") or column_span)
        is_card = isinstance(node.get("type"), str)
        if is_card and (path.endswith("]") and "/cards[" in path
                          or "/card" in path):
            yield path, node, local_span
        for k in ("views", "sections", "cards"):
            v = node.get(k)
            if isinstance(v, list):
                for i, child in enumerate(v):
                    sub = f"{path}/{k}[{i}]" if path else f"{k}[{i}]"
                    yield from _walk_with_column_span(child, sub, local_span)
        for k in ("card", "default", "error_card"):
            v = node.get(k)
            if isinstance(v, dict):
                sub = f"{path}/{k}" if path else k
                yield from _walk_with_column_span(v, sub, local_span)
    elif isinstance(node, list):
        for i, child in enumerate(node):
            yield from _walk_with_column_span(child, f"[{i}]", column_span)


# ────────────────────────────────────────────────────── view-level rules

def _check_view_panel_multi_card(view: dict, path: str) -> list[dict]:
    if view.get("type") != "panel": return []
    cards = view.get("cards") or []
    if len(cards) <= 1: return []
    return [{
        "severity": "warning", "path": path, "rule": "panel-multi-card",
        "message": (f"panel view has {len(cards)} cards but panel layout "
                      f"renders only the FIRST one — others are silently dropped"),
        "hint": "wrap the cards in a vertical-stack and use that single card",
    }]


def _check_view_sections_missing_max_cols(view: dict, path: str) -> list[dict]:
    if view.get("type") != "sections": return []
    if "max_columns" in view: return []
    return [{
        "severity": "info", "path": path,
        "rule": "sections-no-max-columns",
        "message": ("sections view without max_columns defaults to 4 on "
                      "desktop — sections may pack densely on wide screens"),
        "hint": "set max_columns=2 or 3 for mobile-first dashboards",
    }]


def _check_view_sidebar_deprecated(view: dict, path: str) -> list[dict]:
    if view.get("type") != "sidebar": return []
    return [{
        "severity": "info", "path": path, "rule": "sidebar-deprecated",
        "message": ("sidebar view layout is deprecated — still works but "
                      "won't get new features"),
        "hint": "migrate to sections or custom:grid-layout",
    }]


def _check_subview_back_path(view: dict, path: str) -> list[dict]:
    if not view.get("subview"): return []
    if view.get("back_path"): return []
    return [{
        "severity": "info", "path": path, "rule": "subview-no-back-path",
        "message": ("subview without back_path — the back button defaults to "
                      "the previous browser page, which may not be intuitive"),
        "hint": "set back_path to the parent view's path",
    }]


def lint_views(dash: dict) -> list[dict]:
    """View-level lint (separate from card-level rules)."""
    issues: list[dict] = []
    for v_i, view in enumerate(dash.get("views") or []):
        path = f"views[{v_i}]"
        for fn in (_check_view_panel_multi_card,
                     _check_view_sections_missing_max_cols,
                     _check_view_sidebar_deprecated,
                     _check_subview_back_path):
            issues.extend(fn(view, path))
    return issues


def lint_layout(dash: dict, *, rules: set[str] | None = None,
                  viewport: str = "mobile") -> list[dict]:
    """Run all layout-lint rules over `dash`. Returns a list of issues.

    `rules` — restrict to a subset (rule names). None = run all.
    `viewport` — ``"mobile"`` (default — sections collapse to 1 col,
    horizontal-stacks pile vertically) or ``"desktop"`` (column_span
    matters, hstacks render side-by-side). Use ``"both"`` to run rules
    under both viewports and tag each issue.
    """
    if viewport not in ("mobile", "desktop", "both"):
        raise ValueError("viewport must be mobile|desktop|both")
    if viewport == "both":
        out_mobile = lint_layout(dash, rules=rules, viewport="mobile")
        out_desktop = lint_layout(dash, rules=rules, viewport="desktop")
        for i in out_mobile: i["viewport"] = "mobile"
        for i in out_desktop: i["viewport"] = "desktop"
        # View-level rules are viewport-agnostic; emit once.
        view_issues = lint_views(dash)
        return out_mobile + out_desktop + view_issues

    import inspect
    enabled = rules
    issues: list[dict] = []
    rule_fns = (
        (_check_heading_truncation,           "heading-truncation"),
        (_check_useless_single_child_stack,   "useless-single-stack"),
        (_check_horizontal_stack_squeeze,     "hstack-squeeze"),
        (_check_sibling_height_mismatch,      "sibling-height-mismatch"),
        (_check_default_digital_clock,        "digital-clock-oversize"),
        (_check_tight_grid_with_text_heavy,   "tight-grid-text-heavy"),
    )
    for path, card, col_span in _walk_with_column_span(dash):
        for fn, rule_name in rule_fns:
            if enabled is not None and rule_name not in enabled:
                continue
            try:
                params = inspect.signature(fn).parameters
                kwargs = {}
                if "column_span" in params: kwargs["column_span"] = col_span
                if "viewport" in params: kwargs["viewport"] = viewport
                issues.extend(fn(card, path, **kwargs))
            except Exception as e:
                issues.append({
                    "severity": "info", "path": path, "rule": rule_name,
                    "message": f"rule errored: {e}", "hint": ""})
    # Run view-level rules once.
    issues.extend(lint_views(dash))
    return issues


def format_issues(issues: list[dict]) -> str:
    if not issues:
        return "✓ no layout issues"
    out = []
    for i in issues:
        sev = i.get("severity", "info").upper()
        rule = i.get("rule", "?")
        path = i.get("path") or "<root>"
        out.append(f"[{sev}] [{rule}] {path}")
        out.append(f"    → {i.get('message','')}")
        if i.get("hint"):
            out.append(f"    hint: {i['hint']}")
    return "\n".join(out)


def summarise_by_rule(issues: list[dict]) -> dict[str, int]:
    """Return ``{rule_name: count}`` for quick aggregate inspection."""
    from collections import Counter
    return dict(Counter(i.get("rule", "?") for i in issues))
