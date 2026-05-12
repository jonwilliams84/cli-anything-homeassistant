"""Singletons grab-bag — nine one-off WS commands that don't fit other modules.

Home Assistant exposes the following singleton WebSocket commands:

1. ``diagnostics/get`` — request handler-level diagnostics
2. ``update/release_notes`` — fetch release notes for an update entity
3. ``usb/scan`` — trigger a USB hardware rescan
4. ``zha/devices/permit`` — permit new ZHA device joins for a duration
5. ``search/related`` — search for items related to a given entity/device
6. ``media_player/browse_media`` — browse media in a media player entity
7. ``persistent_notification/subscribe`` — subscribe to persistent notification updates
8. ``todo/item/subscribe`` — subscribe to todo list item updates
9. ``hardware/subscribe_system_status`` — subscribe to hardware status (minimal wrapper)

Public API
----------
* :func:`diagnostics_get`
* :func:`update_release_notes`
* :func:`usb_scan`
* :func:`zha_devices_permit`
* :func:`search_related`
* :func:`browse_media_player`
* :func:`subscribe_persistent_notifications`
* :func:`subscribe_todo_items`
* :func:`subscribe_hardware_status`
"""

from __future__ import annotations

import threading
from typing import Any, Callable


# ════════════════════════════════════════════════════════════════════════
# 1. diagnostics_get — WS diagnostics/get
# ════════════════════════════════════════════════════════════════════════

def diagnostics_get(client, *, handler: str) -> Any:
    """Request handler-level (integration domain) diagnostics.

    ``handler`` — the integration domain name (e.g., "mqtt", "zwave_js").
                  Required, non-empty string.

    Uses WS command ``diagnostics/get``.
    """
    if not handler:
        raise ValueError("handler must be a non-empty string")
    return client.ws_call("diagnostics/get", {"handler": handler})


# ════════════════════════════════════════════════════════════════════════
# 2. update_release_notes — WS update/release_notes
# ════════════════════════════════════════════════════════════════════════

def update_release_notes(client, *, entity_id: str) -> Any:
    """Fetch release notes for an update entity.

    ``entity_id`` — must be an update.* entity (required, validated).

    Uses WS command ``update/release_notes``.
    """
    if not entity_id.startswith("update."):
        raise ValueError(f"expected update.* entity_id, got {entity_id!r}")
    return client.ws_call("update/release_notes", {"entity_id": entity_id})


# ════════════════════════════════════════════════════════════════════════
# 3. usb_scan — WS usb/scan
# ════════════════════════════════════════════════════════════════════════

def usb_scan(client) -> Any:
    """Trigger a USB hardware rescan.

    Uses WS command ``usb/scan``.
    """
    return client.ws_call("usb/scan")


# ════════════════════════════════════════════════════════════════════════
# 4. zha_devices_permit — WS zha/devices/permit
# ════════════════════════════════════════════════════════════════════════

def zha_devices_permit(client, *, duration: int = 60, ieee: str | None = None) -> Any:
    """Permit new ZHA device joins for a specified duration.

    ``duration`` — permit window in seconds; must be 1–254 (default 60).
                   Required, validated.
    ``ieee`` — optional IEEE address of a specific device to permit.

    Uses WS command ``zha/devices/permit``.
    """
    if not (1 <= duration <= 254):
        raise ValueError(f"duration must be 1–254, got {duration}")
    payload: dict = {"duration": duration}
    if ieee is not None:
        payload["ieee"] = ieee
    return client.ws_call("zha/devices/permit", payload)


# ════════════════════════════════════════════════════════════════════════
# 5. search_related — WS search/related
# ════════════════════════════════════════════════════════════════════════

_VALID_ITEM_TYPES = {
    "automation", "config_entry", "area", "device", "entity",
    "floor", "group", "label", "person", "scene", "script"
}


def search_related(client, *, item_type: str, item_id: str) -> Any:
    """Search for items related to a given entity, device, or config item.

    ``item_type`` — one of: automation, config_entry, area, device, entity,
                    floor, group, label, person, scene, script
                    (required, validated).
    ``item_id`` — identifier within the item_type (required, non-empty).

    Uses WS command ``search/related``.
    """
    if item_type not in _VALID_ITEM_TYPES:
        raise ValueError(
            f"item_type must be one of {sorted(_VALID_ITEM_TYPES)}, "
            f"got {item_type!r}"
        )
    if not item_id:
        raise ValueError("item_id must be a non-empty string")
    return client.ws_call("search/related", {
        "item_type": item_type,
        "item_id": item_id
    })


# ════════════════════════════════════════════════════════════════════════
# 6. browse_media_player — WS media_player/browse_media
# ════════════════════════════════════════════════════════════════════════

def browse_media_player(
    client,
    *,
    entity_id: str,
    media_content_id: str | None = None,
    media_content_type: str | None = None,
) -> Any:
    """Browse media library in a media player entity.

    ``entity_id`` — must be a media_player.* entity (required, validated).
    ``media_content_id`` — optional media content identifier to browse into.
    ``media_content_type`` — optional content type (e.g., "music").

    Uses WS command ``media_player/browse_media``.
    """
    if not entity_id.startswith("media_player."):
        raise ValueError(f"expected media_player.* entity_id, got {entity_id!r}")
    payload: dict = {"entity_id": entity_id}
    if media_content_id is not None:
        payload["media_content_id"] = media_content_id
    if media_content_type is not None:
        payload["media_content_type"] = media_content_type
    return client.ws_call("media_player/browse_media", payload)


# ════════════════════════════════════════════════════════════════════════
# 7. subscribe_persistent_notifications — WS persistent_notification/subscribe
# ════════════════════════════════════════════════════════════════════════

