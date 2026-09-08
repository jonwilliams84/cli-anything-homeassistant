"""ZHA (Zigbee Home Automation) — the ``zha`` integration's WebSocket + service surface.

THE GAP THIS CLOSES
    The harness's Zigbee story was one incidental command (``system
    zha-permit-join``). ZHA is the de-facto Zigbee integration and its
    configuration panel is driven entirely by websocket commands registered
    in ``homeassistant/components/zha/websocket_api.py`` — devices, groups,
    cluster inspection, direct bindings, network settings and backups, all
    of them absent until now.

TWO COMMANDS THAT ARE DELIBERATELY NOT HERE
    * ``zha/devices/reconfigure`` — registers a subscription and streams
      progress events, but NEVER sends a result. A blocking request/response
      client would wait forever (the same class of trap as
      ``…/logs/follow``, see the v1.52.0 notes). Not exposed.
    * ``zha/topology/update`` — kicks off a network scan and returns
      NOTHING: no result, no events. Also not exposed.

    Everything else in the module answers ``result: ok`` and is wrapped
    below. ``zha/devices/permit`` does answer, but it is already wired as
    ``system zha-permit-join``; it is not duplicated here.

IDENTIFIERS
    ZHA addresses devices by **IEEE address** (an EUI-64, e.g.
    ``00:0d:6f:00:05:7d:2d:34``), not by device-registry id — the
    integration's schemas convert through zigpy's ``EUI64``, which tolerates
    ``:``, ``-``, ``.`` separators and a ``0x`` prefix but nothing else.
    Every IEEE argument is normalised and shape-checked here so a typo dies
    with a name of the offending value instead of HA's bare ``vol.Invalid``.
    Group members ride as ``<ieee>:<endpoint_id>`` strings in the CLI and as
    ``{"ieee": …, "endpoint_id": …}`` dicts on the wire.

WHEN THE INTEGRATION IS NOT LOADED
    The ``zha`` integration cannot even load without its Python dependencies
    (the ``zha`` / ``zigpy`` packages), and on a controller-less instance it
    is simply not set up. HA answers every ``zha/...`` websocket command
    with ``unknown_command`` — the same code a typo gets — and a ``zha``
    REST service call with a 400 and an EMPTY body. Every function here
    re-raises that as :data:`ABSENT_NOTE`, which names the integration and
    points at ``system components`` (the same pattern the zwave_js and
    supervisor modules use). ``available()`` turns the same condition into
    an answer with exit 0, so scripts branch on it.

Public API
----------
* :func:`available`                  — is zha loaded (no error when no)
* :func:`list_devices` / :func:`get_device` / :func:`groupable_devices`
* :func:`bindable_devices`
* :func:`list_groups` / :func:`get_group`
* :func:`clusters` / :func:`cluster_attributes` / :func:`cluster_commands`
* :func:`read_attribute`
* :func:`configuration` / :func:`update_configuration`
* :func:`network_settings` / :func:`list_network_backups`
* :func:`create_network_backup` / :func:`restore_network_backup`
* :func:`change_channel`
* :func:`add_group` / :func:`remove_groups`
* :func:`add_group_members` / :func:`remove_group_members`
* :func:`bind_devices` / :func:`unbind_devices`
* :func:`bind_to_group` / :func:`unbind_from_group`
* :func:`parse_ieee` / :func:`parse_member` / :func:`parse_binding`
* :func:`remove_device`
* :func:`set_cluster_attribute` / :func:`issue_cluster_command`
* :func:`issue_group_command`
* :func:`warning_squawk` / :func:`warning_warn`
"""

from __future__ import annotations

from typing import Any

from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

DOMAIN = "zha"

#: ``unknown_command`` means the ``zha`` integration is not loaded: ZHA is
#: either not set up (no coordinator) or its Python dependencies (the
#: ``zha`` / ``zigpy`` packages) are missing, so it never registered its
#: ``zha/…`` websocket commands.
ABSENT_NOTE = (
    "This Home Assistant has no ZHA (Zigbee) coordinator configured: the `zha` "
    "integration is not loaded, so it never registered its `zha/…` websocket "
    "commands. Confirm it independently with `system components` — and to set "
    "one up, add the integration in the HA UI with a Zigbee USB coordinator "
    "first. (`zha` also needs its `zha`/`zigpy` Python packages; a pip-installed "
    "HA without them cannot load the integration at all.)"
)

