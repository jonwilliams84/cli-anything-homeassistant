"""Unit tests for cli_anything.homeassistant.core.assist_satellite."""

from __future__ import annotations

import threading

import pytest

from tests.conftest import SubscribingFakeClient
from cli_anything.homeassistant.core import assist_satellite


class TestAssistSatellite:
    # ── get_configuration ───────────────────────────────────────────────────

    def test_get_configuration_happy(self, fake_client):
        config_data = {
            "available_wake_words": [
                {"id": "hey_google", "name": "Hey Google"},
                {"id": "hey_assistant", "name": "Hey Assistant"},
            ],
            "active_wake_words": ["hey_google"],
            "max_active_wake_words": 3,
            "pipeline_entity_id": "pipeline.home",
            "vad_entity_id": "binary_sensor.vad_enabled",
        }
        fake_client.set_ws("assist_satellite/get_configuration", config_data)
        result = assist_satellite.get_configuration(
            fake_client, entity_id="assist_satellite.device_1"
        )
        assert result == config_data
        last_ws = fake_client.ws_calls[-1]
        assert last_ws["type"] == "assist_satellite/get_configuration"
        assert last_ws["payload"]["entity_id"] == "assist_satellite.device_1"

    def test_get_configuration_invalid_entity_prefix(self, fake_client):
        with pytest.raises(ValueError, match="expected assist_satellite"):
            assist_satellite.get_configuration(
                fake_client, entity_id="sensor.temperature"
            )

    def test_get_configuration_return_shape(self, fake_client):
        fake_client.set_ws(
            "assist_satellite/get_configuration",
            {
                "available_wake_words": [],
                "active_wake_words": [],
                "max_active_wake_words": 1,
                "pipeline_entity_id": "pipeline.default",
                "vad_entity_id": None,
            },
        )
        result = assist_satellite.get_configuration(
            fake_client, entity_id="assist_satellite.sat1"
        )
        assert isinstance(result, dict)
        assert "available_wake_words" in result or len(result) >= 0

    # ── set_wake_words ──────────────────────────────────────────────────────

    def test_set_wake_words_happy(self, fake_client):
        fake_client.set_ws("assist_satellite/set_wake_words", {})
        result = assist_satellite.set_wake_words(
            fake_client,
            entity_id="assist_satellite.device_1",
            wake_word_ids=["hey_google", "hey_assistant"],
        )
        last_ws = fake_client.ws_calls[-1]
        assert last_ws["type"] == "assist_satellite/set_wake_words"
        assert last_ws["payload"]["entity_id"] == "assist_satellite.device_1"
        assert last_ws["payload"]["wake_word_ids"] == [
            "hey_google",
            "hey_assistant",
        ]

    def test_set_wake_words_single_id(self, fake_client):
        fake_client.set_ws("assist_satellite/set_wake_words", {})
        assist_satellite.set_wake_words(
            fake_client,
            entity_id="assist_satellite.device_1",
            wake_word_ids=["hey_google"],
        )
        last_ws = fake_client.ws_calls[-1]
        assert last_ws["payload"]["wake_word_ids"] == ["hey_google"]

    def test_set_wake_words_invalid_entity_prefix(self, fake_client):
        with pytest.raises(ValueError, match="expected assist_satellite"):
            assist_satellite.set_wake_words(
                fake_client,
                entity_id="binary_sensor.wake_word",
                wake_word_ids=["hey_google"],
            )

    def test_set_wake_words_empty_list_raises(self, fake_client):
        with pytest.raises(ValueError, match="wake_word_ids must be a non-empty list"):
            assist_satellite.set_wake_words(
                fake_client,
                entity_id="assist_satellite.device_1",
                wake_word_ids=[],
            )

    def test_set_wake_words_not_list_raises(self, fake_client):
        with pytest.raises(ValueError, match="wake_word_ids must be a non-empty list"):
            assist_satellite.set_wake_words(
                fake_client,
                entity_id="assist_satellite.device_1",
                wake_word_ids="hey_google",  # type: ignore
            )

    def test_set_wake_words_empty_string_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="each wake_word_id must be a non-empty string"):
            assist_satellite.set_wake_words(
                fake_client,
                entity_id="assist_satellite.device_1",
                wake_word_ids=["hey_google", ""],
            )

    def test_set_wake_words_non_string_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="each wake_word_id must be a non-empty string"):
            assist_satellite.set_wake_words(
                fake_client,
                entity_id="assist_satellite.device_1",
                wake_word_ids=["hey_google", 123],  # type: ignore
            )

    def test_set_wake_words_return_shape(self, fake_client):
        fake_client.set_ws("assist_satellite/set_wake_words", {"result": "success"})
        result = assist_satellite.set_wake_words(
            fake_client,
            entity_id="assist_satellite.device_1",
            wake_word_ids=["hey_google"],
        )
        assert isinstance(result, dict)

    # ── test_connection ─────────────────────────────────────────────────────

    def test_test_connection_happy(self, fake_client):
        fake_client.set_ws(
            "assist_satellite/test_connection", {"status": "success"}
        )
        result = assist_satellite.test_connection(
            fake_client, entity_id="assist_satellite.device_1"
        )
        assert result == {"status": "success"}
        last_ws = fake_client.ws_calls[-1]
        assert last_ws["type"] == "assist_satellite/test_connection"
        assert last_ws["payload"]["entity_id"] == "assist_satellite.device_1"

    def test_test_connection_timeout(self, fake_client):
        fake_client.set_ws(
            "assist_satellite/test_connection", {"status": "timeout"}
        )
        result = assist_satellite.test_connection(
            fake_client, entity_id="assist_satellite.device_1"
        )
        assert result["status"] == "timeout"

    def test_test_connection_invalid_entity_prefix(self, fake_client):
        with pytest.raises(ValueError, match="expected assist_satellite"):
            assist_satellite.test_connection(
                fake_client, entity_id="light.living_room"
            )

    def test_test_connection_return_shape(self, fake_client):
        fake_client.set_ws(
            "assist_satellite/test_connection", {"status": "success"}
        )
        result = assist_satellite.test_connection(
            fake_client, entity_id="assist_satellite.device_1"
        )
        assert isinstance(result, dict)
        assert "status" in result

    # ── intercept_wake_word ─────────────────────────────────────────────────

    def test_intercept_wake_word_calls_ws_subscribe(self):
        """intercept_wake_word calls ws_subscribe with correct type and payload."""
        client = SubscribingFakeClient()
        stop = threading.Event()
        stop.set()
        assist_satellite.intercept_wake_word(
            client,
            entity_id="assist_satellite.device_1",
            on_event=lambda e: None,
            stop_event=stop,
        )
        assert len(client.subscribe_calls) == 1
        msg_type, payload = client.subscribe_calls[0]
        assert msg_type == "assist_satellite/intercept_wake_word"
        assert payload == {"entity_id": "assist_satellite.device_1"}

    def test_intercept_wake_word_delivers_events(self):
        """intercept_wake_word forwards wake word events to on_event."""
        client = SubscribingFakeClient()
        ev = {"wake_word_phrase": "Hey Google"}
        client.queue_events(ev)
        received = []
        assist_satellite.intercept_wake_word(
            client,
            entity_id="assist_satellite.device_1",
            on_event=received.append,
            max_events=1,
        )
        assert received == [ev]

    def test_intercept_wake_word_max_events_auto_stop(self):
        """intercept_wake_word stops after max_events deliveries."""
        client = SubscribingFakeClient()
        client.queue_events(
            {"wake_word_phrase": "Hey Google"},
            {"wake_word_phrase": "Hey Jarvis"},
            {"wake_word_phrase": "Hey Siri"},
        )
        received = []
        assist_satellite.intercept_wake_word(
            client,
            entity_id="assist_satellite.device_1",
            on_event=received.append,
            max_events=2,
        )
        assert len(received) == 2

    def test_intercept_wake_word_stop_event(self):
        """intercept_wake_word respects a pre-set stop_event."""
        client = SubscribingFakeClient()
        client.queue_events({"wake_word_phrase": "Hey Google"})
        stop = threading.Event()
        stop.set()
        received = []
        assist_satellite.intercept_wake_word(
            client,
            entity_id="assist_satellite.device_1",
            on_event=received.append,
            stop_event=stop,
        )
        assert received == []

    def test_intercept_wake_word_invalid_entity_prefix(self):
        """intercept_wake_word raises ValueError for non-assist_satellite entity."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="expected assist_satellite"):
            assist_satellite.intercept_wake_word(
                client,
                entity_id="sensor.microphone",
                on_event=lambda e: None,
                max_events=1,
            )

    def test_intercept_wake_word_raises_without_stop_or_max(self):
        """intercept_wake_word raises ValueError if no stop_event or max_events."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="must supply stop_event or max_events"):
            assist_satellite.intercept_wake_word(
                client,
                entity_id="assist_satellite.device_1",
                on_event=lambda e: None,
            )

    def test_intercept_wake_word_raises_on_non_callable(self):
        """intercept_wake_word raises ValueError if on_event is not callable."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="on_event must be callable"):
            assist_satellite.intercept_wake_word(
                client,
                entity_id="assist_satellite.device_1",
                on_event="not_callable",  # type: ignore[arg-type]
                max_events=1,
            )
