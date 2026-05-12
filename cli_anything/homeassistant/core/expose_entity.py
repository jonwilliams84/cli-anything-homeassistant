"""Assist entity exposure control.

Manage which entities are exposed to voice assistants via the
``homeassistant/expose_entity*`` WebSocket commands.
"""

from __future__ import annotations


def list_exposed(client, *, assistant: str | None = None) -> dict:
    """List entities exposed to assistants.

    WS: ``homeassistant/expose_entity/list``

    Returns a dict mapping entity_id → {<assistant>: bool, ...} for each
    configured assistant's expose setting. If `assistant` is specified,
    filters to only that assistant's settings.
    """
    result = client.ws_call("homeassistant/expose_entity/list", {})
    exposed = result.get("exposed_entities", {})

    if assistant is None:
        return exposed

    # Filter to just the requested assistant
    filtered = {}
    for entity_id, settings in exposed.items():
        if assistant in settings:
            filtered[entity_id] = {assistant: settings[assistant]}
    return filtered


def expose_entity(client, *, assistants: list[str], entity_ids: list[str],
                  should_expose: bool) -> dict:
    """Expose or hide entities from assistants.

    WS: ``homeassistant/expose_entity``

    Sets the should_expose flag for each (entity_id, assistant) pair.
    Payload: {assistants, entity_ids, should_expose}.
    """
    if not assistants:
        raise ValueError("assistants must be a non-empty list")
    if not isinstance(assistants, list):
        raise ValueError("assistants must be a list")
    if not entity_ids:
        raise ValueError("entity_ids must be a non-empty list")
    if not isinstance(entity_ids, list):
        raise ValueError("entity_ids must be a list")

    return client.ws_call("homeassistant/expose_entity", {
        "assistants": assistants,
        "entity_ids": entity_ids,
        "should_expose": should_expose,
    })


def get_expose_new_entities(client, *, assistant: str) -> bool:
    """Check if new entities are auto-exposed to an assistant.

    WS: ``homeassistant/expose_new_entities/get``

    Returns True if new entities are automatically exposed to the assistant.
    """
    if not assistant:
        raise ValueError("assistant is required and must be non-empty")
    if not isinstance(assistant, str):
        raise ValueError("assistant must be a string")

    result = client.ws_call("homeassistant/expose_new_entities/get", {
        "assistant": assistant,
    })
    return result.get("expose_new", False)


def set_expose_new_entities(client, *, assistant: str,
                             expose_new: bool) -> dict:
    """Set auto-expose for new entities to an assistant.

    WS: ``homeassistant/expose_new_entities/set``

    Controls whether new entities are automatically exposed to the assistant.
    """
    if not assistant:
        raise ValueError("assistant is required and must be non-empty")
    if not isinstance(assistant, str):
        raise ValueError("assistant must be a string")

    return client.ws_call("homeassistant/expose_new_entities/set", {
        "assistant": assistant,
        "expose_new": expose_new,
    })
