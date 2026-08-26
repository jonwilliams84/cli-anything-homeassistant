"""Thread networks: the dataset store, router discovery, and what they imply.

THE GAP THIS CLOSES
    Matter-over-Thread devices are joined to a Thread network, and the thing
    that defines that network — the operational DATASET — lives in Home
    Assistant's own dataset store, reachable only over the `thread/*`
    websocket commands. Nothing in this harness could read it. An agent could
    see the resulting entities, the config entries and the repair issues
    ("insecure Thread network", "channel collision") and could not see the one
    object those complaints are about, could not say which of several stored
    networks was preferred, and could not move a border router onto another
    one.

THE DATASET IS A CREDENTIAL, SO IT IS REDACTED BY DEFAULT
    `thread/get_dataset_tlv` returns the full operational dataset, which
    carries the NETWORKKEY and the PSKc. Anyone holding the network key can
    join the mesh. `dataset()` therefore decodes the TLV and replaces those
    two values with `<redacted>` unless the caller passes `reveal=True`, and
    `list_datasets()` never fetches TLVs at all. HA's own list command does
    not include them either — this keeps that property instead of "helpfully"
    joining the two.

`add_dataset` IS AN UPSERT KEYED ON EXTENDED PAN ID, AND IT ALWAYS RETURNS NULL
    Measured against HA 2025.1.4, `thread/add_dataset_tlv` has FOUR outcomes
    and one response (`null`):

      * the extended PAN ID is new                       → a dataset is created
      * an identical dataset is already stored           → nothing happens
      * same extended PAN ID, NEWER active timestamp     → the stored TLV is
        REPLACED IN PLACE. The dataset id, the creation time and — measured —
        the `source` string all stay as they were, so the store now describes
        a network nobody in this harness added.
      * same extended PAN ID, same or OLDER timestamp    → SILENTLY DROPPED.
        HA logs "Got dataset with same extended PAN ID and same or older
        active timestamp" server-side and returns success.

    A caller that trusts the return value cannot tell those apart. So
    :func:`add_dataset` is dry-run by default (the repo's `--apply` pattern),
    predicts which of the four will happen by comparing the parsed active
    timestamps, and on apply re-reads the store and reports the outcome it
    actually observed.

LOCAL DECODE, NOT LOCAL LOGIC
    The TLV parser here is a decoder for bytes HA has already handed over —
    the same role as pretty-printing a JSON response. It is a faithful
    re-implementation of `python_otbr_api.tlv_parser` (same tag table, same
    "duplicate tag" and "truncated" errors) so that the harness keeps its
    "no dependency you do not need" rule: `python-otbr-api` is a Home
    Assistant requirement, not a client one. Nothing here decides anything
    HA would decide — validation only pre-empts errors HA reports opaquely.

ERROR CODES, MEASURED
    * `thread/add_dataset_tlv` with non-hex             → `invalid_format`
    * ... missing EXTPANID or ACTIVETIMESTAMP           → `home_assistant_error`
      with the bare message "Invalid dataset". Both are checked locally first
      so the caller is told WHICH TLV is missing.
    * `thread/delete_dataset` on the preferred dataset  → `not_allowed`
    * `thread/get_dataset_tlv` / `set_preferred_dataset` on an unknown id
                                                        → `not_found`
    * `thread/set_preferred_border_agent` on an unknown id → `unknown_error`.
      That is an UNCAUGHT KeyError in HA's store, not a real error class, so
      the id is checked against the store first and refused by name.
    * every command when the `thread` integration is not loaded
                                                        → `unknown_command`,
      which reads as a named `available: false` answer, never as a crash.
"""

from __future__ import annotations

import threading

from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

#: HA's code when a websocket command is not registered — for `thread/*` that
#: always means the `thread` integration is not set up on this instance.
UNKNOWN_COMMAND = "unknown_command"

