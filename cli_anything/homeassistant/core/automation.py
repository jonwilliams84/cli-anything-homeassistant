"""Automation helpers — thin wrappers over the automation domain services."""

from __future__ import annotations

from cli_anything.homeassistant.core import services as services_core
from cli_anything.homeassistant.core import states as states_core


def list_automations(client) -> list[dict]:
    """Return automations as state entries (entity_id starts with 'automation.')."""
    return states_core.list_states(client, domain="automation")


def trigger(client, entity_id: str, skip_condition: bool = False) -> dict:
    if not entity_id.startswith("automation."):
        raise ValueError(f"Expected an automation entity_id, got: {entity_id}")
    data = {"skip_condition": skip_condition} if skip_condition else None
    return services_core.call_service(
        client, "automation", "trigger",
        service_data=data, target={"entity_id": entity_id},
    )


def toggle(client, entity_id: str) -> dict:
    return services_core.call_service(
        client, "automation", "toggle",
        target={"entity_id": entity_id},
    )


def turn_on(client, entity_id: str) -> dict:
    return services_core.call_service(
        client, "automation", "turn_on",
        target={"entity_id": entity_id},
    )


def turn_off(client, entity_id: str) -> dict:
    return services_core.call_service(
        client, "automation", "turn_off",
        target={"entity_id": entity_id},
    )


def reload(client) -> dict:
    return services_core.call_service(client, "automation", "reload")


def get_config(client, entity_id: str) -> dict:
    """Return the full YAML/JSON config for a UI-managed automation."""
    if not entity_id.startswith("automation."):
        raise ValueError(f"Expected an automation entity_id, got: {entity_id}")
    response = client.ws_call("automation/config", {"entity_id": entity_id})
    if isinstance(response, dict) and "config" in response:
        return response["config"]
    return response or {}


def _automation_item_id(client, entity_id: str) -> str:
    """The trace API addresses automations by their numeric `id` (from
    the YAML/UI config), not the entity_id slug. Resolve via get_config.
    """
    if not entity_id.startswith("automation."):
        raise ValueError(f"Expected an automation entity_id, got: {entity_id}")
    cfg = get_config(client, entity_id)
    item_id = cfg.get("id") if isinstance(cfg, dict) else None
    if not item_id:
        raise ValueError(
            f"could not resolve numeric `id` for {entity_id!r} "
            "(needed by trace/list — automations defined in YAML may "
            "not have one)"
        )
    return str(item_id)


def list_traces(client, entity_id: str) -> list[dict]:
    """List recent execution traces for an automation (most recent last).

    HA keeps a small ring buffer (default 5 traces) per automation.
    """
    item_id = _automation_item_id(client, entity_id)
    result = client.ws_call("trace/list", {"domain": "automation",
                                              "item_id": item_id})
    return result if isinstance(result, list) else []


def get_trace(client, entity_id: str, run_id: str | None = None) -> dict:
    """Return the full trace dict for a single run.

    If ``run_id`` is omitted, fetches the MOST RECENT trace.
    """
    item_id = _automation_item_id(client, entity_id)
    if run_id is None:
        traces = client.ws_call("trace/list", {"domain": "automation",
                                                  "item_id": item_id}) or []
        if not traces:
            return {}
        run_id = traces[-1].get("run_id")
        if not run_id:
            return {}
    return client.ws_call("trace/get", {"domain": "automation",
                                            "item_id": item_id,
                                            "run_id": run_id}) or {}


def save_config(client, entity_id: str, config: dict) -> dict:
    """Save (replace) the config for a UI-managed automation.

    Uses the REST endpoint that the HA UI uses internally. Requires admin.
    `config` must include the matching `id` field.
    """
    if not entity_id.startswith("automation."):
        raise ValueError(f"Expected an automation entity_id, got: {entity_id}")
    if not isinstance(config, dict):
        raise ValueError("config must be a dict")
    auto_id = config.get("id")
    if not auto_id:
        raise ValueError("config['id'] is required")
    return client.post(f"config/automation/config/{auto_id}", config)