#: Cluster types the panel's own selectors offer. ``in``/``out`` is what
#: ``zha/devices/clusters`` returns in each row's ``type`` field.
CLUSTER_TYPES = ("in", "out")

#: Zigbee 2.4 GHz channels. HA validates ``vol.Range(11, 26)`` (or the
#: string ``auto``); refusing out-of-range values here reads better than
#: HA's bare ``vol.Invalid``.
ZIGBEE_CHANNELS = range(11, 27)

#: Warning-device modes. HA validates plain positive ints; these are the
#: semantic names the ZHA docs give each value, surfaced for the CLI help.
SQUAWK_MODES = ("armed", "disarmed")
WARN_MODES = (
    "stop",
    "burglar",
    "fire",
    "emergency",
    "police_panic",
    "fire_panic",
    "emergency_panic",
)


# ── plumbing ────────────────────────────────────────────────────────────────


def _is_absent(exc: HomeAssistantError) -> bool:
    return exc.code == "unknown_command"


def _raise_absent() -> None:
    raise HomeAssistantError(ABSENT_NOTE, code="unknown_command")


def _integration_loaded(client) -> bool:
    """Is ``zha`` in the loaded-components list? (independent of the WS
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
    """One ``zha/…`` websocket call, with the absent-integration guard."""
    try:
        return client.ws_call(msg_type, payload)
    except HomeAssistantError as exc:
        if _is_absent(exc):
            _raise_absent()
        raise


def _service(client, service: str, payload: dict) -> Any:
    """One ``services/zha/<service>`` call, with the absent guard.

    A REST service call to a domain that is not loaded answers 400 with an
    empty body — indistinguishable by shape from any other bad request. The
    failure path therefore re-checks the components list: ``zha`` absent
    there is re-raised as :data:`ABSENT_NOTE`; anything else passes through
    untouched.
    """
    try:
        return client.post(f"services/zha/{service}", payload)
    except HomeAssistantError:
        if not _integration_loaded(client):
            _raise_absent()
        raise


# ── identifiers ─────────────────────────────────────────────────────────────


def parse_ieee(raw: str) -> str:
    """Shape-check and normalise one IEEE address (EUI-64).

    Zigpy's ``EUI64.convert`` tolerates ``:``, ``-``, ``.`` and ``0x`` but
    nothing else, and demands exactly 16 hex digits. A value that fails the
    shape check is refused here with a name of the offender instead of HA's
    bare ``vol.Invalid`` — which says nothing about which argument was wrong.
    The SEPARATOR STYLE is preserved: HA's panel uses colon form, and
    normalising would rewrite what the caller sent.
    """
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("an IEEE address is required (e.g. 00:0d:6f:00:05:7d:2d:34)")
    body = raw.lower()
    for sep in (":", "-", ".", " "):
        body = body.replace(sep, "")
    if body.startswith("0x"):
        body = body[2:]
    if len(body) != 16 or any(c not in "0123456789abcdef" for c in body):
        raise ValueError(
            f"{raw!r} is not a 16-hex-digit IEEE address (e.g. 00:0d:6f:00:05:7d:2d:34)"
        )
    return raw


def parse_member(raw: str | dict) -> dict:
    """``<ieee>:<endpoint_id>`` → the ``{ieee, endpoint_id}`` dict HA wants.

    Split on the LAST colon so a colon-separated IEEE still parses. An
    already-parsed ``{ieee, endpoint_id}`` dict passes through validated —
    the Click callbacks parse before the core functions see the value.
    """
    if isinstance(raw, dict):
        if "ieee" not in raw or "endpoint_id" not in raw:
            raise ValueError(f"group member needs 'ieee' and 'endpoint_id', got {raw!r}")
        return {
            "ieee": parse_ieee(str(raw["ieee"])),
            "endpoint_id": _member_endpoint(raw["endpoint_id"]),
        }
    raw = (raw or "").strip()
    if ":" not in raw:
        raise ValueError(f"group member must be <ieee>:<endpoint>, got {raw!r}")
    ieee, _, endpoint = raw.rpartition(":")
    return {"ieee": parse_ieee(ieee), "endpoint_id": _member_endpoint(endpoint)}


def _member_endpoint(value) -> int:
    """The endpoint half of a group member: a plain integer, negative refused."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        if isinstance(value, str) and value.strip().isdigit():
            value = int(value.strip())
        else:
            raise ValueError(f"group member endpoint must be a non-negative integer, got {value!r}")
    return value


