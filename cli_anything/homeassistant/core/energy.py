"""Energy dashboard preferences + fossil-fuel consumption derivations.

WS namespace: `energy/*`. Reads + writes the Energy dashboard config (which
sensors drive the electricity/gas/water cards, individual device sources,
solar production, grid pricing, etc.) and exposes the fossil-consumption
helper used to compute % renewable energy.
"""

from __future__ import annotations

from typing import Any, Optional


def get_prefs(client) -> dict:
    """Read the current Energy dashboard preferences."""
    return client.ws_call("energy/get_prefs") or {}


def save_prefs(client, prefs: dict) -> dict:
    """Replace the Energy dashboard preferences.

    The full prefs object must be passed — partial updates aren't supported by
    the WS API. Read with `get_prefs`, modify, and pass back.
    """
    if not isinstance(prefs, dict):
        raise ValueError("prefs must be a dict")
    return client.ws_call("energy/save_prefs", prefs) or {}


def info(client) -> dict:
    """Energy integration capability flags (cost_sensors_enabled etc)."""
    return client.ws_call("energy/info") or {}


def fossil_energy_consumption(client, *,
                                energy_statistic_ids: list[str],
                                co2_signal_entity: str,
                                start_time: str,
                                end_time: Optional[str] = None,
                                period: str = "hour") -> dict:
    """Derive fossil-fuel kWh-equivalent for a stat over a period.

    Used by the energy dashboard to compute the "% renewable" gauge.
    Needs a CO2 signal entity (e.g. from the `co2signal` integration).
    """
    if not energy_statistic_ids:
        raise ValueError("energy_statistic_ids must not be empty")
    if period not in ("5minute", "hour", "day", "week", "month"):
        raise ValueError("invalid period")
    payload: dict[str, Any] = {
        "energy_statistic_ids": list(energy_statistic_ids),
        "co2_signal_entity": co2_signal_entity,
        "start_time": start_time,
        "period": period,
    }
    if end_time:
        payload["end_time"] = end_time
    return client.ws_call("energy/fossil_energy_consumption", payload) or {}
