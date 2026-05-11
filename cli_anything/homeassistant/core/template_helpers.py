"""Create / update template-based helpers (template sensor, binary_sensor,
number, switch, select, button).

These are UI-created helpers that live as config_entries with domain
``template``. WLED 16 ... err, HA 2024+ exposes their lifecycle through
a REST options-flow API:

  POST /api/config/config_entries/flow  {"handler": "template", ...}
  POST /api/config/config_entries/flow/<flow_id>  {"next_step_id": "sensor"}
  POST /api/config/config_entries/flow/<flow_id>  {"name": ..., "state": ...}

The ``config_entry`` module already wraps the options-flow API for
UPDATING existing template helpers; this module covers CREATION (a
distinct API endpoint) and adds template-specific conveniences.
"""

from __future__ import annotations

from typing import Any


VALID_TYPES = {
    "sensor",
    "binary_sensor",
    "number",
    "switch",
    "select",
    "button",
}


def create(client, *, name: str, state_template: str,
            template_type: str = "sensor",
            unit_of_measurement: str | None = None,
            device_class: str | None = None,
            state_class: str | None = None,
            extra: dict | None = None) -> dict:
    """Create a UI-style template helper.

    Args:
        name: visible name (also becomes the entity slug).
        state_template: Jinja2 template that renders the state.
        template_type: one of "sensor", "binary_sensor", "number",
            "switch", "select", "button".
        unit_of_measurement: optional unit (e.g. "Mbps", "%").
        device_class: optional HA device_class.
        state_class: optional state_class (e.g. "measurement").
        extra: any additional fields HA expects for this template_type
            (e.g. for "binary_sensor" you may pass {"delay_on": "00:00:30"}).

    Returns the response from the final flow step (typically
    ``{"type": "create_entry", "title": "...", "result": {...}}``).
    """
    if template_type not in VALID_TYPES:
        raise ValueError(f"template_type must be one of {sorted(VALID_TYPES)}; "
                          f"got {template_type!r}")
    if not name:
        raise ValueError("name is required")
    if not state_template:
        raise ValueError("state_template is required")

    # Step 1: initiate the config-flow for the template integration.
    init = client.post("config/config_entries/flow",
                       {"handler": "template", "show_advanced_options": False})
    flow_id = init.get("flow_id")
    if not flow_id:
        raise RuntimeError(f"template flow init failed: {init!r}")

    # Step 2: pick the template type (sensor / binary_sensor / ...).
    client.post(f"config/config_entries/flow/{flow_id}",
                {"next_step_id": template_type})

    # Step 3: submit the helper's config.
    payload: dict[str, Any] = {
        "name": name,
        "state": state_template.strip(),
    }
    if unit_of_measurement:
        payload["unit_of_measurement"] = unit_of_measurement
    if device_class:
        payload["device_class"] = device_class
    if state_class:
        payload["state_class"] = state_class
    if extra:
        payload.update(extra)

    return client.post(f"config/config_entries/flow/{flow_id}", payload)


def update(client, entry_id: str, *, name: str | None = None,
            state_template: str | None = None,
            unit_of_measurement: str | None = None,
            device_class: str | None = None,
            state_class: str | None = None,
            extra: dict | None = None) -> dict:
    """Update an existing template helper's state template / options.

    Uses ``options-flow`` (init + configure), which is the documented way
    to mutate a UI-created helper. Any fields you don't pass are pulled
    from the current entry's options so we don't blow them away.
    """
    if not entry_id:
        raise ValueError("entry_id is required")

    # Pull current options to preserve untouched fields.
    init = client.post("config/config_entries/options/flow",
                       {"handler": entry_id})
    flow_id = init.get("flow_id")
    if not flow_id:
        raise RuntimeError(f"options flow init failed: {init!r}")
    schema = init.get("data_schema", [])
    current: dict[str, Any] = {}
    for f in schema:
        if isinstance(f, dict) and "name" in f:
            desc = f.get("description") or {}
            if "suggested_value" in desc:
                current[f["name"]] = desc["suggested_value"]

    # Apply caller's overrides.
    if name is not None:                current["name"] = name
    if state_template is not None:      current["state"] = state_template.strip()
    if unit_of_measurement is not None: current["unit_of_measurement"] = unit_of_measurement
    if device_class is not None:        current["device_class"] = device_class
    if state_class is not None:         current["state_class"] = state_class
    if extra:                           current.update(extra)

    return client.post(f"config/config_entries/flow/{flow_id}", current)


def show(client, ident: str) -> dict:
    """Return the current options of a template-helper config entry.

    ``ident`` may be the config entry id (e.g. `01KR9E7CTQK...`) or the entity
    id of any entity the helper produces (e.g. `sensor.k8s_cluster_online_label`).
    The lookup-by-entity path resolves via the entity registry.
    """
    if not ident:
        raise ValueError("ident is required")

    entry_id: str | None = None
    if "." in ident:
        # entity_id — resolve via entity registry
        ents = client.ws_call("config/entity_registry/list") or []
        for e in ents:
            if e.get("entity_id") == ident:
                entry_id = e.get("config_entry_id")
                break
        if not entry_id:
            raise KeyError(f"no config_entry_id linked to entity {ident!r}")
    else:
        entry_id = ident

    # Use options-flow init to read the current values — but DON'T submit.
    init = client.post("config/config_entries/options/flow",
                       {"handler": entry_id})
    flow_id = init.get("flow_id")
    schema = init.get("data_schema", []) or []
    current: dict[str, Any] = {}
    for f in schema:
        if isinstance(f, dict) and "name" in f:
            desc = f.get("description") or {}
            if "suggested_value" in desc:
                current[f["name"]] = desc["suggested_value"]

    # Abort the flow so we don't leave it hanging.
    if flow_id:
        try:
            client.request("DELETE", f"config/config_entries/options/flow/{flow_id}")
        except Exception:
            pass

    # Also pull the entry's basic metadata for context
    try:
        entry_meta = client.ws_call("config_entries/get",
                                       {"entry_id": entry_id}) or {}
    except Exception:
        entry_meta = {}

    return {
        "entry_id": entry_id,
        "title": entry_meta.get("title"),
        "domain": entry_meta.get("domain"),
        "options": current,
    }
