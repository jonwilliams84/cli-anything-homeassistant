"""Frontend metadata — sidebar panels, translations, icons, integration catalog.

Everything the Home Assistant frontend loads *about itself* before it can draw
a page, and which the harness previously had no way to read:

* **Panels** (``get_panels``) — the sidebar. This is the only authoritative
  list of what a dashboard URL resolves to: built-in panels (``config``,
  ``history``, ``developer-tools``), every Lovelace dashboard (including the
  auto-generated default), custom-panel modules shipped by integrations, and
  iframe panels. ``lovelace dashboards`` only sees the storage-mode ones.
* **Translations / icons** (``frontend/get_translations`` /
  ``frontend/get_icons``) — the display strings and mdi icons for entity
  components, states and services in a given language. This is how you turn a
  raw state value like ``not_home`` into the "Away" the UI shows.
* **Integration descriptions** (``integration/descriptions``) — the catalog
  behind the "Add integration" dialog: every integration HA knows about, its
  ``iot_class``, whether it has a config flow, and whether it is core or a
  custom component. ``system components`` only lists what is already loaded.

WS commands wrapped
-------------------
* ``get_panels``
* ``frontend/get_version``
* ``frontend/get_translations``
* ``frontend/get_icons``
* ``integration/descriptions``

Public API
----------
* :func:`panels`
* :func:`list_panels`
* :func:`get_panel`
* :func:`dashboards`
* :func:`frontend_version`
* :func:`translations`
* :func:`icons`
* :func:`integration_descriptions`
* :func:`list_integrations`
* :func:`find_integration`
"""

from __future__ import annotations

from typing import Any

WS_PANELS = "get_panels"
WS_VERSION = "frontend/get_version"
WS_TRANSLATIONS = "frontend/get_translations"
WS_ICONS = "frontend/get_icons"
WS_INTEGRATIONS = "integration/descriptions"

#: Categories accepted by ``frontend/get_icons``.
ICON_CATEGORIES = ("entity", "entity_component", "services")

#: The integration kinds ``integration/descriptions`` groups by.
INTEGRATION_KINDS = ("integration", "helper")


# ────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ────────────────────────────────────────────────────────────────────────────


def _require(value: str | None, name: str) -> str:
    if not value or not str(value).strip():
        raise ValueError(f"{name} is required")
    return str(value)


def _catalog_row(domain: str, meta: dict, *, kind: str, source: str, brand: str | None) -> dict:
    return {
        "domain": domain,
        "name": meta.get("name") or domain,
        "kind": kind,
        "source": source,
        "brand": brand,
        "integration_type": meta.get("integration_type"),
        "iot_class": meta.get("iot_class"),
        "config_flow": bool(meta.get("config_flow", False)),
        "single_config_entry": bool(meta.get("single_config_entry", False)),
    }


def _expand_entry(domain: str, meta: Any, *, kind: str, source: str) -> list[dict]:
    """Return the catalog rows for one entry, unpacking brands.

    HA groups related integrations under a *brand* — ``philips`` holds ``hue``,
    ``dynalite`` and ``philips_js``; ``mqtt`` holds ``mqtt``, ``manual_mqtt``
    and friends. A brand entry has no ``config_flow`` of its own, only a
    nested ``integrations`` mapping. Flattening it away is what makes
    ``--domain hue`` find anything at all.
    """
    meta = meta if isinstance(meta, dict) else {}
    nested = meta.get("integrations")
    if isinstance(nested, dict) and nested:
        return [
            _catalog_row(
                child_domain,
                child_meta if isinstance(child_meta, dict) else {},
                kind=kind,
                source=source,
                brand=domain,
            )
            for child_domain, child_meta in nested.items()
        ]
    return [_catalog_row(domain, meta, kind=kind, source=source, brand=None)]


def _panel_record(url_path: str, raw: Any) -> dict:
    """Normalize one panel entry, keeping the url_path as an explicit field."""
    raw = raw if isinstance(raw, dict) else {}
    return {
        "url_path": raw.get("url_path") or url_path,
        "component_name": raw.get("component_name"),
        "title": raw.get("title"),
        "icon": raw.get("icon"),
        "require_admin": bool(raw.get("require_admin", False)),
        "config_panel_domain": raw.get("config_panel_domain"),
        "config": raw.get("config"),
    }


# ────────────────────────────────────────────────────────────────────────────
# Panels
# ────────────────────────────────────────────────────────────────────────────


def panels(client) -> dict:
    """Return the raw ``get_panels`` mapping ``{url_path: panel}``.

    Panels requiring admin are omitted by HA for non-admin tokens, so an empty
    ``config`` entry is a permissions signal, not a missing feature.
    """
    return client.ws_call(WS_PANELS, {}) or {}


def list_panels(client, *, component_name: str | None = None) -> list[dict]:
    """Return panels as a sorted list, optionally filtered by component.

    ``component_name`` is the panel implementation — ``lovelace`` for
    dashboards, ``custom`` for third-party panels, ``iframe`` for embedded
    URLs, or a built-in like ``config`` / ``history``.
    """
    records = [_panel_record(key, value) for key, value in panels(client).items()]
    if component_name:
        records = [r for r in records if r["component_name"] == component_name]
    return sorted(records, key=lambda r: r["url_path"] or "")