def parse_binding(raw: str | dict) -> dict:
    """A cluster binding: a JSON object (``{"name": …, "type": …, "id": …, "endpoint_id": …}``).

    Compact-string forms would collide with the ``:``-laden IEEE inside a
    human-typed ``name``, so bindings are JSON only — unambiguous and
    validated here against the same four keys HA's ``CLUSTER_BINDING_SCHEMA``
    demands. An already-parsed dict passes through validated.
    """
    import json

    if isinstance(raw, dict):
        parsed = raw
    else:
        raw = (raw or "").strip()
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"binding must be a JSON object, got {raw!r}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"binding must be a JSON object, got {raw!r}")
    missing = [k for k in ("name", "type", "id", "endpoint_id") if k not in parsed]
    if missing:
        raise ValueError(f"binding is missing {', '.join(missing)}: {parsed!r}")
    if not isinstance(parsed["id"], int) or isinstance(parsed["id"], bool):
        raise ValueError(f"binding id must be an integer, got {parsed['id']!r}")
    if not isinstance(parsed["endpoint_id"], int) or isinstance(parsed["endpoint_id"], bool):
        raise ValueError(f"binding endpoint_id must be an integer, got {parsed['endpoint_id']!r}")
    return parsed


# ── availability ────────────────────────────────────────────────────────────


def available(client) -> dict:
    """Is the ``zha`` integration loaded? A READ — 'no' is an answer.

    Checks the integration's presence in the loaded-components list (the
    same independent confirmation the error note points at), so the answer
    never depends on a websocket round-trip to a command that does not exist.
    """
    cfg = client.ws_call("get_config") or {}
    components = cfg.get("components") or []
    loaded = DOMAIN in components
    return {
        "available": loaded,
        "note": ("zha is loaded; every `zha` command works here." if loaded else ABSENT_NOTE),
    }


# ── devices ─────────────────────────────────────────────────────────────────


def list_devices(client) -> Any:
    """WS ``zha/devices`` — every device on the Zigbee network, ZHA's view."""
    return _ws(client, "zha/devices", None)


def get_device(client, ieee: str) -> Any:
    """WS ``zha/device`` — one device's ZHA info (routing, neighbours, entities)."""
    return _ws(client, "zha/device", {"ieee": parse_ieee(ieee)})


def groupable_devices(client) -> Any:
    """WS ``zha/devices/groupable`` — devices whose endpoints may join a group."""
    return _ws(client, "zha/devices/groupable", None)


def bindable_devices(client, ieee: str) -> Any:
    """WS ``zha/devices/bindable`` — devices that may be direct-bound to ``ieee``."""
    return _ws(client, "zha/devices/bindable", {"ieee": parse_ieee(ieee)})


# ── groups ──────────────────────────────────────────────────────────────────


def list_groups(client) -> Any:
    """WS ``zha/groups`` — every Zigbee group, ZHA's view."""
    return _ws(client, "zha/groups", None)


def get_group(client, group_id: int) -> Any:
    """WS ``zha/group`` — one group's info (members, entities)."""
    return _ws(client, "zha/group", {"group_id": _require_group_id(group_id)})


