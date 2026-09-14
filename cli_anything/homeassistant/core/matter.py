"""Matter — the ``matter`` integration's WebSocket surface.

THE GAP THIS CLOSES
    Every mainstream integration surface in this harness had a command group —
    alarmo, HACS, MQTT, powercalc, the Supervisor, zwave_js — but Matter, the
    integration that runs the very hub most smart-home purchases ship for,
    had none. Everything below is a direct pass-through to the nine commands
    ``homeassistant/components/matter/api.py`` registers (2026.8.x), plus a
    device-registry read for listing the nodes.

THE NINE WEBSOCKET COMMANDS
    = node-scoped (``device_id``) = ===========================================
    ``matter/node_diagnostics``  — the node's full attribute dump
    ``matter/ping_node``         — round-trip on the node's known addresses
    ``matter/interview_node``    — re-read the device's data model
    ``matter/open_commissioning_window`` — pair the device to ANOTHER
        controller (admin)
    ``matter/remove_matter_fabric`` — erase the device's membership of one
        fabric (admin)
    = not node-scoped = =======================================================
    ``matter/commission``            — pair via QR / manual code (admin)
    ``matter/commission_on_network`` — pair a device already on the IP network
        (admin)
    ``matter/set_wifi_credentials``  — the Wi-Fi new devices are told to join
        (admin)
    ``matter/set_thread``            — the Thread network they are told to join
        (admin)

    HA marks the first five ``@require_admin`` — ping, interview and
    node_diagnostics are deliberately open to non-admin connections. That
    split is upstream's; this module does not duplicate the check, it just
    translates what a non-admin connection gets back.

TWO IDENTIFIERS, KEPT APART
    Upstream resolves a ``device_id`` to a Matter node through the device
    registry: the entry must carry a ``("matter", "deviceid_…")`` identifier
    and the controller's server info must be up. Failures come back as the
    websocket error code ``node_not_found`` with two very different meanings —
    "no such device id" and "that device id is not a Matter device" — and the
    message names the id but never the remedy. Every node-scoped function here
    re-raises that as a :class:`ValueError` that does. Like the ``zwave``
    group, node-scoped functions also accept a ``<domain>.<object_id>`` entity
    id and resolve it through the entity registry first.

THE NODE ID HIDES IN THE IDENTIFIER
    A Matter device row's identifier is ``("matter", "deviceid_<device-id>")``
    where ``<device-id>`` is ``<compressed_fabric_id:016X>-<node_id:016X>``
    followed by ``-MatterNodeDevice`` (whole-node device) or ``-<endpoint>``
    (one endpoint of a bridged device). :func:`list_nodes` extracts the node
    id so callers never parse HA's encoding; the fabric id comes out too,
    which is what tells multiple fabrics apart.

WHEN THE INTEGRATION IS NOT LOADED
    HA answers every ``matter/...`` command with ``unknown_command`` — the
    same code a typo gets. On a Core install there is a concrete second
    reason: ``matter`` needs the ``python-matter-server`` package, and
    without it the integration cannot even be set up. Every function here
    re-raises that as :data:`ABSENT_NOTE`, which names both routes;
    :func:`available` turns the same condition into an answer with exit 0.

TWO MORE WIRE TRAPS
    * A successful commissioning answers an EMPTY result — there is no node
      id, no device id, nothing. The wrappers say so out loud and point at
      ``matter nodes`` (the new device row appears in the registry within
      seconds, via the generic registry, not a Matter command).
    * ``remove_matter_fabric`` and both commission commands can take MINUTES
      (they wait on the device's own commissioning window). The client's
      websocket timeout still applies on top — pass ``--timeout`` generously.

Public API
----------
* :func:`available`             — is matter loaded (no error when no)
* :func:`resolve_device_id`     — entity id → device id (passthrough)
* :func:`list_nodes`            — Matter devices in the registry (node ids)
* :func:`commission`            — WS ``matter/commission``
* :func:`commission_on_network` — WS ``matter/commission_on_network``
* :func:`set_wifi_credentials`  — WS ``matter/set_wifi_credentials``
* :func:`set_thread`            — WS ``matter/set_thread``
* :func:`node_diagnostics`      — WS ``matter/node_diagnostics``
* :func:`ping_node`             — WS ``matter/ping_node``
* :func:`interview_node`        — WS ``matter/interview_node``
* :func:`open_commissioning_window`
* :func:`remove_fabric`         — WS ``matter/remove_matter_fabric``
"""

