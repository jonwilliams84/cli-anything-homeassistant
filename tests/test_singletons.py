"""Unit tests for cli_anything.homeassistant.core.singletons."""

from __future__ import annotations

import threading
from typing import Any

import pytest

from tests.conftest import FakeClient
from cli_anything.homeassistant.core import singletons


# ────────────────────────────────────────────────────────────────────────────
# SubscribingFakeClient — extends FakeClient with ws_subscribe support
# ────────────────────────────────────────────────────────────────────────────

class SubscribingFakeClient(FakeClient):
    """FakeClient subclass that records ws_subscribe calls and replays
    a configurable queue of pre-set events synchronously.

    Usage::

        client = SubscribingFakeClient()
        client.preset_events = [{"id": 1}, {"id": 2}]
        # When ws_subscribe is called the handler will receive both events.
    """

    def __init__(self):
        super().__init__()
        self.subscribe_calls: list[dict] = []
        self.preset_events: list[Any] = []

    def ws_subscribe(
        self,
        msg_type: str,
        payload: dict | None,
        on_message=None,
        stop_event: threading.Event | None = None,
        **kwargs,
    ) -> None:
        """Record the call then feed preset_events to on_message.

        Accepts both positional and keyword forms of on_message/stop_event so
        that callers using ``on_message=`` or ``stop_event=`` keyword args work
        transparently.
        """
        # Merge any keyword overrides (some functions use keyword-only args).
        if on_message is None:
            on_message = kwargs.get("on_message")
        stop_event = kwargs.get("stop_event", stop_event)

        self.subscribe_calls.append({
            "type": msg_type,
            "payload": payload,
        })
        for event in self.preset_events:
            if stop_event is not None and stop_event.is_set():
                break
            on_message(event)


# ────────────────────────────────────────────────────────────────────────────
# Test class
# ────────────────────────────────────────────────────────────────────────────