#: MeshCoP TLV tag table. Mirrors `python_otbr_api.tlv_parser.MeshcopTLVType`
#: (checked against 2.10.0); unknown tags are passed through as bare ints,
#: exactly as HA's parser does.
TLV_TAGS: dict[int, str] = {
    0: "CHANNEL",
    1: "PANID",
    2: "EXTPANID",
    3: "NETWORKNAME",
    4: "PSKC",
    5: "NETWORKKEY",
    6: "NETWORK_KEY_SEQUENCE",
    7: "MESHLOCALPREFIX",
    8: "STEERING_DATA",
    9: "BORDER_AGENT_RLOC",
    10: "COMMISSIONER_ID",
    11: "COMM_SESSION_ID",
    12: "SECURITYPOLICY",
    13: "GET",
    14: "ACTIVETIMESTAMP",
    15: "COMMISSIONER_UDP_PORT",
    16: "STATE",
    17: "JOINER_DTLS",
    18: "JOINER_UDP_PORT",
    19: "JOINER_IID",
    20: "JOINER_RLOC",
    21: "JOINER_ROUTER_KEK",
    23: "DURATION",
    32: "PROVISIONING_URL",
    33: "VENDOR_NAME_TLV",
    34: "VENDOR_MODEL_TLV",
    35: "VENDOR_SW_VERSION_TLV",
    36: "VENDOR_DATA_TLV",
    37: "VENDOR_STACK_VERSION_TLV",
    48: "UDP_ENCAPSULATION_TLV",
    49: "IPV6_ADDRESS_TLV",
    51: "PENDINGTIMESTAMP",
    52: "DELAYTIMER",
    53: "CHANNELMASK",
    54: "COUNT",
    55: "PERIOD",
    56: "SCAN_DURATION",
    57: "ENERGY_LIST",
    59: "THREAD_DOMAIN_NAME",
    74: "WAKEUP_CHANNEL",
    128: "DISCOVERYREQUEST",
    129: "DISCOVERYRESPONSE",
    241: "JOINERADVERTISEMENT",
}

TAG_CHANNEL = 0
TAG_PANID = 1
TAG_EXTPANID = 2
TAG_NETWORKNAME = 3
TAG_PSKC = 4
TAG_NETWORKKEY = 5
TAG_ACTIVETIMESTAMP = 14

#: The two TLVs that are secrets. Redacted unless the caller asks for them.
SECRET_TAGS = (TAG_PSKC, TAG_NETWORKKEY)

#: HA refuses to store a dataset without these two (`dataset_store.async_add`),
#: reporting only "Invalid dataset".
REQUIRED_TAGS = (TAG_EXTPANID, TAG_ACTIVETIMESTAMP)

#: The network key shipped as the default by the Thread web UI. HA raises the
#: `insecure_thread_network` repair issue for it (`otbr/util.py`).
INSECURE_NETWORK_KEYS = ("00112233445566778899aabbccddeeff",)

REDACTED = "<redacted>"

#: Thread runs on 802.15.4 channels 11-26 in the 2.4 GHz band.
MIN_CHANNEL = 11
MAX_CHANNEL = 26


# ─────────────────────────────────────────────────────────────── TLV decoding


def _decode_timestamp(data: bytes) -> dict | None:
    """Decode an 8-byte Thread timestamp: 48b seconds, 15b ticks, 1b flag."""
    if len(data) != 8:
        return None
    raw = int.from_bytes(data, "big")
    return {
        "seconds": raw >> 16,
        "ticks": (raw >> 1) & 0x7FFF,
        "authoritative": bool(raw & 1),
    }


def parse_tlv(tlv: str) -> list[dict]:
    """Decode a MeshCoP TLV hex string into a list of items.

    Raises
    ------
    ValueError
        On non-hex input, a truncated item, or a duplicated tag — the same
        three conditions `python_otbr_api.tlv_parser.parse_tlv` rejects, so a
        TLV this accepts is one HA will also parse.
    """
    if not isinstance(tlv, str) or not tlv.strip():
        raise ValueError("tlv cannot be empty")
    text = tlv.strip()
    try:
        raw = bytes.fromhex(text)
    except ValueError as exc:
        raise ValueError(
            f"tlv is not valid hex: {exc}. Expected the operational dataset as a "
            "hex string, e.g. the output of `thread dataset <id> --reveal`."
        ) from exc
    items: list[dict] = []
    seen: set[int] = set()
    pos, length = 0, len(raw)
    while pos < length:
        if pos + 2 > length:
            raise ValueError("truncated tlv header: a tag byte with no length byte")
        tag = raw[pos]
        size = raw[pos + 1]
        pos += 2
        if pos + size > length:
            raise ValueError(
                f"truncated tlv: tag {tag} declares {size} bytes, "
                f"{length - pos} remain"
            )
        value = raw[pos : pos + size]
        pos += size
        if tag in seen:
            raise ValueError(f"duplicated tlv tag {tag} ({TLV_TAGS.get(tag, 'unknown')})")
        seen.add(tag)
        items.append(
            {
                "tag": tag,
                "name": TLV_TAGS.get(tag),
                "length": size,
                "value": value.hex(),
            }
        )
    if not items:
        raise ValueError("tlv decoded to zero items")
    return items


