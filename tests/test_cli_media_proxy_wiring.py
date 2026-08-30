"""CLI wiring for the media-proxy refine pass.

Covers `camera snapshot|capture|proxy-url`, `image capture` and
`media-player artwork`: that every option reaches the core function, that
`--json` stays parseable, and that the client-side refusals arrive as a clean
`error:` line rather than a traceback.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from cli_anything.homeassistant import homeassistant_cli as cli_mod


def _resp(payload=b"JPEG-DATA", content_type="image/jpeg", *, ok=True, status=200):
    class _R:
        def __init__(self):
            self.ok = ok
            self.status_code = status
            self.content = payload
            self.text = ""
            self.headers = {"Content-Type": content_type}

        def iter_content(self, chunk_size=8192):
            yield payload

        def close(self):
            pass

    return _R()


@pytest.fixture
def media_client():
    client = MagicMock()
    client.base_url = "http://localhost:8123"
    client.timeout = 30
    session = MagicMock()
    session.headers = {"Authorization": "Bearer tok"}
    session.get = MagicMock(return_value=_resp())
    client.session = session
    client.ws_call = MagicMock(return_value={"path": "/api/camera_proxy/camera.front?authSig=s"})
    return client


@pytest.fixture
def runner(monkeypatch, media_client):
    monkeypatch.setattr(cli_mod, "make_client", lambda ctx: media_client)
    return CliRunner()


def _invoke(runner, *args, json_out=True):
    full = (["--json"] if json_out else []) + list(args)
    return runner.invoke(
        cli_mod.cli,
        full,
        obj={
            "url": "http://x", "token": "t", "verify_ssl": False,
            "timeout": 5, "as_json": json_out, "config_path": None,
        },
    )


# ────────────────────────────────────────────────────────── camera snapshot


def test_camera_snapshot_writes_and_reports_json(runner, media_client, tmp_path):
    dest = tmp_path / "front.jpg"
    result = _invoke(runner, "camera", "snapshot", "camera.front", str(dest))
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["entity_id"] == "camera.front"
    assert payload["bytes"] == len(b"JPEG-DATA")
    assert payload["output_path"] == os.path.abspath(str(dest))
    assert dest.read_bytes() == b"JPEG-DATA"


def test_camera_snapshot_passes_dimensions(runner, media_client, tmp_path):
    result = _invoke(
        runner, "camera", "snapshot", "camera.front", str(tmp_path / "a.jpg"),
        "--width", "640", "--height", "480",
    )
    assert result.exit_code == 0, result.output
    assert media_client.session.get.call_args.kwargs["params"] == {"width": 640, "height": 480}
    assert json.loads(result.output)["resized"] is True


def test_camera_snapshot_width_alone_is_a_clean_error(runner, tmp_path):
    """Not a traceback — the refusal has to read like an answer."""
    result = _invoke(
        runner, "camera", "snapshot", "camera.front", str(tmp_path / "a.jpg"), "--width", "640"
    )
    assert result.exit_code != 0
    assert "must be given together" in result.output
    assert "Traceback" not in result.output


def test_camera_snapshot_signed_flag_reaches_sign_path(runner, media_client, tmp_path):
    result = _invoke(
        runner, "camera", "snapshot", "camera.front", str(tmp_path / "a.jpg"),
        "--signed", "--expires", "90",
    )
    assert result.exit_code == 0, result.output
    media_client.ws_call.assert_called_once()
    assert "Authorization" not in media_client.session.get.call_args.kwargs["headers"]


def test_camera_snapshot_human_output_is_not_json(runner, tmp_path):
    result = _invoke(runner, "camera", "snapshot", "camera.front", str(tmp_path / "a.jpg"),
                     json_out=False)
    assert result.exit_code == 0, result.output
    assert "entity_id: camera.front" in result.output


def test_camera_snapshot_off_camera_names_the_remedy(monkeypatch, tmp_path):
    client = MagicMock()
    client.base_url = "http://localhost:8123"
    client.timeout = 30
    client.session = MagicMock()
    client.session.headers = {}
    client.session.get = MagicMock(return_value=_resp(b"", ok=False, status=503))
    monkeypatch.setattr(cli_mod, "make_client", lambda ctx: client)
    result = _invoke(CliRunner(), "camera", "snapshot", "camera.front", str(tmp_path / "a.jpg"))
    assert result.exit_code != 0
    assert "camera turn-on camera.front" in str(result.output) + str(result.exception)


# ─────────────────────────────────────────────────────────── camera capture


def test_camera_capture_rejects_a_sub_floor_interval(runner, tmp_path):
    result = _invoke(
        runner, "camera", "capture", "camera.front", str(tmp_path / "d"), "--interval", "0.1"
    )
    assert result.exit_code != 0
    assert "interval must be >=" in result.output


def test_camera_capture_rejects_an_impossible_timeout(runner, tmp_path):
    result = _invoke(
        runner, "camera", "capture", "camera.front", str(tmp_path / "d"),
        "--frames", "20", "--interval", "1.0", "--timeout", "2",
    )
    assert result.exit_code != 0
    assert "cannot capture" in result.output


def test_camera_capture_forwards_every_option(monkeypatch, tmp_path):
    seen = {}

    def _fake(client, **kwargs):
        seen.update(kwargs)
        return {"frames": 1}

    monkeypatch.setattr(cli_mod, "make_client", lambda ctx: MagicMock())
    monkeypatch.setattr(cli_mod.media_proxy_core, "camera_capture", _fake)
    result = _invoke(
        CliRunner(), "camera", "capture", "camera.front", str(tmp_path / "d"),
        "--frames", "4", "--interval", "1.5", "--timeout", "45",
        "--prefix", "cam", "--overwrite", "--signed", "--expires", "60",
    )
    assert result.exit_code == 0, result.output
    assert seen == {
        "entity_id": "camera.front",
        "output_dir": str(tmp_path / "d"),
        "frames": 4,
        "interval": 1.5,
        "timeout": 45.0,
        "prefix": "cam",
        "overwrite": True,
        "signed": True,
        "expires": 60,
    }


# ───────────────────────────────────────────────────────────── camera proxy-url


def test_camera_proxy_url_unsigned(runner, media_client):
    result = _invoke(runner, "camera", "proxy-url", "camera.front", "--unsigned")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["url"] == "http://localhost:8123/api/camera_proxy/camera.front"
    assert payload["signed"] is False
    media_client.ws_call.assert_not_called()


def test_camera_proxy_url_stream_variant(runner):
    result = _invoke(runner, "camera", "proxy-url", "camera.front", "--unsigned", "--stream")
    assert json.loads(result.output)["path"] == "/api/camera_proxy_stream/camera.front"


def test_camera_proxy_url_is_signed_by_default(runner, media_client):
    result = _invoke(runner, "camera", "proxy-url", "camera.front")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["signed"] is True
    media_client.ws_call.assert_called_once()


# ───────────────────────────────────────────────────────────────── image capture


def test_image_capture_forwards_every_option(monkeypatch, tmp_path):
    seen = {}

    monkeypatch.setattr(cli_mod, "make_client", lambda ctx: MagicMock())
    monkeypatch.setattr(
        cli_mod.media_proxy_core, "image_capture",
        lambda client, **kw: (seen.update(kw), {"frames": 1})[1],
    )
    result = _invoke(
        CliRunner(), "image", "capture", "image.doorbell", str(tmp_path / "d"),
        "--frames", "2", "--timeout", "12", "--prefix", "img",
    )
    assert result.exit_code == 0, result.output
    assert seen["entity_id"] == "image.doorbell"
    assert seen["frames"] == 2
    assert seen["timeout"] == 12.0
    assert seen["prefix"] == "img"
    # The image stream has no interval — the option must not exist here.
    assert "interval" not in seen


def test_image_capture_has_no_interval_option(runner, tmp_path):
    result = _invoke(
        runner, "image", "capture", "image.doorbell", str(tmp_path / "d"), "--interval", "1.0"
    )
    assert result.exit_code != 0
    assert "no such option" in result.output.lower()


def test_image_capture_rejects_a_camera_entity(runner, tmp_path):
    result = _invoke(runner, "image", "capture", "camera.front", str(tmp_path / "d"))
    assert result.exit_code != 0
    assert "not an image" in result.output


# ──────────────────────────────────────────────────────── media-player artwork


def test_media_player_artwork_now_playing(runner, media_client, tmp_path):
    dest = tmp_path / "art.jpg"
    result = _invoke(runner, "media-player", "artwork", "media_player.lounge", str(dest))
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["browse_media"] is False
    assert dest.read_bytes() == b"JPEG-DATA"
    assert media_client.session.get.call_args.args[0].endswith(
        "/api/media_player_proxy/media_player.lounge"
    )


def test_media_player_artwork_browse_media(runner, media_client, tmp_path):
    result = _invoke(
        runner, "media-player", "artwork", "media_player.lounge", str(tmp_path / "art.jpg"),
        "--content-type", "album", "--content-id", "library/albums/17",
        "--image-id", "thumb",
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["browse_media"] is True
    assert media_client.session.get.call_args.args[0].endswith(
        "/browse_media/album/library/albums/17"
    )
    assert media_client.session.get.call_args.kwargs["params"] == {"media_image_id": "thumb"}


def test_media_player_artwork_half_a_pair_is_refused(runner, tmp_path):
    result = _invoke(
        runner, "media-player", "artwork", "media_player.lounge", str(tmp_path / "a.jpg"),
        "--content-type", "album",
    )
    assert result.exit_code != 0
    assert "must be given together" in result.output


def test_media_player_artwork_rejects_wrong_domain(runner, tmp_path):
    result = _invoke(runner, "media-player", "artwork", "camera.front", str(tmp_path / "a.jpg"))
    assert result.exit_code != 0
    assert "not a media_player" in result.output


# ────────────────────────────────────────────────────────────── help surfaces


@pytest.mark.parametrize(
    "args,needle",
    [
        (["camera", "snapshot", "--help"], "--width"),
        (["camera", "capture", "--help"], "--interval"),
        (["camera", "proxy-url", "--help"], "--signed"),
        (["image", "capture", "--help"], "--frames"),
        (["media-player", "artwork", "--help"], "--content-type"),
    ],
)
def test_help_is_registered(runner, args, needle):
    result = _invoke(runner, *args, json_out=False)
    assert result.exit_code == 0
    assert needle in result.output
