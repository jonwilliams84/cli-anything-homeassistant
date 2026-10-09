"""Insteon — the ``insteon`` integration's WebSocket surface.

THE GAP THIS CLOSES
    The last mainstream integration surface in the harness that had no
    command group. ``zwave_js`` (v1.54), ``matter`` (v1.56), ``knx``
    (v1.57), ``zha`` and the Supervisor (v1.52) all have one; Insteon —
    the whole-estate lighting protocol whose config panel is a separate
    frontend (`insteon_frontend`) — was reachable only through raw state
    reads and the entity registry. Everything below is a direct
    pass-through to the 30 commands
    ``homeassistant/components/insteon/api/*.py`` registers (2026.8.x).

THE THIRTY WEBSOCKET COMMANDS, BY FILE UPSTREAM
    = device (api/device.py) = ===============================================
    ``insteon/device/get``        — one device: address, battery, ALDB status
    ``insteon/device/add``        — start all-linking; streams ``device_added``
                                    events as devices join, ``linking_stopped``
                                    when it is done
    ``insteon/device/add/cancel`` — cancel a linking in progress
    ``insteon/device/remove``     — remove device (+ optionally its references)
    ``insteon/device/add_x10``    — register an X10 housecode/unit
    = aldb (api/aldb.py) — the All-Link Database =============================
    ``insteon/aldb/get``                 — the device's link table, pending
                                           changes merged in and flagged
    ``insteon/aldb/change``              — modify an existing record (queued)
    ``insteon/aldb/create``              — add a new record (queued)
    ``insteon/aldb/write``               — push pending changes to the device,
                                           reload + save
    ``insteon/aldb/load``                — re-read the device's database
    ``insteon/aldb/reset``               — discard ALL pending changes
    ``insteon/aldb/add_default_links``   — clear pending + recreate defaults
    ``insteon/aldb/notify``              — subscribe: one device's ALDB status
    ``insteon/aldb/notify_all``          — subscribe: every device's ALDB status
    = properties (api/properties.py) — device configuration ==================
    ``insteon/properties/get``     — the device's configurable properties +
                                     the per-property value schema
    ``insteon/properties/change``  — set one property (queued)
    ``insteon/properties/write``   — push pending properties to the device
    ``insteon/properties/load``    — re-read properties from the device
    ``insteon/properties/reset``   — discard ALL pending property changes
    = config (api/config.py) — the modem connection ==========================
    ``insteon/config/get``                    — modem config, X10 + overrides
    ``insteon/config/get_modem_schema``       — the config form the panel shows
    ``insteon/config/update_modem_config``    — re-point the modem (PLM/Hub)
    ``insteon/config/device_override/add``    — force cat/subcat for an address
    ``insteon/config/device_override/remove`` — drop an override
    ``insteon/config/get_broken_links``       — controller links with no target
    ``insteon/config/get_unknown_devices``    — addresses never seen
    = scenes (api/scenes.py) =================================================
    ``insteon/scenes/get``    — every scene (group → devices/links)
    ``insteon/scene/get``     — one scene
    ``insteon/scene/save``    — add-or-update a scene (name + device links)
    ``insteon/scene/delete``  — delete a scene

EVERY COMMAND IS ADMIN-ONLY UPSTREAM — each one carries
``@require_admin``. The client does not duplicate the check; it just
translates what a non-admin connection gets back.

CHANGE-THEN-WRITE, IN TWO PLACES
    Both the ALDB and the device properties follow pyinsteon's edit → push
    cycle: ``change``/``create`` queue a pending change (and ``aldb/get``
    shows it merged in, flagged ``dirty``), and nothing reaches the device
    until ``write`` runs. The destructive halves — ``aldb reset`` (drop the
    pending changes) and ``properties reset`` — are confirmation-gated in
    the CLI.

ALL-LINKING IS A STREAM THAT ENDS ON ITS OWN
    ``insteon/device/add`` acks, then streams ``device_added`` /
    ``linking_stopped`` events as the modem links devices in, then sends a
    final result. This is the harness's run-to-completion WS shape:
    :func:`add_device` routes it through ``ws_run_events`` with
    ``linking_stopped`` as the terminal predicate. Linking waits for
    YOU to press the device's set button — give the command a long
    ``--timeout`` (the client's timeout bounds the wait).

WHEN THE INTEGRATION IS NOT LOADED
    Insteon needs a configured modem AND (on a Core install) the
    ``pyinsteon`` / ``insteon_frontend`` packages. Without a working setup
    the ``insteon/…`` commands are never registered and the websocket
    layer answers ``unknown_command`` — the same code a typo gets. Every
    function raises :data:`ABSENT_NOTE`, which names both routes;
    ``insteon available`` turns the same condition into an answer with
    exit 0 so scripts branch on it.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from cli_anything.homeassistant.core._ws_subscribe_utils import (
    resolve_stop_event,
    validate_callable,
    wrap_with_max_events,
)
from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

DOMAIN = "insteon"

#: ``unknown_command`` means the ``insteon`` integration is not loaded:
#: no configured modem, or (Core installs) the ``pyinsteon`` /
#: ``insteon_frontend`` packages missing. Nothing in this group can work
#: without it.
ABSENT_NOTE = (
    "This Home Assistant has no Insteon modem configured: the `insteon` "
    "integration is not loaded, so it never registered its `insteon/…` "
    "websocket commands. On a Core install the integration also needs the "
    "`pyinsteon` and `insteon_frontend` packages to be importable. Confirm it "
    "independently with `system components` — and set the integration up in "
    "the HA UI (Settings → Devices & Services → Add Integration → Insteon) "
    "first."
)

#: The X10 platforms the integration accepts for an X10 device row. Not the
#: full ``INSTEON_PLATFORMS`` — X10 hardware cannot do binary anything beyond
#: on/off, so the panel only offers these three.
X10_PLATFORMS = ("binary_sensor", "switch", "light")

#: Housecodes a–p (the X10 letter dials). Upstream validates against
#: ``HC_LOOKUP``; these are its keys.
X10_HOUSECODES = tuple("abcdefghijklmnop")

#: The one-of-many shapes the ALDB record schema accepts as REQUIRED, and the
#: byte ranges it clamps records into. Enforced client-side so the refusal
#: names the field instead of a bare ``vol.Invalid`` message.
ALDB_REQUIRED_KEYS = (
    "mem_addr",
    "in_use",
    "group",
    "is_controller",
    "target",
    "data1",
    "data2",
    "data3",
)
ALDB_BOOL_KEYS = ("in_use", "is_controller")
ALDB_OPTIONAL_KEYS = ("highwater", "target_name", "dirty")


# ── plumbing ────────────────────────────────────────────────────────────────


def _is_absent(exc: HomeAssistantError) -> bool:
    return exc.code == "unknown_command"


def _raise_absent() -> None:
    raise HomeAssistantError(ABSENT_NOTE, code="unknown_command")


def _ws(client, msg_type: str, payload: dict | None = None) -> Any:
    """One ``insteon/…`` websocket call, with the absent-integration guard."""
    try:
        return client.ws_call(msg_type, payload)
    except HomeAssistantError as exc:
        if _is_absent(exc):
            _raise_absent()
        raise


def _require_address(device_address: str) -> str:
    """Shape-check an Insteon device address (or an X10 one)."""
    device_address = (device_address or "").strip()
    if not device_address:
        raise ValueError("the device address (e.g. '1a.2b.3c' or 'X10.a.3') is required")
    return device_address


def resolve_device_id(client, ident: str) -> str:
    """Map ``<domain>.<object_id>`` through the entity registry to a device id.

    A bare string is already treated as a device-registry id and passed
    through unchanged. The registry works whether or not the integration is
    loaded; an entity that resolves to nothing raises ValueError naming it.
    """
    ident = (ident or "").strip()
    if not ident:
        raise ValueError("device id or entity id is required")
    if "." not in ident:
        return ident
    entry = client.ws_call("config/entity_registry/get", {"entity_id": ident}) or {}
    device_id = entry.get("device_id")
    if not device_id:
        raise ValueError(f"entity {ident!r} is not linked to a device; pass a device id instead")
    return device_id


# ── availability ────────────────────────────────────────────────────────────


def available(client) -> dict:
    """Is the ``insteon`` integration loaded? A READ — 'no' is an answer.

    Checks the integration's presence in the loaded-components list, so the
    answer never depends on a websocket round-trip to a command that does
    not exist.
    """
    cfg = client.ws_call("get_config") or {}
    loaded = DOMAIN in (cfg.get("components") or [])
    return {
        "available": loaded,
        "note": (
            "insteon is loaded; every `insteon` command works here." if loaded else ABSENT_NOTE
        ),
    }


# ── devices ─────────────────────────────────────────────────────────────────


def get_device(client, ident: str) -> dict:
    """WS ``insteon/device/get`` — one Insteon device's panel summary.

    Accepts a HA device registry id or any entity id on the device. The
    answer is the address, whether the device is battery-powered and the
    ALDB status — the fields the Insteon panel's device row shows.
    """
    device_id = resolve_device_id(client, ident)
    return _ws(client, "insteon/device/get", {"device_id": device_id})


def add_device(
    client,
    *,
    address: str | None = None,
    multiple: bool = False,
) -> dict:
    """WS ``insteon/device/add`` — start all-linking and collect what joined.

    Run-to-completion: the modem enters linking mode, each device that
    completes adds a ``device_added`` event, and ``linking_stopped`` ends
    it. Linking WAITS for you to press the device's set button, so give
    the command a long ``--timeout``. With no ``address``, linking is open
    to the first device that responds; with one, the modem links that
    specific device.

    Returns every event received — the added addresses first, the
    ``linking_stopped`` marker last — plus a summary listing them.
    """
    payload: dict[str, Any] = {"multiple": bool(multiple)}
    if address:
        payload["device_address"] = (address or "").strip()
    try:
        events = client.ws_run_events(
            "insteon/device/add",
            payload,
            is_terminal=lambda event: event.get("type") == "linking_stopped",
        )
    except HomeAssistantError as exc:
        if _is_absent(exc):
            _raise_absent()
        raise
    added = [
        event["address"]
        for event in events
        if event.get("type") == "device_added" and event.get("address")
    ]
    return {
        "result": "ok",
        "added": added,
        "note": (
            f"{len(added)} device(s) joined: {', '.join(added)}"
            if added
            else "linking finished; no device reported. Confirm with `device list`."
        ),
    }


def cancel_add_device(client) -> dict:
    """WS ``insteon/device/add/cancel`` — end a linking in progress."""
    _ws(client, "insteon/device/add/cancel")
    return {"result": "ok", "note": "all-linking cancelled"}


def remove_device(client, device_address: str, *, remove_all_refs: bool = False) -> dict:
    """WS ``insteon/device/remove`` — remove a device (destructive).

    ``remove_all_refs`` ALSO scrubs every ALDB record that references the
    device; without it the references stay and come back as broken links
    (`insteon broken-links` finds them). An ``X10.<house>.<unit>`` address
    removes the X10 device instead. The CLI confirmation-gates this.
    """
    device_address = _require_address(device_address)
    _ws(
        client,
        "insteon/device/remove",
        {"device_address": device_address, "remove_all_refs": bool(remove_all_refs)},
    )
    note = "device removed"
    if device_address.lower().startswith("x10"):
        note = "X10 device removed"
    elif remove_all_refs:
        note = "device and all its link references removed"
    return {"result": "ok", "note": f"{note} ({device_address})"}


def add_x10_device(
    client,
    housecode: str,
    unitcode: int,
    platform: str,
    *,
    dim_steps: int | None = None,
) -> dict:
    """WS ``insteon/device/add_x10`` — register an X10 housecode/unit pair.

    ``platform`` is one of binary_sensor/switch/light (a light takes
    ``dim_steps``; upstream makes it REQUIRED for that platform and
    defaults the rest to 22). Duplicates (same housecode + unitcode) come
    back as the server's ``duplicate`` error — the options list is NOT
    a merge-on-write surface, but the pair is the identity, so nothing to
    lose.
    """
    housecode = (housecode or "").strip().lower()
    if housecode not in X10_HOUSECODES:
        raise ValueError(f"housecode must be one of {''.join(X10_HOUSECODES)!r}, got {housecode!r}")
    unitcode = int(unitcode)
    if not 1 <= unitcode <= 16:
        raise ValueError(f"unitcode must be 1..16, got {unitcode}")
    if platform not in X10_PLATFORMS:
        raise ValueError(f"platform must be one of {', '.join(X10_PLATFORMS)}, got {platform!r}")
    x10_device: dict[str, Any] = {
        "housecode": housecode,
        "unitcode": unitcode,
        "platform": platform,
    }
    if dim_steps is not None:
        dim_steps = int(dim_steps)
        if not 0 <= dim_steps <= 255:
            raise ValueError(f"dim_steps must be 0..255, got {dim_steps}")
        x10_device["dim_steps"] = dim_steps
    try:
        _ws(client, "insteon/device/add_x10", {"x10_device": x10_device})
    except HomeAssistantError as exc:
        if "Duplicate" in str(exc):
            raise HomeAssistantError(
                f"X10 {housecode}{unitcode} is already registered: {exc}", code=exc.code
            ) from exc
        raise
    return {
        "result": "ok",
        "note": f"X10 {housecode}{unitcode} added as a {platform}",
    }


# ── all-link database ───────────────────────────────────────────────────────


def _validate_aldb_record(record: dict) -> dict:
    """Shape-check one ALDB record against the upstream schema.

    Required: ``mem_addr`` (int), ``in_use`` (bool), ``group`` (0..255),
    ``is_controller`` (bool), ``target`` (str) and the three data bytes
    (0..255). Optional: ``highwater``, ``target_name``, ``dirty``.
    """
    if not isinstance(record, dict):
        raise ValueError("record must be a JSON object with mem_addr/in_use/group/…")
    missing = [key for key in ALDB_REQUIRED_KEYS if key not in record]
    if missing:
        raise ValueError("record is missing required key(s): " + ", ".join(missing))
    for key in ALDB_BOOL_KEYS:
        if not isinstance(record[key], bool):
            raise ValueError(f"record {key!r} must be a boolean, got {record[key]!r}")
    mem_addr = record["mem_addr"]
    if not isinstance(mem_addr, int) or isinstance(mem_addr, bool) or mem_addr < 0:
        raise ValueError(f"record mem_addr must be a non-negative int, got {mem_addr!r}")
    group = record["group"]
    if not isinstance(group, int) or isinstance(group, bool) or not 0 <= group <= 255:
        raise ValueError(f"record group must be 0..255, got {group!r}")
    target = record["target"]
    if not isinstance(target, str) or not target.strip():
        raise ValueError(f"record target must be a non-empty address string, got {target!r}")
    for key in ("data1", "data2", "data3"):
        value = record[key]
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 255:
            raise ValueError(f"record {key!r} must be 0..255, got {value!r}")
    extra = [
        key for key in record if key not in ALDB_REQUIRED_KEYS and key not in ALDB_OPTIONAL_KEYS
    ]
    if extra:
        raise ValueError(f"record has unknown key(s): {', '.join(extra)}")
    return record


def get_aldb(client, device_address: str) -> list[dict]:
    """WS ``insteon/aldb/get`` — a device's link table, pending changes merged.

    Pending (queued, not yet written) records ride along with ``dirty:
    true`` — that flag is the difference between what the device holds and
    what the queue holds.
    """
    device_address = _require_address(device_address)
    return _ws(client, "insteon/aldb/get", {"device_address": device_address})


def add_aldb_record(client, device_address: str, record: dict) -> dict:
    """WS ``insteon/aldb/create`` — queue a NEW link record (not written yet).

    The queue only reaches the device when ``aldb write`` runs. Read back
    with ``aldb get`` — the queued record arrives flagged ``dirty``.
    """
    device_address = _require_address(device_address)
    _validate_aldb_record(record)
    _ws(
        client,
        "insteon/aldb/create",
        {"device_address": device_address, "record": record},
    )
    return {
        "result": "ok",
        "note": f"record queued on {device_address}; `insteon aldb-write` pushes it",
    }


def change_aldb_record(client, device_address: str, record: dict) -> dict:
    """WS ``insteon/aldb/change`` — queue a MODIFICATION of an existing record.

    Same record schema as :func:`add_aldb_record`; ``mem_addr`` selects the
    record to modify (``aldb get`` lists them). Not written until
    ``aldb write``.
    """
    device_address = _require_address(device_address)
    _validate_aldb_record(record)
    _ws(
        client,
        "insteon/aldb/change",
        {"device_address": device_address, "record": record},
    )
    return {
        "result": "ok",
        "note": f"change queued on {device_address}; `insteon aldb-write` pushes it",
    }


def write_aldb(client, device_address: str) -> dict:
    """WS ``insteon/aldb/write`` — push the queued ALDB changes to the device.

    On success upstream reloads the database from the device and saves it,
    so the post-write table is what the device itself reports.
    """
    device_address = _require_address(device_address)
    _ws(client, "insteon/aldb/write", {"device_address": device_address})
    return {
        "result": "ok",
        "note": f"pending records written to {device_address}; `insteon aldb` reads the result",
    }


def load_aldb(client, device_address: str) -> dict:
    """WS ``insteon/aldb/load`` — re-read a device's database from the bus.

    Also saves the loaded devices file. Use after powering up devices that
    were linked elsewhere, or to spot-check what write actually produced.
    """
    device_address = _require_address(device_address)
    _ws(client, "insteon/aldb/load", {"device_address": device_address})
    return {"result": "ok", "note": f"ALDB reload queued for {device_address}"}


def reset_aldb(client, device_address: str) -> dict:
    """WS ``insteon/aldb/reset`` — discard ALL queued ALDB changes (destructive).

    One-way for the queue: every pending record is dropped, the device's
    current table is untouched. The CLI confirmation-gates this.
    """
    device_address = _require_address(device_address)
    _ws(client, "insteon/aldb/reset", {"device_address": device_address})
    return {"result": "ok", "note": f"pending ALDB changes discarded ({device_address})"}


def add_default_links(client, device_address: str) -> dict:
    """WS ``insteon/aldb/add_default_links`` — rebuild the factory link set.

    Clears the pending queue first, THEN queues the defaults — so it is a
    destructive act on anything already queued, and the CLI says so.
    """
    device_address = _require_address(device_address)
    _ws(client, "insteon/aldb/add_default_links", {"device_address": device_address})
    return {
        "result": "ok",
        "note": f"default links queued for {device_address}; `insteon aldb-write` pushes them",
    }


def subscribe_aldb_status(
    client,
    on_event: Callable,
    device_address: str,
    stop_event: threading.Event | None = None,
    max_events: int | None = None,
) -> None:
    """WS ``insteon/aldb/notify`` — a LIVE feed of one device's ALDB state.

    Streams ``record_loaded`` and ``status_changed`` events as the device's
    database loads or changes, until *stop_event* (or *max_events*).
    """
    device_address = _require_address(device_address)
    validate_callable(on_event, "on_event")
    stop, owns_stop = resolve_stop_event(stop_event, max_events)
    wrapper = wrap_with_max_events(on_event, stop, owns_stop, max_events)
    try:
        client.ws_subscribe(
            "insteon/aldb/notify",
            {"device_address": device_address},
            wrapper,
            stop,
        )
    except HomeAssistantError as exc:
        if _is_absent(exc):
            _raise_absent()
        raise


def subscribe_aldb_status_all(
    client,
    on_event: Callable,
    stop_event: threading.Event | None = None,
    max_events: int | None = None,
) -> None:
    """WS ``insteon/aldb/notify_all`` — the same feed for EVERY device.

    What the panel's spinner watches: one event per status change across
    the whole estate, with ``is_loading`` saying whether anything is still
    mid-load.
    """
    validate_callable(on_event, "on_event")
    stop, owns_stop = resolve_stop_event(stop_event, max_events)
    wrapper = wrap_with_max_events(on_event, stop, owns_stop, max_events)
    try:
        client.ws_subscribe("insteon/aldb/notify_all", {}, wrapper, stop)
    except HomeAssistantError as exc:
        if _is_absent(exc):
            _raise_absent()
        raise


# ── device properties ───────────────────────────────────────────────────────


def get_properties(client, device_address: str, *, show_advanced: bool = False) -> dict:
    """WS ``insteon/properties/get`` — a device's configurable properties.

    Returns ``{"properties": […], "schema": {…}}``: one row per property
    (``name`` / ``value`` / ``modified``) and the per-property value schema
    the panel renders its forms from. ``show_advanced`` adds the read-only
    and advanced operating flags — the ones the panel hides behind its
    toggle.
    """
    device_address = _require_address(device_address)
    return _ws(
        client,
        "insteon/properties/get",
        {"device_address": device_address, "show_advanced": bool(show_advanced)},
    )


def change_property(client, device_address: str, name: str, value: Any) -> dict:
    """WS ``insteon/properties/change`` — set one property (queued, not written).

    ``value`` must match the property's type in ``properties/get``'s schema —
    e.g. a toggle mode is its lower-case string (``"on_off"``), a ramp rate
    its seconds as a string. Not written until ``properties-write``.
    """
    device_address = _require_address(device_address)
    name = (name or "").strip()
    if not name:
        raise ValueError("the property name is required (`insteon properties` lists them)")
    _ws(
        client,
        "insteon/properties/change",
        {"device_address": device_address, "name": name, "value": value},
    )
    return {
        "result": "ok",
        "note": f"{name} queued on {device_address}; `insteon properties-write` pushes it",
    }


def write_properties(client, device_address: str) -> dict:
    """WS ``insteon/properties/write`` — push queued property changes to the device.

    A device-side failure comes back as the ``write_failed`` error, not a
    quiet empty result — properties queued but never reaching an awake
    battery device is the common one.
    """
    device_address = _require_address(device_address)
    _ws(client, "insteon/properties/write", {"device_address": device_address})
    return {
        "result": "ok",
        "note": f"pending properties written to {device_address}; `insteon properties` reads the result",
    }


def load_properties(client, device_address: str) -> dict:
    """WS ``insteon/properties/load`` — re-read properties from the device.

    Overwrites the queued values with what the device currently reports;
    also saves the devices file.
    """
    device_address = _require_address(device_address)
    _ws(client, "insteon/properties/load", {"device_address": device_address})
    return {"result": "ok", "note": f"properties re-read from {device_address}"}


def reset_properties(client, device_address: str) -> dict:
    """WS ``insteon/properties/reset`` — discard ALL queued property changes.

    One-way for the queue; the device is untouched. The CLI
    confirmation-gates this.
    """
    device_address = _require_address(device_address)
    _ws(client, "insteon/properties/reset", {"device_address": device_address})
    return {"result": "ok", "note": f"pending property changes discarded ({device_address})"}


# ── modem configuration ─────────────────────────────────────────────────────


def get_config(client) -> dict:
    """WS ``insteon/config/get`` — the entry's modem config + X10 + overrides."""
    return _ws(client, "insteon/config/get")


