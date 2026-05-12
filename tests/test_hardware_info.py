"""Unit tests for cli_anything.homeassistant.core.hardware_info."""

from __future__ import annotations

import threading
from typing import Any

import pytest

from tests.conftest import FakeClient
from cli_anything.homeassistant.core import hardware_info


# ────────────────────────────────────────────────────────────────────────────
# SubscribingFakeClient — extends FakeClient with ws_subscribe support
# ────────────────────────────────────────────────────────────────────────────

class SubscribingFakeClient(FakeClient):
    """FakeClient subclass that records ws_subscribe calls and replays
    a configurable queue of pre-set events synchronously.

    Usage::

        client = SubscribingFakeClient()
        client.preset_events = [{"cpu_percent": 10}, {"cpu_percent": 20}]
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
        # Merge any keyword overrides (hardware_info uses keyword-only args).
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
# Canned responses
# ────────────────────────────────────────────────────────────────────────────

_BOARD_RECORD = {
    "board": {
        "manufacturer": "Raspberry Pi Foundation",
        "model": "Raspberry Pi 4 Model B Rev 1.4",
    },
    "dongle": None,
    "name": "Raspberry Pi",
}

_CPU_RECORD = {
    "cpu_info": {
        "arch": "aarch64",
        "model": "Cortex-A72",
    },
    "name": "CPU",
}

_CANNED_INFO = {
    "hardware": [_BOARD_RECORD, _CPU_RECORD],
}

_STATUS_EVENT = {
    "cpu_percent": 42,
    "memory_used_percent": 55.0,
    "memory_used_mb": 1800.0,
    "memory_free_mb": 1400.0,
    "timestamp": "2026-05-12T00:00:00+00:00",
}


# ────────────────────────────────────────────────────────────────────────────
# Tests
# ────────────────────────────────────────────────────────────────────────────

class TestHardwareInfo:
    # ── info ──────────────────────────────────────────────────────────────

    def test_info_happy_path(self, fake_client):
        """info() sends hardware/info WS command and returns the full dict."""
        fake_client.set_ws("hardware/info", _CANNED_INFO)
        result = hardware_info.info(fake_client)
        assert result == _CANNED_INFO
        assert fake_client.ws_calls[-1]["type"] == "hardware/info"

    def test_info_ws_call_recorded(self, fake_client):
        """info() records a ws_call entry with the right type."""
        fake_client.set_ws("hardware/info", _CANNED_INFO)
        hardware_info.info(fake_client)
        assert any(c["type"] == "hardware/info" for c in fake_client.ws_calls)

    def test_info_empty_hardware_list(self, fake_client):
        """info() returns whatever HA sends, including an empty hardware list."""
        fake_client.set_ws("hardware/info", {"hardware": []})
        result = hardware_info.info(fake_client)
        assert result == {"hardware": []}

    # ── board_info ────────────────────────────────────────────────────────

    def test_board_info_happy_path(self, fake_client):
        """board_info() returns only records with a 'board' key."""
        fake_client.set_ws("hardware/info", _CANNED_INFO)
        result = hardware_info.board_info(fake_client)
        assert isinstance(result, list)
        assert result == [_BOARD_RECORD]
        assert all("board" in r for r in result)

    def test_board_info_empty_when_no_board_records(self, fake_client):
        """board_info() returns [] when no hardware record has 'board'."""
        fake_client.set_ws("hardware/info", {"hardware": [_CPU_RECORD]})
        result = hardware_info.board_info(fake_client)
        assert result == []

    def test_board_info_sends_hardware_info_ws_command(self, fake_client):
        """board_info() delegates to info() which sends hardware/info."""
        fake_client.set_ws("hardware/info", _CANNED_INFO)
        hardware_info.board_info(fake_client)
        assert fake_client.ws_calls[-1]["type"] == "hardware/info"

    # ── cpu_info ──────────────────────────────────────────────────────────

    def test_cpu_info_happy_path(self, fake_client):
        """cpu_info() returns only records with a 'cpu_info' key."""
        fake_client.set_ws("hardware/info", _CANNED_INFO)
        result = hardware_info.cpu_info(fake_client)
        assert isinstance(result, list)
        assert result == [_CPU_RECORD]
        assert all("cpu_info" in r for r in result)

    def test_cpu_info_empty_when_no_cpu_records(self, fake_client):
        """cpu_info() returns [] when no hardware record has 'cpu_info'."""
        fake_client.set_ws("hardware/info", {"hardware": [_BOARD_RECORD]})
        result = hardware_info.cpu_info(fake_client)
        assert result == []

    def test_cpu_info_sends_hardware_info_ws_command(self, fake_client):
        """cpu_info() delegates to info() which sends hardware/info."""
        fake_client.set_ws("hardware/info", _CANNED_INFO)
        hardware_info.cpu_info(fake_client)
        assert fake_client.ws_calls[-1]["type"] == "hardware/info"

    # ── subscribe_system_status ───────────────────────────────────────────

    def test_subscribe_calls_ws_subscribe_with_correct_type(self):
        """subscribe_system_status calls ws_subscribe with the right type."""
        client = SubscribingFakeClient()
        client.preset_events = [_STATUS_EVENT]
        received = []
        hardware_info.subscribe_system_status(
            client,
            on_status=received.append,
            max_events=1,
        )
        assert len(client.subscribe_calls) == 1
        assert client.subscribe_calls[0]["type"] == "hardware/subscribe_system_status"

    def test_subscribe_delivers_events_to_callback(self):
        """subscribe_system_status forwards each preset event to on_status."""
        client = SubscribingFakeClient()
        events = [_STATUS_EVENT, {**_STATUS_EVENT, "cpu_percent": 99}]
        client.preset_events = events
        received = []
        hardware_info.subscribe_system_status(
            client,
            on_status=received.append,
            max_events=2,
        )
        assert received == events

    def test_subscribe_respects_stop_event(self):
        """subscribe_system_status stops delivering after stop_event is set."""
        client = SubscribingFakeClient()
        # Provide many events but set stop_event before they can all fire.
        stop = threading.Event()
        stop.set()  # already signalled — no events should be delivered
        client.preset_events = [_STATUS_EVENT, _STATUS_EVENT, _STATUS_EVENT]
        received = []
        hardware_info.subscribe_system_status(
            client,
            on_status=received.append,
            stop_event=stop,
        )
        assert received == []

    def test_subscribe_payload_is_empty_dict(self):
        """subscribe_system_status sends {} as the WS payload."""
        client = SubscribingFakeClient()
        client.preset_events = []
        stop = threading.Event()
        stop.set()
        hardware_info.subscribe_system_status(
            client,
            on_status=lambda e: None,
            stop_event=stop,
        )
        assert client.subscribe_calls[0]["payload"] == {}

    # ── ValueError — missing stop_event and max_events ────────────────────

    def test_subscribe_raises_if_neither_stop_event_nor_max_events(self):
        """subscribe_system_status raises ValueError when both are None."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="stop_event or max_events"):
            hardware_info.subscribe_system_status(
                client,
                on_status=lambda e: None,
            )

    def test_subscribe_raises_if_max_events_is_zero(self):
        """subscribe_system_status raises ValueError when max_events == 0."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="max_events"):
            hardware_info.subscribe_system_status(
                client,
                on_status=lambda e: None,
                max_events=0,
            )

    # ── ValueError — bad on_status ─────────────────────────────────────────

    def test_subscribe_raises_if_on_status_not_callable(self):
        """subscribe_system_status raises ValueError when on_status is not callable."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="on_status must be callable"):
            hardware_info.subscribe_system_status(
                client,
                on_status="not-a-function",  # type: ignore[arg-type]
                max_events=1,
            )
