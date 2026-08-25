"""Home Assistant Cloud (Nabu Casa) — core wire payloads and the logged-out split.

These pin two things: the exact websocket payloads sent, and the deliberate
asymmetry between READ commands (which answer `logged_in: false`) and WRITE
commands (which raise). See `core/cloud.py` for why they differ.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import cloud as cloud_core
from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

from .conftest import FakeClient


# ─────────────────────────────────────────────────────────────────── status


LOGGED_IN_STATUS = {
    "logged_in": True,
    "email": "someone@example.com",
    "cloud": "connected",
    "active_subscription": True,
    "cloud_last_disconnect_reason": None,
    "alexa_registered": True,
    "google_registered": False,
    "google_local_connected": True,
    "remote_connected": True,
    "remote_domain": "abc123.ui.nabu.casa",
    "remote_certificate_status": "ready",
    "remote_certificate": {"expire_date": "2027-01-01"},
    "http_use_ssl": False,
    "prefs": {
        "alexa_enabled": True,
        "alexa_report_state": True,
        "google_enabled": False,
        "google_report_state": False,
        "google_secure_devices_pin": "1234",
        "remote_allow_remote_enable": True,
    },
}


class TestStatus:
    def test_sends_the_command_and_summarises(self):
        client = FakeClient()
        client.set_ws("cloud/status", LOGGED_IN_STATUS)
        out = cloud_core.status(client)
        assert client.ws_calls == [{"type": "cloud/status", "payload": None}]
        assert out["logged_in"] is True
        assert out["email"] == "someone@example.com"
        assert out["connection"] == "connected"
        assert out["connected"] is True
        assert out["active_subscription"] is True

    def test_flattens_remote_alexa_and_google(self):
        client = FakeClient()
        client.set_ws("cloud/status", LOGGED_IN_STATUS)
        out = cloud_core.status(client)
        assert out["remote"]["domain"] == "abc123.ui.nabu.casa"
        assert out["remote"]["certificate_status"] == "ready"
        assert out["alexa"] == {"enabled": True, "report_state": True, "registered": True}
        assert out["google"]["enabled"] is False
        assert out["google"]["local_connected"] is True

    def test_pin_is_reported_as_set_not_echoed(self):
        """A secure-devices PIN must not be handed back in the summary."""
        client = FakeClient()
        client.set_ws("cloud/status", LOGGED_IN_STATUS)
        out = cloud_core.status(client)
        assert out["google"]["secure_devices_pin_set"] is True
        assert "1234" not in str(out["google"])

    def test_logged_out_keeps_every_key(self):
        """HA returns 3 keys logged out; the summary shape must not change."""
        client = FakeClient()
        client.set_ws("cloud/status", {"logged_in": False, "cloud": "disconnected"})
        out = cloud_core.status(client)
        assert out["logged_in"] is False
        assert out["email"] is None
        assert out["connected"] is False
        assert out["alexa"]["enabled"] is None
        assert out["remote"]["domain"] is None
        assert "not logged in" in out["note"].lower()

    def test_connected_is_not_logged_in(self):
        """A signed-in but disconnected instance is the 'Alexa broke' symptom."""
        client = FakeClient()
        client.set_ws(
            "cloud/status", dict(LOGGED_IN_STATUS, cloud="disconnected")
        )
        out = cloud_core.status(client)
        assert out["logged_in"] is True
        assert out["connected"] is False

    def test_non_dict_is_refused(self):
        client = FakeClient()
        client.set_ws("cloud/status", ["nope"])
        with pytest.raises(ValueError, match="expected an object"):
            cloud_core.status(client)


# ─────────────────────────────────────────────────────────── read vs write


class TestLoggedOutSplit:
    def test_read_returns_a_named_answer(self):
        client = FakeClient()
        client.set_ws_error("cloud/subscription", "not_logged_in", "You need to be logged in.")
        out = cloud_core.subscription(client)
        assert out["logged_in"] is False
        assert out["subscription"] is None
        assert "sign in" in out["note"].lower()

    def test_read_passes_the_payload_through_when_logged_in(self):
        client = FakeClient()
        client.set_ws("cloud/subscription", {"plan": "yearly", "human_description": "Expires"})
        out = cloud_core.subscription(client)
        assert out["logged_in"] is True
        assert out["subscription"]["plan"] == "yearly"

    def test_read_does_not_swallow_other_errors(self):
        """`request_failed` means 'could not ask', which is not 'no subscription'."""
        client = FakeClient()
        client.set_ws_error("cloud/subscription", "request_failed", "Failed to request")
        with pytest.raises(HomeAssistantError, match="request_failed"):
            cloud_core.subscription(client)

    def test_write_raises_with_the_remedy(self):
        client = FakeClient()
        client.set_ws_error("cloud/remote/connect", "not_logged_in", "")
        with pytest.raises(ValueError, match="not logged in"):
            cloud_core.remote_connect(client)

    def test_write_error_names_the_ui_path(self):
        client = FakeClient()
        client.set_ws_error("cloud/update_prefs", "not_logged_in", "")
        with pytest.raises(ValueError, match="Settings > Home Assistant Cloud"):
            cloud_core.set_prefs(client, alexa_enabled=True)


# ──────────────────────────────────────────────────────────────────── prefs


class TestSetPrefs:
    def test_only_sends_what_was_passed(self):
        client = FakeClient()
        cloud_core.set_prefs(client, alexa_enabled=True)
        assert client.ws_calls[0]["type"] == "cloud/update_prefs"
        assert client.ws_calls[0]["payload"] == {"alexa_enabled": True}

    def test_false_is_sent_not_treated_as_absent(self):
        """`--no-alexa` must reach HA; a falsy value is not a missing value."""
        client = FakeClient()
        cloud_core.set_prefs(client, alexa_enabled=False, google_report_state=False)
        assert client.ws_calls[0]["payload"] == {
            "alexa_enabled": False,
            "google_report_state": False,
        }

    def test_empty_pin_clears_it(self):
        client = FakeClient()
        cloud_core.set_prefs(client, google_secure_devices_pin="")
        assert client.ws_calls[0]["payload"] == {"google_secure_devices_pin": None}

    def test_pin_is_sent_verbatim(self):
        client = FakeClient()
        cloud_core.set_prefs(client, google_secure_devices_pin="4321")
        assert client.ws_calls[0]["payload"] == {"google_secure_devices_pin": "4321"}

    def test_tts_voice_pair(self):
        client = FakeClient()
        cloud_core.set_prefs(client, tts_default_voice=("en-GB", "RyanNeural"))
        assert client.ws_calls[0]["payload"]["tts_default_voice"] == ["en-GB", "RyanNeural"]

    @pytest.mark.parametrize("bad", [("en-GB",), ("en-GB", "", ), ("a", "b", "c")])
    def test_bad_tts_pair_is_refused_before_the_call(self, bad):
        client = FakeClient()
        with pytest.raises(ValueError, match="language, voice"):
            cloud_core.set_prefs(client, tts_default_voice=bad)
        assert client.ws_calls == []

    def test_nothing_to_update_is_refused(self):
        client = FakeClient()
        with pytest.raises(ValueError, match="Nothing to update"):
            cloud_core.set_prefs(client)
        assert client.ws_calls == []

    def test_returns_what_it_sent(self):
        client = FakeClient()
        out = cloud_core.set_prefs(client, google_enabled=True)
        assert out["applied"] is True
        assert out["updated"] == {"google_enabled": True}


# ─────────────────────────────────────────────────────────────────── remote


class TestRemote:
    def test_connect(self):
        client = FakeClient()
        out = cloud_core.remote_connect(client)
        assert client.ws_calls == [{"type": "cloud/remote/connect", "payload": None}]
        assert out["applied"] is True

    def test_disconnect(self):
        client = FakeClient()
        out = cloud_core.remote_disconnect(client)
        assert client.ws_calls == [{"type": "cloud/remote/disconnect", "payload": None}]
        assert out["applied"] is True
        assert "cloudhooks" in out["note"]


# ─────────────────────────────────────────────────────────────────── alexa


class TestAlexa:
    def test_entities_list(self):
        client = FakeClient()
        client.set_ws(
            "cloud/alexa/entities",
            [{"entity_id": "light.k", "display_categories": ["LIGHT"], "interfaces": ["PowerController"]}],
        )
        out = cloud_core.alexa_entities(client)
        assert out["logged_in"] is True
        assert out["entities"][0]["entity_id"] == "light.k"

    def test_entity_supported_is_an_empty_result(self):
        """HA sends no payload on success — `supported: true` is inferred."""
        client = FakeClient()
        client.set_ws("cloud/alexa/entities/get", None)
        out = cloud_core.alexa_entity(client, "light.kitchen")
        assert out["supported"] is True
        assert client.ws_calls[0]["payload"] == {"entity_id": "light.kitchen"}

    def test_entity_not_supported_is_false_not_an_error(self):
        client = FakeClient()
        client.set_ws_error("cloud/alexa/entities/get", "not_supported", "nope")
        out = cloud_core.alexa_entity(client, "sensor.weird")
        assert out["supported"] is False
        assert "cannot be represented" in out["note"]

    def test_entity_logged_out(self):
        client = FakeClient()
        client.set_ws_error("cloud/alexa/entities/get", "not_logged_in", "")
        out = cloud_core.alexa_entity(client, "light.kitchen")
        assert out["logged_in"] is False
        assert out["supported"] is None

    @pytest.mark.parametrize("bad", ["", "kitchen", "nodot"])
    def test_entity_id_is_validated_first(self, bad):
        client = FakeClient()
        with pytest.raises(ValueError, match="Not an entity_id"):
            cloud_core.alexa_entity(client, bad)
        assert client.ws_calls == []

    def test_sync(self):
        client = FakeClient()
        out = cloud_core.alexa_sync(client)
        assert client.ws_calls == [{"type": "cloud/alexa/sync", "payload": None}]
        assert out["applied"] is True

    def test_relink_names_the_app_not_a_retry(self):
        client = FakeClient()
        client.set_ws_error("cloud/alexa/sync", "alexa_relink", "Please re-link.")
        with pytest.raises(ValueError, match="re-linked"):
            cloud_core.alexa_sync(client)


# ────────────────────────────────────────────────────────────────── google


class TestGoogle:
    def test_entities_list(self):
        client = FakeClient()
        client.set_ws(
            "cloud/google_assistant/entities",
            [{"entity_id": "lock.front", "traits": ["action.devices.traits.LockUnlock"], "might_2fa": True}],
        )
        out = cloud_core.google_entities(client)
        assert out["entities"][0]["might_2fa"] is True

    def test_entity(self):
        client = FakeClient()
        client.set_ws(
            "cloud/google_assistant/entities/get",
            {"entity_id": "lock.front", "traits": [], "might_2fa": True, "disable_2fa": None},
        )
        out = cloud_core.google_entity(client, "lock.front")
        assert out["entity"]["might_2fa"] is True
        assert client.ws_calls[0]["payload"] == {"entity_id": "lock.front"}

    def test_entity_not_found_is_a_value_error(self):
        client = FakeClient()
        client.set_ws_error("cloud/google_assistant/entities/get", "not_found", "unknown")
        with pytest.raises(ValueError, match="no such entity"):
            cloud_core.google_entity(client, "lock.nope")

    def test_set_2fa_skip(self):
        client = FakeClient()
        out = cloud_core.google_set_2fa(client, "lock.front", disable_2fa=True)
        assert client.ws_calls[0]["type"] == "cloud/google_assistant/entities/update"
        assert client.ws_calls[0]["payload"] == {"entity_id": "lock.front", "disable_2fa": True}
        assert "WITHOUT asking" in out["note"]

    def test_set_2fa_require(self):
        client = FakeClient()
        out = cloud_core.google_set_2fa(client, "lock.front", disable_2fa=False)
        assert client.ws_calls[0]["payload"]["disable_2fa"] is False
        assert "require" in out["note"]


# ───────────────────────────────────────────────────────────────────── tts


TTS_PAIRS = {
    "languages": [
        ["en-GB", "RyanNeural"],
        ["en-GB", "SoniaNeural"],
        ["en-US", "JennyNeural"],
        ["nl-NL", "ColetteNeural"],
    ]
}


class TestTtsInfo:
    def test_groups_pairs_by_language(self):
        client = FakeClient()
        client.set_ws("cloud/tts/info", TTS_PAIRS)
        out = cloud_core.tts_info(client)
        assert out["languages"] == ["en-GB", "en-US", "nl-NL"]
        assert out["voices"]["en-GB"] == ["RyanNeural", "SoniaNeural"]
        assert out["language_count"] == 3
        assert out["voice_count"] == 4

    def test_filter_by_language(self):
        client = FakeClient()
        client.set_ws("cloud/tts/info", TTS_PAIRS)
        out = cloud_core.tts_info(client, language="en-GB")
        assert out["languages"] == ["en-GB"]
        assert out["voice_count"] == 2

    def test_unknown_language_suggests_the_family(self):
        client = FakeClient()
        client.set_ws("cloud/tts/info", TTS_PAIRS)
        with pytest.raises(ValueError, match="en-GB"):
            cloud_core.tts_info(client, language="en-AU")

    def test_malformed_pairs_are_skipped_not_fatal(self):
        client = FakeClient()
        client.set_ws("cloud/tts/info", {"languages": [["en-GB", "A"], ["oops"], "nope", None]})
        out = cloud_core.tts_info(client)
        assert out["voices"] == {"en-GB": ["A"]}

    def test_empty_is_not_an_error(self):
        client = FakeClient()
        client.set_ws("cloud/tts/info", {})
        out = cloud_core.tts_info(client)
        assert out["languages"] == []
        assert out["voice_count"] == 0


# ─────────────────────────────────────────────────────────── remove-data


class TestRemoveData:
    def test_dry_run_by_default_sends_nothing(self):
        client = FakeClient()
        out = cloud_core.remove_data(client)
        assert out["applied"] is False
        assert client.ws_calls == []
        assert "--apply" in out["note"]

    def test_apply_sends_the_command(self):
        client = FakeClient()
        out = cloud_core.remove_data(client, apply=True)
        assert client.ws_calls == [{"type": "cloud/remove_data", "payload": None}]
        assert out["applied"] is True

    def test_refuses_while_logged_in_with_the_inverted_guard(self):
        """This is the one command HA blocks while you ARE signed in."""
        client = FakeClient()
        client.set_ws_error("cloud/remove_data", "logged_in", "Can't remove data when logged in.")
        with pytest.raises(ValueError, match="Sign out"):
            cloud_core.remove_data(client, apply=True)
