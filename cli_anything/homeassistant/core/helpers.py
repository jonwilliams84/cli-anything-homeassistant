"""Helper-entity CRUD and runtime actions.

Home Assistant exposes helpers via two completely different mechanisms:

1. **Storage-collection helpers** (12 types) — managed via a uniform
   ``<domain>/list|create|update|delete`` WS API. Writes land in
   ``.storage/<domain>`` immediately and survive restart.

     - input_boolean (Toggle)        input_button (Button)
     - input_datetime (Date/Time)    input_number (Number)
     - input_select (Dropdown)       input_text (Text)
     - counter                       timer
     - schedule                      tag
     - person                        zone

2. **Config-flow helpers** (17+ types) — created by *initiating a config
   flow* against an integration that registers a helper handler. The
   flow API is generic: ``config_entries/flow/init`` →
   ``config_entries/flow/configure``. The created entry lives in
   ``.storage/core.config_entries``. Helpers in this family:

     - derivative           integration (Riemann sum)
     - utility_meter        min_max (combine sensors)
     - threshold            trend
     - statistics           history_stats
     - filter               random
     - template             group
     - generic_thermostat   generic_hygrostat
     - switch_as_x          tod (Times of the Day)
     - mold_indicator (Mould Indicator)

Service calls on these domains are typically for RUNTIME state changes
(turn_on, set_value, increment, etc.) and are persistent ONLY for state
attributes — NOT for config attributes like options or step. Use
``<type>_update`` for config changes; use the service-call helpers
for runtime actions.

Key gotcha: `input_select.set_options` is a SERVICE call that updates the
runtime options list but DOES NOT write to .storage. The change reverts
on restart. Use ``input_select_update(client, eid, options=...)`` for
persistent option changes. Same caveat applies if you ever see
`<helper>.set_<something>` services — prefer the WS update.
"""

from __future__ import annotations


def _get_state(client, entity_id: str) -> dict:
    states = client.get(f"states/{entity_id}")
    if not isinstance(states, dict) or "attributes" not in states:
        raise ValueError(f"entity {entity_id!r} not found or missing attributes")
    return states


def _name_of(state: dict, fallback_eid: str) -> str:
    return (state.get("attributes", {}).get("friendly_name")
            or fallback_eid.split(".", 1)[1])


def _split_eid(entity_id: str, expected_domain: str) -> str:
    """Validate and return the object_id portion of entity_id."""
    domain, _, obj = entity_id.partition(".")
    if domain != expected_domain:
        raise ValueError(
            f"expected {expected_domain}.* entity_id, got {entity_id!r}"
        )
    if not obj:
        raise ValueError(f"entity_id {entity_id!r} has no object_id")
    return obj


def _ws_collection(client, domain: str, op: str, *, payload: dict) -> dict:
    """Wrap a `<domain>/<op>` storage-collection WS call."""
    return client.ws_call(f"{domain}/{op}", payload)


def input_select_set_options(client, entity_id: str, options: list[str]) -> dict:
    """Set the options list on an input_select via service call.

    Returns the entity's state dict after the change.
    """
    if not entity_id.startswith("input_select."):
        raise ValueError(f"expected input_select.* entity_id, got {entity_id!r}")
    if not isinstance(options, list) or not all(isinstance(o, str) for o in options):
        raise ValueError("options must be a list of strings")
    client.post("services/input_select/set_options", {
        "entity_id": entity_id,
        "options": options,
    })
    return _get_state(client, entity_id)


def input_select_select(client, entity_id: str, option: str) -> dict:
    """Set the current selection on an input_select."""
    client.post("services/input_select/select_option", {
        "entity_id": entity_id,
        "option": option,
    })
    return _get_state(client, entity_id)


def input_select_create(client, name: str, options: list[str], *,
                          icon: str | None = None,
                          initial: str | None = None) -> dict:
    """Create a NEW input_select helper at runtime.

    Uses HA's storage-collection WS command (``input_select/create``).
    The new helper is registered in `.storage/input_select` immediately
    and survives restart — so this is the right thing to call when
    provisioning a new helper from a script.

    Returns the created helper's record (with ``id``).
    """
    if not name:
        raise ValueError("name is required")
    if not isinstance(options, list) or not options:
        raise ValueError("options must be a non-empty list")
    payload: dict = {"name": name, "options": list(options)}
    if icon:
        payload["icon"] = icon
    if initial:
        payload["initial"] = initial
    return client.ws_call("input_select/create", payload)


def input_select_update(client, entity_id: str, *,
                          options: list[str] | None = None,
                          name: str | None = None,
                          icon: str | None = None,
                          initial: str | None = None) -> dict:
    """PERSISTENTLY update an input_select helper (UI-managed only).

    Uses HA's storage-collection WS command ``input_select/update``. The
    change is written to ``.storage/input_select`` immediately and
    survives HA restart — unlike ``input_select_set_options`` which only
    updates the runtime state and reverts on restart.

    The helper must be UI-managed (created via Settings → Helpers or via
    ``input_select/create``). YAML-defined input_selects cannot be
    updated this way — for those, the YAML config must be edited.

    `entity_id` — the full entity_id (e.g. `input_select.room_selector_jon`).
    The WS API strips the domain prefix internally.

    At least one of `options`, `name`, `icon`, or `initial` must be set.
    """
    if not entity_id.startswith("input_select."):
        raise ValueError(f"expected input_select.* entity_id, got {entity_id!r}")
    if options is None and name is None and icon is None and initial is None:
        raise ValueError("nothing to update — pass options/name/icon/initial")
    payload: dict = {"input_select_id": entity_id.split(".", 1)[1]}
    if options is not None:
        if not isinstance(options, list) or not options:
            raise ValueError("options must be a non-empty list")
        payload["options"] = list(options)
    if name is not None: payload["name"] = name
    if icon is not None: payload["icon"] = icon
    if initial is not None: payload["initial"] = initial
    return client.ws_call("input_select/update", payload)


