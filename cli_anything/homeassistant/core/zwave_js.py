"""Z-Wave JS — the ``zwave_js`` integration's WebSocket + service surface.

THE GAP THIS CLOSES
    Every mainstream integration surface in this harness had a group — alarmo,
    HACS, MQTT, powercalc, the Supervisor — but the Z-Wave JS integration,
    the WebSocket API that the Z-Wave configuration panel itself drives, had
    none. Everything below is a direct pass-through to the commands that
    ``homeassistant/components/zwave_js/api.py`` registers, plus the domain's
    services for the operations that only exist as services.

TWO IDENTIFIERS, KEPT APART
    The integration's commands take one of two identifiers and the schema
    makes them mutually exclusive:

      * ``device_id`` — a device-registry id (``zwave_js`` node-scoped
        commands: node_status, node_metadata, node_alerts,
        get_config_parameters, set_config_parameter, refresh_node_info,
        refresh_node_values, rebuild_node_routes, remove_failed_node,
        node_capabilities, invoke_cc_api, firmware upload);
      * ``entry_id`` — the config-entry id (entry-scoped commands:
        network_status, get_log_config, update_log_config,
        data_collection_status, update_data_collection_preference,
        check_for_config_updates, install_config_update,
        begin/stop_rebuilding_routes, hard_reset_controller,
        get_integration_settings).

    Humans think in entity ids, so every node-scoped function also accepts a
    ``<domain>.<object_id>`` entity id and resolves it through the entity
    registry first (:func:`resolve_device_id`).

WHEN THE INTEGRATION IS NOT LOADED
    HA answers every ``zwave_js/...`` command with ``unknown_command`` —
    the same code it gives a genuinely misspelled command. Every function
    here re-raises that as :data:`ABSENT_NOTE`, which names the integration
    and points at ``system components`` (the same pattern the supervisor
    module uses). ``available()`` turns the same condition into an
    answer instead of an error, so scripts can branch on it.

Public API
----------
* :func:`available`                  — is zwave_js loaded (no error when no)
* :func:`resolve_device_id`          — entity id → device id (passthrough)
* :func:`list_nodes`                 — devices owned by zwave_js (node ids)
* :func:`network_status`             — WS ``zwave_js/network_status``
* :func:`node_status` / :func:`node_metadata` / :func:`node_alerts`
* :func:`node_capabilities`
* :func:`config_parameters` / :func:`set_config_parameter`
* :func:`refresh_node_info` / :func:`refresh_node_values`
* :func:`rebuild_node_routes` / :func:`begin_rebuilding_routes`
* :func:`stop_rebuilding_routes` / :func:`remove_failed_node`
* :func:`hard_reset_controller`
* :func:`get_log_config` / :func:`update_log_config`
* :func:`data_collection_status` / :func:`update_data_collection_preference`
* :func:`check_for_config_updates` / :func:`install_config_update`
* :func:`integration_settings`
* :func:`ping` / :func:`set_lock_usercode` / :func:`clear_lock_usercode`
* :func:`set_lock_configuration`
* :func:`add_node` / :func:`remove_node` / :func:`stop_inclusion` /
  :func:`stop_exclusion` / :func:`replace_failed_node`
* :func:`grant_security_classes` / :func:`validate_dsk_and_enter_pin` /
  :func:`cancel_secure_bootstrap_s2`
* :func:`provision_smart_start_node` / :func:`unprovision_smart_start_node` /
  :func:`get_provisioning_entries` / :func:`parse_qr_code_string` /
  :func:`try_parse_dsk_from_qr_code_string`
* :func:`refresh_node_cc_values` / :func:`invoke_cc_api` /
  :func:`supports_feature`
* :func:`get_raw_config_parameter` / :func:`set_raw_config_parameter`
* :func:`get_node_firmware_update_capabilities` /
  :func:`is_node_firmware_update_in_progress` /
  :func:`is_any_ota_firmware_update_in_progress` / :func:`abort_firmware_update`
"""

from __future__ import annotations

from typing import Any

from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

DOMAIN = "zwave_js"

#: ``unknown_command`` means the ``zwave_js`` integration is not loaded:
#: no Z-Wave controller is set up on this instance (or the integration was
#: disabled). Nothing in this group can work without it.
ABSENT_NOTE = (
    "This Home Assistant has no Z-Wave controller configured: the `zwave_js` "
    "integration is not loaded, so it never registered its `zwave_js/…` "
    "websocket commands. Confirm it independently with `system components` — "
    "and to set one up, add the integration in the HA UI (Settings → Devices "
    "& Services) or a Z-Wave USB stick's serial path first."
)

#: Services the ``zwave_js`` domain registers (services.yaml). Kept here so
#: the wrappers validate against the real list rather than a typo.
LOCK_OPERATIONS = ("constant", "timed")


# ── plumbing ────────────────────────────────────────────────────────────────


def _is_absent(exc: HomeAssistantError) -> bool:
    return exc.code == "unknown_command"


def _raise_absent() -> None:
    raise HomeAssistantError(ABSENT_NOTE, code="unknown_command")


def _integration_loaded(client) -> bool:
    """Is ``zwave_js`` in the loaded-components list? (independent of the WS
    commands being registered — the read the error note points at).

    Returns True when the check itself fails, so the ORIGINAL error is what
    the caller sees rather than a wrong "not loaded" claim.
    """
    try:
        cfg = client.ws_call("get_config") or {}
    except HomeAssistantError:
        return True
    return DOMAIN in (cfg.get("components") or [])