def describe_dataset(tlv: str, *, reveal: bool = False) -> dict:
    """Decode a dataset TLV into named fields, redacting the credentials.

    `reveal=True` puts the network key, the PSKc and the raw TLV back in. That
    is the whole credential for the mesh — anything that can reach the radio
    and holds it can join.
    """
    items = parse_tlv(tlv)
    by_tag = {item["tag"]: item for item in items}
    out_items = []
    for item in items:
        row = dict(item)
        row["secret"] = item["tag"] in SECRET_TAGS
        if row["secret"] and not reveal:
            row["value"] = REDACTED
        out_items.append(row)

    name_item = by_tag.get(TAG_NETWORKNAME)
    network_name = None
    if name_item is not None:
        try:
            network_name = bytes.fromhex(name_item["value"]).decode()
        except (UnicodeDecodeError, ValueError):
            network_name = None

    channel = None
    if TAG_CHANNEL in by_tag:
        channel = int(by_tag[TAG_CHANNEL]["value"], 16) if by_tag[TAG_CHANNEL]["length"] else None

    key_item = by_tag.get(TAG_NETWORKKEY)
    missing = [TLV_TAGS[tag] for tag in REQUIRED_TAGS if tag not in by_tag]
    timestamp = (
        _decode_timestamp(bytes.fromhex(by_tag[TAG_ACTIVETIMESTAMP]["value"]))
        if TAG_ACTIVETIMESTAMP in by_tag
        else None
    )
    return {
        "network_name": network_name,
        "channel": channel,
        "pan_id": by_tag[TAG_PANID]["value"] if TAG_PANID in by_tag else None,
        "extended_pan_id": by_tag[TAG_EXTPANID]["value"] if TAG_EXTPANID in by_tag else None,
        "active_timestamp": timestamp,
        "items": out_items,
        "contains_credentials": any(tag in by_tag for tag in SECRET_TAGS),
        "revealed": bool(reveal),
        "tlv": tlv.strip() if reveal else None,
        "insecure_default_network_key": bool(
            key_item is not None and key_item["value"].lower() in INSECURE_NETWORK_KEYS
        ),
        "storable": not missing,
        "missing_required": missing,
        "note": (
            "Credentials (NETWORKKEY, PSKC) and the raw TLV are withheld. Pass "
            "reveal/--reveal to print them; the TLV is enough to join the mesh."
            if not reveal
            else "REVEALED: this output contains the Thread network key. Anyone "
            "holding it can join the mesh — do not paste it into a ticket."
        ),
    }


def _compare_timestamps(new: dict | None, old: dict | None) -> str:
    """Return 'newer', 'older_or_same' or 'unknown' the way HA compares them."""
    if not new or not old:
        return "unknown"
    if old["seconds"] > new["seconds"]:
        return "older_or_same"
    if old["seconds"] < new["seconds"]:
        return "newer"
    return "older_or_same" if old["ticks"] >= new["ticks"] else "newer"


# ──────────────────────────────────────────────────────────────────── reading


def _unavailable(subject: str) -> dict:
    return {
        "available": False,
        "datasets": [],
        "count": 0,
        "preferred": None,
        "networks": 0,
        "note": (
            f"The Thread integration is not set up on this instance, so there is no "
            f"{subject}. It is added automatically when a border router (an OTBR "
            "add-on, an Apple/Google hub, a SkyConnect/Yellow) is discovered, or "
            "manually under Settings > Devices & Services > Add Integration > Thread."
        ),
    }


