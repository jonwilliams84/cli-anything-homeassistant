"""Text-to-speech — engines list / speak / get-url / clear-cache.

Modern path: `tts.speak` service takes (tts entity_id, message, media_player_entity_id,
options, cache, language). Engines are exposed as `tts.<engine>` entities.

Legacy per-engine services like `tts.google_translate_say` still work; the
wrapper below targets the modern `tts.speak` only.

TWO THINGS MEASURED ON 2026.8.1, BOTH OF WHICH CORRECT SOMETHING

    1. `supported_languages` IS NOT ON THE ENTITY. `list_engines()` read it out
       of the `tts.*` entity attributes and got `[]` for all four engines on a
       real instance — not because HA does not know, but because it keeps the
       list on the WebSocket `tts/engine/list` command instead. So the harness
       was printing an empty list next to an engine that supports eighty-one
       languages. `engine_languages()` reads the real source and
       `list_engines()` now merges it in.

    2. A 500 FROM `/api/tts_get_url` MEANS "THIS ENGINE DOES NOT SUPPORT THAT
       LANGUAGE", AND NOTHING ELSE SAYS SO. HA returns a bare
       `500: Internal Server Error` with no body. Measured across four engines:

           engine                  (no language)   en_GB   en-GB
           tts.piper                   200          200     500
           tts.omnivoice               200          500     200
           tts.chatterbox_wyoming      200          500     200
           tts.google_ai_tts           200          500     500

       OMITTING the language is fine everywhere — which corrects the belief
       that a missing `language` field causes the 500. What causes it is a
       language string the engine does not DECLARE, and there is no rule to
       infer: each engine ships its own strings and they are not even
       internally consistent. Measured, piper's 50 languages include BOTH
       `en_GB` and `en-us`; the Wyoming pair declare only `en-GB`; and
       google_ai_tts declares 81 languages with `en-IN` and `en-US` among them
       and no British English at all. So the list has to be read, not guessed:
       `get_url()` checks against that engine's own before calling, and names
       the near matches when it refuses.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from cli_anything.homeassistant.core import services as services_core
from cli_anything.homeassistant.core import states as states_core

_LOGGER = logging.getLogger(__name__)


def engine_languages(client) -> dict[str, list[str]]:
    """Every engine's REAL `supported_languages`, from `tts/engine/list`.

    The entity attributes do not carry this — measured, all four engines on a
    live instance report `[]` there while HA has the full list here.
    """
    data = client.ws_call("tts/engine/list") or {}
    providers = data.get("providers") if isinstance(data, dict) else None
    out: dict[str, list[str]] = {}
    for provider in providers or []:
        engine = provider.get("engine_id")
        if engine:
            out[engine] = provider.get("supported_languages") or []
    return out


def list_engines(client) -> list[dict]:
    """Return every `tts.*` entity HA has registered.

    Each row: {entity_id, friendly_name, supported_languages, default_language}.

    `supported_languages` is merged in from `tts/engine/list`, because the
    entity attributes do not carry it — see the module docstring. When that WS
    call cannot be made the attribute value is used unchanged, so this degrades
    to the old behaviour rather than to an exception.
    """
    try:
        languages = engine_languages(client)
    except Exception:  # noqa: BLE001 - a missing WS surface must not kill `tts list`
        _LOGGER.debug("tts/engine/list unavailable; falling back to entity attributes")
        languages = {}
    rows = []
    for s in states_core.list_states(client, domain="tts"):
        eid = s.get("entity_id", "")
        if not eid.startswith("tts."):
            continue
        attrs = s.get("attributes", {}) or {}
        rows.append(
            {
                "entity_id": eid,
                "friendly_name": attrs.get("friendly_name"),
                "default_language": attrs.get("default_language"),
                "supported_languages": languages.get(eid, attrs.get("supported_languages")),
                "languages_from": "tts/engine/list" if eid in languages else "entity attributes",
            }
        )
    return rows


def get_url(
    client,
    *,
    engine_id: str,
    message: str,
    language: Optional[str] = None,
    options: Optional[dict] = None,
    cache: Optional[bool] = None,
    check_language: bool = True,
) -> dict:
    """Synthesise `message` and return a playable URL — without playing it.

    This is the endpoint behind every "send the clip somewhere else" workflow:
    it renders the audio and hands back `/api/tts_proxy/<token>.mp3`, which any
    player can fetch.

    `check_language` pre-validates against the engine's own
    `supported_languages`, because HA's failure here is a bare
    `500: Internal Server Error` with no body — see the module docstring for
    the measurement. Set it False to send the language through untouched.
    """
    if not engine_id:
        raise ValueError("engine_id is required (e.g. tts.piper)")
    if not message:
        raise ValueError("message is required")

    checked: dict[str, Any] = {"language_checked": False}
    if language and check_language:
        try:
            supported = engine_languages(client).get(engine_id)
        except Exception:  # noqa: BLE001 - never fail the call over the pre-check
            supported = None
        if supported:
            checked = {"language_checked": True, "supported_languages": supported}
            if language not in supported:
                near = [
                    x
                    for x in supported
                    if x.split("-")[0].split("_")[0] == language.split("-")[0].split("_")[0]
                ]
                raise ValueError(
                    f"{engine_id} does not support language {language!r}. HA would "
                    f"answer a bare 500 with no body. It declares "
                    f"{len(supported)} languages"
                    + (f"; closest matches: {', '.join(near[:6])}" if near else "")
                    + ". Omitting --language works on every engine."
                )

    payload: dict[str, Any] = {"engine_id": engine_id, "message": message}
    if language:
        payload["language"] = language
    if options:
        payload["options"] = options
    if cache is not None:
        payload["cache"] = bool(cache)

    result = client.post("tts_get_url", payload) or {}
    return {
        "engine_id": engine_id,
        "language": language,
        "url": result.get("url"),
        "path": result.get("path"),
        **checked,
    }


def speak(
    client,
    *,
    tts_entity: str,
    media_player_entity: str,
    message: str,
    language: Optional[str] = None,
    options: Optional[dict] = None,
    cache: bool = True,
) -> Any:
    """Have a TTS engine speak `message` through a media_player entity.

    `tts_entity` is the speech-synth engine; `media_player_entity` is where
    the audio comes out. They're two different entity_ids.
    """
    if not tts_entity.startswith("tts."):
        raise ValueError(f"expected tts.* entity_id, got {tts_entity!r}")
    if not media_player_entity.startswith("media_player."):
        raise ValueError(f"expected media_player.* entity_id, got {media_player_entity!r}")
    if not message:
        raise ValueError("message is required")
    data: dict[str, Any] = {
        "media_player_entity_id": media_player_entity,
        "message": message,
        "cache": bool(cache),
    }
    if language:
        data["language"] = language
    if options:
        data["options"] = options
    return services_core.call_service(
        client,
        "tts",
        "speak",
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
    return services_core.call_service(client, "tts", "clear_cache", target=target)