def _ws(client, msg_type: str, payload: dict | None = None) -> Any:
    """One ``zwave_js/…`` websocket call, with the absent-integration guard."""
    try:
        return client.ws_call(msg_type, payload)
    except HomeAssistantError as exc:
        if _is_absent(exc):
            _raise_absent()
        raise


def _service(client, service: str, payload: dict) -> Any:
    """One ``services/zwave_js/<service>`` call, with the absent guard.

    A REST service call to a domain that is not loaded answers 400 with an
    empty body — indistinguishable by shape from any other bad request. The
    failure path therefore re-checks the components list: ``zwave_js``
    absent there is re-raised as :data:`ABSENT_NOTE`; anything else passes
    through untouched.
    """
    try:
        return client.post(f"services/zwave_js/{service}", payload)
    except HomeAssistantError:
        if not _integration_loaded(client):
            _raise_absent()
        raise


# ── identifiers ─────────────────────────────────────────────────────────────


def resolve_device_id(client, ident: str) -> str:
    """Map ``<domain>.<object_id>`` through the entity registry to a device id.

    A bare string is already treated as a device-registry id and passed
    through unchanged. An entity id that resolves to nothing (an orphan or a
    non-zwave helper) raises ValueError naming the entity — HA would answer
    the follow-up node command with a bare ``not_found`` that says nothing
    about which half of the resolution went wrong.
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


def _require_entry_id(entry_id: str | None) -> str:
    if not entry_id or not str(entry_id).strip():
        raise ValueError("entry_id (the zwave_js config entry id) is required")
    return str(entry_id).strip()


# ── availability ────────────────────────────────────────────────────────────


def available(client) -> dict:
    """Is the ``zwave_js`` integration loaded? A READ — 'no' is an answer.

    Checks the integration's presence in the loaded-components list (the same
    independent confirmation the error note points at), so the answer never
    depends on a websocket round-trip to a command that does not exist.
    """
    cfg = client.ws_call("get_config") or {}
    components = cfg.get("components") or []
    loaded = DOMAIN in components
    return {
        "available": loaded,
        "note": (
            "zwave_js is loaded; every `zwave` command works here." if loaded else ABSENT_NOTE
        ),
    }


def list_nodes(client, *, pattern: str | None = None) -> list[dict]:
    """The Z-Wave nodes HA knows about, as device-registry rows.

    There is no ``zwave_js/nodes`` websocket command — the Z-Wave panel lists
    its devices through the device registry, filtered to devices whose
    identifiers carry the ``zwave_js`` domain. Each row's identifier is
    ``("zwave_js", "<home_id>-<node_id>")``; ``node_id`` is extracted from it
    so the caller never has to parse HA's tuple encoding.
    """
    devices = client.ws_call("config/device_registry/list") or []
    p = (pattern or "").lower()
    out: list[dict] = []
    for dev in devices:
        identifiers = dev.get("identifiers") or []
        for pair in identifiers:
            if isinstance(pair, (list, tuple)) and pair and pair[0] == DOMAIN:
                node_id = None
                if len(pair) > 1 and pair[1]:
                    node_id = str(pair[1]).rsplit("-", 1)[-1]
                row = dict(dev)
                row["node_id"] = node_id
                if (
                    not p
                    or p in str(row.get("name") or "").lower()
                    or p in str(row.get("name_by_user") or "").lower()
                ):
                    out.append(row)
                break
    return out


# ── network / node reads ────────────────────────────────────────────────────


def network_status(client, *, entry_id: str | None = None, device_id: str | None = None) -> Any:
    """WS ``zwave_js/network_status`` — controller state, home id, statistics.

    The schema takes exactly one of ``entry_id`` / ``device_id`` (vol.Exclusive
    groups); pass at least one and not both.
    """
    if bool(entry_id) == bool(device_id):
        raise ValueError("pass exactly one of --entry or --device")
    payload: dict[str, Any] = {}
    if entry_id:
        payload["entry_id"] = _require_entry_id(entry_id)
    else:
        payload["device_id"] = resolve_device_id(client, device_id or "")
    return _ws(client, "zwave_js/network_status", payload)


def node_status(client, ident: str) -> Any:
    """WS ``zwave_js/node_status`` — one node's ready/dead state."""
    return _ws(client, "zwave_js/node_status", {"device_id": resolve_device_id(client, ident)})


def node_metadata(client, ident: str) -> Any:
    """WS ``zwave_js/node_metadata`` — vendor, product, protocol info."""
    return _ws(client, "zwave_js/node_metadata", {"device_id": resolve_device_id(client, ident)})


def node_alerts(client, ident: str) -> Any:
    """WS ``zwave_js/node_alerts`` — the node's current alert list."""
    return _ws(client, "zwave_js/node_alerts", {"device_id": resolve_device_id(client, ident)})


def node_capabilities(client, ident: str) -> Any:
    """WS ``zwave_js/node_capabilities`` — command classes and their versions."""
    return _ws(
        client, "zwave_js/node_capabilities", {"device_id": resolve_device_id(client, ident)}
    )


# ── configuration parameters ────────────────────────────────────────────────