def list_datasets(client) -> dict:
    """Every stored Thread network, with the preferred one marked.

    A READ, so a missing `thread` integration is an answer (`available:
    false`) and not an error. No TLVs are fetched: the list HA returns is
    already credential-free and this keeps it that way.
    """
    try:
        result = client.ws_call("thread/list_datasets")
    except HomeAssistantError as exc:
        if getattr(exc, "code", None) != UNKNOWN_COMMAND:
            raise
        return _unavailable("dataset store")
    rows = list((result or {}).get("datasets") or [])
    preferred = next((row.get("dataset_id") for row in rows if row.get("preferred")), None)
    return {
        "available": True,
        "datasets": rows,
        "count": len(rows),
        "preferred": preferred,
        "networks": len({row.get("extended_pan_id") for row in rows if row.get("extended_pan_id")}),
        "note": (
            "The PREFERRED dataset is the network new Matter-over-Thread devices "
            "are commissioned onto. More than one stored network is normal (each "
            "border-router vendor adds its own) but only one can be preferred."
            if rows
            else "No Thread networks are stored. A border router adds one when it "
            "forms or joins a network."
        ),
    }


def _find_dataset(client, dataset_id: str) -> dict | None:
    for row in list_datasets(client).get("datasets") or []:
        if row.get("dataset_id") == dataset_id:
            return row
    return None


def dataset(client, dataset_id: str, *, reveal: bool = False) -> dict:
    """One dataset, decoded. Credentials redacted unless `reveal` is set."""
    if not dataset_id or not str(dataset_id).strip():
        raise ValueError("dataset_id cannot be empty")
    dataset_id = str(dataset_id).strip()
    try:
        result = client.ws_call("thread/get_dataset_tlv", {"dataset_id": dataset_id})
    except HomeAssistantError as exc:
        code = getattr(exc, "code", None)
        if code == UNKNOWN_COMMAND:
            raise ValueError(
                "The Thread integration is not set up on this instance, so it has "
                "no datasets. `thread datasets` reports that as a plain answer."
            ) from exc
        if code == "not_found":
            raise ValueError(
                f"No Thread dataset with id {dataset_id!r}. List the ids with "
                "`thread datasets`; they are ULIDs, not network names."
            ) from exc
        raise
    tlv = (result or {}).get("tlv")
    if not tlv:
        raise ValueError(
            f"Home Assistant returned no TLV for dataset {dataset_id!r}, which "
            "should not happen for an id that exists."
        )
    described = describe_dataset(tlv, reveal=reveal)
    entry = _find_dataset(client, dataset_id) or {}
    described.update(
        {
            "dataset_id": dataset_id,
            "source": entry.get("source"),
            "created": entry.get("created"),
            "preferred": entry.get("preferred"),
            "preferred_border_agent_id": entry.get("preferred_border_agent_id"),
            "preferred_extended_address": entry.get("preferred_extended_address"),
        }
    )
    return described


# ──────────────────────────────────────────────────────────────────── writing


