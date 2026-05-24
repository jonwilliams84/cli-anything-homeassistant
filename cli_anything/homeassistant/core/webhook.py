"""Webhook triggers — `/api/webhook/<id>` plus cloudhook bindings.

Webhooks in Home Assistant are the *incoming* call surface: an automation
declares a ``trigger: webhook`` with an id, and any external system can POST
(or PUT/GET/HEAD if explicitly allowed) to ``/api/webhook/<id>`` to fire it.

Discovery is bolted together from three independent sources because HA does
not expose a single "list every webhook id" endpoint:

* ``webhook/list`` WS — registered by the ``webhook`` integration; covers
  every dynamically registered webhook (mobile_app, cloud, integrations).
* ``/config/automation/config/<aid>`` REST — for automations with
  ``trigger: webhook`` declared in YAML/storage.
* ``/cloud/cloudhooks`` WS — the Nabu Casa cloud relay (only when the
  cloud component is loaded and connected).

The triggering path (``trigger()``) is a thin wrapper over the REST
endpoint with an optional safety check that refuses to fire ids that the
registry does not currently know about — useful for catching typos.
"""

from __future__ import annotations

import secrets
from typing import Any, Optional


# ─────────────────────────────────────────────────────────────────── discovery

def list_registered(client) -> list[dict]:
    """Return the active webhook table via WebSocket ``webhook/list``.

    Each entry has ``webhook_id`` plus optional ``name``, ``domain`` (which
    integration owns the registration), ``local_only`` (whether external
    networks may call it), and ``allowed_methods``.
    """
    data = client.ws_call("webhook/list")
    return list(data) if isinstance(data, list) else []


def list_automation_webhooks(client) -> list[dict]:
    """Return one row per automation with a ``webhook`` trigger.

    Walks every automation entity, fetches its full config, and yields the
    embedded webhook trigger blocks. Returns ``[{"automation_id", "entity_id",
    "alias", "webhook_id", "allowed_methods", "local_only"}]``.
    """
    out: list[dict] = []
    states = client.get("states") or []
    if not isinstance(states, list):
        return out

    for st in states:
        if not isinstance(st, dict):
            continue
        eid = st.get("entity_id") or ""
        if not eid.startswith("automation."):
            continue
        attrs = st.get("attributes") or {}
        aid = attrs.get("id")
        if not aid:
            continue
        try:
            cfg = client.get(f"config/automation/config/{aid}")
        except Exception:
            continue
        if not isinstance(cfg, dict):
            continue
        triggers = cfg.get("trigger") or cfg.get("triggers") or []
        if isinstance(triggers, dict):
            triggers = [triggers]
        for t in triggers:
            if not isinstance(t, dict):
                continue
            platform = t.get("platform") or t.get("trigger")
            if platform != "webhook":
                continue
            wid = t.get("webhook_id")
            if not wid:
                continue
            out.append({
                "automation_id": aid,
                "entity_id": eid,
                "alias": cfg.get("alias") or attrs.get("friendly_name"),
                "webhook_id": wid,
                "allowed_methods": t.get("allowed_methods"),
                "local_only": t.get("local_only"),
            })
    return out


def list_mobile_app_webhooks(client) -> list[dict]:
    """Return one row per registered mobile_app device webhook.

    Uses ``mobile_app/list_for_user`` if available (newer HA) and falls back
    to scanning the device registry for entries owned by ``mobile_app``.
    """
    try:
        rows = client.ws_call("mobile_app/list_for_user") or []
        if isinstance(rows, list):
            return rows
    except Exception:
        pass
    return []


def list_webhooks(client, *,
                   include_automations: bool = True,
                   include_mobile: bool = True) -> dict:
    """Aggregate every webhook id this HA currently honours.

    Returns ``{"registered": [...], "automations": [...], "mobile_app": [...],
    "summary": {"total_unique": int}}``. Each section is a separate list so
    agents can join them on ``webhook_id``.
    """
    registered = list_registered(client)
    automations = list_automation_webhooks(client) if include_automations else []
    mobile = list_mobile_app_webhooks(client) if include_mobile else []

    ids: set[str] = set()
    for row in registered:
        if isinstance(row, dict) and row.get("webhook_id"):
            ids.add(row["webhook_id"])
    for row in automations:
        if row.get("webhook_id"):
            ids.add(row["webhook_id"])
    for row in mobile:
        if isinstance(row, dict) and row.get("webhook_id"):
            ids.add(row["webhook_id"])

    return {
        "registered": registered,
        "automations": automations,
        "mobile_app": mobile,
        "summary": {"total_unique": len(ids)},
    }


