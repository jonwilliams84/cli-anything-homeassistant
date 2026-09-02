"""Config-flow helper integrations — create / list / delete.

The "Helpers" page in HA has two completely different backends. The storage
helpers (`input_boolean`, `input_number`, `counter`, `timer`, …) are
WebSocket storage collections and live in `core/helpers.py`. The other
sixteen — derivative, Riemann integral, utility meter, min/max, threshold,
trend, statistics, history stats, random, template, group, generic
thermostat, generic hygrostat, switch-as-x, times-of-day and mould indicator
— are **config entries built by a config flow**, and that flow is only
reachable over REST:

  POST   /api/config/config_entries/flow            {"handler": "<domain>"}
  POST   /api/config/config_entries/flow/<flow_id>  <step user_input>
  DELETE /api/config/config_entries/flow/<flow_id>  (abort)
  DELETE /api/config/config_entries/entry/<entry_id>

There is **no** `config_entries/flow/init` or `config_entries/flow/configure`
WebSocket command (only `config_entries/flow/progress` and
`config_entries/flow/subscribe`), and no `config_entries/remove` either — all
three answer `unknown_command`. Listing IS a WS command
(`config_entries/get` with `type_filter: "helper"`).

Flow shapes, measured against HA 2025.1.4:

  single form step  derivative, integration, utility_meter, min_max,
                    threshold, generic_hygrostat, switch_as_x, tod,
                    mold_indicator
  two form steps    trend (user → settings), history_stats (user → options),
                    generic_thermostat (user → presets)
  three form steps  statistics (user → state_characteristic → options)
  menu then form    random, template, group — the first submission is
                    ``{"next_step_id": "<variant>"}``

Every step is validated against the form HA actually returned before it is
submitted, so an unknown field or a bad select value is named locally instead
of coming back as an opaque 400.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

_FLOW = "config/config_entries/flow"

#: Duration dicts accept these keys (HA's DurationSelector).
_DURATION_KEYS = {"hours", "minutes", "seconds", "days", "milliseconds"}

ZERO_DURATION = {"hours": 0, "minutes": 0, "seconds": 0}

# ── kind registry ───────────────────────────────────────────────────────────
# `kind` is the CLI-facing name; `domain` is HA's integration domain. They
# differ only for `riemann` (HA calls it `integration`, which is far too
# generic a word to put in a CLI).

KINDS: dict[str, dict[str, Any]] = {
    "derivative": {
        "domain": "derivative",
        "summary": "d/dt of a source sensor (e.g. energy → power).",
        "creates": "sensor",
        "steps": ["user"],
        "required": ["name", "source", "time_window"],
        "optional": ["unit_time", "round_digits", "unit_prefix"],
    },
    "riemann": {
        "domain": "integration",
        "summary": "Riemann-sum integral of a source sensor (power → energy).",
        "creates": "sensor",
        "steps": ["user"],
        "required": ["name", "source", "method", "unit_time"],
        "optional": ["round_digits", "unit_prefix", "max_sub_interval"],
    },
    "utility-meter": {
        "domain": "utility_meter",
        "summary": "Totaliser with optional cycle resets and tariffs.",
        "creates": "sensor (+ one per tariff)",
        "steps": ["user"],
        "required": ["name", "source", "cycle"],
        "optional": [
            "offset",
            "tariffs",
            "net_consumption",
            "delta_values",
            "periodically_resetting",
            "always_available",
        ],
    },
    "min-max": {
        "domain": "min_max",
        "summary": "Combine several numeric sensors (min/max/mean/median/…).",
        "creates": "sensor",
        "steps": ["user"],
        "required": ["name", "entity_ids", "type"],
        "optional": ["round_digits"],
    },
    "threshold": {
        "domain": "threshold",
        "summary": "Binary sensor that trips when a source crosses a bound.",
        "creates": "binary_sensor",
        "steps": ["user"],
        "required": ["name", "entity_id", "lower|upper"],
        "optional": ["hysteresis"],
    },
    "trend": {
        "domain": "trend",
        "summary": "Binary sensor that is on while a source is rising.",
        "creates": "binary_sensor",
        "steps": ["user", "settings"],
        "required": ["name", "entity_id"],
        "optional": ["attribute", "invert"],
        "options_only": ["max_samples", "min_samples", "min_gradient", "sample_duration"],
    },
    "statistics": {
        "domain": "statistics",
        "summary": "Rolling statistic over a window of a source's samples.",
        "creates": "sensor",
        "steps": ["user", "state_characteristic", "options"],
        "required": ["name", "entity_id", "state_characteristic"],
        "optional": ["sampling_size", "max_age", "keep_last_sample", "percentile", "precision"],
    },
    "history-stats": {
        "domain": "history_stats",
        "summary": "Time/count/ratio a source spent in given states.",
        "creates": "sensor",
        "steps": ["user", "options"],
        "required": ["name", "entity_id", "state", "type", "two of start/end/duration"],
        "optional": [],
    },
    "random": {
        "domain": "random",
        "summary": "Random sensor / binary_sensor (handy for testing).",
        "creates": "sensor | binary_sensor",
        "variants": ["sensor", "binary_sensor"],
        "steps": ["user(menu)", "<variant>"],
        "required": ["name"],
        "optional": ["minimum", "maximum", "device_class", "unit_of_measurement"],
    },
    "template": {
        "domain": "template",
        "summary": "Template-backed entity (sensor, switch, number, …).",
        "creates": "<variant>",
        "variants": [
            "alarm_control_panel",
            "binary_sensor",
            "button",
            "image",
            "number",
            "select",
            "sensor",
            "switch",
        ],
        "steps": ["user(menu)", "<variant>"],
        "required": ["name", "state (most variants)"],
        "optional": ["any field the variant's form offers, via fields=..."],
    },
    "group": {
        "domain": "group",
        "summary": "Group several entities of one domain into a single entity.",
        "creates": "<variant>",
        "variants": [
            "binary_sensor",
            "button",
            "cover",
            "event",
            "fan",
            "light",
            "lock",
            "media_player",
            "notify",
            "sensor",
            "switch",
        ],
        "steps": ["user(menu)", "<variant>"],
        "required": ["name", "entities"],
        "optional": ["hide_members", "all (binary_sensor only)", "type (sensor only)"],
    },
    "generic-thermostat": {
        "domain": "generic_thermostat",
        "summary": "Turn a switch + temperature sensor into a climate entity.",
        "creates": "climate",
        "steps": ["user", "presets"],
        "required": ["name", "heater", "target_sensor"],
        "optional": [
            "ac_mode",
            "cold_tolerance",
            "hot_tolerance",
            "min_cycle_duration",
            "min_temp",
            "max_temp",
            "presets",
        ],
    },
    "generic-hygrostat": {
        "domain": "generic_hygrostat",
        "summary": "Turn a switch + humidity sensor into a humidifier entity.",
        "creates": "humidifier",
        "steps": ["user"],
        "required": ["name", "humidifier", "target_sensor", "device_class"],
        "optional": ["dry_tolerance", "wet_tolerance", "min_cycle_duration"],
    },
    "switch-as-x": {
        "domain": "switch_as_x",
        "summary": "Re-expose a switch as a light / cover / lock / fan / …",
        "creates": "<target_domain>",
        "steps": ["user"],
        "required": ["entity_id", "target_domain"],
        "optional": ["invert"],
        "notes": "Takes NO name — the new entity inherits the switch's name.",
    },
    "tod": {
        "domain": "tod",
        "summary": "Binary sensor that is on between two times of day.",
        "creates": "binary_sensor",
        "steps": ["user"],
        "required": ["name", "after_time", "before_time"],
        "optional": [],
    },
    "mold-indicator": {
        "domain": "mold_indicator",
        "summary": "Estimate wall-surface mould risk from indoor/outdoor climate.",
        "creates": "sensor",
        "steps": ["user"],
        "required": [
            "name",
            "indoor_temp_sensor",
            "indoor_humidity_sensor",
            "outdoor_temp_sensor",
        ],
        "optional": ["calibration_factor"],
    },
}


def list_kinds() -> list[dict]:
    """Return one descriptor per supported helper kind."""
    return [{"kind": k, **v} for k, v in sorted(KINDS.items())]


def describe_kind(kind: str) -> dict:
    """Return the descriptor for one kind. Raises ValueError if unknown."""
    if kind not in KINDS:
        raise ValueError(f"unknown helper kind {kind!r} — try one of: {', '.join(sorted(KINDS))}")
    return {"kind": kind, **KINDS[kind]}


def kind_domain(kind: str) -> str:
    """Map a CLI kind name to HA's integration domain."""
    return describe_kind(kind)["domain"]