def subscribe_persistent_notifications(
    client,
    *,
    on_notification: Callable,
    stop_event: threading.Event | None = None,
    max_notifications: int | None = None,
) -> None:
    """Subscribe to persistent notification updates.

    Wraps the ``persistent_notification/subscribe`` WS command. Blocks until
    ``stop_event`` is set (or ``max_notifications`` have been received when
    only that is supplied).

    Parameters
    ----------
    client:
        Home Assistant client instance exposing ``ws_subscribe``.
    on_notification:
        Callable invoked with each notification dict received from HA.
    stop_event:
        :class:`threading.Event` whose set-state terminates the loop. At
        least one of ``stop_event`` or ``max_notifications`` must be supplied.
    max_notifications:
        Stop automatically after this many notifications. Ignored when
        ``stop_event`` is also supplied.

    Raises
    ------
    ValueError
        If neither ``stop_event`` nor ``max_notifications`` is provided, or if
        ``on_notification`` is not callable.
    """
    if not callable(on_notification):
        raise ValueError("on_notification must be callable")

    stop, owns_stop = _resolve_stop_event(stop_event, max_notifications)

    count_box = [0]

    def wrapper(notification: object) -> None:
        on_notification(notification)
        if owns_stop and max_notifications is not None:
            count_box[0] += 1
            if count_box[0] >= max_notifications:
                stop.set()

    client.ws_subscribe("persistent_notification/subscribe", {}, wrapper, stop)


# ════════════════════════════════════════════════════════════════════════
# 8. subscribe_todo_items — WS todo/item/subscribe
# ════════════════════════════════════════════════════════════════════════

def subscribe_todo_items(
    client,
    *,
    entity_id: str,
    on_update: Callable,
    stop_event: threading.Event | None = None,
    max_updates: int | None = None,
) -> None:
    """Subscribe to todo list item updates.

    Wraps the ``todo/item/subscribe`` WS command. Blocks until ``stop_event``
    is set (or ``max_updates`` have been received when only that is supplied).

    Parameters
    ----------
    client:
        Home Assistant client instance exposing ``ws_subscribe``.
    entity_id:
        Must be a todo.* entity (required, validated).
    on_update:
        Callable invoked with each update dict received from HA.
    stop_event:
        :class:`threading.Event` whose set-state terminates the loop. At
        least one of ``stop_event`` or ``max_updates`` must be supplied.
    max_updates:
        Stop automatically after this many updates. Ignored when
        ``stop_event`` is also supplied.

    Raises
    ------
    ValueError
        If entity_id does not start with "todo.", if neither ``stop_event`` nor
        ``max_updates`` is provided, or if ``on_update`` is not callable.
    """
    if not entity_id.startswith("todo."):
        raise ValueError(f"expected todo.* entity_id, got {entity_id!r}")
    if not callable(on_update):
        raise ValueError("on_update must be callable")

    stop, owns_stop = _resolve_stop_event(stop_event, max_updates)

    count_box = [0]

    def wrapper(update: object) -> None:
        on_update(update)
        if owns_stop and max_updates is not None:
            count_box[0] += 1
            if count_box[0] >= max_updates:
                stop.set()

    client.ws_subscribe("todo/item/subscribe", {"entity_id": entity_id}, wrapper, stop)


# ════════════════════════════════════════════════════════════════════════
# 9. subscribe_hardware_status — WS hardware/subscribe_system_status
# ════════════════════════════════════════════════════════════════════════

def subscribe_hardware_status(
    client,
    *,
    on_status: Callable,
    stop_event: threading.Event | None = None,
    max_updates: int | None = None,
) -> None:
    """Subscribe to hardware system status updates (minimal one-shot wrapper).

    Wraps the ``hardware/subscribe_system_status`` WS command. Blocks until
    ``stop_event`` is set (or ``max_updates`` have been received when only
    that is supplied).

    This is a minimal wrapper for completeness; see hardware_info.py for a
    more featured subscribe_system_status with custom callbacks per metric.

    Parameters
    ----------
    client:
        Home Assistant client instance exposing ``ws_subscribe``.
    on_status:
        Callable invoked with each status dict received from HA.
    stop_event:
        :class:`threading.Event` whose set-state terminates the loop. At
        least one of ``stop_event`` or ``max_updates`` must be supplied.
    max_updates:
        Stop automatically after this many updates. Ignored when
        ``stop_event`` is also supplied.

    Raises
    ------
    ValueError
        If neither ``stop_event`` nor ``max_updates`` is provided, or if
        ``on_status`` is not callable.
    """
    if not callable(on_status):
        raise ValueError("on_status must be callable")

    stop, owns_stop = _resolve_stop_event(stop_event, max_updates)

    count_box = [0]

    def wrapper(status: object) -> None:
        on_status(status)
        if owns_stop and max_updates is not None:
            count_box[0] += 1
            if count_box[0] >= max_updates:
                stop.set()

    client.ws_subscribe("hardware/subscribe_system_status", {}, wrapper, stop)


# ════════════════════════════════════════════════════════════════════════
# Internal helpers
# ════════════════════════════════════════════════════════════════════════

def _resolve_stop_event(
    stop_event: threading.Event | None,
    max_events: int | None,
) -> tuple[threading.Event, bool]:
    """Return (stop_event, caller_owns_it).

    *caller_owns_it* is True when we created the event internally so that
    the subscription loop should set it after max_events have arrived.
    """
    if stop_event is None and max_events is None:
        raise ValueError("must supply stop_event or max_events")
    if stop_event is None:
        return threading.Event(), True
    return stop_event, False
