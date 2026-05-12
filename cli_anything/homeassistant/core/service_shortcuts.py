"""Service call shortcuts for common Home Assistant operations.

Thin wrappers around client.post("services/<domain>/<service>", payload).
Each function validates its inputs and constructs the appropriate payload,
omitting None-valued kwargs from the final request.
"""

from __future__ import annotations


def notify(client, *, message: str, title: str | None = None,
           target: str | list[str] | None = None, data: dict | None = None,
           service: str = "notify") -> dict:
    """Send a notification.

    POST services/notify/<service>.
    Validates message is non-empty.
    """
    if not message:
        raise ValueError("message is required and must be non-empty")

    payload: dict = {"message": message}
    if title is not None:
        payload["title"] = title
    if target is not None:
        payload["target"] = target
    if data is not None:
        payload["data"] = data

    return client.post(f"services/notify/{service}", payload)


def mqtt_publish(client, *, topic: str, payload: str | None = None,
                 qos: int = 0, retain: bool = False) -> dict:
    """Publish to an MQTT topic.

    POST services/mqtt/publish.
    Validates topic is non-empty and qos is in {0, 1, 2}.
    """
    if not topic:
        raise ValueError("topic is required and must be non-empty")
    if qos not in (0, 1, 2):
        raise ValueError(f"qos must be 0, 1, or 2, got {qos!r}")

    post_payload: dict = {"topic": topic}
    if payload is not None:
        post_payload["payload"] = payload
    post_payload["qos"] = qos
    post_payload["retain"] = retain

    return client.post("services/mqtt/publish", post_payload)


def lock_lock(client, entity_id: str, *, code: str | None = None) -> dict:
    """Lock a lock entity.

    POST services/lock/lock.
    Validates entity_id starts with "lock.".
    """
    if not entity_id.startswith("lock."):
        raise ValueError(f"expected lock.* entity_id, got {entity_id!r}")

    payload: dict = {"entity_id": entity_id}
    if code is not None:
        payload["code"] = code

    return client.post("services/lock/lock", payload)


def lock_unlock(client, entity_id: str, *, code: str | None = None) -> dict:
    """Unlock a lock entity.

    POST services/lock/unlock.
    Validates entity_id starts with "lock.".
    """
    if not entity_id.startswith("lock."):
        raise ValueError(f"expected lock.* entity_id, got {entity_id!r}")

    payload: dict = {"entity_id": entity_id}
    if code is not None:
        payload["code"] = code

    return client.post("services/lock/unlock", payload)


def lock_open(client, entity_id: str, *, code: str | None = None) -> dict:
    """Open a lock entity (garage door, etc.).

    POST services/lock/open.
    Validates entity_id starts with "lock.".
    """
    if not entity_id.startswith("lock."):
        raise ValueError(f"expected lock.* entity_id, got {entity_id!r}")

    payload: dict = {"entity_id": entity_id}
    if code is not None:
        payload["code"] = code

    return client.post("services/lock/open", payload)


def alarm_arm_away(client, entity_id: str, *, code: str | None = None) -> dict:
    """Arm alarm in away mode.

    POST services/alarm_control_panel/alarm_arm_away.
    Validates entity_id starts with "alarm_control_panel.".
    """
    if not entity_id.startswith("alarm_control_panel."):
        raise ValueError(f"expected alarm_control_panel.* entity_id, got {entity_id!r}")

    payload: dict = {"entity_id": entity_id}
    if code is not None:
        payload["code"] = code

    return client.post("services/alarm_control_panel/alarm_arm_away", payload)


def alarm_arm_home(client, entity_id: str, *, code: str | None = None) -> dict:
    """Arm alarm in home mode.

    POST services/alarm_control_panel/alarm_arm_home.
    Validates entity_id starts with "alarm_control_panel.".
    """
    if not entity_id.startswith("alarm_control_panel."):
        raise ValueError(f"expected alarm_control_panel.* entity_id, got {entity_id!r}")

    payload: dict = {"entity_id": entity_id}
    if code is not None:
        payload["code"] = code

    return client.post("services/alarm_control_panel/alarm_arm_home", payload)


def alarm_arm_night(client, entity_id: str, *, code: str | None = None) -> dict:
    """Arm alarm in night mode.

    POST services/alarm_control_panel/alarm_arm_night.
    Validates entity_id starts with "alarm_control_panel.".
    """
    if not entity_id.startswith("alarm_control_panel."):
        raise ValueError(f"expected alarm_control_panel.* entity_id, got {entity_id!r}")

    payload: dict = {"entity_id": entity_id}
    if code is not None:
        payload["code"] = code

    return client.post("services/alarm_control_panel/alarm_arm_night", payload)


def alarm_disarm(client, entity_id: str, *, code: str | None = None) -> dict:
    """Disarm alarm.

    POST services/alarm_control_panel/alarm_disarm.
    Validates entity_id starts with "alarm_control_panel.".
    """
    if not entity_id.startswith("alarm_control_panel."):
        raise ValueError(f"expected alarm_control_panel.* entity_id, got {entity_id!r}")

    payload: dict = {"entity_id": entity_id}
    if code is not None:
        payload["code"] = code

    return client.post("services/alarm_control_panel/alarm_disarm", payload)


def persistent_notification_create(client, *, message: str,
                                   title: str | None = None,
                                   notification_id: str | None = None) -> dict:
    """Create a persistent notification.

    POST services/persistent_notification/create.
    Validates message is non-empty.
    """
    if not message:
        raise ValueError("message is required and must be non-empty")

    payload: dict = {"message": message}
    if title is not None:
        payload["title"] = title
    if notification_id is not None:
        payload["notification_id"] = notification_id

    return client.post("services/persistent_notification/create", payload)


def persistent_notification_dismiss(client, *, notification_id: str) -> dict:
    """Dismiss a persistent notification.

    POST services/persistent_notification/dismiss.
    Validates notification_id is non-empty.
    """
    if not notification_id:
        raise ValueError("notification_id is required and must be non-empty")

    payload: dict = {"notification_id": notification_id}

    return client.post("services/persistent_notification/dismiss", payload)
