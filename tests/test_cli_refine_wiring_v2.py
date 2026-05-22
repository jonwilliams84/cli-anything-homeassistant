"""CLI wiring tests for the second refine pass:
camera, device-automation, assist (extensions), assist-satellite, mobile-app, media.

Same pattern as test_cli_refine_wiring.py — CliRunner with FakeClient injected
via make_client. No real Home Assistant required.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from cli_anything.homeassistant import homeassistant_cli as cli_mod


@pytest.fixture
def runner(monkeypatch, fake_client):
    monkeypatch.setattr(cli_mod, "make_client", lambda ctx: fake_client)
    return CliRunner()


def _invoke(runner, *args, json_out=True):
    full = ["--json"] + list(args) if json_out else list(args)
    return runner.invoke(cli_mod.cli, full, obj={
        "url": "http://x", "token": "t", "verify_ssl": False,
        "timeout": 5, "as_json": json_out, "config_path": None,
    })


# ──────────────────────────────────────────────────────────────────── camera

class TestCameraCli:
    def test_capabilities(self, runner, fake_client):
        fake_client.set_ws("camera/capabilities",
                           {"frontend_stream_types": ["hls", "webrtc"]})
        r = _invoke(runner, "camera", "capabilities", "camera.front_door")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["frontend_stream_types"] == ["hls", "webrtc"]
        assert fake_client.ws_calls[-1]["payload"] == {
            "entity_id": "camera.front_door",
        }

    def test_stream(self, runner, fake_client):
        fake_client.set_ws("camera/stream", {"url": "/api/hls/abc.m3u8"})
        r = _invoke(runner, "camera", "stream", "camera.front_door")
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert last["type"] == "camera/stream"
        assert last["payload"] == {
            "entity_id": "camera.front_door", "format": "hls",
        }

    def test_stream_wrong_domain(self, runner, fake_client):
        r = _invoke(runner, "camera", "stream", "light.kitchen")
        assert r.exit_code != 0

    def test_prefs_get(self, runner, fake_client):
        fake_client.set_ws("camera/get_prefs",
                           {"preload_stream": True, "orientation": 1})
        r = _invoke(runner, "camera", "prefs-get", "camera.front_door")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["preload_stream"] is True

    def test_prefs_set_requires_flag(self, runner, fake_client):
        r = _invoke(runner, "camera", "prefs-set", "camera.front_door")
        assert r.exit_code != 0
        assert "preload-stream" in r.output

    def test_prefs_set_preload(self, runner, fake_client):
        fake_client.set_ws("camera/update_prefs", {"ok": True})
        r = _invoke(runner, "camera", "prefs-set", "camera.front_door",
                    "--preload-stream")
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert last["type"] == "camera/update_prefs"
        assert last["payload"]["preload_stream"] is True
        assert last["payload"]["entity_id"] == "camera.front_door"

    def test_prefs_set_orientation(self, runner, fake_client):
        fake_client.set_ws("camera/update_prefs", {"ok": True})
        r = _invoke(runner, "camera", "prefs-set", "camera.front_door",
                    "--orientation", "3")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"]["orientation"] == 3

    def test_webrtc_config(self, runner, fake_client):
        fake_client.set_ws("camera/webrtc/get_client_config",
                           {"configuration": {"iceServers": []}})
        r = _invoke(runner, "camera", "webrtc-config", "camera.front_door")
        assert r.exit_code == 0, r.output


# ──────────────────────────────────────────────────────────────────── device-automation

class TestDeviceAutomationCli:
    def test_triggers(self, runner, fake_client):
        fake_client.set("POST", "config/device_automation/trigger/list",
                        [{"platform": "device", "type": "turned_on"}])
        # device_automation uses get/post — check the appropriate call.
        # We don't know exact mechanism; let's stub both ws and rest paths.
        fake_client.set_ws("device_automation/list/trigger",
                           [{"platform": "device", "type": "turned_on"}])
        r = _invoke(runner, "device-automation", "triggers", "dev_abc")
        assert r.exit_code == 0, r.output

    def test_conditions(self, runner, fake_client):
        fake_client.set("POST", "config/device_automation/condition/list", [])
        fake_client.set_ws("device_automation/list/condition", [])
        r = _invoke(runner, "device-automation", "conditions", "dev_abc")
        assert r.exit_code == 0, r.output

    def test_actions(self, runner, fake_client):
        fake_client.set("POST", "config/device_automation/action/list", [])
        fake_client.set_ws("device_automation/list/action", [])
        r = _invoke(runner, "device-automation", "actions", "dev_abc")
        assert r.exit_code == 0, r.output

    def test_summary(self, runner, fake_client):
        fake_client.set("POST", "config/device_automation/trigger/list", [])
        fake_client.set("POST", "config/device_automation/condition/list", [])
        fake_client.set("POST", "config/device_automation/action/list", [])
        fake_client.set_ws("device_automation/list/trigger", [])
        fake_client.set_ws("device_automation/list/condition", [])
        fake_client.set_ws("device_automation/list/action", [])
        r = _invoke(runner, "device-automation", "summary", "dev_abc")
        assert r.exit_code == 0, r.output


# ──────────────────────────────────────────────────────────────────── assist (new subcommands)

class TestAssistExtensionsCli:
    def test_agents(self, runner, fake_client):
        fake_client.set_ws("conversation/agent/list",
                           {"agents": [{"id": "homeassistant"}]})
        r = _invoke(runner, "assist", "agents")
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert last["type"] == "conversation/agent/list"

    def test_agents_with_filters(self, runner, fake_client):
        fake_client.set_ws("conversation/agent/list", {"agents": []})
        r = _invoke(runner, "assist", "agents",
                    "--country", "GB", "--language", "en")
        assert r.exit_code == 0, r.output
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload.get("country") == "GB"
        assert payload.get("language") == "en"

    def test_sentences(self, runner, fake_client):
        fake_client.set_ws("conversation/sentences/list", {"intents": {}})
        r = _invoke(runner, "assist", "sentences", "en")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {"language": "en"}

    def test_debug(self, runner, fake_client):
        fake_client.set_ws("conversation/agent/homeassistant/debug",
                           {"results": [{"intent": "HassTurnOn"}]})
        r = _invoke(runner, "assist", "debug", "turn on the lamp")
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert "debug" in last["type"]
        assert last["payload"]["sentence"] == "turn on the lamp"

    def test_satellites(self, runner, fake_client):
        fake_client.set_ws("assist_pipeline/device/list", [{"device_id": "d1"}])
        r = _invoke(runner, "assist", "satellites")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data[0]["device_id"] == "d1"

    def test_languages(self, runner, fake_client):
        fake_client.set_ws("assist_pipeline/language/list",
                           {"languages": ["en", "fr"]})
        r = _invoke(runner, "assist", "languages")
        assert r.exit_code == 0, r.output


# ──────────────────────────────────────────────────────────────────── assist-satellite

class TestAssistSatelliteCli:
    def test_config(self, runner, fake_client):
        fake_client.set_ws("assist_satellite/get_configuration",
                           {"active_wake_words": ["okay_nabu"]})
        r = _invoke(runner, "assist-satellite", "config",
                    "assist_satellite.kitchen")
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert last["payload"] == {"entity_id": "assist_satellite.kitchen"}

    def test_wake_words_set(self, runner, fake_client):
        fake_client.set_ws("assist_satellite/set_wake_words", {"ok": True})
        r = _invoke(runner, "assist-satellite", "wake-words-set",
                    "assist_satellite.kitchen",
                    "okay_nabu", "hey_jarvis")
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert last["payload"]["wake_word_ids"] == ["okay_nabu", "hey_jarvis"]
        assert last["payload"]["entity_id"] == "assist_satellite.kitchen"

    def test_wake_words_set_requires_at_least_one(self, runner, fake_client):
        r = _invoke(runner, "assist-satellite", "wake-words-set",
                    "assist_satellite.kitchen")
        # Click marks `nargs=-1, required=True` as needing 1+ args
        assert r.exit_code != 0

    def test_test_connection(self, runner, fake_client):
        fake_client.set_ws("assist_satellite/test_connection", {"ok": True})
        r = _invoke(runner, "assist-satellite", "test-connection",
                    "assist_satellite.kitchen")
        assert r.exit_code == 0, r.output


# ──────────────────────────────────────────────────────────────────── mobile-app

class TestMobileAppCli:
    def test_confirm_push(self, runner, fake_client):
        fake_client.set_ws("mobile_app/push_notification_confirm",
                           {"ok": True})
        r = _invoke(runner, "mobile-app", "confirm-push",
                    "webhook-123", "confirm-456")
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert last["type"] == "mobile_app/push_notification_confirm"
        assert last["payload"] == {
            "webhook_id": "webhook-123",
            "confirm_id": "confirm-456",
        }


# ──────────────────────────────────────────────────────────────────── media

class TestMediaCli:
    def test_browse_root(self, runner, fake_client):
        fake_client.set_ws("media_source/browse_media",
                           {"title": "Media", "children": []})
        r = _invoke(runner, "media", "browse")
        assert r.exit_code == 0, r.output
        last = fake_client.ws_calls[-1]
        assert last["type"] == "media_source/browse_media"

    def test_browse_with_id(self, runner, fake_client):
        fake_client.set_ws("media_source/browse_media",
                           {"title": "TTS", "children": []})
        r = _invoke(runner, "media", "browse",
                    "--media-content-id", "media-source://tts")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"].get("media_content_id") == \
            "media-source://tts"

    def test_resolve(self, runner, fake_client):
        fake_client.set_ws("media_source/resolve_media",
                           {"url": "/api/tts_proxy/abc.mp3",
                            "mime_type": "audio/mp3"})
        r = _invoke(runner, "media", "resolve",
                    "media-source://tts/cloud?message=hi")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["mime_type"] == "audio/mp3"

    def test_remove_requires_confirm(self, runner, fake_client):
        # --confirmation_option without --yes should reject (no tty input).
        r = _invoke(runner, "media", "remove",
                    "media-source://media_source/local/song.mp3")
        assert r.exit_code != 0  # aborted by confirmation prompt

    def test_remove_with_yes(self, runner, fake_client):
        fake_client.set_ws("media_source/local_source/remove", {"ok": True})
        r = _invoke(runner, "media", "remove",
                    "media-source://media_source/local/song.mp3",
                    "--yes")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["type"] == "media_source/local_source/remove"