# ── flow plumbing ───────────────────────────────────────────────────────────


def _schema_fields(form: dict) -> list[dict]:
    schema = form.get("data_schema")
    return [f for f in schema if isinstance(f, dict)] if isinstance(schema, list) else []


def _select_options(field: dict) -> list[str] | None:
    selector = field.get("selector")
    if not isinstance(selector, dict) or "select" not in selector:
        return None
    options = (selector.get("select") or {}).get("options")
    if not isinstance(options, list):
        return None
    return [o.get("value") if isinstance(o, dict) else o for o in options]


def _validate_step(form: dict, user_input: dict) -> None:
    """Check `user_input` against the form HA just returned.

    HA answers a bad step with a bare 400 whose body is a nested `errors`
    dict; naming the problem here (with the valid values, which are often
    computed per-source and cannot be hardcoded) is far more useful.
    """
    fields = _schema_fields(form)
    if not fields:
        return
    names = {f.get("name") for f in fields}
    unknown = sorted(k for k in user_input if k not in names)
    if unknown:
        raise ValueError(
            f"step {form.get('step_id')!r} has no field(s) {', '.join(unknown)} — "
            f"it accepts: {', '.join(sorted(n for n in names if n))}"
        )
    missing = sorted(
        f["name"] for f in fields if f.get("required") and f.get("name") not in user_input
    )
    if missing:
        raise ValueError(
            f"step {form.get('step_id')!r} requires {', '.join(missing)} "
            f"(accepts: {', '.join(sorted(n for n in names if n))})"
        )
    for field in fields:
        options = _select_options(field)
        name = field.get("name")
        if not options or name not in user_input:
            continue
        value = user_input[name]
        values = value if isinstance(value, list) else [value]
        bad = [v for v in values if v not in options]
        if bad:
            raise ValueError(
                f"{name}={bad[0]!r} is not valid for this source — "
                f"valid values: {', '.join(str(o) for o in options)}"
            )


