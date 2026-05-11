"""Subentry management for config-entries — list / show / reconfigure.

Many modern HA integrations expose sub-configurations on a single config
entry: Google Generative AI Conversation has separate subentries for
``conversation``, ``ai_task_data``, ``stt`` and ``tts``; Ollama has
``conversation`` subentries; the cloud integration has a per-feature one.
Each subentry has its own option flow that's distinct from the parent
entry's options flow.

The endpoints used:
  - WS   ``config_entries/subentries/list``
         → list subentries for a parent entry
  - REST ``POST /api/config/config_entries/subentries/flow``
         with body ``{handler: [entry_id, subentry_type], subentry_id,
                      source: "reconfigure"}``
         → init the reconfigure flow, returns ``flow_id`` + ``data_schema``
           where each field has ``description.suggested_value`` = current
  - REST ``POST /api/config/config_entries/subentries/flow/<flow_id>``
         with the merged form payload → applies (response is
         ``{type: "abort", reason: "reconfigure_successful"}``)
  - REST ``DELETE /api/config/config_entries/subentries/flow/<flow_id>``
         → cleanly aborts a flow that was just opened to read values
"""

from __future__ import annotations

from typing import Any, Optional


def list_subentries(client, entry_id: str) -> list[dict]:
    """List all subentries of a parent config-entry.

    Each row: {subentry_id, subentry_type, title, data?, unique_id?}.
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    data = client.ws_call("config_entries/subentries/list",
                            {"entry_id": entry_id})
    return list(data) if isinstance(data, list) else []


def find_subentry(client, entry_id: str, ident: str) -> Optional[dict]:
    """Find a subentry by id OR by title (case-insensitive)."""
    if not ident:
        return None
    rows = list_subentries(client, entry_id)
    ident_l = ident.lower()
    for r in rows:
        if r.get("subentry_id") == ident:
            return r
        if (r.get("title") or "").lower() == ident_l:
            return r
    return None


def list_all(client, *,
              subentry_type: Optional[str] = None,
              title_pattern: Optional[str] = None,
              domain: Optional[str] = None) -> list[dict]:
    """List subentries across EVERY config entry.

    Useful when you don't know which integration owns a subentry. Each row is
    a regular subentry record with `entry_id`, `entry_title`, `entry_domain`
    keys merged in so the caller can drill back to the parent.

    Filters:
      subentry_type   exact match on subentry_type (e.g. "ai_task_data")
      title_pattern   substring match on subentry title (case-insensitive)
      domain          restrict to parent entries in this integration domain
    """
    # Enumerate every config entry, then list its subentries.
    entries = client.ws_call("config_entries/get") or []
    if not isinstance(entries, list):
        return []
    if domain:
        entries = [e for e in entries if e.get("domain") == domain]
    p = (title_pattern or "").lower()
    out: list[dict] = []
    for e in entries:
        eid = e.get("entry_id")
        if not eid:
            continue
        try:
            subs = client.ws_call("config_entries/subentries/list",
                                    {"entry_id": eid}) or []
        except Exception:
            continue
        for s in subs:
            if subentry_type and s.get("subentry_type") != subentry_type:
                continue
            if p and p not in (s.get("title") or "").lower():
                continue
            out.append({
                **s,
                "entry_id": eid,
                "entry_title": e.get("title"),
                "entry_domain": e.get("domain"),
            })
    return out


def _init_reconfigure(client, *, entry_id: str, subentry_id: str,
                        subentry_type: str) -> dict:
    """Open a reconfigure flow and return its first-step descriptor."""
    return client.post(
        "config/config_entries/subentries/flow",
        {
            "handler": [entry_id, subentry_type],
            "subentry_id": subentry_id,
            "source": "reconfigure",
        },
    )


def _abort_flow(client, flow_id: str) -> None:
    """Close a subentry flow cleanly. Swallows errors — best-effort cleanup."""
    if not flow_id:
        return
    try:
        client.delete(f"config/config_entries/subentries/flow/{flow_id}")
    except Exception:
        pass


def _current_values_from_schema(form: dict) -> dict:
    """Extract {field_name: suggested_value} from a form descriptor."""
    out: dict[str, Any] = {}
    for f in form.get("data_schema", []) or []:
        if not isinstance(f, dict) or "name" not in f:
            continue
        desc = f.get("description") or {}
        if "suggested_value" in desc:
            out[f["name"]] = desc["suggested_value"]
    return out


def read_subentry(client, entry_id: str, ident: str) -> dict:
    """Return the current options of a subentry.

    `ident` is either the subentry_id OR its title (case-insensitive). The
    method opens a reconfigure flow to read the suggested values, then
    cleanly aborts the flow so it doesn't linger.

    Returns: {entry_id, subentry_id, subentry_type, title, options}.
    """
    sub = find_subentry(client, entry_id, ident)
    if not sub:
        raise KeyError(f"no subentry matching {ident!r} on entry {entry_id!r}")
    form = _init_reconfigure(
        client,
        entry_id=entry_id,
        subentry_id=sub["subentry_id"],
        subentry_type=sub["subentry_type"],
    )
    options = _current_values_from_schema(form)
    _abort_flow(client, form.get("flow_id"))
    return {
        "entry_id": entry_id,
        "subentry_id": sub["subentry_id"],
        "subentry_type": sub["subentry_type"],
        "title": sub.get("title"),
        "options": options,
    }


def reconfigure(client, entry_id: str, ident: str,
                 overrides: dict, *,
                 dry_run: bool = False) -> dict:
    """Reconfigure a subentry by merging `overrides` into the current options.

    Fields not in `overrides` are preserved at their current value. The merge
    is a shallow dict update; nested dicts are replaced wholesale (HA's
    schemas don't usually nest).
    """
    if not isinstance(overrides, dict):
        raise ValueError("overrides must be a dict")
    sub = find_subentry(client, entry_id, ident)
    if not sub:
        raise KeyError(f"no subentry matching {ident!r} on entry {entry_id!r}")

    form = _init_reconfigure(
        client,
        entry_id=entry_id,
        subentry_id=sub["subentry_id"],
        subentry_type=sub["subentry_type"],
    )
    flow_id = form.get("flow_id")
    current = _current_values_from_schema(form)
    merged = {**current, **overrides}

    if dry_run:
        _abort_flow(client, flow_id)
        return {
            "dry_run": True,
            "subentry_id": sub["subentry_id"],
            "title": sub.get("title"),
            "current": current,
            "would_set": overrides,
            "merged": merged,
        }

    resp = client.post(
        f"config/config_entries/subentries/flow/{flow_id}",
        merged,
    )
    return {
        "subentry_id": sub["subentry_id"],
        "title": sub.get("title"),
        "merged": merged,
        "response": resp,
        "ok": isinstance(resp, dict) and resp.get("reason") == "reconfigure_successful",
    }
