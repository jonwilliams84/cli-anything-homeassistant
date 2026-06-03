"""Powercalc helpers — safe operations on virtual-power entries and groups.

Powercalc's config-entry options-flow API has several undocumented footguns
that this module exists to defuse:

1. **Group membership is REPLACE-on-write, AND omitted fields are cleared.**
   Submitting ``{"group_power_entities": [new_id]}`` to a group's options flow
   does NOT append — it wipes the existing list AND blanks every other
   membership field you didn't resend (``group_member_sensors``,
   ``group_energy_entities``, ``sub_groups``, ``area`` …). The safe writers
   here read the current config off the flow form first and resend every
   field, so editing one list can't silently drop the others.

2. **The configured membership is only readable from the options form.** The
   config-entry REST list does not expose powercalc options, and a group power
   sensor's ``entities`` attribute is the *resolved leaf list*, not the
   configured one (a member-sensor group resolves to leaf ``*_power`` ids that
   are NOT what you'd write back). Read config with :func:`get_group_config`,
   which pulls each field's ``description.suggested_value`` off the form — the
   only reliable source. (The old code read ``suggested_value``/``default`` at
   the top level, which powercalc leaves empty here, so reads came back blank.)

3. **A group write is not trustworthy until reloaded and read back.** An
   options-flow ``create_entry`` response does not guarantee the entry
   reloaded, so a freshly-written membership can read correct in-session yet
   evaporate on the next HA restart. The safe writers reload the entry and
   then re-read the stored config to confirm it actually changed.

4. **Power and energy roll up separately.** A group's ``group_power_entities``
   feeds the ``*_power`` rollup; ``group_energy_entities`` feeds the
   ``*_energy`` rollup. Populate only the power list and the energy dashboard
   silently shows nothing (or the entry falls back to integrating group power,
   which resets on reload). The safe add/set writers take both, and
   :func:`energy_siblings_for` derives the matching ``*_energy`` ids.

5. **Fixed-mode powercalc on a ``binary_sensor`` source silently no-ops.** The
   options form accepts ``power: 3000`` gated on ``binary_sensor.*`` without
   complaint, but the resulting power sensor never leaves 0 W. The relay can
   close and the dashboard estimate doesn't budge. ``create_virtual_power``
   refuses this combination and steers callers to ``power_template`` instead.

6. **Calculation mode cannot be changed in place.** Powercalc's options flow
   exposes no step to switch a ``linear`` entry to ``fixed`` (the menu only
   offers the current mode's step). The only route is delete + recreate — and
   *deleting* a grouped entry cascades it out of every ``group_member_sensors``
   rollup silently. :func:`recreate_preserving_groups` wraps that round-trip:
   snapshot every group the entry belongs to, delete, recreate, restore.

Background: a 2026-05-12 session lost 92+ entities across 4 groups to (1),
missed a 3 900 W immersion-heater cycle to (5), and a 2026-06-02 session
stripped 30 spotlights out of their area + energy rollups via (2)/(3)/(6).
All of these are silent in raw API usage.
"""

from __future__ import annotations

from typing import Any, Iterable

from cli_anything.homeassistant.core import config_entries as _ce


POWERCALC_DOMAIN = "powercalc"

# Source-entity domains for which powercalc's fixed-mode `power: <number>`
# form is known not to gate state changes. Use `power_template` instead.
_BAD_FIXED_DOMAINS = frozenset({"binary_sensor"})


# ── group membership ───────────────────────────────────────────────────────

# The membership list fields on the powercalc `group_custom` options form, and
# the kwarg each maps to in this module's writers.
_GROUP_LIST_FIELDS = (
    "group_member_sensors",   # member powercalc config-entry IDs → power+energy
    "group_power_entities",   # external power sensor entity IDs   → power rollup
    "group_energy_entities",  # external energy sensor entity IDs  → energy rollup
    "sub_groups",             # child powercalc group config-entry IDs
)
# Scalar fields we resend verbatim so a list edit doesn't blank them.
_GROUP_SCALAR_FIELDS = ("area", "floor")


