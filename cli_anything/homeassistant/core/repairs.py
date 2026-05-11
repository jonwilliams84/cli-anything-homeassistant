"""Repairs feed — what does HA think is wrong right now?

The UI's "Repairs" page maps to WS `repairs/list_issues`. Each issue has a
severity (`error` / `warning`), a domain, breaks_in_ha_version, plus a
translation_key + placeholders that render the human-readable title.

We expose:
  - list (with optional severity / domain / include-dismissed filters)
  - show (full detail by issue_id)
  - ignore  (`repairs/ignore` — dismiss without fixing)
  - fix    (start the fix-flow → returns a flow descriptor; subsequent
            steps go via the standard config-entries flow API)
"""

from __future__ import annotations

from typing import Any, Optional


def list_issues(client, *,
                 severity: Optional[str] = None,
                 domain: Optional[str] = None,
                 include_dismissed: bool = False) -> list[dict]:
    """List active (non-dismissed by default) repair issues."""
    data = client.ws_call("repairs/list_issues") or {}
    raw = data.get("issues") if isinstance(data, dict) else None
    items = raw if isinstance(raw, list) else []
    out: list[dict] = []
    for it in items:
        if not include_dismissed and it.get("dismissed_version"):
            continue
        if severity and it.get("severity") != severity:
            continue
        if domain and it.get("domain") != domain:
            continue
        out.append(it)
    return out


def show(client, issue_id: str, *, domain: Optional[str] = None) -> Optional[dict]:
    """Return one issue by `issue_id` (and optionally narrow by domain).

    Repair issue_ids are not globally unique — same id can exist under
    multiple domains, so pass `domain` if you have it for an exact match.
    """
    if not issue_id:
        raise ValueError("issue_id is required")
    for it in list_issues(client, include_dismissed=True):
        if it.get("issue_id") != issue_id:
            continue
        if domain and it.get("domain") != domain:
            continue
        return it
    return None


def ignore(client, *, issue_id: str, domain: str,
            ignore_value: bool = True) -> Any:
    """Dismiss an issue. Pass `ignore_value=False` to un-dismiss."""
    if not issue_id or not domain:
        raise ValueError("issue_id and domain are required")
    return client.ws_call("repairs/ignore", {
        "issue_id": issue_id,
        "domain": domain,
        "ignore": bool(ignore_value),
    })


def fix(client, *, issue_id: str, domain: str) -> dict:
    """Start the fix-flow for an issue. Returns the flow descriptor.

    Subsequent flow steps can be driven via the standard
    `config_entry options-configure` machinery on the returned `flow_id`.
    """
    if not issue_id or not domain:
        raise ValueError("issue_id and domain are required")
    return client.post("repairs/issues/fix", {
        "handler": domain,
        "issue_id": issue_id,
    })