def _explain(exc: HomeAssistantError, domain: str, step_id: str | None) -> HomeAssistantError:
    """Turn HA's raw 4xx body into a sentence that names the field."""
    text = str(exc)
    body = text[text.find("{") :] if "{" in text else ""
    detail = ""
    try:
        parsed = json.loads(body) if body else {}
    except ValueError:
        parsed = {}
    errors = parsed.get("errors") if isinstance(parsed, dict) else None
    if isinstance(errors, dict):
        parts = []
        for key, value in errors.items():
            if isinstance(value, list):
                value = "; ".join(str(v) for v in value)
            parts.append(f"{key}: {value}")
        detail = " — ".join(parts)
    elif isinstance(parsed, dict) and parsed.get("message"):
        detail = str(parsed["message"])
    where = f"{domain} step {step_id!r}" if step_id else domain
    if "Invalid handler specified" in detail:
        detail += (
            f" (this HA build has no config flow for {domain!r}; "
            "check `config-flow handlers`)"
        )
    return HomeAssistantError(f"{where} rejected: {detail or text}")


def flow_abort(client, flow_id: str) -> None:
    """Best-effort abort so a failed walk leaves no dangling flow behind."""
    try:
        client.delete(f"{_FLOW}/{flow_id}")
    except HomeAssistantError as exc:  # pragma: no cover - diagnostic only
        _LOGGER.debug("aborting flow %s failed: %s", flow_id, exc)


def walk_flow(client, domain: str, steps: list[dict], *, validate: bool = True) -> dict:
    """Init a config flow for `domain` and submit each step in `steps`.

    Returns HA's final response. Raises HomeAssistantError if the flow ends
    on anything other than ``create_entry`` (and aborts the flow first, so a
    failed attempt does not linger in `config-flow progress`).
    """
    if not domain:
        raise ValueError("domain required")
    if not isinstance(steps, list) or not steps:
        raise ValueError("steps must be a non-empty list of user_input dicts")
    try:
        form = client.post(_FLOW, {"handler": domain})
    except HomeAssistantError as exc:
        raise _explain(exc, domain, None) from exc
    flow_id = form.get("flow_id")
    if not flow_id:
        raise HomeAssistantError(f"{domain}: flow did not start: {form!r}")
    for user_input in steps:
        if not isinstance(user_input, dict):
            flow_abort(client, flow_id)
            raise ValueError("each step must be a dict of user_input")
        if form.get("type") == "menu":
            choice = user_input.get("next_step_id")
            menu = form.get("menu_options") or []
            if choice not in menu:
                flow_abort(client, flow_id)
                raise ValueError(
                    f"{domain} is a menu flow — next_step_id must be one of: {', '.join(menu)}"
                )
        elif validate:
            try:
                _validate_step(form, user_input)
            except ValueError:
                flow_abort(client, flow_id)
                raise
        try:
            form = client.post(f"{_FLOW}/{flow_id}", user_input)
        except HomeAssistantError as exc:
            step_id = form.get("step_id")
            flow_abort(client, flow_id)
            raise _explain(exc, domain, step_id) from exc
    if form.get("type") != "create_entry":
        step_id = form.get("step_id")
        reason = form.get("reason") or form.get("errors")
        flow_abort(client, flow_id)
        raise HomeAssistantError(
            f"{domain}: flow stopped at step {step_id!r} (type={form.get('type')!r}"
            + (f", reason={reason!r}" if reason else "")
            + ") — more steps are needed than were supplied"
        )
    return form