def input_select_sync(client, src_entity_id: str, dst_entity_id: str,
                       *, fallback: str = "Auto") -> dict:
    """Copy the OPTIONS list from src to dst input_select. PERSISTS across
    HA restarts (uses ``input_select/update`` WS API).

    If the destination's current state isn't in the new options list,
    selects ``fallback`` first (or the first option if ``fallback`` is
    missing) so the helper isn't stranded in an unknown value.

    Returns ``{"changed": bool, "src_options": [...], "dst_state": "..."}``.
    """
    src = _get_state(client, src_entity_id)
    dst = _get_state(client, dst_entity_id)
    src_opts = src["attributes"].get("options", [])
    dst_opts = dst["attributes"].get("options", [])
    if src_opts == dst_opts:
        return {"changed": False, "src_options": src_opts,
                "dst_state": dst.get("state")}
    dst_state = dst.get("state")
    if dst_state not in src_opts:
        choose = fallback if fallback in src_opts else (src_opts[0] if src_opts else None)
        if choose is not None:
            input_select_select(client, dst_entity_id, choose)
    # Use the PERSISTENT update API (not set_options, which is in-memory).
    dst_name = dst["attributes"].get("friendly_name") or \
        dst_entity_id.split(".", 1)[1]
    input_select_update(client, dst_entity_id,
                          options=src_opts, name=dst_name)
    after = _get_state(client, dst_entity_id)
    return {
        "changed": True,
        "src_options": src_opts,
        "dst_state": after.get("state"),
    }


# ════════════════════════════════════════════════════════════════════════
# input_boolean — toggle
# ════════════════════════════════════════════════════════════════════════

def input_boolean_list(client) -> list[dict]:
    return _ws_collection(client, "input_boolean", "list", payload={})


def input_boolean_create(client, name: str, *,
                           icon: str | None = None,
                           initial: bool | None = None) -> dict:
    if not name:
        raise ValueError("name required")
    payload: dict = {"name": name}
    if icon: payload["icon"] = icon
    if initial is not None: payload["initial"] = initial
    return _ws_collection(client, "input_boolean", "create", payload=payload)


def input_boolean_update(client, entity_id: str, *,
                           name: str | None = None,
                           icon: str | None = None,
                           initial: bool | None = None) -> dict:
    obj = _split_eid(entity_id, "input_boolean")
    if name is None and icon is None and initial is None:
        raise ValueError("pass at least one of name/icon/initial")
    state = _get_state(client, entity_id)
    payload: dict = {
        "input_boolean_id": obj,
        "name": name if name is not None else _name_of(state, entity_id),
    }
    if icon is not None: payload["icon"] = icon
    if initial is not None: payload["initial"] = initial
    return _ws_collection(client, "input_boolean", "update", payload=payload)


def input_boolean_delete(client, entity_id: str) -> dict:
    return _ws_collection(client, "input_boolean", "delete",
                            payload={"input_boolean_id":
                                     _split_eid(entity_id, "input_boolean")})


def input_boolean_turn_on(client, entity_id: str) -> dict:
    return client.post("services/input_boolean/turn_on", {"entity_id": entity_id})


def input_boolean_turn_off(client, entity_id: str) -> dict:
    return client.post("services/input_boolean/turn_off", {"entity_id": entity_id})


def input_boolean_toggle(client, entity_id: str) -> dict:
    return client.post("services/input_boolean/toggle", {"entity_id": entity_id})


# ════════════════════════════════════════════════════════════════════════
# input_button — momentary press
# ════════════════════════════════════════════════════════════════════════

def input_button_list(client) -> list[dict]:
    return _ws_collection(client, "input_button", "list", payload={})


def input_button_create(client, name: str, *,
                          icon: str | None = None) -> dict:
    if not name:
        raise ValueError("name required")
    payload: dict = {"name": name}
    if icon: payload["icon"] = icon
    return _ws_collection(client, "input_button", "create", payload=payload)


def input_button_update(client, entity_id: str, *,
                          name: str | None = None,
                          icon: str | None = None) -> dict:
    obj = _split_eid(entity_id, "input_button")
    if name is None and icon is None:
        raise ValueError("pass at least one of name/icon")
    state = _get_state(client, entity_id)
    payload: dict = {
        "input_button_id": obj,
        "name": name if name is not None else _name_of(state, entity_id),
    }
    if icon is not None: payload["icon"] = icon
    return _ws_collection(client, "input_button", "update", payload=payload)


def input_button_delete(client, entity_id: str) -> dict:
    return _ws_collection(client, "input_button", "delete",
                            payload={"input_button_id":
                                     _split_eid(entity_id, "input_button")})


def input_button_press(client, entity_id: str) -> dict:
    return client.post("services/input_button/press", {"entity_id": entity_id})


# ════════════════════════════════════════════════════════════════════════
# input_number — numeric value
# ════════════════════════════════════════════════════════════════════════

def input_number_list(client) -> list[dict]:
    return _ws_collection(client, "input_number", "list", payload={})


def input_number_create(client, name: str, *,
                          min: float, max: float,
                          step: float = 1.0,
                          mode: str = "slider",
                          unit_of_measurement: str | None = None,
                          icon: str | None = None,
                          initial: float | None = None) -> dict:
    if not name:
        raise ValueError("name required")
    if mode not in ("slider", "box"):
        raise ValueError(f"mode must be slider/box, got {mode!r}")
    if step <= 0:
        raise ValueError("step must be positive")
    if max <= min:
        raise ValueError("max must be > min")
    payload: dict = {"name": name, "min": min, "max": max,
                       "step": step, "mode": mode}
    if unit_of_measurement is not None:
        payload["unit_of_measurement"] = unit_of_measurement
    if icon is not None: payload["icon"] = icon
    if initial is not None: payload["initial"] = initial
    return _ws_collection(client, "input_number", "create", payload=payload)


