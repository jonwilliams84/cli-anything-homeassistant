"""Unit tests for cli_anything.homeassistant.core.notifications — no real HA required."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import notifications


class TestListNotifications:
    def test_list_response(self, fake_client):
        fake_client.set_ws("persistent_notification/get", [
            {"notification_id": "n1", "title": "Alert", "message": "Hi",
             "created_at": "2024-01-01T00:00:00+00:00", "status": "unread"},
        ])
        rows = notifications.list_notifications(fake_client)
        assert len(rows) == 1
        assert rows[0]["notification_id"] == "n1"
        assert rows[0]["title"] == "Alert"
        assert rows[0]["message"] == "Hi"
        assert rows[0]["created_at"] == "2024-01-01T00:00:00+00:00"
        assert rows[0]["status"] == "unread"

    def test_dict_response_uses_values(self, fake_client):
        """Some HA versions return a dict keyed by notification_id."""
        fake_client.set_ws("persistent_notification/get", {
            "n1": {"notification_id": "n1", "title": "A", "message": "M"},
            "n2": {"notification_id": "n2", "title": "B", "message": "M2"},
        })
        rows = notifications.list_notifications(fake_client)
        assert {r["notification_id"] for r in rows} == {"n1", "n2"}

    def test_non_list_non_dict_returns_empty(self, fake_client):
        fake_client.set_ws("persistent_notification/get", "garbage")
        assert notifications.list_notifications(fake_client) == []

    def test_none_response_returns_empty(self, fake_client):
        fake_client.set_ws("persistent_notification/get", None)
        assert notifications.list_notifications(fake_client) == []

    def test_skips_non_dict_items(self, fake_client):
        fake_client.set_ws("persistent_notification/get", [
            "garbage",
            42,
            {"notification_id": "ok", "title": "T", "message": "M"},
        ])
        rows = notifications.list_notifications(fake_client)
        assert len(rows) == 1
        assert rows[0]["notification_id"] == "ok"

    def test_missing_fields_become_none(self, fake_client):
        fake_client.set_ws("persistent_notification/get", [{"notification_id": "n1"}])
        rows = notifications.list_notifications(fake_client)
        assert rows[0]["title"] is None
        assert rows[0]["message"] is None
        assert rows[0]["created_at"] is None
        assert rows[0]["status"] is None


class TestCreate:
    def test_minimal_create(self, fake_client):
        notifications.create(fake_client, message="Hello")
        call = fake_client.service_calls[-1]
        assert call["domain"] == "persistent_notification"
        assert call["service"] == "create"
        assert call["service_data"] == {"message": "Hello"}

    def test_create_with_title_and_id(self, fake_client):
        notifications.create(
            fake_client, message="Hello", title="Alert", notification_id="my_id"
        )
        call = fake_client.service_calls[-1]
        assert call["service_data"] == {
            "message": "Hello", "title": "Alert", "notification_id": "my_id",
        }

    def test_empty_message_raises(self, fake_client):
        with pytest.raises(ValueError, match="message is required"):
            notifications.create(fake_client, message="")


class TestDismiss:
    def test_sends_dismiss(self, fake_client):
        notifications.dismiss(fake_client, "n1")
        call = fake_client.service_calls[-1]
        assert call["domain"] == "persistent_notification"
        assert call["service"] == "dismiss"
        assert call["service_data"] == {"notification_id": "n1"}

    def test_empty_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="notification_id is required"):
            notifications.dismiss(fake_client, "")


class TestDismissAll:
    def test_sends_dismiss_all(self, fake_client):
        notifications.dismiss_all(fake_client)
        call = fake_client.service_calls[-1]
        assert call["domain"] == "persistent_notification"
        assert call["service"] == "dismiss_all"


class TestMarkRead:
    def test_sends_mark_read(self, fake_client):
        notifications.mark_read(fake_client, "n1")
        call = fake_client.service_calls[-1]
        assert call["domain"] == "persistent_notification"
        assert call["service"] == "mark_read"
        assert call["service_data"] == {"notification_id": "n1"}

    def test_empty_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="notification_id is required"):
            notifications.mark_read(fake_client, "")
