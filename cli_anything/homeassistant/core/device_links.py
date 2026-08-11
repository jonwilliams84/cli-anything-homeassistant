"""Device topology the flat registry cannot show: linked devices and composite
splits.

WHAT THE DEVICE REGISTRY LEAVES OUT
    `device list` returns a flat list with `via_device_id` — the parent/child
    link, which the harness already reports. Two other relationships exist in
    2026.8.1 and neither is on that record:

    LINKED DEVICES — the same physical thing reached through more than one
        integration. A socket that appears once via Zigbee and once via Matter
        is two device entries with no shared field to join them on; HA knows
        they are linked and `config/device_registry/list_linked_devices` is the
        only way to ask.

    COMPOSITE SPLITS — one device that HA has split into several registry
        entries, with a `primary_id` and the `split_ids` it was split into.
        Measured on a live instance: a real map with primary/split ids, so this
        estate has them.

WHY IT MATTERS TO ANYTHING AUTOMATED
    A device-scoped target (`target extract --device-id …`), an area assignment
    or a `device_automation` lookup applies to ONE registry entry. If the thing
    you mean is split across three, two of them are silently left out — the
    same class of silent partial application as a missing `label_id`.
"""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)


def composite_splits(client) -> dict:
    """Every composite device split, keyed by COMPOSITE id.

    THE KEY IS NOT A DEVICE ID, which is the thing to get right and the thing
    the first version of this got wrong. HA returns
    `{composite_id: {primary_id, split_ids}}` where the key identifies the
    LOGICAL device and `primary_id`/`split_ids` are the registry entries it was
    split into. Measured on a live instance: of 51 keys, ZERO are also a
    `primary_id`, and none of the 102 split ids is a key. So looking a device
    up by its own id in this dict always misses.

    `member_of` is therefore the reverse index that actually works: registry
    device id -> the composite key it belongs to.
    """
    data = client.ws_call("config/device_registry/list_composite_splits") or {}
    if not isinstance(data, dict):
        return {"count": 0, "splits": {}, "member_of": {}}
    member_of: dict[str, str] = {}
    for composite_id, info in data.items():
        info = info or {}
        for device_id in set(info.get("split_ids") or []) | {info.get("primary_id")}:
            if device_id:
                member_of[device_id] = composite_id
    return {
        "count": len(data),
        "splits": data,
        "member_of": member_of,
        "note": (
            "A device-scoped target applies to ONE registry entry. Where a device "
            "is split, addressing one member does not address the others."
        ),
    }


def split_for(client, device_id: str) -> dict:
    """Is this REGISTRY DEVICE part of a composite split, and what is the set?

    Resolved through `member_of`, never by looking the device id up as a key —
    see `composite_splits` for why that can never match.
    """
    report = composite_splits(client)
    composite_id = report["member_of"].get(device_id)
    if not composite_id:
        return {
            "device_id": device_id,
            "is_split": False,
            "composite_id": None,
            "primary_id": None,
            "split_ids": [],
            "siblings": [],
        }
    info = report["splits"].get(composite_id) or {}
    split_ids = info.get("split_ids") or []
    return {
        "device_id": device_id,
        "is_split": True,
        "composite_id": composite_id,
        "primary_id": info.get("primary_id"),
        "split_ids": split_ids,
        "is_primary": info.get("primary_id") == device_id,
        # The ones a device-scoped call against `device_id` would MISS.
        "siblings": [d for d in split_ids if d != device_id],
    }


def linked_devices(client, device_id: str) -> dict:
    """Other registry entries HA considers the same physical device."""
    data = client.ws_call("config/device_registry/list_linked_devices", {"device_id": device_id})
    if isinstance(data, dict):
        rows = data.get("linked_devices") or data.get("devices") or []
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    return {
        "device_id": device_id,
        "count": len(rows),
        "linked_devices": rows,
        "has_links": bool(rows),
        # The raw payload is kept because HA's shape here is newer than most of
        # the registry API and a future release may add fields; guessing at a
        # narrower projection would drop them silently.
        "raw": data,
    }