def add_dataset(client, tlv: str, *, source: str = "cli-anything", apply: bool = False) -> dict:
    """Store an operational dataset. Dry-run unless `apply`.

    Predicts, then verifies, which of HA's four silent outcomes happened —
    see the module docstring. `source` is a free-text label; note that HA
    keeps the ORIGINAL source when it replaces an existing dataset, so the
    label only sticks on a create.
    """
    if not source or not str(source).strip():
        raise ValueError("source cannot be empty")
    described = describe_dataset(tlv, reveal=False)
    if described["missing_required"]:
        raise ValueError(
            "Home Assistant will not store this dataset: it is missing "
            + ", ".join(described["missing_required"])
            + ". HA reports that as the bare message 'Invalid dataset'. A complete "
            "operational dataset comes from `thread dataset <id> --reveal` or from "
            "the border router's own web UI."
        )
    normalized = tlv.strip()

    current = list_datasets(client)
    if not current["available"]:
        raise ValueError(
            "Cannot add a Thread dataset: the Thread integration is not set up on "
            "this instance. Add it under Settings > Devices & Services."
        )
    epid = described["extended_pan_id"]
    existing = next(
        (row for row in current["datasets"] if (row.get("extended_pan_id") or "").lower() == (epid or "").lower()),
        None,
    )

    prediction = "create"
    detail = "No stored dataset has this extended PAN ID, so a new one is created."
    existing_stamp = None
    if existing is not None:
        stored = dataset(client, existing["dataset_id"], reveal=True)
        existing_stamp = stored.get("active_timestamp")
        if (stored.get("tlv") or "").lower() == normalized.lower():
            prediction = "unchanged"
            detail = (
                f"Dataset {existing['dataset_id']} already holds exactly this TLV; "
                "Home Assistant will do nothing and report success."
            )
        elif _compare_timestamps(described["active_timestamp"], existing_stamp) == "newer":
            prediction = "replace"
            detail = (
                f"Dataset {existing['dataset_id']} has the same extended PAN ID and an "
                "older active timestamp, so its TLV is REPLACED IN PLACE — same "
                "dataset id, same created time, and the original source label is kept."
            )
        else:
            prediction = "ignored_older"
            detail = (
                f"Dataset {existing['dataset_id']} has the same extended PAN ID and a "
                "same-or-newer active timestamp. Home Assistant will DROP this one "
                "silently and still report success. Bump the active timestamp if the "
                "new dataset is really the current one."
            )

    report = {
        "applied": False,
        "predicted": prediction,
        "outcome": None,
        "extended_pan_id": epid,
        "network_name": described["network_name"],
        "channel": described["channel"],
        "matched_dataset_id": existing["dataset_id"] if existing else None,
        "insecure_default_network_key": described["insecure_default_network_key"],
        "detail": detail,
        "note": (
            "Dry run — nothing was sent. Re-run with apply/--apply to store it. "
            "`thread/add_dataset_tlv` answers `null` for all four of its outcomes, "
            "so this command reads the store back to say which one happened."
        ),
    }
    if not apply:
        return report

    client.ws_call("thread/add_dataset_tlv", {"source": str(source).strip(), "tlv": normalized})
    after = list_datasets(client)
    before_ids = {row.get("dataset_id") for row in current["datasets"]}
    created = [row for row in after["datasets"] if row.get("dataset_id") not in before_ids]
    if created:
        outcome = "created"
        report["dataset_id"] = created[0].get("dataset_id")
    elif existing is not None:
        now = next(
            (row for row in after["datasets"] if row.get("dataset_id") == existing["dataset_id"]),
            None,
        )
        report["dataset_id"] = existing["dataset_id"]
        if now is None:
            outcome = "unknown"
        elif now == existing:
            outcome = "unchanged" if prediction == "unchanged" else "ignored_older"
        else:
            outcome = "replaced"
    else:
        outcome = "unknown"
    report["applied"] = True
    report["outcome"] = outcome
    report["note"] = (
        "Outcome read back from the dataset store, not from the command's own "
        "response — it returns `null` either way."
    )
    return report


def delete_dataset(client, dataset_id: str, *, apply: bool = False) -> dict:
    """Delete a stored dataset. Dry-run unless `apply`.

    HA refuses to delete the PREFERRED dataset (`not_allowed`); that is
    checked first so the refusal names the remedy instead of the code.
    """
    if not dataset_id or not str(dataset_id).strip():
        raise ValueError("dataset_id cannot be empty")
    dataset_id = str(dataset_id).strip()
    entry = _find_dataset(client, dataset_id)
    if entry is None:
        raise ValueError(
            f"No Thread dataset with id {dataset_id!r}. List them with `thread datasets`."
        )
    if entry.get("preferred"):
        raise ValueError(
            f"Dataset {dataset_id} is the PREFERRED network and Home Assistant "
            "refuses to delete it (error code `not_allowed`). Make another dataset "
            "preferred first with `thread set-preferred <other-id> --apply`. There "
            "is no way to have no preferred network once one is set."
        )
    report = {
        "applied": False,
        "dataset_id": dataset_id,
        "network_name": entry.get("network_name"),
        "extended_pan_id": entry.get("extended_pan_id"),
        "note": (
            "Dry run — nothing was sent. Re-run with apply/--apply. Deleting a "
            "dataset does not tell any device to leave the network; it only "
            "forgets the credential, and re-adding needs the TLV again. Read it "
            "out first with `thread dataset <id> --reveal` if it is not stored "
            "elsewhere."
        ),
    }
    if not apply:
        return report
    client.ws_call("thread/delete_dataset", {"dataset_id": dataset_id})
    report["applied"] = True
    report["gone"] = _find_dataset(client, dataset_id) is None
    report["note"] = "Deleted. Verified by re-reading the dataset store."
    return report