def get_group_members(client, sensor_entity_id: str) -> list[str]:
    """Return the *resolved leaf* entity list for a group's power sensor.

    Reads ``state.attributes.entities`` — the flattened leaf list powercalc
    actually sums. For a member-sensor or sub-group rollup this is NOT what you
    write back into the config (those leaves are derived); use
    :func:`get_group_config` for the editable configuration.
    """
    if not sensor_entity_id:
        raise ValueError("sensor_entity_id is required")
    state = client.get(f"states/{sensor_entity_id}")
    return list(state.get("attributes", {}).get("entities", []))


def _form_current_value(field: dict) -> Any:
    """Pull the current stored value out of an options-form field descriptor.

    Powercalc surfaces it under ``description.suggested_value`` (NOT the
    top-level ``suggested_value``/``default``, which it leaves unset for these
    fields — the cause of the silent blank reads). Falls back to the top-level
    keys for forms that do populate them.
    """
    desc = field.get("description") or {}
    if "suggested_value" in desc:
        return desc["suggested_value"]
    return field.get("suggested_value", field.get("default"))


def _open_group_custom(client, entry_id: str) -> dict:
    """Open a group entry's options flow, advance to `group_custom`, and return
    the resulting **form** descriptor (which carries ``flow_id`` plus the
    current field values). Raises if the entry exposes no `group_custom` step.
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
            client.delete(f"config/config_entries/options/flow/{flow_id}")
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
        return resp
    return init


def _form_field_map(form: dict) -> dict[str, dict]:
    return {f.get("name"): f for f in (form.get("data_schema") or [])}


def get_group_config(client, entry_id: str) -> dict:
    """Read a powercalc group's **configured** membership lists.

    Returns a dict with keys ``group_member_sensors``, ``group_power_entities``,
    ``group_energy_entities``, ``sub_groups`` (each a list, possibly empty) and
    ``area`` / ``floor`` (scalar or None). This is the editable config — the
    source of truth for the safe writers — not the resolved leaf list.

    Opens, reads, and aborts the options flow (no mutation).
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    form = _open_group_custom(client, entry_id)
    flow_id = form.get("flow_id")
    fields = _form_field_map(form)
    out: dict[str, Any] = {}
    for name in _GROUP_LIST_FIELDS:
        f = fields.get(name)
        val = _form_current_value(f) if f else None
        out[name] = list(val) if isinstance(val, list) else []
    for name in _GROUP_SCALAR_FIELDS:
        f = fields.get(name)
        out[name] = _form_current_value(f) if f else None
    if flow_id:
        try:
            client.delete(f"config/config_entries/options/flow/{flow_id}")
        except Exception:  # noqa: BLE001 — abort is best-effort
            pass
    return out


def _diff_lists(a: list, b: list) -> bool:
    """True if two membership lists differ as *sets* (order-insensitive)."""
    return set(a or []) != set(b or [])


