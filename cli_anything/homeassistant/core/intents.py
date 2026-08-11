"""Fire an INTENT directly, skipping the sentence parser.

WHY THIS IS NOT `assist ask`
    `assist ask` sends a SENTENCE and lets HA's conversation agent decide what
    it means. That is the right call for testing what a user would say, and the
    wrong one for testing what happens once the intent is chosen — a failure
    then has two possible causes and the response cannot separate them.

    `/api/intent/handle` takes the intent NAME and its slots directly, so a
    handler can be exercised with no parsing in the way. When `assist ask`
    misbehaves, running the same intent here is what says whether the sentence
    matching or the handler is at fault.

THE SLOT SHAPE IS NOT WHAT THE API TAKES
    HA's view wraps every value: `data: {name: "Kitchen"}` becomes the slot
    `{"name": {"value": "Kitchen"}}` server-side. Callers pass plain values and
    the wrapping is HA's, so nothing here needs to know it — recorded because
    the intent DOCS show the wrapped form and hand-building it here would
    double-wrap.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

_LOGGER = logging.getLogger(__name__)


def handle(
    client,
    name: str,
    *,
    slots: Optional[dict] = None,
    language: Optional[str] = None,
    assistant: Optional[str] = None,
    device_id: Optional[str] = None,
) -> dict:
    """Run one intent by name with plain-valued slots."""
    if not name:
        raise ValueError("intent name is required (e.g. HassTurnOn)")
    payload: dict[str, Any] = {"name": name}
    if slots:
        payload["data"] = slots
    if language:
        payload["language"] = language
    if assistant:
        payload["assistant"] = assistant
    if device_id:
        payload["device_id"] = device_id
    result = client.post("intent/handle", payload) or {}
    speech = ((result.get("speech") or {}).get("plain") or {}).get("speech")
    return {
        "intent": name,
        "slots": slots or None,
        "response_type": result.get("response_type"),
        "speech": speech,
        "targets": (result.get("data") or {}).get("targets"),
        "success": (result.get("data") or {}).get("success"),
        "failed": (result.get("data") or {}).get("failed"),
        "raw": result,
    }