def helper_entities(client, entry_id: str, *, wait: float = 5.0, interval: float = 0.25) -> list[str]:
    """Entity ids the config entry `entry_id` produced.

    A helper's entity is registered a moment after `create_entry` returns, so
    this polls the entity registry for up to `wait` seconds. Pass ``wait=0``
    to read once.
    """
    if not entry_id:
        raise ValueError("entry_id required")
    deadline = time.monotonic() + max(wait, 0.0)
    while True:
        entries = client.ws_call("config/entity_registry/list")
        found = [
            e.get("entity_id")
            for e in (entries if isinstance(entries, list) else [])
            if e.get("config_entry_id") == entry_id and e.get("entity_id")
        ]
        if found or time.monotonic() >= deadline:
            return sorted(found)
        time.sleep(interval)


def _finish(
    client,
    kind: str,
    domain: str,
    result: dict,
    *,
    resolve: bool = True,
    wait: float = 5.0,
) -> dict:
    entry = result.get("result") or {}
    out = {
        "created": True,
        "kind": kind,
        "domain": domain,
        "entry_id": entry.get("entry_id"),
        "title": result.get("title") or entry.get("title"),
        "state": entry.get("state"),
    }
    if resolve and out["entry_id"]:
        out["entities"] = helper_entities(client, out["entry_id"], wait=wait)
    return out


def _create(
    client,
    kind: str,
    steps: list[dict],
    *,
    options: dict | None = None,
    resolve: bool = True,
    wait: float = 5.0,
) -> dict:
    domain = kind_domain(kind)
    result = walk_flow(client, domain, steps)
    out = _finish(client, kind, domain, result, resolve=resolve, wait=wait)
    if options:
        out["options"] = set_helper_options(client, out["entry_id"], options)
        out["options_applied"] = True
    return out


# ── shared field helpers ────────────────────────────────────────────────────


def _require(name: str, value) -> None:
    if value in (None, "", []):
        raise ValueError(f"{name} required")


def _duration(value, field: str) -> dict:
    if isinstance(value, dict):
        bad = sorted(set(value) - _DURATION_KEYS)
        if bad:
            raise ValueError(
                f"{field}: unknown duration key(s) {', '.join(bad)} — "
                f"use {', '.join(sorted(_DURATION_KEYS))}"
            )
        return value
    if isinstance(value, (int, float)):
        return {"hours": 0, "minutes": 0, "seconds": value}
    raise ValueError(f"{field} must be a duration dict or a number of seconds")


# ── typed creators ──────────────────────────────────────────────────────────


def create_derivative(
    client,
    *,
    name: str,
    source: str,
    time_window: dict | float | None = None,
    unit_time: str = "h",
    round_digits: int = 2,
    unit_prefix: str | None = None,
    resolve: bool = True,
    wait: float = 5.0,
) -> dict:
    """Derivative sensor — the rate of change of `source`.

    `time_window` is REQUIRED by HA (a zero duration, the default here, means
    no smoothing). `unit_prefix` is one of n µ m k M G T P.
    """
    _require("name", name)
    _require("source", source)
    step = {
        "name": name,
        "source": source,
        "round": round_digits,
        "time_window": _duration(
            ZERO_DURATION if time_window is None else time_window, "time_window"
        ),
        "unit_time": unit_time,
    }
    if unit_prefix is not None:
        step["unit_prefix"] = unit_prefix
    return _create(client, "derivative", [step], resolve=resolve, wait=wait)


