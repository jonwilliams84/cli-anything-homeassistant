"""Per-domain helpers (turn_on / turn_off / toggle / set).

These map to the standard service calls every controllable domain in HA
provides (`light`, `switch`, `fan`, `cover`, `media_player`, `input_boolean`,
`scene`, `climate`, ...).
"""

from __future__ import annotations

from typing import Any

from cli_anything.homeassistant.core import services as services_core
from cli_anything.homeassistant.core import states as states_core


_TOGGLABLE_DOMAINS = {
    "automation",
    "climate",
    "cover",
    "fan",
    "humidifier",
    "input_boolean",
    "light",
    "media_player",
    "remote",
    "scene",
    "script",
    "siren",
    "switch",
    "vacuum",
    "water_heater",
}


def list_entities(client, domain: str) -> list[dict]:
    """Return entities for the given domain."""
    return states_core.list_states(client, domain=domain)


def _service_call(
    client,
    domain: str,
    service: str,
    entity_id: str | None,
    extra: dict | None = None,
) -> Any:
    target = {"entity_id": entity_id} if entity_id else None
    return services_core.call_service(client, domain, service, service_data=extra, target=target)


def turn_on(client, domain: str, entity_id: str | None = None, extra: dict | None = None) -> Any:
    if domain not in _TOGGLABLE_DOMAINS:
        raise ValueError(
            f"Domain '{domain}' is not a known controllable domain. "
            f"Use `service call` directly."
        )
    return _service_call(client, domain, "turn_on", entity_id, extra)


def turn_off(client, domain: str, entity_id: str | None = None, extra: dict | None = None) -> Any:
    if domain not in _TOGGLABLE_DOMAINS:
        raise ValueError(
            f"Domain '{domain}' is not a known controllable domain. "
            f"Use `service call` directly."
        )
    return _service_call(client, domain, "turn_off", entity_id, extra)


def toggle(client, domain: str, entity_id: str | None = None, extra: dict | None = None) -> Any:
    if domain not in _TOGGLABLE_DOMAINS:
        raise ValueError(
            f"Domain '{domain}' is not a known controllable domain. "
            f"Use `service call` directly."
        )
    return _service_call(client, domain, "toggle", entity_id, extra)
