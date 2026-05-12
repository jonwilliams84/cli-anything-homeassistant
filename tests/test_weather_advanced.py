"""Unit tests for weather_advanced — convertible units, subscribe, get forecasts."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import weather_advanced as weather_core


class TestWeatherAdvanced:
    """Test suite for weather advanced functions."""

    # ────────────────────────────────────────────────────────── convertible_units

    def test_convertible_units_happy_path(self, fake_client):
        """Test successful retrieval of convertible units."""
        fake_client.set_ws("weather/convertible_units", {
            "units": {
                "temperature": ["°C", "°F", "K"],
                "speed": ["m/s", "km/h", "mph"],
                "pressure": ["hPa", "mmHg", "inHg"],
            }
        })
        result = weather_core.convertible_units(fake_client)
        assert result == {
            "temperature": ["°C", "°F", "K"],
            "speed": ["m/s", "km/h", "mph"],
            "pressure": ["hPa", "mmHg", "inHg"],
        }
        # Verify WS call was made
        last_ws = fake_client.ws_calls[-1]
        assert last_ws["type"] == "weather/convertible_units"
        assert last_ws["payload"] is None

    def test_convertible_units_empty_response(self, fake_client):
        """Test handling of empty response."""
        fake_client.set_ws("weather/convertible_units", {})
        result = weather_core.convertible_units(fake_client)
        assert result == {}

    def test_convertible_units_none_response(self, fake_client):
        """Test handling of None response."""
        fake_client.set_ws("weather/convertible_units", None)
        result = weather_core.convertible_units(fake_client)
        assert result == {}

    # ────────────────────────────────────────────────────────── subscribe_forecast

    def test_subscribe_forecast_daily_happy_path(self, fake_client):
        """Test successful daily forecast subscription."""
        fake_client.set_ws("weather/subscribe_forecast", {"ok": True})
        result = weather_core.subscribe_forecast(
            fake_client, entity_id="weather.home", forecast_type="daily"
        )
        assert result == {"ok": True}
        # Verify WS call payload
        last_ws = fake_client.ws_calls[-1]
        assert last_ws["type"] == "weather/subscribe_forecast"
        assert last_ws["payload"]["entity_id"] == "weather.home"
        assert last_ws["payload"]["forecast_type"] == "daily"

    def test_subscribe_forecast_hourly(self, fake_client):
        """Test hourly forecast subscription."""
        fake_client.set_ws("weather/subscribe_forecast", {"ok": True})
        weather_core.subscribe_forecast(
            fake_client, entity_id="weather.living_room", forecast_type="hourly"
        )
        last_ws = fake_client.ws_calls[-1]
        assert last_ws["payload"]["forecast_type"] == "hourly"

    def test_subscribe_forecast_twice_daily(self, fake_client):
        """Test twice_daily forecast subscription."""
        fake_client.set_ws("weather/subscribe_forecast", {"ok": True})
        weather_core.subscribe_forecast(
            fake_client, entity_id="weather.garden", forecast_type="twice_daily"
        )
        last_ws = fake_client.ws_calls[-1]
        assert last_ws["payload"]["forecast_type"] == "twice_daily"

    def test_subscribe_forecast_missing_entity_id(self):
        """Test validation: entity_id is required."""
        with pytest.raises(ValueError, match="entity_id is required"):
            weather_core.subscribe_forecast(None, entity_id="", forecast_type="daily")

    def test_subscribe_forecast_invalid_entity_id_prefix(self):
        """Test validation: entity_id must start with 'weather.'."""
        with pytest.raises(ValueError, match="entity_id must start with 'weather.'"):
            weather_core.subscribe_forecast(
                None, entity_id="sensor.temperature", forecast_type="daily"
            )

    def test_subscribe_forecast_missing_forecast_type(self):
        """Test validation: forecast_type is required."""
        with pytest.raises(ValueError, match="forecast_type is required"):
            weather_core.subscribe_forecast(
                None, entity_id="weather.home", forecast_type=""
            )

    def test_subscribe_forecast_invalid_forecast_type(self):
        """Test validation: forecast_type must be one of the allowed values."""
        with pytest.raises(ValueError, match="forecast_type must be one of"):
            weather_core.subscribe_forecast(
                None, entity_id="weather.home", forecast_type="invalid"
            )

    # ────────────────────────────────────────────────────────── get_forecasts

    def test_get_forecasts_daily_happy_path(self, fake_client):
        """Test successful daily forecast retrieval."""
        fake_client.set("POST", "services/weather/get_forecasts", {
            "forecast": [
                {
                    "datetime": "2026-05-12T12:00:00Z",
                    "temperature": 22,
                    "condition": "sunny",
                },
                {
                    "datetime": "2026-05-13T12:00:00Z",
                    "temperature": 20,
                    "condition": "cloudy",
                },
            ]
        })
        result = weather_core.get_forecasts(
            fake_client, entity_id="weather.home", forecast_type="daily"
        )
        assert len(result) == 2
        assert result[0]["temperature"] == 22
        assert result[1]["condition"] == "cloudy"
        # Verify POST call payload
        last_call = fake_client.calls[-1]
        assert last_call["verb"] == "POST"
        assert last_call["payload"]["entity_id"] == "weather.home"
        assert last_call["payload"]["type"] == "daily"

    def test_get_forecasts_hourly(self, fake_client):
        """Test hourly forecast retrieval."""
        fake_client.set("POST", "services/weather/get_forecasts", {
            "forecast": [{"datetime": "2026-05-12T13:00:00Z", "temperature": 21}]
        })
        result = weather_core.get_forecasts(
            fake_client, entity_id="weather.home", forecast_type="hourly"
        )
        assert len(result) == 1
        assert result[0]["temperature"] == 21

    def test_get_forecasts_twice_daily(self, fake_client):
        """Test twice_daily forecast retrieval."""
        fake_client.set("POST", "services/weather/get_forecasts", {
            "forecast": [{"datetime": "2026-05-12T06:00:00Z", "temperature": 18}]
        })
        result = weather_core.get_forecasts(
            fake_client, entity_id="weather.home", forecast_type="twice_daily"
        )
        assert len(result) == 1

    def test_get_forecasts_default_type(self, fake_client):
        """Test that type defaults to 'daily'."""
        fake_client.set("POST", "services/weather/get_forecasts", {"forecast": []})
        weather_core.get_forecasts(fake_client, entity_id="weather.home")
        last_call = fake_client.calls[-1]
        assert last_call["payload"]["type"] == "daily"

    def test_get_forecasts_empty_forecast(self, fake_client):
        """Test handling of empty forecast list."""
        fake_client.set("POST", "services/weather/get_forecasts", {"forecast": []})
        result = weather_core.get_forecasts(
            fake_client, entity_id="weather.home", forecast_type="daily"
        )
        assert result == []

    def test_get_forecasts_missing_forecast_key(self, fake_client):
        """Test handling of response without forecast key."""
        fake_client.set("POST", "services/weather/get_forecasts", {})
        result = weather_core.get_forecasts(
            fake_client, entity_id="weather.home", forecast_type="daily"
        )
        assert result == []

    def test_get_forecasts_missing_entity_id(self):
        """Test validation: entity_id is required."""
        with pytest.raises(ValueError, match="entity_id is required"):
            weather_core.get_forecasts(None, entity_id="")

    def test_get_forecasts_invalid_entity_id_prefix(self):
        """Test validation: entity_id must start with 'weather.'."""
        with pytest.raises(ValueError, match="entity_id must start with 'weather.'"):
            weather_core.get_forecasts(None, entity_id="sensor.temperature")

    def test_get_forecasts_invalid_type(self):
        """Test validation: forecast_type must be one of the allowed values."""
        with pytest.raises(ValueError, match="forecast_type must be one of"):
            weather_core.get_forecasts(
                None, entity_id="weather.home", forecast_type="invalid"
            )
