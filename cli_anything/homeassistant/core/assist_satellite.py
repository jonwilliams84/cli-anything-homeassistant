"""Assist satellite entity control via WS API.

Assist satellites are remote devices that interact with a local voice pipeline.
Commands allow configuring wake words, retrieving configuration, testing
connection, and intercepting wake words for testing.
"""

from __future__ import annotations

import threading
from typing import Callable

from cli_anything.homeassistant.core._ws_subscribe_utils import (
    resolve_stop_event as _resolve_stop_event,
    wrap_with_max_events as _wrap_with_max_events,
)


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


def intercept_wake_word(
    client,
    *,
    entity_id: str,
    on_event: Callable,
    stop_event: threading.Event | None = None,
    max_events: int | None = None,
) -> None:
    """Intercept wake word events from an assist_satellite entity.

    Subscribes to the ``assist_satellite/intercept_wake_word`` WS command.
    Blocks until ``stop_event`` is set or ``max_events`` wake word events are
    received and forwarded to ``on_event``.

    Parameters
    ----------
    client:
        HomeAssistantClient instance exposing ``ws_subscribe``.
    entity_id:
        Full entity_id (must start with "assist_satellite.").
    on_event:
        Callable invoked with each wake word event dict received from HA.
        Events typically contain a ``wake_word_phrase`` key.
    stop_event:
        :class:`threading.Event` whose set-state terminates the loop. At
        least one of ``stop_event`` or ``max_events`` must be supplied.
    max_events:
        Stop automatically after this many events. Ignored when
        ``stop_event`` is also supplied.

    Raises
    ------
    ValueError
        If entity_id does not start with "assist_satellite.", ``on_event``
        is not callable, or neither ``stop_event`` nor ``max_events`` is
        provided.
    """
    if not entity_id.startswith("assist_satellite."):
        raise ValueError(
            f"expected assist_satellite.* entity_id, got {entity_id!r}"
        )
    if not callable(on_event):
        raise ValueError("on_event must be callable")
    stop, owns_stop = _resolve_stop_event(stop_event, max_events)
    wrapper = _wrap_with_max_events(on_event, stop, owns_stop, max_events)
    client.ws_subscribe(
        "assist_satellite/intercept_wake_word",
        {"entity_id": entity_id},
        wrapper,
        stop,
    )
