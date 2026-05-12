"""Assist satellite entity control via WS API.

Assist satellites are remote devices that interact with a local voice pipeline.
Commands allow configuring wake words, retrieving configuration, testing
connection, and intercepting wake words for testing.
"""

from __future__ import annotations


def get_configuration(client, *, entity_id: str) -> dict:
    """Get the current configuration of an assist_satellite entity.

    Returns a dict with keys like `available_wake_words`, `active_wake_words`,
    `max_active_wake_words`, `pipeline_entity_id`, `vad_entity_id`, etc.

    Args:
        client: HomeAssistantClient instance.
        entity_id: Full entity_id (must start with "assist_satellite.").

    Raises:
        ValueError: If entity_id does not start with "assist_satellite.".
    """
    if not entity_id.startswith("assist_satellite."):
        raise ValueError(
            f"expected assist_satellite.* entity_id, got {entity_id!r}"
        )
    return client.ws_call("assist_satellite/get_configuration", {"entity_id": entity_id})


def set_wake_words(client, *, entity_id: str, wake_word_ids: list[str]) -> dict:
    """Set the active wake words for an assist_satellite entity.

    Args:
        client: HomeAssistantClient instance.
        entity_id: Full entity_id (must start with "assist_satellite.").
        wake_word_ids: List of wake word IDs to activate. Must be non-empty;
            each ID must be a non-empty string.

    Raises:
        ValueError: If entity_id prefix is invalid, list is empty, or
            any wake word ID is empty.
    """
    if not entity_id.startswith("assist_satellite."):
        raise ValueError(
            f"expected assist_satellite.* entity_id, got {entity_id!r}"
        )
    if not isinstance(wake_word_ids, list) or not wake_word_ids:
        raise ValueError("wake_word_ids must be a non-empty list")
    if not all(isinstance(wid, str) and wid for wid in wake_word_ids):
        raise ValueError("each wake_word_id must be a non-empty string")
    return client.ws_call(
        "assist_satellite/set_wake_words",
        {"entity_id": entity_id, "wake_word_ids": wake_word_ids},
    )


def test_connection(client, *, entity_id: str) -> dict:
    """Test the connection between the device and Home Assistant.

    Sends an announcement with a special media ID and waits for the device
    to acknowledge. Returns `{"status": "success"}` or `{"status": "timeout"}`.

    Args:
        client: HomeAssistantClient instance.
        entity_id: Full entity_id (must start with "assist_satellite.").

    Raises:
        ValueError: If entity_id does not start with "assist_satellite.".
    """
    if not entity_id.startswith("assist_satellite."):
        raise ValueError(
            f"expected assist_satellite.* entity_id, got {entity_id!r}"
        )
    return client.ws_call("assist_satellite/test_connection", {"entity_id": entity_id})


def intercept_wake_word(client, *, entity_id: str) -> dict:
    """Intercept the next wake word from an assist_satellite entity.

    NOTE: This WS command is a SUBSCRIBE command that returns a stream of
    results. This wrapper sends a one-shot WS call and records it in
    ``client.ws_calls`` for testing. For full streaming support, use
    ``client.ws_subscribe()`` directly on the returned task.

    Returns a dict with `wake_word_phrase` key upon successful interception.

    Args:
        client: HomeAssistantClient instance.
        entity_id: Full entity_id (must start with "assist_satellite.").

    Raises:
        ValueError: If entity_id does not start with "assist_satellite.".
    """
    if not entity_id.startswith("assist_satellite."):
        raise ValueError(
            f"expected assist_satellite.* entity_id, got {entity_id!r}"
        )
    return client.ws_call(
        "assist_satellite/intercept_wake_word", {"entity_id": entity_id}
    )
