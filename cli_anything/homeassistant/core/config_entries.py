"""Config entry management — list, get, delete, reload, disable."""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


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


def update_entry(
    client, entry_id: str, *, options: dict | None = None, title: str | None = None
) -> dict:
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
    return client.post("config/config_entries/options/flow", {"handler": entry_id})


def options_flow_configure(client, flow_id: str, user_input: dict) -> dict:
    """Submit user input to an active options flow, returning the result."""
    if not flow_id:
        raise ValueError("flow_id is required")
    return client.post(f"config/config_entries/options/flow/{flow_id}", user_input or {})


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


def flow_init(client, handler: str, *, show_advanced_options: bool = False) -> dict:
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
    return client.post(f"config/config_entries/flow/{flow_id}", user_input or {})


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


def create(client, handler: str, user_input: dict, *, show_advanced_options: bool = False) -> dict:
    """Convenience: init a flow and submit `user_input` to its first step.

    Most simple integrations finish in a single step (host + creds), so this
    is the one-shot "configure this integration with these args" call.
    Multi-step flows should be driven via `flow_init` + `flow_configure`.
    """
    init = flow_init(client, handler, show_advanced_options=show_advanced_options)
    flow_id = init.get("flow_id")
    if not flow_id:
        return init  # the init itself might be the final step
    return flow_configure(client, flow_id, user_input)


def walk(
    client,
    handler: str,
    steps: list[dict],
    *,
    show_advanced_options: bool = False,
    stop_on_form: bool = False,
) -> dict:
    """Drive a multi-step config flow: init → step → step → ...

    `steps` is the list of form payloads, one per step. The flow is
    expected to terminate after `len(steps)` submissions; if it doesn't
    (and `stop_on_form` is False), the remaining form is returned in the
    result for the caller to inspect.

    Returns: {flow_id, history: [{step_id, type, response}, ...],
              final: <last response>, completed: bool}.

    Aborts the flow on any error and includes the partial history.
    """
    if not handler:
        raise ValueError("handler is required")
    if not isinstance(steps, list):
        raise ValueError("steps must be a list of dicts")

    history: list[dict] = []
    current = flow_init(client, handler, show_advanced_options=show_advanced_options)
    flow_id = current.get("flow_id")
    history.append(
        {
            "step": "init",
            "type": current.get("type"),
            "step_id": current.get("step_id"),
            "response": current,
        }
    )
    if current.get("type") in ("create_entry", "abort"):
        return {"flow_id": flow_id, "history": history, "final": current, "completed": True}
    if not flow_id:
        return {"flow_id": None, "history": history, "final": current, "completed": False}

    completed = False
    for i, payload in enumerate(steps):
        try:
            resp = flow_configure(client, flow_id, payload)
        except Exception as exc:
            try:
                flow_abort(client, flow_id)
            except Exception as abort_exc:  # noqa: BLE001 — best-effort cleanup
                _LOGGER.debug(
                    "flow_abort failed while cleaning up flow %s: %s",
                    flow_id,
                    abort_exc,
                )
            history.append({"step": f"submit[{i}]", "error": str(exc), "payload": payload})
            return {"flow_id": flow_id, "history": history, "final": None, "completed": False}
        history.append(
            {
                "step": f"submit[{i}]",
                "type": resp.get("type"),
                "step_id": resp.get("step_id"),
                "response": resp,
            }
        )
        if resp.get("type") in ("create_entry", "abort"):
            completed = True
            return {"flow_id": flow_id, "history": history, "final": resp, "completed": True}
        if resp.get("type") == "form" and stop_on_form:
            return {"flow_id": flow_id, "history": history, "final": resp, "completed": False}

    # Ran out of payloads but flow isn't done.
    return {
        "flow_id": flow_id,
        "history": history,
        "final": current if not history else history[-1].get("response"),
        "completed": completed,
    }


def disable_entry(client, entry_id: str, disabled: bool = True) -> dict:
    """Disable or enable a config entry."""
    if not entry_id:
        raise ValueError("entry_id is required")
    payload: dict[str, Any] = {"entry_id": entry_id}
    payload["disabled_by"] = "user" if disabled else None
    return client.ws_call("config_entries/disable", payload)


# ─── the discovery half: flows HA started BY ITSELF ─────────────────────────
#
# Everything above initiates a flow the operator asked for. HA also starts
# flows on its own — a hub found by mDNS, a device that needs re-auth after a
# password change, an integration asking to be reconfigured. Those are what the
# "N discovered" badge on the frontend counts, and until now this harness could
# neither see nor dismiss them, which meant an instance could sit for months
# with a broken re-auth flow that nothing on the command line could report.


def flows_in_progress(client) -> list[dict]:
    """Flows HA started that are waiting on a human (`config_entries/flow/progress`).

    HA FILTERS OUT `source == "user"` server-side, so this never returns a flow
    the operator started — by construction it is the discovered/re-auth/
    reconfigure set and nothing else. An empty list is the healthy state.

    `context.source` is the field worth reading: `reauth` means an integration
    has stopped working and is asking for credentials; `discovery`/`zeroconf`/
    `dhcp`/`ssdp` mean something new appeared on the network.
    """
    data = client.ws_call("config_entries/flow/progress")
    if not isinstance(data, list):
        return []
    return data