def config_parameters(client, ident: str) -> dict:
    """WS ``zwave_js/get_config_parameters`` — every config parameter's metadata + value."""
    return _ws(
        client, "zwave_js/get_config_parameters", {"device_id": resolve_device_id(client, ident)}
    )


def set_config_parameter(
    client,
    ident: str,
    parameter: int,
    value: Any,
    *,
    property_key: int | None = None,
    endpoint: int = 0,
) -> Any:
    """WS ``zwave_js/set_config_parameter`` — write one config parameter.

    ``parameter`` is the numeric property id (HA's schema requires int);
    ``value`` is an int or a bitmask dict (``{"1": true, ...}``), which HA
    validates against BITMASK_SCHEMA. ``property_key`` selects the sub-
    parameter (bitmask bit / multi-channel endpoint); ``endpoint`` the node
    endpoint, default 0.
    """
    if not isinstance(parameter, int) or isinstance(parameter, bool):
        raise ValueError(f"parameter must be an integer, got {parameter!r}")
    if isinstance(value, bool) or not isinstance(value, (int, dict)):
        raise ValueError(f"value must be an integer or a bitmask object, got {value!r}")
    payload: dict[str, Any] = {
        "device_id": resolve_device_id(client, ident),
        "property": parameter,
        "endpoint": endpoint,
        "value": value,
    }
    if property_key is not None:
        payload["property_key"] = property_key
    return _ws(client, "zwave_js/set_config_parameter", payload)


# ── node maintenance ────────────────────────────────────────────────────────


def refresh_node_info(client, ident: str) -> Any:
    """WS ``zwave_js/refresh_node_info`` — re-interview: refresh all node info."""
    return _ws(
        client, "zwave_js/refresh_node_info", {"device_id": resolve_device_id(client, ident)}
    )


def refresh_node_values(client, ident: str) -> Any:
    """WS ``zwave_js/refresh_node_values`` — refresh every value on a node."""
    return _ws(
        client, "zwave_js/refresh_node_values", {"device_id": resolve_device_id(client, ident)}
    )


def rebuild_node_routes(client, ident: str) -> Any:
    """WS ``zwave_js/rebuild_node_routes`` — recalculate routes for one node."""
    return _ws(
        client, "zwave_js/rebuild_node_routes", {"device_id": resolve_device_id(client, ident)}
    )


def begin_rebuilding_routes(client, entry_id: str) -> Any:
    """WS ``zwave_js/begin_rebuilding_routes`` — heal the whole network."""
    return _ws(
        client, "zwave_js/begin_rebuilding_routes", {"entry_id": _require_entry_id(entry_id)}
    )


def stop_rebuilding_routes(client, entry_id: str) -> Any:
    """WS ``zwave_js/stop_rebuilding_routes`` — abort a network-wide rebuild."""
    return _ws(client, "zwave_js/stop_rebuilding_routes", {"entry_id": _require_entry_id(entry_id)})


def remove_failed_node(client, ident: str) -> Any:
    """WS ``zwave_js/remove_failed_node`` — drop a node the controller thinks is dead."""
    return _ws(
        client, "zwave_js/remove_failed_node", {"device_id": resolve_device_id(client, ident)}
    )


def hard_reset_controller(client, entry_id: str) -> Any:
    """WS ``zwave_js/hard_reset_controller`` — factory reset: ERASES the network."""
    return _ws(client, "zwave_js/hard_reset_controller", {"entry_id": _require_entry_id(entry_id)})


# ── logging ─────────────────────────────────────────────────────────────────


def get_log_config(client, entry_id: str) -> Any:
    """WS ``zwave_js/get_log_config`` — the Z-Wave driver's log level + sinks."""
    return _ws(client, "zwave_js/get_log_config", {"entry_id": _require_entry_id(entry_id)})


def update_log_config(
    client,
    entry_id: str,
    *,
    level: str | None = None,
    log_to_file: bool | None = None,
    filename: str | None = None,
    force_console: bool | None = None,
) -> Any:
    """WS ``zwave_js/update_log_config`` — change the Z-Wave driver's logging.

    ``level`` is the loguru-style level name (debug/info/warning/error, or
    ``off``). Only the fields you pass are sent — HA treats absent keys as
    "keep the current one".
    """
    config: dict[str, Any] = {}
    if level is not None:
        config["level"] = str(level)
    if log_to_file is not None:
        config["log_to_file"] = bool(log_to_file)
    if filename is not None:
        config["filename"] = str(filename)
    if force_console is not None:
        config["force_console"] = bool(force_console)
    if not config:
        raise ValueError("pass at least one of --level, --log-to-file, --filename, --force-console")
    return _ws(
        client,
        "zwave_js/update_log_config",
        {"entry_id": _require_entry_id(entry_id), "config": config},
    )


# ── telemetry / updates ─────────────────────────────────────────────────────


def data_collection_status(client, entry_id: str) -> Any:
    """WS ``zwave_js/data_collection_status`` — telemetry opt-in state + endpoint health."""
    return _ws(client, "zwave_js/data_collection_status", {"entry_id": _require_entry_id(entry_id)})


def update_data_collection_preference(client, entry_id: str, *, opted_in: bool) -> Any:
    """WS ``zwave_js/update_data_collection_preference`` — opt telemetry in/out."""
    return _ws(
        client,
        "zwave_js/update_data_collection_preference",
        {"entry_id": _require_entry_id(entry_id), "opted_in": bool(opted_in)},
    )


