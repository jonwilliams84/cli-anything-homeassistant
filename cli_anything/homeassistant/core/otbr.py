"""OpenThread Border Router — the radio Home Assistant runs the Thread mesh on.

THE GAP THIS CLOSES
    `thread_network` covers the dataset STORE: what networks Home Assistant
    knows the credentials for. This module covers the RADIO: which border
    router is running, on what channel, with which network, and how to move
    it. Those are four websocket commands (`otbr/info`, `otbr/create_network`,
    `otbr/set_network`, `otbr/set_channel`) and none of them was reachable.

WHY EVERY WRITE HERE IS DRY-RUN BY DEFAULT
    These are the most destructive commands in the harness. Measured against
    HA's `components/otbr/websocket_api.py`:

      * `otbr/create_network` FACTORY-RESETS the border router and forms a
        brand-new network with a random PAN ID. Every Thread device that had
        joined the old one is orphaned and has to be re-commissioned by hand.
        There is no undo and no confirmation on HA's side.
      * `otbr/set_network` disables the radio, writes another dataset, and
        re-enables it. Devices on the previous network stop being reachable
        through this router.
      * `otbr/set_channel` moves the radio. Devices follow via the PENDING
        dataset, which is why HA answers with a `delay` (measured constant:
        `PENDING_DATASET_DELAY_TIMER`, 300s in python-otbr-api) rather than
        taking effect at once. A device that is asleep or out of range for
        the whole delay window does not get the memo and is lost until it is
        re-commissioned.

    So each takes `apply=False` by default and reports what it would do,
    following the same pattern as `powercalc` and `entity prune`.

ERROR CODES HA USES HERE, TURNED INTO SENTENCES
    * `not_loaded`        — no OTBR config entry is loaded. For the READ that
                            is an answer (`available: false`); for a write it
                            is the reason nothing happened.
    * `unknown_router`    — the `extended_address` matched no loaded OTBR. It
                            is checked against `otbr/info` first, because HA's
                            message for it is the EMPTY STRING.
    * `channel_conflict`  — ZHA holds the radio on another channel
                            (multiprotocol). Named with both channels.
    * `multiprotocol_enabled` — channel changes are refused outright while the
                            multiprotocol add-on owns the radio.
    * `unknown_command`   — the `otbr` integration is not installed at all.
                            Same shape as `not_loaded`.
"""

from __future__ import annotations

from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

#: Codes that all mean "there is no border router to talk to".
ABSENT_CODES = ("unknown_command", "not_loaded")

#: 802.15.4 channels usable by Thread in the 2.4 GHz band.
MIN_CHANNEL = 11
MAX_CHANNEL = 26

#: What `otbr/set_channel` returns as `delay`, in seconds, when HA does not
#: say otherwise. Only used to describe the wait — the value HA returns wins.
DEFAULT_PENDING_DELAY = 300.0

_ABSENT_NOTE = (
    "No OpenThread Border Router is set up on this instance. Home Assistant "
    "manages an OTBR when the Open Thread Border Router add-on, a SkyConnect "
    "or a Yellow is configured; an Apple or Google hub can be a border router "
    "for the same mesh without ever appearing here."
)


def _absent(exc: HomeAssistantError) -> bool:
    return getattr(exc, "code", None) in ABSENT_CODES


def info(client) -> dict:
    """Every border router Home Assistant manages, one row each.

    HA returns a dict keyed by extended address; it is flattened to a list so
    the shape does not change between one router and several. A READ, so "no
    OTBR" is an answer rather than an error.
    """
    try:
        result = client.ws_call("otbr/info")
    except HomeAssistantError as exc:
        if not _absent(exc):
            raise
        return {"available": False, "routers": [], "count": 0, "note": _ABSENT_NOTE}
    rows = []
    for extended_address, data in sorted((result or {}).items()):
        row = dict(data or {})
        row.setdefault("extended_address", extended_address)
        # The active dataset TLV carries the network key. HA hands it over
        # here; this drops it and keeps only "is there one", so the credential
        # has exactly one way out of the harness (`thread dataset --reveal`).
        row["has_active_dataset"] = bool(row.pop("active_dataset_tlvs", None))
        rows.append(row)
    return {
        "available": True,
        "routers": rows,
        "count": len(rows),
        "note": (
            "`extended_address` is the argument every other otbr command takes. "
            "The active dataset TLV is withheld: it is the network key. Read it "
            "from the dataset store with `thread dataset <id> --reveal` when the "
            "network is stored there."
            if rows
            else "The OTBR integration is loaded but reports no border router."
        ),
    }


