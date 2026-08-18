"""Unit tests for `voice` — TTS voices, TTS/STT engine lists, wake words, prepare.

FakeClient only. Shapes taken from `components/tts/__init__.py`,
`components/stt/__init__.py`, `components/wake_word/__init__.py` and
`components/conversation/http.py`.

WS message types covered:
  tts/engine/get        — voice.engine
  tts/engine/voices     — voice.voices
  tts/engine/list       — voice.tts_engines (and the language pre-check)
  stt/engine/list       — voice.stt_engines
  wake_word/info        — voice.wake_words
  conversation/prepare  — voice.prepare
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import voice


PIPER_LANGS = ["en_GB", "en-us", "de_DE", "fr_FR"]


@pytest.fixture
def engines(fake_client):
    fake_client.set_ws(
        "tts/engine/list",
        {
            "providers": [
                {"engine_id": "tts.piper", "supported_languages": PIPER_LANGS},
                {
                    "engine_id": "google_translate",
                    "name": "Google Translate",
                    "supported_languages": ["en", "de"],
                    "deprecated": True,
                },
            ]
        },
    )
    return fake_client


class TestEngine:
    def test_an_entity_backed_engine(self, fake_client):
        fake_client.set_ws(
            "tts/engine/get",
            {"provider": {"engine_id": "tts.piper", "supported_languages": PIPER_LANGS}},
        )
        got = voice.engine(fake_client, "tts.piper")
        assert got["kind"] == "entity"
        assert got["language_count"] == 4

    def test_a_legacy_provider_has_a_name_and_no_dot(self, fake_client):
        """These have no entity, so `tts list` / `state get` cannot see them."""
        fake_client.set_ws(
            "tts/engine/get",
            {
                "provider": {
                    "engine_id": "google_translate",
                    "name": "Google Translate",
                    "supported_languages": ["en"],
                }
            },
        )
        got = voice.engine(fake_client, "google_translate")
        assert got["kind"] == "legacy provider"
        assert got["name"] == "Google Translate"

    def test_an_unknown_engine_names_where_to_look(self, fake_client):
        fake_client.set_ws("tts/engine/get", {})
        with pytest.raises(ValueError, match="No TTS engine"):
            voice.engine(fake_client, "tts.nope")

    def test_an_empty_engine_id_is_refused_before_the_call(self, fake_client):
        with pytest.raises(ValueError, match="engine_id is required"):
            voice.engine(fake_client, "")
        assert fake_client.ws_calls == []


class TestVoices:
    def test_the_voice_ids_come_back_with_how_to_use_them(self, engines):
        engines.set_ws(
            "tts/engine/voices",
            {"voices": [{"voice_id": "alan", "name": "Alan"}, {"voice_id": "alba"}]},
        )
        got = voice.voices(engines, "tts.piper", "en_GB")
        assert got["count"] == 2
        assert "--options" in got["note"] or "--option" in got["note"]

    def test_an_empty_engine_id_is_refused_before_anything_is_read(self, engines):
        with pytest.raises(ValueError, match="engine_id is required"):
            voice.voices(engines, "", "en_GB")
        assert engines.ws_calls == []

    def test_language_is_required_because_has_schema_requires_it(self, engines):
        with pytest.raises(ValueError, match="language is required"):
            voice.voices(engines, "tts.piper", "")
        assert engines.ws_calls == []

    def test_an_undeclared_language_is_caught_before_the_empty_list(self, engines):
        """HA answers an unknown language with `voices: []`, not an error."""
        with pytest.raises(ValueError) as exc:
            voice.voices(engines, "tts.piper", "en-GB")
        assert "does not declare" in str(exc.value)
        assert "en_GB" in str(exc.value)  # the near match is named
        assert [c["type"] for c in engines.ws_calls] == ["tts/engine/list"]

    def test_the_check_can_be_turned_off(self, engines):
        engines.set_ws("tts/engine/voices", {"voices": []})
        got = voice.voices(engines, "tts.piper", "en-GB", check_language=False)
        assert got["language_checked"] is False
        assert engines.ws_calls[-1]["type"] == "tts/engine/voices"

    def test_an_engine_with_no_declared_languages_is_not_second_guessed(self, fake_client):
        fake_client.set_ws("tts/engine/list", {"providers": []})
        fake_client.set_ws("tts/engine/voices", {"voices": [{"voice_id": "x"}]})
        got = voice.voices(fake_client, "tts.mystery", "en-GB")
        assert got["count"] == 1
        assert got["language_checked"] is False

    def test_a_broken_engine_list_does_not_kill_the_real_call(self, fake_client):
        class Boom(type(fake_client)):
            def ws_call(self, msg_type, payload=None):
                if msg_type == "tts/engine/list":
                    raise RuntimeError("no")
                return super().ws_call(msg_type, payload)

        client = Boom()
        client.set_ws("tts/engine/voices", {"voices": [{"voice_id": "x"}]})
        assert voice.voices(client, "tts.piper", "en_GB")["count"] == 1

    def test_no_voices_is_explained_rather_than_left_ambiguous(self, engines):
        engines.set_ws("tts/engine/voices", {"voices": []})
        got = voice.voices(engines, "tts.piper", "de_DE")
        assert got["count"] == 0
        assert "single built-in voice" in got["note"]

    def test_the_payload_is_exactly_what_ha_asks_for(self, engines):
        engines.set_ws("tts/engine/voices", {"voices": []})
        voice.voices(engines, "tts.piper", "fr_FR")
        assert engines.ws_calls[-1]["payload"] == {
            "engine_id": "tts.piper",
            "language": "fr_FR",
        }


class TestEngineLists:
    def test_tts_engines_separates_entities_from_legacy_providers(self, engines):
        rows = voice.tts_engines(engines)
        kinds = {r["engine_id"]: r["kind"] for r in rows}
        assert kinds == {"tts.piper": "entity", "google_translate": "legacy provider"}

    def test_has_own_deprecated_flag_is_passed_through(self, engines):
        rows = voice.tts_engines(engines)
        legacy = next(r for r in rows if r["engine_id"] == "google_translate")
        assert legacy["deprecated"] is True

    def test_tts_engines_takes_the_same_filters_as_the_stt_list(self, engines):
        rows = voice.tts_engines(engines, language="en_GB", country="GB")
        assert engines.ws_calls[-1]["payload"] == {"language": "en_GB", "country": "GB"}
        by_id = {r["engine_id"]: r["supports_requested_language"] for r in rows}
        assert by_id == {"tts.piper": True, "google_translate": True}

    def test_tts_engines_unfiltered_sends_no_payload(self, engines):
        voice.tts_engines(engines)
        assert engines.ws_calls[-1]["payload"] is None

    def test_a_language_filter_marks_the_engines_that_cannot_do_it(self, fake_client):
        """HA empties `supported_languages` instead of dropping the engine."""
        fake_client.set_ws(
            "stt/engine/list",
            {
                "providers": [
                    {"engine_id": "stt.whisper", "supported_languages": ["en-GB"]},
                    {"engine_id": "stt.deaf", "supported_languages": []},
                ]
            },
        )
        rows = voice.stt_engines(fake_client, language="en-GB")
        assert {r["engine_id"]: r["supports_requested_language"] for r in rows} == {
            "stt.whisper": True,
            "stt.deaf": False,
        }

    def test_no_filter_means_no_payload_at_all(self, fake_client):
        fake_client.set_ws("stt/engine/list", {"providers": []})
        voice.stt_engines(fake_client)
        assert fake_client.ws_calls[-1]["payload"] is None

    def test_country_refines_the_language_and_is_sent_as_given(self, fake_client):
        fake_client.set_ws("stt/engine/list", {"providers": []})
        voice.stt_engines(fake_client, language="en", country="GB")
        assert fake_client.ws_calls[-1]["payload"] == {"language": "en", "country": "GB"}

    def test_a_missing_providers_key_is_an_empty_list_not_a_crash(self, fake_client):
        fake_client.set_ws("stt/engine/list", {})
        assert voice.stt_engines(fake_client) == []


class TestWakeWords:
    def test_the_ids_are_pulled_out_because_that_is_what_gets_configured(self, fake_client):
        fake_client.set_ws(
            "wake_word/info",
            {"wake_words": [{"id": "ok_nabu", "name": "Okay Nabu"}, {"id": "hey_jarvis"}]},
        )
        got = voice.wake_words(fake_client, "wake_word.openwakeword")
        assert got["ids"] == ["ok_nabu", "hey_jarvis"]
        assert got["count"] == 2

    def test_a_satellite_entity_is_refused_with_the_right_command_named(self, fake_client):
        with pytest.raises(ValueError) as exc:
            voice.wake_words(fake_client, "assist_satellite.kitchen")
        assert "assist-satellite config" in str(exc.value)
        assert fake_client.ws_calls == []

    def test_an_empty_entity_id_is_refused(self, fake_client):
        with pytest.raises(ValueError, match="entity_id is required"):
            voice.wake_words(fake_client, "")

    def test_a_provider_offering_nothing_is_zero_not_an_error(self, fake_client):
        fake_client.set_ws("wake_word/info", {"wake_words": []})
        assert voice.wake_words(fake_client, "wake_word.x")["count"] == 0


class TestPrepare:
    def test_a_null_result_is_success_not_a_dropped_call(self, fake_client):
        fake_client.set_ws("conversation/prepare", None)
        got = voice.prepare(fake_client)
        assert got["prepared"] is True
        assert got["agent_id"] == "(default agent)"

    def test_no_options_sends_no_payload(self, fake_client):
        voice.prepare(fake_client)
        assert fake_client.ws_calls[-1] == {"type": "conversation/prepare", "payload": None}

    def test_both_options_are_forwarded(self, fake_client):
        voice.prepare(fake_client, agent_id="conversation.home", language="en-GB")
        assert fake_client.ws_calls[-1]["payload"] == {
            "agent_id": "conversation.home",
            "language": "en-GB",
        }
