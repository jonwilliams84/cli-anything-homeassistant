"""What does this target actually hit, and what can I do with it?

THE QUESTION NOTHING COULD ANSWER
    A service call takes a `target` — `area_id`, `device_id`, `floor_id`,
    `label_id`, `entity_id` — and Home Assistant expands it into a concrete set
    of entities. Until now this harness could send that target and could not
    ask what it would resolve to. So "turn off the kitchen" was a call you made
    and then went looking at the states to see what had happened.

    `extract()` asks HA the same question its own service layer asks, using the
    same helper (`async_extract_referenced_entity_ids`), and returns the
    referenced entities, devices and areas plus — the half that matters — the
    MISSING ones. A `label_id` that does not exist comes back in
    `missing_labels` rather than silently contributing nothing.

WHAT THE THREE `*_for_target` COMMANDS ARE FOR
    They answer "what can I do with this?" from the other direction: given a
    target, which services / triggers / conditions are usable against it.
    Measured against `sun.sun` on 2026.8.1:

        services   -> homeassistant.turn_on, homeassistant.turn_off,
                      homeassistant.toggle, homeassistant.reload_config_entry
        triggers   -> []
        conditions -> []

    An empty list is a real answer, not a failure: `sun.sun` genuinely has no
    entity-specific trigger or condition platform. Reporting it as empty rather
    than as an error is the whole point.

NOT COVERED HERE, DELIBERATELY
    `entity/source` — which integration supplies an entity — landed on main as
    `entity source` while this module was being written. Two commands for one
    websocket call is worse than either, so it is not duplicated here.

`expand_group` DIFFERS BETWEEN THEM, AND THE DEFAULTS ARE HA'S
    `extract_from_target` defaults `expand_group` to FALSE; the three
    `*_for_target` commands default it to TRUE. That asymmetry is Home
    Assistant's, not this module's, and it is preserved rather than smoothed
    over — a caller who assumes one default for all four gets a different
    entity set from `extract` than the services list was computed over.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

_LOGGER = logging.getLogger(__name__)

#: The fields HA's `cv.TARGET_FIELDS` accepts. Anything else is rejected before
#: the call, because HA's own error for an unknown key — `extra keys not
#: allowed @ data['selector']` — names the wrapper key and not the mistake.
TARGET_FIELDS = ("entity_id", "device_id", "area_id", "floor_id", "label_id")


def build_target(
    *,
    entity_id: Optional[list[str]] = None,
    device_id: Optional[list[str]] = None,
    area_id: Optional[list[str]] = None,
    floor_id: Optional[list[str]] = None,
    label_id: Optional[list[str]] = None,
) -> dict:
    """Assemble a target dict from repeatable CLI options."""
    target: dict[str, Any] = {}
    for key, value in (
        ("entity_id", entity_id),
        ("device_id", device_id),
        ("area_id", area_id),
        ("floor_id", floor_id),
        ("label_id", label_id),
    ):
        if value:
            target[key] = list(value)
    if not target:
        raise ValueError(
            "Empty target. Pass at least one of: "
            + ", ".join(f"--{f.replace('_', '-')}" for f in TARGET_FIELDS)
        )
    return target


def _validate(target: dict) -> dict:
    unknown = [k for k in target if k not in TARGET_FIELDS]
    if unknown:
        raise ValueError(
            f"Not a target field: {', '.join(unknown)}. HA accepts only {', '.join(TARGET_FIELDS)}."
        )
    return target


def extract(
    client,
    target: dict,
    *,
    expand_group: bool = False,
    primary_entities_only: bool = True,
) -> dict:
    """Resolve a target to the entities a service call would really hit.

    `missing_*` is the field to read. HA reports an area/device/floor/label in
    the target that it cannot resolve, and a service call given the same target
    would simply do nothing for it — silently.
    """
    payload = {
        "target": _validate(target),
        "expand_group": expand_group,
        "primary_entities_only": primary_entities_only,
    }
    result = client.ws_call("extract_from_target", payload) or {}
    missing = {
        k: result.get(k) or []
        for k in ("missing_devices", "missing_areas", "missing_floors", "missing_labels")
    }
    entities = result.get("referenced_entities") or []
    return {
        "target": target,
        "expand_group": expand_group,
        "primary_entities_only": primary_entities_only,
        "referenced_entities": entities,
        "referenced_devices": result.get("referenced_devices") or [],
        "referenced_areas": result.get("referenced_areas") or [],
        "entity_count": len(entities),
        **missing,
        "has_missing": any(missing.values()),
        "resolves_to_nothing": not entities,
    }


def _for_target(client, command: str, target: dict, expand_group: bool) -> list:
    result = client.ws_call(command, {"target": _validate(target), "expand_group": expand_group})
    return result if isinstance(result, list) else []


def services_for(client, target: dict, *, expand_group: bool = True) -> dict:
    """Which services can be called against this target."""
    rows = _for_target(client, "get_services_for_target", target, expand_group)
    return {"target": target, "count": len(rows), "services": rows}


def triggers_for(client, target: dict, *, expand_group: bool = True) -> dict:
    """Which triggers are available for this target.

    An empty list is a real answer — most entities have no entity-specific
    trigger platform, and the generic `state` trigger is not reported here.
    """
    rows = _for_target(client, "get_triggers_for_target", target, expand_group)
    return {"target": target, "count": len(rows), "triggers": rows}


def conditions_for(client, target: dict, *, expand_group: bool = True) -> dict:
    """Which conditions are available for this target. Empty is a real answer."""
    rows = _for_target(client, "get_conditions_for_target", target, expand_group)
    return {"target": target, "count": len(rows), "conditions": rows}


def slugify(client, text: str) -> dict:
    """Slugify a string the way HA itself would.

    Reimplementing this in Python would drift: HA's slugify handles unicode,
    em-dashes and repeated separators with rules that have changed across
    releases. Measured: 'Living Room — Lamp #2' -> 'living_room_lamp_2'.
    """
    result = client.ws_call("slugify", {"text": text}) or {}
    return {"text": text, "slug": result.get("slug")}