def create_riemann(
    client,
    *,
    name: str,
    source: str,
    method: str = "trapezoidal",
    unit_time: str = "h",
    round_digits: int | None = 2,
    unit_prefix: str | None = None,
    max_sub_interval: dict | float | None = None,
    resolve: bool = True,
    wait: float = 5.0,
) -> dict:
    """Riemann-sum integral sensor (HA domain `integration`)."""
    _require("name", name)
    _require("source", source)
    step: dict[str, Any] = {
        "name": name,
        "source": source,
        "method": method,
        "unit_time": unit_time,
    }
    if round_digits is not None:
        step["round"] = round_digits
    if unit_prefix is not None:
        step["unit_prefix"] = unit_prefix
    if max_sub_interval is not None:
        step["max_sub_interval"] = _duration(max_sub_interval, "max_sub_interval")
    return _create(client, "riemann", [step], resolve=resolve, wait=wait)


def create_utility_meter(
    client,
    *,
    name: str,
    source: str,
    cycle: str = "none",
    offset: int = 0,
    tariffs: list[str] | None = None,
    net_consumption: bool = False,
    delta_values: bool = False,
    periodically_resetting: bool = True,
    always_available: bool | None = None,
    resolve: bool = True,
    wait: float = 5.0,
) -> dict:
    """Utility meter — a totaliser that can reset on a cycle."""
    _require("name", name)
    _require("source", source)
    step: dict[str, Any] = {
        "name": name,
        "source": source,
        "cycle": cycle,
        "offset": offset,
        "tariffs": list(tariffs or []),
        "net_consumption": net_consumption,
        "delta_values": delta_values,
        "periodically_resetting": periodically_resetting,
    }
    if always_available is not None:
        step["always_available"] = always_available
    return _create(client, "utility-meter", [step], resolve=resolve, wait=wait)


def create_min_max(
    client,
    *,
    name: str,
    entity_ids: list[str],
    type: str = "mean",
    round_digits: int = 2,
    resolve: bool = True,
    wait: float = 5.0,
) -> dict:
    """Min/max/mean/median/last/range/sum over several sensors."""
    _require("name", name)
    if not entity_ids:
        raise ValueError("entity_ids must be a non-empty list")
    step = {
        "name": name,
        "entity_ids": list(entity_ids),
        "type": type,
        "round_digits": round_digits,
    }
    return _create(client, "min-max", [step], resolve=resolve, wait=wait)


def create_threshold(
    client,
    *,
    name: str,
    entity_id: str,
    lower: float | None = None,
    upper: float | None = None,
    hysteresis: float = 0.0,
    resolve: bool = True,
    wait: float = 5.0,
) -> dict:
    """Threshold binary sensor — on while the source is past a bound."""
    _require("name", name)
    _require("entity_id", entity_id)
    if lower is None and upper is None:
        raise ValueError("at least one of lower/upper required")
    step: dict[str, Any] = {"name": name, "entity_id": entity_id, "hysteresis": hysteresis}
    if lower is not None:
        step["lower"] = lower
    if upper is not None:
        step["upper"] = upper
    return _create(client, "threshold", [step], resolve=resolve, wait=wait)


def create_trend(
    client,
    *,
    name: str,
    entity_id: str,
    attribute: str | None = None,
    invert: bool = False,
    max_samples: int | None = None,
    min_samples: int | None = None,
    min_gradient: float | None = None,
    sample_duration: int | None = None,
    resolve: bool = True,
    wait: float = 5.0,
) -> dict:
    """Trend binary sensor — on while the source is rising (or falling).

    HA's CONFIG flow only offers `attribute` and `invert`; the sample-window
    tuning (`max_samples`, `min_samples`, `min_gradient`, `sample_duration`)
    exists solely in the OPTIONS flow, so it is applied here as a second call
    once the entry exists.
    """
    _require("name", name)
    _require("entity_id", entity_id)
    settings: dict[str, Any] = {"invert": invert}
    if attribute is not None:
        settings["attribute"] = attribute
    tuning = {
        "max_samples": max_samples,
        "min_samples": min_samples,
        "min_gradient": min_gradient,
        "sample_duration": sample_duration,
    }
    tuning = {k: v for k, v in tuning.items() if v is not None}
    options = None
    if tuning:
        options = {**settings, **tuning}
    return _create(
        client,
        "trend",
        [{"name": name, "entity_id": entity_id}, settings],
        options=options,
        resolve=resolve,
        wait=wait,
    )


