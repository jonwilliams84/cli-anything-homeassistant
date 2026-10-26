"""LCN — the ``lcn`` integration's WebSocket surface.

THE GAP THIS CLOSES
    The sibling of ``knx`` (v1.57) and ``insteon`` (v1.58): LCN is the
    European building-automation bus whose configuration lives in its own
    ``lcn`` config panel, and until now the harness could read raw states
    and registry rows but not configure anything. Every function below
    passes through to one of the 7 WS commands
    ``homeassistant/components/lcn/websocket.py`` registers (2025.1.x):
    the device/entity stores around the config entry, the bus scan, and
    the add/delete pair for each. Every command is ``@require_admin``
    upstream; the client does not duplicate the check, it just translates
    what a non-admin connection gets back.

THE SEVEN WEBSOCKET COMMANDS
    = devices = ===============================================================
    ``lcn/devices``         — every device config in the entry (address,
                              name, hardware/software serial, hw type)
    ``lcn/devices/scan``    — scan the bus: creates/updates one device per
                              address the pchk connection knows (WRITES)
    ``lcn/devices/add``     — add one address by hand → True, or False when
                              the address is already configured
    ``lcn/devices/delete``  — remove a device + all its child entities
                              (destructive; confirmation-gated in the CLI)
    = entities = ==============================================================
    ``lcn/entities``        — every entity config in the entry, optionally
                              narrowed to one address
    ``lcn/entities/add``    — create an entity around a device address.
                              ``domain`` is one of binary_sensor/sensor/
                              switch/light/climate/cover/scene; ``domain_data``
                              is the platform's options object (source or
                              output port, register, …). Anything but the
                              DOMAIN WHITELIST is validated SERVER-side:
                              a bad port or register comes back as a
                              voluptuous message naming the key.
    ``lcn/entities/delete`` — remove one entity by (address, domain,
                              resource). Destructive; confirmation-gated.

ADDRESSES
    An LCN address is the triple ``(segment_id, address_id, is_group)``. The
    wire form is a 3-item list; the CLI form is ``SEG.ADDR`` for a module
    (e.g. ``1.7``) and ``SEG.gADDR`` (case-insensitive) for a group (e.g.
    ``1.g12``). The raw list form is accepted everywhere too. Only rough
    bounds are checked client-side (segment ≥ 0, address ≥ 1); LCN's own
    ranges (modules 1–10 per segment, groups 1–255) are enforced by HA. Use
    ``group addresses against the same bus`` only when the devices mean it —
    a group address is a different device object here, not a shortcut.

WHEN THE INTEGRATION IS NOT LOADED
    The commands are registered by the integration's setup, so with no LCN
    entry configured (no pchk/PC connection) the websocket layer answers
    ``unknown_command`` — the same code a typo gets. Every function raises
    :data:`ABSENT_NOTE`, which says how to check and how to fix it; the
    CLI's ``lcn available`` turns the same condition into an answer with
    exit 0. The config entry itself must have made it past setup: the
    commands answer ``False`` (not an error) when handed an ``entry_id``
    that does not exist, which :func:`_require_entry` surfaces as a plain
    "entry not found" message naming the id.
"""

from __future__ import annotations

from typing import Any

from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

DOMAIN = "lcn"

#: ``unknown_command`` means the ``lcn`` integration never set up: usually no
#: LCN hardware/pchk connection is configured. Nothing in this group works
#: without it.
ABSENT_NOTE = (
    "This Home Assistant has no LCN bus configured: the `lcn` integration is "
    "not set up, so it never registered its `lcn/…` websocket commands. "
    "Confirm it independently with `system components` — and set up the "
    "integration in the HA UI (Settings → Devices & Services → Add "
    "Integration → LCN, pointing it at pchk) first."
)

#: The message the WS layer answers for an unknown entry_id — the handler
#: sends ``result: False`` rather than an error, so this is produced
#: client-side by :func:`_require_entry`. The ``entry_id`` comes from
#: `config-entry list` / `config-entry list --integration lcn`.
ENTRY_NOT_FOUND = (
    "No config entry with id {entry_id!r} (HA answered False, which is what "
    "an unknown entry_id gets). List them with `config-entry list`."
)

#: The 7 platforms the LCN entity store supports upstream.
SUPPORTED_DOMAINS = (
    "binary_sensor",
    "sensor",
    "switch",
    "light",
    "climate",
    "cover",
    "scene",
)

#: The keys every ``domain_data`` object must carry, per platform — the
#: STRUCTURAL check this module performs client-side. Port ranges and
#: register values stay server-side (they are LCN-version-dependent).
REQUIRED_DOMAIN_DATA_KEYS = {
    "binary_sensor": ("source",),
    "sensor": ("source",),
    "switch": ("output",),
    "light": ("output",),
    "climate": ("source", "setpoint"),
    "cover": ("motor",),
    "scene": ("register", "scene"),
}


# ── plumbing ────────────────────────────────────────────────────────────────


def _is_absent(exc: HomeAssistantError) -> bool:
    return exc.code == "unknown_command"


