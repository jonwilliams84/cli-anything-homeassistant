"""Weather advanced — convertible units, subscribe forecasts, get forecasts.

WS namespace: `weather/convertible_units` and `weather/subscribe_forecast`.
Service: `POST services/weather/get_forecasts`.
"""

from __future__ import annotations

from typing import Any, Optional


def convertible_units(client) -> dict[str, list[str]]:
    """Retrieve supported units for weather measurement types.

    Returns a dict mapping each unit_type (e.g. "temperature", "speed") to
    the list of convertible units (e.g. ["°C", "°F", "K"]).
    """
    result = client.ws_call("weather/convertible_units") or {}
    return result.get("units", {})


def subscribe_forecast(client, *, entity_id: str, forecast_type: str) -> dict:
    """Subscribe to weather forecast updates via WebSocket.

    This sends a one-shot WS subscribe command. For full streaming, use
    ws_subscribe() to maintain the subscription and receive multiple updates.

    Args:
        client: HomeAssistant client.
        entity_id: Must start with "weather." (e.g., "weather.home").
        forecast_type: One of "daily", "hourly", "twice_daily".

    Returns:
        Response dict from the subscribe command.

    Raises:
        ValueError: If entity_id does not start with "weather." or
                   forecast_type is not one of the allowed values.
    """
    if not entity_id:
        raise ValueError("entity_id is required")
    if not entity_id.startswith("weather."):
        raise ValueError(f"entity_id must start with 'weather.', got: {entity_id}")

    if not forecast_type:
        raise ValueError("forecast_type is required")
    valid_types = {"daily", "hourly", "twice_daily"}
    if forecast_type not in valid_types:
        raise ValueError(
            f"forecast_type must be one of {valid_types}, got: {forecast_type}"
        )

    payload = {
        "entity_id": entity_id,
        "forecast_type": forecast_type,
    }
    return client.ws_call("weather/subscribe_forecast", payload) or {}


def get_forecasts(client, *, entity_id: str, type: str = "daily") -> list[dict]:
    """Retrieve weather forecast data via service call.

    Args:
        client: HomeAssistant client.
        entity_id: Must start with "weather." (e.g., "weather.home").
        type: One of "daily", "hourly", "twice_daily". Defaults to "daily".

    Returns:
        List of forecast dicts. Empty list if no forecast available.

    Raises:
        ValueError: If entity_id does not start with "weather." or
                   type is not one of the allowed values.
    """
    if not entity_id:
        raise ValueError("entity_id is required")
    if not entity_id.startswith("weather."):
        raise ValueError(f"entity_id must start with 'weather.', got: {entity_id}")

    if not type:
        raise ValueError("type is required")
    valid_types = {"daily", "hourly", "twice_daily"}
    if type not in valid_types:
        raise ValueError(f"type must be one of {valid_types}, got: {type}")

    payload = {"entity_id": entity_id, "type": type}
    result = client.post("services/weather/get_forecasts", payload) or {}
    return result.get("forecast", [])