def get_panel(client, url_path: str) -> dict:
    """Return the panel served at *url_path*.

    Raises
    ------
    ValueError
        If no such panel exists (or it is admin-only and this token is not).
    """
    url_path = _require(url_path, "url_path")
    raw = panels(client)
    if url_path not in raw:
        known = ", ".join(sorted(raw)[:12]) or "(none visible)"
        raise ValueError(f"no panel at url_path {url_path!r}. Visible panels: {known}")
    return _panel_record(url_path, raw[url_path])


def dashboards(client) -> list[dict]:
    """Return only the Lovelace panels — every dashboard the sidebar shows.

    Unlike ``lovelace/dashboards/list`` this includes the default
    (``lovelace``) dashboard, which has no storage-collection entry.
    """
    return list_panels(client, component_name="lovelace")


# ────────────────────────────────────────────────────────────────────────────
# Frontend build / translations / icons
# ────────────────────────────────────────────────────────────────────────────


def frontend_version(client) -> dict:
    """Return ``{"version": ...}`` — the pinned home-assistant-frontend build."""
    return client.ws_call(WS_VERSION, {}) or {}


def translations(
    client,
    *,
    language: str = "en",
    category: str = "entity_component",
    integration: str | list[str] | None = None,
    config_flow: bool | None = None,
) -> dict:
    """Return the translation resources for *category* in *language*.

    Common categories: ``entity_component`` (state strings + attribute names),
    ``entity``, ``state``, ``services``, ``title``, ``config``, ``options``.
    Narrow with *integration* to avoid pulling the whole catalog.
    """
    payload: dict[str, Any] = {
        "language": _require(language, "language"),
        "category": _require(category, "category"),
    }
    if integration is not None:
        payload["integration"] = (
            [integration] if isinstance(integration, str) else list(integration)
        )
    if config_flow is not None:
        payload["config_flow"] = bool(config_flow)
    result = client.ws_call(WS_TRANSLATIONS, payload) or {}
    return result.get("resources", {}) if isinstance(result, dict) else {}


def icons(
    client,
    *,
    category: str = "entity_component",
    integration: str | list[str] | None = None,
) -> dict:
    """Return the mdi icon resources for *category*.

    Raises
    ------
    ValueError
        If *category* is not one of :data:`ICON_CATEGORIES`.
    """
    category = _require(category, "category")
    if category not in ICON_CATEGORIES:
        raise ValueError(f"category must be one of {ICON_CATEGORIES}, got: {category!r}")
    payload: dict[str, Any] = {"category": category}
    if integration is not None:
        payload["integration"] = (
            [integration] if isinstance(integration, str) else list(integration)
        )
    result = client.ws_call(WS_ICONS, payload) or {}
    return result.get("resources", {}) if isinstance(result, dict) else {}


# ────────────────────────────────────────────────────────────────────────────
# Integration catalog
# ────────────────────────────────────────────────────────────────────────────


def integration_descriptions(client) -> dict:
    """Return the raw catalog: ``{"core": {...}, "custom": {...}}``."""
    return client.ws_call(WS_INTEGRATIONS, {}) or {}


def list_integrations(
    client,
    *,
    kind: str | None = None,
    source: str | None = None,
    config_flow_only: bool = False,
    iot_class: str | None = None,
) -> list[dict]:
    """Flatten the catalog into one sorted row per integration.

    Parameters
    ----------
    kind:
        ``integration`` or ``helper`` (default: both).
    source:
        ``core`` or ``custom`` (default: both). ``custom`` is the HACS /
        manually-installed set — useful as a supply-chain inventory.
    config_flow_only:
        Only integrations that can be added from the UI (and therefore via
        ``config-flow start``).
    iot_class:
        e.g. ``local_push``, ``cloud_polling``.

    Brands (``philips``, ``google``, ``mqtt``, …) are unpacked into their
    member integrations, each row carrying the ``brand`` it came from.
    """
    if kind is not None and kind not in INTEGRATION_KINDS:
        raise ValueError(f"kind must be one of {INTEGRATION_KINDS}, got: {kind!r}")
    if source is not None and source not in ("core", "custom"):
        raise ValueError(f"source must be 'core' or 'custom', got: {source!r}")

    raw = integration_descriptions(client)
    rows: list[dict] = []
    for src in ("core", "custom"):
        if source is not None and src != source:
            continue
        bucket = raw.get(src) or {}
        if not isinstance(bucket, dict):
            continue
        for group in INTEGRATION_KINDS:
            if kind is not None and group != kind:
                continue
            entries = bucket.get(group) or {}
            if not isinstance(entries, dict):
                continue
            for domain, meta in entries.items():
                rows.extend(_expand_entry(domain, meta, kind=group, source=src))
    if config_flow_only:
        rows = [r for r in rows if r["config_flow"]]
    if iot_class is not None:
        rows = [r for r in rows if r["iot_class"] == iot_class]
    return sorted(rows, key=lambda r: (r["domain"], r["kind"]))


def find_integration(client, domain: str) -> dict | None:
    """Return the catalog row for *domain*, or ``None`` when HA never heard of it."""
    domain = _require(domain, "domain")
    for row in list_integrations(client):
        if row["domain"] == domain:
            return row
    return None