def add_group(client, name: str, *, group_id: int | None = None, members=None) -> Any:
    """WS ``zha/group/add`` — create a Zigbee group, optionally with members."""
    name = (name or "").strip()
    if not name:
        raise ValueError("a group name is required")
    payload: dict[str, Any] = {"name": name}
    if group_id is not None:
        payload["group_id"] = _require_group_id(group_id)
    if members:
        payload["members"] = [parse_member(m) for m in members]
    return _ws(client, "zha/group/add", payload)


def remove_groups(client, group_ids) -> Any:
    """WS ``zha/group/remove`` — delete one or more groups; returns what is left."""
    ids = [_require_group_id(g) for g in (group_ids or ())]
    if not ids:
        raise ValueError("at least one group id is required")
    return _ws(client, "zha/group/remove", {"group_ids": ids})


def add_group_members(client, group_id: int, members) -> Any:
    """WS ``zha/group/members/add`` — put devices into a group."""
    return _ws(
        client,
        "zha/group/members/add",
        {"group_id": _require_group_id(group_id), "members": _parse_members(members)},
    )


def remove_group_members(client, group_id: int, members) -> Any:
    """WS ``zha/group/members/remove`` — take devices out of a group."""
    return _ws(
        client,
        "zha/group/members/remove",
        {"group_id": _require_group_id(group_id), "members": _parse_members(members)},
    )


def _parse_members(members) -> list[dict]:
    parsed = [parse_member(m) for m in (members or ())]
    if not parsed:
        raise ValueError("at least one --member <ieee>:<endpoint> is required")
    return parsed


def _require_group_id(group_id) -> int:
    if isinstance(group_id, bool) or not isinstance(group_id, int) or group_id < 1:
        raise ValueError(f"group id must be a positive integer, got {group_id!r}")
    return group_id


# ── cluster inspection ──────────────────────────────────────────────────────


def clusters(client, ieee: str) -> Any:
    """WS ``zha/devices/clusters`` — every cluster on every endpoint of a device."""
    return _ws(client, "zha/devices/clusters", {"ieee": parse_ieee(ieee)})


def cluster_attributes(
    client, ieee: str, *, endpoint_id: int, cluster_id: int, cluster_type: str
) -> Any:
    """WS ``zha/devices/clusters/attributes`` — attribute names/ids of one cluster."""
    return _ws(
        client,
        "zha/devices/clusters/attributes",
        _cluster_payload(
            ieee, endpoint_id=endpoint_id, cluster_id=cluster_id, cluster_type=cluster_type
        ),
    )


def cluster_commands(
    client, ieee: str, *, endpoint_id: int, cluster_id: int, cluster_type: str
) -> Any:
    """WS ``zha/devices/clusters/commands`` — command ids/names/schemas of one cluster."""
    return _ws(
        client,
        "zha/devices/clusters/commands",
        _cluster_payload(
            ieee, endpoint_id=endpoint_id, cluster_id=cluster_id, cluster_type=cluster_type
        ),
    )


def read_attribute(
    client,
    ieee: str,
    *,
    endpoint_id: int,
    cluster_id: int,
    cluster_type: str,
    attribute: int,
    manufacturer: int | None = None,
) -> Any:
    """WS ``zha/devices/clusters/attributes/value`` — read one attribute, live.

    The result is the attribute's VALUE as a string (HA stringifies it) —
    not a structure, and failures are not distinguished: an unreadable
    attribute comes back as ``None``.
    """
    payload = _cluster_payload(
        ieee, endpoint_id=endpoint_id, cluster_id=cluster_id, cluster_type=cluster_type
    )
    if isinstance(attribute, bool) or not isinstance(attribute, int) or attribute < 0:
        raise ValueError(f"attribute id must be a non-negative integer, got {attribute!r}")
    payload["attribute"] = attribute
    if manufacturer is not None:
        if isinstance(manufacturer, bool) or not isinstance(manufacturer, int) or manufacturer < -1:
            raise ValueError(f"manufacturer must be an integer >= -1, got {manufacturer!r}")
        payload["manufacturer"] = manufacturer
    return _ws(client, "zha/devices/clusters/attributes/value", payload)