def set_group_members(client, entry_id: str, *,
                       member_sensors: list[str] | None = None,
                       power_entities: list[str] | None = None,
                       energy_entities: list[str] | None = None,
                       sub_groups: list[str] | None = None,
                       reload: bool = True,
                       verify: bool = True) -> dict:
    """REPLACE a group's membership, preserving every field you don't touch.

    Reads the current config first and resends *all* membership fields, so
    setting (say) only ``energy_entities`` cannot blank ``member_sensors`` or
    ``power_entities`` — the omitted-field-clears-it footgun. Any kwarg left as
    ``None`` keeps its current value; pass ``[]`` to genuinely clear a list.

    With ``reload`` (default), the entry is reloaded after the write. With
    ``verify`` (default), the stored config is re-read and compared to what was
    requested; a mismatch raises ``RuntimeError`` (a write that "took" in the
    flow response but did not persist). Returns the flow response augmented
    with a ``_verified`` block.

    DESTRUCTIVE per field: prefer :func:`add_group_members` /
    :func:`remove_group_members` for incremental edits.
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    if all(v is None for v in
           (member_sensors, power_entities, energy_entities, sub_groups)):
        raise ValueError(
            "Provide at least one of member_sensors / power_entities / "
            "energy_entities / sub_groups",
        )

    form = _open_group_custom(client, entry_id)
    flow_id = form["flow_id"]
    fields = _form_field_map(form)
    current = {n: (_form_current_value(fields[n]) if n in fields else None)
               for n in (*_GROUP_LIST_FIELDS, *_GROUP_SCALAR_FIELDS)}

    desired = {
        "group_member_sensors": member_sensors,
        "group_power_entities": power_entities,
        "group_energy_entities": energy_entities,
        "sub_groups": sub_groups,
    }
    payload: dict[str, Any] = {}
    for name in _GROUP_LIST_FIELDS:
        if name not in fields:
            continue
        val = desired[name]
        payload[name] = list(val) if val is not None else \
            (list(current[name]) if isinstance(current[name], list) else [])
    # Resend scalar fields verbatim so they aren't cleared.
    for name in _GROUP_SCALAR_FIELDS:
        if name in fields and current[name] not in (None, ""):
            payload[name] = current[name]

    resp = client.post(
        f"config/config_entries/options/flow/{flow_id}", payload,
    )
    # Walk any trailing confirm steps. Bounded so a flow that keeps returning a
    # form (or a fake that always does) can't spin forever.
    for _ in range(6):
        if resp.get("type") != "form":
            break
        resp = client.post(
            f"config/config_entries/options/flow/{flow_id}", {},
        )

    if reload:
        try:
            reload_entry(client, entry_id)
        except Exception:  # noqa: BLE001 — reload is best-effort
            pass

    if verify:
        stored = get_group_config(client, entry_id)
        mismatches = {}
        for name in _GROUP_LIST_FIELDS:
            if desired[name] is None:
                continue
            if _diff_lists(stored.get(name) or [], desired[name]):
                mismatches[name] = {
                    "wanted": sorted(desired[name]),
                    "stored": sorted(stored.get(name) or []),
                }
        if mismatches:
            raise RuntimeError(
                f"Group {entry_id}: write did not persist for "
                f"{list(mismatches)} — {mismatches}",
            )
        resp = {**resp, "_verified": {"stored": stored}}
    return resp


def add_group_members(client, entry_id: str, *,
                       member_sensors: Iterable[str] | None = None,
                       power_entities: Iterable[str] | None = None,
                       energy_entities: Iterable[str] | None = None,
                       reload: bool = True, verify: bool = True) -> dict:
    """SAFELY add members to a group (read current config → merge → write).

    Reads the *configured* lists via :func:`get_group_config` (not the resolved
    leaf list — that was the bug that wrote derived ids back and never stuck),
    merges in the new members per field (de-duplicated, order preserved), and
    writes via :func:`set_group_members` (which reloads + verifies).

    Prefer ``member_sensors`` (powercalc config-entry IDs) when the leaves are
    powercalc entries: powercalc then rolls up both their power and energy
    automatically. Use ``power_entities`` / ``energy_entities`` for external
    (non-powercalc) sensors, and pair them (see :func:`energy_siblings_for`).
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    adds = {
        "member_sensors": list(member_sensors) if member_sensors else [],
        "power_entities": list(power_entities) if power_entities else [],
        "energy_entities": list(energy_entities) if energy_entities else [],
    }
    if not any(adds.values()):
        raise ValueError(
            "Provide at least one of member_sensors / power_entities / "
            "energy_entities to add",
        )
    cfg = get_group_config(client, entry_id)
    merged = {
        "member_sensors": list(dict.fromkeys(
            (cfg["group_member_sensors"] or []) + adds["member_sensors"])),
        "power_entities": list(dict.fromkeys(
            (cfg["group_power_entities"] or []) + adds["power_entities"])),
        "energy_entities": list(dict.fromkeys(
            (cfg["group_energy_entities"] or []) + adds["energy_entities"])),
    }
    return set_group_members(
        client, entry_id,
        member_sensors=merged["member_sensors"] if adds["member_sensors"]
        else None,
        power_entities=merged["power_entities"] if adds["power_entities"]
        else None,
        energy_entities=merged["energy_entities"] if adds["energy_entities"]
        else None,
        reload=reload, verify=verify,
    )


