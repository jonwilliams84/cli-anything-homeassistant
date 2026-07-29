"""Unit tests for cli_anything.homeassistant.core.tts — no real HA required."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import tts


class TestListEngines:
    def test_returns_tts_entities(self, fake_client):
        fake_client.set("GET", "states", [
            {"entity_id": "tts.google", "attributes": {
                "friendly_name": "Google", "default_language": "en",
                "supported_languages": ["en", "fr"]}},
            {"entity_id": "light.kitchen", "attributes": {}},
            {"entity_id": "tts.piper", "attributes": {
                "friendly_name": "Piper", "default_language": "de"}},
        ])
        rows = tts.list_engines(fake_client)
        assert len(rows) == 2
        assert {r["entity_id"] for r in rows} == {"tts.google", "tts.piper"}
        assert rows[0]["friendly_name"] == "Google"
        assert rows[0]["default_language"] == "en"
        assert rows[0]["supported_languages"] == ["en", "fr"]

    def test_no_tts_entities_returns_empty(self, fake_client):
        fake_client.set("GET", "states", [
            {"entity_id": "light.kitchen", "attributes": {}},
        ])
        assert tts.list_engines(fake_client) == []

    def test_non_list_states_returns_empty(self, fake_client):
        fake_client.set("GET", "states", None)
        assert tts.list_engines(fake_client) == []

    def test_entity_with_no_attributes(self, fake_client):
        fake_client.set("GET", "states", [
            {"entity_id": "tts.google"},
        ])
        rows = tts.list_engines(fake_client)
        assert len(rows) == 1
        assert rows[0]["friendly_name"] is None
        assert rows[0]["default_language"] is None
        assert rows[0]["supported_languages"] is None


class TestSpeak:
    def test_minimal_speak(self, fake_client):
        tts.speak(
            fake_client,
            tts_entity="tts.google",
            media_player_entity="media_player.kitchen",
            message="Hello world",
        )
        call = fake_client.service_calls[-1]
        assert call["domain"] == "tts"
        assert call["service"] == "speak"
        assert call["service_data"]["media_player_entity_id"] == "media_player.kitchen"
        assert call["service_data"]["message"] == "Hello world"
        assert call["service_data"]["cache"] is True
        # target entity_id is folded into service_data
        assert call["service_data"]["entity_id"] == "tts.google"

    def test_speak_with_language_and_options(self, fake_client):
        tts.speak(
            fake_client,
            tts_entity="tts.google",
            media_player_entity="media_player.kitchen",
            message="Hello",
            language="fr",
            options={"gender": "female"},
            cache=False,
        )
        call = fake_client.service_calls[-1]
        assert call["service_data"]["language"] == "fr"
        assert call["service_data"]["options"] == {"gender": "female"}
        assert call["service_data"]["cache"] is False

    def test_non_tts_entity_raises(self, fake_client):
        with pytest.raises(ValueError, match="tts"):
            tts.speak(
                fake_client,
                tts_entity="light.kitchen",
                media_player_entity="media_player.kitchen",
                message="Hello",
            )

    def test_non_media_player_entity_raises(self, fake_client):
        with pytest.raises(ValueError, match="media_player"):
            tts.speak(
                fake_client,
                tts_entity="tts.google",
                media_player_entity="light.kitchen",
                message="Hello",
            )

    def test_empty_message_raises(self, fake_client):
        with pytest.raises(ValueError, match="message is required"):
            tts.speak(
                fake_client,
                tts_entity="tts.google",
                media_player_entity="media_player.kitchen",
                message="",
            )


class TestClearCache:
    def test_clear_all_without_entity(self, fake_client):
        tts.clear_cache(fake_client)
        call = fake_client.service_calls[-1]
        assert call["domain"] == "tts"
        assert call["service"] == "clear_cache"
        # No target when no entity specified — no entity_id in payload
        assert "entity_id" not in call["service_data"]

    def test_clear_for_specific_entity(self, fake_client):
        tts.clear_cache(fake_client, tts_entity="tts.google")
        call = fake_client.service_calls[-1]
        assert call["domain"] == "tts"
        assert call["service"] == "clear_cache"
        assert call["service_data"]["entity_id"] == "tts.google"

    def test_non_tts_entity_raises(self, fake_client):
        with pytest.raises(ValueError, match="tts"):
            tts.clear_cache(fake_client, tts_entity="light.kitchen")
