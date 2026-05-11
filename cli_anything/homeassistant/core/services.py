"""Service registry + service calls (/api/services)."""

from __future__ import annotations

from typing import Any


def list_services(client, domain: str | None = None) -> list[dict]:
    """Return the service registry. If `domain` is set, return only that domain's services."""
    data = client.get("services")
    if not isinstance(data, list):
        return []
    if domain:
        return [d for d in data if d.get("domain") == domain]
    return data


def list_domains(client) -> list[str]:
    """Return the sorted list of service domains."""
    data = list_services(client)
    return sorted({d.get("domain") for d in data if d.get("domain")})


def call_service(
    client,
    domain: str,
    service: str,
    service_data: dict | None = None,
    target: dict | None = None,
    return_response: bool = False,
) -> Any:
    """Call a Home Assistant service.

    `service_data` becomes the request body. `target` (entity_id/area_id/device_id)
    is folded into the body — that's how Home Assistant's REST endpoint accepts it.
    """
    if not domain or not service:
        raise ValueError("domain and service are required")
    payload: dict[str, Any] = {}
    if service_data:
        payload.update(service_data)
    if target:
        payload.update(target)
    path = f"services/{domain}/{service}"
    if return_response:
        path += "?return_response"
    return client.post(path, payload)
