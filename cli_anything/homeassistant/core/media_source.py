"""Media source operations for Home Assistant.

Home Assistant exposes media source operations via WebSocket commands:
   - ``media_source/browse_media``     — browse available media
   - ``media_source/resolve_media``    — resolve media to a playable URL
   - ``media_source/local_source/remove`` — remove a local media file

The browse_media response contains media hierarchy with fields like
domain, identifier, media_class, media_content_type, title, can_play, can_expand.

The resolve_media response contains {url, mime_type} for playback.
"""

from __future__ import annotations


# ════════════════════════════════════════════════════════════════════════
# browse_media — WS media_source/browse_media
# ════════════════════════════════════════════════════════════════════════

def browse_media(client, *, media_content_id: str | None = None) -> dict:
    """Browse available media by media content ID.

    ``media_content_id`` — the content ID to browse (optional).
                           Pass None (default) to browse the root.

    Returns a dict with media hierarchy information.
    Uses WS command ``media_source/browse_media``.
    """
    payload: dict = {}
    if media_content_id is not None:
        payload["media_content_id"] = media_content_id
    return client.ws_call("media_source/browse_media", payload)


# ════════════════════════════════════════════════════════════════════════
# resolve_media — WS media_source/resolve_media
# ════════════════════════════════════════════════════════════════════════

def resolve_media(client, *, media_content_id: str) -> dict:
    """Resolve media to a playable URL.

    ``media_content_id`` — the content ID to resolve (required, non-empty).

    Returns a dict with {url, mime_type}.
    Uses WS command ``media_source/resolve_media``.
    """
    if not media_content_id:
        raise ValueError("media_content_id must be a non-empty string")
    payload: dict = {"media_content_id": media_content_id}
    return client.ws_call("media_source/resolve_media", payload)


# ════════════════════════════════════════════════════════════════════════
# local_source_remove — WS media_source/local_source/remove
# ════════════════════════════════════════════════════════════════════════

def local_source_remove(client, *, media_content_id: str) -> dict:
    """Remove a local media file.

    ``media_content_id`` — the content ID of the file to remove
                           (required, non-empty).

    Uses WS command ``media_source/local_source/remove``.
    """
    if not media_content_id:
        raise ValueError("media_content_id must be a non-empty string")
    payload: dict = {"media_content_id": media_content_id}
    return client.ws_call("media_source/local_source/remove", payload)
