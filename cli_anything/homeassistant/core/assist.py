"""Conversation / Assist pipeline — send a natural-language utterance to HA.

`process(text)` runs the input through the `conversation` integration's
intent recogniser (or the configured Assist pipeline). Returns a structured
response with `response.speech.plain.speech` for the spoken reply and
`response.data.targets` for any matched entities.

`pipelines()` lists the configured Assist pipelines (whisper+LLM+TTS sets).
"""

from __future__ import annotations

from typing import Any, Optional


def process(client, text: str, *,
            conversation_id: Optional[str] = None,
            language: Optional[str] = None,
            agent_id: Optional[str] = None) -> dict:
    """Send `text` to HA's conversation pipeline and return the reply."""
    if not text:
        raise ValueError("text is required")
    body: dict[str, Any] = {"text": text}
    if conversation_id: body["conversation_id"] = conversation_id
    if language:        body["language"] = language
    if agent_id:        body["agent_id"] = agent_id
    return client.post("conversation/process", body)


def pipelines(client) -> dict:
    """Return the list of configured Assist pipelines + the preferred id."""
    data = client.ws_call("assist_pipeline/pipeline/list") or {}
    return data if isinstance(data, dict) else {"pipelines": [], "preferred_pipeline": None}


def pipeline_get(client, pipeline_id: str) -> dict:
    """Read one pipeline's full config (LLM agent, STT, TTS, wake-word)."""
    if not pipeline_id:
        raise ValueError("pipeline_id is required")
    return client.ws_call("assist_pipeline/pipeline/get",
                            {"pipeline_id": pipeline_id}) or {}
