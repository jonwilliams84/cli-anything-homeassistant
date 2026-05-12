"""Advanced Conversation and Assist Pipeline WebSocket wrappers.

Covers the richer WS surface that the basic ``assist.py`` does not expose:

Conversation (``conversation/`` namespace):
  process            — send text to the conversation agent and get a reply
  list_agents        — enumerate available conversation agents
  list_sentences     — list custom trigger sentences for a language
  debug_agent        — debug how the built-in HA agent matches a sentence

Assist Pipeline (``assist_pipeline/`` namespace):
  list_pipelines         — list pipelines for which debug data is available
  get_pipeline           — fetch debug data for a single pipeline
  list_pipeline_languages — list languages supported by a complete pipeline
  list_satellite_devices  — list registered assist satellite devices
  capture_satellite       — capture raw audio from a satellite device

All functions accept a ``client`` as the first argument and use
``client.ws_call(type, payload)`` — the same thin interface used
throughout this codebase.
"""

from __future__ import annotations

from typing import Any


# ════════════════════════════════════════════════════════════════════════
# Conversation
# ════════════════════════════════════════════════════════════════════════

def process(
    client,
    *,
    text: str,
    language: str | None = None,
    agent_id: str | None = None,
    conversation_id: str | None = None,
) -> dict:
    """Send *text* to the HA conversation agent and return the reply dict.

    Maps to the ``conversation/process`` WS command.

    Parameters
    ----------
    text:
        The natural-language utterance. Must be non-empty.
    language:
        BCP-47 language tag (e.g. ``"en"``). Defaults to HA's configured
        language when omitted.
    agent_id:
        Identifier of the conversation agent to use. Defaults to the HA
        default agent when omitted.
    conversation_id:
        Opaque string that links successive turns into a single conversation.
        Pass ``None`` (default) to start a fresh conversation.
    """
    if not text:
        raise ValueError("text must be a non-empty string")
    payload: dict[str, Any] = {"text": text}
    if language is not None:
        payload["language"] = language
    if agent_id is not None:
        payload["agent_id"] = agent_id
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id
    return client.ws_call("conversation/process", payload)


def list_agents(
    client,
    *,
    country: str | None = None,
    language: str | None = None,
) -> dict:
    """Return the list of available conversation agents.

    Maps to the ``conversation/agent/list`` WS command.

    Parameters
    ----------
    country:
        ISO 3166-1 alpha-2 country code used to narrow language matching.
    language:
        BCP-47 language tag. When supplied, each agent's
        ``supported_languages`` list is filtered to those matching the tag.
    """
    payload: dict[str, Any] = {}
    if country is not None:
        payload["country"] = country
    if language is not None:
        payload["language"] = language
    return client.ws_call("conversation/agent/list", payload)


def list_sentences(client, *, language: str) -> dict:
    """Return custom trigger sentences registered for *language*.

    Maps to the ``conversation/sentences/list`` WS command.

    Parameters
    ----------
    language:
        BCP-47 language tag. Must be non-empty.
    """
    if not language:
        raise ValueError("language must be a non-empty string")
    return client.ws_call("conversation/sentences/list", {"language": language})


def debug_agent(client, *, sentence: str, language: str) -> dict:
    """Return the intent the built-in HA agent would match for *sentence*.

    Maps to the ``conversation/agent/homeassistant/debug`` WS command.

    Parameters
    ----------
    sentence:
        The utterance to test. Must be non-empty.
    language:
        BCP-47 language tag. Must be non-empty.
    """
    if not sentence:
        raise ValueError("sentence must be a non-empty string")
    if not language:
        raise ValueError("language must be a non-empty string")
    return client.ws_call(
        "conversation/agent/homeassistant/debug",
        {"sentence": sentence, "language": language},
    )


# ════════════════════════════════════════════════════════════════════════
# Assist Pipeline
# ════════════════════════════════════════════════════════════════════════

def list_pipelines(client) -> list:
    """Return pipeline debug records available on this HA instance.

    Maps to the ``assist_pipeline/pipeline_debug/list`` WS command.
    Returns a list (empty when no debug data has been captured yet).
    """
    result = client.ws_call("assist_pipeline/pipeline_debug/list")
    if isinstance(result, list):
        return result
    return []


def get_pipeline(client, *, pipeline_id: str) -> dict:
    """Return debug data for the pipeline identified by *pipeline_id*.

    Maps to the ``assist_pipeline/pipeline_debug/get`` WS command.

    Parameters
    ----------
    pipeline_id:
        The pipeline's unique identifier. Must be non-empty.
    """
    if not pipeline_id:
        raise ValueError("pipeline_id must be a non-empty string")
    return client.ws_call(
        "assist_pipeline/pipeline_debug/get",
        {"pipeline_id": pipeline_id},
    )


def list_pipeline_languages(client) -> dict:
    """Return languages supported by at least one complete pipeline.

    A "complete" pipeline has a matching STT, TTS, and conversation engine.
    Maps to the ``assist_pipeline/language/list`` WS command.
    """
    return client.ws_call("assist_pipeline/language/list")


def list_satellite_devices(client) -> list:
    """Return the list of registered assist satellite devices.

    Maps to the ``assist_pipeline/device/list`` WS command.
    Returns a list of device records.
    """
    result = client.ws_call("assist_pipeline/device/list")
    if isinstance(result, list):
        return result
    return []


def capture_satellite(
    client,
    *,
    device_id: str,
    timeout: float = 30.0,
) -> dict:
    """Subscribe to raw audio capture from a satellite device.

    Maps to the ``assist_pipeline/device/capture`` WS command.
    Audio chunks arrive as events on the subscription after the initial
    result acknowledgement.

    Parameters
    ----------
    device_id:
        The device registry ID of the satellite. Must be non-empty.
    timeout:
        Maximum number of seconds to capture audio. Must be > 0. HA caps
        this at 60 seconds server-side; values above that are accepted here
        but will be rejected by HA.
    """
    if not device_id:
        raise ValueError("device_id must be a non-empty string")
    if timeout <= 0:
        raise ValueError("timeout must be greater than 0")
    return client.ws_call(
        "assist_pipeline/device/capture",
        {"device_id": device_id, "timeout": timeout},
    )