def _raise_absent() -> None:
    raise HomeAssistantError(ABSENT_NOTE, code="unknown_command")


def _ws(client, msg_type: str, payload: dict | None = None) -> Any:
    """One ``lcn/…`` websocket call, with the absent-integration guard."""
    try:
        return client.ws_call(msg_type, payload)
    except HomeAssistantError as exc:
        if _is_absent(exc):
            _raise_absent()
        raise


def _require_entry(entry_id: str, result: Any) -> dict:
    """Turn HA's ``result: False`` for an unknown entry_id into an error.

    Every LCN WS handler passes through :func:`get_config_entry` upstream,
    which answers ``result: False`` — success WITH a false payload — when
    the entry id does not exist. That silently reads as "no devices" if it
    is not named.
    """
    if result is False:
        raise ValueError(ENTRY_NOT_FOUND.format(entry_id=entry_id))
    return result


def parse_address(raw: str | list | tuple) -> list[int]:
    """Parse an LCN address into the wire form ``[seg_id, addr_id, is_group]``.

    Accepts the CLI forms — ``"1.7"`` (module), ``"1.g12"`` (group,
    case-insensitive) — and pass-through lists/tuples of
    ``[seg_id, addr_id, is_group]`` (bools coerced). The wire form is a
    LIST because HA's ``vol.Coerce(tuple)`` accepts any sequence.
    """
    if isinstance(raw, str):
        text = raw.strip().lower()
        if "." not in text:
            raise ValueError(
                f"invalid LCN address {raw!r}: expected 'SEG.ADDR' for a "
                "module or 'SEG.gADDR' for a group (e.g. '1.7', '1.g12')"
            )
        seg_raw, _, addr_raw = text.partition(".")
        is_group = addr_raw.startswith("g")
        if is_group:
            addr_raw = addr_raw[1:]
        try:
            seg_id, addr_id = int(seg_raw), int(addr_raw)
        except ValueError:
            raise ValueError(
                f"invalid LCN address {raw!r}: segment and address must be integers"
            ) from None
    else:
        try:
            seg_id, addr_id, is_group = (
                int(raw[0]),
                int(raw[1]),
                bool(raw[2]),
            )
        except (TypeError, ValueError, IndexError):
            raise ValueError(
                f"invalid LCN address {raw!r}: expected [seg_id, addr_id, is_group]"
            ) from None
    if seg_id < 0:
        raise ValueError(f"invalid LCN address {raw!r}: segment must be ≥ 0")
    if addr_id < 1:
        raise ValueError(f"invalid LCN address {raw!r}: address must be ≥ 1")
    return [seg_id, addr_id, is_group]


def _check_domain_data(domain: str, domain_data: dict) -> None:
    """Structural client-side validation of an entity's domain_data.

    The 7 domains and their REQUIRED keys are stable across LCN versions;
    the ALLOWED VALUES (ports, registers, variables) are LCN
    hardware/version detail and are deliberately left server-side, where
    HA's voluptuous schema names the offending key.
    """
    if domain not in SUPPORTED_DOMAINS:
        raise ValueError(
            f"unsupported domain {domain!r}: LCN supports " + ", ".join(sorted(SUPPORTED_DOMAINS))
        )
    missing = [k for k in REQUIRED_DOMAIN_DATA_KEYS[domain] if k not in domain_data]
    if missing:
        raise ValueError(
            f"domain_data for {domain} is missing required keys: " + ", ".join(missing)
        )


def _require_entity_args(address, domain: str, resource: str) -> dict:
    """Validate the (address, domain, resource) triple entity deletes need."""
    if not (resource or "").strip():
        raise ValueError("resource is required (e.g. 'output1', 'led1')")
    return {
        "address": address,
        "domain": domain,
        "resource": resource,
    }


# ── availability ────────────────────────────────────────────────────────────


def available(client) -> dict:
    """Is the ``lcn`` integration set up? A READ — 'no' is an answer.

    Checks the integration's presence in the loaded-components list (the
    same independent confirmation the error note points at), so the answer
    never depends on a websocket round-trip to a command that does not
    exist.
    """
    cfg = client.ws_call("get_config") or {}
    loaded = DOMAIN in (cfg.get("components") or [])
    return {
        "available": loaded,
        "note": ("lcn is loaded; every `lcn` command works here." if loaded else ABSENT_NOTE),
    }


# ── devices ─────────────────────────────────────────────────────────────────


def devices(client, entry_id: str) -> list[dict]:
    """WS ``lcn/devices`` — every device config in the entry.

    The LCN panel's "Devices" view boots from this: address triple, name,
    hardware/software serial numbers, hardware type.
    """
    return _require_entry(entry_id, _ws(client, "lcn/devices", {"entry_id": entry_id}))


def entities(client, entry_id: str, *, address: str | list | None = None) -> list[dict]:
    """WS ``lcn/entities`` — every entity config in the entry.

    With *address* (any :func:`parse_address` form) the list narrows to the
    entities living at that one device — the drill-down the panel's row
    click does. Entity configs come back with the resolved entity name and
    entity_id joined in.
    """
    payload: dict[str, Any] = {"entry_id": entry_id}
    if address is not None:
        payload["address"] = parse_address(address)
    return _require_entry(entry_id, _ws(client, "lcn/entities", payload))


