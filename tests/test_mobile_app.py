"""Unit tests for mobile_app module."""

from __future__ import annotations

import threading

import pytest

from tests.conftest import SubscribingFakeClient
from cli_anything.homeassistant.core import mobile_app


class TestMobileApp:
    """Test mobile app push notification channel operations."""

    # ── open_push_channel ───────────────────────────────────────────────────

    def test_open_push_channel_calls_ws_subscribe(self):
        """open_push_channel calls ws_subscribe with the correct type and payload."""
        client = SubscribingFakeClient()
        stop = threading.Event()
        stop.set()
        mobile_app.open_push_channel(
            client,
            webhook_id="webhook-123",
            on_event=lambda e: None,
            stop_event=stop,
        )
        assert len(client.subscribe_calls) == 1
        msg_type, payload = client.subscribe_calls[0]
        assert msg_type == "mobile_app/push_notification_channel"
        assert payload["webhook_id"] == "webhook-123"
        assert payload["support_confirm"] is True

    def test_open_push_channel_delivers_events(self):
        """open_push_channel forwards push notification events to on_event."""
        client = SubscribingFakeClient()
        ev = {"title": "Test Push", "message": "Hello"}
        client.queue_events(ev)
        received = []
        mobile_app.open_push_channel(
            client,
            webhook_id="webhook-abc",
            on_event=received.append,
            max_events=1,
        )
        assert received == [ev]

    def test_open_push_channel_max_events_auto_stop(self):
        """open_push_channel stops after max_events deliveries."""
        client = SubscribingFakeClient()
        client.queue_events({"n": 1}, {"n": 2}, {"n": 3})
        received = []
        mobile_app.open_push_channel(
            client,
            webhook_id="webhook-xyz",
            on_event=received.append,
            max_events=2,
        )
        assert received == [{"n": 1}, {"n": 2}]

    def test_open_push_channel_stop_event(self):
        """open_push_channel respects a pre-set stop_event."""
        client = SubscribingFakeClient()
        client.queue_events({"n": 1})
        stop = threading.Event()
        stop.set()
        received = []
        mobile_app.open_push_channel(
            client,
            webhook_id="webhook-123",
            on_event=received.append,
            stop_event=stop,
        )
        assert received == []

    def test_open_push_channel_requires_webhook_id(self):
        """open_push_channel raises ValueError if webhook_id is empty."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="webhook_id is required"):
            mobile_app.open_push_channel(
                client, webhook_id="", on_event=lambda e: None, max_events=1
            )

    def test_open_push_channel_raises_without_stop_or_max(self):
        """open_push_channel raises ValueError if no stop_event or max_events."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="must supply stop_event or max_events"):
            mobile_app.open_push_channel(
                client, webhook_id="webhook-123", on_event=lambda e: None
            )

    def test_open_push_channel_raises_on_non_callable(self):
        """open_push_channel raises ValueError if on_event is not callable."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="on_event must be callable"):
            mobile_app.open_push_channel(
                client,
                webhook_id="webhook-123",
                on_event="not_callable",  # type: ignore[arg-type]
                max_events=1,
            )

    # ── confirm_push_notification ────────────────────────────────────────────

    def test_confirm_push_notification_happy_path(self, fake_client):
        """confirm_push_notification sends mobile_app/push_notification_confirm."""
        fake_client.set_ws("mobile_app/push_notification_confirm", {"success": True})
        result = mobile_app.confirm_push_notification(
            fake_client, webhook_id="webhook-123", confirm_id="notif-456"
        )
        assert result == {"success": True}
        assert fake_client.ws_calls[-1]["type"] == "mobile_app/push_notification_confirm"
        assert fake_client.ws_calls[-1]["payload"]["webhook_id"] == "webhook-123"
        assert fake_client.ws_calls[-1]["payload"]["confirm_id"] == "notif-456"

    def test_confirm_push_notification_requires_webhook_id(self, fake_client):
        """confirm_push_notification raises ValueError if webhook_id is empty."""
        with pytest.raises(ValueError, match="webhook_id is required"):
            mobile_app.confirm_push_notification(
                fake_client, webhook_id="", confirm_id="notif-456"
            )

    def test_confirm_push_notification_requires_confirm_id(self, fake_client):
        """confirm_push_notification raises ValueError if confirm_id is empty."""
        with pytest.raises(ValueError, match="confirm_id is required"):
            mobile_app.confirm_push_notification(
                fake_client, webhook_id="webhook-123", confirm_id=""
            )
