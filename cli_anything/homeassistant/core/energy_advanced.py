"""Energy advanced — fossil consumption, solar forecast, validation, structured save_prefs.

WS namespace: ``energy/*``.

This module wraps the four advanced energy WebSocket commands that are distinct
from the basic ``get_prefs`` / ``info`` helpers already in ``energy.py``:

* ``energy/validate``                  → :func:`validate_energy_prefs`
* ``energy/solar_forecast``            → :func:`solar_forecast`
* ``energy/fossil_energy_consumption`` → :func:`fossil_energy_consumption`
* ``energy/save_prefs``                → :func:`save_prefs`

The ``fossil_energy_consumption`` and ``save_prefs`` signatures here differ
intentionally from those in ``energy.py``:

- ``fossil_energy_consumption`` uses ``co2_statistic_id`` (a recorder statistic
  ID) and requires a mandatory ``end_time``, matching the HA 2024+ WS schema.
- ``save_prefs`` accepts structured keyword arguments (``energy_sources``,
  ``device_consumption``, ``manual_configured_statistic_ids``) rather than a
  raw prefs dict.

Do **not** import from ``energy.py`` here — this module is self-contained.
"""

from __future__ import annotations

from typing import Any

_VALID_PERIODS = frozenset({"5minute", "hour", "day", "week", "month"})


def validate_energy_prefs(client) -> dict:
    """Validate the current Energy dashboard preferences.

    Sends ``energy/validate`` over the WebSocket and returns the server's
    dict of validation issues keyed by energy source / integration.

    Returns:
        A ``dict`` of validation issues; empty dict when everything is valid.
    """
    result = client.ws_call("energy/validate")
    if not isinstance(result, dict):
        return {}
    return result


def solar_forecast(client) -> dict:
    """Retrieve the solar production forecast for the next day.

    Sends ``energy/solar_forecast`` over the WebSocket.  The response is
    keyed by config-entry ID and contains watt-hour forecasts per time slot.

    Returns:
        A ``dict`` mapping config-entry IDs to forecast data; empty dict when
        no solar sources are configured or no forecast platform is available.
    """
    result = client.ws_call("energy/solar_forecast")
    if not isinstance(result, dict):
        return {}
    return result


def fossil_energy_consumption(
    client,
    *,
    start_time: str,
    end_time: str,
    energy_statistic_ids: list[str],
    co2_statistic_id: str,
    period: str = "hour",
) -> dict:
    """Compute fossil-fuel energy consumption over a time range.

    Sends ``energy/fossil_energy_consumption`` with the full required payload.
    The server uses the CO2-intensity statistic to weight each kWh of energy
    consumption and returns the fossil-fuel fraction per time bucket.

    Args:
        client: An authenticated HA client with a ``ws_call`` method.
        start_time: ISO-8601 timestamp (UTC) for the start of the range.
        end_time: ISO-8601 timestamp (UTC) for the end of the range.
        energy_statistic_ids: Non-empty list of recorder statistic IDs for the
            energy sources to include (e.g. ``["sensor:grid_import_energy"]``).
        co2_statistic_id: Recorder statistic ID for the CO2-intensity signal
            (e.g. ``"co2signal:co2_intensity_de"``).
        period: Aggregation bucket size.  Must be one of ``"5minute"``,
            ``"hour"``, ``"day"``, ``"week"``, or ``"month"``.
            Defaults to ``"hour"``.

    Returns:
        A ``dict`` mapping ISO-8601 period-start strings to fossil kWh values.

    Raises:
        ValueError: If ``start_time`` is empty, ``end_time`` is empty,
            ``energy_statistic_ids`` is empty, ``co2_statistic_id`` is empty,
            or ``period`` is not one of the accepted values.
    """
    if not start_time:
        raise ValueError("start_time must not be empty")
    if not end_time:
        raise ValueError("end_time must not be empty")
    if not energy_statistic_ids:
        raise ValueError("energy_statistic_ids must be a non-empty list")
    if not co2_statistic_id:
        raise ValueError("co2_statistic_id must not be empty")
    if period not in _VALID_PERIODS:
        raise ValueError(
            f"period must be one of {sorted(_VALID_PERIODS)!r}, got {period!r}"
        )

    payload: dict[str, Any] = {
        "start_time": start_time,
        "end_time": end_time,
        "energy_statistic_ids": list(energy_statistic_ids),
        "co2_statistic_id": co2_statistic_id,
        "period": period,
    }
    result = client.ws_call("energy/fossil_energy_consumption", payload)
    if not isinstance(result, dict):
        return {}
    return result


def save_prefs(
    client,
    *,
    energy_sources: list[dict],
    device_consumption: list[dict] | None = None,
    manual_configured_statistic_ids: list[str] | None = None,
) -> dict:
    """Save structured Energy dashboard preferences.

    Sends ``energy/save_prefs`` with the provided keyword arguments as the
    payload.  Only ``energy_sources`` is required by this wrapper; the
    remaining fields are included in the payload only when provided.

    Args:
        client: An authenticated HA client with a ``ws_call`` method.
        energy_sources: Non-empty list of energy-source dicts (solar, grid,
            gas, water, etc.).  Each dict must conform to HA's
            ``ENERGY_SOURCE_SCHEMA``.
        device_consumption: Optional list of device-consumption dicts.  When
            ``None`` the key is omitted from the payload.
        manual_configured_statistic_ids: Optional list of statistic IDs that
            are manually configured rather than auto-discovered.  When
            ``None`` the key is omitted from the payload.

    Returns:
        The updated preferences dict returned by the server, or an empty dict
        if the server response is not a dict.

    Raises:
        ValueError: If ``energy_sources`` is not a non-empty list.
    """
    if not isinstance(energy_sources, list) or not energy_sources:
        raise ValueError("energy_sources must be a non-empty list of dicts")

    payload: dict[str, Any] = {
        "energy_sources": energy_sources,
    }
    if device_consumption is not None:
        payload["device_consumption"] = device_consumption
    if manual_configured_statistic_ids is not None:
        payload["manual_configured_statistic_ids"] = manual_configured_statistic_ids

    result = client.ws_call("energy/save_prefs", payload)
    if not isinstance(result, dict):
        return {}
    return result
