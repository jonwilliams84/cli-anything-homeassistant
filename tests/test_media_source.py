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


class TestSearchMedia:
    # ────────────────────────────────────────────────────────── search_media

    def test_search_media_sends_query_and_scope(self, fake_client):
        """search_media passes the query and scope as HA expects them."""
        fake_client.set_ws(
            "media_source/search_media",
            {"result": {"result": [{"title": "Track One"}]}},
        )
        out = media_source.search_media(
            fake_client,
            query="track one",
            media_content_id="media-source://media_source",
        )
        assert fake_client.ws_calls[-1] == {
            "type": "media_source/search_media",
            "payload": {
                "search_query": "track one",
                "media_content_id": "media-source://media_source",
            },
        }
        assert out["count"] == 1
        assert out["results"][0]["title"] == "Track One"
        assert out["query"] == "track one"
        assert out["scope"] == "media-source://media_source"
        assert out["filter_classes"] is None

    def test_search_media_flat_result_list(self, fake_client):
        """A flat result list (not nested under result.result) still counts."""
        fake_client.set_ws("media_source/search_media", {"result": [{"title": "A"}]})
        out = media_source.search_media(fake_client, query="a")
        assert out["count"] == 1
        assert out["results"] == [{"title": "A"}]

    def test_search_media_filter_classes_forwarded(self, fake_client):
        """filter_classes rides the payload when given."""
        fake_client.set_ws("media_source/search_media", {"result": {"result": []}})
        out = media_source.search_media(
            fake_client, query="x", filter_classes=["music"]
        )
        assert fake_client.ws_calls[-1]["payload"]["filter_classes"] == ["music"]
        assert out["filter_classes"] == ["music"]
        assert out["count"] == 0

    def test_search_media_empty_query_rejected(self, fake_client):
        with pytest.raises(ValueError, match="query is required"):
            media_source.search_media(fake_client, query="")

    def test_search_media_not_supported_names_the_scope(self, fake_client):
        """HA's two-word `search_not_supported` error is re-raised with a fix."""
        fake_client.set_ws_error(
            "media_source/search_media",
            "search_not_supported",
            "Search not supported",
        )
        with pytest.raises(ValueError, match="media-source://frigate does not support"):
            media_source.search_media(
                fake_client, query="q", media_content_id="media-source://frigate"
            )

    def test_search_media_root_scope_suggests_a_working_scope(self, fake_client):
        fake_client.set_ws_error(
            "media_source/search_media", "search_not_supported", "Search not supported"
        )
        with pytest.raises(ValueError, match="the media-source root does not support"):
            media_source.search_media(fake_client, query="q")

    def test_search_media_other_errors_pass_through(self, fake_client):
        """An unrelated WS failure is not rewritten."""
        fake_client.set_ws_error(
            "media_source/search_media", "search_media_failed", "source tried"
        )
        with pytest.raises(Exception, match="search_media_failed"):
            media_source.search_media(fake_client, query="q")

    def test_search_media_none_response_counts_zero(self, fake_client):
        """A None/empty answer is an empty result, not a crash."""
        fake_client.set_ws("media_source/search_media", None)
        out = media_source.search_media(fake_client, query="q")
        assert out["count"] == 0
        assert out["results"] == []


class TestPlayerSearch:
    # ────────────────────────────────────────────────────────── player_search

    def test_player_search_basic(self, fake_client):
        fake_client.set_ws(
            "media_player/search_media", {"result": {"result": [{"title": "Song"}]}}
        )
        out = media_source.player_search(
            fake_client, entity_id="media_player.speaker", query="song"
        )
        assert fake_client.ws_calls[-1] == {
            "type": "media_player/search_media",
            "payload": {"entity_id": "media_player.speaker", "search_query": "song"},
        }
        assert out["count"] == 1
        assert out["entity_id"] == "media_player.speaker"
        assert out["raw"] == {"result": {"result": [{"title": "Song"}]}}

    def test_player_search_flat_list_result(self, fake_client):
        fake_client.set_ws("media_player/search_media", {"result": [{"title": "S"}]})
        out = media_source.player_search(
            fake_client, entity_id="media_player.speaker", query="s"
        )
        assert out["count"] == 1

    def test_player_search_content_pair_forwarded(self, fake_client):
        """media_content_id and type are sent together, per HA's validator."""
        fake_client.set_ws("media_player/search_media", {"result": []})
        media_source.player_search(
            fake_client,
            entity_id="media_player.speaker",
            query="s",
            media_content_id="spotify:playlist",
            media_content_type="playlist",
        )
        assert fake_client.ws_calls[-1]["payload"] == {
            "entity_id": "media_player.speaker",
            "search_query": "s",
            "media_content_id": "spotify:playlist",
            "media_content_type": "playlist",
        }

    def test_player_search_rejects_non_player_entity(self, fake_client):
        with pytest.raises(ValueError, match="expected media_player"):
            media_source.player_search(
                fake_client, entity_id="light bulb", query="q"
            )

    def test_player_search_empty_query_rejected(self, fake_client):
        with pytest.raises(ValueError, match="query is required"):
            media_source.player_search(
                fake_client, entity_id="media_player.speaker", query=""
            )

    def test_player_search_half_content_pair_rejected(self, fake_client):
        """One of the pair alone is rejected client-side (HA is strict too)."""
        with pytest.raises(ValueError, match="mutually inclusive"):
            media_source.player_search(
                fake_client,
                entity_id="media_player.speaker",
                query="q",
                media_content_id="spotify:playlist",
            )
        with pytest.raises(ValueError, match="mutually inclusive"):
            media_source.player_search(
                fake_client,
                entity_id="media_player.speaker",
                query="s",
                media_content_type="playlist",
            )