def create_statistics(
    client,
    *,
    name: str,
    entity_id: str,
    state_characteristic: str = "mean",
    sampling_size: int | None = 20,
    max_age: dict | float | None = None,
    keep_last_sample: bool | None = None,
    percentile: int | None = None,
    precision: int | None = 2,
    resolve: bool = True,
    wait: float = 5.0,
) -> dict:
    """Statistics sensor — a rolling characteristic of a source's samples.

    Which `state_characteristic` values are legal depends on the source's
    domain (a binary_sensor offers count_on/count_off, a numeric sensor
    offers mean/median/…), so the value is checked against the form HA
    returns rather than a hardcoded list.
    """
    _require("name", name)
    _require("entity_id", entity_id)
    options: dict[str, Any] = {}
    if sampling_size is not None:
        options["sampling_size"] = sampling_size
    if max_age is not None:
        options["max_age"] = _duration(max_age, "max_age")
    if keep_last_sample is not None:
        options["keep_last_sample"] = keep_last_sample
    if percentile is not None:
        options["percentile"] = percentile
    if precision is not None:
        options["precision"] = precision
    return _create(
        client,
        "statistics",
        [
            {"name": name, "entity_id": entity_id},
            {"state_characteristic": state_characteristic},
            options,
        ],
        resolve=resolve,
        wait=wait,
    )


def create_history_stats(
    client,
    *,
    name: str,
    entity_id: str,
    state: list[str] | str,
    type: str = "time",
    start: str | None = None,
    end: str | None = None,
    duration: dict | float | None = None,
    resolve: bool = True,
    wait: float = 5.0,
) -> dict:
    """History-stats sensor — time / ratio / count in the given state(s).

    `state` is a LIST on the wire even for a single value (HA answers a bare
    string with ``{"state": "Value should be a list"}``); a string is wrapped
    here. Exactly two of start/end/duration must be given.
    """
    _require("name", name)
    _require("entity_id", entity_id)
    _require("state", state)
    states = [state] if isinstance(state, str) else list(state)
    bounds = {"start": start, "end": end, "duration": duration}
    given = {k: v for k, v in bounds.items() if v is not None}
    if len(given) != 2:
        raise ValueError(
            "provide exactly two of start/end/duration "
            f"(got {', '.join(sorted(given)) or 'none'})"
        )
    if "duration" in given:
        given["duration"] = _duration(given["duration"], "duration")
    return _create(
        client,
        "history-stats",
        [
            {"name": name, "entity_id": entity_id, "state": states, "type": type},
            given,
        ],
        resolve=resolve,
        wait=wait,
    )


def create_random(
    client,
    *,
    name: str,
    variant: str = "sensor",
    minimum: int | None = None,
    maximum: int | None = None,
    device_class: str | None = None,
    unit_of_measurement: str | None = None,
    resolve: bool = True,
    wait: float = 5.0,
) -> dict:
    """Random sensor / binary_sensor — a menu flow."""
    _require("name", name)
    if variant not in ("sensor", "binary_sensor"):
        raise ValueError("variant must be sensor|binary_sensor")
    step: dict[str, Any] = {"name": name}
    if variant == "sensor":
        if minimum is not None:
            step["minimum"] = minimum
        if maximum is not None:
            step["maximum"] = maximum
        if unit_of_measurement is not None:
            step["unit_of_measurement"] = unit_of_measurement
    elif minimum is not None or maximum is not None or unit_of_measurement is not None:
        raise ValueError("minimum/maximum/unit_of_measurement apply to variant=sensor only")
    if device_class is not None:
        step["device_class"] = device_class
    if minimum is not None and maximum is not None and maximum <= minimum:
        raise ValueError("maximum must be greater than minimum")
    return _create(
        client, "random", [{"next_step_id": variant}, step], resolve=resolve, wait=wait
    )


def create_template(
    client,
    *,
    name: str,
    variant: str = "sensor",
    state: str | None = None,
    unit_of_measurement: str | None = None,
    device_class: str | None = None,
    state_class: str | None = None,
    fields: dict | None = None,
    resolve: bool = True,
    wait: float = 5.0,
) -> dict:
    """Template helper — a menu flow, one form per entity type.

    Variant-specific fields (image `url`, number `min`/`max`/`set_value`,
    select `options`, switch `turn_on`/`turn_off`, …) go through `fields`;
    they are validated against the form HA returns for that variant.
    """
    _require("name", name)
    variants = KINDS["template"]["variants"]
    if variant not in variants:
        raise ValueError(f"variant must be one of: {', '.join(variants)}")
    step: dict[str, Any] = {"name": name}
    if state is not None:
        step["state"] = state
    if unit_of_measurement is not None:
        step["unit_of_measurement"] = unit_of_measurement
    if device_class is not None:
        step["device_class"] = device_class
    if state_class is not None:
        step["state_class"] = state_class
    step.update(fields or {})
    return _create(
        client, "template", [{"next_step_id": variant}, step], resolve=resolve, wait=wait
    )


