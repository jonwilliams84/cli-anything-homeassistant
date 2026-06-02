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

from cli_anything.homeassistant.core import config_entries as _ce


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


# ── list / reload / set-power-template ─────────────────────────────────────

def list_entries(client, *, title_contains: str | None = None,
                 state: str | None = None) -> list[dict]:
    """Return all powercalc config entries.

    Optional filters:
      * ``title_contains`` — case-insensitive substring match on entry title.
      * ``state`` — filter to entries whose ``state`` matches exactly
        (e.g. ``"loaded"``, ``"not_loaded"``, ``"setup_error"``).
    """
    entries = _ce.list_entries(client, domain=POWERCALC_DOMAIN)
    if title_contains is not None:
        needle = title_contains.lower()
        entries = [e for e in entries
                   if needle in (e.get("title") or "").lower()]
    if state is not None:
        entries = [e for e in entries if e.get("state") == state]
    return entries


def reload_entry(client, entry_id: str) -> dict:
    """Reload a powercalc config entry without restarting HA.

    Useful after editing a power_template, or when a group's flat
    ``entities`` attribute hasn't refreshed after a new leaf was added.
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    return _ce.reload_entry(client, entry_id)


def reload_groups_for_member(client, *, parent_entry_ids: list[str]) -> dict:
    """Reload the supplied parent powercalc group entries so their flat
    ``entities`` attribute regenerates after a new leaf was added.

    Common use: after :func:`create_virtual_power` joins a sub-group, the
    upstream rollup groups (e.g. Ground Floor, Home Total) still cache the
    old flat list until reloaded.

    Returns ``{parent_entry_id: <reload response>}``.
    """
    out: dict[str, dict] = {}
    for eid in parent_entry_ids:
        out[eid] = reload_entry(client, eid)
    return out


def _open_fixed_step(client, entry_id: str) -> str:
    """Open a powercalc virtual_power entry's options flow and advance to the
    ``fixed`` step, returning the flow_id ready for the next submit.

    Raises ``RuntimeError`` if the menu doesn't expose a ``fixed`` step (which
    means this is either a group entry, a non-fixed-mode entry, or an unknown
    entry type — none of which `set_power_template` can edit).
    """
    init = _ce.options_flow_init(client, entry_id)
    flow_id = init.get("flow_id")
    if not flow_id:
        raise RuntimeError(
            f"Could not open options flow for {entry_id}: {init!r}",
        )
    if init.get("type") == "menu":
        if "fixed" not in (init.get("menu_options") or []):
            raise RuntimeError(
                f"Entry {entry_id} options flow has no `fixed` step "
                f"(menu options: {init.get('menu_options')!r}). "
                f"Not a fixed-mode virtual_power entry?",
            )
        resp = _ce.options_flow_configure(
            client, flow_id, {"next_step_id": "fixed"},
        )
        if resp.get("type") != "form":
            raise RuntimeError(
                f"Expected form after selecting `fixed`, got "
                f"{resp.get('type')!r}: {resp!r}",
            )
    return flow_id


def set_power_template(client, entry_id: str, *,
                        power_template: str, reload: bool = True) -> dict:
    """Replace the ``power_template`` on a fixed-mode virtual_power entry.

    The 6-line manual flow (options-init → options-configure
    next_step_id=fixed → options-configure power_template) collapsed into
    one call. Used e.g. to bump a fan model from 24 W to 30 W:

        set_power_template(client, fan_entry_id,
            power_template="{{ 30 * ((state_attr('fan.x','percentage')|float(0))/100)**3 "
                            "if is_state('fan.x','on') else 0 }}")

    Auto-reloads the entry after the write (``reload=False`` to skip) so the
    new model takes effect on the sensor immediately — an options-flow
    ``create_entry`` does not always reload the entry on its own, which is the
    usual reason a freshly-written template "doesn't take".
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    if not power_template:
        raise ValueError("power_template is required and must be non-empty")
    flow_id = _open_fixed_step(client, entry_id)
    resp = _ce.options_flow_configure(
        client, flow_id, {"power_template": power_template},
    )
    if reload:
        try:
            reload_entry(client, entry_id)
        except Exception:  # noqa: BLE001 — reload is best-effort
            pass
    return resp