from __future__ import annotations

from typing import Any

from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

DOMAIN = "matter"

#: ``unknown_command`` means the ``matter`` integration is not loaded: either
#: no Matter hub is configured, or this is a Core install without the
#: ``python-matter-server`` package the integration is built on. Nothing in
#: this group can work without it.
ABSENT_NOTE = (
    "This Home Assistant has no Matter controller configured: the `matter` "
    "integration is not loaded, so it never registered its `matter/…` "
    "websocket commands. On a Core install the integration also needs the "
    "`python-matter-server` package to be importable. Confirm it "
    "independently with `system components` — and set the integration up in "
    "the HA UI (Settings → Devices & Services → Add Integration → Matter) "
    "first."
)

#: The error code HA's ``@async_handle_failed_command`` sends for every
#: Matter failure: ``str(err.error_code)`` of the underlying MatterError.
NODE_NOT_FOUND = "node_not_found"

#: How many digits a Matter manual-pairing code carries. HA's schema only
#: demands ``int`` — the server rejects the rest — but an 11- or 31-character
#: CODE passed as ``--pin`` is always a commissioning CODE in the wrong
#: argument, so the client names the mistake instead of the server.
PIN_LENGTHS = (8, 11)

#: FabricIndex is a uint8 with 0 reserved and 255 meaning "wildcard" in some
#: contexts — usable values are 1..254.
FABRIC_INDEX_RANGE = (1, 254)


# ── plumbing ────────────────────────────────────────────────────────────────


def _is_absent(exc: HomeAssistantError) -> bool:
    return exc.code == "unknown_command"


def _raise_absent() -> None:
    raise HomeAssistantError(ABSENT_NOTE, code="unknown_command")


def _integration_loaded(client) -> bool:
    """Is ``matter`` in the loaded-components list? (the independent read the
    error note points at).

    Returns True when the check itself fails, so the ORIGINAL error is what
    the caller sees rather than a wrong "not loaded" claim.
    """
    try:
        cfg = client.ws_call("get_config") or {}
    except HomeAssistantError:
        return True
    return DOMAIN in (cfg.get("components") or [])


def _ws(client, msg_type: str, payload: dict | None = None) -> Any:
    """One ``matter/…`` websocket call, with the absent-integration guard and
    the ``node_not_found`` translation.
    """
    try:
        return client.ws_call(msg_type, payload)
    except HomeAssistantError as exc:
        if _is_absent(exc):
            _raise_absent()
        if exc.code == NODE_NOT_FOUND:
            raise ValueError(_node_not_found_note(payload)) from exc
        raise


def _node_not_found_note(payload: dict | None) -> str:
    ident = (payload or {}).get("device_id", "?")
    return (
        f"device id {ident!r} does not resolve to a Matter node: either it is "
        f"not in the device registry, or it is not a Matter device at all. "
        f"`matter nodes` lists the devices that are."
    )


# ── identifiers ─────────────────────────────────────────────────────────────


