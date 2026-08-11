"""Unit tests for the instance-preferences cluster: labs, prefs, device-links,
intents, and the two TTS corrections.

(Unit conversion is NOT here — `core/device_class_units.py` landed on main
while this was being written and owns it.)

All against FakeClient. Every expected shape was taken from the running
2026.8.1 instance.

WS message types covered:
  labs/list, labs/update
  ai_task/preferences/get, ai_task/preferences/set
  http/config
  config/entity_registry/settings/get, .../settings/update
  config/entity_registry/get_automatic_entity_ids
  recorder/entity_options/get
  config/device_registry/list_composite_splits, .../list_linked_devices
  tts/engine/list

REST endpoint covered:
  POST intent/handle, POST tts_get_url
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import (
    device_links,
    intents,
    labs,
    preferences,
    tts,
)

FEATURES = {
    "features": [
        {
            "domain": "analytics",
            "preview_feature": "snapshots",
            "enabled": False,
            "is_built_in": True,
            "learn_more_url": "https://example.invalid/a",
            "feedback_url": "https://example.invalid/b",
        },
        {
            "domain": "frontend",
            "preview_feature": "winter_mode",
            "enabled": True,
            "is_built_in": True,
        },
    ]
}


class TestLabs:
    def test_list_flattens_the_features_array(self, fake_client):
        fake_client.set_ws("labs/list", FEATURES)
        rows = labs.list_features(fake_client)
        assert [r["preview_feature"] for r in rows] == ["snapshots", "winter_mode"]

    def test_enabled_only_is_the_one_that_explains_odd_behaviour(self, fake_client):
        fake_client.set_ws("labs/list", FEATURES)
        assert [f["preview_feature"] for f in labs.enabled_features(fake_client)] == [
            "winter_mode"
        ]

    def test_an_unknown_feature_names_what_the_domain_does_have(self, fake_client):
        fake_client.set_ws("labs/list", FEATURES)
        with pytest.raises(ValueError, match="snapshots"):
            labs.get_feature(fake_client, "analytics", "nope")

    def test_an_unknown_domain_names_the_domains_that_exist(self, fake_client):
        fake_client.set_ws("labs/list", FEATURES)
        with pytest.raises(ValueError, match="analytics"):
            labs.get_feature(fake_client, "nosuchdomain", "x")

    def test_create_backup_is_sent_explicitly(self, fake_client):
        """HA defaults it False; a preview feature can migrate storage."""
        fake_client.set_ws("labs/list", FEATURES)
        fake_client.set_ws("labs/update", {})
        labs.set_feature(fake_client, "analytics", "snapshots", True, create_backup=True)
        update = [c for c in fake_client.ws_calls if c["type"] == "labs/update"][-1]
        assert update["payload"]["create_backup"] is True
        assert update["payload"]["enabled"] is True

    def test_it_reports_was_and_now(self, fake_client):
        fake_client.set_ws("labs/list", FEATURES)
        fake_client.set_ws("labs/update", {})
        got = labs.set_feature(fake_client, "frontend", "winter_mode", False)
        # FakeClient replays the same list, so `now` equals `was` — which is
        # exactly the shape that proves both were read rather than assumed.
        assert got["was"] is True
        assert got["now"] is True
        assert got["changed"] is False


class TestAiTaskPreferences:
    def test_get(self, fake_client):
        fake_client.set_ws(
            "ai_task/preferences/get",
            {"gen_data_entity_id": "ai_task.google", "gen_image_entity_id": None},
        )
        got = preferences.ai_task_get(fake_client)
        assert got["gen_data_entity_id"] == "ai_task.google"

    def test_only_the_keys_given_are_sent(self, fake_client):
        """Omitting a key leaves it alone; sending None CLEARS it."""
        fake_client.set_ws("ai_task/preferences/get", {})
        fake_client.set_ws("ai_task/preferences/set", {})
        preferences.ai_task_set(fake_client, gen_data_entity_id="ai_task.x")
        sent = [c for c in fake_client.ws_calls if c["type"] == "ai_task/preferences/set"][-1]
        assert sent["payload"] == {"gen_data_entity_id": "ai_task.x"}

    def test_setting_nothing_is_refused(self, fake_client):
        with pytest.raises(ValueError, match="Nothing to set"):
            preferences.ai_task_set(fake_client)


class TestHttpConfig:
    def test_the_active_config_is_resolved_rather_than_left_to_the_caller(self, fake_client):
        fake_client.set_ws(
            "http/config",
            {"active_config_type": "stable", "stable": {"cors_allowed_origins": []},
             "pending": None, "default": {}},
        )
        got = preferences.http_config(fake_client)
        assert got["active_config_type"] == "stable"
        assert got["active"] == {"cors_allowed_origins": []}
        assert got["has_pending"] is False

    def test_a_pending_config_is_flagged(self, fake_client):
        """A change that "did not take" is usually sitting here, unpromoted."""
        fake_client.set_ws(
            "http/config",
            {"active_config_type": "stable", "stable": {}, "pending": {"x": 1}},
        )
        assert preferences.http_config(fake_client)["has_pending"] is True


class TestEntityNaming:
    def test_none_means_the_default(self, fake_client):
        fake_client.set_ws("config/entity_registry/settings/get", {"entity_id_parts": None})
        got = preferences.entity_id_settings(fake_client)
        assert got["is_default"] is True

    def test_a_list_is_not_the_default(self, fake_client):
        fake_client.set_ws(
            "config/entity_registry/settings/get",
            {"entity_id_parts": ["device", "entity"]},
        )
        assert preferences.entity_id_settings(fake_client)["is_default"] is False

    def test_automatic_ids_report_none_as_an_answer(self, fake_client):
        """None means HA has no automatic id — not that the lookup failed."""
        fake_client.set_ws(
            "config/entity_registry/get_automatic_entity_ids",
            {"sun.sun": None, "light.a": "light.kitchen_lamp"},
        )
        got = preferences.automatic_entity_ids(fake_client, ["sun.sun", "light.a"])
        by_id = {e["entity_id"]: e for e in got["entities"]}
        assert by_id["sun.sun"]["has_automatic_id"] is False
        assert by_id["light.a"]["automatic_entity_id"] == "light.kitchen_lamp"
        assert by_id["light.a"]["matches_current"] is False

    def test_an_empty_entity_list_is_refused(self, fake_client):
        with pytest.raises(ValueError, match="at least one"):
            preferences.automatic_entity_ids(fake_client, [])


class TestRecorderEntityOptions:
    def test_a_disabled_entity_explains_an_empty_history(self, fake_client):
        """Measured on a live instance: sun.sun is disabled_by "user"."""
        fake_client.set_ws("recorder/entity_options/get", {"recording_disabled_by": "user"})
        got = preferences.recorder_entity_options(fake_client, "sun.sun")
        assert got["is_recorded"] is False
        assert got["explains_empty_history"] is True

    def test_a_recorded_entity_explains_nothing(self, fake_client):
        fake_client.set_ws("recorder/entity_options/get", {"recording_disabled_by": None})
        got = preferences.recorder_entity_options(fake_client, "light.a")
        assert got["is_recorded"] is True
        assert got["explains_empty_history"] is False


class TestDeviceLinks:
    #: The key is a COMPOSITE id and is never a device id — measured on a live
    #: instance, where 0 of 51 keys were also a primary_id.
    SPLITS = {
        "composite-1": {
            "primary_id": "device-primary",
            "split_ids": ["device-primary", "device-secondary"],
        }
    }

    def test_member_of_maps_device_ids_to_the_composite_key(self, fake_client):
        fake_client.set_ws("config/device_registry/list_composite_splits", self.SPLITS)
        got = device_links.composite_splits(fake_client)
        assert got["member_of"]["device-secondary"] == "composite-1"
        assert got["member_of"]["device-primary"] == "composite-1"

    def test_a_split_member_finds_its_whole_set(self, fake_client):
        """Looking the device id up as a KEY can never match — this is why."""
        fake_client.set_ws("config/device_registry/list_composite_splits", self.SPLITS)
        got = device_links.split_for(fake_client, "device-secondary")
        assert got["is_split"] is True
        assert got["primary_id"] == "device-primary"
        assert got["is_primary"] is False
        # The ones a device-scoped call against this id would MISS.
        assert got["siblings"] == ["device-primary"]

    def test_an_unsplit_device_says_so(self, fake_client):
        fake_client.set_ws("config/device_registry/list_composite_splits", self.SPLITS)
        got = device_links.split_for(fake_client, "device-alone")
        assert got["is_split"] is False
        assert got["siblings"] == []

    def test_linked_devices_keeps_the_raw_payload(self, fake_client):
        """This API is newer than the rest of the registry; do not project it away."""
        fake_client.set_ws(
            "config/device_registry/list_linked_devices", {"linked_devices": ["d1"]}
        )
        got = device_links.linked_devices(fake_client, "d0")
        assert got["count"] == 1
        assert got["has_links"] is True
        assert got["raw"] == {"linked_devices": ["d1"]}


class TestIntents:
    def test_slots_are_sent_as_plain_values(self, fake_client):
        """HA wraps them into {"value": …} server-side; double-wrapping breaks it."""
        fake_client.set("POST", "intent/handle", {"response_type": "query_answer"})
        intents.handle(fake_client, "HassGetState", slots={"name": "sun"})
        call = fake_client.calls[-1]
        assert call["payload"]["data"] == {"name": "sun"}

    def test_the_speech_is_lifted_out_of_the_nested_shape(self, fake_client):
        fake_client.set(
            "POST",
            "intent/handle",
            {"speech": {"plain": {"speech": "The sun is up"}}, "response_type": "query_answer"},
        )
        got = intents.handle(fake_client, "HassGetState")
        assert got["speech"] == "The sun is up"

    def test_a_missing_name_is_refused(self, fake_client):
        with pytest.raises(ValueError, match="name is required"):
            intents.handle(fake_client, "")


class TestTtsCorrections:
    def test_languages_come_from_the_ws_command_not_the_entity(self, fake_client):
        """MEASURED: the entity attributes report [] while HA has the full list."""
        fake_client.set_ws(
            "tts/engine/list",
            {"providers": [{"engine_id": "tts.piper", "supported_languages": ["en_GB"]}]},
        )
        assert tts.engine_languages(fake_client) == {"tts.piper": ["en_GB"]}

    def test_list_engines_merges_the_real_languages_in(self, fake_client):
        fake_client.set_ws(
            "tts/engine/list",
            {"providers": [{"engine_id": "tts.piper", "supported_languages": ["en_GB"]}]},
        )
        fake_client.set(
            "GET",
            "states",
            [{"entity_id": "tts.piper", "state": "unknown", "attributes": {"supported_languages": []}}],
        )
        rows = tts.list_engines(fake_client)
        assert rows[0]["supported_languages"] == ["en_GB"]
        assert rows[0]["languages_from"] == "tts/engine/list"

    def test_an_unsupported_language_is_refused_before_the_bare_500(self, fake_client):
        """HA answers `500: Internal Server Error` with no body for this."""
        fake_client.set_ws(
            "tts/engine/list",
            {"providers": [{"engine_id": "tts.piper", "supported_languages": ["en_GB", "de_DE"]}]},
        )
        with pytest.raises(ValueError) as exc:
            tts.get_url(fake_client, engine_id="tts.piper", message="hi", language="en-GB")
        # The near-match is the actionable half — the separator differs per engine.
        assert "en_GB" in str(exc.value)
        assert "bare 500" in str(exc.value)

    def test_omitting_the_language_never_triggers_the_check(self, fake_client):
        """Measured: no --language works on every engine."""
        fake_client.set("POST", "tts_get_url", {"url": "http://x/a.mp3", "path": "/a.mp3"})
        got = tts.get_url(fake_client, engine_id="tts.piper", message="hi")
        assert got["url"] == "http://x/a.mp3"
        assert got["language_checked"] is False

    def test_the_check_can_be_switched_off(self, fake_client):
        fake_client.set_ws(
            "tts/engine/list",
            {"providers": [{"engine_id": "tts.piper", "supported_languages": ["en_GB"]}]},
        )
        fake_client.set("POST", "tts_get_url", {"url": "http://x/a.mp3"})
        got = tts.get_url(
            fake_client, engine_id="tts.piper", message="hi", language="en-GB",
            check_language=False,
        )
        assert got["url"] == "http://x/a.mp3"