def input_number_update(client, entity_id: str, *,
                          name: str | None = None,
                          min: float | None = None,
                          max: float | None = None,
                          step: float | None = None,
                          mode: str | None = None,
                          unit_of_measurement: str | None = None,
                          icon: str | None = None,
                          initial: float | None = None) -> dict:
    obj = _split_eid(entity_id, "input_number")
    state = _get_state(client, entity_id)
    attrs = state.get("attributes", {})
    payload: dict = {
        "input_number_id": obj,
        "name": name if name is not None else _name_of(state, entity_id),
        "min": min if min is not None else attrs.get("min", 0),
        "max": max if max is not None else attrs.get("max", 100),
        "step": step if step is not None else attrs.get("step", 1),
        "mode": mode if mode is not None else attrs.get("mode", "slider"),
    }
    cur_unit = attrs.get("unit_of_measurement")
    if unit_of_measurement is not None or cur_unit:
        payload["unit_of_measurement"] = unit_of_measurement or cur_unit
    if icon is not None: payload["icon"] = icon
    if initial is not None: payload["initial"] = initial
    return _ws_collection(client, "input_number", "update", payload=payload)


def input_number_delete(client, entity_id: str) -> dict:
    return _ws_collection(client, "input_number", "delete",
                            payload={"input_number_id":
                                     _split_eid(entity_id, "input_number")})


def input_number_set_value(client, entity_id: str, value: float) -> dict:
    return client.post("services/input_number/set_value",
                          {"entity_id": entity_id, "value": value})


def input_number_increment(client, entity_id: str) -> dict:
    return client.post("services/input_number/increment", {"entity_id": entity_id})


def input_number_decrement(client, entity_id: str) -> dict:
    return client.post("services/input_number/decrement", {"entity_id": entity_id})


# ════════════════════════════════════════════════════════════════════════
# input_text — string value
# ════════════════════════════════════════════════════════════════════════

def input_text_list(client) -> list[dict]:
    return _ws_collection(client, "input_text", "list", payload={})


def input_text_create(client, name: str, *,
                        min: int = 0,
                        max: int = 100,
                        pattern: str | None = None,
                        mode: str = "text",
                        icon: str | None = None,
                        initial: str | None = None) -> dict:
    if not name:
        raise ValueError("name required")
    if mode not in ("text", "password"):
        raise ValueError(f"mode must be text/password, got {mode!r}")
    if min < 0 or max < min:
        raise ValueError("min/max must satisfy 0 <= min <= max")
    payload: dict = {"name": name, "min": min, "max": max, "mode": mode}
    if pattern is not None: payload["pattern"] = pattern
    if icon is not None: payload["icon"] = icon
    if initial is not None: payload["initial"] = initial
    return _ws_collection(client, "input_text", "create", payload=payload)


def input_text_update(client, entity_id: str, *,
                        name: str | None = None,
                        min: int | None = None,
                        max: int | None = None,
                        pattern: str | None = None,
                        mode: str | None = None,
                        icon: str | None = None,
                        initial: str | None = None) -> dict:
    obj = _split_eid(entity_id, "input_text")
    state = _get_state(client, entity_id)
    attrs = state.get("attributes", {})
    payload: dict = {
        "input_text_id": obj,
        "name": name if name is not None else _name_of(state, entity_id),
        "min": min if min is not None else attrs.get("min", 0),
        "max": max if max is not None else attrs.get("max", 100),
        "mode": mode if mode is not None else attrs.get("mode", "text"),
    }
    cur_pattern = attrs.get("pattern")
    if pattern is not None or cur_pattern:
        payload["pattern"] = pattern or cur_pattern
    if icon is not None: payload["icon"] = icon
    if initial is not None: payload["initial"] = initial
    return _ws_collection(client, "input_text", "update", payload=payload)


def input_text_delete(client, entity_id: str) -> dict:
    return _ws_collection(client, "input_text", "delete",
                            payload={"input_text_id":
                                     _split_eid(entity_id, "input_text")})


def input_text_set_value(client, entity_id: str, value: str) -> dict:
    return client.post("services/input_text/set_value",
                          {"entity_id": entity_id, "value": value})


# ════════════════════════════════════════════════════════════════════════
# input_datetime — date and/or time
# ════════════════════════════════════════════════════════════════════════

def input_datetime_list(client) -> list[dict]:
    return _ws_collection(client, "input_datetime", "list", payload={})


def input_datetime_create(client, name: str, *,
                            has_date: bool = True,
                            has_time: bool = True,
                            icon: str | None = None,
                            initial: str | None = None) -> dict:
    if not name:
        raise ValueError("name required")
    if not (has_date or has_time):
        raise ValueError("at least one of has_date/has_time must be true")
    payload: dict = {"name": name,
                       "has_date": has_date, "has_time": has_time}
    if icon is not None: payload["icon"] = icon
    if initial is not None: payload["initial"] = initial
    return _ws_collection(client, "input_datetime", "create", payload=payload)


def input_datetime_update(client, entity_id: str, *,
                            name: str | None = None,
                            has_date: bool | None = None,
                            has_time: bool | None = None,
                            icon: str | None = None,
                            initial: str | None = None) -> dict:
    obj = _split_eid(entity_id, "input_datetime")
    state = _get_state(client, entity_id)
    attrs = state.get("attributes", {})
    payload: dict = {
        "input_datetime_id": obj,
        "name": name if name is not None else _name_of(state, entity_id),
        "has_date": has_date if has_date is not None else attrs.get("has_date", True),
        "has_time": has_time if has_time is not None else attrs.get("has_time", True),
    }
    if icon is not None: payload["icon"] = icon
    if initial is not None: payload["initial"] = initial
    return _ws_collection(client, "input_datetime", "update", payload=payload)


def input_datetime_delete(client, entity_id: str) -> dict:
    return _ws_collection(client, "input_datetime", "delete",
                            payload={"input_datetime_id":
                                     _split_eid(entity_id, "input_datetime")})


def input_datetime_set(client, entity_id: str, *,
                         date: str | None = None,
                         time: str | None = None,
                         datetime: str | None = None) -> dict:
    """Set value via service. Pass `date` (YYYY-MM-DD), `time` (HH:MM:SS),
    or `datetime` (YYYY-MM-DD HH:MM:SS) — any combination of the helper's
    enabled fields.
    """
    payload: dict = {"entity_id": entity_id}
    if date is not None: payload["date"] = date
    if time is not None: payload["time"] = time
    if datetime is not None: payload["datetime"] = datetime
    if not (date or time or datetime):
        raise ValueError("pass at least one of date/time/datetime")
    return client.post("services/input_datetime/set_datetime", payload)


# ════════════════════════════════════════════════════════════════════════
# counter — incrementing integer
# ════════════════════════════════════════════════════════════════════════