def get_modem_schema(client) -> list[dict]:
    """WS ``insteon/config/get_modem_schema`` — the config form the panel shows.

    Which schema comes back depends on the connection type stored in the
    entry: a PLM (serial/USB) gets the port form, an Hub v1/v2 the
    host/credentials form. The shape of what ``modem-config-set`` accepts.
    """
    return _ws(client, "insteon/config/get_modem_schema")


def update_modem_config(client, config: dict) -> dict:
    """WS ``insteon/config/update_modem_config`` — re-point the modem (destructive).

    Connects to the NEW settings first; only a successful connect updates
    the config entry. A failed connect comes back as ``connection_failed``
    and the old connection is restored. Give it the same key set
    ``insteon modem-schema`` describes — passing a Hub form where the entry
    says PLM is a server-side rejection. The CLI confirmation-gates this.
    """
    if not isinstance(config, dict) or not config:
        raise ValueError(
            "config must be a non-empty JSON object (the fields `insteon modem-schema` describes)"
        )
    _ws(client, "insteon/config/update_modem_config", {"config": config})
    return {
        "result": "ok",
        "note": "modem re-connected and config entry updated; `insteon config` reads it back",
    }


def add_device_override(
    client, address: str, *, cat: str | None = None, subcat: str | None = None
) -> dict:
    """WS ``insteon/config/device_override/add`` — force cat/subcat for an address.

    For devices the modem reads a wrong product identity for: the override
    makes the platform be derived from what YOU pass. Duplicates (same
    address) come back as the server's ``duplicate`` error.
    """
    address = _require_address(address)
    override: dict[str, Any] = {"address": address}
    if cat is not None:
        override["cat"] = cat
    if subcat is not None:
        override["subcat"] = subcat
    try:
        _ws(client, "insteon/config/device_override/add", {"override": override})
    except HomeAssistantError as exc:
        if "Duplicate" in str(exc):
            raise HomeAssistantError(
                f"{address} already has a device override: {exc}", code=exc.code
            ) from exc
        raise
    return {"result": "ok", "note": f"device override added for {address}"}


