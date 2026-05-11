"""Persistent notifications — list / create / dismiss.

The "bell" notifications in the HA UI. They're stored as a special
domain in the state machine (`persistent_notification.*`) and managed via
`persistent_notification.create` / `dismiss` / `dismiss_all` services.
"""

from __future__ import annotations

from typing import Any, Optional

from cli_anything.homeassistant.core import services as services_core
from cli_anything.homeassistant.core import states as states_core


def list_notifications(client) -> list[dict]:
    """Return one row per current persistent notification.

    Modern HA exposes these via the `persistent_notification/get` WS call; the
    state-machine path was deprecated. Each row:
        {notification_id, title, message, created_at, status}.
    """
    data = client.ws_call("persistent_notification/get") or []
    rows: list[dict] = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = list(data.values())
    else:
        items = []
    for n in items:
        if not isinstance(n, dict):
            continue
        rows.append({
            "notification_id": n.get("notification_id"),
            "title": n.get("title"),
            "message": n.get("message"),
            "created_at": n.get("created_at"),
            "status": n.get("status"),
        })
    return rows


def create(client, *, message: str, title: Optional[str] = None,
            notification_id: Optional[str] = None) -> Any:
    """Create (or update by id) a persistent notification."""
    if not message:
        raise ValueError("message is required")
    data: dict[str, Any] = {"message": message}
    if title:           data["title"] = title
    if notification_id: data["notification_id"] = notification_id
    return services_core.call_service(client, "persistent_notification", "create",
                                       service_data=data)


def dismiss(client, notification_id: str) -> Any:
    """Dismiss one notification by id (the slug after `persistent_notification.`)."""
    if not notification_id:
        raise ValueError("notification_id is required")
    return services_core.call_service(client, "persistent_notification", "dismiss",
                                       service_data={"notification_id": notification_id})


def dismiss_all(client) -> Any:
    """Wipe every persistent notification (including system-generated ones)."""
    return services_core.call_service(client, "persistent_notification", "dismiss_all")


def mark_read(client, notification_id: str) -> Any:
    """Mark a notification as read without dismissing it."""
    if not notification_id:
        raise ValueError("notification_id is required")
    return services_core.call_service(client, "persistent_notification", "mark_read",
                                       service_data={"notification_id": notification_id})