def check_for_config_updates(client, entry_id: str) -> Any:
    """WS ``zwave_js/check_for_config_updates`` — device database updates available?"""
    return _ws(
        client, "zwave_js/check_for_config_updates", {"entry_id": _require_entry_id(entry_id)}
    )


def install_config_update(client, entry_id: str) -> Any:
    """WS ``zwave_js/install_config_update`` — apply pending device-database updates."""
    return _ws(client, "zwave_js/install_config_update", {"entry_id": _require_entry_id(entry_id)})


def integration_settings(client, entry_id: str) -> Any:
    """WS ``zwave_js/get_integration_settings`` — poll interval, ignore timeouts, ..."""
    return _ws(
        client, "zwave_js/get_integration_settings", {"entry_id": _require_entry_id(entry_id)}
    )


# ── services ────────────────────────────────────────────────────────────────


def ping(client, entity_id: str) -> Any:
    """``zwave_js/ping`` service — round-trip one device over the mesh."""
    _require_lock_entity(entity_id, required_domain=None)
    return _service(client, "ping", {"entity_id": entity_id})


def _require_lock_entity(entity_id: str, *, required_domain: str = "lock") -> None:
    if not entity_id or not entity_id.strip():
        raise ValueError("entity_id is required")
    entity_id = entity_id.strip()
    if required_domain and not entity_id.startswith(f"{required_domain}."):
        raise ValueError(f"expected {required_domain}.* entity_id, got {entity_id!r}")


def set_lock_usercode(client, entity_id: str, slot: int, code: str) -> Any:
    """``zwave_js/set_lock_usercode`` — program one lock's user code slot."""
    _require_lock_entity(entity_id)
    if not isinstance(slot, int) or isinstance(slot, bool) or slot < 1:
        raise ValueError(f"code_slot must be a positive integer, got {slot!r}")
    if not code:
        raise ValueError("usercode is required")
    return _service(
        client,
        "set_lock_usercode",
        {"entity_id": entity_id, "code_slot": slot, "usercode": code},
    )


def clear_lock_usercode(client, entity_id: str, slot: int) -> Any:
    """``zwave_js/clear_lock_usercode`` — wipe one lock's user code slot."""
    _require_lock_entity(entity_id)
    if not isinstance(slot, int) or isinstance(slot, bool) or slot < 1:
        raise ValueError(f"code_slot must be a positive integer, got {slot!r}")
    return _service(
        client,
        "clear_lock_usercode",
        {"entity_id": entity_id, "code_slot": slot},
    )


def set_lock_configuration(
    client,
    entity_id: str,
    *,
    operation_type: str,
    lock_timeout: int | None = None,
    auto_relock_time: int | None = None,
) -> Any:
    """``zwave_js/set_lock_configuration`` — RF-relock behaviour of one lock.

    ``operation_type`` is ``constant`` (always relock after auto_relock_time)
    or ``timed`` (relock only when left unlocked by keypad for lock_timeout
    seconds) — the two options zwave_js's services.yaml offers.
    """
    _require_lock_entity(entity_id)
    if operation_type not in LOCK_OPERATIONS:
        raise ValueError(
            f"operation_type must be one of {', '.join(LOCK_OPERATIONS)}, got {operation_type!r}"
        )
    payload: dict[str, Any] = {"entity_id": entity_id, "operation_type": operation_type}
    if lock_timeout is not None:
        payload["lock_timeout"] = lock_timeout
    if auto_relock_time is not None:
        payload["auto_relock_time"] = auto_relock_time
    return _service(client, "set_lock_configuration", payload)


# ── pairing: strategies, S2 classes, value formats ──────────────────────────

#: zwave-js-server ``InclusionStrategy`` ids (the integration's schema coerces
#: to this enum). ``SMART_START`` (1) is deliberately absent from ADD choices:
#: HA's ``zwave_js/add_node`` schema refuses it — SmartStart pairing rides in
#: a provisioning option, not as a strategy.
INCLUSION_STRATEGIES = {
    "default": 0,
    "smart_start": 1,
    "insecure": 2,
    "security_s0": 3,
    "security_s2": 4,
}
ADD_STRATEGY_CHOICES = tuple(INCLUSION_STRATEGIES)  # validated names (ints pass raw)

#: zwave-js-server ``ExclusionStrategy`` ids — the enum has exactly one member.
EXCLUSION_STRATEGIES = {"default": 0}

#: zwave-js-server ``SecurityClass`` ids. Sent as the ENUM NAME (an IntEnum
#: accepts its own name), so HA's ``vol.Coerce(SecurityClass)`` resolves it
#: and a typo is refused client-side rather than by HA's generic schema error.
SECURITY_CLASSES = {
    "s2_unauthenticated": "S2_Unauthenticated",
    "s2_authenticated": "S2_Authenticated",
    "s2_authenticated_nomr": "S2_AuthenticatedNoMR",
    "s0_legacy": "S0_Legacy",
}

#: zwave-js-server ``ConfigurationValueFormat`` ids (raw config-parameter
#: writes carry the wire format explicitly — a read returns whatever the
#: parameter stores).
VALUE_FORMATS = {
    "signed_integer": "SignedInteger",
    "unsigned_integer": "UnsignedInteger",
    "enumerated": "Enumerated",
    "bitfield": "BitField",
}

