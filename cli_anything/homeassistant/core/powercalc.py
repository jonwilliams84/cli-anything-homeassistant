"""Powercalc helpers — safe operations on virtual-power entries and groups.

Powercalc's config-entry options-flow API has two undocumented footguns that
this module exists to defuse:

1. **Group membership is REPLACE-on-write.** Submitting
   ``{"group_power_entities": [new_id]}`` to a group's options flow does NOT
   append — it wipes the existing list. ``add_group_members`` /
   ``remove_group_members`` fetch the current state and submit the merged
   list so a typo can't blow away 92 entries.

2. **Fixed-mode powercalc on a ``binary_sensor`` source silently no-ops.** The
   options form accepts ``power: 3000`` gated on ``binary_sensor.*`` without
   complaint, but the resulting power sensor never leaves 0 W. The relay can
   close and the dashboard estimate doesn't budge. ``create_virtual_power``
   refuses this combination and steers callers to ``power_template`` instead.

Background: a 2026-05-12 session lost 92+ entities across 4 groups to (1),
and missed a 3 900 W immersion-heater cycle to (2). Both bugs are silent
in raw API usage.
"""

from __future__ import annotations

from typing import Any, Iterable


POWERCALC_DOMAIN = "powercalc"

# Source-entity domains for which powercalc's fixed-mode `power: <number>`
# form is known not to gate state changes. Use `power_template` instead.
_BAD_FIXED_DOMAINS = frozenset({"binary_sensor"})


# ── group membership ───────────────────────────────────────────────────────

def get_group_members(client, sensor_entity_id: str) -> list[str]:
    """Return the resolved entity list for a powercalc group's power sensor.

    Reads ``state.attributes.entities``. For groups built via ``sub_groups``
    this is the *flattened leaf list*, not the sub-group config-entry IDs.
    """
    if not sensor_entity_id:
        raise ValueError("sensor_entity_id is required")
    state = client.get(f"states/{sensor_entity_id}")
    return list(state.get("attributes", {}).get("entities", []))


def _open_group_custom(client, entry_id: str) -> str:
    """Open the options flow on a group entry and advance to `group_custom`.

    Returns the flow_id, ready for a subsequent POST with the desired payload.
    Raises if the entry's options flow doesn't expose a `group_custom` step.
    """
    init = client.post(
        "config/config_entries/options/flow", {"handler": entry_id},
    )
    flow_id = init.get("flow_id")
    if not flow_id:
        raise RuntimeError(
            f"Could not open options flow for {entry_id}: {init!r}",
        )
    if init.get("type") == "menu":
        options = init.get("menu_options") or []
        if "group_custom" not in options:
            raise RuntimeError(
                f"Entry {entry_id} options-flow has no `group_custom` step "
                f"(menu options: {options}). Not a powercalc group entry?",
            )
        resp = client.post(
            f"config/config_entries/options/flow/{flow_id}",
            {"next_step_id": "group_custom"},
        )
        if resp.get("type") != "form":
            raise RuntimeError(
                f"Expected `form` after selecting group_custom, got "
                f"{resp.get('type')!r}: {resp!r}",
            )
    return flow_id


def set_group_members(client, entry_id: str, *,
                       power_entities: list[str] | None = None,
                       sub_groups: list[str] | None = None,
                       energy_entities: list[str] | None = None,
                       ) -> dict:
    """REPLACE a group's membership with the supplied list(s).

    Each list-typed kwarg is independent. Kwargs left as ``None`` are simply
    not submitted (powercalc keeps the existing value). To clear a field,
    pass ``[]``.

    DESTRUCTIVE: this is the operation that wipes membership if used wrong.
    Prefer :func:`add_group_members` / :func:`remove_group_members` unless
    you really do want to replace the whole list.
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    payload: dict[str, Any] = {}
    if power_entities is not None:
        payload["group_power_entities"] = list(power_entities)
    if sub_groups is not None:
        payload["sub_groups"] = list(sub_groups)
    if energy_entities is not None:
        payload["group_energy_entities"] = list(energy_entities)
    if not payload:
        raise ValueError(
            "Provide at least one of power_entities / sub_groups / "
            "energy_entities",
        )
    flow_id = _open_group_custom(client, entry_id)
    return client.post(
        f"config/config_entries/options/flow/{flow_id}", payload,
    )


def add_group_members(client, entry_id: str, *,
                       sensor_entity_id: str,
                       entities: Iterable[str]) -> dict:
    """SAFELY add entities to a group's ``group_power_entities`` list.

    Reads the current resolved entity list from the group's power sensor,
    merges in the new ones (de-duplicated, original order preserved), and
    submits the full merged list. Prevents the REPLACE-on-write footgun.

    Only works for groups configured with flat ``group_power_entities``,
    not for sub-group-based rollups. For sub-group rollups, edit the leaf
    group instead and let the cascade carry the change upward.
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    if not sensor_entity_id:
        raise ValueError(
            "sensor_entity_id is required to read current members safely",
        )
    new_entities = list(entities)
    if not new_entities:
        raise ValueError("entities must be a non-empty iterable")
    current = get_group_members(client, sensor_entity_id)
    merged = list(dict.fromkeys(current + new_entities))
    return set_group_members(client, entry_id, power_entities=merged)