def counter_list(client) -> list[dict]:
    return _ws_collection(client, "counter", "list", payload={})


def counter_create(client, name: str, *,
                     initial: int = 0,
                     step: int = 1,
                     minimum: int | None = None,
                     maximum: int | None = None,
                     restore: bool = True,
                     icon: str | None = None) -> dict:
    if not name:
        raise ValueError("name required")
    if step <= 0:
        raise ValueError("step must be positive")
    payload: dict = {"name": name,
                       "initial": initial, "step": step, "restore": restore}
    if minimum is not None: payload["minimum"] = minimum
    if maximum is not None: payload["maximum"] = maximum
    if icon is not None: payload["icon"] = icon
    return _ws_collection(client, "counter", "create", payload=payload)


def counter_update(client, entity_id: str, *,
                     name: str | None = None,
                     initial: int | None = None,
                     step: int | None = None,
                     minimum: int | None = None,
                     maximum: int | None = None,
                     restore: bool | None = None,
                     icon: str | None = None) -> dict:
    obj = _split_eid(entity_id, "counter")
    state = _get_state(client, entity_id)
    attrs = state.get("attributes", {})
    payload: dict = {
        "counter_id": obj,
        "name": name if name is not None else _name_of(state, entity_id),
        "initial": initial if initial is not None else attrs.get("initial", 0),
        "step": step if step is not None else attrs.get("step", 1),
        "restore": restore if restore is not None else attrs.get("restore", True),
    }
    if minimum is not None or attrs.get("minimum") is not None:
        payload["minimum"] = minimum if minimum is not None else attrs.get("minimum")
    if maximum is not None or attrs.get("maximum") is not None:
        payload["maximum"] = maximum if maximum is not None else attrs.get("maximum")
    if icon is not None: payload["icon"] = icon
    return _ws_collection(client, "counter", "update", payload=payload)


def counter_delete(client, entity_id: str) -> dict:
    return _ws_collection(client, "counter", "delete",
                            payload={"counter_id":
                                     _split_eid(entity_id, "counter")})


def counter_increment(client, entity_id: str) -> dict:
    return client.post("services/counter/increment", {"entity_id": entity_id})


def counter_decrement(client, entity_id: str) -> dict:
    return client.post("services/counter/decrement", {"entity_id": entity_id})


def counter_reset(client, entity_id: str) -> dict:
    return client.post("services/counter/reset", {"entity_id": entity_id})


def counter_set_value(client, entity_id: str, value: int) -> dict:
    return client.post("services/counter/set_value",
                          {"entity_id": entity_id, "value": value})


# ════════════════════════════════════════════════════════════════════════
# timer — countdown
# ════════════════════════════════════════════════════════════════════════

def timer_list(client) -> list[dict]:
    return _ws_collection(client, "timer", "list", payload={})


def timer_create(client, name: str, *,
                   duration: str = "00:00:00",
                   restore: bool = False,
                   icon: str | None = None) -> dict:
    """Create a timer. `duration` is HH:MM:SS string."""
    if not name:
        raise ValueError("name required")
    payload: dict = {"name": name, "duration": duration, "restore": restore}
    if icon is not None: payload["icon"] = icon
    return _ws_collection(client, "timer", "create", payload=payload)


def timer_update(client, entity_id: str, *,
                   name: str | None = None,
                   duration: str | None = None,
                   restore: bool | None = None,
                   icon: str | None = None) -> dict:
    obj = _split_eid(entity_id, "timer")
    state = _get_state(client, entity_id)
    attrs = state.get("attributes", {})
    payload: dict = {
        "timer_id": obj,
        "name": name if name is not None else _name_of(state, entity_id),
        "duration": duration if duration is not None
                      else attrs.get("duration", "00:00:00"),
        "restore": restore if restore is not None
                      else attrs.get("restore", False),
    }
    if icon is not None: payload["icon"] = icon
    return _ws_collection(client, "timer", "update", payload=payload)


def timer_delete(client, entity_id: str) -> dict:
    return _ws_collection(client, "timer", "delete",
                            payload={"timer_id": _split_eid(entity_id, "timer")})


def timer_start(client, entity_id: str, *, duration: str | None = None) -> dict:
    payload: dict = {"entity_id": entity_id}
    if duration: payload["duration"] = duration
    return client.post("services/timer/start", payload)


def timer_pause(client, entity_id: str) -> dict:
    return client.post("services/timer/pause", {"entity_id": entity_id})


def timer_cancel(client, entity_id: str) -> dict:
    return client.post("services/timer/cancel", {"entity_id": entity_id})


def timer_finish(client, entity_id: str) -> dict:
    return client.post("services/timer/finish", {"entity_id": entity_id})


def timer_change(client, entity_id: str, duration: str) -> dict:
    """Add (positive) or subtract (negative) duration from a running timer."""
    return client.post("services/timer/change",
                          {"entity_id": entity_id, "duration": duration})


# ════════════════════════════════════════════════════════════════════════
# schedule — weekly recurring on/off windows
# ════════════════════════════════════════════════════════════════════════
# Schedule has no runtime service actions — it's entirely managed via
# the storage-collection API. State is auto-computed from the windows.

def schedule_list(client) -> list[dict]:
    return _ws_collection(client, "schedule", "list", payload={})


def schedule_create(client, name: str, *,
                      monday: list[dict] | None = None,
                      tuesday: list[dict] | None = None,
                      wednesday: list[dict] | None = None,
                      thursday: list[dict] | None = None,
                      friday: list[dict] | None = None,
                      saturday: list[dict] | None = None,
                      sunday: list[dict] | None = None,
                      icon: str | None = None) -> dict:
    """Create a schedule. Each day takes a list of windows like
    ``[{from: "08:00:00", to: "12:00:00"}, ...]``."""
    if not name:
        raise ValueError("name required")
    payload: dict = {"name": name}
    for day, windows in (("monday", monday), ("tuesday", tuesday),
                           ("wednesday", wednesday), ("thursday", thursday),
                           ("friday", friday), ("saturday", saturday),
                           ("sunday", sunday)):
        if windows is not None:
            payload[day] = windows
    if icon is not None: payload["icon"] = icon
    return _ws_collection(client, "schedule", "create", payload=payload)


