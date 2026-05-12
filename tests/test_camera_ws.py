"""Unit tests for camera WS commands."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import camera_ws


class TestCameraWs:
    """Tests for camera WebSocket command wrappers."""

    # ────────────────────────────────────────────────────────── capabilities

    def test_capabilities_happy_path(self, fake_client):
        """Test capabilities() sends correct WS message."""
        fake_client.set_ws("camera/capabilities",
                           {"frontend_stream_types": ["hls"]})
        result = camera_ws.capabilities(fake_client, entity_id="camera.living_room")
        assert fake_client.ws_calls[-1]["type"] == "camera/capabilities"
        assert fake_client.ws_calls[-1]["payload"]["entity_id"] == "camera.living_room"
        assert result == {"frontend_stream_types": ["hls"]}

    def test_capabilities_bad_entity_id_prefix(self, fake_client):
        """Test capabilities() rejects non-camera entity_id."""
        with pytest.raises(ValueError, match="expected camera.* entity_id"):
            camera_ws.capabilities(fake_client, entity_id="light.living_room")

    def test_capabilities_bad_entity_id_no_prefix(self, fake_client):
        """Test capabilities() rejects entity_id without domain."""
        with pytest.raises(ValueError, match="expected camera.* entity_id"):
            camera_ws.capabilities(fake_client, entity_id="living_room")

    # ────────────────────────────────────────────────────────── stream

    def test_stream_happy_path_default_format(self, fake_client):
        """Test stream() sends correct WS message with default format."""
        fake_client.set_ws("camera/stream", {"url": "http://example.com/stream.m3u8"})
        result = camera_ws.stream(fake_client, entity_id="camera.front_door")
        assert fake_client.ws_calls[-1]["type"] == "camera/stream"
        assert fake_client.ws_calls[-1]["payload"]["entity_id"] == "camera.front_door"
        assert fake_client.ws_calls[-1]["payload"]["format"] == "hls"
        assert result == {"url": "http://example.com/stream.m3u8"}

    def test_stream_happy_path_explicit_hls(self, fake_client):
        """Test stream() with explicit hls format."""
        fake_client.set_ws("camera/stream", {"url": "http://example.com/stream.m3u8"})
        result = camera_ws.stream(fake_client, entity_id="camera.back_door",
                                   format="hls")
        assert fake_client.ws_calls[-1]["payload"]["format"] == "hls"
        assert result == {"url": "http://example.com/stream.m3u8"}

    def test_stream_bad_entity_id_prefix(self, fake_client):
        """Test stream() rejects non-camera entity_id."""
        with pytest.raises(ValueError, match="expected camera.* entity_id"):
            camera_ws.stream(fake_client, entity_id="sensor.temperature")

    def test_stream_bad_format(self, fake_client):
        """Test stream() rejects unsupported format."""
        with pytest.raises(ValueError, match="format must be 'hls'"):
            camera_ws.stream(fake_client, entity_id="camera.test", format="rtsp")

    def test_stream_bad_format_empty(self, fake_client):
        """Test stream() rejects empty format string."""
        with pytest.raises(ValueError, match="format must be 'hls'"):
            camera_ws.stream(fake_client, entity_id="camera.test", format="")

    # ────────────────────────────────────────────────────────── get_prefs

    def test_get_prefs_happy_path(self, fake_client):
        """Test get_prefs() sends correct WS message."""
        fake_client.set_ws("camera/get_prefs",
                           {"preload_stream": True, "orientation": 1})
        result = camera_ws.get_prefs(fake_client, entity_id="camera.bedroom")
        assert fake_client.ws_calls[-1]["type"] == "camera/get_prefs"
        assert fake_client.ws_calls[-1]["payload"]["entity_id"] == "camera.bedroom"
        assert result == {"preload_stream": True, "orientation": 1}

    def test_get_prefs_bad_entity_id(self, fake_client):
        """Test get_prefs() rejects non-camera entity_id."""
        with pytest.raises(ValueError, match="expected camera.* entity_id"):
            camera_ws.get_prefs(fake_client, entity_id="switch.test")

    # ────────────────────────────────────────────────────────── update_prefs

    def test_update_prefs_happy_path_preload_stream(self, fake_client):
        """Test update_prefs() with preload_stream."""
        fake_client.set_ws("camera/update_prefs",
                           {"preload_stream": True, "orientation": 1})
        result = camera_ws.update_prefs(fake_client, entity_id="camera.kitchen",
                                        preload_stream=True)
        assert fake_client.ws_calls[-1]["type"] == "camera/update_prefs"
        assert fake_client.ws_calls[-1]["payload"]["entity_id"] == "camera.kitchen"
        assert fake_client.ws_calls[-1]["payload"]["preload_stream"] is True
        assert "orientation" not in fake_client.ws_calls[-1]["payload"]
        assert result == {"preload_stream": True, "orientation": 1}

    def test_update_prefs_happy_path_orientation(self, fake_client):
        """Test update_prefs() with orientation."""
        fake_client.set_ws("camera/update_prefs",
                           {"preload_stream": False, "orientation": 3})
        result = camera_ws.update_prefs(fake_client, entity_id="camera.garage",
                                        orientation=3)
        assert fake_client.ws_calls[-1]["type"] == "camera/update_prefs"
        assert fake_client.ws_calls[-1]["payload"]["entity_id"] == "camera.garage"
        assert fake_client.ws_calls[-1]["payload"]["orientation"] == 3
        assert "preload_stream" not in fake_client.ws_calls[-1]["payload"]
        assert result == {"preload_stream": False, "orientation": 3}

    def test_update_prefs_happy_path_both(self, fake_client):
        """Test update_prefs() with both preload_stream and orientation."""
        fake_client.set_ws("camera/update_prefs",
                           {"preload_stream": False, "orientation": 6})
        result = camera_ws.update_prefs(fake_client, entity_id="camera.hallway",
                                        preload_stream=False, orientation=6)
        assert fake_client.ws_calls[-1]["type"] == "camera/update_prefs"
        assert fake_client.ws_calls[-1]["payload"]["preload_stream"] is False
        assert fake_client.ws_calls[-1]["payload"]["orientation"] == 6
        assert result == {"preload_stream": False, "orientation": 6}

    def test_update_prefs_bad_entity_id(self, fake_client):
        """Test update_prefs() rejects non-camera entity_id."""
        with pytest.raises(ValueError, match="expected camera.* entity_id"):
            camera_ws.update_prefs(fake_client, entity_id="binary_sensor.motion",
                                   preload_stream=True)

    def test_update_prefs_no_params(self, fake_client):
        """Test update_prefs() requires at least one param."""
        with pytest.raises(ValueError,
                           match="at least one of preload_stream/orientation must be set"):
            camera_ws.update_prefs(fake_client, entity_id="camera.test")

    def test_update_prefs_orientation_too_low(self, fake_client):
        """Test update_prefs() rejects orientation < 1."""
        with pytest.raises(ValueError, match="orientation must be an integer in range 1..8"):
            camera_ws.update_prefs(fake_client, entity_id="camera.test",
                                   orientation=0)

    def test_update_prefs_orientation_too_high(self, fake_client):
        """Test update_prefs() rejects orientation > 8."""
        with pytest.raises(ValueError, match="orientation must be an integer in range 1..8"):
            camera_ws.update_prefs(fake_client, entity_id="camera.test",
                                   orientation=9)

    def test_update_prefs_orientation_not_int(self, fake_client):
        """Test update_prefs() rejects non-integer orientation."""
        with pytest.raises(ValueError, match="orientation must be an integer in range 1..8"):
            camera_ws.update_prefs(fake_client, entity_id="camera.test",
                                   orientation="5")

    # ────────────────────────────────────────────────────────── webrtc_get_client_config

    def test_webrtc_get_client_config_happy_path(self, fake_client):
        """Test webrtc_get_client_config() sends correct WS message."""
        fake_client.set_ws("camera/webrtc/get_client_config",
                           {"ice_servers": [{"urls": ["stun:stun.l.google.com:19302"]}]})
        result = camera_ws.webrtc_get_client_config(fake_client,
                                                     entity_id="camera.driveway")
        assert fake_client.ws_calls[-1]["type"] == "camera/webrtc/get_client_config"
        assert fake_client.ws_calls[-1]["payload"]["entity_id"] == "camera.driveway"
        assert "ice_servers" in result

    def test_webrtc_get_client_config_bad_entity_id(self, fake_client):
        """Test webrtc_get_client_config() rejects non-camera entity_id."""
        with pytest.raises(ValueError, match="expected camera.* entity_id"):
            camera_ws.webrtc_get_client_config(fake_client, entity_id="climate.test")

    # ────────────────────────────────────────────────────────── webrtc_offer

    def test_webrtc_offer_happy_path(self, fake_client):
        """Test webrtc_offer() sends correct WS message."""
        offer_sdp = "v=0\no=- 123 456 IN IP4 127.0.0.1\n..."
        fake_client.set_ws("camera/webrtc/offer", {"session_id": "abc123"})
        result = camera_ws.webrtc_offer(fake_client, entity_id="camera.patio",
                                        offer=offer_sdp)
        assert fake_client.ws_calls[-1]["type"] == "camera/webrtc/offer"
        assert fake_client.ws_calls[-1]["payload"]["entity_id"] == "camera.patio"
        assert fake_client.ws_calls[-1]["payload"]["offer"] == offer_sdp
        assert result == {"session_id": "abc123"}

    def test_webrtc_offer_bad_entity_id(self, fake_client):
        """Test webrtc_offer() rejects non-camera entity_id."""
        with pytest.raises(ValueError, match="expected camera.* entity_id"):
            camera_ws.webrtc_offer(fake_client, entity_id="media_player.living_room",
                                   offer="v=0\n...")

    def test_webrtc_offer_empty_offer(self, fake_client):
        """Test webrtc_offer() rejects empty offer string."""
        with pytest.raises(ValueError, match="offer must be a non-empty string"):
            camera_ws.webrtc_offer(fake_client, entity_id="camera.test", offer="")

    def test_webrtc_offer_none_offer(self, fake_client):
        """Test webrtc_offer() rejects None offer."""
        with pytest.raises(ValueError, match="offer must be a non-empty string"):
            camera_ws.webrtc_offer(fake_client, entity_id="camera.test", offer=None)

    def test_webrtc_offer_non_string_offer(self, fake_client):
        """Test webrtc_offer() rejects non-string offer."""
        with pytest.raises(ValueError, match="offer must be a non-empty string"):
            camera_ws.webrtc_offer(fake_client, entity_id="camera.test",
                                   offer={"v": "0"})

    # ────────────────────────────────────────────────────────── webrtc_candidate

    def test_webrtc_candidate_happy_path(self, fake_client):
        """Test webrtc_candidate() sends correct WS message."""
        candidate_dict = {
            "candidate": "candidate:123 1 udp 2130706431 192.168.1.1 54321 typ host",
            "sdpMLineIndex": 0
        }
        fake_client.set_ws("camera/webrtc/candidate", {})
        result = camera_ws.webrtc_candidate(fake_client, session_id="xyz789",
                                            candidate=candidate_dict)
        assert fake_client.ws_calls[-1]["type"] == "camera/webrtc/candidate"
        assert fake_client.ws_calls[-1]["payload"]["session_id"] == "xyz789"
        assert fake_client.ws_calls[-1]["payload"]["candidate"] == candidate_dict
        assert result == {}

    def test_webrtc_candidate_empty_session_id(self, fake_client):
        """Test webrtc_candidate() rejects empty session_id."""
        with pytest.raises(ValueError, match="session_id must be a non-empty string"):
            camera_ws.webrtc_candidate(fake_client, session_id="",
                                       candidate={"candidate": "..."})

    def test_webrtc_candidate_none_session_id(self, fake_client):
        """Test webrtc_candidate() rejects None session_id."""
        with pytest.raises(ValueError, match="session_id must be a non-empty string"):
            camera_ws.webrtc_candidate(fake_client, session_id=None,
                                       candidate={"candidate": "..."})

    def test_webrtc_candidate_non_string_session_id(self, fake_client):
        """Test webrtc_candidate() rejects non-string session_id."""
        with pytest.raises(ValueError, match="session_id must be a non-empty string"):
            camera_ws.webrtc_candidate(fake_client, session_id=123,
                                       candidate={"candidate": "..."})

    def test_webrtc_candidate_empty_candidate_dict(self, fake_client):
        """Test webrtc_candidate() rejects empty candidate dict."""
        with pytest.raises(ValueError, match="candidate must be a non-empty dict"):
            camera_ws.webrtc_candidate(fake_client, session_id="valid_id",
                                       candidate={})

    def test_webrtc_candidate_none_candidate(self, fake_client):
        """Test webrtc_candidate() rejects None candidate."""
        with pytest.raises(ValueError, match="candidate must be a non-empty dict"):
            camera_ws.webrtc_candidate(fake_client, session_id="valid_id",
                                       candidate=None)

    def test_webrtc_candidate_non_dict_candidate(self, fake_client):
        """Test webrtc_candidate() rejects non-dict candidate."""
        with pytest.raises(ValueError, match="candidate must be a non-empty dict"):
            camera_ws.webrtc_candidate(fake_client, session_id="valid_id",
                                       candidate="candidate_string")
