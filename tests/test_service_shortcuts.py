"""Unit tests for service_shortcuts module."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import service_shortcuts


class TestServiceShortcuts:
    """Tests for service shortcut functions."""

    # ────────────────────────────────────────────────────────────────────────
    # notify
    # ────────────────────────────────────────────────────────────────────────

    def test_notify_minimal(self, fake_client):
        """Test notify with only required message."""
        service_shortcuts.notify(fake_client, message="Hello")
        assert fake_client.calls[-1]["path"] == "services/notify/notify"
        assert fake_client.calls[-1]["payload"] == {"message": "Hello"}

    def test_notify_with_title(self, fake_client):
        """Test notify with message and title."""
        service_shortcuts.notify(fake_client, message="Hello", title="Alert")
        assert fake_client.calls[-1]["path"] == "services/notify/notify"
        assert fake_client.calls[-1]["payload"] == {
            "message": "Hello",
            "title": "Alert",
        }

    def test_notify_with_target_string(self, fake_client):
        """Test notify with target as string."""
        service_shortcuts.notify(fake_client, message="Hello", target="mobile_app_phone")
        assert fake_client.calls[-1]["path"] == "services/notify/notify"
        assert fake_client.calls[-1]["payload"] == {
            "message": "Hello",
            "target": "mobile_app_phone",
        }

    def test_notify_with_target_list(self, fake_client):
        """Test notify with target as list."""
        service_shortcuts.notify(fake_client, message="Hello",
                                 target=["mobile_app_phone", "mobile_app_tablet"])
        assert fake_client.calls[-1]["path"] == "services/notify/notify"
        assert fake_client.calls[-1]["payload"] == {
            "message": "Hello",
            "target": ["mobile_app_phone", "mobile_app_tablet"],
        }

    def test_notify_with_data(self, fake_client):
        """Test notify with data dict."""
        service_shortcuts.notify(fake_client, message="Hello",
                                 data={"channel": "alarm"})
        assert fake_client.calls[-1]["path"] == "services/notify/notify"
        assert fake_client.calls[-1]["payload"] == {
            "message": "Hello",
            "data": {"channel": "alarm"},
        }

    def test_notify_with_custom_service(self, fake_client):
        """Test notify with custom service name."""
        service_shortcuts.notify(fake_client, message="Hello",
                                 service="telegram")
        assert fake_client.calls[-1]["path"] == "services/notify/telegram"
        assert fake_client.calls[-1]["payload"] == {"message": "Hello"}

    def test_notify_with_all_options(self, fake_client):
        """Test notify with all options."""
        service_shortcuts.notify(fake_client, message="Alert",
                                 title="Warning", target="phone",
                                 data={"priority": "high"}, service="email")
        assert fake_client.calls[-1]["path"] == "services/notify/email"
        assert fake_client.calls[-1]["payload"] == {
            "message": "Alert",
            "title": "Warning",
            "target": "phone",
            "data": {"priority": "high"},
        }

    def test_notify_empty_message_raises(self, fake_client):
        """Test notify raises ValueError for empty message."""
        with pytest.raises(ValueError, match="message is required"):
            service_shortcuts.notify(fake_client, message="")

    def test_notify_none_message_raises(self, fake_client):
        """Test notify raises ValueError when message is missing (keyword-only)."""
        with pytest.raises(TypeError):
            service_shortcuts.notify(fake_client)  # type: ignore

    # ────────────────────────────────────────────────────────────────────────
    # mqtt_publish
    # ────────────────────────────────────────────────────────────────────────

    def test_mqtt_publish_minimal(self, fake_client):
        """Test mqtt_publish with only topic."""
        service_shortcuts.mqtt_publish(fake_client, topic="home/living_room/temp")
        assert fake_client.calls[-1]["path"] == "services/mqtt/publish"
        assert fake_client.calls[-1]["payload"] == {
            "topic": "home/living_room/temp",
            "qos": 0,
            "retain": False,
        }

    def test_mqtt_publish_with_payload(self, fake_client):
        """Test mqtt_publish with payload."""
        service_shortcuts.mqtt_publish(fake_client, topic="home/temp",
                                       payload="23.5")
        assert fake_client.calls[-1]["path"] == "services/mqtt/publish"
        assert fake_client.calls[-1]["payload"] == {
            "topic": "home/temp",
            "payload": "23.5",
            "qos": 0,
            "retain": False,
        }

    def test_mqtt_publish_with_qos(self, fake_client):
        """Test mqtt_publish with custom QoS."""
        service_shortcuts.mqtt_publish(fake_client, topic="home/temp",
                                       payload="23.5", qos=1)
        assert fake_client.calls[-1]["payload"] == {
            "topic": "home/temp",
            "payload": "23.5",
            "qos": 1,
            "retain": False,
        }

    def test_mqtt_publish_with_retain(self, fake_client):
        """Test mqtt_publish with retain flag."""
        service_shortcuts.mqtt_publish(fake_client, topic="home/temp",
                                       payload="23.5", retain=True)
        assert fake_client.calls[-1]["payload"] == {
            "topic": "home/temp",
            "payload": "23.5",
            "qos": 0,
            "retain": True,
        }

    def test_mqtt_publish_empty_topic_raises(self, fake_client):
        """Test mqtt_publish raises ValueError for empty topic."""
        with pytest.raises(ValueError, match="topic is required"):
            service_shortcuts.mqtt_publish(fake_client, topic="")

    def test_mqtt_publish_invalid_qos_raises(self, fake_client):
        """Test mqtt_publish raises ValueError for invalid QoS."""
        with pytest.raises(ValueError, match="qos must be 0, 1, or 2"):
            service_shortcuts.mqtt_publish(fake_client, topic="home/temp", qos=3)

    def test_mqtt_publish_invalid_qos_negative_raises(self, fake_client):
        """Test mqtt_publish raises ValueError for negative QoS."""
        with pytest.raises(ValueError, match="qos must be 0, 1, or 2"):
            service_shortcuts.mqtt_publish(fake_client, topic="home/temp", qos=-1)

    # ────────────────────────────────────────────────────────────────────────
    # lock_lock
    # ────────────────────────────────────────────────────────────────────────

    def test_lock_lock_minimal(self, fake_client):
        """Test lock_lock with only entity_id."""
        service_shortcuts.lock_lock(fake_client, "lock.front_door")
        assert fake_client.calls[-1]["path"] == "services/lock/lock"
        assert fake_client.calls[-1]["payload"] == {"entity_id": "lock.front_door"}

    def test_lock_lock_with_code(self, fake_client):
        """Test lock_lock with code."""
        service_shortcuts.lock_lock(fake_client, "lock.front_door", code="1234")
        assert fake_client.calls[-1]["path"] == "services/lock/lock"
        assert fake_client.calls[-1]["payload"] == {
            "entity_id": "lock.front_door",
            "code": "1234",
        }

    def test_lock_lock_invalid_entity_raises(self, fake_client):
        """Test lock_lock raises ValueError for non-lock entity_id."""
        with pytest.raises(ValueError, match="expected lock.*"):
            service_shortcuts.lock_lock(fake_client, "switch.front_door")

    def test_lock_lock_invalid_entity_no_domain_raises(self, fake_client):
        """Test lock_lock raises ValueError for malformed entity_id."""
        with pytest.raises(ValueError, match="expected lock.*"):
            service_shortcuts.lock_lock(fake_client, "lock")

    # ────────────────────────────────────────────────────────────────────────
    # lock_unlock
    # ────────────────────────────────────────────────────────────────────────

    def test_lock_unlock_minimal(self, fake_client):
        """Test lock_unlock with only entity_id."""
        service_shortcuts.lock_unlock(fake_client, "lock.front_door")
        assert fake_client.calls[-1]["path"] == "services/lock/unlock"
        assert fake_client.calls[-1]["payload"] == {"entity_id": "lock.front_door"}

    def test_lock_unlock_with_code(self, fake_client):
        """Test lock_unlock with code."""
        service_shortcuts.lock_unlock(fake_client, "lock.front_door", code="1234")
        assert fake_client.calls[-1]["path"] == "services/lock/unlock"
        assert fake_client.calls[-1]["payload"] == {
            "entity_id": "lock.front_door",
            "code": "1234",
        }

    def test_lock_unlock_invalid_entity_raises(self, fake_client):
        """Test lock_unlock raises ValueError for non-lock entity_id."""
        with pytest.raises(ValueError, match="expected lock.*"):
            service_shortcuts.lock_unlock(fake_client, "switch.front_door")

    # ────────────────────────────────────────────────────────────────────────
    # lock_open
    # ────────────────────────────────────────────────────────────────────────

    def test_lock_open_minimal(self, fake_client):
        """Test lock_open with only entity_id."""
        service_shortcuts.lock_open(fake_client, "lock.garage_door")
        assert fake_client.calls[-1]["path"] == "services/lock/open"
        assert fake_client.calls[-1]["payload"] == {"entity_id": "lock.garage_door"}

    def test_lock_open_with_code(self, fake_client):
        """Test lock_open with code."""
        service_shortcuts.lock_open(fake_client, "lock.garage_door", code="5678")
        assert fake_client.calls[-1]["path"] == "services/lock/open"
        assert fake_client.calls[-1]["payload"] == {
            "entity_id": "lock.garage_door",
            "code": "5678",
        }

    def test_lock_open_invalid_entity_raises(self, fake_client):
        """Test lock_open raises ValueError for non-lock entity_id."""
        with pytest.raises(ValueError, match="expected lock.*"):
            service_shortcuts.lock_open(fake_client, "light.garage")

    # ────────────────────────────────────────────────────────────────────────
    # alarm_arm_away
    # ────────────────────────────────────────────────────────────────────────

    def test_alarm_arm_away_minimal(self, fake_client):
        """Test alarm_arm_away with only entity_id."""
        service_shortcuts.alarm_arm_away(fake_client, "alarm_control_panel.home")
        assert fake_client.calls[-1]["path"] == "services/alarm_control_panel/alarm_arm_away"
        assert fake_client.calls[-1]["payload"] == {
            "entity_id": "alarm_control_panel.home"
        }

    def test_alarm_arm_away_with_code(self, fake_client):
        """Test alarm_arm_away with code."""
        service_shortcuts.alarm_arm_away(fake_client, "alarm_control_panel.home",
                                         code="1234")
        assert fake_client.calls[-1]["path"] == "services/alarm_control_panel/alarm_arm_away"
        assert fake_client.calls[-1]["payload"] == {
            "entity_id": "alarm_control_panel.home",
            "code": "1234",
        }

    def test_alarm_arm_away_invalid_entity_raises(self, fake_client):
        """Test alarm_arm_away raises ValueError for wrong entity_id."""
        with pytest.raises(ValueError, match="expected alarm_control_panel.*"):
            service_shortcuts.alarm_arm_away(fake_client, "lock.door")

    # ────────────────────────────────────────────────────────────────────────
    # alarm_arm_home
    # ────────────────────────────────────────────────────────────────────────

    def test_alarm_arm_home_minimal(self, fake_client):
        """Test alarm_arm_home with only entity_id."""
        service_shortcuts.alarm_arm_home(fake_client, "alarm_control_panel.home")
        assert fake_client.calls[-1]["path"] == "services/alarm_control_panel/alarm_arm_home"
        assert fake_client.calls[-1]["payload"] == {
            "entity_id": "alarm_control_panel.home"
        }

    def test_alarm_arm_home_with_code(self, fake_client):
        """Test alarm_arm_home with code."""
        service_shortcuts.alarm_arm_home(fake_client, "alarm_control_panel.home",
                                         code="1234")
        assert fake_client.calls[-1]["path"] == "services/alarm_control_panel/alarm_arm_home"
        assert fake_client.calls[-1]["payload"] == {
            "entity_id": "alarm_control_panel.home",
            "code": "1234",
        }

    def test_alarm_arm_home_invalid_entity_raises(self, fake_client):
        """Test alarm_arm_home raises ValueError for wrong entity_id."""
        with pytest.raises(ValueError, match="expected alarm_control_panel.*"):
            service_shortcuts.alarm_arm_home(fake_client, "switch.alarm")

    # ────────────────────────────────────────────────────────────────────────
    # alarm_arm_night
    # ────────────────────────────────────────────────────────────────────────

    def test_alarm_arm_night_minimal(self, fake_client):
        """Test alarm_arm_night with only entity_id."""
        service_shortcuts.alarm_arm_night(fake_client, "alarm_control_panel.home")
        assert fake_client.calls[-1]["path"] == "services/alarm_control_panel/alarm_arm_night"
        assert fake_client.calls[-1]["payload"] == {
            "entity_id": "alarm_control_panel.home"
        }

    def test_alarm_arm_night_with_code(self, fake_client):
        """Test alarm_arm_night with code."""
        service_shortcuts.alarm_arm_night(fake_client, "alarm_control_panel.home",
                                          code="9999")
        assert fake_client.calls[-1]["path"] == "services/alarm_control_panel/alarm_arm_night"
        assert fake_client.calls[-1]["payload"] == {
            "entity_id": "alarm_control_panel.home",
            "code": "9999",
        }

    def test_alarm_arm_night_invalid_entity_raises(self, fake_client):
        """Test alarm_arm_night raises ValueError for wrong entity_id."""
        with pytest.raises(ValueError, match="expected alarm_control_panel.*"):
            service_shortcuts.alarm_arm_night(fake_client, "input_boolean.alarm")

    # ────────────────────────────────────────────────────────────────────────
    # alarm_disarm
    # ────────────────────────────────────────────────────────────────────────

    def test_alarm_disarm_minimal(self, fake_client):
        """Test alarm_disarm with only entity_id."""
        service_shortcuts.alarm_disarm(fake_client, "alarm_control_panel.home")
        assert fake_client.calls[-1]["path"] == "services/alarm_control_panel/alarm_disarm"
        assert fake_client.calls[-1]["payload"] == {
            "entity_id": "alarm_control_panel.home"
        }

    def test_alarm_disarm_with_code(self, fake_client):
        """Test alarm_disarm with code."""
        service_shortcuts.alarm_disarm(fake_client, "alarm_control_panel.home",
                                       code="0000")
        assert fake_client.calls[-1]["path"] == "services/alarm_control_panel/alarm_disarm"
        assert fake_client.calls[-1]["payload"] == {
            "entity_id": "alarm_control_panel.home",
            "code": "0000",
        }

    def test_alarm_disarm_invalid_entity_raises(self, fake_client):
        """Test alarm_disarm raises ValueError for wrong entity_id."""
        with pytest.raises(ValueError, match="expected alarm_control_panel.*"):
            service_shortcuts.alarm_disarm(fake_client, "cover.blinds")

    # ────────────────────────────────────────────────────────────────────────
    # persistent_notification_create
    # ────────────────────────────────────────────────────────────────────────

    def test_persistent_notification_create_minimal(self, fake_client):
        """Test persistent_notification_create with only message."""
        service_shortcuts.persistent_notification_create(
            fake_client, message="System update completed"
        )
        assert fake_client.calls[-1]["path"] == "services/persistent_notification/create"
        assert fake_client.calls[-1]["payload"] == {
            "message": "System update completed"
        }

    def test_persistent_notification_create_with_title(self, fake_client):
        """Test persistent_notification_create with title."""
        service_shortcuts.persistent_notification_create(
            fake_client, message="Update done", title="System"
        )
        assert fake_client.calls[-1]["path"] == "services/persistent_notification/create"
        assert fake_client.calls[-1]["payload"] == {
            "message": "Update done",
            "title": "System",
        }

    def test_persistent_notification_create_with_id(self, fake_client):
        """Test persistent_notification_create with notification_id."""
        service_shortcuts.persistent_notification_create(
            fake_client, message="Warning", notification_id="my_warning"
        )
        assert fake_client.calls[-1]["path"] == "services/persistent_notification/create"
        assert fake_client.calls[-1]["payload"] == {
            "message": "Warning",
            "notification_id": "my_warning",
        }

    def test_persistent_notification_create_with_all_options(self, fake_client):
        """Test persistent_notification_create with all options."""
        service_shortcuts.persistent_notification_create(
            fake_client, message="Critical", title="Alert",
            notification_id="critical_alert"
        )
        assert fake_client.calls[-1]["path"] == "services/persistent_notification/create"
        assert fake_client.calls[-1]["payload"] == {
            "message": "Critical",
            "title": "Alert",
            "notification_id": "critical_alert",
        }

    def test_persistent_notification_create_empty_message_raises(self, fake_client):
        """Test persistent_notification_create raises for empty message."""
        with pytest.raises(ValueError, match="message is required"):
            service_shortcuts.persistent_notification_create(fake_client, message="")

    # ────────────────────────────────────────────────────────────────────────
    # persistent_notification_dismiss
    # ────────────────────────────────────────────────────────────────────────

    def test_persistent_notification_dismiss(self, fake_client):
        """Test persistent_notification_dismiss."""
        service_shortcuts.persistent_notification_dismiss(
            fake_client, notification_id="my_warning"
        )
        assert fake_client.calls[-1]["path"] == "services/persistent_notification/dismiss"
        assert fake_client.calls[-1]["payload"] == {"notification_id": "my_warning"}

    def test_persistent_notification_dismiss_empty_id_raises(self, fake_client):
        """Test persistent_notification_dismiss raises for empty notification_id."""
        with pytest.raises(ValueError, match="notification_id is required"):
            service_shortcuts.persistent_notification_dismiss(fake_client, notification_id="")