def schedule_update(client, entity_id: str, *,
                      name: str | None = None,
                      monday: list[dict] | None = None,
                      tuesday: list[dict] | None = None,
                      wednesday: list[dict] | None = None,
                      thursday: list[dict] | None = None,
                      friday: list[dict] | None = None,
                      saturday: list[dict] | None = None,
                      sunday: list[dict] | None = None,
                      icon: str | None = None) -> dict:
    obj = _split_eid(entity_id, "schedule")
    state = _get_state(client, entity_id)
    payload: dict = {
        "schedule_id": obj,
        "name": name if name is not None else _name_of(state, entity_id),
    }
    for day, windows in (("monday", monday), ("tuesday", tuesday),
                           ("wednesday", wednesday), ("thursday", thursday),
                           ("friday", friday), ("saturday", saturday),
                           ("sunday", sunday)):
        if windows is not None:
            payload[day] = windows
    if icon is not None: payload["icon"] = icon
    return _ws_collection(client, "schedule", "update", payload=payload)


def schedule_delete(client, entity_id: str) -> dict:
    return _ws_collection(client, "schedule", "delete",
                            payload={"schedule_id":
                                     _split_eid(entity_id, "schedule")})


# ════════════════════════════════════════════════════════════════════════
# person — household members (storage-collection)
# ════════════════════════════════════════════════════════════════════════

def person_list(client) -> list[dict]:
    return _ws_collection(client, "person", "list", payload={})


def person_create(client, name: str, *,
                    user_id: str | None = None,
                    device_trackers: list[str] | None = None,
                    picture: str | None = None) -> dict:
    if not name:
        raise ValueError("name required")
    payload: dict = {"name": name,
                       "device_trackers": list(device_trackers or [])}
    if user_id is not None: payload["user_id"] = user_id
    if picture is not None: payload["picture"] = picture
    return _ws_collection(client, "person", "create", payload=payload)


def person_update(client, person_id: str, *,
                    name: str | None = None,
                    user_id: str | None = None,
                    device_trackers: list[str] | None = None,
                    picture: str | None = None) -> dict:
    """`person_id` is the registry id (not entity_id), as returned by
    ``person_list``/``person_create``."""
    if not person_id:
        raise ValueError("person_id required")
    payload: dict = {"person_id": person_id}
    if name is not None: payload["name"] = name
    if user_id is not None: payload["user_id"] = user_id
    if device_trackers is not None:
        payload["device_trackers"] = list(device_trackers)
    if picture is not None: payload["picture"] = picture
    if len(payload) == 1:
        raise ValueError("pass at least one of name/user_id/device_trackers/picture")
    return _ws_collection(client, "person", "update", payload=payload)


def person_delete(client, person_id: str) -> dict:
    if not person_id:
        raise ValueError("person_id required")
    return _ws_collection(client, "person", "delete",
                            payload={"person_id": person_id})


# ════════════════════════════════════════════════════════════════════════
# zone — geographic zones (storage-collection)
# ════════════════════════════════════════════════════════════════════════

def zone_list(client) -> list[dict]:
    return _ws_collection(client, "zone", "list", payload={})


def zone_create(client, name: str, *,
                  latitude: float, longitude: float,
                  radius: float = 100.0,
                  icon: str | None = None,
                  passive: bool = False) -> dict:
    if not name:
        raise ValueError("name required")
    if radius <= 0:
        raise ValueError("radius must be positive (metres)")
    payload: dict = {"name": name, "latitude": latitude,
                       "longitude": longitude, "radius": radius,
                       "passive": passive}
    if icon is not None: payload["icon"] = icon
    return _ws_collection(client, "zone", "create", payload=payload)


def zone_update(client, zone_id: str, *,
                  name: str | None = None,
                  latitude: float | None = None,
                  longitude: float | None = None,
                  radius: float | None = None,
                  icon: str | None = None,
                  passive: bool | None = None) -> dict:
    """`zone_id` is the registry id (not entity_id)."""
    if not zone_id:
        raise ValueError("zone_id required")
    payload: dict = {"zone_id": zone_id}
    if name is not None: payload["name"] = name
    if latitude is not None: payload["latitude"] = latitude
    if longitude is not None: payload["longitude"] = longitude
    if radius is not None:
        if radius <= 0:
            raise ValueError("radius must be positive")
        payload["radius"] = radius
    if icon is not None: payload["icon"] = icon
    if passive is not None: payload["passive"] = passive
    if len(payload) == 1:
        raise ValueError("pass at least one field to update")
    return _ws_collection(client, "zone", "update", payload=payload)


def zone_delete(client, zone_id: str) -> dict:
    if not zone_id:
        raise ValueError("zone_id required")
    return _ws_collection(client, "zone", "delete",
                            payload={"zone_id": zone_id})


# ════════════════════════════════════════════════════════════════════════
# tag — NFC / QR tags (storage-collection)
# ════════════════════════════════════════════════════════════════════════
# Tag IDs are user-assigned strings (often UUIDs from physical tags).
# ``tag/create`` requires ``tag_id``; ``tag/update`` keys on the same.

def tag_list(client) -> list[dict]:
    return _ws_collection(client, "tag", "list", payload={})


def tag_create(client, tag_id: str, *,
                 name: str | None = None,
                 description: str | None = None) -> dict:
    if not tag_id:
        raise ValueError("tag_id required")
    payload: dict = {"tag_id": tag_id}
    if name is not None: payload["name"] = name
    if description is not None: payload["description"] = description
    return _ws_collection(client, "tag", "create", payload=payload)


def tag_update(client, tag_id: str, *,
                 name: str | None = None,
                 description: str | None = None) -> dict:
    if not tag_id:
        raise ValueError("tag_id required")
    if name is None and description is None:
        raise ValueError("pass name and/or description")
    payload: dict = {"tag_id": tag_id}
    if name is not None: payload["name"] = name
    if description is not None: payload["description"] = description
    return _ws_collection(client, "tag", "update", payload=payload)


