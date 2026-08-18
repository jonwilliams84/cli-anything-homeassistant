"""The voice stack, asked instead of guessed: TTS voices, STT engines, wake words.

WHAT WAS MISSING AND WHY IT BIT

    `tts speak` and `tts get-url` both take an `options` dict, and the option
    every real call wants is `voice`. The harness could send it and had no way
    to find out what a legal value was — so the workflow was "type a plausible
    voice name and read the failure", and the failure is not always a failure:
    an unknown voice is accepted by some engines and quietly replaced with the
    default. `voices()` asks HA (`tts/engine/voices`), which is the only place
    the list exists.

    The same hole ran the other way for input. `assist pipelines` could show
    that a pipeline names an STT engine and a wake-word entity; nothing could
    ask what those engines actually SUPPORT. A pipeline configured with a
    language its STT engine does not speak fails at use time, in a
    voice-assistant satellite, with no log line the operator will see.

THREE MEASURED FACTS ABOUT THESE COMMANDS

    1. `tts/engine/voices` REQUIRES `language` — it is `vol.Required` — and
       answers an UNKNOWN language with an empty list, not an error. Only an
       unknown ENGINE is an error (`ERR_NOT_FOUND`). So `voices: []` is
       ambiguous at the protocol level: it means either "no voices for that
       language" or "you asked for a language this engine never declared".
       `voices()` disambiguates by checking the language against the engine's
       own `supported_languages` first — read from `tts/engine/list`, the same
       source `core/tts.py` had to fall back to because the entity attributes
       come back empty.

    2. `stt/engine/list` AND `tts/engine/list` BOTH RETURN `{"providers": [...]}`
       AND BOTH MIX TWO KINDS OF ENTRY. Entity-backed engines have an
       `engine_id` that is an entity_id (`stt.faster_whisper`) and no `name`;
       legacy platform providers have a bare domain id and a `name`. The TTS
       list additionally flags the legacy half `deprecated: true` when an
       entity of the same platform exists. Sorting the two apart is left to
       the caller, but `kind` is added so it can be.

    3. `wake_word/info` IS ENTITY-SCOPED AND HA VALIDATES THE DOMAIN
       (`cv.entity_domain("wake_word")`). Passing a satellite's
       `assist_satellite.*` entity — the obvious mistake, since that is where
       wake words are CONFIGURED — produces a voluptuous error about the
       schema. Rejected here with the actual remedy. HA also has a 10s
       internal timeout fetching the list from the provider and returns
       `ERR_TIMEOUT`; that is a slow provider, not a missing one.

AND ONE ABOUT `conversation/prepare`

    It returns NOTHING — `connection.send_result(msg["id"])` with no payload.
    It is a warm-up: the agent loads its intent/sentence data for a language so
    the first real utterance is not the slow one. A null result is success;
    `prepare()` reports it as such rather than passing back a bare `None` that
    reads like a failed call.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from cli_anything.homeassistant.core import tts as tts_core

_LOGGER = logging.getLogger(__name__)


def _language_family(language: str) -> str:
    """`en-GB` / `en_US` / `en` all share the family `en`."""
    return language.split("-")[0].split("_")[0].lower()


# ───────────────────────────────────────────────────────────────── text to speech


def engine(client, engine_id: str) -> dict:
    """One TTS engine's declared capabilities (`tts/engine/get`).

    `tts list` walks the `tts.*` entities; this asks about a single engine by
    id and works for the legacy platform providers too, which have no entity
    and therefore never appear in a state list.
    """
    if not engine_id:
        raise ValueError("engine_id is required (e.g. tts.piper)")
    data = client.ws_call("tts/engine/get", {"engine_id": engine_id}) or {}
    provider = data.get("provider") if isinstance(data, dict) else None
    if not provider:
        raise ValueError(
            f"No TTS engine {engine_id!r}. Run `tts list` for the entity-backed "
            "engines; a legacy provider is named by its integration domain "
            "(e.g. 'google_translate'), not by an entity_id."
        )
    languages = provider.get("supported_languages") or []
    return {
        "engine_id": provider.get("engine_id", engine_id),
        "name": provider.get("name"),
        "kind": "entity" if "." in str(provider.get("engine_id", engine_id)) else "legacy provider",
        "supported_languages": languages,
        "language_count": len(languages),
    }


def voices(client, engine_id: str, language: str, *, check_language: bool = True) -> dict:
    """Every voice `engine_id` offers for `language` — the values `options.voice` takes.

    `language` is required by HA and an unknown one comes back as an empty
    list rather than an error, so it is checked against the engine's own
    declared languages first (see the module docstring). `check_language=False`
    sends it through untouched, which is what you want when the engine's
    declared list is wrong.
    """
    if not engine_id:
        raise ValueError("engine_id is required (e.g. tts.piper)")
    if not language:
        raise ValueError(
            "language is required — HA's schema marks it vol.Required, and an "
            "omitted one is a protocol error rather than 'all languages'."
        )

    declared: list[str] | None = None
    if check_language:
        try:
            declared = tts_core.engine_languages(client).get(engine_id)
        except Exception:  # noqa: BLE001 - never fail the real call over the pre-check
            _LOGGER.debug("tts/engine/list unavailable; skipping the language pre-check")
            declared = None
        if declared and language not in declared:
            near = [x for x in declared if _language_family(x) == _language_family(language)]
            raise ValueError(
                f"{engine_id} does not declare language {language!r}, and HA "
                f"answers an unknown language with an EMPTY voice list rather "
                f"than an error. It declares {len(declared)} languages"
                + (f"; closest matches: {', '.join(near[:6])}" if near else "")
                + "."
            )

    data = client.ws_call("tts/engine/voices", {"engine_id": engine_id, "language": language}) or {}
    found = data.get("voices") if isinstance(data, dict) else None
    rows = found or []
    return {
        "engine_id": engine_id,
        "language": language,
        "voices": rows,
        "count": len(rows),
        "language_checked": bool(declared),
        "note": (
            "Pass one of these as `voice` in --options, e.g. "
            "`tts speak ... --options voice=<voice_id>`."
            if rows
            else "No voices for this language. The engine declares it but "
            "offers no named voice — it has a single built-in voice, which "
            "is normal for a legacy provider."
        ),
    }


# ───────────────────────────────────────────────────────────────── speech to text


def _annotate_providers(providers: list[dict]) -> list[dict]:
    """Tag each row `entity` or `legacy provider` — the two kinds are mixed."""
    rows = []
    for provider in providers or []:
        engine_id = provider.get("engine_id") or ""
        languages = provider.get("supported_languages") or []
        row = dict(provider)
        row["kind"] = "entity" if "." in str(engine_id) else "legacy provider"
        row["language_count"] = len(languages)
        rows.append(row)
    return rows


def stt_engines(
    client, *, language: Optional[str] = None, country: Optional[str] = None
) -> list[dict]:
    """Speech-to-text engines (`stt/engine/list`) — the input half of a pipeline.

    With `language` HA FILTERS each engine's `supported_languages` down to the
    matches rather than dropping the engine, so an engine that cannot handle
    the language appears with an EMPTY list. That is the signal to read: it is
    the difference between "not installed" and "installed and cannot do it".
    `country` refines a language match (`en` + `GB` prefers `en-GB`) and does
    nothing on its own.
    """
    payload: dict[str, Any] = {}
    if language:
        payload["language"] = language
    if country:
        payload["country"] = country
    data = client.ws_call("stt/engine/list", payload or None) or {}
    providers = data.get("providers") if isinstance(data, dict) else None
    rows = _annotate_providers(providers or [])
    if language:
        for row in rows:
            row["supports_requested_language"] = bool(row.get("supported_languages"))
    return rows


def tts_engines(
    client, *, language: Optional[str] = None, country: Optional[str] = None
) -> list[dict]:
    """TTS engines as HA lists them (`tts/engine/list`), filtered by language.

    `tts list` walks entity states and merges this in; this is the raw list,
    which is the one that includes legacy providers with no entity and carries
    HA's own `deprecated` flag for a legacy provider shadowed by an entity.
    """
    payload: dict[str, Any] = {}
    if language:
        payload["language"] = language
    if country:
        payload["country"] = country
    data = client.ws_call("tts/engine/list", payload or None) or {}
    providers = data.get("providers") if isinstance(data, dict) else None
    rows = _annotate_providers(providers or [])
    if language:
        for row in rows:
            row["supports_requested_language"] = bool(row.get("supported_languages"))
    return rows


# ───────────────────────────────────────────────────────────────── wake word


def wake_words(client, entity_id: str) -> dict:
    """The wake words a `wake_word.*` entity can detect (`wake_word/info`).

    NOT the satellite. `assist-satellite config` reports which wake words a
    satellite has ACTIVE and how many it may run at once; this reports what the
    detection engine can offer at all. Choosing a wake word needs both.
    """
    if not entity_id:
        raise ValueError("entity_id is required (e.g. wake_word.openwakeword)")
    if not entity_id.startswith("wake_word."):
        raise ValueError(
            f"expected a wake_word.* entity_id, got {entity_id!r}. A satellite's "
            "assist_satellite.* entity is where wake words are CONFIGURED — use "
            "`assist-satellite config` for that; this asks the detection engine "
            "what it can offer."
        )
    data = client.ws_call("wake_word/info", {"entity_id": entity_id}) or {}
    found = data.get("wake_words") if isinstance(data, dict) else None
    rows = found or []
    return {
        "entity_id": entity_id,
        "wake_words": rows,
        "count": len(rows),
        "ids": [w.get("id") for w in rows if isinstance(w, dict) and w.get("id")],
    }


# ───────────────────────────────────────────────────────────────── conversation


def prepare(client, *, agent_id: Optional[str] = None, language: Optional[str] = None) -> dict:
    """Warm a conversation agent up for a language (`conversation/prepare`).

    Loads the agent's sentence/intent data ahead of time so the first real
    utterance is not the slow one — worth doing after `assist sentences`
    changes or a restart. HA returns NO payload on success, so a null result
    is reported here as `prepared: true` rather than passed back as a bare
    `None` that reads like a dropped call.

    An unknown `agent_id` is `ERR_NOT_FOUND`, which surfaces as an error from
    the client — that is a real answer and not a warm-up failure.
    """
    payload: dict[str, Any] = {}
    if agent_id:
        payload["agent_id"] = agent_id
    if language:
        payload["language"] = language
    client.ws_call("conversation/prepare", payload or None)
    return {
        "prepared": True,
        "agent_id": agent_id or "(default agent)",
        "language": language or "(instance language)",
        "note": (
            "HA returns no payload for this command; success is the absence of "
            "an error. Run it after editing custom sentences or a restart."
        ),
    }
