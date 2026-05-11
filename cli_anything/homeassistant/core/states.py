"""Entity state operations against /api/states."""

from __future__ import annotations

from typing import Any


def list_states(client, domain: str | None = None) -> list[dict]:
    """Return all entity states; optionally filter by domain."""
    data = client.get("states")
    if not isinstance(data, list):
        return []
    if domain:
        return [s for s in data if str(s.get("entity_id", "")).startswith(f"{domain}.")]
    return data


def get_state(client, entity_id: str) -> dict:
    """Return the state of a single entity."""
    if not entity_id:
        raise ValueError("entity_id cannot be empty")
    return client.get(f"states/{entity_id}")


def set_state(
    client,
    entity_id: str,
    state: str,
    attributes: dict | None = None,
) -> dict:
    """Create or update an entity state (POST /api/states/<entity_id>)."""
    if not entity_id:
        raise ValueError("entity_id cannot be empty")
    payload: dict[str, Any] = {"state": state}
    if attributes:
        payload["attributes"] = attributes
    return client.post(f"states/{entity_id}", payload)


def list_domains(client) -> list[str]:
    """Return the unique sorted list of domains found in current states."""
    domains: set[str] = set()
    for s in list_states(client):
        eid = s.get("entity_id", "")
        if "." in eid:
            domains.add(eid.split(".", 1)[0])
    return sorted(domains)


def count_by_domain(client) -> dict[str, int]:
    """Return {domain: count} for all currently loaded entities."""
    counts: dict[str, int] = {}
    for s in list_states(client):
        eid = s.get("entity_id", "")
        if "." in eid:
            d = eid.split(".", 1)[0]
            counts[d] = counts.get(d, 0) + 1
    return dict(sorted(counts.items()))