def tag_delete(client, tag_id: str) -> dict:
    if not tag_id:
        raise ValueError("tag_id required")
    return _ws_collection(client, "tag", "delete",
                            payload={"tag_id": tag_id})


# ════════════════════════════════════════════════════════════════════════
# Config-flow helpers — derivative, utility_meter, template, group, etc.
# ════════════════════════════════════════════════════════════════════════
# These don't have a per-domain storage-collection API. Instead, HA exposes
# helpers as config-flow integrations: you initiate a flow, walk through
# the steps (usually just "user"), and it creates a ConfigEntry that lives
# in `.storage/core.config_entries`.
#
# WS APIs used here:
#   config_entries/flow/init      { handler, show_advanced_options }
#   config_entries/flow/configure { flow_id, user_input }
#   config_entries/get            (list all config entries)
#   config_entries/remove         { entry_id }
#
# REST fallback (when WS is awkward) — same shape under /api/config/...
# but we stick to WS for consistency with the rest of this module.

CONFIG_FLOW_HELPER_DOMAINS = (
    "derivative", "integration", "utility_meter",
    "min_max", "threshold", "trend",
    "statistics", "history_stats", "filter",
    "random", "template", "group",
    "generic_thermostat", "generic_hygrostat",
    "switch_as_x", "tod", "mold_indicator",
)


def config_entries_list(client, *, domain: str | None = None,
                          type_filter: str | None = None) -> list[dict]:
    """List config entries.

    `type_filter` — pass ``"helper"`` to get only helper integrations
    (recommended for inspecting created helpers). Pass ``"integration"``
    for normal integrations, or omit for everything.

    `domain` — further filter by integration domain (e.g. ``"derivative"``).
    """
    payload: dict = {}
    if type_filter: payload["type_filter"] = type_filter
    if domain: payload["domain"] = domain
    entries = _ws_collection(client, "config_entries", "get",
                               payload=payload) or []
    if not isinstance(entries, list):
        return entries
    if domain:
        entries = [e for e in entries if e.get("domain") == domain]
    return entries


def config_entry_remove(client, entry_id: str) -> dict:
    """Remove a config entry (works for both integrations and helpers)."""
    if not entry_id:
        raise ValueError("entry_id required")
    return _ws_collection(client, "config_entries", "remove",
                            payload={"entry_id": entry_id})


def config_flow_init(client, handler: str, *,
                      show_advanced_options: bool = False) -> dict:
    """Start a new config-entry flow for `handler` (e.g. ``"derivative"``).

    Returns the flow descriptor including ``flow_id`` and either
    ``data_schema`` (more steps needed) or a created ``result``.
    """
    if not handler:
        raise ValueError("handler required")
    return _ws_collection(client, "config_entries/flow", "init",
                            payload={"handler": handler,
                                       "show_advanced_options": show_advanced_options})


def config_flow_configure(client, flow_id: str, user_input: dict) -> dict:
    """Submit user_input for an in-progress flow step.

    Returns either the next step's descriptor or the final ``create_entry``
    result with the new entry's ``result.entry_id``.
    """
    if not flow_id:
        raise ValueError("flow_id required")
    if not isinstance(user_input, dict):
        raise ValueError("user_input must be a dict")
    return _ws_collection(client, "config_entries/flow", "configure",
                            payload={"flow_id": flow_id,
                                       "user_input": user_input})


def config_flow_helper_create(client, domain: str, user_input: dict,
                                *, show_advanced_options: bool = False) -> dict:
    """Convenience: create a helper by initiating its flow and submitting
    `user_input` in one shot. Works for any single-step helper flow (the
    common case — most helpers only have a ``user`` step).

    Multi-step flows can call ``config_flow_init`` / ``config_flow_configure``
    directly to walk each step.

    Returns the final flow result. The created entry_id is at
    ``result["result"]["entry_id"]`` (when type == "create_entry").
    """
    if domain not in CONFIG_FLOW_HELPER_DOMAINS:
        # Allow unknown domains too (HA may add more), just warn via ValueError
        # caller can pass any domain; we only validate against the known list
        # for typo protection. Disabling here so future helpers keep working.
        pass
    flow = config_flow_init(client, domain,
                              show_advanced_options=show_advanced_options)
    flow_id = flow.get("flow_id")
    if not flow_id:
        # Already finished? (some single-shot handlers may resolve in init)
        return flow
    return config_flow_configure(client, flow_id, user_input)


# ────────────────────────────────────────────────────────────────────────
# Per-domain convenience wrappers (validate the required fields HA expects
# for each helper integration's user_input). All return the create_entry
# flow result.
# ────────────────────────────────────────────────────────────────────────

def _create_helper(client, domain: str, data: dict) -> dict:
    return config_flow_helper_create(client, domain, data)


def derivative_create(client, *, name: str, source: str,
                        time_window: dict | None = None,
                        unit_prefix: str | None = None,
                        unit_time: str = "h",
                        round: int = 2) -> dict:
    """Create a Derivative sensor (d/dt of a source sensor).

    `time_window` — e.g. ``{"hours": 0, "minutes": 5, "seconds": 0}``.
    `unit_prefix` — None|k|M|G|...   `unit_time` — s|min|h|d
    """
    if not name or not source:
        raise ValueError("name and source required")
    data: dict = {"name": name, "source": source,
                    "unit_time": unit_time, "round": round}
    if time_window is not None: data["time_window"] = time_window
    if unit_prefix is not None: data["unit_prefix"] = unit_prefix
    return _create_helper(client, "derivative", data)


def integration_create(client, *, name: str, source: str,
                         method: str = "trapezoidal",
                         round: int = 2,
                         unit_prefix: str | None = None,
                         unit_time: str = "h") -> dict:
    """Create a Riemann-sum Integral sensor.

    `method` — left | right | trapezoidal
    """
    if method not in ("left", "right", "trapezoidal"):
        raise ValueError("method must be left|right|trapezoidal")
    data: dict = {"name": name, "source": source,
                    "method": method, "round": round, "unit_time": unit_time}
    if unit_prefix is not None: data["unit_prefix"] = unit_prefix
    return _create_helper(client, "integration", data)


