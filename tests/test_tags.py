"""Unit tests for cli_anything.homeassistant.core.tags — no real HA required."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import tags


class TestListTags:
    def test_returns_list(self, fake_client):
        fake_client.set_ws("tag/list", [{"id": "1"}, {"id": "2"}])
        assert len(tags.list_tags(fake_client)) == 2

    def test_non_list_response_returns_empty(self, fake_client):
        fake_client.set_ws("tag/list", None)
        assert tags.list_tags(fake_client) == []

    def test_dict_response_returns_empty(self, fake_client):
        fake_client.set_ws("tag/list", {"not": "a list"})
        assert tags.list_tags(fake_client) == []


class TestFindTag:
    def test_find_by_id(self, fake_client):
        fake_client.set_ws("tag/list", [{"id": "abc", "name": "Front Door"}])
        result = tags.find_tag(fake_client, "abc")
        assert result is not None
        assert result["id"] == "abc"

    def test_find_by_tag_id(self, fake_client):
        """Some HA versions use 'tag_id' instead of 'id'."""
        fake_client.set_ws("tag/list", [{"tag_id": "nfc123", "name": "Badge"}])
        result = tags.find_tag(fake_client, "nfc123")
        assert result is not None
        assert result["tag_id"] == "nfc123"

    def test_find_by_name_case_insensitive(self, fake_client):
        fake_client.set_ws("tag/list", [{"id": "1", "name": "Front Door"}])
        result = tags.find_tag(fake_client, "front door")
        assert result is not None
        assert result["id"] == "1"

    def test_find_by_name_exact_case(self, fake_client):
        fake_client.set_ws("tag/list", [{"id": "1", "name": "Front Door"}])
        result = tags.find_tag(fake_client, "Front Door")
        assert result is not None

    def test_not_found_returns_none(self, fake_client):
        fake_client.set_ws("tag/list", [{"id": "1", "name": "Foo"}])
        assert tags.find_tag(fake_client, "nonexistent") is None

    def test_empty_ident_returns_none(self, fake_client):
        fake_client.set_ws("tag/list", [{"id": "1"}])
        assert tags.find_tag(fake_client, "") is None

    def test_tag_with_no_name_does_not_crash(self, fake_client):
        fake_client.set_ws("tag/list", [{"id": "1", "name": None}])
        assert tags.find_tag(fake_client, "anything") is None


class TestCreate:
    def test_minimal_create(self, fake_client):
        fake_client.set_ws("tag/create", {"tag_id": "nfc1"})
        result = tags.create(fake_client, "nfc1")
        assert result == {"tag_id": "nfc1"}
        assert fake_client.ws_calls[-1]["payload"] == {"tag_id": "nfc1"}

    def test_create_with_name_and_description(self, fake_client):
        fake_client.set_ws("tag/create", {"tag_id": "nfc1"})
        tags.create(fake_client, "nfc1", name="Badge", description="Front door")
        assert fake_client.ws_calls[-1]["payload"] == {
            "tag_id": "nfc1", "name": "Badge", "description": "Front door",
        }

    def test_empty_tag_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="tag_id is required"):
            tags.create(fake_client, "")

    def test_none_response_returns_empty_dict(self, fake_client):
        fake_client.set_ws("tag/create", None)
        assert tags.create(fake_client, "nfc1") == {}


class TestUpdate:
    def test_update_with_name(self, fake_client):
        fake_client.set_ws("tag/update", {"ok": True})
        tags.update(fake_client, "nfc1", name="New Name")
        assert fake_client.ws_calls[-1]["payload"] == {
            "tag_id": "nfc1", "name": "New Name",
        }

    def test_update_with_description_only(self, fake_client):
        fake_client.set_ws("tag/update", {"ok": True})
        tags.update(fake_client, "nfc1", description="Updated desc")
        assert "name" not in fake_client.ws_calls[-1]["payload"]
        assert fake_client.ws_calls[-1]["payload"]["description"] == "Updated desc"

    def test_empty_tag_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="tag_id is required"):
            tags.update(fake_client, "")

    def test_none_response_returns_empty_dict(self, fake_client):
        fake_client.set_ws("tag/update", None)
        assert tags.update(fake_client, "nfc1") == {}


class TestDelete:
    def test_delete_sends_payload(self, fake_client):
        fake_client.set_ws("tag/delete", {"ok": True})
        result = tags.delete(fake_client, "nfc1")
        assert result == {"ok": True}
        assert fake_client.ws_calls[-1]["payload"] == {"tag_id": "nfc1"}

    def test_empty_tag_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="tag_id is required"):
            tags.delete(fake_client, "")

    def test_none_response_returns_empty_dict(self, fake_client):
        fake_client.set_ws("tag/delete", None)
        assert tags.delete(fake_client, "nfc1") == {}
