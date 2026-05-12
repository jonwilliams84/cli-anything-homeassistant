"""Unit tests for cli_anything.homeassistant.core.media_source — no real HA required."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import media_source


class TestMediaSource:
    # ────────────────────────────────────────────────────────── browse_media

    def test_browse_media_root(self, fake_client):
        """browse_media at root sends WS with empty payload."""
        response = {
            "domain": "media_source",
            "identifier": "",
            "media_class": "directory",
            "media_content_type": None,
            "title": "My media",
            "can_play": False,
            "can_expand": True,
            "children": [],
        }
        fake_client.set_ws("media_source/browse_media", response)
        result = media_source.browse_media(fake_client)
        assert fake_client.ws_calls[-1] == {
            "type": "media_source/browse_media",
            "payload": {},
        }
        assert result["title"] == "My media"

    def test_browse_media_with_content_id(self, fake_client):
        """browse_media with content_id sends that in the payload."""
        response = {
            "domain": "media_source",
            "identifier": "folder/subfolder",
            "media_class": "directory",
            "media_content_type": None,
            "title": "Subfolder",
            "can_play": False,
            "can_expand": True,
            "children": [],
        }
        fake_client.set_ws("media_source/browse_media", response)
        result = media_source.browse_media(fake_client, media_content_id="media_source://media_source/folder/subfolder")
        assert fake_client.ws_calls[-1] == {
            "type": "media_source/browse_media",
            "payload": {"media_content_id": "media_source://media_source/folder/subfolder"},
        }
        assert result["identifier"] == "folder/subfolder"

    def test_browse_media_returns_dict(self, fake_client):
        """browse_media returns the response dict as-is."""
        response = {
            "domain": "media_source",
            "identifier": "",
            "media_class": "directory",
            "children": [
                {
                    "domain": "media_source",
                    "identifier": "video.mp4",
                    "media_class": "video",
                    "media_content_type": "video/mp4",
                    "title": "Video File",
                    "can_play": True,
                    "can_expand": False,
                }
            ],
        }
        fake_client.set_ws("media_source/browse_media", response)
        result = media_source.browse_media(fake_client)
        assert isinstance(result, dict)
        assert len(result["children"]) == 1
        assert result["children"][0]["title"] == "Video File"

    # ────────────────────────────────────────────────────────── resolve_media

    def test_resolve_media(self, fake_client):
        """resolve_media sends correct WS with media_content_id."""
        response = {"url": "/media/video.mp4", "mime_type": "video/mp4"}
        fake_client.set_ws("media_source/resolve_media", response)
        result = media_source.resolve_media(
            fake_client, media_content_id="media_source://media_source/video.mp4"
        )
        assert fake_client.ws_calls[-1] == {
            "type": "media_source/resolve_media",
            "payload": {"media_content_id": "media_source://media_source/video.mp4"},
        }
        assert result["url"] == "/media/video.mp4"
        assert result["mime_type"] == "video/mp4"

    def test_resolve_media_returns_dict(self, fake_client):
        """resolve_media returns dict with url and mime_type."""
        response = {"url": "/media/audio.mp3", "mime_type": "audio/mpeg"}
        fake_client.set_ws("media_source/resolve_media", response)
        result = media_source.resolve_media(
            fake_client, media_content_id="media_source://media_source/audio.mp3"
        )
        assert isinstance(result, dict)
        assert "url" in result
        assert "mime_type" in result
        assert result["mime_type"] == "audio/mpeg"

    def test_resolve_media_empty_id(self, fake_client):
        with pytest.raises(ValueError, match="media_content_id must be a non-empty"):
            media_source.resolve_media(fake_client, media_content_id="")

    # ────────────────────────────────────────────────────────── local_source_remove

    def test_local_source_remove(self, fake_client):
        """local_source_remove sends correct WS with media_content_id."""
        fake_client.set_ws("media_source/local_source/remove", {})
        media_source.local_source_remove(
            fake_client, media_content_id="media_source://media_source/video.mp4"
        )
        assert fake_client.ws_calls[-1] == {
            "type": "media_source/local_source/remove",
            "payload": {"media_content_id": "media_source://media_source/video.mp4"},
        }

    def test_local_source_remove_empty_id(self, fake_client):
        with pytest.raises(ValueError, match="media_content_id must be a non-empty"):
            media_source.local_source_remove(fake_client, media_content_id="")