#: Controller events that END a pairing run. ``add_node``/``remove_node`` are
#: ACK-then-stream commands — the controller stays in pairing mode emitting
#: events until the device joins (or it gives up) — so the client needs its
#: own terminal condition: the pairing outcome event.
_INCLUSION_TERMINAL = frozenset({"node added", "inclusion failed", "inclusion stopped"})
_EXCLUSION_TERMINAL = frozenset({"node removed", "exclusion failed", "exclusion stopped"})

_PAIRING_TIMEOUT = 300.0  # pairing waits for a physical button press — not 10 s


def _strategy_id(name_or_int: int | str, table: dict, what: str, choices: tuple) -> int:
    """A pairing strategy: a documented name or a raw zwave-js-server id."""
    if isinstance(name_or_int, bool):
        raise ValueError(f"{what} must be a name or integer, got a bool")
    if isinstance(name_or_int, int):
        return name_or_int
    key = (name_or_int or "").strip().lower().replace("-", "_")
    if key not in table:
        raise ValueError(f"{what} must be one of {', '.join(choices)}, got {name_or_int!r}")
    return table[key]


def _run_pairing(
    client,
    msg_type: str,
    payload: dict,
    terminal: frozenset,
    *,
    timeout: float | None = None,
) -> dict:
    """One ACK-then-stream pairing command, collected to its outcome event.

    The integration streams ``{"event": …}`` dicts after the ack and keeps
    them coming until the controller leaves pairing mode; HA's own frontend
    unsubscribes once the outcome event arrives. :meth:`ws_run_events` with a
    terminal predicate on that event is the same contract — without it the
    command either never returns (a subscription) or closes the socket at the
    ack and cancels the pairing server-side (a request/response read).
    """
    limit = float(timeout) if timeout else _PAIRING_TIMEOUT
    try:
        events = client.ws_run_events(
            msg_type,
            payload,
            is_terminal=lambda event: str(event.get("event", "")) in terminal,
            timeout=limit,
        )
    except HomeAssistantError as exc:
        if _is_absent(exc):
            _raise_absent()
        raise
    outcome = next(
        (str(e.get("event")) for e in events if str(e.get("event", "")) in terminal),
        None,
    )
    if outcome == "inclusion failed" or outcome == "exclusion failed":
        result, note = "failed", "the controller reported the pairing failed"
    elif outcome in ("inclusion stopped", "exclusion stopped"):
        result, note = "stopped", "pairing mode ended without a device joining"
    elif outcome in ("node added", "node removed"):
        result, note = "ok", f"the device {outcome}: {outcome}"  # note refined below
        if outcome == "node added":
            node = next((e.get("node") for e in events if e.get("event") == "node added"), None)
            if isinstance(node, dict):
                note = f"node {node.get('node_id')} added"
        else:
            node = next((e.get("node") for e in events if e.get("event") == "node removed"), {})
            if isinstance(node, dict):
                note = f"node {node.get('node_id')} removed (reason: {node.get('reason')})"

    else:
        result = (
            "pending"
            if outcome is None
            else "ok"  # pragma: no cover — unreachable with the sets above
        )
        note = (
            f"pairing is still in progress after {int(limit)} s — the device may not "
            "have been put into pairing mode yet; retry with a longer --timeout, "
            "then confirm with `zwave nodes`"
            if outcome is None
            else note  # pragma: no cover
        )
    return {"result": result, "outcome": outcome, "events": events, "note": note}


# ── pairing: inclusion / exclusion runs ─────────────────────────────────────


def add_node(
    client,
    entry_id: str,
    *,
    strategy: int | str = 0,
    force_security: bool | None = None,
    qr_code_string: str | None = None,
    dsk: str | None = None,
    timeout: float | None = None,
) -> dict:
    """WS ``zwave_js/add_node`` — start pairing and stream to the outcome.

    Run-to-completion: the controller enters inclusion mode, and each event
    (``inclusion started``, ``node found``, the S2 grant/DSK callbacks,
    ``node added``) streams back until the outcome. The S2 steps that pause
    the run are answered with :func:`grant_security_classes` and
    :func:`validate_dsk_and_enter_pin` — IN A SECOND TERMINAL, because this
    one stays busy streaming. Pairing waits for a physical button press, so
    pair with a generous ``--timeout`` (the default is 300 s).

    Exactly one provisioning option may ride along: ``--qr`` (a scanned SmartStart
    QR string) or ``--dsk`` (the device-specific key for S2). HA's schema makes
    the four options mutually exclusive and refuses a bare SmartStart strategy.
    """
    strategy_id = _strategy_id(
        strategy,
        INCLUSION_STRATEGIES,
        "strategy",
        tuple(k for k in INCLUSION_STRATEGIES if k != "smart_start"),
    )
    if isinstance(strategy_id, int) and strategy_id == INCLUSION_STRATEGIES["smart_start"]:
        raise ValueError(
            "strategy 'smart_start' is refused by zwave_js/add_node — SmartStart "
            "pairing is entered through a provisioning option, not a strategy"
        )
    options = [opt for opt in (qr_code_string, dsk) if opt]
    if len(options) > 1:
        raise ValueError("pass at most one of --qr and --dsk")
    payload: dict[str, Any] = {"entry_id": _require_entry_id(entry_id)}
    if strategy_id != 0:
        # The schema defaults to InclusionStrategy.DEFAULT — send the key
        # only when the caller picked one, so the recorded payload shows
        # exactly the caller's delta.
        payload["inclusion_strategy"] = strategy_id
    if force_security is not None:
        payload["force_security"] = bool(force_security)
    if qr_code_string:
        payload["qr_code_string"] = str(qr_code_string)
    if dsk:
        payload["dsk"] = str(dsk)
    return _run_pairing(client, "zwave_js/add_node", payload, _INCLUSION_TERMINAL, timeout=timeout)


