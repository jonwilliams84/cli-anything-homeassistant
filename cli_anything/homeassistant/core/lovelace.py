"""Lovelace dashboard operations: list dashboards, read/write configs, manage resources.

All operations use the WebSocket API since Lovelace doesn't expose REST.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------- dashboards

def list_dashboards(client) -> list[dict]:
    """Return all Lovelace dashboards (the storage-mode + YAML-mode ones)."""
    data = client.ws_call("lovelace/dashboards/list")
    return list(data) if isinstance(data, list) else []


def get_dashboard_config(client, url_path: str | None = None) -> dict:
    """Return the full Lovelace config for a dashboard.

    `url_path=None` returns the main 'lovelace' dashboard config.
    """
    payload: dict[str, Any] = {}
    if url_path:
        payload["url_path"] = url_path
    return client.ws_call("lovelace/config", payload)


def save_dashboard_config(client, url_path: str, config: dict) -> Any:
    """Replace a dashboard's config. The frontend will refresh open clients."""
    if not url_path:
        raise ValueError("url_path is required")
    if not isinstance(config, dict):
        raise ValueError("config must be a dict")
    return client.ws_call(
        "lovelace/config/save",
        {"url_path": url_path, "config": config},
    )


# ---------------------------------------------------------------- resources

def list_resources(client) -> list[dict]:
    """Return Lovelace resources (registered JS/CSS modules for cards)."""
    data = client.ws_call("lovelace/resources")
    return list(data) if isinstance(data, list) else []


def delete_resource(client, resource_id: str) -> Any:
    """Remove a Lovelace resource by id."""
    if not resource_id:
        raise ValueError("resource_id is required")
    return client.ws_call(
        "lovelace/resources/delete",
        {"resource_id": resource_id},
    )


def create_resource(client, url: str, res_type: str = "module") -> Any:
    """Register a new Lovelace resource.

    `res_type` is one of "module", "css", "js" (per Lovelace API).
    """
    if not url:
        raise ValueError("url is required")
    return client.ws_call(
        "lovelace/resources/create",
        {"url": url, "res_type": res_type},
    )


def update_resource(client, resource_id: str, url: str, res_type: str = "module") -> Any:
    """Update a Lovelace resource's URL or type."""
    if not resource_id:
        raise ValueError("resource_id is required")
    return client.ws_call(
        "lovelace/resources/update",
        {"resource_id": resource_id, "url": url, "res_type": res_type},
    )