def _require_router(client, extended_address: str) -> dict:
    """Resolve an extended address to a loaded OTBR, or refuse by name."""
    if not extended_address or not str(extended_address).strip():
        raise ValueError(
            "extended_address cannot be empty — it names WHICH border router to "
            "act on. `thread otbr info` lists them."
        )
    wanted = str(extended_address).strip().lower()
    current = info(client)
    if not current["available"]:
        raise ValueError(f"Cannot reach a border router. {_ABSENT_NOTE}")
    for row in current["routers"]:
        if str(row.get("extended_address", "")).lower() == wanted:
            return row
    known = ", ".join(str(r.get("extended_address")) for r in current["routers"]) or "none"
    raise ValueError(
        f"No border router with extended address {extended_address!r}. Home "
        "Assistant answers this with the code `unknown_router` and an EMPTY "
        f"message, so it is checked here. Loaded routers: {known}."
    )


def create_network(client, extended_address: str, *, apply: bool = False) -> dict:
    """Factory-reset the border router and form a NEW network. Dry-run unless `apply`.

    The most destructive command in this harness. Everything currently joined
    to this router's Thread network is orphaned — Matter devices included —
    and each has to be re-commissioned physically.
    """
    router = _require_router(client, extended_address)
    report = {
        "applied": False,
        "extended_address": router.get("extended_address"),
        "current_channel": router.get("channel"),
        "current_extended_pan_id": router.get("extended_pan_id"),
        "note": (
            "Dry run — nothing was sent. This would FACTORY-RESET the border "
            "router, form a network with a random PAN ID on the channel Home "
            "Assistant picks, and store the new dataset. Every Thread device on "
            "the old network is orphaned and must be re-commissioned. Save the "
            "current credential first: `thread dataset <id> --reveal`. Re-run "
            "with apply/--apply once that is done."
        ),
    }
    if not apply:
        return report
    try:
        client.ws_call("otbr/create_network", {"extended_address": router["extended_address"]})
    except HomeAssistantError as exc:
        raise ValueError(_write_failure(exc, "create a new Thread network")) from exc
    after = info(client)
    now = next(
        (
            r
            for r in after["routers"]
            if str(r.get("extended_address", "")).lower()
            == str(router.get("extended_address", "")).lower()
        ),
        {},
    )
    return {
        "applied": True,
        "extended_address": router.get("extended_address"),
        "previous_extended_pan_id": router.get("extended_pan_id"),
        "extended_pan_id": now.get("extended_pan_id"),
        "channel": now.get("channel"),
        "changed": now.get("extended_pan_id") != router.get("extended_pan_id"),
        "note": (
            "A new network was formed and its dataset added to the store — "
            "`thread datasets` shows it. Devices on the previous network are "
            "orphaned; re-commission them."
        ),
    }


def set_network(client, extended_address: str, dataset_id: str, *, apply: bool = False) -> dict:
    """Move a border router onto a stored dataset. Dry-run unless `apply`."""
    from cli_anything.homeassistant.core import thread_network

    if not dataset_id or not str(dataset_id).strip():
        raise ValueError("dataset_id cannot be empty")
    dataset_id = str(dataset_id).strip()
    router = _require_router(client, extended_address)
    stored = thread_network.list_datasets(client)
    entry = next(
        (row for row in stored.get("datasets") or [] if row.get("dataset_id") == dataset_id),
        None,
    )
    if entry is None:
        raise ValueError(
            f"No Thread dataset with id {dataset_id!r} — Home Assistant would answer "
            "`unknown_dataset`. List them with `thread datasets`."
        )
    report = {
        "applied": False,
        "extended_address": router.get("extended_address"),
        "dataset_id": dataset_id,
        "network_name": entry.get("network_name"),
        "target_channel": entry.get("channel"),
        "current_channel": router.get("channel"),
        "current_extended_pan_id": router.get("extended_pan_id"),
        "already_on_network": (
            str(entry.get("extended_pan_id") or "").lower()
            == str(router.get("extended_pan_id") or "").lower()
        ),
        "note": (
            "Dry run — nothing was sent. Applying disables the radio, writes this "
            "dataset and re-enables it: devices on the router's previous network "
            "lose it. If ZHA holds the radio on another channel Home Assistant "
            "refuses with `channel_conflict` rather than doing half of this."
        ),
    }
    if not apply:
        return report
    try:
        client.ws_call(
            "otbr/set_network",
            {"extended_address": router["extended_address"], "dataset_id": dataset_id},
        )
    except HomeAssistantError as exc:
        raise ValueError(_write_failure(exc, f"move the border router onto {dataset_id}")) from exc
    after = info(client)
    now = next(
        (
            r
            for r in after["routers"]
            if str(r.get("extended_address", "")).lower()
            == str(router.get("extended_address", "")).lower()
        ),
        {},
    )
    return {
        "applied": True,
        "extended_address": router.get("extended_address"),
        "dataset_id": dataset_id,
        "extended_pan_id": now.get("extended_pan_id"),
        "channel": now.get("channel"),
        "took": str(now.get("extended_pan_id") or "").lower()
        == str(entry.get("extended_pan_id") or "").lower(),
        "note": "Read back from `otbr/info`; the command itself returns null.",
    }


