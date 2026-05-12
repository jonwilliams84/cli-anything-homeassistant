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


def save_dashboard_config(client, url_path: str, config: dict, *,
                            snapshot: bool = False,
                            snapshot_dir: str | None = None) -> Any:
    """Replace a dashboard's config. The frontend will refresh open clients.

    Pass `snapshot=True` to write a JSON snapshot of the CURRENT dashboard
    state (before the save) to `snapshot_dir` (default
    ``.cli-anything-homeassistant/snapshots/``). The snapshot file is named
    ``<url_path>-<YYYYMMDD-HHMMSS>.json`` and includes the pre-save config
    plus the save metadata so it can be restored verbatim by
    ``restore_dashboard_snapshot``.

    Recommended pattern for risky edits:

        save_dashboard_config(client, "jon-mobile", new_cfg, snapshot=True)
    """
    if not url_path:
        raise ValueError("url_path is required")
    if not isinstance(config, dict):
        raise ValueError("config must be a dict")
    if snapshot:
        try:
            current = get_dashboard_config(client, url_path)
        except Exception as e:
            # Don't block the save just because snapshot failed.
            current = {"_error": f"snapshot read failed: {e}"}
        _write_snapshot(url_path, current, snapshot_dir)
    return client.ws_call(
        "lovelace/config/save",
        {"url_path": url_path, "config": config},
    )


# ---------------------------------------------------------------- snapshots

def _snapshot_dir(snapshot_dir: str | None) -> str:
    import os
    return snapshot_dir or os.path.expanduser(
        "~/.cli-anything-homeassistant/snapshots")


def _write_snapshot(url_path: str, config: dict,
                      snapshot_dir: str | None = None) -> str:
    import datetime as _dt
    import json
    import os
    target = _snapshot_dir(snapshot_dir)
    os.makedirs(target, exist_ok=True)
    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    fname = f"{url_path}-{ts}.json"
    path = os.path.join(target, fname)
    with open(path, "w") as f:
        json.dump({"url_path": url_path, "timestamp": ts,
                    "config": config}, f, indent=2)
    return path


def snapshot_dashboard(client, url_path: str | None = None,
                        snapshot_dir: str | None = None) -> str:
    """Write the current state of a dashboard to a JSON snapshot file.

    Returns the absolute path of the written file. Call this BEFORE any
    risky edit so you have a guaranteed restore point.
    """
    cfg = get_dashboard_config(client, url_path)
    # `url_path=None` resolves to the main lovelace dashboard; we save it
    # under "lovelace" as a stable filename.
    key = url_path or "lovelace"
    return _write_snapshot(key, cfg, snapshot_dir)


def list_snapshots(snapshot_dir: str | None = None,
                     url_path: str | None = None) -> list[dict]:
    """List snapshot files in `snapshot_dir`. Filter by `url_path` if given.

    Each entry: ``{path, url_path, timestamp, bytes}`` — sorted newest first.
    """
    import os
    target = _snapshot_dir(snapshot_dir)
    if not os.path.isdir(target):
        return []
    out = []
    for name in sorted(os.listdir(target), reverse=True):
        if not name.endswith(".json"):
            continue
        path = os.path.join(target, name)
        # Filenames are <url_path>-<ts>.json — split on the LAST hyphen
        # that separates url_path from the timestamp. The timestamp is
        # always 15 chars: YYYYMMDD-HHMMSS (with one hyphen). So split on
        # the LAST 16 chars (-YYYYMMDD-HHMMSS).
        stem = name[:-5]  # strip .json
        # ts is the last 15 chars (8 date + 1 dash + 6 time).
        if len(stem) >= 16 and stem[-16] == "-":
            up = stem[:-16]
            ts = stem[-15:]
        else:
            up = stem
            ts = ""
        if url_path is not None and up != url_path:
            continue
        out.append({"path": path, "url_path": up, "timestamp": ts,
                      "bytes": os.path.getsize(path)})
    return out


def restore_dashboard_snapshot(client, snapshot_path: str,
                                  *, url_path_override: str | None = None) -> Any:
    """Restore a dashboard from a snapshot file written by
    ``snapshot_dashboard``/``save_dashboard_config(snapshot=True)``.

    `url_path_override` lets you restore a snapshot under a different
    dashboard URL (useful for testing).
    """
    import json
    with open(snapshot_path) as f:
        data = json.load(f)
    cfg = data.get("config")
    if not isinstance(cfg, dict):
        raise ValueError(f"snapshot {snapshot_path!r} has no `config` dict")
    target = url_path_override or data.get("url_path")
    if not target or target == "lovelace":
        target = url_path_override  # cannot restore main dashboard without explicit url_path
    if not target:
        raise ValueError("snapshot has no url_path and none was provided")
    return client.ws_call(
        "lovelace/config/save",
        {"url_path": target, "config": cfg},
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
