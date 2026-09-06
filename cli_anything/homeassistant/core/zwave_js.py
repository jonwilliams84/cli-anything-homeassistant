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
