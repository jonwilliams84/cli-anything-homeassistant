"""Unit tests for cli_anything.homeassistant.core.zone."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import zone


_SAMPLE_ZONE = {
    "id": "zone-001",
    "name": "Office",
    "latitude": 51.50,
    "longitude": -0.10,
    "radius": 200.0,
    "icon": "mdi:office-building",
    "passive": False,
}


class TestZoneRegistry:

    # ──────────────────────────────────────────────────── list

    def test_list_zones_happy(self, fake_client):
        fake_client.set_ws("config/zone/list", [_SAMPLE_ZONE])
        result = zone.list_zones(fake_client)
        assert result == [_SAMPLE_ZONE]
        assert fake_client.ws_calls[0]["type"] == "config/zone/list"

    def test_list_zones_empty(self, fake_client):
        assert zone.list_zones(fake_client) == []

    # ──────────────────────────────────────────────────── find

    def test_find_zone_by_id(self, fake_client):
        fake_client.set_ws("config/zone/list", [_SAMPLE_ZONE])
        assert zone.find_zone(fake_client, "zone-001") == _SAMPLE_ZONE

    def test_find_zone_by_name_case_insensitive(self, fake_client):
        fake_client.set_ws("config/zone/list", [_SAMPLE_ZONE])
        assert zone.find_zone(fake_client, "OFFICE") == _SAMPLE_ZONE

    def test_find_zone_none(self, fake_client):
        fake_client.set_ws("config/zone/list", [_SAMPLE_ZONE])
        assert zone.find_zone(fake_client, "nope") is None

    def test_find_zone_empty_ident(self, fake_client):
        assert zone.find_zone(fake_client, "") is None

    # ──────────────────────────────────────────────────── create

    def test_create_happy_path(self, fake_client):
        fake_client.set_ws("config/zone/create", _SAMPLE_ZONE)
        result = zone.create(
            fake_client, name="Office",
            latitude=51.5, longitude=-0.1,
            radius=200, icon="mdi:office-building", passive=False,
        )
        call = fake_client.ws_calls[0]
        assert call["type"] == "config/zone/create"
        assert call["payload"]["name"] == "Office"
        assert call["payload"]["latitude"] == 51.5
        assert call["payload"]["longitude"] == -0.1
        assert call["payload"]["radius"] == 200.0
        assert call["payload"]["passive"] is False
        assert result == _SAMPLE_ZONE

    def test_create_minimal_payload(self, fake_client):
        fake_client.set_ws("config/zone/create", _SAMPLE_ZONE)
        zone.create(fake_client, name="Home", latitude=0, longitude=0)
        payload = fake_client.ws_calls[0]["payload"]
        assert payload == {"name": "Home", "latitude": 0.0, "longitude": 0.0}
        # No radius / icon / passive when not given
        assert "radius" not in payload
        assert "icon" not in payload
        assert "passive" not in payload

    def test_create_missing_name(self, fake_client):
        with pytest.raises(ValueError, match="name"):
            zone.create(fake_client, name="", latitude=0, longitude=0)

    def test_create_missing_coords(self, fake_client):
        with pytest.raises(ValueError, match="latitude"):
            zone.create(fake_client, name="X", latitude=None, longitude=0)
        with pytest.raises(ValueError, match="latitude"):
            zone.create(fake_client, name="X", latitude=0, longitude=None)

    # ──────────────────────────────────────────────────── update

    def test_update_happy_path(self, fake_client):
        fake_client.set_ws("config/zone/update", _SAMPLE_ZONE)
        zone.update(fake_client, "zone-001", name="New Office", radius=300)
        payload = fake_client.ws_calls[0]["payload"]
        assert payload["zone_id"] == "zone-001"
        assert payload["name"] == "New Office"
        assert payload["radius"] == 300.0
        assert "latitude" not in payload  # not passed → not sent

    def test_update_passive_flag(self, fake_client):
        fake_client.set_ws("config/zone/update", _SAMPLE_ZONE)
        zone.update(fake_client, "zone-001", passive=True)
        payload = fake_client.ws_calls[0]["payload"]
        assert payload == {"zone_id": "zone-001", "passive": True}

    def test_update_no_zone_id(self, fake_client):
        with pytest.raises(ValueError, match="zone_id"):
            zone.update(fake_client, "", name="X")

    # ──────────────────────────────────────────────────── delete

    def test_delete_happy(self, fake_client):
        fake_client.set_ws("config/zone/delete", None)
        zone.delete(fake_client, "zone-001")
        call = fake_client.ws_calls[0]
        assert call["type"] == "config/zone/delete"
        assert call["payload"] == {"zone_id": "zone-001"}

    def test_delete_no_zone_id(self, fake_client):
        with pytest.raises(ValueError, match="zone_id"):
            zone.delete(fake_client, "")


class TestZoneEntityHelpers:

    def test_list_state_zones_filters_to_zone_domain(self, fake_client):
        fake_client.set("GET", "states", [
            {"entity_id": "zone.home", "state": "zoning", "attributes": {"friendly_name": "Home"}},
            {"entity_id": "zone.work", "state": "zoning", "attributes": {"friendly_name": "Work"}},
            {"entity_id": "light.kitchen", "state": "on", "attributes": {}},
        ])
        result = zone.list_state_zones(fake_client)
        assert [r["entity_id"] for r in result] == ["zone.home", "zone.work"]

    def test_list_state_zones_handles_empty(self, fake_client):
        fake_client.set("GET", "states", [])
        assert zone.list_state_zones(fake_client) == []

    def test_entities_in_zone_by_entity_id(self, fake_client):
        # state lookup → friendly_name
        fake_client.set("GET", "states/zone.home", {
            "entity_id": "zone.home",
            "state": "zoning",
            "attributes": {"friendly_name": "Home"},
        })
        fake_client.set("GET", "states", [
            {"entity_id": "person.alice", "state": "Home"},
            {"entity_id": "person.bob", "state": "not_home"},
            {"entity_id": "device_tracker.phone", "state": "Home"},
            {"entity_id": "light.kitchen", "state": "Home"},  # wrong domain
        ])
        result = zone.entities_in_zone(fake_client, "zone.home")
        eids = sorted(r["entity_id"] for r in result)
        assert eids == ["device_tracker.phone", "person.alice"]

    def test_entities_in_zone_by_friendly_name(self, fake_client):
        fake_client.set("GET", "states", [
            {"entity_id": "zone.office", "state": "zoning",
             "attributes": {"friendly_name": "Office"}},
            {"entity_id": "person.alice", "state": "Office"},
            {"entity_id": "person.bob", "state": "Home"},
        ])
        result = zone.entities_in_zone(fake_client, "Office")
        eids = [r["entity_id"] for r in result]
        assert eids == ["person.alice"]

    def test_entities_in_zone_empty_ident(self, fake_client):
        with pytest.raises(ValueError, match="zone identifier"):
            zone.entities_in_zone(fake_client, "")
