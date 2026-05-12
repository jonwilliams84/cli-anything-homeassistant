"""Validate cards against builder schemas BEFORE saving a dashboard.

The harness builds dashboards via `lovelace_card_builders`. Each builder
registers metadata in `BUILDER_META` (card type, custom-resource URL,
required fields, example). This module walks an entire dashboard config
and surfaces problems locally — instead of waiting for HA to render the
config and show a "Configuration error" in the UI.

Usage:

    from cli_anything.homeassistant.core import (
        lovelace as ll, lovelace_card_validate as v
    )
    dash = ll.get_dashboard_config(client, "jon-mobile")
    issues = v.validate_dashboard(dash, client=client)
    for i in issues:
        print(i["severity"], i["path"], i["message"])

What's checked:
  - Every card slot has a ``type`` field.
  - For builder-backed types, every required builder kwarg appears on the card.
  - ``custom:*`` cards have their HACS plugin installed (when ``client`` given).
  - No stray ``card_mod`` keys inside non-card slots (series/chips/elements).
"""

from __future__ import annotations

import inspect
from typing import Any

from . import lovelace_card_builders as cb
from . import lovelace_cards as lc


# Build a quick reverse-lookup: card type string → builder name.
def _card_type_to_builder() -> dict[str, str]:
    return {meta["card_type"]: name
            for name, meta in cb.BUILDER_META.items()
            if meta.get("card_type")}


def _required_kwargs(builder_fn) -> set[str]:
    """Return the set of parameter names without defaults
    (positional or keyword) — these MUST be present on the card."""
    out = set()
    for p in inspect.signature(builder_fn).parameters.values():
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        if p.default is p.empty:
            out.add(p.name)
    return out


# Known-broken card_mod placements — HA will reject these.
# (apexcharts series, ApexCharts entities, etc.) These always error.
_BROKEN_CARD_MOD_PARENTS = {
    "series",         # apexcharts: series entries reject unknown keys
    "forecast",       # weather-chart-card forecast block
    "filter",         # auto-entities filter dict
    "include",        # auto-entities include patterns
    "exclude",        # auto-entities exclude patterns
    "tools",          # swiss-army-knife tools
    "options",        # template-card / auto-entities sub-options
}

# Likely-broken-but-context-dependent placements. Warn only.
_SUSPICIOUS_CARD_MOD_PARENTS = {
    "chips",          # mushroom chips — card_mod sometimes works
    "elements",       # picture-elements — card_mod styles inner icon, works
    "entities",       # entities-card rows — supports card_mod on row entries
}


# Native HA cards not in BUILDERS but recognised by HA. Don't warn on these.
_KNOWN_NATIVE_TYPES = {
    "heading", "section", "sections", "panel",
    "alarm-panel", "area", "calendar", "energy-date-selection",
    "energy-distribution", "energy-flow", "energy-grid-neutrality-gauge",
    "energy-solar-graph", "energy-sources-table", "energy-usage-graph",
    "entity", "energy-carbon-consumed-gauge",
    "light", "logbook", "map", "media-control", "plant-status",
    "picture", "picture-entity", "picture-glance", "shopping-list",
    "sensor", "starting", "thermostat", "todo-list", "tile",
    "vertical-stack", "horizontal-stack",
}


# Bundle-based custom plugins — one resource file ships many card types.
# Without this, the validator falsely reports "not installed" for every
# card-type beyond the bundle's primary filename.
_BUNDLE_CARDS: dict[str, set[str]] = {
    # filename stem (or fragment) → set of card types it ships
    "mushroom": {
        "custom:mushroom-template-card", "custom:mushroom-light-card",
        "custom:mushroom-person-card", "custom:mushroom-climate-card",
        "custom:mushroom-chips-card", "custom:mushroom-title-card",
        "custom:mushroom-entity-card", "custom:mushroom-cover-card",
        "custom:mushroom-fan-card", "custom:mushroom-vacuum-card",
        "custom:mushroom-humidifier-card", "custom:mushroom-lock-card",
        "custom:mushroom-media-player-card", "custom:mushroom-number-card",
        "custom:mushroom-select-card", "custom:mushroom-update-card",
        "custom:mushroom-alarm-control-panel-card",
    },
    "bubble-card": {
        "custom:bubble-card",  # popup/button/separator/slider all use this type
    },
    "better-thermostat-ui": {
        "custom:better-thermostat-ui-card",
    },
    "decluttering-card": {
        "custom:decluttering-card",
    },
    "auto-entities": {
        "custom:auto-entities",
    },
}


