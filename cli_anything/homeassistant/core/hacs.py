"""HACS (Home Assistant Community Store) repository management.

Wraps the WebSocket API the HACS frontend itself uses:

  - ``hacs/info``                — overall HACS status (version, stage, categories)
  - ``hacs/repositories/list``   — every known repo (default ~3000, with ~30-100 installed)
  - ``hacs/repository/info``     — full metadata for one repo
  - ``hacs/repository/download`` — install (download files + register Lovelace resource)
  - ``hacs/repository/remove``   — uninstall (delete files + remove resource registration)
  - ``hacs/repository/refresh``  — refresh metadata from upstream
"""

from __future__ import annotations

from typing import Any, Optional


def info(client) -> dict:
    """Return HACS global info (version, stage, startup flag, lovelace_mode)."""
    return client.ws_call("hacs/info") or {}


def list_repos(client, *,
                installed_only: bool = False,
                category: Optional[str] = None,
                pattern: Optional[str] = None) -> list[dict]:
    """List repositories known to HACS.

    `installed_only=True`  → only the ones with files on disk
    `category`             → one of integration / plugin / theme / appdaemon /
                             python_script / netdaemon (depends on user config)
    `pattern`              → substring filter (case-insensitive) on name OR full_name
    """
    data = client.ws_call("hacs/repositories/list")
    rows = data if isinstance(data, list) else []
    out: list[dict] = []
    p = (pattern or "").lower()
    for r in rows:
        if installed_only and not r.get("installed"):
            continue
        if category and r.get("category") != category:
            continue
        if p:
            haystack = ((r.get("full_name") or "") + " " + (r.get("name") or "")).lower()
            if p not in haystack:
                continue
        out.append(r)
    return out


def find_repo(client, ident: str) -> Optional[dict]:
    """Resolve a repo by id, full_name (`user/repo`), or just `repo` short name."""
    if not ident:
        return None
    ident_l = ident.lower()
    rows = client.ws_call("hacs/repositories/list") or []
    if not isinstance(rows, list):
        return None
    # Exact matches first (id, then full_name)
    for r in rows:
        if str(r.get("id")) == ident:
            return r
    for r in rows:
        if (r.get("full_name") or "").lower() == ident_l:
            return r
    # Short name match (the part after the slash) — only if unique
    short_matches = [r for r in rows
                     if (r.get("full_name") or "").lower().split("/")[-1] == ident_l]
    if len(short_matches) == 1:
        return short_matches[0]
    if len(short_matches) > 1:
        raise ValueError(
            f"{ident!r} matches multiple repos: "
            + ", ".join(r.get("full_name") for r in short_matches)
            + ". Use the full user/repo form."
        )
    # Loose substring match — only if unique among INSTALLED repos
    installed_substr = [r for r in rows
                        if r.get("installed")
                        and ident_l in (r.get("full_name") or "").lower()]
    if len(installed_substr) == 1:
        return installed_substr[0]
    return None


def show(client, ident: str) -> dict:
    """Return one repo's full record."""
    repo = find_repo(client, ident)
    if not repo:
        raise KeyError(f"no HACS repo matching {ident!r}")
    return repo


def install(client, ident: str, *, version: Optional[str] = None) -> Any:
    """Install / download a HACS repo. If already installed, this re-downloads
    (HACS treats it as a refresh + redownload to the requested version)."""
    repo = find_repo(client, ident)
    if not repo:
        raise KeyError(f"no HACS repo matching {ident!r}")
    payload: dict[str, Any] = {"repository": str(repo["id"])}
    if version:
        payload["version"] = version
    return client.ws_call("hacs/repository/download", payload)


def remove(client, ident: str) -> Any:
    """Uninstall a HACS repo — deletes the files under local_path AND removes
    any Lovelace resource registration (for plugin repos)."""
    repo = find_repo(client, ident)
    if not repo:
        raise KeyError(f"no HACS repo matching {ident!r}")
    return client.ws_call("hacs/repository/remove",
                            {"repository": str(repo["id"])})


def refresh(client, ident: str) -> Any:
    """Refresh upstream metadata for a repo (re-check versions, README, etc)."""
    repo = find_repo(client, ident)
    if not repo:
        raise KeyError(f"no HACS repo matching {ident!r}")
    return client.ws_call("hacs/repository/refresh",
                            {"repository": str(repo["id"])})