def remove_device_override(client, device_address: str) -> dict:
    """WS ``insteon/config/device_override/remove`` — drop the override.

    The device re-derives its platform from the modem's identity on the
    next reload — which is the point, but also the way to break it if the
    modem really does misread it.
    """
    device_address = _require_address(device_address)
    _ws(client, "insteon/config/device_override/remove", {"device_address": device_address})
    return {"result": "ok", "note": f"device override removed for {device_address}"}


def get_broken_links(client) -> list[dict]:
    """WS ``insteon/config/get_broken_links`` — links whose responder is gone.

    One row per controller record whose target device no longer exists:
    the cleanup candidates. ``device-remove --remove-all-refs`` is the
    fix.
    """
    return _ws(client, "insteon/config/get_broken_links")


def get_unknown_devices(client) -> list[str]:
    """WS ``insteon/config/get_unknown_devices`` — addresses only seen as targets.

    Same broken-link scan, the other half: device addresses that appear in
    link records but are not registered. Adding them (or removing the
    records pointing at them) is what clears the entries.
    """
    return _ws(client, "insteon/config/get_unknown_devices")


# ── scenes ──────────────────────────────────────────────────────────────────


def _validate_scene_links(links: Any) -> list[dict]:
    """Shape-check a scene's device-link list.

    Upstream's ``DeviceLinkSchema`` is a LIST of
    ``{"address": str, "data1": int, "data2": int, "data3": int}`` — one
    entry per device participating in the scene.
    """
    if not isinstance(links, list) or not links:
        raise ValueError(
            "links must be a non-empty JSON list of "
            '{"address": "1a.2b.3c", "data1": 0, "data2": 0, "data3": 255} objects'
        )
    cleaned: list[dict] = []
    for i, link in enumerate(links):
        if not isinstance(link, dict):
            raise ValueError(f"links[{i}] must be a JSON object")
        missing = [key for key in ("address", "data1", "data2", "data3") if key not in link]
        if missing:
            raise ValueError(f"links[{i}] is missing required key(s): {', '.join(missing)}")
        address = link["address"]
        if not isinstance(address, str) or not address.strip():
            raise ValueError(f"links[{i}].address must be a non-empty address string")
        cleaned.append(
            {
                "address": address,
                "data1": int(link["data1"]),
                "data2": int(link["data2"]),
                "data3": int(link["data3"]),
            }
        )
    return cleaned