def _cluster_payload(
    ieee: str, *, endpoint_id: int, cluster_id: int, cluster_type: str
) -> dict[str, Any]:
    """The ieee+endpoint+cluster tuple three cluster commands share."""
    if isinstance(endpoint_id, bool) or not isinstance(endpoint_id, int) or endpoint_id < 0:
        raise ValueError(f"endpoint id must be a non-negative integer, got {endpoint_id!r}")
    if (
        isinstance(cluster_id, bool)
        or not isinstance(cluster_id, int)
        or not 0 <= cluster_id <= 65535
    ):
        raise ValueError(f"cluster id must be an integer 0..65535, got {cluster_id!r}")
    if cluster_type not in CLUSTER_TYPES:
        raise ValueError(f"cluster type must be 'in' or 'out', got {cluster_type!r}")
    return {
        "ieee": parse_ieee(ieee),
        "endpoint_id": endpoint_id,
        "cluster_id": cluster_id,
        "cluster_type": cluster_type,
    }


# ── bindings ────────────────────────────────────────────────────────────────


def bind_devices(client, source_ieee: str, target_ieee: str) -> Any:
    """WS ``zha/devices/bind`` — direct Zigbee binding between two devices."""
    return _ws(
        client,
        "zha/devices/bind",
        {"source_ieee": parse_ieee(source_ieee), "target_ieee": parse_ieee(target_ieee)},
    )


def unbind_devices(client, source_ieee: str, target_ieee: str) -> Any:
    """WS ``zha/devices/unbind`` — remove a direct binding between two devices."""
    return _ws(
        client,
        "zha/devices/unbind",
        {"source_ieee": parse_ieee(source_ieee), "target_ieee": parse_ieee(target_ieee)},
    )


def bind_to_group(client, source_ieee: str, group_id: int, bindings) -> Any:
    """WS ``zha/groups/bind`` — bind a device's clusters to a group."""
    return _ws(
        client,
        "zha/groups/bind",
        {
            "source_ieee": parse_ieee(source_ieee),
            "group_id": _require_group_id(group_id),
            "bindings": _parse_bindings(bindings),
        },
    )


def unbind_from_group(client, source_ieee: str, group_id: int, bindings) -> Any:
    """WS ``zha/groups/unbind`` — unbind a device's clusters from a group."""
    return _ws(
        client,
        "zha/groups/unbind",
        {
            "source_ieee": parse_ieee(source_ieee),
            "group_id": _require_group_id(group_id),
            "bindings": _parse_bindings(bindings),
        },
    )


def _parse_bindings(bindings) -> list[dict]:
    parsed = [parse_binding(b) for b in (bindings or ())]
    if not parsed:
        raise ValueError("at least one --binding (JSON object) is required")
    return parsed


# ── network settings / backups ──────────────────────────────────────────────


def configuration(client) -> Any:
    """WS ``zha/configuration`` — the ZHA options UI: schemas + current values."""
    return _ws(client, "zha/configuration", None)


def update_configuration(client, data: dict) -> Any:
    """WS ``zha/configuration/update`` — write ZHA's custom configuration.

    ``data`` is the full custom-configuration object the options UI edits
    (section → option → value). Reloads the config entry, so every ZHA
    entity is briefly unavailable.
    """
    if not isinstance(data, dict) or not data:
        raise ValueError("configuration data must be a non-empty JSON object")
    return _ws(client, "zha/configuration/update", {"data": data})


def network_settings(client) -> Any:
    """WS ``zha/network/settings`` — radio type, device path, active network settings."""
    return _ws(client, "zha/network/settings", None)


def list_network_backups(client) -> Any:
    """WS ``zha/network/backups/list`` — the Zigbee network backups on disk."""
    return _ws(client, "zha/network/backups/list", None)


def create_network_backup(client) -> Any:
    """WS ``zha/network/backups/create`` — take a fresh backup (5–30s).

    ``is_complete`` in the result says whether devices were included; a
    backup without them cannot restore a working network.
    """
    return _ws(client, "zha/network/backups/create", None)