class TestSingletons:

    # ──────────────────────────────────────────────────────────────────────
    # 1. diagnostics_get
    # ──────────────────────────────────────────────────────────────────────

    def test_diagnostics_get_happy_path(self, fake_client):
        """diagnostics_get sends diagnostics/get WS with handler payload."""
        response = {"result": "diagnostics_data"}
        fake_client.set_ws("diagnostics/get", response)
        result = singletons.diagnostics_get(fake_client, handler="mqtt")
        assert result == response
        assert fake_client.ws_calls[-1] == {
            "type": "diagnostics/get",
            "payload": {"handler": "mqtt"}
        }

    def test_diagnostics_get_empty_handler(self, fake_client):
        """diagnostics_get raises ValueError when handler is empty."""
        with pytest.raises(ValueError, match="handler must be a non-empty"):
            singletons.diagnostics_get(fake_client, handler="")

    def test_diagnostics_get_return_shape(self, fake_client):
        """diagnostics_get returns whatever HA sends."""
        fake_client.set_ws("diagnostics/get", {"key": "value"})
        result = singletons.diagnostics_get(fake_client, handler="test")
        assert isinstance(result, dict)
        assert "key" in result

    # ──────────────────────────────────────────────────────────────────────
    # 2. update_release_notes
    # ──────────────────────────────────────────────────────────────────────

    def test_update_release_notes_happy_path(self, fake_client):
        """update_release_notes sends update/release_notes WS."""
        response = {"release_notes": "- Feature 1\n- Feature 2"}
        fake_client.set_ws("update/release_notes", response)
        result = singletons.update_release_notes(fake_client, entity_id="update.myupdate")
        assert result == response
        assert fake_client.ws_calls[-1] == {
            "type": "update/release_notes",
            "payload": {"entity_id": "update.myupdate"}
        }

    def test_update_release_notes_wrong_domain(self, fake_client):
        """update_release_notes raises ValueError for non-update.* entity."""
        with pytest.raises(ValueError, match="expected update\\.\\*"):
            singletons.update_release_notes(fake_client, entity_id="sensor.temperature")

    def test_update_release_notes_return_shape(self, fake_client):
        """update_release_notes returns dict response."""
        fake_client.set_ws("update/release_notes", {"notes": "text"})
        result = singletons.update_release_notes(fake_client, entity_id="update.x")
        assert isinstance(result, dict)

    # ──────────────────────────────────────────────────────────────────────
    # 3. usb_scan
    # ──────────────────────────────────────────────────────────────────────

    def test_usb_scan_happy_path(self, fake_client):
        """usb_scan sends usb/scan WS with no payload."""
        response = {"scanned": True}
        fake_client.set_ws("usb/scan", response)
        result = singletons.usb_scan(fake_client)
        assert result == response
        assert fake_client.ws_calls[-1] == {
            "type": "usb/scan",
            "payload": None
        }

    def test_usb_scan_return_shape(self, fake_client):
        """usb_scan returns whatever HA sends."""
        fake_client.set_ws("usb/scan", {"status": "ok"})
        result = singletons.usb_scan(fake_client)
        assert isinstance(result, dict)

    # ──────────────────────────────────────────────────────────────────────
    # 4. zha_devices_permit
    # ──────────────────────────────────────────────────────────────────────

    def test_zha_devices_permit_happy_path_default_duration(self, fake_client):
        """zha_devices_permit sends zha/devices/permit with default duration=60."""
        response = {"result": "permitted"}
        fake_client.set_ws("zha/devices/permit", response)
        result = singletons.zha_devices_permit(fake_client)
        assert result == response
        assert fake_client.ws_calls[-1] == {
            "type": "zha/devices/permit",
            "payload": {"duration": 60}
        }

    def test_zha_devices_permit_custom_duration(self, fake_client):
        """zha_devices_permit sends custom duration when supplied."""
        response = {}
        fake_client.set_ws("zha/devices/permit", response)
        singletons.zha_devices_permit(fake_client, duration=120)
        assert fake_client.ws_calls[-1]["payload"] == {"duration": 120}

    def test_zha_devices_permit_with_ieee(self, fake_client):
        """zha_devices_permit includes ieee when supplied."""
        response = {}
        fake_client.set_ws("zha/devices/permit", response)
        singletons.zha_devices_permit(
            fake_client, duration=60, ieee="00:11:22:33:44:55:66:77"
        )
        assert fake_client.ws_calls[-1]["payload"] == {
            "duration": 60,
            "ieee": "00:11:22:33:44:55:66:77"
        }

    def test_zha_devices_permit_duration_too_low(self, fake_client):
        """zha_devices_permit raises ValueError when duration < 1."""
        with pytest.raises(ValueError, match="duration must be 1–254"):
            singletons.zha_devices_permit(fake_client, duration=0)

    def test_zha_devices_permit_duration_too_high(self, fake_client):
        """zha_devices_permit raises ValueError when duration > 254."""
        with pytest.raises(ValueError, match="duration must be 1–254"):
            singletons.zha_devices_permit(fake_client, duration=255)

    def test_zha_devices_permit_duration_boundary_low(self, fake_client):
        """zha_devices_permit accepts duration=1."""
        fake_client.set_ws("zha/devices/permit", {})
        singletons.zha_devices_permit(fake_client, duration=1)
        assert fake_client.ws_calls[-1]["payload"]["duration"] == 1

    def test_zha_devices_permit_duration_boundary_high(self, fake_client):
        """zha_devices_permit accepts duration=254."""
        fake_client.set_ws("zha/devices/permit", {})
        singletons.zha_devices_permit(fake_client, duration=254)
        assert fake_client.ws_calls[-1]["payload"]["duration"] == 254

    # ──────────────────────────────────────────────────────────────────────
    # 5. search_related
    # ──────────────────────────────────────────────────────────────────────

    def test_search_related_entity_happy_path(self, fake_client):
        """search_related sends search/related WS with valid item_type."""
        response = {"related": []}
        fake_client.set_ws("search/related", response)
        result = singletons.search_related(
            fake_client, item_type="entity", item_id="light.bedroom"
        )
        assert result == response
        assert fake_client.ws_calls[-1] == {
            "type": "search/related",
            "payload": {"item_type": "entity", "item_id": "light.bedroom"}
        }

    def test_search_related_device(self, fake_client):
        """search_related works with item_type=device."""
        fake_client.set_ws("search/related", [])
        singletons.search_related(fake_client, item_type="device", item_id="abc123")
        assert fake_client.ws_calls[-1]["payload"]["item_type"] == "device"

    def test_search_related_automation(self, fake_client):
        """search_related works with item_type=automation."""
        fake_client.set_ws("search/related", [])
        singletons.search_related(fake_client, item_type="automation", item_id="id1")
        assert fake_client.ws_calls[-1]["payload"]["item_type"] == "automation"

    def test_search_related_all_valid_types(self, fake_client):
        """search_related accepts all valid item_type values."""
        fake_client.set_ws("search/related", [])
        valid_types = {
            "automation", "config_entry", "area", "device", "entity",
            "floor", "group", "label", "person", "scene", "script"
        }
        for item_type in valid_types:
            singletons.search_related(fake_client, item_type=item_type, item_id="x")

    def test_search_related_invalid_type(self, fake_client):
        """search_related raises ValueError for invalid item_type."""
        with pytest.raises(ValueError, match="item_type must be one of"):
            singletons.search_related(fake_client, item_type="invalid", item_id="x")

    def test_search_related_empty_item_id(self, fake_client):
        """search_related raises ValueError when item_id is empty."""
        with pytest.raises(ValueError, match="item_id must be a non-empty"):
            singletons.search_related(fake_client, item_type="entity", item_id="")

    # ──────────────────────────────────────────────────────────────────────
    # 6. browse_media_player
    # ──────────────────────────────────────────────────────────────────────

    def test_browse_media_player_happy_path(self, fake_client):
        """browse_media_player sends media_player/browse_media WS."""
        response = {"title": "Library", "media": []}
        fake_client.set_ws("media_player/browse_media", response)
        result = singletons.browse_media_player(
            fake_client, entity_id="media_player.living_room"
        )
        assert result == response
        assert fake_client.ws_calls[-1] == {
            "type": "media_player/browse_media",
            "payload": {"entity_id": "media_player.living_room"}
        }

    def test_browse_media_player_with_content_id(self, fake_client):
        """browse_media_player includes media_content_id when supplied."""
        fake_client.set_ws("media_player/browse_media", {})
        singletons.browse_media_player(
            fake_client,
            entity_id="media_player.x",
            media_content_id="album-123"
        )
        assert fake_client.ws_calls[-1]["payload"]["media_content_id"] == "album-123"

    def test_browse_media_player_with_content_type(self, fake_client):
        """browse_media_player includes media_content_type when supplied."""
        fake_client.set_ws("media_player/browse_media", {})
        singletons.browse_media_player(
            fake_client,
            entity_id="media_player.x",
            media_content_type="music"
        )
        assert fake_client.ws_calls[-1]["payload"]["media_content_type"] == "music"

    def test_browse_media_player_with_both_content_params(self, fake_client):
        """browse_media_player includes both content params when supplied."""
        fake_client.set_ws("media_player/browse_media", {})
        singletons.browse_media_player(
            fake_client,
            entity_id="media_player.x",
            media_content_id="id123",
            media_content_type="music"
        )
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["media_content_id"] == "id123"
        assert payload["media_content_type"] == "music"

    def test_browse_media_player_wrong_domain(self, fake_client):
        """browse_media_player raises ValueError for non-media_player.* entity."""
        with pytest.raises(ValueError, match="expected media_player\\.\\*"):
            singletons.browse_media_player(
                fake_client, entity_id="speaker.living_room"
            )

    def test_browse_media_player_return_shape(self, fake_client):
        """browse_media_player returns dict response."""
        fake_client.set_ws("media_player/browse_media", {"items": []})
        result = singletons.browse_media_player(fake_client, entity_id="media_player.x")
        assert isinstance(result, dict)

    # ──────────────────────────────────────────────────────────────────────
    # 7. subscribe_persistent_notifications
    # ──────────────────────────────────────────────────────────────────────

    def test_subscribe_persistent_notifications_happy_path(self):
        """subscribe_persistent_notifications calls ws_subscribe correctly."""
        client = SubscribingFakeClient()
        notification = {"id": "notif1", "message": "test"}
        client.preset_events = [notification]
        received = []

        singletons.subscribe_persistent_notifications(
            client,
            on_notification=received.append,
            max_notifications=1
        )

        assert len(client.subscribe_calls) == 1
        assert client.subscribe_calls[0]["type"] == "persistent_notification/subscribe"
        assert client.subscribe_calls[0]["payload"] == {}
        assert received == [notification]

    def test_subscribe_persistent_notifications_multiple(self):
        """subscribe_persistent_notifications delivers multiple notifications."""
        client = SubscribingFakeClient()
        notifs = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        client.preset_events = notifs
        received = []

        singletons.subscribe_persistent_notifications(
            client,
            on_notification=received.append,
            max_notifications=3
        )

        assert received == notifs

    def test_subscribe_persistent_notifications_with_stop_event(self):
        """subscribe_persistent_notifications respects stop_event."""
        client = SubscribingFakeClient()
        stop = threading.Event()
        stop.set()
        client.preset_events = [{"id": "1"}, {"id": "2"}]
        received = []

        singletons.subscribe_persistent_notifications(
            client,
            on_notification=received.append,
            stop_event=stop
        )

        assert received == []

    def test_subscribe_persistent_notifications_not_callable(self):
        """subscribe_persistent_notifications raises ValueError if on_notification not callable."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="on_notification must be callable"):
            singletons.subscribe_persistent_notifications(
                client,
                on_notification="not-a-function",  # type: ignore[arg-type]
                max_notifications=1
            )

    def test_subscribe_persistent_notifications_no_stop_or_max(self):
        """subscribe_persistent_notifications raises if neither stop_event nor max_notifications."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="must supply stop_event or max_events"):
            singletons.subscribe_persistent_notifications(
                client,
                on_notification=lambda x: None
            )

    # ──────────────────────────────────────────────────────────────────────
    # 8. subscribe_todo_items
    # ──────────────────────────────────────────────────────────────────────

    def test_subscribe_todo_items_happy_path(self):
        """subscribe_todo_items calls ws_subscribe with correct type and payload."""
        client = SubscribingFakeClient()
        update = {"uid": "item1", "summary": "Buy milk"}
        client.preset_events = [update]
        received = []

        singletons.subscribe_todo_items(
            client,
            entity_id="todo.shopping",
            on_update=received.append,
            max_updates=1
        )

        assert len(client.subscribe_calls) == 1
        assert client.subscribe_calls[0]["type"] == "todo/item/subscribe"
        assert client.subscribe_calls[0]["payload"] == {"entity_id": "todo.shopping"}
        assert received == [update]

    def test_subscribe_todo_items_multiple(self):
        """subscribe_todo_items delivers multiple updates."""
        client = SubscribingFakeClient()
        updates = [
            {"uid": "1", "summary": "Task 1"},
            {"uid": "2", "summary": "Task 2"}
        ]
        client.preset_events = updates
        received = []

        singletons.subscribe_todo_items(
            client,
            entity_id="todo.work",
            on_update=received.append,
            max_updates=2
        )

        assert received == updates

    def test_subscribe_todo_items_wrong_entity_domain(self):
        """subscribe_todo_items raises ValueError for non-todo.* entity."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="expected todo\\.\\*"):
            singletons.subscribe_todo_items(
                client,
                entity_id="input_text.notes",
                on_update=lambda x: None,
                max_updates=1
            )

    def test_subscribe_todo_items_not_callable(self):
        """subscribe_todo_items raises ValueError if on_update not callable."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="on_update must be callable"):
            singletons.subscribe_todo_items(
                client,
                entity_id="todo.x",
                on_update="not-a-function",  # type: ignore[arg-type]
                max_updates=1
            )

    def test_subscribe_todo_items_no_stop_or_max(self):
        """subscribe_todo_items raises if neither stop_event nor max_updates."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="must supply stop_event or max_events"):
            singletons.subscribe_todo_items(
                client,
                entity_id="todo.x",
                on_update=lambda x: None
            )

    def test_subscribe_todo_items_with_stop_event(self):
        """subscribe_todo_items respects stop_event."""
        client = SubscribingFakeClient()
        stop = threading.Event()
        stop.set()
        client.preset_events = [{"uid": "1"}]
        received = []

        singletons.subscribe_todo_items(
            client,
            entity_id="todo.x",
            on_update=received.append,
            stop_event=stop
        )

        assert received == []

    # ──────────────────────────────────────────────────────────────────────
    # 9. subscribe_hardware_status
    # ──────────────────────────────────────────────────────────────────────

    def test_subscribe_hardware_status_happy_path(self):
        """subscribe_hardware_status calls ws_subscribe correctly."""
        client = SubscribingFakeClient()
        status = {"cpu_percent": 45, "memory_used_percent": 60.0}
        client.preset_events = [status]
        received = []

        singletons.subscribe_hardware_status(
            client,
            on_status=received.append,
            max_updates=1
        )

        assert len(client.subscribe_calls) == 1
        assert client.subscribe_calls[0]["type"] == "hardware/subscribe_system_status"
        assert client.subscribe_calls[0]["payload"] == {}
        assert received == [status]

    def test_subscribe_hardware_status_multiple(self):
        """subscribe_hardware_status delivers multiple status updates."""
        client = SubscribingFakeClient()
        statuses = [
            {"cpu_percent": 10},
            {"cpu_percent": 20},
            {"cpu_percent": 30}
        ]
        client.preset_events = statuses
        received = []

        singletons.subscribe_hardware_status(
            client,
            on_status=received.append,
            max_updates=3
        )

        assert received == statuses

    def test_subscribe_hardware_status_with_stop_event(self):
        """subscribe_hardware_status respects stop_event."""
        client = SubscribingFakeClient()
        stop = threading.Event()
        stop.set()
        client.preset_events = [{"cpu_percent": 50}]
        received = []

        singletons.subscribe_hardware_status(
            client,
            on_status=received.append,
            stop_event=stop
        )

        assert received == []

    def test_subscribe_hardware_status_not_callable(self):
        """subscribe_hardware_status raises ValueError if on_status not callable."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="on_status must be callable"):
            singletons.subscribe_hardware_status(
                client,
                on_status="not-a-function",  # type: ignore[arg-type]
                max_updates=1
            )

    def test_subscribe_hardware_status_no_stop_or_max(self):
        """subscribe_hardware_status raises if neither stop_event nor max_updates."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="must supply stop_event or max_events"):
            singletons.subscribe_hardware_status(
                client,
                on_status=lambda x: None
            )