# ─────────────────────────────────────────────────────────────────── triggering

_ALLOWED_METHODS = {"POST", "PUT", "GET", "HEAD"}


def trigger(
    client,
    *,
    webhook_id: str,
    method: str = "POST",
    body: Any = None,
    guard_registered: bool = True,
) -> dict:
    """Hit ``/api/webhook/<webhook_id>``.

    *method* is upper-cased and must be one of POST/PUT/GET/HEAD. *body* may
    be a dict (JSON), a list (JSON), a string (sent verbatim — useful for
    raw text), or ``None``. *guard_registered* asks ``webhook/list`` first
    and refuses unknown ids — turn it off for fire-and-forget testing.

    Returns ``{"webhook_id", "method", "status", "ok", "response"}``.
    """
    if not webhook_id:
        raise ValueError("webhook_id is required")
    method = method.upper()
    if method not in _ALLOWED_METHODS:
        raise ValueError(
            f"method must be one of {sorted(_ALLOWED_METHODS)}, got {method!r}"
        )

    if guard_registered:
        known = {row.get("webhook_id") for row in list_registered(client)
                 if isinstance(row, dict)}
        if webhook_id not in known:
            raise ValueError(
                f"webhook_id {webhook_id!r} is not in the registered list; "
                f"pass guard_registered=False (--all in CLI) to fire anyway."
            )

    path = f"webhook/{webhook_id}"
    if method == "POST":
        resp = client.post(path, body)
        return {
            "webhook_id": webhook_id, "method": "POST",
            "ok": True, "response": resp,
        }

    # The HA REST client we use only exposes get/post/delete; for PUT/HEAD/GET
    # we drop through to the underlying requests session.
    sess = getattr(client, "session", None)
    base = getattr(client, "base_url", None)
    if sess is None or base is None:
        raise ValueError(
            "client lacks HTTP session — only POST is supported on this client"
        )
    url = f"{base}/api/webhook/{webhook_id}"
    timeout = getattr(client, "timeout", 30)
    if method == "PUT":
        resp = sess.put(url, json=body, timeout=timeout)
    elif method == "GET":
        resp = sess.get(url, timeout=timeout)
    else:  # HEAD
        resp = sess.head(url, timeout=timeout)
    try:
        decoded = resp.json() if resp.content else None
    except Exception:
        decoded = resp.text or None
    return {
        "webhook_id": webhook_id,
        "method": method,
        "status": resp.status_code,
        "ok": resp.ok,
        "response": decoded,
    }


# ────────────────────────────────────────────────────────────── id generation

def generate_id() -> dict:
    """Mint a fresh webhook id (32 url-safe characters, same as HA's RNG)."""
    return {"webhook_id": secrets.token_urlsafe(24)}


# ─────────────────────────────────────────────────────────────────── cloudhooks

def cloudhooks(client) -> list[dict]:
    """Return cloudhook bindings — webhook_id ↔ external cloudhook_url.

    Backed by ``cloud/cloudhooks`` (Nabu Casa cloud component). Empty list
    when the cloud is offline or not configured. The shape is a dict on the
    server side (id → url); we flatten it for easy consumption.
    """
    try:
        raw = client.ws_call("cloud/cloudhooks") or {}
    except Exception:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        out: list[dict] = []
        for wid, meta in raw.items():
            if isinstance(meta, dict):
                row = {"webhook_id": wid}
                row.update(meta)
                out.append(row)
            else:
                out.append({"webhook_id": wid, "cloudhook_url": meta})
        return out
    return []


def cloudhook_create(client, webhook_id: str) -> dict:
    """Create a Nabu Casa cloudhook for an existing local webhook id."""
    if not webhook_id:
        raise ValueError("webhook_id is required")
    return client.ws_call(
        "cloud/cloudhook/create",
        {"webhook_id": webhook_id},
    ) or {}


def cloudhook_delete(client, webhook_id: str) -> Any:
    """Delete a Nabu Casa cloudhook binding (local webhook remains)."""
    if not webhook_id:
        raise ValueError("webhook_id is required")
    return client.ws_call(
        "cloud/cloudhook/delete",
        {"webhook_id": webhook_id},
    )