def restore_network_backup(client, backup: dict, *, ezsp_force_write_eui64: bool = False) -> Any:
    """WS ``zha/network/backups/restore`` — RESTORE a network backup.

    Replaces the network settings on the coordinator. Pass the backup
    exactly as a ``network-backups`` row gave it. On EZ-SP (Silicon Labs)
    radios whose NVRAM already holds a different EUI64, HA refuses with a
    format error unless ``ezsp_force_write_eui64`` is set — that flag
    OVERWRITES the stick's identity, so it is its own decision.
    """
    if not isinstance(backup, dict):
        raise ValueError("backup must be the JSON object a `zha network-backups` row gave")
    payload: dict[str, Any] = {"backup": backup}
    if ezsp_force_write_eui64:
        payload["ezsp_force_write_eui64"] = True
    return _ws(client, "zha/network/backups/restore", payload)


def change_channel(client, new_channel) -> Any:
    """WS ``zha/network/change_channel`` — migrate the whole network (minutes).

    ``new_channel`` is ``auto`` or an integer 11–26. Every device must
    follow the migration over the air; battery devices that are asleep
    re-join late or not at all. There is no undo short of a network backup.
    """
    if new_channel == "auto":
        return _ws(client, "zha/network/change_channel", {"new_channel": "auto"})
    if (
        isinstance(new_channel, bool)
        or not isinstance(new_channel, int)
        or new_channel not in ZIGBEE_CHANNELS
    ):
        raise ValueError(f"new channel must be 'auto' or an integer 11–26, got {new_channel!r}")
    return _ws(client, "zha/network/change_channel", {"new_channel": new_channel})


# ── services ────────────────────────────────────────────────────────────────


def remove_device(client, ieee: str) -> Any:
    """``zha.remove`` service — drop a device from the network.

    The device must be power-cycled to re-join (or `system zha-permit-join`
    re-run); automations that referenced its entities keep pointing at
    nothing until then.
    """
    return _service(client, "remove", {"ieee": parse_ieee(ieee)})


def set_cluster_attribute(
    client,
    ieee: str,
    *,
    endpoint_id: int,
    cluster_id: int,
    attribute,
    value,
    cluster_type: str = "in",
    manufacturer: int | None = None,
) -> Any:
    """``zha.set_zigbee_cluster_attribute`` — write one Zigbee attribute directly.

    A raw zigbee write: no unit conversion, no state validation, and HA
    will happily send a value the device misinterprets. ``attribute`` may
    be the numeric id or the attribute's name; ``value`` int / bool / str.
    """
    payload = _cluster_payload(
        ieee, endpoint_id=endpoint_id, cluster_id=cluster_id, cluster_type=cluster_type
    )
    if not isinstance(attribute, (int, str)) or isinstance(attribute, bool):
        raise ValueError(f"attribute must be an integer id or a name, got {attribute!r}")
    if isinstance(value, float):
        raise ValueError(f"value must be an integer, boolean or string, got {value!r}")
    if not isinstance(value, (int, bool, str)):
        raise ValueError(f"value must be an integer, boolean or string, got {value!r}")
    payload["attribute"] = attribute
    payload["value"] = value
    if manufacturer is not None:
        if isinstance(manufacturer, bool) or not isinstance(manufacturer, int) or manufacturer < -1:
            raise ValueError(f"manufacturer must be an integer >= -1, got {manufacturer!r}")
        payload["manufacturer"] = manufacturer
    return _service(client, "set_zigbee_cluster_attribute", payload)


