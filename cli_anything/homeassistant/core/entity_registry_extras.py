"""Entity registry extras + config-related singletons (WebSocket).

Additional entity registry operations and miscellaneous config commands not
covered by the main registry module. Includes config entry subscriptions,
integration setup info, and statistic queries.
"""

from __future__ import annotations


def get_entity_registry_entry(client, *, entity_id: str) -> dict:
    """Retrieve a single entity registry entry by entity_id.

    WS command: config/entity_registry/get
    """
    if not entity_id:
        raise ValueError("entity_id is required")
    return client.ws_call("config/entity_registry/get", {"entity_id": entity_id}) or {}


def get_entity_registry_entries(client, *, entity_ids: list[str]) -> list[dict]:
    """Retrieve multiple entity registry entries by entity_ids.

    WS command: config/entity_registry/get_entries
    """
    if not isinstance(entity_ids, list) or not entity_ids:
        raise ValueError("entity_ids must be a non-empty list")
    if not all(isinstance(eid, str) and eid for eid in entity_ids):
        raise ValueError("all entity_ids must be non-empty strings")
    return client.ws_call("config/entity_registry/get_entries",
                           {"entity_ids": entity_ids}) or []


def list_entity_registry_for_display(client) -> list[dict]:
    """List entity registry in UI-optimized format.

    Returns a UI-optimized list suitable for display purposes.

    WS command: config/entity_registry/list_for_display
    """
    return client.ws_call("config/entity_registry/list_for_display") or []


def remove_entity_registry_entry(client, *, entity_id: str) -> dict:
    """Remove an entity from the registry.

    WS command: config/entity_registry/remove
    """
    if not entity_id:
        raise ValueError("entity_id is required")
    return client.ws_call("config/entity_registry/remove", {"entity_id": entity_id}) or {}


def subscribe_config_entries(client) -> dict:
    """Subscribe to config entry changes (one-shot; streaming requires ws_subscribe).

    Returns the current config entries state. For continuous streaming of changes,
    use the WebSocket subscribe API directly.

    WS command: config_entries/subscribe
    """
    return client.ws_call("config_entries/subscribe") or {}


def get_integration_setup_info(client) -> dict:
    """Get integration setup timings and error information.

    Returns a dict with setup-time durations and any errors per integration.

    WS command: integration/setup_info
    """
    return client.ws_call("integration/setup_info") or {}


def statistic_during_period(client, *, statistic_id: str,
                             fixed_period: dict | None = None,
                             calendar: dict | None = None,
                             rolling_window: dict | None = None,
                             types: list[str] | None = None,
                             units: dict | None = None) -> dict:
    """Query statistics for a single statistic_id over a time period.

    At least one of fixed_period, calendar, or rolling_window must be provided.

    WS command: recorder/statistic_during_period (singular)

    Args:
        statistic_id: The statistic identifier to query.
        fixed_period: Period definition with start/end times.
        calendar: Period definition using calendar dates.
        rolling_window: Rolling time window definition.
        types: List of statistic types to include (e.g., ["max", "min"]).
        units: Unit overrides per statistic_id.
    """
    if not statistic_id:
        raise ValueError("statistic_id is required")
    if not any(x is not None for x in [fixed_period, calendar, rolling_window]):
        raise ValueError(
            "at least one of fixed_period, calendar, or rolling_window is required"
        )
    payload: dict = {"statistic_id": statistic_id}
    if fixed_period is not None:
        payload["fixed_period"] = fixed_period
    if calendar is not None:
        payload["calendar"] = calendar
    if rolling_window is not None:
        payload["rolling_window"] = rolling_window
    if types is not None:
        payload["types"] = types
    if units is not None:
        payload["units"] = units
    return client.ws_call("recorder/statistic_during_period", payload) or {}