def remove_node(
    client,
    entry_id: str,
    *,
    strategy: int | str = 0,
    timeout: float | None = None,
) -> dict:
    """WS ``zwave_js/remove_node`` — start exclusion and stream to the outcome.

    Same run-to-completion shape as :func:`add_node`: put the device into
    its own "excluded" mode, the controller emits ``node removed`` (with the
    reason), and the run ends. The only strategy the current
    zwave-js-server enum offers is ``default``.
    """
    payload: dict[str, Any] = {"entry_id": _require_entry_id(entry_id)}
    strategy_id = _strategy_id(strategy, EXCLUSION_STRATEGIES, "strategy", ("default",))
    if strategy_id != EXCLUSION_STRATEGIES["default"]:
        # The enum currently has exactly one member; the key rides only when
        # a future server adds more, so the default payload stays minimal.
        payload["strategy"] = strategy_id
    return _run_pairing(
        client, "zwave_js/remove_node", payload, _EXCLUSION_TERMINAL, timeout=timeout
    )


def stop_inclusion(client, entry_id: str) -> dict:
    """WS ``zwave_js/stop_inclusion`` — cancel an add-node in progress."""
    result = _ws(client, "zwave_js/stop_inclusion", {"entry_id": _require_entry_id(entry_id)})
    return {"result": "ok", "controller_says": result}


def stop_exclusion(client, entry_id: str) -> dict:
    """WS ``zwave_js/stop_exclusion`` — cancel a remove-node in progress."""
    result = _ws(client, "zwave_js/stop_exclusion", {"entry_id": _require_entry_id(entry_id)})
    return {"result": "ok", "controller_says": result}


def replace_failed_node(
    client,
    ident: str,
    *,
    strategy: int | str = 0,
    force_security: bool | None = None,
    qr_code_string: str | None = None,
    timeout: float | None = None,
) -> dict:
    """WS ``zwave_js/replace_failed_node`` — re-pair a node the controller calls dead.

    Same streaming shape as :func:`add_node`: the failed node is dropped and
    its replacement is paired in the same slot. No ``--dsk`` — the S2 boot-
    strap of a replacement rides the DSK the node itself reports.
    """
    strategy_id = _strategy_id(
        strategy,
        INCLUSION_STRATEGIES,
        "strategy",
        tuple(k for k in INCLUSION_STRATEGIES if k != "smart_start"),
    )
    payload: dict[str, Any] = {"device_id": resolve_device_id(client, ident)}
    if strategy_id != 0:
        payload["inclusion_strategy"] = strategy_id
    if force_security is not None:
        payload["force_security"] = bool(force_security)
    if qr_code_string:
        payload["qr_code_string"] = str(qr_code_string)
    return _run_pairing(
        client, "zwave_js/replace_failed_node", payload, _INCLUSION_TERMINAL, timeout=timeout
    )


# ── pairing: the S2 callbacks the run pauses on ─────────────────────────────


def grant_security_classes(
    client,
    entry_id: str,
    security_classes: list[int | str],
    *,
    client_side_auth: bool = False,
) -> dict:
    """WS ``zwave_js/grant_security_classes`` — answer a ``grant_security_classes`` pause.

    The controller asks which security classes it may grant during an S2
    inclusion. ``security_classes`` takes the class NAMES (``s2_unauthenticated``,
    ``s2_authenticated``, ``s2_authenticated_nomr``, ``s0_legacy``) or their
    zwave-js-server ids (0-3). The names are sent as the enum names HA itself
    coerces, so a typo is refused HERE, not by a generic HA schema error.
    """
    if not security_classes:
        raise ValueError("pass at least one security class")
    payload: dict[str, Any] = {"entry_id": _require_entry_id(entry_id)}
    granted = []
    for cls in security_classes:
        if isinstance(cls, bool):
            raise ValueError("security class must be a name or integer, got a bool")
        if isinstance(cls, int):
            if not 0 <= cls <= 3:
                raise ValueError(f"security class id must be 0-3, got {cls}")
            granted.append(cls)
            continue
        key = (cls or "").strip().lower()
        if key not in SECURITY_CLASSES:
            raise ValueError(
                f"unknown security class {cls!r} — pass one of {', '.join(SECURITY_CLASSES)}"
            )
        granted.append(SECURITY_CLASSES[key])
    payload["securityClasses"] = granted
    if client_side_auth:
        payload["clientSideAuth"] = True
    _ws(client, "zwave_js/grant_security_classes", payload)
    return {"result": "ok", "granted": granted}