def create_group(
    client,
    *,
    name: str,
    entities: list[str],
    variant: str = "light",
    hide_members: bool = False,
    all: bool | None = None,
    type: str | None = None,
    resolve: bool = True,
    wait: float = 5.0,
) -> dict:
    """Group helper — a menu flow, one form per grouped domain.

    `all` is only offered on the binary_sensor form and `type` (the
    aggregation) only on the sensor form; passing either elsewhere is
    refused before the request goes out.
    """
    _require("name", name)
    if not entities:
        raise ValueError("entities must be a non-empty list")
    variants = KINDS["group"]["variants"]
    if variant not in variants:
        raise ValueError(f"variant must be one of: {', '.join(variants)}")
    if all is not None and variant != "binary_sensor":
        raise ValueError("`all` is only accepted for variant=binary_sensor")
    if type is not None and variant != "sensor":
        raise ValueError("`type` (aggregation) is only accepted for variant=sensor")
    step: dict[str, Any] = {
        "name": name,
        "entities": list(entities),
        "hide_members": hide_members,
    }
    if all is not None:
        step["all"] = all
    if type is not None:
        step["type"] = type
    return _create(
        client, "group", [{"next_step_id": variant}, step], resolve=resolve, wait=wait
    )


def create_generic_thermostat(
    client,
    *,
    name: str,
    heater: str,
    target_sensor: str,
    ac_mode: bool = False,
    cold_tolerance: float = 0.3,
    hot_tolerance: float = 0.3,
    min_cycle_duration: dict | float | None = None,
    min_temp: float | None = None,
    max_temp: float | None = None,
    presets: dict | None = None,
    resolve: bool = True,
    wait: float = 5.0,
) -> dict:
    """Generic thermostat — switch + temperature sensor → climate entity.

    Two steps; the second (`presets`) is optional and takes per-preset
    temperatures (`away_temp`, `comfort_temp`, `eco_temp`, `home_temp`,
    `sleep_temp`, `activity_temp`). The target temperature itself is not part
    of the config flow — set it afterwards with `climate set-temperature`.
    """
    _require("name", name)
    _require("heater", heater)
    _require("target_sensor", target_sensor)
    step: dict[str, Any] = {
        "name": name,
        "heater": heater,
        "target_sensor": target_sensor,
        "ac_mode": ac_mode,
        "cold_tolerance": cold_tolerance,
        "hot_tolerance": hot_tolerance,
    }
    if min_cycle_duration is not None:
        step["min_cycle_duration"] = _duration(min_cycle_duration, "min_cycle_duration")
    if min_temp is not None:
        step["min_temp"] = min_temp
    if max_temp is not None:
        step["max_temp"] = max_temp
    return _create(
        client,
        "generic-thermostat",
        [step, dict(presets or {})],
        resolve=resolve,
        wait=wait,
    )


def create_generic_hygrostat(
    client,
    *,
    name: str,
    humidifier: str,
    target_sensor: str,
    device_class: str = "humidifier",
    dry_tolerance: float = 3.0,
    wet_tolerance: float = 3.0,
    min_cycle_duration: dict | float | None = None,
    resolve: bool = True,
    wait: float = 5.0,
) -> dict:
    """Generic hygrostat — switch + humidity sensor → humidifier entity.

    The humidity limits (`min_humidity` / `max_humidity` / `target_humidity`)
    are options-flow only; set them with `helpers set-options` after
    creation.
    """
    _require("name", name)
    _require("humidifier", humidifier)
    _require("target_sensor", target_sensor)
    step: dict[str, Any] = {
        "name": name,
        "humidifier": humidifier,
        "target_sensor": target_sensor,
        "device_class": device_class,
        "dry_tolerance": dry_tolerance,
        "wet_tolerance": wet_tolerance,
    }
    if min_cycle_duration is not None:
        step["min_cycle_duration"] = _duration(min_cycle_duration, "min_cycle_duration")
    return _create(client, "generic-hygrostat", [step], resolve=resolve, wait=wait)


