"""image.* domain — snapshots, image_proxy URLs, signed access.

Home Assistant exposes image entities (``image.*``) for any integration
that provides a *currently-known* visual frame: weather radar tiles, AI
snapshot bots, IP camera last-frame cache, etc. Every image entity has a
companion HTTP endpoint at ``/api/image_proxy/<entity_id>`` that returns
the current frame as raw bytes.

This module wraps:

* listing every image entity with its state
* downloading the current frame to disk (signed or direct auth)
* getting a signed proxy URL for offline / external use
* subscribing to fresh-frame events for a given image entity
"""

from __future__ import annotations

import os
import threading
from typing import Any, Optional

from cli_anything.homeassistant.core import auth_tokens as auth_tokens_core


_DEFAULT_SUBSCRIBE_TIMEOUT = 10


# ─────────────────────────────────────────────────────────────────── listing

def list_image_entities(client, *, include_attributes: bool = False) -> list[dict]:
    """Return every ``image.*`` entity state.

    When *include_attributes* is False (default), strip the ``attributes``
    dict so the output stays small — image entity attribute payloads include
    base64 thumbnails on some integrations.
    """
    states = client.get("states") or []
    out: list[dict] = []
    for s in states:
        if not isinstance(s, dict):
            continue
        eid = s.get("entity_id") or ""
        if not eid.startswith("image."):
            continue
        if include_attributes:
            out.append(s)
        else:
            row = {k: v for k, v in s.items() if k != "attributes"}
            attrs = s.get("attributes") or {}
            row["friendly_name"] = attrs.get("friendly_name")
            row["entity_picture"] = attrs.get("entity_picture")
            out.append(row)
    return out


def get_image_entity(client, entity_id: str) -> dict:
    """Return the full state record for one image entity."""
    if not entity_id:
        raise ValueError("entity_id is required")
    if not entity_id.startswith("image."):
        raise ValueError(f"{entity_id!r} is not an image.* entity")
    return client.get(f"states/{entity_id}") or {}


# ────────────────────────────────────────────────────────────── proxy URLs

def proxy_url(client, *, entity_id: str,
               signed: bool = True, expires: int = 30) -> dict:
    """Build the ``/api/image_proxy/<entity_id>`` URL.

    Returns ``{"entity_id", "path", "url", "signed", "expires"}``.

    When *signed* is True (default), call ``auth/sign_path`` to mint a
    one-shot URL — useful for embedding in scripts that fetch unauthenticated
    or in HTML that an external viewer will load. When False, the path is
    plain and the caller must add an ``Authorization: Bearer …`` header.
    """
    if not entity_id:
        raise ValueError("entity_id is required")
    if not entity_id.startswith("image."):
        raise ValueError(f"{entity_id!r} is not an image.* entity")

    path = f"/api/image_proxy/{entity_id}"
    base = getattr(client, "base_url", "") or ""

    if not signed:
        return {
            "entity_id": entity_id, "path": path,
            "url": f"{base}{path}" if base else path,
            "signed": False, "expires": None,
        }

    result = auth_tokens_core.sign_path(client, path=path, expires=expires) or {}
    signed_path = result.get("path") or path
    return {
        "entity_id": entity_id,
        "path": signed_path,
        "url": f"{base}{signed_path}" if base else signed_path,
        "signed": True,
        "expires": expires,
    }


# ──────────────────────────────────────────────────────────────── snapshot

def snapshot(
    client,
    *,
    entity_id: str,
    output_path: str,
    overwrite: bool = False,
    signed: bool = False,
    expires: int = 30,
) -> dict:
    """Fetch the current frame and write it to *output_path*.

    Returns ``{"entity_id", "output_path", "bytes", "content_type"}``.

    *signed* uses ``auth/sign_path`` + an unauthenticated GET; *direct*
    sends the existing Authorization header. Both should produce identical
    bytes — the signed path is useful when the calling client's auth header
    contains a scope that's been narrowed.
    """
    if not entity_id:
        raise ValueError("entity_id is required")
    if not entity_id.startswith("image."):
        raise ValueError(f"{entity_id!r} is not an image.* entity")
    if not output_path:
        raise ValueError("output_path is required")
    if os.path.exists(output_path) and not overwrite:
        raise FileExistsError(
            f"{output_path} already exists — pass overwrite=True (--overwrite)"
        )

    sess = getattr(client, "session", None)
    base = getattr(client, "base_url", None)
    if sess is None or base is None:
        raise ValueError("client lacks an HTTP session — cannot snapshot binary")
    timeout = getattr(client, "timeout", 30)

    if signed:
        result = auth_tokens_core.sign_path(
            client, path=f"/api/image_proxy/{entity_id}", expires=expires,
        ) or {}
        signed_path = result.get("path")
        if not signed_path:
            raise RuntimeError("auth/sign_path returned no signed path")
        url = f"{base}{signed_path}"
        # Use a header-free request — the signature carries auth.
        headers = {k: v for k, v in sess.headers.items() if k.lower() != "authorization"}
        resp = sess.get(url, headers=headers, timeout=timeout, stream=True)
    else:
        url = f"{base}/api/image_proxy/{entity_id}"
        resp = sess.get(url, timeout=timeout, stream=True)

    if not resp.ok:
        raise RuntimeError(
            f"GET /api/image_proxy/{entity_id} -> {resp.status_code}: "
            f"{resp.text[:300] if resp.content else ''}"
        )

    parent = os.path.dirname(os.path.abspath(output_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    total = 0
    with open(output_path, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                fh.write(chunk)
                total += len(chunk)
    return {
        "entity_id": entity_id,
        "output_path": os.path.abspath(output_path),
        "bytes": total,
        "content_type": resp.headers.get("Content-Type"),
    }


# ────────────────────────────────────────────────────────── live updates

def subscribe_updates(
    client, *,
    entity_id: str,
    timeout: int = _DEFAULT_SUBSCRIBE_TIMEOUT,
) -> list[dict]:
    """Listen for state_changed events for ENTITY_ID for up to *timeout* seconds.

    Returns the list of captured events; useful for snapshotting "did a new
    frame arrive in the next 30 seconds?". Each event includes the new state
    hash so consumers can decide whether to refetch.
    """
    if not entity_id:
        raise ValueError("entity_id is required")
    if not entity_id.startswith("image."):
        raise ValueError(f"{entity_id!r} is not an image.* entity")
    if timeout <= 0:
        raise ValueError("timeout must be positive")

    captured: list[dict] = []
    stop = threading.Event()
    timer = threading.Timer(timeout, stop.set)
    timer.daemon = True
    timer.start()
    try:
        def on_event(ev: Any) -> None:
            if not isinstance(ev, dict):
                return
            data = ev.get("data") or {}
            if data.get("entity_id") == entity_id:
                captured.append(ev)

        client.ws_subscribe(
            "subscribe_events", {"event_type": "state_changed"},
            on_event, stop,
        )
    finally:
        timer.cancel()
        stop.set()
    return captured
