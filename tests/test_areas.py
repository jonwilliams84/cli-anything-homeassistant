"""Unit tests for cli_anything.homeassistant.core.areas — no real HA required."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import areas


class TestListAreas:
    def test_returns_list(self, fake_client):
        fake_client.set_ws("config/area_registry/list", [
            {"area_id": "a1", "name": "Kitchen"},
            {"area_id": "a2", "name": "Living Room"},
        ])
        result = areas.list_areas(fake_client)
        assert len(result) == 2

    def test_non_list_returns_empty(self, fake_client):
        fake_client.set_ws("config/area_registry/list", None)
        assert areas.list_areas(fake_client) == []

    def test_dict_returns_empty(self, fake_client):
        fake_client.set_ws("config/area_registry/list", {"not": "a list"})
        assert areas.list_areas(fake_client) == []


class TestFindArea:
    def test_find_by_area_id(self, fake_client):
        fake_client.set_ws("config/area_registry/list", [
            {"area_id": "kitchen", "name": "Kitchen"},
        ])
        result = areas.find_area(fake_client, "kitchen")
        assert result is not None
        assert result["area_id"] == "kitchen"

    def test_find_by_name_case_insensitive(self, fake_client):
        fake_client.set_ws("config/area_registry/list", [
            {"area_id": "k1", "name": "Kitchen"},
        ])
        result = areas.find_area(fake_client, "KITCHEN")
        assert result is not None
        assert result["area_id"] == "k1"

    def test_not_found_returns_none(self, fake_client):
        fake_client.set_ws("config/area_registry/list", [
            {"area_id": "k1", "name": "Kitchen"},
        ])
        assert areas.find_area(fake_client, "garage") is None

    def test_empty_ident_returns_none(self, fake_client):
        fake_client.set_ws("config/area_registry/list", [{"area_id": "k1"}])
        assert areas.find_area(fake_client, "") is None

    def test_area_with_no_name_does_not_crash(self, fake_client):
        fake_client.set_ws("config/area_registry/list", [
            {"area_id": "k1", "name": None},
        ])
        assert areas.find_area(fake_client, "anything") is None


class TestCreate:
    def test_minimal_create(self, fake_client):
        fake_client.set_ws("config/area_registry/create", {"area_id": "k1"})
        result = areas.create(fake_client, name="Kitchen")
        assert result == {"area_id": "k1"}
        assert fake_client.ws_calls[-1]["payload"] == {"name": "Kitchen"}

    def test_create_with_all_options(self, fake_client):
        fake_client.set_ws("config/area_registry/create", {"area_id": "k1"})
        areas.create(
            fake_client,
            name="Kitchen",
            floor_id="f1",
            icon="mdi:fridge",
            picture="/pic.jpg",
            aliases=["Cooking"],
            labels=["food"],
        )
        assert fake_client.ws_calls[-1]["payload"] == {
            "name": "Kitchen",
            "floor_id": "f1",
            "icon": "mdi:fridge",
            "picture": "/pic.jpg",
            "aliases": ["Cooking"],
            "labels": ["food"],
        }

    def test_empty_name_raises(self, fake_client):
        with pytest.raises(ValueError, match="name is required"):
            areas.create(fake_client, name="")

    def test_none_response_returns_empty_dict(self, fake_client):
        fake_client.set_ws("config/area_registry/create", None)
        assert areas.create(fake_client, name="Kitchen") == {}


class TestUpdate:
    def test_update_name_only(self, fake_client):
        fake_client.set_ws("config/area_registry/update", {"ok": True})
        areas.update(fake_client, "k1", name="New Name")
        assert fake_client.ws_calls[-1]["payload"] == {
            "area_id": "k1", "name": "New Name",
        }

    def test_update_all_fields(self, fake_client):
        fake_client.set_ws("config/area_registry/update", {"ok": True})
        areas.update(
            fake_client, "k1",
            name="New", floor_id="f2", icon="mdi:sofa",
            picture="/p.jpg", aliases=["a"], labels=["b"],
        )
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["name"] == "New"
        assert payload["floor_id"] == "f2"
        assert payload["icon"] == "mdi:sofa"
        assert payload["picture"] == "/p.jpg"
        assert payload["aliases"] == ["a"]
        assert payload["labels"] == ["b"]

    def test_update_omits_none_fields(self, fake_client):
        """update() with default None values omits them from the payload."""
        fake_client.set_ws("config/area_registry/update", {"ok": True})
        areas.update(fake_client, "k1")
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload == {"area_id": "k1"}
        assert "name" not in payload
        assert "icon" not in payload

    def test_empty_area_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="area_id is required"):
            areas.update(fake_client, "")

    def test_none_response_returns_empty_dict(self, fake_client):
        fake_client.set_ws("config/area_registry/update", None)
        assert areas.update(fake_client, "k1") == {}


class TestDelete:
    def test_delete_sends_payload(self, fake_client):
        fake_client.set_ws("config/area_registry/delete", {"ok": True})
        result = areas.delete(fake_client, "k1")
        assert result == {"ok": True}
        assert fake_client.ws_calls[-1]["payload"] == {"area_id": "k1"}

    def test_empty_area_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="area_id is required"):
            areas.delete(fake_client, "")