def set_fixed_power(client, entry_id: str, *, power: float,
                    reload: bool = True) -> dict:
    """Replace the fixed ``power`` (constant W) on a fixed-mode entry.

    Submits ``power`` **and clears any existing** ``power_template`` — powercalc
    gives a template precedence over the constant, so a stale template left in
    place would silently shadow the new fixed value. Auto-reloads afterwards
    (``reload=False`` to skip) so the change lands on the sensor immediately.

    Note: this sets the **on-state** power. The **off-state** standby is a
    separate field on the ``basic_options`` step — use :func:`set_standby`.
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    if power is None:
        raise ValueError("power is required")
    flow_id = _open_fixed_step(client, entry_id)
    resp = _ce.options_flow_configure(
        client, flow_id, {"power": power, "power_template": ""},
    )
    if reload:
        try:
            reload_entry(client, entry_id)
        except Exception:  # noqa: BLE001 — reload is best-effort
            pass
    return resp


# ── basic_options step: standby_power + source ─────────────────────────────

def _open_basic_step(client, entry_id: str) -> str:
    """Open a virtual_power entry's options flow and advance to the
    ``basic_options`` step (where ``standby_power`` and the source
    ``entity_id`` live — NOT the ``fixed`` step, which only has on-state
    power). Mirrors :func:`_open_fixed_step`.
    """
    init = _ce.options_flow_init(client, entry_id)
    flow_id = init.get("flow_id")
    if not flow_id:
        raise RuntimeError(
            f"Could not open options flow for {entry_id}: {init!r}",
        )
    if init.get("type") == "menu":
        if "basic_options" not in (init.get("menu_options") or []):
            raise RuntimeError(
                f"Entry {entry_id} options flow has no `basic_options` step "
                f"(menu options: {init.get('menu_options')!r}).",
            )
        resp = _ce.options_flow_configure(
            client, flow_id, {"next_step_id": "basic_options"},
        )
        if resp.get("type") != "form":
            raise RuntimeError(
                f"Expected form after selecting `basic_options`, got "
                f"{resp.get('type')!r}: {resp!r}",
            )
    return flow_id


def _source_entity_for(client, entry_id: str) -> str | None:
    """Resolve the source entity_id for a virtual_power entry by joining the
    entry title to its powercalc power sensor (``friendly_name`` minus the
    " Power" suffix → ``source_entity``). Used so :func:`set_standby` can
    re-send ``entity_id`` and never blank the source.
    """
    title = next((e.get("title") for e in list_entries(client)
                  if e.get("entry_id") == entry_id), None)
    if not title:
        return None
    target = title.strip()
    states = client.get("states")
    if not isinstance(states, list):
        return None
    for s in states:
        a = s.get("attributes") or {}
        if a.get("integration") != "powercalc":
            continue
        fn = a.get("friendly_name") or ""
        for suffix in (" Power", " power"):
            if fn.endswith(suffix):
                fn = fn[:-len(suffix)]
        if fn.strip() == target and a.get("source_entity"):
            return a["source_entity"]
    return None


def set_standby(client, entry_id: str, *, standby_power: float,
                source_entity: str | None = None,
                create_energy_sensor: bool = True,
                create_utility_meters: bool = False,
                reload: bool = True) -> dict:
    """Set the **off-state** ``standby_power`` (W) on a virtual_power entry.

    standby_power lives on the ``basic_options`` step, not ``fixed`` — so
    :func:`set_fixed_power` / :func:`set_power_template` cannot touch it. This
    drives that step. The source ``entity_id`` is re-sent (resolved
    automatically, or pass ``source_entity=`` to override) because submitting
    ``basic_options`` without it would blank the entry's source.

    Pairs with :func:`set_fixed_power`: ``set_fixed_power`` = on-state W,
    ``set_standby`` = off-state W.
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    if standby_power is None:
        raise ValueError("standby_power is required")
    src = source_entity or _source_entity_for(client, entry_id)
    if not src:
        raise RuntimeError(
            f"Could not resolve the source entity for {entry_id}; pass "
            f"source_entity= explicitly so the basic_options submit does not "
            f"blank the source.",
        )
    flow_id = _open_basic_step(client, entry_id)
    resp = _ce.options_flow_configure(client, flow_id, {
        "entity_id": src,
        "standby_power": standby_power,
        "create_energy_sensor": create_energy_sensor,
        "create_utility_meters": create_utility_meters,
    })
    if reload:
        try:
            reload_entry(client, entry_id)
        except Exception:  # noqa: BLE001 — reload is best-effort
            pass
    return resp


def read_entry(client, entry_id: str) -> dict:
    """Best-effort read of a virtual_power entry's live + configured state.

    The REST/WS config-entry list doesn't expose powercalc options, so we
    combine two sources:
      * the live power sensor's attributes (``calculation_mode``,
        ``source_entity``) and current value — reliable; and
      * the options-flow forms' ``suggested_value``s for ``power`` /
        ``power_template`` / ``standby_power`` — surfaced when HA includes
        them, else omitted.
    """
    entries = list_entries(client)
    meta = next((e for e in entries if e.get("entry_id") == entry_id), None)
    out: dict[str, Any] = {
        "entry_id": entry_id,
        "title": meta.get("title") if meta else None,
        "state": meta.get("state") if meta else None,
        "calculation_mode": None,
        "source_entity": None,
        "current_power_w": None,
        "configured": {},
    }
    if meta:
        target = (meta.get("title") or "").strip()
        states = client.get("states")
        if isinstance(states, list):
            for s in states:
                a = s.get("attributes") or {}
                if a.get("integration") != "powercalc":
                    continue
                fn = a.get("friendly_name") or ""
                for suffix in (" Power", " power"):
                    if fn.endswith(suffix):
                        fn = fn[:-len(suffix)]
                if fn.strip() == target:
                    out["calculation_mode"] = a.get("calculation_mode")
                    out["source_entity"] = a.get("source_entity")
                    try:
                        out["current_power_w"] = float(s.get("state"))
                    except (TypeError, ValueError):
                        pass
                    break
    # Best-effort configured values from the options-flow forms.
    try:
        configured: dict[str, Any] = {}
        for step, names in (("basic_options", ("standby_power",)),
                            ("fixed", ("power", "power_template"))):
            init = _ce.options_flow_init(client, entry_id)
            fid = init.get("flow_id")
            if not fid:
                continue
            form = (_ce.options_flow_configure(client, fid,
                                               {"next_step_id": step})
                    if init.get("type") == "menu" else init)
            for f in (form.get("data_schema") or []):
                n = f.get("name")
                if n in names:
                    val = f.get("suggested_value", f.get("default"))
                    if val is not None:
                        configured[n] = val
        out["configured"] = configured
    except Exception as exc:  # noqa: BLE001 — read is best-effort
        out["configured_error"] = str(exc)
    return out
