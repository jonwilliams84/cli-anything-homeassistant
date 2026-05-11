"""Text-to-speech — engines list / speak / clear-cache.

Modern path: `tts.speak` service takes (tts entity_id, message, media_player_entity_id,
options, cache, language). Engines are exposed as `tts.<engine>` entities.

Legacy per-engine services like `tts.google_translate_say` still work; the
wrapper below targets the modern `tts.speak` only.
"""

from __future__ import annotations

from typing import Any, Optional

from cli_anything.homeassistant.core import services as services_core
from cli_anything.homeassistant.core import states as states_core


def list_engines(client) -> list[dict]:
    """Return every `tts.*` entity HA has registered.

    Each row: {entity_id, friendly_name, supported_languages, default_language}.
    """
    rows = []
    for s in states_core.list_states(client, domain="tts"):
        eid = s.get("entity_id", "")
        if not eid.startswith("tts."):
            continue
        attrs = s.get("attributes", {}) or {}
        rows.append({
            "entity_id": eid,
            "friendly_name": attrs.get("friendly_name"),
            "default_language": attrs.get("default_language"),
            "supported_languages": attrs.get("supported_languages"),
        })
    return rows


def speak(client, *, tts_entity: str,
          media_player_entity: str,
          message: str,
          language: Optional[str] = None,
          options: Optional[dict] = None,
          cache: bool = True) -> Any:
    """Have a TTS engine speak `message` through a media_player entity.

    `tts_entity` is the speech-synth engine; `media_player_entity` is where
    the audio comes out. They're two different entity_ids.
    """
    if not tts_entity.startswith("tts."):
        raise ValueError(f"expected tts.* entity_id, got {tts_entity!r}")
    if not media_player_entity.startswith("media_player."):
        raise ValueError(
            f"expected media_player.* entity_id, got {media_player_entity!r}"
        )
    if not message:
        raise ValueError("message is required")
    data: dict[str, Any] = {
        "media_player_entity_id": media_player_entity,
        "message": message,
        "cache": bool(cache),
    }
    if language: data["language"] = language
    if options:  data["options"] = options
    return services_core.call_service(
        client, "tts", "speak",
        service_data=data,
        target={"entity_id": tts_entity},
    )


def clear_cache(client, tts_entity: Optional[str] = None) -> Any:
    """Wipe cached TTS audio. Without an entity, clears every engine."""
    if tts_entity:
        if not tts_entity.startswith("tts."):
            raise ValueError(f"expected tts.* entity_id, got {tts_entity!r}")
        target = {"entity_id": tts_entity}
    else:
        target = None
    return services_core.call_service(client, "tts", "clear_cache",
                                       target=target)