def utility_meter_create(client, *, name: str, source: str,
                           cycle: str = "none",
                           offset: int = 0,
                           net_consumption: bool = False,
                           delta_values: bool = False,
                           periodically_resetting: bool = True,
                           tariffs: list[str] | None = None) -> dict:
    """Create a Utility Meter (totaliser with optional cycle resets).

    `cycle` — none | quarter-hourly | hourly | daily | weekly | monthly |
              bimonthly | quarterly | yearly
    """
    valid_cycles = {"none", "quarter-hourly", "hourly", "daily", "weekly",
                    "monthly", "bimonthly", "quarterly", "yearly"}
    if cycle not in valid_cycles:
        raise ValueError(f"cycle must be one of {sorted(valid_cycles)}")
    data: dict = {"name": name, "source": source, "cycle": cycle,
                    "offset": offset, "net_consumption": net_consumption,
                    "delta_values": delta_values,
                    "periodically_resetting": periodically_resetting,
                    "tariffs": list(tariffs or [])}
    return _create_helper(client, "utility_meter", data)


def min_max_create(client, *, name: str, entity_ids: list[str],
                     type: str = "mean",
                     round_digits: int = 2) -> dict:
    """Combine the state of several sensors.

    `type` — min | max | mean | median | last | range | sum
    """
    valid = {"min", "max", "mean", "median", "last", "range", "sum"}
    if type not in valid:
        raise ValueError(f"type must be one of {sorted(valid)}")
    if not entity_ids:
        raise ValueError("entity_ids must be non-empty")
    data = {"name": name, "entity_ids": list(entity_ids),
              "type": type, "round_digits": round_digits}
    return _create_helper(client, "min_max", data)


def threshold_create(client, *, name: str, entity_id: str,
                       hysteresis: float = 0.0,
                       lower: float | None = None,
                       upper: float | None = None) -> dict:
    """Threshold binary sensor — on when source crosses lower/upper."""
    if lower is None and upper is None:
        raise ValueError("at least one of lower/upper required")
    data: dict = {"name": name, "entity_id": entity_id,
                    "hysteresis": hysteresis}
    if lower is not None: data["lower"] = lower
    if upper is not None: data["upper"] = upper
    return _create_helper(client, "threshold", data)


def trend_create(client, *, name: str, entity_id: str,
                   attribute: str | None = None,
                   invert: bool = False,
                   max_samples: int = 2,
                   min_gradient: float = 0.0,
                   sample_duration: int = 0) -> dict:
    """Trend binary sensor — on when source is rising (or falling, inverted)."""
    data: dict = {"name": name, "entity_id": entity_id, "invert": invert,
                    "max_samples": max_samples,
                    "min_gradient": min_gradient,
                    "sample_duration": sample_duration}
    if attribute is not None: data["attribute"] = attribute
    return _create_helper(client, "trend", data)


def statistics_create(client, *, name: str, entity_id: str,
                        state_characteristic: str = "mean",
                        max_age: dict | None = None,
                        sampling_size: int = 20,
                        precision: int = 2,
                        keep_last_sample: bool = False,
                        percentile: int = 50) -> dict:
    """Statistics sensor — rolling stats over a window of samples."""
    data: dict = {"name": name, "entity_id": entity_id,
                    "state_characteristic": state_characteristic,
                    "sampling_size": sampling_size,
                    "precision": precision,
                    "keep_last_sample": keep_last_sample,
                    "percentile": percentile}
    if max_age is not None: data["max_age"] = max_age
    return _create_helper(client, "statistics", data)


def history_stats_create(client, *, name: str, entity_id: str,
                           state: str,
                           type: str = "time",
                           start: str | None = None,
                           end: str | None = None,
                           duration: dict | None = None) -> dict:
    """History stats — count/duration/ratio of `entity_id` in `state` over
    a period defined by (start, end) or (start, duration) or (end, duration).

    `type` — time | ratio | count
    `state` — the value to count (e.g. ``"on"``).
    """
    if type not in ("time", "ratio", "count"):
        raise ValueError("type must be time|ratio|count")
    bounds = sum(x is not None for x in (start, end, duration))
    if bounds != 2:
        raise ValueError("provide exactly two of start/end/duration")
    data: dict = {"name": name, "entity_id": entity_id, "state": state,
                    "type": type}
    if start is not None: data["start"] = start
    if end is not None: data["end"] = end
    if duration is not None: data["duration"] = duration
    return _create_helper(client, "history_stats", data)


def filter_create(client, *, name: str, entity_id: str,
                    filters: list[dict]) -> dict:
    """Filter sensor — apply low-pass/outlier/range/etc. to a source.

    `filters` — list of filter descriptors, e.g.
       ``[{"filter": "lowpass", "time_constant": 10}]``
    """
    if not filters:
        raise ValueError("filters list required")
    data = {"name": name, "entity_id": entity_id, "filters": list(filters)}
    return _create_helper(client, "filter", data)


def random_create(client, *, name: str,
                    minimum: int = 0, maximum: int = 20) -> dict:
    """Random integer sensor (re-rolled on demand or schedule)."""
    if maximum <= minimum:
        raise ValueError("maximum must be > minimum")
    return _create_helper(client, "random",
                            {"name": name, "minimum": minimum,
                             "maximum": maximum})


def template_create(client, *, name: str,
                      template_type: str = "sensor",
                      state: str | None = None,
                      device_class: str | None = None,
                      unit_of_measurement: str | None = None,
                      state_class: str | None = None,
                      **extra) -> dict:
    """Template helper.

    `template_type` — sensor | binary_sensor | button | switch | image |
                      number | select
    `state` — the Jinja template for the entity's state. Required for
    most types except button.

    Extra type-specific fields can be passed as kwargs (e.g.
    ``picture="..."`` for image, ``min=0, max=100`` for number).
    """
    valid_types = {"sensor", "binary_sensor", "button", "switch",
                   "image", "number", "select"}
    if template_type not in valid_types:
        raise ValueError(f"template_type must be one of {sorted(valid_types)}")
    if template_type != "button" and not state:
        raise ValueError(f"state template required for template_type={template_type!r}")
    data: dict = {"name": name, "template_type": template_type}
    if state is not None: data["state"] = state
    if device_class is not None: data["device_class"] = device_class
    if unit_of_measurement is not None: data["unit_of_measurement"] = unit_of_measurement
    if state_class is not None: data["state_class"] = state_class
    data.update(extra)
    return _create_helper(client, "template", data)


