"""Unit tests for cli_anything.homeassistant.core.services."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import services


class TestListServices:
    def test_returns_all_services(self, fake_client):
        fake_client.set("GET", "services", [
            {"domain": "light", "services": {}},
            {"domain": "switch", "services": {}},
        ])
        result = services.list_services(fake_client)
        assert len(result) == 2

    def test_filters_by_domain(self, fake_client):
        fake_client.set("GET", "services", [
            {"domain": "light", "services": {}},
            {"domain": "switch", "services": {}},
        ])
        result = services.list_services(fake_client, domain="light")
        assert len(result) == 1
        assert result[0]["domain"] == "light"

    def test_non_list_returns_empty(self, fake_client):
        fake_client.set("GET", "services", {"not": "a list"})
        assert services.list_services(fake_client) == []


class TestListDomains:
    def test_returns_sorted_domains(self, fake_client):
        fake_client.set("GET", "services", [
            {"domain": "switch"},
            {"domain": "light"},
            {"domain": "light"},  # duplicate
        ])
        result = services.list_domains(fake_client)
        assert result == ["light", "switch"]

    def test_skips_entries_without_domain(self, fake_client):
        fake_client.set("GET", "services", [
            {"domain": "light"},
            {"services": {}},  # no domain key
        ])
        result = services.list_domains(fake_client)
        assert result == ["light"]


class TestGetService:
    def test_returns_service_descriptor(self, fake_client):
        fake_client.set("GET", "services", [
            {"domain": "light", "services": {
                "turn_on": {"name": "Turn on", "description": "Turns on"},
                "turn_off": {"name": "Turn off"},
            }},
        ])
        result = services.get_service(fake_client, "light", "turn_on")
        assert result["name"] == "Turn on"

    def test_returns_none_when_service_not_found(self, fake_client):
        fake_client.set("GET", "services", [
            {"domain": "light", "services": {"turn_on": {}}},
        ])
        assert services.get_service(fake_client, "light", "turn_off") is None

    def test_returns_none_when_domain_not_found(self, fake_client):
        fake_client.set("GET", "services", [
            {"domain": "light", "services": {}},
        ])
        assert services.get_service(fake_client, "switch", "turn_on") is None

    def test_empty_domain_raises(self, fake_client):
        with pytest.raises(ValueError, match="domain and service are required"):
            services.get_service(fake_client, "", "turn_on")

    def test_empty_service_raises(self, fake_client):
        with pytest.raises(ValueError, match="domain and service are required"):
            services.get_service(fake_client, "light", "")


class TestCallService:
    def test_calls_service_with_target(self, fake_client):
        fake_client.set_service("light", "turn_on", {"ok": True})
        result = services.call_service(
            fake_client, "light", "turn_on",
            target={"entity_id": "light.living_room"},
        )
        assert result == {"ok": True}
        call = fake_client.service_calls[-1]
        assert call["domain"] == "light"
        assert call["service"] == "turn_on"
        assert call["service_data"]["entity_id"] == "light.living_room"

    def test_calls_service_with_service_data(self, fake_client):
        fake_client.set_service("light", "set_level", {})
        services.call_service(
            fake_client, "light", "set_level",
            service_data={"brightness": 128},
            target={"entity_id": "light.x"},
        )
        data = fake_client.service_calls[-1]["service_data"]
        assert data["brightness"] == 128
        assert data["entity_id"] == "light.x"

    def test_empty_domain_raises(self, fake_client):
        with pytest.raises(ValueError, match="domain and service are required"):
            services.call_service(fake_client, "", "turn_on")

    def test_empty_service_raises(self, fake_client):
        with pytest.raises(ValueError, match="domain and service are required"):
            services.call_service(fake_client, "light", "")

    def test_return_response_passes_params(self, fake_client):
        fake_client.set_service("light", "turn_on", {})
        services.call_service(
            fake_client, "light", "turn_on",
            return_response=True,
        )
        call = fake_client.calls[-1]
        assert call.get("params") == {"return_response": "true"}

    def test_no_return_response_no_params(self, fake_client):
        fake_client.set_service("light", "turn_on", {})
        services.call_service(fake_client, "light", "turn_on")
        call = fake_client.calls[-1]
        assert "params" not in call