def set_channel(client, extended_address: str, channel: int, *, apply: bool = False) -> dict:
    """Move the border router to another 802.15.4 channel. Dry-run unless `apply`.

    Not immediate: HA writes a PENDING dataset with a delay timer so joined
    devices have time to follow, and returns that delay in seconds.
    """
    try:
        channel = int(channel)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"channel must be an integer, got {channel!r}") from exc
    if not MIN_CHANNEL <= channel <= MAX_CHANNEL:
        raise ValueError(
            f"channel must be between {MIN_CHANNEL} and {MAX_CHANNEL} "
            f"(2.4 GHz 802.15.4), got {channel}"
        )
    router = _require_router(client, extended_address)
    report = {
        "applied": False,
        "extended_address": router.get("extended_address"),
        "current_channel": router.get("channel"),
        "channel": channel,
        "no_op": router.get("channel") == channel,
        "note": (
            "Dry run — nothing was sent. Applying schedules the move through a "
            f"PENDING dataset (~{DEFAULT_PENDING_DELAY:g}s) so joined devices can "
            "follow; anything asleep or out of range for the whole window is left "
            "on the old channel and has to be re-commissioned. Refused outright "
            "with `multiprotocol_enabled` while the multiprotocol add-on owns the "
            "radio."
        ),
    }
    if not apply:
        return report
    try:
        result = client.ws_call(
            "otbr/set_channel",
            {"extended_address": router["extended_address"], "channel": channel},
        )
    except HomeAssistantError as exc:
        raise ValueError(_write_failure(exc, f"move the radio to channel {channel}")) from exc
    delay = (result or {}).get("delay", DEFAULT_PENDING_DELAY)
    return {
        "applied": True,
        "extended_address": router.get("extended_address"),
        "previous_channel": router.get("channel"),
        "channel": channel,
        "delay": delay,
        "note": (
            f"Scheduled. The radio moves in about {delay}s (Thread's pending-dataset "
            "delay timer) — `thread otbr info` still reports the OLD channel until "
            "then, which is correct, not a failure."
        ),
    }


def _write_failure(exc: HomeAssistantError, action: str) -> str:
    """Turn an OTBR error code into a sentence naming the remedy."""
    code = getattr(exc, "code", None)
    if code in ABSENT_CODES:
        return f"Cannot {action}: {_ABSENT_NOTE}"
    if code == "multiprotocol_enabled":
        return (
            f"Cannot {action}: the multiprotocol add-on owns this radio, and Home "
            "Assistant does not allow a channel change while Zigbee and Thread "
            "share it. Change the channel in ZHA instead, or split the radios."
        )
    if code == "channel_conflict":
        return (
            f"Cannot {action}: ZHA is holding the shared radio on a different "
            f"channel ({exc}). Move ZHA first, or pick a dataset on ZHA's channel."
        )
    if code == "unknown_dataset":
        return f"Cannot {action}: Home Assistant does not have that dataset stored."
    if code == "unknown_router":
        return (
            f"Cannot {action}: Home Assistant does not have a border router with "
            "that extended address loaded. `thread otbr info` lists them."
        )
    return (
        f"Cannot {action}: Home Assistant refused with `{code or 'no code'}` — {exc}. "
        "The border router itself logs the reason; check `system error-log`."
    )
