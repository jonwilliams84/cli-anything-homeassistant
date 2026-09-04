"""Unit tests for `core/media_proxy` — the binary media proxy endpoints.

Covers `camera snapshot|capture|proxy-url`, `image capture` and
`media-player artwork`: URL construction, the query parameters HA actually
reads, the signed-vs-bearer split, multipart frame parsing, duplicate
collapsing, and the bodyless failure codes translated into sentences.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from cli_anything.homeassistant.core import media_proxy


# ───────────────────────────────────────────────────────────────── helpers


def _resp(*, ok=True, status=200, payload=b"JPEG-DATA", content_type="image/jpeg"):
    class _R:
        def __init__(self):
            self.ok = ok
            self.status_code = status
            self.content = payload
            self.text = "" if ok else ""
            self.headers = {"Content-Type": content_type}
            self.closed = False

        def iter_content(self, chunk_size=8192):
            for i in range(0, len(payload), chunk_size):
                yield payload[i : i + chunk_size]

        def close(self):
            self.closed = True

    return _R()


def _client(*, response=None, signed_path="/api/camera_proxy/camera.front?authSig=tok"):
    client = MagicMock()
    client.base_url = "http://localhost:8123"
    client.timeout = 30
    session = MagicMock()
    session.headers = {"Authorization": "Bearer tok", "Content-Type": "application/json"}
    session.get = MagicMock(return_value=response if response is not None else _resp())
    client.session = session
    client.ws_call = MagicMock(return_value={"path": signed_path} if signed_path else {})
    return client


# ──────────────────────────────────────────────────────── camera snapshot


class TestCameraSnapshot:

    def test_writes_bytes_and_reports_content_type(self, tmp_path):
        client = _client()
        out = str(tmp_path / "front.jpg")
        result = media_proxy.camera_snapshot(client, entity_id="camera.front", output_path=out)
        assert os.path.exists(out)
        with open(out, "rb") as fh:
            assert fh.read() == b"JPEG-DATA"
        assert result["bytes"] == len(b"JPEG-DATA")
        assert result["content_type"] == "image/jpeg"
        assert result["output_path"] == os.path.abspath(out)

    def test_hits_the_camera_proxy_view(self, tmp_path):
        client = _client()
        media_proxy.camera_snapshot(
            client, entity_id="camera.front", output_path=str(tmp_path / "a.jpg")
        )
        url = client.session.get.call_args.args[0]
        assert url == "http://localhost:8123/api/camera_proxy/camera.front"
        # No resize asked for -> no query parameters at all.
        assert client.session.get.call_args.kwargs["params"] is None

    def test_width_and_height_become_query_params(self, tmp_path):
        client = _client()
        result = media_proxy.camera_snapshot(
            client,
            entity_id="camera.front",
            output_path=str(tmp_path / "a.jpg"),
            width=320,
            height=240,
        )
        assert client.session.get.call_args.kwargs["params"] == {"width": 320, "height": 240}
        assert result["resized"] is True

    def test_resized_is_false_for_a_png_camera(self, tmp_path):
        """HA only rescales JPEG — a PNG comes back full size with NO error."""
        client = _client(response=_resp(content_type="image/png", payload=b"PNG"))
        result = media_proxy.camera_snapshot(
            client,
            entity_id="camera.front",
            output_path=str(tmp_path / "a.png"),
            width=320,
            height=240,
        )
        assert result["resized"] is False

    def test_width_without_height_is_refused(self, tmp_path):
        client = _client()
        with pytest.raises(ValueError, match="must be given together"):
            media_proxy.camera_snapshot(
                client,
                entity_id="camera.front",
                output_path=str(tmp_path / "a.jpg"),
                width=320,
            )

    def test_height_without_width_is_refused(self, tmp_path):
        with pytest.raises(ValueError, match="must be given together"):
            media_proxy.camera_snapshot(
                _client(),
                entity_id="camera.front",
                output_path=str(tmp_path / "a.jpg"),
                height=240,
            )

    @pytest.mark.parametrize("bad", [0, -1])
    def test_non_positive_dimensions_refused(self, tmp_path, bad):
        with pytest.raises(ValueError, match="positive integer"):
            media_proxy.camera_snapshot(
                _client(),
                entity_id="camera.front",
                output_path=str(tmp_path / "a.jpg"),
                width=bad,
                height=bad,
            )

    def test_rejects_non_camera_entity(self, tmp_path):
        with pytest.raises(ValueError, match="not a camera"):
            media_proxy.camera_snapshot(
                _client(), entity_id="image.doorbell", output_path=str(tmp_path / "a.jpg")
            )

    def test_requires_entity_id(self, tmp_path):
        with pytest.raises(ValueError, match="entity_id is required"):
            media_proxy.camera_snapshot(
                _client(), entity_id="", output_path=str(tmp_path / "a.jpg")
            )

    def test_refuses_existing_file(self, tmp_path):
        dest = tmp_path / "a.jpg"
        dest.write_bytes(b"old")
        with pytest.raises(FileExistsError):
            media_proxy.camera_snapshot(
                _client(), entity_id="camera.front", output_path=str(dest)
            )

    def test_overwrite_replaces(self, tmp_path):
        dest = tmp_path / "a.jpg"
        dest.write_bytes(b"old")
        media_proxy.camera_snapshot(
            _client(), entity_id="camera.front", output_path=str(dest), overwrite=True
        )
        assert dest.read_bytes() == b"JPEG-DATA"

    def test_no_session_is_explained(self, tmp_path):
        client = MagicMock()
        client.session = None
        with pytest.raises(ValueError, match="HTTP session"):
            media_proxy.camera_snapshot(
                client, entity_id="camera.front", output_path=str(tmp_path / "a.jpg")
            )

    def test_signed_strips_the_authorization_header(self, tmp_path):
        """A signed request carrying a bearer header turns a signature
        failure (403) into a token failure (401) — so the header must go."""
        client = _client()
        media_proxy.camera_snapshot(
            client,
            entity_id="camera.front",
            output_path=str(tmp_path / "a.jpg"),
            signed=True,
            expires=120,
        )
        client.ws_call.assert_called_once()
        headers = client.session.get.call_args.kwargs["headers"]
        assert "Authorization" not in headers
        assert "Content-Type" in headers  # other headers survive
        assert client.session.get.call_args.args[0].endswith("authSig=tok")

    def test_signed_failure_is_named(self, tmp_path):
        client = _client(signed_path=None)
        with pytest.raises(RuntimeError, match="sign_path"):
            media_proxy.camera_snapshot(
                client,
                entity_id="camera.front",
                output_path=str(tmp_path / "a.jpg"),
                signed=True,
            )


# ────────────────────────────────────────────────── bodyless status codes


class TestStatusTranslation:
    """Every failure of these views is a bare code with an empty body."""

    def _fails_with(self, status, tmp_path, **kwargs):
        client = _client(response=_resp(ok=False, status=status, payload=b""))
        with pytest.raises(RuntimeError) as excinfo:
            media_proxy.camera_snapshot(
                client,
                entity_id="camera.front",
                output_path=str(tmp_path / "a.jpg"),
                **kwargs,
            )
        return str(excinfo.value)

    def test_503_names_the_camera_being_off(self, tmp_path):
        msg = self._fails_with(503, tmp_path)
        assert "503" in msg
        assert "is OFF" in msg
        assert "camera turn-on camera.front" in msg

    def test_404_names_the_missing_entity(self, tmp_path):
        msg = self._fails_with(404, tmp_path)
        assert "no such camera entity" in msg
        assert "camera.front" in msg

    def test_403_explains_that_no_credentials_arrived(self, tmp_path):
        msg = self._fails_with(403, tmp_path)
        assert "no credentials reached" in msg
        assert "403" in msg

    def test_401_direct_points_at_the_token(self, tmp_path):
        msg = self._fails_with(401, tmp_path)
        assert "bearer token" in msg
        assert "HASS_TOKEN" in msg

    def test_401_signed_points_at_expiry(self, tmp_path):
        msg = self._fails_with(401, tmp_path, signed=True)
        assert "expired" in msg
        assert "--expires" in msg

    def test_500_names_both_causes(self, tmp_path):
        msg = self._fails_with(500, tmp_path)
        assert "could not produce an image" in msg
        assert str(media_proxy.CAMERA_IMAGE_TIMEOUT) in msg

    def test_no_file_is_written_on_failure(self, tmp_path):
        dest = tmp_path / "a.jpg"
        client = _client(response=_resp(ok=False, status=503, payload=b""))
        with pytest.raises(RuntimeError):
            media_proxy.camera_snapshot(
                client, entity_id="camera.front", output_path=str(dest)
            )
        assert not dest.exists()

    def test_502_on_a_stream_suggests_the_stills_fallback(self, tmp_path):
        client = _client(response=_resp(ok=False, status=502, payload=b""))
        with pytest.raises(RuntimeError, match="no MJPEG stream"):
            media_proxy.camera_capture(
                client, entity_id="camera.front", output_dir=str(tmp_path), frames=1
            )

    def test_400_on_a_stream_names_the_interval_floor(self, tmp_path):
        client = _client(response=_resp(ok=False, status=400, payload=b""))
        with pytest.raises(RuntimeError, match="stream interval"):
            media_proxy.camera_capture(
                client, entity_id="camera.front", output_dir=str(tmp_path), frames=1
            )


# ─────────────────────────────────────────────────────── capture validation


class TestCaptureValidation:

    def test_interval_below_the_floor_is_refused_locally(self, tmp_path):
        with pytest.raises(ValueError, match="interval must be >="):
            media_proxy.camera_capture(
                _client(),
                entity_id="camera.front",
                output_dir=str(tmp_path),
                interval=0.4,
            )

    def test_the_floor_itself_is_accepted(self, tmp_path):
        """HA's check is `interval < MIN_STREAM_INTERVAL` even though its own
        error message says `must be > 0.5`. Match the code, not the sentence."""
        media_proxy._validate_capture(1, 30.0, media_proxy.MIN_STREAM_INTERVAL)

    def test_timeout_that_cannot_fit_the_frames_is_refused(self, tmp_path):
        with pytest.raises(ValueError, match="cannot capture"):
            media_proxy.camera_capture(
                _client(),
                entity_id="camera.front",
                output_dir=str(tmp_path),
                frames=10,
                interval=1.0,
                timeout=3.0,
            )

    @pytest.mark.parametrize("frames", [0, -3])
    def test_frames_must_be_positive(self, tmp_path, frames):
        with pytest.raises(ValueError, match="frames must be >= 1"):
            media_proxy.camera_capture(
                _client(), entity_id="camera.front", output_dir=str(tmp_path), frames=frames
            )

    def test_timeout_must_be_positive(self, tmp_path):
        with pytest.raises(ValueError, match="timeout must be > 0"):
            media_proxy.camera_capture(
                _client(), entity_id="camera.front", output_dir=str(tmp_path), timeout=0
            )

    def test_capture_rejects_wrong_domain(self, tmp_path):
        with pytest.raises(ValueError, match="not a camera"):
            media_proxy.camera_capture(
                _client(), entity_id="image.x", output_dir=str(tmp_path)
            )

    def test_image_capture_rejects_wrong_domain(self, tmp_path):
        with pytest.raises(ValueError, match="not an image"):
            media_proxy.image_capture(
                _client(), entity_id="camera.front", output_dir=str(tmp_path)
            )

    def test_output_dir_is_required(self):
        with pytest.raises(ValueError, match="output_dir is required"):
            media_proxy.camera_capture(_client(), entity_id="camera.front", output_dir="")


# ─────────────────────────────────────────────────────── media player art


class TestMediaPlayerArtwork:

    def test_now_playing_path(self, tmp_path):
        client = _client()
        result = media_proxy.media_player_artwork(
            client, entity_id="media_player.lounge", output_path=str(tmp_path / "art.jpg")
        )
        url = client.session.get.call_args.args[0]
        assert url == "http://localhost:8123/api/media_player_proxy/media_player.lounge"
        assert result["browse_media"] is False
        assert result["bytes"] == len(b"JPEG-DATA")

    def test_browse_media_path_is_appended_verbatim(self, tmp_path):
        """`media_content_id:.+` — HA's own regex allows slashes and braces,
        so the id must NOT be escaped away."""
        client = _client()
        result = media_proxy.media_player_artwork(
            client,
            entity_id="media_player.lounge",
            output_path=str(tmp_path / "art.jpg"),
            media_content_type="album",
            media_content_id="library/albums/17",
        )
        url = client.session.get.call_args.args[0]
        assert url.endswith(
            "/api/media_player_proxy/media_player.lounge/browse_media/album/library/albums/17"
        )
        assert result["browse_media"] is True
        assert result["media_content_type"] == "album"

    def test_media_image_id_is_a_query_param(self, tmp_path):
        client = _client()
        media_proxy.media_player_artwork(
            client,
            entity_id="media_player.lounge",
            output_path=str(tmp_path / "art.jpg"),
            media_content_type="album",
            media_content_id="x",
            media_image_id="thumb2",
        )
        assert client.session.get.call_args.kwargs["params"] == {"media_image_id": "thumb2"}

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"media_content_type": "album"},
            {"media_content_id": "library/1"},
        ],
    )
    def test_content_pair_must_be_complete(self, tmp_path, kwargs):
        with pytest.raises(ValueError, match="must be given together"):
            media_proxy.media_player_artwork(
                _client(),
                entity_id="media_player.lounge",
                output_path=str(tmp_path / "art.jpg"),
                **kwargs,
            )

    def test_rejects_wrong_domain(self, tmp_path):
        with pytest.raises(ValueError, match="not a media_player"):
            media_proxy.media_player_artwork(
                _client(), entity_id="camera.front", output_path=str(tmp_path / "a.jpg")
            )

    def test_missing_artwork_500_is_explained(self, tmp_path):
        client = _client(response=_resp(ok=False, status=500, payload=b""))
        with pytest.raises(RuntimeError) as excinfo:
            media_proxy.media_player_artwork(
                client, entity_id="media_player.lounge", output_path=str(tmp_path / "a.jpg")
            )
        assert "no artwork" in str(excinfo.value)

    def test_401_for_media_player_mentions_the_token(self, tmp_path):
        client = _client(response=_resp(ok=False, status=401, payload=b""))
        with pytest.raises(RuntimeError, match="bearer token"):
            media_proxy.media_player_artwork(
                client, entity_id="media_player.lounge", output_path=str(tmp_path / "a.jpg")
            )


# ──────────────────────────────────────────────────────────────── proxy url


class TestProxyUrl:

    def test_unsigned_still(self):
        client = _client()
        result = media_proxy.proxy_url(client, entity_id="camera.front", signed=False)
        assert result["url"] == "http://localhost:8123/api/camera_proxy/camera.front"
        assert result["signed"] is False
        assert result["expires"] is None
        assert result["stream"] is False
        client.ws_call.assert_not_called()

    def test_unsigned_stream_switches_the_view(self):
        result = media_proxy.proxy_url(
            _client(), entity_id="camera.front", signed=False, stream=True
        )
        assert result["path"] == "/api/camera_proxy_stream/camera.front"
        assert result["stream"] is True

    def test_signed_uses_sign_path(self):
        client = _client()
        result = media_proxy.proxy_url(client, entity_id="camera.front", expires=90)
        client.ws_call.assert_called_once()
        assert result["signed"] is True
        assert result["expires"] == 90
        assert "authSig=tok" in result["url"]

    def test_signed_falls_back_to_the_plain_path(self):
        client = _client(signed_path=None)
        result = media_proxy.proxy_url(client, entity_id="camera.front")
        assert result["path"] == "/api/camera_proxy/camera.front"

    def test_rejects_wrong_domain(self):
        with pytest.raises(ValueError, match="not a camera"):
            media_proxy.proxy_url(_client(), entity_id="image.x")


# ───────────────────────────────────────────────────────── header parsing


class TestPartHeaders:

    def test_reads_type_and_length(self):
        blob = b"--frameboundary\r\nContent-Type: image/jpeg\r\nContent-Length: 9"
        assert media_proxy._parse_part_headers(blob) == ("image/jpeg", 9)

    def test_is_case_insensitive(self):
        blob = b"content-type: image/png\r\ncontent-length: 3"
        assert media_proxy._parse_part_headers(blob) == ("image/png", 3)

    def test_missing_length_is_none(self):
        assert media_proxy._parse_part_headers(b"Content-Type: image/jpeg") == (
            "image/jpeg",
            None,
        )

    def test_non_numeric_length_is_none(self):
        assert media_proxy._parse_part_headers(b"Content-Length: abc")[1] is None