def remove_group_members(client, entry_id: str, *,
                          sensor_entity_id: str,
                          entities: Iterable[str]) -> dict:
    """SAFELY remove entities from a group's ``group_power_entities`` list.

    Reads the current resolved entity list, removes the supplied entities,
    and submits what's left. If the resulting list is empty an empty list
    is submitted (caller's choice whether to also delete the group entry).
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    if not sensor_entity_id:
        raise ValueError(
            "sensor_entity_id is required to read current members safely",
        )
    drop = set(entities)
    if not drop:
        raise ValueError("entities must be a non-empty iterable")
    current = get_group_members(client, sensor_entity_id)
    remaining = [e for e in current if e not in drop]
    return set_group_members(client, entry_id, power_entities=remaining)


# ── virtual_power creation ────────────────────────────────────────────────

def create_virtual_power(
    client,
    *,
    source_entity: str,
    name: str,
    power: float | None = None,
    power_template: str | None = None,
    standby_power: float = 0,
    create_energy_sensor: bool = True,
    create_utility_meters: bool = False,
    groups: list[str] | None = None,
) -> dict:
    """Create a powercalc ``virtual_power`` config entry in fixed mode.

    Supply exactly one of:

    * ``power=<number>``         — constant wattage when source is "on"
    * ``power_template=<jinja>`` — Jinja template evaluated each tick

    For ``binary_sensor.*`` sources you MUST use ``power_template``.
    Powercalc's ``fixed: <number>`` form does not gate on binary_sensor
    state — the resulting sensor stays at 0 W even when the source flips
    to ``on``. This function raises ``ValueError`` if you try.

    Returns the final flow response (typically ``type=create_entry`` with
    ``result.entry_id``).
    """
    if not source_entity:
        raise ValueError("source_entity is required")
    if not name:
        raise ValueError("name is required")
    if power is None and power_template is None:
        raise ValueError("Provide either power= or power_template=")
    if power is not None and power_template is not None:
        raise ValueError("Provide only one of power= or power_template=")

    domain = source_entity.split(".", 1)[0]
    if domain in _BAD_FIXED_DOMAINS and power is not None:
        suggested = (
            f"\"{{{{ {power} if is_state('{source_entity}', 'on') else 0 }}}}\""
        )
        raise ValueError(
            f"Source `{source_entity}` is a {domain!r} — powercalc's "
            f"fixed-mode `power: <number>` form does not gate on {domain} "
            f"state and the resulting sensor will be stuck at 0 W. Use "
            f"`power_template=` with an explicit `is_state(...)` check "
            f"instead, e.g.:\n  power_template={suggested}",
        )

    init = client.post(
        "config/config_entries/flow", {"handler": POWERCALC_DOMAIN},
    )
    flow_id = init["flow_id"]
    client.post(
        f"config/config_entries/flow/{flow_id}",
        {"next_step_id": "virtual_power"},
    )
    client.post(f"config/config_entries/flow/{flow_id}", {
        "entity_id": source_entity,
        "name": name,
        "mode": "fixed",
        "create_energy_sensor": create_energy_sensor,
        "create_utility_meters": create_utility_meters,
        "standby_power": standby_power,
    })

    fixed_payload: dict[str, Any] = (
        {"power_template": power_template}
        if power_template is not None else {"power": power}
    )
    resp = client.post(
        f"config/config_entries/flow/{flow_id}", fixed_payload,
    )

    if resp.get("step_id") == "assign_groups":
        resp = client.post(
            f"config/config_entries/flow/{flow_id}",
            {"group": list(groups or [])},
        )

    while resp.get("type") == "form":
        resp = client.post(f"config/config_entries/flow/{flow_id}", {})

    return resp
