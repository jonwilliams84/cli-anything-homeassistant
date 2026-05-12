"""Mobile app push notification channel — WS commands for push notification testing.

The mobile_app integration is primarily a server-to-client channel: the phone
subscribes to push notifications. These wrappers are useful for CLI testing of
push notification flows by allowing clients to interact with the subscription
and confirmation lifecycle.

`open_push_channel(webhook_id)` opens a push notification subscription (registers
the client as a listener for incoming push notifications to the given webhook ID).

`confirm_push_notification(webhook_id, confirm_id)` confirms receipt of a specific
push notification by ID.
"""

from __future__ import annotations

from typing import Any


def open_push_channel(client, *, webhook_id: str) -> Any:
    """Open a push notification channel for the given webhook ID.

    This sends a WebSocket `mobile_app/push_notification_channel` subscription
    command. The phone will then receive push notifications sent to this webhook.

    Args:
        client: HomeAssistant client.
        webhook_id: The webhook ID to subscribe to push notifications for.

    Returns:
        The response from the WebSocket command.

    Raises:
        ValueError: If webhook_id is empty.
    """
    if not webhook_id:
        raise ValueError("webhook_id is required")
    payload: dict[str, Any] = {
        "webhook_id": webhook_id,
        "support_confirm": True,
    }
    return client.ws_call("mobile_app/push_notification_channel", payload)


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