def validate_dsk_and_enter_pin(client, entry_id: str, pin: str) -> dict:
    """WS ``zwave_js/validate_dsk_and_enter_pin`` — answer a DSK/PIN pause.

    During S2 inclusion the controller surfaces the first five digits of the
    node's DSK (the ``validate dsk and enter pin`` event in an
    :func:`add_node` run); the user answers with the PIN printed on the
    device. Passing the FULL DSK instead of the PIN is the classic mistake —
    the schema takes exactly the short PIN string.
    """
    pin = (pin or "").strip()
    if not pin:
        raise ValueError("the device's PIN is required (its printed 5-digit code)")
    _ws(
        client,
        "zwave_js/validate_dsk_and_enter_pin",
        {"entry_id": _require_entry_id(entry_id), "pin": pin},
    )
    return {"result": "ok"}


def cancel_secure_bootstrap_s2(client, entry_id: str) -> dict:
    """WS ``zwave_js/cancel_secure_bootstrap_s2`` — abort a stuck S2 bootstrap."""
    _ws(client, "zwave_js/cancel_secure_bootstrap_s2", {"entry_id": _require_entry_id(entry_id)})
    return {"result": "ok"}


# ── SmartStart provisioning ─────────────────────────────────────────────────


def provision_smart_start_node(client, entry_id: str, *, qr_code_string: str) -> dict:
    """WS ``zwave_js/provision_smart_start_node`` — pre-provision from a QR string.

    A provisioned node joins AUTOMATICALLY when powered on near the
    controller — no button press, no :func:`add_node` run. (The schema also
    takes a fully-assembled ``planned_provisioning_entry`` object; the CLI
    exposes the QR path, which is what a scanner gives you.)
    """
    qr_code_string = (qr_code_string or "").strip()
    if not qr_code_string:
        raise ValueError("a SmartStart QR code string is required")
    _ws(
        client,
        "zwave_js/provision_smart_start_node",
        {"entry_id": _require_entry_id(entry_id), "qr_code_string": qr_code_string},
    )
    return {"result": "ok"}


def unprovision_smart_start_node(
    client, entry_id: str, *, dsk: str | None = None, node_id: int | None = None
) -> dict:
    """WS ``zwave_js/unprovision_smart_start_node`` — remove one provisioning entry.

    HA's schema takes EXACTLY ONE of the DSK string or the node id
    (``vol.Exclusive`` on the wire) — pass the other as None.
    """
    if bool(dsk) == bool(node_id is not None):
        raise ValueError("pass exactly one of --dsk or --node-id")
    payload: dict[str, Any] = {"entry_id": _require_entry_id(entry_id)}
    payload["dsk" if dsk else "node_id"] = str(dsk) if dsk else node_id
    _ws(client, "zwave_js/unprovision_smart_start_node", payload)
    return {"result": "ok"}


def get_provisioning_entries(client, entry_id: str) -> Any:
    """WS ``zwave_js/get_provisioning_entries`` — every pre-provisioned device."""
    return _ws(
        client, "zwave_js/get_provisioning_entries", {"entry_id": _require_entry_id(entry_id)}
    )


def parse_qr_code_string(client, entry_id: str, qr_code_string: str) -> Any:
    """WS ``zwave_js/parse_qr_code_string`` — decode a QR string to its fields."""
    qr_code_string = (qr_code_string or "").strip()
    if not qr_code_string:
        raise ValueError("a SmartStart QR code string is required")
    return _ws(
        client,
        "zwave_js/parse_qr_code_string",
        {"entry_id": _require_entry_id(entry_id), "qr_code_string": qr_code_string},
    )


def try_parse_dsk_from_qr_code_string(client, entry_id: str, qr_code_string: str) -> Any:
    """WS ``zwave_js/try_parse_dsk_from_qr_code_string`` — best-effort DSK only.

    Unlike :func:`parse_qr_code_string` this is TOLERANT: a string it cannot
    read returns ``{}`` rather than an error, because "no DSK visible" is an
    answer the caller branches on.
    """
    qr_code_string = (qr_code_string or "").strip()
    if not qr_code_string:
        raise ValueError("a SmartStart QR code string is required")
    return _ws(
        client,
        "zwave_js/try_parse_dsk_from_qr_code_string",
        {"entry_id": _require_entry_id(entry_id), "qr_code_string": qr_code_string},
    )


# ── command-class calls ─────────────────────────────────────────────────────


def refresh_node_cc_values(client, ident: str, command_class_id: int) -> Any:
    """WS ``zwave_js/refresh_node_cc_values`` — refresh values of ONE command class."""
    if not isinstance(command_class_id, int) or isinstance(command_class_id, bool):
        raise ValueError(f"command class id must be an integer, got {command_class_id!r}")
    return _ws(
        client,
        "zwave_js/refresh_node_cc_values",
        {"device_id": resolve_device_id(client, ident), "command_class_id": command_class_id},
    )