def flows_needing_attention(client) -> dict:
    """`flows_in_progress` grouped by what it means, because sources are not equal.

    A `reauth` flow is an integration that has ALREADY stopped working; a
    discovery flow is an offer. Reporting them in one flat list invites
    treating them the same. Broken things are counted separately.
    """
    flows = flows_in_progress(client)
    reauth, reconfigure, discovered = [], [], []
    for flow in flows:
        source = ((flow.get("context") or {}).get("source") or "").lower()
        row = {
            "flow_id": flow.get("flow_id"),
            "handler": flow.get("handler"),
            "source": source,
            "step_id": flow.get("step_id"),
            "title": flow.get("context", {}).get("title_placeholders"),
            "unique_id": (flow.get("context") or {}).get("unique_id"),
            "ignorable": "unique_id" in (flow.get("context") or {}),
        }
        if source == "reauth":
            reauth.append(row)
        elif source == "reconfigure":
            reconfigure.append(row)
        else:
            discovered.append(row)
    return {
        "total": len(flows),
        "broken": len(reauth),
        "reauth": reauth,
        "reconfigure": reconfigure,
        "discovered": discovered,
        "note": (
            "`reauth` means an integration has already stopped working and is "
            "asking for credentials — it is not an offer. `ignorable: false` "
            "means the flow has no unique_id and `ignore` will refuse it."
        ),
    }


def ignore_flow(client, flow_id: str, title: str) -> dict:
    """Dismiss a discovered flow for good (`config_entries/ignore_flow`).

    This is not `abort`. Aborting closes the flow and HA re-discovers the same
    device on the next scan; ignoring writes an `ignore`-source config entry
    with the flow's `unique_id`, which suppresses it permanently (until that
    entry is deleted).

    HA requires the flow to have a `unique_id` in its context and answers
    `no_unique_id` otherwise; a flow_id that is not in progress comes back as
    "Config entry not found", which is confusing but means the flow, not an
    entry. `title` is required — it is what the ignored entry is called in the
    integrations list, and it is the only trace left of what was dismissed.
    """
    if not flow_id:
        raise ValueError("flow_id is required — see `config-flow progress`")
    if not title:
        raise ValueError(
            "title is required: it names the ignored entry in the integrations "
            "list and is the only record of what was dismissed."
        )
    client.ws_call("config_entries/ignore_flow", {"flow_id": flow_id, "title": title})
    return {
        "ignored": True,
        "flow_id": flow_id,
        "title": title,
        "note": (
            "An `ignore`-source config entry now holds this flow's unique_id, "
            "so HA will not offer it again. Delete that entry to un-ignore."
        ),
    }


def get_entry_single(client, entry_id: str) -> dict:
    """One config entry, asked for directly (`config_entries/get_single`).

    `get_entry()` above lists EVERY entry and filters client-side, which is a
    full registry transfer to answer a one-row question. This asks HA. The
    trade is that it is admin-only where the list is not, so both are kept:
    the scan still works on a non-admin token.

    A missing entry is `ERR_NOT_FOUND` from HA, raised by the client, rather
    than the `None` the scanning version returns.
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    data = client.ws_call("config_entries/get_single", {"entry_id": entry_id}) or {}
    entry = data.get("config_entry") if isinstance(data, dict) else None
    if not entry:
        raise ValueError(f"No config entry {entry_id!r}. `config-entry list` shows the ids.")
    return entry


def flow_handlers(client, type_filter: str | None = None) -> list[str]:
    """Every integration domain that CAN be set up from the UI/API.

    `GET /api/config/config_entries/flow_handlers`. This is the catalogue that
    `config-flow init <handler>` draws from: a domain not in this list has no
    config flow and can only be configured in YAML — which is the real answer
    to "why does `config-flow init` say it does not exist".

    `type_filter` is HA's own `type` query param: `integration`, `helper`,
    `device`, `hub` or `service`. `helper` is the interesting one — those are
    the domains behind the `helpers` group.
    """
    params = {"type": type_filter} if type_filter else None
    data = client.get("config/config_entries/flow_handlers", params)
    if not isinstance(data, list):
        return []
    return data


def remove_device(client, entry_id: str, device_id: str) -> dict:
    """Detach one device from a config entry (`config/device_registry/remove_config_entry`).

    The narrow tool that was missing: deleting the config entry removes EVERY
    device it owns, which is a sledgehammer when one stale device from a
    fifty-device hub needs to go.

    HA refuses this in four distinct ways and all four are `HomeAssistantError`
    with a plain-text reason worth reading rather than swallowing:
      * "Unknown config entry" / "Unknown device" — bad id;
      * "Config entry not in device" — the device is owned by a DIFFERENT
        entry (common on a device two integrations both see);
      * "Config entry does not support device removal" — the integration never
        implemented `async_remove_config_entry_device`, and no amount of
        retrying changes that.

    Returns the updated device entry, or `{"removed": True, "device": None}`
    when the integration deleted the device itself as part of the removal —
    which HA explicitly allows and reports as a null result.
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    if not device_id:
        raise ValueError("device_id is required")
    result = client.ws_call(
        "config/device_registry/remove_config_entry",
        {"config_entry_id": entry_id, "device_id": device_id},
    )
    return {
        "removed": True,
        "config_entry_id": entry_id,
        "device_id": device_id,
        "device": result or None,
        "note": (
            "A null `device` means the integration removed the device entry "
            "itself during the detach — that is success, not a failure."
            if not result
            else "The device survives, minus this config entry."
        ),
    }
