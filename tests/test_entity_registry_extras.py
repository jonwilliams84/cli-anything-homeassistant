"""Unit tests for entity_registry_extras module."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import entity_registry_extras


class TestEntityRegistryExtras:
    """Tests for entity_registry_extras module functions."""

    # ─── get_entity_registry_entry ────────────────────────────────────────

    def test_get_entity_registry_entry_happy_path(self, fake_client):
        """Test retrieving a single entity registry entry."""
        fake_client.set_ws("config/entity_registry/get", {
            "entity_id": "light.living_room",
            "name": "Living Room Light",
            "platform": "hue",
            "device_id": "abc123",
            "area_id": "living_room",
        })
        result = entity_registry_extras.get_entity_registry_entry(
            fake_client, entity_id="light.living_room"
        )
        assert result["entity_id"] == "light.living_room"
        assert result["name"] == "Living Room Light"
        assert fake_client.ws_calls[-1]["type"] == "config/entity_registry/get"
        assert fake_client.ws_calls[-1]["payload"] == {"entity_id": "light.living_room"}

    def test_get_entity_registry_entry_empty_raises(self, fake_client):
        """Test that empty entity_id raises ValueError."""
        with pytest.raises(ValueError, match="entity_id is required"):
            entity_registry_extras.get_entity_registry_entry(fake_client, entity_id="")

    def test_get_entity_registry_entry_return_shape(self, fake_client):
        """Test that get_entity_registry_entry returns a dict."""
        fake_client.set_ws("config/entity_registry/get", {"entity_id": "light.a"})
        result = entity_registry_extras.get_entity_registry_entry(
            fake_client, entity_id="light.a"
        )
        assert isinstance(result, dict)

    # ─── get_entity_registry_entries ──────────────────────────────────────

    def test_get_entity_registry_entries_happy_path(self, fake_client):
        """Test retrieving multiple entity registry entries."""
        fake_client.set_ws("config/entity_registry/get_entries", [
            {"entity_id": "light.a", "name": "Light A"},
            {"entity_id": "light.b", "name": "Light B"},
        ])
        result = entity_registry_extras.get_entity_registry_entries(
            fake_client, entity_ids=["light.a", "light.b"]
        )
        assert len(result) == 2
        assert result[0]["entity_id"] == "light.a"
        assert fake_client.ws_calls[-1]["type"] == "config/entity_registry/get_entries"
        assert fake_client.ws_calls[-1]["payload"] == {
            "entity_ids": ["light.a", "light.b"]
        }

    def test_get_entity_registry_entries_empty_list_raises(self, fake_client):
        """Test that empty entity_ids list raises ValueError."""
        with pytest.raises(ValueError, match="entity_ids must be a non-empty list"):
            entity_registry_extras.get_entity_registry_entries(
                fake_client, entity_ids=[]
            )

    def test_get_entity_registry_entries_non_list_raises(self, fake_client):
        """Test that non-list entity_ids raises ValueError."""
        with pytest.raises(ValueError, match="entity_ids must be a non-empty list"):
            entity_registry_extras.get_entity_registry_entries(
                fake_client, entity_ids="light.a"
            )

    def test_get_entity_registry_entries_empty_string_in_list_raises(self, fake_client):
        """Test that empty string in entity_ids raises ValueError."""
        with pytest.raises(ValueError, match="all entity_ids must be non-empty strings"):
            entity_registry_extras.get_entity_registry_entries(
                fake_client, entity_ids=["light.a", ""]
            )

    def test_get_entity_registry_entries_non_string_in_list_raises(self, fake_client):
        """Test that non-string in entity_ids raises ValueError."""
        with pytest.raises(ValueError, match="all entity_ids must be non-empty strings"):
            entity_registry_extras.get_entity_registry_entries(
                fake_client, entity_ids=["light.a", 123]
            )

    def test_get_entity_registry_entries_return_shape(self, fake_client):
        """Test that get_entity_registry_entries returns a list."""
        fake_client.set_ws("config/entity_registry/get_entries", [
            {"entity_id": "light.a"},
            {"entity_id": "light.b"},
        ])
        result = entity_registry_extras.get_entity_registry_entries(
            fake_client, entity_ids=["light.a", "light.b"]
        )
        assert isinstance(result, list)
        for entry in result:
            assert isinstance(entry, dict)
            assert "entity_id" in entry

    # ─── list_entity_registry_for_display ─────────────────────────────────

    def test_list_entity_registry_for_display_happy_path(self, fake_client):
        """Test retrieving UI-optimized entity registry list."""
        fake_client.set_ws("config/entity_registry/list_for_display", [
            {"entity_id": "light.a", "name": "Light A", "icon": "mdi:lightbulb"},
            {"entity_id": "switch.b", "name": "Switch B", "icon": "mdi:power"},
        ])
        result = entity_registry_extras.list_entity_registry_for_display(fake_client)
        assert len(result) == 2
        assert result[0]["entity_id"] == "light.a"
        assert fake_client.ws_calls[-1]["type"] == "config/entity_registry/list_for_display"
        assert fake_client.ws_calls[-1]["payload"] is None

    def test_list_entity_registry_for_display_return_shape(self, fake_client):
        """Test that list_entity_registry_for_display returns a list."""
        fake_client.set_ws("config/entity_registry/list_for_display", [
            {"entity_id": "light.a", "name": "Light A"},
        ])
        result = entity_registry_extras.list_entity_registry_for_display(fake_client)
        assert isinstance(result, list)
        for entry in result:
            assert isinstance(entry, dict)

    # ─── remove_entity_registry_entry ─────────────────────────────────────

    def test_remove_entity_registry_entry_happy_path(self, fake_client):
        """Test removing an entity from the registry."""
        fake_client.set_ws("config/entity_registry/remove", {})
        result = entity_registry_extras.remove_entity_registry_entry(
            fake_client, entity_id="light.living_room"
        )
        assert result == {}
        assert fake_client.ws_calls[-1]["type"] == "config/entity_registry/remove"
        assert fake_client.ws_calls[-1]["payload"] == {"entity_id": "light.living_room"}

    def test_remove_entity_registry_entry_empty_raises(self, fake_client):
        """Test that empty entity_id raises ValueError."""
        with pytest.raises(ValueError, match="entity_id is required"):
            entity_registry_extras.remove_entity_registry_entry(fake_client, entity_id="")

    def test_remove_entity_registry_entry_return_shape(self, fake_client):
        """Test that remove_entity_registry_entry returns a dict."""
        fake_client.set_ws("config/entity_registry/remove", {"status": "removed"})
        result = entity_registry_extras.remove_entity_registry_entry(
            fake_client, entity_id="light.a"
        )
        assert isinstance(result, dict)

    # ─── subscribe_config_entries ─────────────────────────────────────────

    def test_subscribe_config_entries_happy_path(self, fake_client):
        """Test subscribing to config entry changes."""
        fake_client.set_ws("config_entries/subscribe", {
            "entries": [
                {"entry_id": "entry1", "domain": "hue", "title": "Hue Bridge"},
            ]
        })
        result = entity_registry_extras.subscribe_config_entries(fake_client)
        assert "entries" in result
        assert fake_client.ws_calls[-1]["type"] == "config_entries/subscribe"
        assert fake_client.ws_calls[-1]["payload"] is None

    def test_subscribe_config_entries_return_shape(self, fake_client):
        """Test that subscribe_config_entries returns a dict."""
        fake_client.set_ws("config_entries/subscribe", {"entries": []})
        result = entity_registry_extras.subscribe_config_entries(fake_client)
        assert isinstance(result, dict)

    # ─── get_integration_setup_info ───────────────────────────────────────

    def test_get_integration_setup_info_happy_path(self, fake_client):
        """Test getting integration setup info."""
        fake_client.set_ws("integration/setup_info", {
            "setup_times": {
                "hue": 1.234,
                "mqtt": 0.567,
            },
            "setup_errors": {
                "zwave": "Device not found",
            }
        })
        result = entity_registry_extras.get_integration_setup_info(fake_client)
        assert "setup_times" in result
        assert result["setup_times"]["hue"] == 1.234
        assert fake_client.ws_calls[-1]["type"] == "integration/setup_info"

    def test_get_integration_setup_info_return_shape(self, fake_client):
        """Test that get_integration_setup_info returns a dict."""
        fake_client.set_ws("integration/setup_info", {"setup_times": {}})
        result = entity_registry_extras.get_integration_setup_info(fake_client)
        assert isinstance(result, dict)

    # ─── statistic_during_period ─────────────────────────────────────────

    def test_statistic_during_period_with_fixed_period_happy_path(self, fake_client):
        """Test querying statistics with fixed period."""
        fake_client.set_ws("recorder/statistic_during_period", {
            "stat1": [
                {"start": "2024-01-01T00:00:00", "mean": 50.5, "min": 30, "max": 70},
            ]
        })
        result = entity_registry_extras.statistic_during_period(
            fake_client,
            statistic_id="stat1",
            fixed_period={"start": "2024-01-01T00:00:00", "end": "2024-01-02T00:00:00"}
        )
        assert "stat1" in result
        assert fake_client.ws_calls[-1]["type"] == "recorder/statistic_during_period"
        assert fake_client.ws_calls[-1]["payload"]["statistic_id"] == "stat1"

    def test_statistic_during_period_with_calendar_happy_path(self, fake_client):
        """Test querying statistics with calendar period."""
        fake_client.set_ws("recorder/statistic_during_period", {})
        entity_registry_extras.statistic_during_period(
            fake_client,
            statistic_id="stat1",
            calendar={"year": 2024, "month": 1}
        )
        assert fake_client.ws_calls[-1]["payload"]["calendar"] == {"year": 2024, "month": 1}

    def test_statistic_during_period_with_rolling_window_happy_path(self, fake_client):
        """Test querying statistics with rolling window."""
        fake_client.set_ws("recorder/statistic_during_period", {})
        entity_registry_extras.statistic_during_period(
            fake_client,
            statistic_id="stat1",
            rolling_window={"days": 7}
        )
        assert fake_client.ws_calls[-1]["payload"]["rolling_window"] == {"days": 7}

    def test_statistic_during_period_with_types_happy_path(self, fake_client):
        """Test querying statistics with specific types."""
        fake_client.set_ws("recorder/statistic_during_period", {})
        entity_registry_extras.statistic_during_period(
            fake_client,
            statistic_id="stat1",
            fixed_period={"start": "2024-01-01T00:00:00", "end": "2024-01-02T00:00:00"},
            types=["max", "min"]
        )
        assert fake_client.ws_calls[-1]["payload"]["types"] == ["max", "min"]

    def test_statistic_during_period_with_units_happy_path(self, fake_client):
        """Test querying statistics with unit overrides."""
        fake_client.set_ws("recorder/statistic_during_period", {})
        entity_registry_extras.statistic_during_period(
            fake_client,
            statistic_id="stat1",
            fixed_period={"start": "2024-01-01T00:00:00", "end": "2024-01-02T00:00:00"},
            units={"stat1": "°C"}
        )
        assert fake_client.ws_calls[-1]["payload"]["units"] == {"stat1": "°C"}

    def test_statistic_during_period_empty_statistic_id_raises(self, fake_client):
        """Test that empty statistic_id raises ValueError."""
        with pytest.raises(ValueError, match="statistic_id is required"):
            entity_registry_extras.statistic_during_period(
                fake_client,
                statistic_id="",
                fixed_period={"start": "2024-01-01T00:00:00", "end": "2024-01-02T00:00:00"}
            )

    def test_statistic_during_period_no_period_raises(self, fake_client):
        """Test that missing period definition raises ValueError."""
        with pytest.raises(
            ValueError,
            match="at least one of fixed_period, calendar, or rolling_window is required"
        ):
            entity_registry_extras.statistic_during_period(
                fake_client, statistic_id="stat1"
            )

    def test_statistic_during_period_return_shape(self, fake_client):
        """Test that statistic_during_period returns a dict."""
        fake_client.set_ws("recorder/statistic_during_period", {
            "stat1": [{"mean": 50}]
        })
        result = entity_registry_extras.statistic_during_period(
            fake_client,
            statistic_id="stat1",
            fixed_period={"start": "2024-01-01T00:00:00", "end": "2024-01-02T00:00:00"}
        )
        assert isinstance(result, dict)

    def test_statistic_during_period_all_optional_params(self, fake_client):
        """Test with all optional parameters."""
        fake_client.set_ws("recorder/statistic_during_period", {})
        entity_registry_extras.statistic_during_period(
            fake_client,
            statistic_id="stat1",
            fixed_period={"start": "2024-01-01T00:00:00", "end": "2024-01-02T00:00:00"},
            types=["max", "min"],
            units={"stat1": "°C"}
        )
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["statistic_id"] == "stat1"
        assert payload["fixed_period"]["start"] == "2024-01-01T00:00:00"
        assert payload["types"] == ["max", "min"]
        assert payload["units"] == {"stat1": "°C"}
