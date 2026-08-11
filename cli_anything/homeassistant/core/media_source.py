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


def search_media(
    client,
    *,
    query: str,
    media_content_id: str = "",
    filter_classes: list[str] | None = None,
) -> dict:
    """Search the media sources instead of walking `browse` by hand.

    `browse_media` returns one folder's children, so finding a track meant
    recursing the whole tree client-side — both slow and a reimplementation of
    something HA already does.

    AN UNSUPPORTED SOURCE RAISES; IT DOES NOT RETURN AN EMPTY LIST. That is the
    opposite of what this function first assumed, and it was measured:

        (no scope, i.e. the root)        -> search_not_supported   [ERROR]
        media-source://frigate           -> search_not_supported   [ERROR]
        media-source://music_assistant   -> search_media_failed    [ERROR]
        media-source://media_source      -> {"result": []}         [OK, empty]

    So an unscoped search is an error on most instances rather than a broad
    search, and the three outcomes have to be told apart: `search_not_supported`
    means ask somewhere else, `search_media_failed` means the source tried and
    could not, and an empty result means nobody matched. This re-raises the
    first with the scope named and a scope that does work suggested, because
    HA's own message is two words.
    """
    if not query:
        raise ValueError("query is required")
    payload: dict = {"search_query": query, "media_content_id": media_content_id}
    if filter_classes:
        payload["filter_classes"] = list(filter_classes)
    try:
        data = client.ws_call("media_source/search_media", payload) or {}
    except Exception as exc:  # noqa: BLE001 - re-raised below with a better message
        text = str(exc)
        if "search_not_supported" in text:
            raise ValueError(
                f"{media_content_id or 'the media-source root'} does not support "
                "searching. Scope the search to a source that does — "
                "`media search <query> --scope media-source://media_source` works "
                "on a stock instance. Run `media browse` for the sources here."
            ) from exc
        raise
    result = data.get("result") if isinstance(data, dict) else None
    items = (result or {}).get("result") if isinstance(result, dict) else None
    if items is None and isinstance(data, dict):
        items = data.get("result") if isinstance(data.get("result"), list) else None
    items = items or []
    return {
        "query": query,
        "scope": media_content_id or "(the media-source root)",
        "filter_classes": filter_classes or None,
        "count": len(items),
        "results": items,
        "raw": data,
    }


def player_search(
    client,
    *,
    entity_id: str,
    query: str,
    media_content_id: str | None = None,
    media_content_type: str | None = None,
) -> dict:
    """Search inside ONE media_player's own library.

    Different question from `search_media`: this asks the player's integration
    (Music Assistant, Emby, Spotify, …) to search its own catalogue, which
    reaches content that is not exposed as a media source at all.

    HA marks `media_content_id` and `media_content_type` mutually inclusive —
    supply both or neither — and rejects the pair otherwise.

    A player whose integration has no search answers
    `not_supported: Player does not support searching media` (measured against
    a real media_player). That is an error, not an empty list, and it is left
    to surface as HA wrote it because the message already names the cause.
    """
    if not entity_id.startswith("media_player."):
        raise ValueError(f"expected media_player.* entity_id, got {entity_id!r}")
    if not query:
        raise ValueError("query is required")
    if bool(media_content_id) != bool(media_content_type):
        raise ValueError(
            "media_content_id and media_content_type must be given together — "
            "HA declares them mutually inclusive and rejects one alone."
        )
    payload: dict = {"entity_id": entity_id, "search_query": query}
    if media_content_id:
        payload["media_content_id"] = media_content_id
        payload["media_content_type"] = media_content_type
    data = client.ws_call("media_player/search_media", payload) or {}
    result = data.get("result") if isinstance(data, dict) else None
    items = result if isinstance(result, list) else (result or {}).get("result") or []
    return {
        "entity_id": entity_id,
        "query": query,
        "count": len(items) if isinstance(items, list) else 0,
        "results": items,
        "raw": data,
    }
