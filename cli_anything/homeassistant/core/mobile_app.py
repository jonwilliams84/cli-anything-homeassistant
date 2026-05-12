"""Mobile app push notification channel — WS commands for push notification testing.

The mobile_app integration is primarily a server-to-client channel: the phone
subscribes to push notifications. These wrappers are useful for CLI testing of
push notification flows by allowing clients to interact with the subscription
and confirmation lifecycle.

`open_push_channel` opens a push notification subscription (registers the
client as a listener for incoming push notifications to the given webhook ID)
and delivers received notifications via ``on_event`` callback.

`confirm_push_notification(webhook_id, confirm_id)` confirms receipt of a
specific push notification by ID.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from cli_anything.homeassistant.core._ws_subscribe_utils import (
    resolve_stop_event as _resolve_stop_event,
    wrap_with_max_events as _wrap_with_max_events,
)


def open_push_channel(
    client,
    *,
    webhook_id: str,
    on_event: Callable,
    stop_event: threading.Event | None = None,
    max_events: int | None = None,
) -> None:
    """Open a push notification channel for the given webhook ID.

    Subscribes to the ``mobile_app/push_notification_channel`` WS command.
    Blocks until ``stop_event`` is set or ``max_events`` notifications are
    received and forwarded to ``on_event``.

    Parameters
    ----------
    client:
        HomeAssistant client instance exposing ``ws_subscribe``.
    webhook_id:
        The webhook ID to subscribe to push notifications for.
    on_event:
        Callable invoked with each push notification dict received from HA.
    stop_event:
        :class:`threading.Event` whose set-state terminates the loop. At
        least one of ``stop_event`` or ``max_events`` must be supplied.
    max_events:
        Stop automatically after this many notifications. Ignored when
        ``stop_event`` is also supplied.

    Raises
    ------
    ValueError
        If ``webhook_id`` is empty, ``on_event`` is not callable, or neither
        ``stop_event`` nor ``max_events`` is provided.
    """
    if not webhook_id:
        raise ValueError("webhook_id is required")
    if not callable(on_event):
        raise ValueError("on_event must be callable")
    payload: dict[str, Any] = {
        "webhook_id": webhook_id,
        "support_confirm": True,
    }
    stop, owns_stop = _resolve_stop_event(stop_event, max_events)
    wrapper = _wrap_with_max_events(on_event, stop, owns_stop, max_events)
    client.ws_subscribe("mobile_app/push_notification_channel", payload, wrapper, stop)


def confirm_push_notification(client, *, webhook_id: str, confirm_id: str) -> Any:
    """Confirm receipt of a push notification.

    Sends a WebSocket `mobile_app/push_notification_confirm` command to acknowledge
    that a specific push notification (identified by confirm_id) was received.

    Args:
        client: HomeAssistant client.
        webhook_id: The webhook ID associated with the notification.
        confirm_id: The ID of the notification to confirm.

    Returns:
        The response from the WebSocket command.

    Raises:
        ValueError: If webhook_id or confirm_id is empty.
    """
    if not webhook_id:
        raise ValueError("webhook_id is required")
    if not confirm_id:
        raise ValueError("confirm_id is required")
    payload: dict[str, Any] = {
        "webhook_id": webhook_id,
        "confirm_id": confirm_id,
    }
    return client.ws_call("mobile_app/push_notification_confirm", payload)
