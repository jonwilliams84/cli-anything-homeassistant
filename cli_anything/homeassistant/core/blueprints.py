"""Blueprints — reusable automation/script templates.

WS namespace: `blueprint/*`. Blueprints live under `blueprints/<domain>/<path>`
in the HA config directory. The API lets you list, import (from URL/file),
save, delete, and substitute (render) without restarting HA.

Domain values: 'automation', 'script'.
"""

from __future__ import annotations

from typing import Any, Optional

VALID_DOMAINS = ("automation", "script")


def _check_domain(domain: str) -> None:
    if domain not in VALID_DOMAINS:
        raise ValueError(f"domain must be one of {VALID_DOMAINS}")


def list_blueprints(client, domain: str) -> dict:
    """List installed blueprints for `domain`.

    Returns a dict {blueprint_path: {metadata, inputs, ...}}.
    """
    _check_domain(domain)
    data = client.ws_call("blueprint/list", {"domain": domain})
    return data if isinstance(data, dict) else {}


def show(client, domain: str, path: str) -> Optional[dict]:
    """Return one blueprint's full record by path. Best-effort lookup."""
    _check_domain(domain)
    bps = list_blueprints(client, domain)
    return bps.get(path) if isinstance(bps, dict) else None


def import_blueprint(client, *, url: str) -> dict:
    """Import a blueprint from a URL (GitHub, gist, raw file, …).

    Returns {raw_data, suggested_filename, blueprint, exists}.
    """
    if not url:
        raise ValueError("url is required")
    return client.ws_call("blueprint/import", {"url": url}) or {}


def save_imported(client, *, domain: str, path: str,
                    yaml_text: str, source_url: Optional[str] = None) -> dict:
    """Persist an imported blueprint to `blueprints/<domain>/<path>.yaml`."""
    _check_domain(domain)
    if not path:
        raise ValueError("path is required")
    if not yaml_text:
        raise ValueError("yaml_text is required")
    payload: dict[str, Any] = {
        "domain": domain,
        "path": path,
        "yaml": yaml_text,
    }
    if source_url:
        payload["source_url"] = source_url
    return client.ws_call("blueprint/save", payload) or {}


def delete(client, *, domain: str, path: str) -> Any:
    _check_domain(domain)
    if not path:
        raise ValueError("path is required")
    return client.ws_call("blueprint/delete", {
        "domain": domain, "path": path,
    })


def substitute(client, *, domain: str, path: str,
                user_input: dict) -> dict:
    """Render a blueprint with the supplied inputs, returning the resulting
    automation/script body."""
    _check_domain(domain)
    if not path:
        raise ValueError("path is required")
    if not isinstance(user_input, dict):
        raise ValueError("user_input must be a dict")
    return client.ws_call("blueprint/substitute", {
        "domain": domain, "path": path, "input": user_input,
    }) or {}