def _check_no_stray_card_mod(node: Any, path: str = "",
                                parent_key: str | None = None) -> list[dict]:
    """Walk arbitrary tree and flag card_mod on dicts that are NOT card-slot
    members. Errors only on KNOWN-broken placements; warns on suspicious
    placements that may or may not work depending on the parent card."""
    issues: list[dict] = []
    if isinstance(node, dict):
        if "card_mod" in node and parent_key is not None:
            if parent_key in _BROKEN_CARD_MOD_PARENTS:
                issues.append({
                    "severity": "error", "path": path,
                    "message": (f"card_mod inside {parent_key!r} is rejected "
                                  f"by HA — this card will show "
                                  f"'Configuration error'"),
                })
            elif parent_key in _SUSPICIOUS_CARD_MOD_PARENTS:
                issues.append({
                    "severity": "warning", "path": path,
                    "message": (f"card_mod inside {parent_key!r} works in some "
                                  f"contexts and not others — verify visually"),
                })
        for k, v in node.items():
            issues.extend(_check_no_stray_card_mod(
                v, f"{path}.{k}" if path else k, parent_key=k))
    elif isinstance(node, list):
        for i, child in enumerate(node):
            issues.extend(_check_no_stray_card_mod(
                child, f"{path}[{i}]", parent_key=parent_key))
    return issues


def installed_card_types(client) -> set[str]:
    """Return the set of `custom:<type>` card strings whose HACS resource is
    currently installed (by scanning `lovelace/resources` filenames).

    The mapping is heuristic: we treat the filename stem as the resource
    name and compare against the `custom:<stem>` of each builder. This
    catches common cases (e.g. ``apexcharts-card.js`` →
    ``custom:apexcharts-card``); for plugins that publish files under a
    different name from their card type, we fall back to substring match
    against BUILDER_META values.
    """
    from . import lovelace as ll
    try:
        resources = ll.list_resources(client) or []
    except Exception:
        return set()
    files = []
    for r in resources:
        url = r.get("url", "")
        # Trailing `?cache_buster` etc.
        stem = url.rsplit("/", 1)[-1].split("?", 1)[0]
        if stem.endswith(".js"): stem = stem[:-3]
        if stem.endswith(".mjs"): stem = stem[:-4]
        files.append(stem)
    installed: set[str] = set()
    for meta in cb.BUILDER_META.values():
        ct = meta.get("card_type", "")
        if not ct.startswith("custom:"):
            continue
        bare = ct[len("custom:"):]  # e.g. apexcharts-card
        if any(bare in f or f in bare for f in files):
            installed.add(ct)
    # Bundle-based plugins: if any of the bundle's filename fragments are
    # present, add ALL card types the bundle ships.
    for bundle_stem, card_types in _BUNDLE_CARDS.items():
        if any(bundle_stem in f for f in files):
            installed.update(card_types)
    return installed


def validate_card(card: dict, path: str = "",
                    *, installed: set[str] | None = None) -> list[dict]:
    """Validate a single card. Returns a list of issues."""
    issues: list[dict] = []
    if not isinstance(card, dict):
        return [{"severity": "error", "path": path,
                  "message": f"expected card dict, got {type(card).__name__}"}]
    t = card.get("type")
    if not isinstance(t, str):
        return [{"severity": "error", "path": path,
                  "message": "card has no 'type' field"}]

    # Custom-card resource check
    if t.startswith("custom:") and installed is not None and t not in installed:
        issues.append({
            "severity": "error", "path": path,
            "message": (f"{t!r} requires a HACS plugin that is not installed. "
                          f"Install via HACS Frontend or skip this card."),
        })

    # Required-field check via builder signature (WARNING, not error —
    # HA accepts some "required by builder" cards without those fields
    # if the card relies on tap_action / templates instead).
    reverse = _card_type_to_builder()
    builder_name = reverse.get(t)
    if builder_name:
        fn = cb.BUILDERS[builder_name]
        required = _required_kwargs(fn)
        for r in required:
            if r not in card:
                issues.append({
                    "severity": "warning", "path": path,
                    "message": (f"field {r!r} missing for {t!r} — builder "
                                  f"requires it, but HA may accept the card "
                                  f"if it uses tap_action/templates"),
                })
    elif not t.startswith("custom:") and t not in _KNOWN_NATIVE_TYPES:
        # Native unknown type — warn (HA may still know it; we just don't).
        issues.append({
            "severity": "warning", "path": path,
            "message": f"unknown native card type {t!r} (no builder registered)",
        })

    # Stray card_mod check
    issues.extend(_check_no_stray_card_mod(card, path=path))
    return issues


def validate_dashboard(dash: dict, *, client=None,
                          installed: set[str] | None = None) -> list[dict]:
    """Walk all card slots and validate each card.

    `client` — pass an HA client to auto-discover installed custom cards
    via `lovelace/resources`. Skip both `client` and `installed` to disable
    the resource check.
    """
    if client is not None and installed is None:
        installed = installed_card_types(client)

    issues: list[dict] = []
    for path, card in lc.walk_cards_strict(dash, with_path=True):
        issues.extend(validate_card(card, path=path, installed=installed))
    return issues


def format_issues(issues: list[dict]) -> str:
    """Pretty-print a list of issues for CLI/REPL display."""
    if not issues:
        return "✓ no issues"
    out = []
    for i in issues:
        sev = i["severity"].upper()
        path = i.get("path") or "<root>"
        out.append(f"[{sev}] {path}: {i['message']}")
    return "\n".join(out)
