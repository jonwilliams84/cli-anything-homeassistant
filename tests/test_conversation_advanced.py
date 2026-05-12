"""Unit tests for cli_anything.homeassistant.core.conversation_advanced.

All tests run against FakeClient (auto-injected via the ``fake_client``
fixture in conftest.py) — no live Home Assistant required.

WS message types covered:
  conversation/process                        — process
  conversation/agent/list                     — list_agents
  conversation/sentences/list                 — list_sentences
  conversation/agent/homeassistant/debug      — debug_agent
  assist_pipeline/pipeline_debug/list         — list_pipelines
  assist_pipeline/pipeline_debug/get          — get_pipeline
  assist_pipeline/language/list               — list_pipeline_languages
  assist_pipeline/device/list                 — list_satellite_devices
  assist_pipeline/device/capture              — capture_satellite
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import conversation_advanced


class TestConversationAdvanced:
    # ──────────────────────────────────────────────────── process ────────────

    def test_process_happy_path_payload(self, fake_client):
        """process sends conversation/process with required text field."""
        fake_client.set_ws("conversation/process", {"response": {}})
        conversation_advanced.process(fake_client, text="Turn on the lights")
        call = fake_client.ws_calls[-1]
        assert call["type"] == "conversation/process"
        assert call["payload"]["text"] == "Turn on the lights"

    def test_process_optional_fields_included(self, fake_client):
        """process includes all optional fields when provided."""
        fake_client.set_ws("conversation/process", {})
        conversation_advanced.process(
            fake_client,
            text="Play jazz",
            language="en",
            agent_id="conversation.home_assistant",
            conversation_id="conv-42",
        )
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["language"] == "en"
        assert payload["agent_id"] == "conversation.home_assistant"
        assert payload["conversation_id"] == "conv-42"

    def test_process_optional_fields_omitted_when_none(self, fake_client):
        """process omits optional keys when they are None."""
        fake_client.set_ws("conversation/process", {})
        conversation_advanced.process(fake_client, text="Hello")
        payload = fake_client.ws_calls[-1]["payload"]
        assert "language" not in payload
        assert "agent_id" not in payload
        assert "conversation_id" not in payload

    def test_process_returns_response(self, fake_client):
        """process returns the dict from the WS response."""
        response = {"response": {"speech": {"plain": {"speech": "Lights on."}}}}
        fake_client.set_ws("conversation/process", response)
        result = conversation_advanced.process(fake_client, text="Turn on the lights")
        assert result == response

    def test_process_empty_text_raises(self, fake_client):
        """process raises ValueError when text is empty."""
        with pytest.raises(ValueError, match="text must be a non-empty string"):
            conversation_advanced.process(fake_client, text="")

    # ─────────────────────────────────────────────── list_agents ────────────

    def test_list_agents_happy_path_payload(self, fake_client):
        """list_agents sends conversation/agent/list WS message."""
        fake_client.set_ws("conversation/agent/list", {"agents": []})
        conversation_advanced.list_agents(fake_client)
        call = fake_client.ws_calls[-1]
        assert call["type"] == "conversation/agent/list"

    def test_list_agents_with_filters(self, fake_client):
        """list_agents passes country and language to the WS payload."""
        fake_client.set_ws("conversation/agent/list", {"agents": []})
        conversation_advanced.list_agents(fake_client, country="US", language="en")
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["country"] == "US"
        assert payload["language"] == "en"

    def test_list_agents_no_filters_sends_empty_payload(self, fake_client):
        """list_agents with no args sends an empty payload."""
        fake_client.set_ws("conversation/agent/list", {"agents": []})
        conversation_advanced.list_agents(fake_client)
        assert fake_client.ws_calls[-1]["payload"] == {}

    def test_list_agents_returns_response(self, fake_client):
        """list_agents returns the full WS response dict."""
        agents_response = {
            "agents": [
                {"id": "conversation.home_assistant", "name": "Home Assistant",
                 "supported_languages": ["en", "nl"]},
            ]
        }
        fake_client.set_ws("conversation/agent/list", agents_response)
        result = conversation_advanced.list_agents(fake_client)
        assert result == agents_response

    # ──────────────────────────────────────────── list_sentences ─────────────

    def test_list_sentences_happy_path_payload(self, fake_client):
        """list_sentences sends conversation/sentences/list with language."""
        fake_client.set_ws("conversation/sentences/list", {"trigger_sentences": []})
        conversation_advanced.list_sentences(fake_client, language="en")
        call = fake_client.ws_calls[-1]
        assert call["type"] == "conversation/sentences/list"
        assert call["payload"] == {"language": "en"}

    def test_list_sentences_returns_response(self, fake_client):
        """list_sentences returns the WS response dict."""
        data = {"trigger_sentences": ["turn on [the] {area} lights"]}
        fake_client.set_ws("conversation/sentences/list", data)
        result = conversation_advanced.list_sentences(fake_client, language="en")
        assert result == data

    def test_list_sentences_empty_language_raises(self, fake_client):
        """list_sentences raises ValueError when language is empty."""
        with pytest.raises(ValueError, match="language must be a non-empty string"):
            conversation_advanced.list_sentences(fake_client, language="")

    # ──────────────────────────────────────────────── debug_agent ────────────

    def test_debug_agent_happy_path_payload(self, fake_client):
        """debug_agent sends the correct WS type and payload."""
        fake_client.set_ws("conversation/agent/homeassistant/debug", {"results": []})
        conversation_advanced.debug_agent(
            fake_client, sentence="Turn on the kitchen lights", language="en"
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "conversation/agent/homeassistant/debug"
        assert call["payload"] == {
            "sentence": "Turn on the kitchen lights",
            "language": "en",
        }

    def test_debug_agent_returns_response(self, fake_client):
        """debug_agent returns the WS response dict."""
        data = {"results": [{"match": True, "source": "builtin"}]}
        fake_client.set_ws("conversation/agent/homeassistant/debug", data)
        result = conversation_advanced.debug_agent(
            fake_client, sentence="Turn on the lights", language="en"
        )
        assert result == data

    def test_debug_agent_empty_sentence_raises(self, fake_client):
        """debug_agent raises ValueError when sentence is empty."""
        with pytest.raises(ValueError, match="sentence must be a non-empty string"):
            conversation_advanced.debug_agent(
                fake_client, sentence="", language="en"
            )

    def test_debug_agent_empty_language_raises(self, fake_client):
        """debug_agent raises ValueError when language is empty."""
        with pytest.raises(ValueError, match="language must be a non-empty string"):
            conversation_advanced.debug_agent(
                fake_client, sentence="Turn on the lights", language=""
            )

    # ──────────────────────────────────────────── list_pipelines ─────────────

    def test_list_pipelines_happy_path_payload(self, fake_client):
        """list_pipelines sends assist_pipeline/pipeline_debug/list WS message."""
        fake_client.set_ws("assist_pipeline/pipeline_debug/list", [])
        conversation_advanced.list_pipelines(fake_client)
        call = fake_client.ws_calls[-1]
        assert call["type"] == "assist_pipeline/pipeline_debug/list"

    def test_list_pipelines_returns_list(self, fake_client):
        """list_pipelines returns the list from the WS response."""
        pipelines = [
            {"pipeline_id": "p1", "pipeline_runs": []},
            {"pipeline_id": "p2", "pipeline_runs": []},
        ]
        fake_client.set_ws("assist_pipeline/pipeline_debug/list", pipelines)
        result = conversation_advanced.list_pipelines(fake_client)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_list_pipelines_non_list_response_normalised(self, fake_client):
        """list_pipelines returns [] when HA returns a non-list."""
        fake_client.set_ws("assist_pipeline/pipeline_debug/list", {"unexpected": True})
        result = conversation_advanced.list_pipelines(fake_client)
        assert result == []

    # ───────────────────────────────────────────────── get_pipeline ──────────

    def test_get_pipeline_happy_path_payload(self, fake_client):
        """get_pipeline sends assist_pipeline/pipeline_debug/get with pipeline_id."""
        fake_client.set_ws("assist_pipeline/pipeline_debug/get", {})
        conversation_advanced.get_pipeline(fake_client, pipeline_id="pipe-abc")
        call = fake_client.ws_calls[-1]
        assert call["type"] == "assist_pipeline/pipeline_debug/get"
        assert call["payload"] == {"pipeline_id": "pipe-abc"}

    def test_get_pipeline_returns_dict(self, fake_client):
        """get_pipeline returns the WS response dict."""
        data = {"pipeline_runs": [{"pipeline_run_id": "r1", "timestamp": "2026-01-01"}]}
        fake_client.set_ws("assist_pipeline/pipeline_debug/get", data)
        result = conversation_advanced.get_pipeline(fake_client, pipeline_id="p1")
        assert result == data

    def test_get_pipeline_empty_id_raises(self, fake_client):
        """get_pipeline raises ValueError when pipeline_id is empty."""
        with pytest.raises(ValueError, match="pipeline_id must be a non-empty string"):
            conversation_advanced.get_pipeline(fake_client, pipeline_id="")

    # ───────────────────────────────────── list_pipeline_languages ───────────

    def test_list_pipeline_languages_happy_path_payload(self, fake_client):
        """list_pipeline_languages sends assist_pipeline/language/list."""
        fake_client.set_ws("assist_pipeline/language/list", {"languages": []})
        conversation_advanced.list_pipeline_languages(fake_client)
        call = fake_client.ws_calls[-1]
        assert call["type"] == "assist_pipeline/language/list"

    def test_list_pipeline_languages_returns_response(self, fake_client):
        """list_pipeline_languages returns the WS response dict."""
        data = {"languages": ["en", "nl", "de"]}
        fake_client.set_ws("assist_pipeline/language/list", data)
        result = conversation_advanced.list_pipeline_languages(fake_client)
        assert result == data

    # ──────────────────────────────────── list_satellite_devices ────────────

    def test_list_satellite_devices_happy_path_payload(self, fake_client):
        """list_satellite_devices sends assist_pipeline/device/list."""
        fake_client.set_ws("assist_pipeline/device/list", [])
        conversation_advanced.list_satellite_devices(fake_client)
        call = fake_client.ws_calls[-1]
        assert call["type"] == "assist_pipeline/device/list"

    def test_list_satellite_devices_returns_list(self, fake_client):
        """list_satellite_devices returns the list from the WS response."""
        devices = [
            {"device_id": "d1", "pipeline_entity": "select.kitchen_pipeline"},
            {"device_id": "d2", "pipeline_entity": "select.bedroom_pipeline"},
        ]
        fake_client.set_ws("assist_pipeline/device/list", devices)
        result = conversation_advanced.list_satellite_devices(fake_client)
        assert isinstance(result, list)
        assert result[0]["device_id"] == "d1"

    def test_list_satellite_devices_non_list_normalised(self, fake_client):
        """list_satellite_devices returns [] when HA returns a non-list."""
        fake_client.set_ws("assist_pipeline/device/list", {"unexpected": "dict"})
        result = conversation_advanced.list_satellite_devices(fake_client)
        assert result == []

    # ──────────────────────────────────────────── capture_satellite ──────────

    def test_capture_satellite_happy_path_payload(self, fake_client):
        """capture_satellite sends assist_pipeline/device/capture with all fields."""
        fake_client.set_ws("assist_pipeline/device/capture", {})
        conversation_advanced.capture_satellite(
            fake_client, device_id="device-xyz", timeout=10.0
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "assist_pipeline/device/capture"
        assert call["payload"] == {"device_id": "device-xyz", "timeout": 10.0}

    def test_capture_satellite_default_timeout(self, fake_client):
        """capture_satellite uses 30.0 s as the default timeout."""
        fake_client.set_ws("assist_pipeline/device/capture", {})
        conversation_advanced.capture_satellite(fake_client, device_id="dev-1")
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["timeout"] == 30.0

    def test_capture_satellite_returns_response(self, fake_client):
        """capture_satellite returns the WS response."""
        fake_client.set_ws("assist_pipeline/device/capture", {"ok": True})
        result = conversation_advanced.capture_satellite(
            fake_client, device_id="dev-1", timeout=5.0
        )
        assert result == {"ok": True}

    def test_capture_satellite_empty_device_id_raises(self, fake_client):
        """capture_satellite raises ValueError when device_id is empty."""
        with pytest.raises(ValueError, match="device_id must be a non-empty string"):
            conversation_advanced.capture_satellite(fake_client, device_id="")

    def test_capture_satellite_zero_timeout_raises(self, fake_client):
        """capture_satellite raises ValueError when timeout is 0."""
        with pytest.raises(ValueError, match="timeout must be greater than 0"):
            conversation_advanced.capture_satellite(
                fake_client, device_id="dev-1", timeout=0.0
            )

    def test_capture_satellite_negative_timeout_raises(self, fake_client):
        """capture_satellite raises ValueError when timeout is negative."""
        with pytest.raises(ValueError, match="timeout must be greater than 0"):
            conversation_advanced.capture_satellite(
                fake_client, device_id="dev-1", timeout=-5.0
            )