def scan_devices(client, entry_id: str) -> list[dict]:
    """WS ``lcn/devices/scan`` — scan the bus, create/update every device.

    WRITES: one device per address the pchk connection knows, plus fresh
    hardware/software serials on the existing ones. The device and entity
    REGISTRIES are re-derived afterwards, so removed addresses lose their
    devices too. Returns the resulting device list.
    """
    return _require_entry(entry_id, _ws(client, "lcn/devices/scan", {"entry_id": entry_id}))


def add_device(client, entry_id: str, address: str | list) -> dict:
    """WS ``lcn/devices/add`` — add one address as a device, by hand.

    The address needs no bus knowledge: the device is created immediately
    and its serials refreshed from LCN in the background. HA answers False
    (not an error) when the address is ALREADY configured — surfaced here
    as the literal same ``already_configured`` wording a duplicate would
    expect, naming the address.
    """
    addr = parse_address(address)
    result = _ws(client, "lcn/devices/add", {"entry_id": entry_id, "address": addr})
    if result is False:
        return {
            "added": False,
            "note": (
                f"address {addr} is already configured as a device "
                "(HA answered False for an exact duplicate)"
            ),
            "address": addr,
        }
    return {"added": True, "address": addr}


def delete_device(client, entry_id: str, address: str | list) -> dict:
    """WS ``lcn/devices/delete`` — remove a device AND its child entities.

    DESTRUCTIVE: the device's entity configs are removed from the entry and
    the entity/device registry rows are purged in the same transaction —
    there is no undo beyond a fresh bus scan. HA answers without a payload;
    the returned dict records what was requested and the registry-clean-up
    that implies. Confirmation-gated in the CLI.
    """
    addr = parse_address(address)
    _ws(client, "lcn/devices/delete", {"entry_id": entry_id, "address": addr})
    return {
        "deleted": True,
        "address": addr,
        "note": (
            "device and all its child entities removed from the entry and "
            "purged from the entity/device registries"
        ),
    }


# ── entities ────────────────────────────────────────────────────────────────


def add_entity(
    client,
    entry_id: str,
    address: str | list,
    *,
    name: str,
    domain: str,
    domain_data: dict,
) -> dict:
    """WS ``lcn/entities/add`` — create an entity at a device address.

    The device for *address* must already be configured
    (:func:`add_device` / :func:`scan_devices` first — HA answers False for
    an unknown device, also surfaced here). ``domain`` is one of
    :data:`SUPPORTED_DOMAINS`; ``domain_data`` is the platform's options —
    e.g. ``{"output": "output1"}`` for a switch/light,
    ``{"source": "r1varsetpoint", "setpoint": "r1varsetpoint"}`` for
    climate, ``{"register": 0, "scene": 1}`` for scene. Required keys are
    checked client-side; allowed VALUES are validated by LCN's schema
    server-side.
    """
    addr = parse_address(address)
    if not (name or "").strip():
        raise ValueError("name is required")
    if not isinstance(domain_data, dict):
        raise ValueError("domain_data must be a JSON object")
    _check_domain_data(domain, domain_data)
    result = _ws(
        client,
        "lcn/entities/add",
        {
            "entry_id": entry_id,
            "address": addr,
            "name": name,
            "domain": domain,
            "domain_data": domain_data,
        },
    )
    if result is False:
        return {
            "added": False,
            "note": (
                "HA refused the entity: either the address has no configured "
                "device or an entity with the same unique_id (address + "
                "resource) already exists. Check with "
                f"`lcn entities {entry_id}` --address."
            ),
            "address": addr,
            "domain": domain,
        }
    return {"added": True, "address": addr, "domain": domain, "name": name}


def delete_entity(
    client,
    entry_id: str,
    address: str | list,
    *,
    domain: str,
    resource: str,
) -> dict:
    """WS ``lcn/entities/delete`` — remove one entity from the entry.

    Keyed by the (address, domain, resource) triple the entity store uses;
    ``resource`` is the lowercase resource key (``output1``, ``led1``,
    ``bin_sensor1``, ``register1/scene2``-style for scenes as the store
    recorded it — read it off `lcn entities` first). Unknown triples answer
    False (not an error) upstream; surfaced here as an explanatory value.
    The entity registry row is purged too. Confirmation-gated in the CLI.
    """
    addr = parse_address(address)
    payload = {"entry_id": entry_id, **_require_entity_args(addr, domain, resource)}
    result = _ws(client, "lcn/entities/delete", payload)
    if result is False:
        return {
            "deleted": False,
            "note": (
                "no matching entity: check `lcn entities` for the address's "
                "domain/resource spelled exactly as stored"
            ),
            "address": addr,
            "domain": domain,
            "resource": resource,
        }
    return {"deleted": True, "address": addr, "domain": domain, "resource": resource}