def group_create(client, *, name: str, entities: list[str],
                   group_type: str = "light",
                   all: bool = False,
                   hide_members: bool = False) -> dict:
    """Group helper — combine multiple entities of the same domain.

    `group_type` — light | switch | binary_sensor | sensor | cover |
                   fan | media_player | lock | notify | event
    `all` — if True, group is on only when all members are on
            (default: any member on)
    """
    valid = {"light", "switch", "binary_sensor", "sensor", "cover",
             "fan", "media_player", "lock", "notify", "event"}
    if group_type not in valid:
        raise ValueError(f"group_type must be one of {sorted(valid)}")
    if not entities:
        raise ValueError("entities required")
    data = {"name": name, "group_type": group_type,
              "entities": list(entities), "all": all,
              "hide_members": hide_members}
    return _create_helper(client, "group", data)


def generic_thermostat_create(client, *, name: str, heater: str,
                                target_sensor: str,
                                ac_mode: bool = False,
                                cold_tolerance: float = 0.3,
                                hot_tolerance: float = 0.3,
                                min_temp: float = 7.0,
                                max_temp: float = 35.0,
                                target_temp: float = 20.0) -> dict:
    """Generic thermostat — wraps a switch + temperature sensor into a
    climate entity."""
    data = {"name": name, "heater": heater, "target_sensor": target_sensor,
              "ac_mode": ac_mode, "cold_tolerance": cold_tolerance,
              "hot_tolerance": hot_tolerance,
              "min_temp": min_temp, "max_temp": max_temp,
              "target_temp": target_temp}
    return _create_helper(client, "generic_thermostat", data)


def generic_hygrostat_create(client, *, name: str, humidifier: str,
                               target_sensor: str,
                               device_class: str = "humidifier",
                               dry_tolerance: float = 3.0,
                               wet_tolerance: float = 3.0,
                               min_humidity: int = 30,
                               max_humidity: int = 99,
                               target_humidity: int = 50) -> dict:
    """Generic hygrostat — wraps a switch + humidity sensor into a
    humidifier entity. `device_class` is humidifier|dehumidifier."""
    if device_class not in ("humidifier", "dehumidifier"):
        raise ValueError("device_class must be humidifier|dehumidifier")
    data = {"name": name, "humidifier": humidifier,
              "target_sensor": target_sensor, "device_class": device_class,
              "dry_tolerance": dry_tolerance, "wet_tolerance": wet_tolerance,
              "min_humidity": min_humidity, "max_humidity": max_humidity,
              "target_humidity": target_humidity}
    return _create_helper(client, "generic_hygrostat", data)


def switch_as_x_create(client, *, name: str, entity_id: str,
                         target_domain: str) -> dict:
    """Re-expose a switch as another domain.

    `target_domain` — light | fan | lock | cover | siren | valve
    """
    valid = {"light", "fan", "lock", "cover", "siren", "valve"}
    if target_domain not in valid:
        raise ValueError(f"target_domain must be one of {sorted(valid)}")
    if not entity_id.startswith("switch."):
        raise ValueError("entity_id must be a switch.* entity_id")
    return _create_helper(client, "switch_as_x",
                            {"name": name, "entity_id": entity_id,
                             "target_domain": target_domain})


def tod_create(client, *, name: str,
                 after: str, before: str,
                 after_offset: dict | None = None,
                 before_offset: dict | None = None) -> dict:
    """Times-of-the-Day binary sensor — on during [after, before].

    `after`/`before` — ``"sunrise"``, ``"sunset"``, or ``"HH:MM:SS"``.
    """
    data: dict = {"name": name, "after": after, "before": before}
    if after_offset is not None: data["after_offset"] = after_offset
    if before_offset is not None: data["before_offset"] = before_offset
    return _create_helper(client, "tod", data)


def mold_indicator_create(client, *, name: str,
                            indoor_temp_sensor: str,
                            indoor_humidity_sensor: str,
                            outdoor_temp_sensor: str,
                            calibration_factor: float = 2.0) -> dict:
    """Mould Indicator — predicts wall surface mould risk from indoor +
    outdoor conditions."""
    data = {"name": name,
              "indoor_temp_sensor": indoor_temp_sensor,
              "indoor_humidity_sensor": indoor_humidity_sensor,
              "outdoor_temp_sensor": outdoor_temp_sensor,
              "calibration_factor": calibration_factor}
    return _create_helper(client, "mold_indicator", data)


# ════════════════════════════════════════════════════════════════════════
# Discovery — list every helper across all types
# ════════════════════════════════════════════════════════════════════════

# Storage-collection helpers (one WS list per domain).
HELPER_TYPES = (
    "input_boolean", "input_button", "input_datetime", "input_number",
    "input_select", "input_text", "counter", "timer", "schedule",
    "person", "zone", "tag",
)


def list_all_helpers(client, *, include_config_flow: bool = True) -> dict[str, list[dict]]:
    """Return ``{<type>: [<helper records>]}`` for every helper type.

    With `include_config_flow=True` (default), also enumerates config-flow
    helpers (derivative, utility_meter, template, etc.) by querying
    ``config_entries/get`` with ``type_filter=helper`` and grouping by
    domain.
    """
    out: dict[str, list[dict]] = {}
    for t in HELPER_TYPES:
        try:
            out[t] = _ws_collection(client, t, "list", payload={}) or []
        except Exception as e:
            out[t] = [{"_error": str(e)}]
    if include_config_flow:
        try:
            entries = config_entries_list(client, type_filter="helper") or []
        except Exception as e:
            for d in CONFIG_FLOW_HELPER_DOMAINS:
                out[d] = [{"_error": str(e)}]
        else:
            by_domain: dict[str, list[dict]] = {d: [] for d in CONFIG_FLOW_HELPER_DOMAINS}
            for entry in entries:
                d = entry.get("domain")
                if d in by_domain:
                    by_domain[d].append(entry)
                else:
                    by_domain.setdefault(d or "_unknown", []).append(entry)
            out.update(by_domain)
    return out