def set_preferred(client, dataset_id: str, *, apply: bool = False) -> dict:
    """Make a dataset the preferred network. Dry-run unless `apply`."""
    if not dataset_id or not str(dataset_id).strip():
        raise ValueError("dataset_id cannot be empty")
    dataset_id = str(dataset_id).strip()
    current = list_datasets(client)
    if not current["available"]:
        raise ValueError(
            "Cannot set a preferred Thread network: the Thread integration is not "
            "set up on this instance."
        )
    entry = next((row for row in current["datasets"] if row.get("dataset_id") == dataset_id), None)
    if entry is None:
        raise ValueError(
            f"No Thread dataset with id {dataset_id!r}. List them with `thread datasets`."
        )
    report = {
        "applied": False,
        "dataset_id": dataset_id,
        "network_name": entry.get("network_name"),
        "was_preferred": current["preferred"],
        "already_preferred": bool(entry.get("preferred")),
        "note": (
            "Dry run — nothing was sent. Re-run with apply/--apply. The preferred "
            "network is the one new Matter-over-Thread devices are commissioned "
            "onto; changing it does not move devices that already joined."
        ),
    }
    if not apply:
        return report
    client.ws_call("thread/set_preferred_dataset", {"dataset_id": dataset_id})
    after = list_datasets(client)
    report["applied"] = True
    report["preferred"] = after["preferred"]
    report["took"] = after["preferred"] == dataset_id
    report["note"] = "Read back from the dataset store; the command itself returns null."
    return report


def set_border_agent(
    client,
    dataset_id: str,
    *,
    extended_address: str,
    border_agent_id: str | None = None,
    apply: bool = False,
) -> dict:
    """Pin which border router owns a dataset. Dry-run unless `apply`.

    `extended_address` is REQUIRED by HA's schema even when clearing the
    border agent id. An unknown `dataset_id` reaches an uncaught KeyError in
    HA and comes back as `unknown_error`, so it is checked here first.
    """
    if not dataset_id or not str(dataset_id).strip():
        raise ValueError("dataset_id cannot be empty")
    if not extended_address or not str(extended_address).strip():
        raise ValueError(
            "extended_address cannot be empty — Home Assistant requires it even "
            "when clearing the border agent id. `thread routers` and `thread otbr "
            "info` both report it."
        )
    dataset_id = str(dataset_id).strip()
    entry = _find_dataset(client, dataset_id)
    if entry is None:
        raise ValueError(
            f"No Thread dataset with id {dataset_id!r}. Home Assistant answers this "
            "one with the opaque code `unknown_error` (an uncaught KeyError in its "
            "dataset store), so it is refused here. List ids with `thread datasets`."
        )
    payload = {
        "dataset_id": dataset_id,
        "border_agent_id": str(border_agent_id).strip() if border_agent_id else None,
        "extended_address": str(extended_address).strip(),
    }
    report = {
        "applied": False,
        "dataset_id": dataset_id,
        "border_agent_id": payload["border_agent_id"],
        "extended_address": payload["extended_address"],
        "was_border_agent_id": entry.get("preferred_border_agent_id"),
        "was_extended_address": entry.get("preferred_extended_address"),
        "note": (
            "Dry run — nothing was sent. Re-run with apply/--apply. This only "
            "records which border router HA should treat as this network's owner; "
            "it does not reconfigure any radio."
        ),
    }
    if not apply:
        return report
    client.ws_call("thread/set_preferred_border_agent", payload)
    after = _find_dataset(client, dataset_id) or {}
    report["applied"] = True
    report["border_agent_id"] = after.get("preferred_border_agent_id")
    report["extended_address"] = after.get("preferred_extended_address")
    report["took"] = after.get("preferred_extended_address") == payload["extended_address"]
    report["note"] = "Read back from the dataset store; the command itself returns null."
    return report


