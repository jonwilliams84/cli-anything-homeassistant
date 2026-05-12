"""Unit tests for mobile_app module."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import mobile_app


class TestMobileApp:
    """Test mobile app push notification channel operations."""

    def test_open_push_channel_happy_path(self, fake_client):
        """Test opening a push notification channel with valid webhook_id."""
        fake_client.set_ws("mobile_app/push_notification_channel", {"success": True})
        result = mobile_app.open_push_channel(fake_client, webhook_id="webhook-123")
        assert result == {"success": True}
        assert fake_client.ws_calls[-1]["type"] == "mobile_app/push_notification_channel"
        assert fake_client.ws_calls[-1]["payload"]["webhook_id"] == "webhook-123"
        assert fake_client.ws_calls[-1]["payload"]["support_confirm"] is True

    def test_open_push_channel_requires_webhook_id(self, fake_client):
        """Test that open_push_channel raises ValueError if webhook_id is empty."""
        with pytest.raises(ValueError, match="webhook_id is required"):
            mobile_app.open_push_channel(fake_client, webhook_id="")

    def test_confirm_push_notification_happy_path(self, fake_client):
        """Test confirming a push notification with valid IDs."""
        fake_client.set_ws("mobile_app/push_notification_confirm", {"success": True})
        result = mobile_app.confirm_push_notification(
            fake_client, webhook_id="webhook-123", confirm_id="notif-456"
        )
        assert result == {"success": True}
        assert fake_client.ws_calls[-1]["type"] == "mobile_app/push_notification_confirm"
        assert fake_client.ws_calls[-1]["payload"]["webhook_id"] == "webhook-123"
        assert fake_client.ws_calls[-1]["payload"]["confirm_id"] == "notif-456"

    def test_confirm_push_notification_requires_webhook_id(self, fake_client):
        """Test that confirm_push_notification raises ValueError if webhook_id is empty."""
        with pytest.raises(ValueError, match="webhook_id is required"):
            mobile_app.confirm_push_notification(
                fake_client, webhook_id="", confirm_id="notif-456"
            )

    def test_confirm_push_notification_requires_confirm_id(self, fake_client):
        """Test that confirm_push_notification raises ValueError if confirm_id is empty."""
        with pytest.raises(ValueError, match="confirm_id is required"):
            mobile_app.confirm_push_notification(
                fake_client, webhook_id="webhook-123", confirm_id=""
            )