def create_switch_as_x(
    client,
    *,
    entity_id: str,
    target_domain: str,
    invert: bool = False,
    resolve: bool = True,
    wait: float = 5.0,
) -> dict:
    """Re-expose a switch as another domain.

    There is deliberately no `name` — the form has no such field (sending one
    is refused with `extra keys not allowed`) and the new entity inherits the
    source switch's name and object id.
    """
    _require("entity_id", entity_id)
    _require("target_domain", target_domain)
    if not entity_id.startswith("switch."):
        raise ValueError("entity_id must be a switch.* entity")
    step = {"entity_id": entity_id, "target_domain": target_domain, "invert": invert}
    return _create(client, "switch-as-x", [step], resolve=resolve, wait=wait)


def create_tod(
    client,
    *,
    name: str,
    after_time: str,
    before_time: str,
    resolve: bool = True,
    wait: float = 5.0,
) -> dict:
    """Times-of-day binary sensor — on between two times.

    The fields are `after_time` / `before_time` (HH:MM:SS), not after/before.
    """
    _require("name", name)
    _require("after_time", after_time)
    _require("before_time", before_time)
    step = {"name": name, "after_time": after_time, "before_time": before_time}
    return _create(client, "tod", [step], resolve=resolve, wait=wait)


def create_mold_indicator(
    client,
    *,
    name: str,
    indoor_temp_sensor: str,
    indoor_humidity_sensor: str,
    outdoor_temp_sensor: str,
    calibration_factor: float = 2.0,
    resolve: bool = True,
    wait: float = 5.0,
) -> dict:
    """Mould indicator — indoor/outdoor climate → estimated surface humidity."""
    _require("name", name)
    _require("indoor_temp_sensor", indoor_temp_sensor)
    _require("indoor_humidity_sensor", indoor_humidity_sensor)
    _require("outdoor_temp_sensor", outdoor_temp_sensor)
    step = {
        "name": name,
        "indoor_temp_sensor": indoor_temp_sensor,
        "indoor_humidity_sensor": indoor_humidity_sensor,
        "outdoor_temp_sensor": outdoor_temp_sensor,
        "calibration_factor": calibration_factor,
    }
    return _create(client, "mold-indicator", [step], resolve=resolve, wait=wait)


def create_raw(
    client,
    domain: str,
    steps: list[dict],
    *,
    resolve: bool = True,
    wait: float = 5.0,
) -> dict:
    """Escape hatch: drive any helper flow with explicit per-step payloads.

    Use this for a helper this build of HA has but this harness does not know
    about (`filter` gained a config flow after 2025.1, for instance).
    """
    result = walk_flow(client, domain, steps)
    return _finish(client, domain, domain, result, resolve=resolve, wait=wait)


# ── lifecycle ───────────────────────────────────────────────────────────────


def list_helpers(client, *, domain: str | None = None) -> list[dict]:
    """Every config-entry-backed helper (`config_entries/get`, helper filter)."""
    payload: dict[str, Any] = {"type_filter": "helper"}
    if domain:
        payload["domain"] = domain
    entries = client.ws_call("config_entries/get", payload)
    if not isinstance(entries, list):
        return []
    if domain:
        entries = [e for e in entries if e.get("domain") == domain]
    return entries


def get_helper(client, entry_id: str) -> dict | None:
    """One helper entry by id, or None."""
    if not entry_id:
        raise ValueError("entry_id required")
    for entry in list_helpers(client):
        if entry.get("entry_id") == entry_id:
            return entry
    return None


def delete_helper(client, entry_id: str) -> dict:
    """Delete a helper config entry.

    REST only — `config_entries/remove` is not a WebSocket command.
    """
    if not entry_id:
        raise ValueError("entry_id required")
    return client.delete(f"config/config_entries/entry/{entry_id}")


def set_helper_options(client, entry_id: str, user_input: dict) -> dict:
    """Run a helper's single-step options flow with `user_input`."""
    if not entry_id:
        raise ValueError("entry_id required")
    if not isinstance(user_input, dict) or not user_input:
        raise ValueError("user_input must be a non-empty dict")
    init = client.post("config/config_entries/options/flow", {"handler": entry_id})
    flow_id = init.get("flow_id")
    if not flow_id:
        raise HomeAssistantError(f"options flow did not start for {entry_id}: {init!r}")
    try:
        return client.post(f"config/config_entries/options/flow/{flow_id}", user_input)
    except HomeAssistantError as exc:
        try:
            client.delete(f"config/config_entries/options/flow/{flow_id}")
        except HomeAssistantError as abort_exc:  # pragma: no cover - diagnostic only
            _LOGGER.debug("aborting options flow %s failed: %s", flow_id, abort_exc)
        raise _explain(exc, entry_id, init.get("step_id")) from exc