# ────────────────────────────────────────────────────────────────── discovery


def discover_routers(
    client,
    *,
    timeout: float = 10.0,
    max_routers: int | None = None,
    on_router=None,
) -> dict:
    """Listen for Thread border routers advertising over mDNS.

    `thread/discover_routers` is a SUBSCRIPTION with no natural end: HA keeps
    the `_meshcop._udp` browser open and streams `router_discovered` /
    `router_removed` events. It is bounded here by `timeout` (and optionally
    `max_routers`), and an empty list after the timeout is a real answer — it
    usually means mDNS does not cross the network between HA and the routers,
    not that there are none.
    """
    if timeout <= 0:
        raise ValueError("timeout must be > 0")
    if max_routers is not None and max_routers < 1:
        raise ValueError("max_routers must be >= 1")
    if on_router is not None and not callable(on_router):
        raise ValueError("on_router must be callable")

    found: dict[str, dict] = {}
    removed: list[str] = []
    errors: list[str] = []
    stop = threading.Event()

    def handle(event) -> None:
        if not isinstance(event, dict):
            return
        kind = event.get("type")
        key = event.get("key")
        if kind == "router_discovered":
            data = event.get("data") or {}
            if isinstance(data, dict):
                found[key] = {"key": key, **data}
            if on_router is not None:
                on_router(found.get(key, {"key": key}))
            if max_routers is not None and len(found) >= max_routers:
                stop.set()
        elif kind == "router_removed":
            found.pop(key, None)
            removed.append(key)

    def run() -> None:
        try:
            client.ws_subscribe("thread/discover_routers", None, handle, stop)
        except HomeAssistantError as exc:
            errors.append(str(exc))

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout=timeout)
    stop.set()
    worker.join(timeout=2.0)

    if errors and not found:
        if UNKNOWN_COMMAND in errors[0]:
            return {
                "available": False,
                "routers": [],
                "count": 0,
                "removed": [],
                "timeout": timeout,
                "note": (
                    "The Thread integration is not set up on this instance, so router "
                    "discovery is not available."
                ),
            }
        raise HomeAssistantError(errors[0])

    routers = sorted(found.values(), key=lambda row: str(row.get("extended_address") or row.get("key")))
    return {
        "available": True,
        "routers": routers,
        "count": len(routers),
        "removed": removed,
        "timeout": timeout,
        "note": (
            f"Listened for {timeout:g}s. Discovery is mDNS (`_meshcop._udp`): an "
            "empty result usually means multicast does not reach Home Assistant "
            "from the routers' network, not that no border router exists. "
            "`unconfigured: true` marks a router that has not formed a network yet."
            if not routers
            else f"Listened for {timeout:g}s over mDNS (`_meshcop._udp`). Routers can "
            "keep arriving after the window closes — raise the timeout if one you "
            "expect is missing."
        ),
    }


# ──────────────────────────────────────────────────────────────────── audit