def get_scenes(client) -> dict:
    """WS ``insteon/scenes/get`` — every scene, keyed by scene number."""
    return _ws(client, "insteon/scenes/get")


def get_scene(client, scene_id: int) -> dict:
    """WS ``insteon/scene/get`` — one scene's name, group and device links."""
    return _ws(client, "insteon/scene/get", {"scene_id": int(scene_id)})


def save_scene(client, scene_id: int, name: str, links: Any) -> dict:
    """WS ``insteon/scene/save`` — add-or-update a scene (add-or-update).

    ``links`` is the list ``scene-save --links`` documents. The saved scene
    REPLACES the stored definition — a partial link list drops the devices
    that were in it. The answer carries which ``scene_id`` the content
    landed under and whether the device write succeeded.
    """
    scene_id = int(scene_id)
    name = (name or "").strip()
    if not name:
        raise ValueError("the scene name is required")
    cleaned = _validate_scene_links(links)
    result = _ws(
        client,
        "insteon/scene/save",
        {"scene_id": scene_id, "name": name, "links": cleaned},
    )
    if isinstance(result, dict):
        return result
    return {"scene_id": scene_id, "result": "ok"}


def delete_scene(client, scene_id: int) -> dict:
    """WS ``insteon/scene/delete`` — delete a scene (destructive).

    The scene's ALDB records on the devices are untouched; use the aldb
    commands for those. The CLI confirmation-gates this.
    """
    scene_id = int(scene_id)
    result = _ws(client, "insteon/scene/delete", {"scene_id": scene_id})
    if isinstance(result, dict) and result:
        return result
    return {"scene_id": scene_id, "result": "ok", "note": f"scene {scene_id} deleted"}