def resolve_device_id(client, ident: str) -> str:
    """Map ``<domain>.<object_id>`` through the entity registry to a device id.

    A bare string is already treated as a device-registry id and passed
    through unchanged. An entity id that resolves to nothing (an orphan, or a
    helper not attached to any device) raises ValueError naming the entity —
    HA would answer the follow-up node command with a bare ``node_not_found``
    that says nothing about which half of the resolution went wrong.
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


def _parse_node_identifier(value: str) -> dict:
    """Decode a Matter device identifier's ``deviceid_…`` payload.

    ``<compressed_fabric_id:016X>-<node_id:016X>-MatterNodeDevice`` for a
    whole-node device, ``…-<endpoint_id>`` for one endpoint of a bridged
    device. Returns ``{"node_id": int|None, "fabric_id": int|None,
    "endpoint": int|None}`` — ``None`` wherever the value does not parse,
    because a wrong claim is worse than an absent field.
    """
    out: dict[str, int | None] = {"node_id": None, "fabric_id": None, "endpoint": None}
    if not value.startswith("deviceid_"):
        return out
    parts = value[len("deviceid_") :].split("-")
    if len(parts) < 2:
        return out
    try:
        out["fabric_id"] = int(parts[0], 16)
    except ValueError:
        pass
    try:
        out["node_id"] = int(parts[1], 16)
    except ValueError:
        pass
    if len(parts) >= 3 and parts[-1] != "MatterNodeDevice":
        try:
            out["endpoint"] = int(parts[-1])
        except ValueError:
            pass
    return out


# ── availability / listing ──────────────────────────────────────────────────


def available(client) -> dict:
    """Is the ``matter`` integration loaded? A READ — 'no' is an answer.

    Checks the integration's presence in the loaded-components list (the same
    independent confirmation the error note points at), so the answer never
    depends on a websocket round-trip to a command that does not exist.
    """
    cfg = client.ws_call("get_config") or {}
    components = cfg.get("components") or []
    loaded = DOMAIN in components
    return {
        "available": loaded,
        "note": ("matter is loaded; every `matter` command works here." if loaded else ABSENT_NOTE),
    }


def list_nodes(client, *, pattern: str | None = None) -> list[dict]:
    """The Matter nodes HA knows about, as device-registry rows.

    There is no ``matter/list_nodes`` websocket command — the Matter panel
    lists its devices through the device registry, filtered to devices whose
    identifiers carry the ``matter`` domain. ``node_id``, ``fabric_id`` and
    ``endpoint`` are extracted from the identifier so the caller never parses
    HA's hex encoding; ``endpoint`` is set only on bridged devices (one
    device row per endpoint), and ``None`` means "did not parse", never
    "value is zero".
    """
    devices = client.ws_call("config/device_registry/list") or []
    p = (pattern or "").lower()
    out: list[dict] = []
    for dev in devices:
        identifiers = dev.get("identifiers") or []
        for pair in identifiers:
            if isinstance(pair, (list, tuple)) and pair and pair[0] == DOMAIN:
                parsed = _parse_node_identifier(str(pair[1])) if len(pair) > 1 else {}
                row = dict(dev)
                row["node_id"] = parsed.get("node_id")
                row["fabric_id"] = parsed.get("fabric_id")
                row["endpoint"] = parsed.get("endpoint")
                if (
                    not p
                    or p in str(row.get("name") or "").lower()
                    or p in str(row.get("name_by_user") or "").lower()
                ):
                    out.append(row)
                break
    return out


# ── commissioning (admin) ───────────────────────────────────────────────────


def _envelope(result: Any, note: str) -> dict:
    """Wrap an empty-ack success so it never reads as 'nothing happened'.

    A successful lifecycle action answers an empty dict — the same shape as
    every other ack — so the caller is told what the empty result MEANS and
    where to look next.
    """
    if result:
        return {"result": result, "note": note}
    return {"result": "ok", "note": note}


def commission(client, code: str, *, network_only: bool = True) -> dict:
    """WS ``matter/commission`` — pair a device via QR / manual-pairing code.

    ``code`` is the 11-digit manual code or the QR payload (``MT:…``).
    ``network_only=True`` (HA's default) restricts the device to the network
    it is ALREADY on — a device joining over the controller's own Wi-Fi needs
    ``--no-network-only``. Takes as long as the device takes (the client's
    websocket timeout applies on top), and success is an EMPTY result — this
    wrapper says so and points at ``matter nodes``.
    """
    code = (code or "").strip()
    if not code:
        raise ValueError("a Matter pairing code is required (QR payload or manual code)")
    result = _ws(
        client,
        "matter/commission",
        {"code": code, "network_only": bool(network_only)},
    )
    return _envelope(
        result,
        "commissioning completed; run `matter nodes` (device registry) to see the "
        "device that joined — the ack itself carries no ids",
    )


def commission_on_network(client, pin: int, *, ip_addr: str | None = None) -> dict:
    """WS ``matter/commission_on_network`` — pair a device already on the network.

    ``pin`` is the device's 8- or 11-digit setup PIN (an integer, NOT the
    manual code with its check digits spelled out). ``ip_addr`` skips
    discovery when the address is known.
    """
    if isinstance(pin, bool) or not isinstance(pin, int):
        raise ValueError(f"pin must be an integer, got {pin!r}")
    if len(str(pin)) not in PIN_LENGTHS:
        raise ValueError(
            f"pin must be the device's 8- or 11-digit setup PIN as an integer, got {pin!r}"
        )
    payload: dict[str, Any] = {"pin": pin}
    if ip_addr:
        payload["ip_addr"] = ip_addr
    result = _ws(client, "matter/commission_on_network", payload)
    return _envelope(
        result,
        "commissioning completed; run `matter nodes` (device registry) to see the "
        "device that joined — the ack itself carries no ids",
    )


def set_wifi_credentials(client, network_name: str, password: str) -> dict:
    """WS ``matter/set_wifi_credentials`` — the Wi-Fi commissioned devices join.

    Sent to the controller, not to a device: it becomes the credential every
    LATER commissioning passes on. Devices already on the network are NOT
    moved by this. Success is an empty result.
    """
    if not (network_name or "").strip():
        raise ValueError("network_name (the Wi-Fi SSID) is required")
    if not isinstance(password, str):
        raise ValueError("password must be a string (pass an empty string for an open network)")
    result = _ws(
        client,
        "matter/set_wifi_credentials",
        {"network_name": network_name, "password": password},
    )
    return _envelope(
        result, "credentials stored on the controller; they apply to commissioning from now on"
    )


def set_thread(client, dataset: str) -> dict:
    """WS ``matter/set_thread`` — the Thread dataset commissioned devices join.

    ``dataset`` is the Thread operation dataset — the TLV hex blob or TLR
    JSON string (`<n>…` / `{"…": …}`) as copied from the Thread border router
    (e.g. `otbr` in this harness: `thread dataset` / `thread network`).
    Devices already on a Thread network are NOT moved by this. Success is an
    empty result.
    """
    dataset = (dataset or "").strip()
    if not dataset:
        raise ValueError(
            "the Thread operational dataset is required (TLV hex or TLR JSON, "
            "as the border router reports it)"
        )
    result = _ws(client, "matter/set_thread", {"thread_operation_dataset": dataset})
    return _envelope(
        result, "dataset stored on the controller; it applies to commissioning from now on"
    )


# ── node operations ─────────────────────────────────────────────────────────


def node_diagnostics(client, ident: str) -> Any:
    """WS ``matter/node_diagnostics`` — the node's full data-model dump.

    Open to non-admin connections upstream (no ``@require_admin``).
    """
    return _ws(
        client,
        "matter/node_diagnostics",
        {"device_id": resolve_device_id(client, ident)},
    )


def ping_node(client, ident: str) -> Any:
    """WS ``matter/ping_node`` — a round-trip to the node's known addresses.

    Open to non-admin connections upstream. A failed ping reads as 'the node
    went quiet', not as a bad argument — HA answers ``node_not_found`` only
    when the DEVICE does not resolve at all.
    """
    return _ws(client, "matter/ping_node", {"device_id": resolve_device_id(client, ident)})


def interview_node(client, ident: str) -> dict:
    """WS ``matter/interview_node`` — re-read the device's data model.

    Open to non-admin connections upstream. Success is an empty result; the
    refreshed attributes surface as new entity states, not in this answer.
    """
    result = _ws(client, "matter/interview_node", {"device_id": resolve_device_id(client, ident)})
    return _envelope(
        result,
        "re-interview completed; the fresh attributes appear "
        "as entity states (`states <entity>`), not in this ack",
    )


def open_commissioning_window(client, ident: str) -> Any:
    """WS ``matter/open_commissioning_window`` — pair THIS device elsewhere.

    Returns the commissioning parameters (the QR-payload-equivalent) another
    controller needs — the ack is the product here, not empty like its
    siblings. Admin-only upstream.
    """
    return _ws(
        client,
        "matter/open_commissioning_window",
        {"device_id": resolve_device_id(client, ident)},
    )


def remove_fabric(client, ident: str, fabric_index: int) -> dict:
    """WS ``matter/remove_matter_fabric`` — erase one fabric from the device.

    ``fabric_index`` is the uint8 index the OTHER controller's fabric holds
    on this device (1..254). Destructive and one-way: after the erase the
    device stops responding to that controller until it is re-paired, and
    the device's entities here usually follow the fabric into oblivion.
    Success is an empty result.
    """
    if isinstance(fabric_index, bool) or not isinstance(fabric_index, int):
        raise ValueError(f"fabric_index must be an integer, got {fabric_index!r}")
    lo, hi = FABRIC_INDEX_RANGE
    if not lo <= fabric_index <= hi:
        raise ValueError(f"fabric_index must be in {lo}..{hi}, got {fabric_index}")
    result = _ws(
        client,
        "matter/remove_matter_fabric",
        {"device_id": resolve_device_id(client, ident), "fabric_index": fabric_index},
    )
    return _envelope(
        result,
        f"fabric {fabric_index} removed from the device; its entities on that "
        "controller's side stop working until it is re-paired",
    )