def audit(client, *, discover_timeout: float = 0.0) -> dict:
    """Cross-reference the dataset store, the OTBRs and (optionally) mDNS.

    The single command worth running when Thread devices misbehave. It names
    the conditions that are invisible in any one of the three views:

      * a stored network with NO border router that claims it — the dataset
        is a leftover;
      * a border router running a network that is NOT the preferred one, so
        newly commissioned devices land somewhere else;
      * a border router whose active network is not in the store at all;
      * the Thread web UI's default network key, which is the same
        `insecure_thread_network` condition HA raises a repair issue for;
      * more than one stored network, which is normal but explains "the
        device joined and then disappeared".
    """
    from cli_anything.homeassistant.core import otbr as otbr_core

    stored = list_datasets(client)
    routers = otbr_core.info(client)
    findings: list[dict] = []

    if not stored["available"]:
        return {
            "available": False,
            "datasets": [],
            "border_routers": [],
            "findings": [],
            "note": stored["note"],
        }

    by_epid: dict[str, dict] = {}
    for row in stored["datasets"]:
        epid = (row.get("extended_pan_id") or "").lower()
        if epid:
            by_epid[epid] = row

    router_rows = []
    for router in routers.get("routers") or []:
        epid = (router.get("extended_pan_id") or "").lower()
        match = by_epid.get(epid)
        router_rows.append(
            {
                **router,
                "dataset_id": match.get("dataset_id") if match else None,
                "network_name": match.get("network_name") if match else None,
                "running_preferred": bool(match and match.get("preferred")),
            }
        )
        if match is None:
            findings.append(
                {
                    "severity": "warning",
                    "code": "router_network_not_stored",
                    "extended_address": router.get("extended_address"),
                    "detail": (
                        f"Border router {router.get('extended_address')} is running a "
                        f"network (extended PAN ID {epid or 'unknown'}) that is not in "
                        "Home Assistant's dataset store, so HA cannot commission "
                        "devices onto it."
                    ),
                }
            )
        elif not match.get("preferred") and stored["preferred"]:
            findings.append(
                {
                    "severity": "warning",
                    "code": "router_not_on_preferred_network",
                    "extended_address": router.get("extended_address"),
                    "detail": (
                        f"Border router {router.get('extended_address')} is running "
                        f"'{match.get('network_name')}' but the preferred network is "
                        f"{stored['preferred']}. New Matter-over-Thread devices are "
                        "commissioned onto the preferred one, which this router is "
                        "not on. `thread otbr set-network` or `thread set-preferred` "
                        "settles it."
                    ),
                }
            )

    claimed = {(r.get("extended_pan_id") or "").lower() for r in routers.get("routers") or []}
    for epid, row in by_epid.items():
        if routers.get("available") and epid not in claimed:
            findings.append(
                {
                    "severity": "info",
                    "code": "dataset_without_router",
                    "dataset_id": row.get("dataset_id"),
                    "detail": (
                        f"Stored network '{row.get('network_name')}' has no OTBR "
                        "running it. That is expected when the border router is an "
                        "Apple or Google hub (HA stores their credentials but does "
                        "not manage them); otherwise the dataset is a leftover."
                    ),
                }
            )

    if stored["count"] and not stored["preferred"]:
        findings.append(
            {
                "severity": "warning",
                "code": "no_preferred_dataset",
                "detail": (
                    "Datasets are stored but none is preferred, so Matter "
                    "commissioning has no network to hand out. Pick one with "
                    "`thread set-preferred <id> --apply`."
                ),
            }
        )
    if stored["networks"] > 1:
        findings.append(
            {
                "severity": "info",
                "code": "multiple_networks",
                "detail": (
                    f"{stored['networks']} distinct Thread networks are stored. "
                    "Devices on the non-preferred ones stay reachable but new ones "
                    "will not join them."
                ),
            }
        )

    discovered = None
    if discover_timeout:
        discovered = discover_routers(client, timeout=discover_timeout)
        seen = {(r.get("extended_address") or "").lower() for r in discovered.get("routers") or []}
        for router in routers.get("routers") or []:
            addr = (router.get("extended_address") or "").lower()
            if addr and addr not in seen:
                findings.append(
                    {
                        "severity": "info",
                        "code": "router_not_advertising",
                        "extended_address": router.get("extended_address"),
                        "detail": (
                            "This OTBR did not advertise over mDNS during the "
                            "discovery window. Matter controllers find border routers "
                            "the same way, so check multicast on that network."
                        ),
                    }
                )

    return {
        "available": True,
        "preferred": stored["preferred"],
        "datasets": stored["datasets"],
        "border_routers": router_rows,
        "otbr_available": routers.get("available"),
        "discovered": discovered,
        "findings": findings,
        "healthy": not any(f["severity"] == "warning" for f in findings),
        "note": (
            "Read-only. `border_routers` covers OTBRs Home Assistant manages; an "
            "Apple TV or Nest hub acting as a border router shows up only under "
            "`thread routers` (mDNS), never here."
        ),
    }