def issue_cluster_command(
    client,
    ieee: str,
    *,
    endpoint_id: int,
    cluster_id: int,
    command: int,
    command_type: str,
    cluster_type: str = "in",
    args: list | None = None,
    params: dict | None = None,
    manufacturer: int | None = None,
) -> Any:
    """``zha.issue_zigbee_cluster_command`` — invoke a raw Zigbee cluster command.

    ``args`` is a positional LIST, ``params`` a named dict — the schema
    makes them mutually exclusive and demands at least one. ``command_type``
    is ``client`` (a command the device sends) or ``server`` (one it
    receives); most automation wants ``server``.
    """
    if command_type not in ("client", "server"):
        raise ValueError(f"command type must be 'client' or 'server', got {command_type!r}")
    if bool(args is not None) == bool(params is not None):
        raise ValueError("pass exactly one of --params (JSON object) or --args (JSON list)")
    payload = _cluster_payload(
        ieee, endpoint_id=endpoint_id, cluster_id=cluster_id, cluster_type=cluster_type
    )
    if isinstance(command, bool) or not isinstance(command, int) or command < 0:
        raise ValueError(f"command id must be a non-negative integer, got {command!r}")
    payload["command"] = command
    payload["command_type"] = command_type
    if args is not None:
        if not isinstance(args, list):
            raise ValueError(f"args must be a JSON list, got {args!r}")
        payload["args"] = args
    else:
        if not isinstance(params, dict):
            raise ValueError(f"params must be a JSON object, got {params!r}")
        payload["params"] = params
    if manufacturer is not None:
        if isinstance(manufacturer, bool) or not isinstance(manufacturer, int) or manufacturer < -1:
            raise ValueError(f"manufacturer must be an integer >= -1, got {manufacturer!r}")
        payload["manufacturer"] = manufacturer
    return _service(client, "issue_zigbee_cluster_command", payload)


def issue_group_command(
    client,
    group_id: int,
    *,
    cluster_id: int,
    command: int,
    cluster_type: str = "in",
    args: list | None = None,
    manufacturer: int | None = None,
) -> Any:
    """``zha.issue_zigbee_group_command`` — broadcast a command to a group."""
    if (
        isinstance(cluster_id, bool)
        or not isinstance(cluster_id, int)
        or not 0 <= cluster_id <= 65535
    ):
        raise ValueError(f"cluster id must be an integer 0..65535, got {cluster_id!r}")
    if isinstance(command, bool) or not isinstance(command, int) or command < 0:
        raise ValueError(f"command id must be a non-negative integer, got {command!r}")
    payload: dict[str, Any] = {
        "group": _require_group_id(group_id),
        "cluster_id": cluster_id,
        "cluster_type": cluster_type,
        "command": command,
        "args": list(args or []),
    }
    if manufacturer is not None:
        if isinstance(manufacturer, bool) or not isinstance(manufacturer, int) or manufacturer < -1:
            raise ValueError(f"manufacturer must be an integer >= -1, got {manufacturer!r}")
        payload["manufacturer"] = manufacturer
    return _service(client, "issue_zigbee_group_command", payload)


def warning_squawk(client, ieee: str, *, mode: int = 0, strobe: int = 1, level: int = 2) -> Any:
    """``zha.warning_device_squawk`` — one short siren chirp (an IAS warning device).

    Defaults are HA's: mode 0 (armed), strobe 1, level 2 (very high).
    """
    payload = {"ieee": parse_ieee(ieee), **_warn_fields(mode=mode, strobe=strobe, level=level)}
    return _service(client, "warning_device_squawk", payload)


def warning_warn(
    client,
    ieee: str,
    *,
    mode: int = 3,
    strobe: int = 1,
    level: int = 2,
    duration: int = 5,
    duty_cycle: int = 0,
    intensity: int = 2,
) -> Any:
    """``zha.warning_device_warn`` — sound the siren for ``duration`` seconds.

    Defaults are HA's: mode 3 (emergency), strobe 1, level 2, 5 s, duty
    cycle 0, intensity 2.
    """
    payload = {
        "ieee": parse_ieee(ieee),
        **_warn_fields(
            mode=mode,
            strobe=strobe,
            level=level,
            duration=duration,
            duty_cycle=duty_cycle,
            intensity=intensity,
        ),
    }
    return _service(client, "warning_device_warn", payload)


def _warn_fields(**fields: int) -> dict[str, int]:
    out: dict[str, int] = {}
    for key, value in fields.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{key} must be a non-negative integer, got {value!r}")
        out[key] = value
    return out
