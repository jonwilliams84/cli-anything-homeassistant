"""Script helpers — thin wrappers over the script domain services."""

from __future__ import annotations

from cli_anything.homeassistant.core import services as services_core
from cli_anything.homeassistant.core import states as states_core


def list_scripts(client) -> list[dict]:
    return states_core.list_states(client, domain="script")


def run(client, entity_id: str, variables: dict | None = None) -> dict:
    if not entity_id.startswith("script."):
        raise ValueError(f"Expected a script entity_id, got: {entity_id}")
    return services_core.call_service(
        client, "script", "turn_on",
        service_data={"variables": variables} if variables else None,
        target={"entity_id": entity_id},
    )


def reload(client) -> dict:
    return services_core.call_service(client, "script", "reload")


def get_config(client, entity_id: str) -> dict:
    """Return the full config for a UI-managed script."""
    if not entity_id.startswith("script."):
        raise ValueError(f"Expected a script entity_id, got: {entity_id}")
    object_id = entity_id.split(".", 1)[1]
    response = client.ws_call("script/config", {"entity_id": entity_id})
    if isinstance(response, dict) and "config" in response:
        return response["config"]
    if isinstance(response, dict):
        return response
    # Fall back to REST.
    return client.get(f"config/script/config/{object_id}")


def save_config(client, entity_id: str, config: dict) -> dict:
    """Save (replace) the config for a UI-managed script. Requires admin."""
    if not entity_id.startswith("script."):
        raise ValueError(f"Expected a script entity_id, got: {entity_id}")
    if not isinstance(config, dict):
        raise ValueError("config must be a dict")
    object_id = entity_id.split(".", 1)[1]
    return client.post(f"config/script/config/{object_id}", config)


def _script_item_id(client, entity_id: str) -> str:
    """The trace API addresses scripts by their `object_id` (the part after the dot).

    Returns the bare object_id for use with `trace/list` / `trace/get`.
    """
    if not entity_id.startswith("script."):
        raise ValueError(f"Expected a script entity_id, got: {entity_id}")
    return entity_id.split(".", 1)[1]


def list_traces(client, entity_id: str) -> list[dict]:
    """List recent execution traces for a script (most recent last).

    HA keeps a small ring buffer (default 5) per script.
    """
    item_id = _script_item_id(client, entity_id)
    result = client.ws_call("trace/list", {"domain": "script",
                                              "item_id": item_id})
    return result if isinstance(result, list) else []


def get_trace(client, entity_id: str, run_id: str | None = None) -> dict:
    """Return the full trace dict for a single script run.

    If ``run_id`` is omitted, fetches the MOST RECENT trace.
    """
    item_id = _script_item_id(client, entity_id)
    if run_id is None:
        traces = client.ws_call("trace/list", {"domain": "script",
                                                  "item_id": item_id}) or []
        if not traces:
            return {}
        run_id = traces[-1].get("run_id")
        if not run_id:
            return {}
    return client.ws_call("trace/get", {"domain": "script",
                                            "item_id": item_id,
                                            "run_id": run_id}) or {}


script_reload = reload
