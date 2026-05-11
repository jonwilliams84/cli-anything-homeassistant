"""Config entry management — list, get, delete, reload, disable."""

from __future__ import annotations

from typing import Any


def list_entries(client, domain: str | None = None) -> list[dict]:
    """Return all config entries, optionally filtered by integration domain."""
    payload = {"domain": domain} if domain else None
    data = client.ws_call("config_entries/get", payload)
    if not isinstance(data, list):
        return []
    return data


def get_entry(client, entry_id: str) -> dict | None:
    """Return a single config entry by ID, or None if not found."""
    if not entry_id:
        raise ValueError("entry_id is required")
    for e in list_entries(client):
        if e.get("entry_id") == entry_id:
            return e
    return None


def delete_entry(client, entry_id: str) -> dict:
    """Remove a config entry. Uses the REST endpoint (no WS equivalent).

    Returns the response dict — typically `{"require_restart": <bool>}`.
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    return client.delete(f"config/config_entries/entry/{entry_id}")


def reload_entry(client, entry_id: str) -> dict:
    """Reload a config entry without restarting HA.

    Uses the REST endpoint (the WS command `config_entries/reload` was removed
    in modern HA — `homeassistant.reload_config_entry` is the service-based
    equivalent, but this REST call is the most direct invocation).
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    return client.post(f"config/config_entries/entry/{entry_id}/reload")


def update_entry(client, entry_id: str, *, options: dict | None = None,
                 title: str | None = None) -> dict:
    """Update a config entry's title and/or its in-memory options dict.

    Note: this updates `entry.title` and `entry.data` directly via the
    `config_entries/update` WS command. To run the integration's full
    options-flow (which validates and persists user input), use
    `options_flow_init` + `options_flow_configure` instead.
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    payload: dict[str, object] = {"entry_id": entry_id}
    if options is not None:
        payload["data"] = options
    if title is not None:
        payload["title"] = title
    return client.ws_call("config_entries/update", payload)


def options_flow_init(client, entry_id: str) -> dict:
    """Start an options flow for an entry, returning the form descriptor.

    The returned dict contains `flow_id`, `step_id`, `data_schema`, and
    `description_placeholders`. Use the `flow_id` with
    `options_flow_configure()` to submit user input.
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    return client.post("config/config_entries/options/flow",
                       {"handler": entry_id})


def options_flow_configure(client, flow_id: str, user_input: dict) -> dict:
    """Submit user input to an active options flow, returning the result."""
    if not flow_id:
        raise ValueError("flow_id is required")
    return client.post(f"config/config_entries/options/flow/{flow_id}",
                       user_input or {})


def options_flow_set(client, entry_id: str, user_input: dict) -> dict:
    """Convenience: init + configure in one call.

    Starts an options flow on the entry, immediately submits the provided
    user_input, and returns the final result. Use this when you just want
    to overwrite an entry's options without inspecting the schema first.
    """
    init = options_flow_init(client, entry_id)
    flow_id = init.get("flow_id")
    if not flow_id:
        raise ValueError(f"options flow did not return flow_id: {init!r}")
    return options_flow_configure(client, flow_id, user_input)


# ─── config-FLOW (new-integration creation) ─────────────────────────────────

def flow_init(client, handler: str, *,
               show_advanced_options: bool = False) -> dict:
    """Start a new config flow for `handler` (the integration domain).

    Returns the first step's form descriptor: {flow_id, step_id,
    data_schema, type='form'|'create_entry'|'menu'|'external_step'|...}.
    """
    if not handler:
        raise ValueError("handler is required")
    payload: dict[str, Any] = {"handler": handler}
    if show_advanced_options:
        payload["show_advanced_options"] = True
    return client.post("config/config_entries/flow", payload)


def flow_configure(client, flow_id: str, user_input: dict | None = None) -> dict:
    """Submit user input to the active step of a config flow."""
    if not flow_id:
        raise ValueError("flow_id is required")
    return client.post(f"config/config_entries/flow/{flow_id}",
                       user_input or {})


def flow_abort(client, flow_id: str) -> dict:
    """Abort a flow without finishing it."""
    if not flow_id:
        raise ValueError("flow_id is required")
    return client.delete(f"config/config_entries/flow/{flow_id}")


def flow_get(client, flow_id: str) -> dict:
    """Return the current state of one flow (its latest form descriptor)."""
    if not flow_id:
        raise ValueError("flow_id is required")
    return client.get(f"config/config_entries/flow/{flow_id}")


def create(client, handler: str, user_input: dict,
            *, show_advanced_options: bool = False) -> dict:
    """Convenience: init a flow and submit `user_input` to its first step.

    Most simple integrations finish in a single step (host + creds), so this
    is the one-shot "configure this integration with these args" call.
    Multi-step flows should be driven via `flow_init` + `flow_configure`.
    """
    init = flow_init(client, handler,
                       show_advanced_options=show_advanced_options)
    flow_id = init.get("flow_id")
    if not flow_id:
        return init  # the init itself might be the final step
    return flow_configure(client, flow_id, user_input)


def disable_entry(client, entry_id: str, disabled: bool = True) -> dict:
    """Disable or enable a config entry."""
    if not entry_id:
        raise ValueError("entry_id is required")
    payload: dict[str, Any] = {"entry_id": entry_id}
    payload["disabled_by"] = "user" if disabled else None
    return client.ws_call("config_entries/disable", payload)