def invoke_cc_api(
    client,
    ident: str,
    command_class: int,
    method_name: str,
    *,
    parameters: list | None = None,
    endpoint: int | None = None,
    wait_for_result: bool | None = None,
) -> Any:
    """WS ``zwave_js/invoke_cc_api`` — call one zwave-js-server CC API method.

    This is the ESCAPE HATCH the integration's panel uses for anything the
    dedicated commands do not wrap: ``command_class`` is the numeric CC id,
    ``method_name`` the zwave-js-server API method (e.g. ``get``/``set`` on
    the Basic or ThermostatSetback command class) and ``parameters`` its
    positional list. ``wait_for_result`` — omit it for fire-and-forget;
    methods that return nothing answer an error when asked to wait.
    """
    if not isinstance(command_class, int) or isinstance(command_class, bool):
        raise ValueError(f"command class id must be an integer, got {command_class!r}")
    if not method_name or not str(method_name).strip():
        raise ValueError("method_name (the zwave-js-server API method) is required")
    if parameters is not None and not isinstance(parameters, list):
        # HA's schema is `list` — a dict ({"1": true}) would only make the
        # error HA's generic "expected a list"; refuse it HERE, named.
        raise ValueError(f"parameters must be a JSON list, got {parameters!r}")
    payload: dict[str, Any] = {
        "device_id": resolve_device_id(client, ident),
        "command_class": command_class,
        "method_name": str(method_name).strip(),
        "parameters": list(parameters or []),
    }
    if endpoint is not None:
        payload["endpoint"] = endpoint
    if wait_for_result is not None:
        payload["wait_for_result"] = bool(wait_for_result)
    return _ws(client, "zwave_js/invoke_cc_api", payload)


def supports_feature(client, entry_id: str, feature: int) -> dict:
    """WS ``zwave_js/supports_feature`` — does the controller support a feature id?

    ``feature`` is the raw zwave-js-server ``ZwaveFeature`` id (its enum, in
    the server's own numbering). The answer is the boolean the panel shows.
    """
    if not isinstance(feature, int) or isinstance(feature, bool):
        raise ValueError(f"feature must be an integer id, got {feature!r}")
    return _ws(
        client,
        "zwave_js/supports_feature",
        {"entry_id": _require_entry_id(entry_id), "feature": feature},
    )


# ── raw configuration parameters ────────────────────────────────────────────


def get_raw_config_parameter(client, ident: str, parameter: int) -> Any:
    """WS ``zwave_js/get_raw_config_parameter`` — one parameter's value, no metadata.

    The typed path (metadata + validation) is :func:`config_parameters`. The
    raw one answers for parameters the device database does not describe —
    which is exactly when the typed path returns nothing useful.
    """
    if not isinstance(parameter, int) or isinstance(parameter, bool):
        raise ValueError(f"parameter must be an integer, got {parameter!r}")
    return _ws(
        client,
        "zwave_js/get_raw_config_parameter",
        {"device_id": resolve_device_id(client, ident), "property": parameter},
    )


def set_raw_config_parameter(
    client,
    ident: str,
    parameter: int,
    value: int,
    *,
    value_size: int,
    value_format: int | str,
) -> Any:
    """WS ``zwave_js/set_raw_config_parameter`` — write a parameter with a raw shape.

    Raw means you supply what the typed path derives from the metadata:
    ``value_size`` (bytes, 1-4) and ``value_format`` — a
    ``signed_integer``/``unsigned_integer``/``enumerated``/``bitfield`` name
    or its zwave-js-server id. A wrong pair is a REAL write to the device —
    there is no metadata check to save you, so both are required here.
    """
    if not isinstance(parameter, int) or isinstance(parameter, bool):
        raise ValueError(f"parameter must be an integer, got {parameter!r}")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"value must be an integer, got {value!r}")
    if not isinstance(value_size, int) or isinstance(value_size, bool) or not 1 <= value_size <= 4:
        raise ValueError(f"value_size must be 1-4 (bytes), got {value_size!r}")
    if isinstance(value_format, str):
        key = value_format.strip().lower().replace("-", "_")
        if key not in VALUE_FORMATS:
            raise ValueError(
                f"value_format must be one of {', '.join(VALUE_FORMATS)}, got {value_format!r}"
            )
        fmt: str | int = VALUE_FORMATS[key]
    elif isinstance(value_format, int) and not isinstance(value_format, bool):
        fmt = value_format
    else:
        raise ValueError(f"value_format must be a name or integer, got {value_format!r}")
    return _ws(
        client,
        "zwave_js/set_raw_config_parameter",
        {
            "device_id": resolve_device_id(client, ident),
            "property": parameter,
            "value": value,
            "value_size": value_size,
            "value_format": fmt,
        },
    )


# ── firmware ────────────────────────────────────────────────────────────────


def get_node_firmware_update_capabilities(client, ident: str) -> Any:
    """WS ``zwave_js/get_node_firmware_update_capabilities`` — what firmware slot(s)."""
    return _ws(
        client,
        "zwave_js/get_node_firmware_update_capabilities",
        {"device_id": resolve_device_id(client, ident)},
    )


def is_node_firmware_update_in_progress(client, ident: str) -> Any:
    """WS ``zwave_js/is_node_firmware_update_in_progress`` — is THIS node updating?"""
    return _ws(
        client,
        "zwave_js/is_node_firmware_update_in_progress",
        {"device_id": resolve_device_id(client, ident)},
    )


def is_any_ota_firmware_update_in_progress(client, entry_id: str) -> Any:
    """WS ``zwave_js/is_any_ota_firmware_update_in_progress`` — is ANY node updating?"""
    return _ws(
        client,
        "zwave_js/is_any_ota_firmware_update_in_progress",
        {"entry_id": _require_entry_id(entry_id)},
    )


def abort_firmware_update(client, ident: str) -> dict:
    """WS ``zwave_js/abort_firmware_update`` — cancel a node's firmware transfer (destructive)."""
    _ws(client, "zwave_js/abort_firmware_update", {"device_id": resolve_device_id(client, ident)})
    return {
        "result": "ok",
        "note": "firmware update aborted on the controller — the device may need a power cycle",
    }