def remove_group_members(client, entry_id: str, *,
                          member_sensors: Iterable[str] | None = None,
                          power_entities: Iterable[str] | None = None,
                          energy_entities: Iterable[str] | None = None,
                          reload: bool = True, verify: bool = True) -> dict:
    """SAFELY remove members from a group (read current config → filter → write).

    Reads the configured lists, drops the supplied members per field, and writes
    back what remains (reload + verify). Fields with nothing to remove are left
    untouched.
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    drops = {
        "member_sensors": set(member_sensors or ()),
        "power_entities": set(power_entities or ()),
        "energy_entities": set(energy_entities or ()),
    }
    if not any(drops.values()):
        raise ValueError(
            "Provide at least one of member_sensors / power_entities / "
            "energy_entities to remove",
        )
    cfg = get_group_config(client, entry_id)
    return set_group_members(
        client, entry_id,
        member_sensors=([e for e in (cfg["group_member_sensors"] or [])
                         if e not in drops["member_sensors"]]
                        if drops["member_sensors"] else None),
        power_entities=([e for e in (cfg["group_power_entities"] or [])
                         if e not in drops["power_entities"]]
                        if drops["power_entities"] else None),
        energy_entities=([e for e in (cfg["group_energy_entities"] or [])
                          if e not in drops["energy_entities"]]
                         if drops["energy_entities"] else None),
        reload=reload, verify=verify,
    )


# ── power↔energy sibling derivation + group discovery ──────────────────────

def energy_siblings_for(client, power_entities: Iterable[str], *,
                        states: list[dict] | None = None) -> dict:
    """Map each ``*_power`` sensor to its matching powercalc ``*_energy`` sensor.

    Powercalc names an entry's energy sensor by swapping the ``_power`` suffix
    for ``_energy``. This validates that the sibling actually exists and carries
    ``device_class: energy`` before trusting it — external/derived power sensors
    (real meters, EV chargers) legitimately have no powercalc energy twin.

    Returns ``{"siblings": {power_id: energy_id, ...},
    "no_sibling": [power_id, ...]}``.
    """
    if states is None:
        states = client.get("states")
    by_id = {s["entity_id"]: s for s in states if isinstance(s, dict)}

    def is_energy(eid: str) -> bool:
        s = by_id.get(eid)
        return bool(s) and (s.get("attributes") or {}).get(
            "device_class") == "energy"

    siblings: dict[str, str] = {}
    no_sibling: list[str] = []
    for pe in power_entities:
        cand = pe[:-len("_power")] + "_energy" if pe.endswith("_power") else None
        if cand and is_energy(cand):
            siblings[pe] = cand
        else:
            no_sibling.append(pe)
    return {"siblings": siblings, "no_sibling": no_sibling}


def find_groups_containing(client, *, entry_ids: Iterable[str] | None = None,
                            power_entities: Iterable[str] | None = None,
                            energy_entities: Iterable[str] | None = None,
                            ) -> list[dict]:
    """Find every powercalc group whose config references the given members.

    Scans all powercalc group entries' configured lists (via
    :func:`get_group_config`). Matches ``entry_ids`` against
    ``group_member_sensors`` / ``sub_groups`` and ``power_entities`` /
    ``energy_entities`` against the respective lists.

    Returns ``[{entry_id, title, matched: {field: [ids]}}, ...]`` — the
    snapshot a safe delete+recreate restores from.
    """
    want_entries = set(entry_ids or ())
    want_power = set(power_entities or ())
    want_energy = set(energy_entities or ())
    out: list[dict] = []
    for e in list_entries(client):
        eid = e.get("entry_id")
        try:
            cfg = get_group_config(client, eid)
        except Exception:  # noqa: BLE001 — not a group / unreadable
            continue
        matched: dict[str, list] = {}
        for field, want in (
            ("group_member_sensors", want_entries),
            ("sub_groups", want_entries),
            ("group_power_entities", want_power),
            ("group_energy_entities", want_energy),
        ):
            hit = [x for x in (cfg.get(field) or []) if x in want]
            if hit:
                matched[field] = hit
        if matched:
            out.append({"entry_id": eid, "title": e.get("title"),
                        "matched": matched})
    return out


def recreate_preserving_groups(client, *, entry_id: str, recreate,
                                verify: bool = True) -> dict:
    """Delete a virtual_power entry and recreate it WITHOUT losing its rollups.

    Powercalc cannot change an entry's calculation mode in place, so a
    ``linear → fixed`` migration needs delete + recreate — but deleting a
    grouped entry cascades it out of every ``group_member_sensors`` rollup, and
    the recreate does not re-add it. This wraps the round-trip:

      1. Snapshot every group referencing ``entry_id`` (member/sub-group) or its
         power/energy sensors.
      2. Delete the entry.
      3. Call ``recreate()`` — a zero-arg callable that creates the replacement
         (e.g. ``lambda: create_virtual_power(...)``) and returns its flow
         response. Recreating with the same name+source yields the same sensor
         entity IDs, so entity-id-based (power/energy) memberships survive on
         their own; only member/sub-group references need restoring.
      4. Restore the snapshotted memberships via :func:`add_group_members`.

    Returns ``{created, snapshot, restored}``. The new config-entry ID differs
    from the old, so member-sensor groups are re-added with the new ID.
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    if not callable(recreate):
        raise ValueError("recreate must be a zero-arg callable")

    psensor = esensor = None
    info = read_entry(client, entry_id)
    # resolve this entry's power/energy sensor ids for entity-id snapshots
    for s in client.get("states"):
        a = s.get("attributes") or {}
        if a.get("integration") != "powercalc":
            continue
        fn = (a.get("friendly_name") or "").strip()
        base = fn
        for suf in (" Power", " power", " Energy", " energy"):
            if base.endswith(suf):
                base = base[:-len(suf)]
        if base.strip() == (info.get("title") or "").strip():
            dc = a.get("device_class")
            if dc == "power":
                psensor = s["entity_id"]
            elif dc == "energy":
                esensor = s["entity_id"]

    snapshot = find_groups_containing(
        client, entry_ids=[entry_id],
        power_entities=[psensor] if psensor else None,
        energy_entities=[esensor] if esensor else None,
    )
    _ce.delete_entry(client, entry_id)
    created = recreate()
    new_entry_id = (created.get("result", {}) or {}).get("entry_id") \
        if isinstance(created, dict) else None

    restored = []
    for g in snapshot:
        m = g["matched"]
        kwargs: dict[str, Any] = {}
        if new_entry_id and (m.get("group_member_sensors")
                             or m.get("sub_groups")):
            kwargs["member_sensors"] = [new_entry_id]
        # entity-id memberships survive recreate (same sensor ids) but re-add
        # defensively in case the cascade touched them.
        if psensor and m.get("group_power_entities"):
            kwargs["power_entities"] = [psensor]
        if esensor and m.get("group_energy_entities"):
            kwargs["energy_entities"] = [esensor]
        if kwargs:
            try:
                add_group_members(client, g["entry_id"], verify=verify,
                                  **kwargs)
                restored.append({"group": g["entry_id"], "added": kwargs})
            except Exception as exc:  # noqa: BLE001 — report, don't abort
                restored.append({"group": g["entry_id"], "error": str(exc)})
    return {"created": created, "new_entry_id": new_entry_id,
            "snapshot": snapshot, "restored": restored}


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
                    val = _form_current_value(f)
                    if val is not None:
                        configured[n] = val
        out["configured"] = configured
    except Exception as exc:  # noqa: BLE001 — read is best-effort
        out["configured_error"] = str(exc)
    return out
