"""Powercalc calibration + audit helpers.

Three workflows on top of the existing powercalc safety wrappers:

* :func:`audit` — passive comparison. Reads ``hours`` of history for the
  smart-meter and the ``Power · Home Total`` rollup; computes the gap and
  ranks the top-level Power · groups by contribution. The output points
  you at the biggest mis-modelled chunks without you needing to flip a
  switch.

* :func:`calibrate` — active single-shot for fixed-power devices.
  Take a baseline reading from the smart meter, trigger a service call
  to put the device under load, wait for stabilisation, take a load
  reading, compute delta. With ``apply=True`` writes the delta into the
  powercalc entry's fixed power via :func:`powercalc.set_fixed_power`.
  Optionally fires a teardown service to leave the device in its
  starting state.

* :func:`calibrate_template` — active multi-step for variable devices
  (variable-speed fans, dimmable lights, multi-mode climate). Walks the
  device through a list of states, measures delta per state, fits a
  piecewise power_template, and optionally writes it via
  :func:`powercalc.set_power_template`.

All three rely on a single ``smart_meter`` sensor (default
``sensor.smart_meter_electricity_power``) as the source of truth. If the
caller's setup uses a different name they pass it explicitly.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

from cli_anything.homeassistant.core import powercalc as _pc


DEFAULT_SMART_METER = "sensor.smart_meter_electricity_power"
DEFAULT_HOME_TOTAL = "sensor.power_home_total_power"


# ── helpers ────────────────────────────────────────────────────────────────

def _read_power(client, entity_id: str) -> float | None:
    """Read a sensor and return its float state, or None on failure."""
    try:
        s = client.get(f"states/{entity_id}")
    except Exception:
        return None
    if not isinstance(s, dict):
        return None
    try:
        return float(s["state"])
    except (KeyError, ValueError, TypeError):
        return None


def _measure(
    client,
    entity_id: str,
    *,
    duration_seconds: float,
    samples: int = 6,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Sample ``entity_id`` ``samples`` times over ``duration_seconds``.

    Returns ``{n, mean, min, max, raw}`` where mean is the simple average
    of the successful reads. (Time-weighted averaging would matter at
    higher sample rates; here we're polling every few seconds.)
    """
    if samples < 1:
        raise ValueError("samples must be >= 1")
    delay = (duration_seconds / max(samples - 1, 1)) if samples > 1 else 0
    raw: list[float] = []
    for i in range(samples):
        v = _read_power(client, entity_id)
        if v is not None:
            raw.append(v)
        if i < samples - 1 and delay > 0:
            sleep(delay)
    if not raw:
        raise RuntimeError(
            f"got no usable readings from {entity_id!r} over {duration_seconds}s"
        )
    return {
        "n": len(raw),
        "mean": sum(raw) / len(raw),
        "min": min(raw),
        "max": max(raw),
        "raw": raw,
    }


def _history_series(
    client,
    entity_id: str,
    *,
    hours: float,
) -> list[dict]:
    """Fetch raw history points for ``entity_id`` over the last ``hours``."""
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(hours=hours)
    raw = client.get(
        f"history/period/{start.isoformat()}",
        params={
            "filter_entity_id": entity_id,
            "end_time": end.isoformat(),
            "minimal_response": "true",
        },
    )
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return raw[0]
    return []


def _time_weighted_mean(points: list[dict]) -> dict:
    """Compute time-weighted mean from a history-period series.

    Each point's state is assumed to hold from its ``last_changed`` up to
    the next point's ``last_changed``. Final point holds to now (we use
    last - first as the total span).
    """
    if not points:
        return {"n": 0, "mean": None, "min": None, "max": None,
                "first": None, "last": None}

    parsed: list[tuple[datetime, float]] = []
    for p in points:
        try:
            ts = datetime.fromisoformat(
                p["last_changed"].replace("Z", "+00:00")
            )
            v = float(p["state"])
        except (KeyError, ValueError, TypeError):
            continue
        parsed.append((ts, v))

    if not parsed:
        return {"n": 0, "mean": None, "min": None, "max": None,
                "first": None, "last": None}

    total_span = (parsed[-1][0] - parsed[0][0]).total_seconds()
    if total_span <= 0:
        return {"n": len(parsed),
                "mean": parsed[-1][1],
                "min": min(v for _, v in parsed),
                "max": max(v for _, v in parsed),
                "first": parsed[0][0].isoformat(),
                "last": parsed[-1][0].isoformat()}

    weighted_sum = 0.0
    for i in range(len(parsed) - 1):
        dt = (parsed[i + 1][0] - parsed[i][0]).total_seconds()
        weighted_sum += parsed[i][1] * dt

    return {
        "n": len(parsed),
        "mean": weighted_sum / total_span,
        "min": min(v for _, v in parsed),
        "max": max(v for _, v in parsed),
        "first": parsed[0][0].isoformat(),
        "last": parsed[-1][0].isoformat(),
    }


def _call_service(
    client,
    service: str,
    *,
    target: str | dict | None = None,
    service_data: dict | None = None,
) -> Any:
    """Helper: POST services/<domain>/<svc> with the supplied payload."""
    if "." not in service:
        raise ValueError(
            f"service must be 'domain.name' (got {service!r})"
        )
    domain, name = service.split(".", 1)
    payload: dict = {}
    if isinstance(target, dict):
        payload.update(target)
    elif isinstance(target, str):
        payload["entity_id"] = target
    if service_data:
        payload.update(service_data)
    return client.post(f"services/{domain}/{name}", payload)


# ── audit ─────────────────────────────────────────────────────────────────

def audit(
    client,
    *,
    smart_meter: str = DEFAULT_SMART_METER,
    home_total: str = DEFAULT_HOME_TOTAL,
    hours: float = 24,
    top_n: int = 8,
) -> dict:
    """Passive coverage report — smart-meter vs powercalc Home Total
    over the last ``hours``.

    Also ranks every powercalc group (``title`` starting with ``"Power · "``)
    by its time-weighted mean over the window. Biggest groups deserve the
    most calibration attention.

    Returns::

        {
          "window_hours": float,
          "smart_meter": {"n", "mean", "min", "max", "first", "last"},
          "home_total": {"n", "mean", "min", "max", "first", "last"},
          "delta_mean": float,             # smart_meter - home_total
          "coverage_ratio": float,         # home_total / smart_meter (0..1+)
          "groups": [
            {"title", "entity_id", "mean", "min", "max",
             "contribution_pct"},  # contribution_pct = mean / sum(group means)
            ...
          ][:top_n],
        }
    """
    sm = _time_weighted_mean(_history_series(client, smart_meter, hours=hours))
    ht = _time_weighted_mean(_history_series(client, home_total, hours=hours))

    # Find every Power · group via the powercalc entry list and resolve its
    # power sensor (the entry's title maps to the friendly_name of the
    # sensor; HA slug-derives the entity_id).
    entries = _pc.list_entries(client, title_contains="Power · ")
    # Filter to entries whose state is loaded — non-loaded groups have
    # no live sensor.
    group_results: list[dict] = []
    for e in entries:
        title = e.get("title") or ""
        if not title.startswith("Power · "):
            continue
        # Power sensor entity_id follows from title slug: "Power · Lounge"
        # → sensor.power_lounge_power
        slug = title.replace("Power · ", "Power ").lower()
        # Strip non-alphanum to slug
        eid_core = "".join(c if c.isalnum() else "_" for c in slug)
        # Collapse repeated underscores and trim
        while "__" in eid_core:
            eid_core = eid_core.replace("__", "_")
        eid_core = eid_core.strip("_")
        candidate = f"sensor.{eid_core}_power"
        stats = _time_weighted_mean(
            _history_series(client, candidate, hours=hours)
        )
        if stats.get("mean") is None:
            continue
        # Skip the Home Total itself in the per-group ranking.
        if candidate == home_total:
            continue
        group_results.append({
            "title": title,
            "entity_id": candidate,
            "mean": round(stats["mean"], 1),
            "min": stats["min"],
            "max": stats["max"],
        })

    # Compute contribution percentages
    group_results.sort(key=lambda r: -(r["mean"] or 0))
    total_mean = sum(r["mean"] or 0 for r in group_results) or 1
    for r in group_results:
        r["contribution_pct"] = round(100.0 * (r["mean"] or 0) / total_mean, 1)

    delta_mean = None
    coverage = None
    if sm["mean"] is not None and ht["mean"] is not None:
        delta_mean = round(sm["mean"] - ht["mean"], 1)
        coverage = round(ht["mean"] / sm["mean"], 3) if sm["mean"] else None

    return {
        "window_hours": hours,
        "smart_meter": sm,
        "home_total": ht,
        "delta_mean": delta_mean,
        "coverage_ratio": coverage,
        "groups": group_results[:top_n],
    }


# ── calibrate (single-shot, fixed-power) ──────────────────────────────────

def calibrate(
    client,
    entry_id: str,
    *,
    service_on: str,
    target: str | dict,
    smart_meter: str = DEFAULT_SMART_METER,
    baseline_seconds: float = 30,
    stabilisation_seconds: float = 10,
    load_seconds: float = 30,
    samples: int = 6,
    service_off: str | None = None,
    apply_: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Active single-shot calibration for a fixed-power device.

    Sequence:
      1. Read ``baseline_seconds`` of smart-meter samples (device assumed
         in baseline state — typically OFF).
      2. Call ``service_on`` with ``target``.
      3. Sleep ``stabilisation_seconds``.
      4. Read ``load_seconds`` of smart-meter samples.
      5. delta = load.mean − baseline.mean
      6. If ``service_off`` given, fire it (returns device to baseline).
      7. If ``apply=True`` and delta > 0, call
         :func:`powercalc.set_fixed_power(entry_id, delta)`.

    Returns a result dict with baseline/load means, the delta, the
    entry's previous fixed power (when discoverable), and an ``applied``
    flag.
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    if not service_on:
        raise ValueError("service_on is required")

    baseline = _measure(client, smart_meter,
                        duration_seconds=baseline_seconds,
                        samples=samples, sleep=sleep)

    _call_service(client, service_on, target=target)
    if stabilisation_seconds > 0:
        sleep(stabilisation_seconds)

    load = _measure(client, smart_meter,
                    duration_seconds=load_seconds,
                    samples=samples, sleep=sleep)

    delta_w = round(load["mean"] - baseline["mean"], 1)

    # Discover previous fixed power on the entry (best-effort).
    previous: float | None = None
    for e in _pc.list_entries(client):
        if e.get("entry_id") == entry_id:
            opts = e.get("options") or {}
            data = e.get("data") or {}
            previous = opts.get("power") or data.get("power")
            break

    if service_off:
        try:
            _call_service(client, service_off, target=target)
        except Exception:
            pass

    applied = False
    if apply_ and delta_w > 0:
        _pc.set_fixed_power(client, entry_id, power=delta_w)
        applied = True

    return {
        "entry_id": entry_id,
        "smart_meter": smart_meter,
        "baseline": baseline,
        "load": load,
        "delta_w": delta_w,
        "previous_fixed_power": previous,
        "applied": applied,
        "service_on": service_on,
        "service_off": service_off,
    }


# ── calibrate-template (multi-step, variable) ─────────────────────────────

def _state_template(source_entity: str, attribute: str,
                    state_value_to_power: list[tuple]) -> str:
    """Build a piecewise Jinja template from sorted ``(value, watts)`` pairs.

    Output looks like::

        {% set v = state_attr('fan.x', 'percentage') | float(0) %}
        {% if not is_state('fan.x', 'on') %}0
        {% elif v <= 12.5 %}5
        {% elif v <= 37.5 %}12
        ...
        {% else %}28
        {% endif %}

    Cut-points are the midpoints between consecutive sample values.
    """
    if not state_value_to_power:
        raise ValueError("state_value_to_power must be non-empty")

    pairs = sorted(state_value_to_power, key=lambda kv: kv[0])
    values = [v for v, _ in pairs]
    watts = [w for _, w in pairs]
    midpoints = [(values[i] + values[i + 1]) / 2
                 for i in range(len(values) - 1)]

    lines: list[str] = [
        f"{{% set v = state_attr('{source_entity}', '{attribute}') "
        f"| float(0) %}}",
        f"{{% if not is_state('{source_entity}', 'on') %}}0",
    ]
    for i, cut in enumerate(midpoints):
        lines.append(f"{{% elif v <= {cut} %}}{watts[i]}")
    lines.append(f"{{% else %}}{watts[-1]}")
    lines.append("{% endif %}")
    return "\n".join(lines)


def calibrate_template(
    client,
    entry_id: str,
    *,
    source_entity: str,
    attribute: str,
    service_set: str,
    state_arg: str,
    states: list[float | int],
    service_off: str,
    smart_meter: str = DEFAULT_SMART_METER,
    baseline_seconds: float = 20,
    stabilisation_seconds: float = 15,
    load_seconds: float = 20,
    samples: int = 5,
    apply_: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Walk ``source_entity`` through each value in ``states`` and measure
    delta per state. Build a piecewise power_template that maps the
    ``attribute`` to the matching wattage.

    Args:
      source_entity: e.g. ``"fan.dining_room_fan_main_fan"``.
      attribute:     state-attribute to key the template on
                     (e.g. ``"percentage"`` for fans).
      service_set:   service to call per step (e.g.
                     ``"fan.set_percentage"`` or ``"light.turn_on"``).
      state_arg:     name of the service arg that carries the step value
                     (e.g. ``"percentage"`` or ``"brightness"``).
      states:        ordered list of values to walk through (e.g.
                     ``[0, 25, 50, 75, 100]``). The first sample
                     measures baseline; subsequent samples measure load.
      service_off:   service to call AFTER the walk to return the device
                     to off (e.g. ``"fan.turn_off"``).

    With ``apply=True`` writes the generated template via
    :func:`powercalc.set_power_template`.
    """
    if not entry_id:
        raise ValueError("entry_id is required")
    if not source_entity or not attribute:
        raise ValueError("source_entity and attribute are required")
    if not states:
        raise ValueError("states must be non-empty")

    # Take baseline with device off
    _call_service(client, service_off, target=source_entity)
    sleep(stabilisation_seconds)
    baseline = _measure(client, smart_meter,
                        duration_seconds=baseline_seconds,
                        samples=samples, sleep=sleep)

    steps: list[dict] = []
    for v in states:
        _call_service(client, service_set, target=source_entity,
                       service_data={state_arg: v})
        sleep(stabilisation_seconds)
        load = _measure(client, smart_meter,
                        duration_seconds=load_seconds,
                        samples=samples, sleep=sleep)
        steps.append({
            "value": v,
            "load_mean": load["mean"],
            "delta_w": round(load["mean"] - baseline["mean"], 1),
        })

    # Switch off after the walk
    try:
        _call_service(client, service_off, target=source_entity)
    except Exception:
        pass

    template = _state_template(
        source_entity, attribute,
        [(s["value"], max(s["delta_w"], 0)) for s in steps],
    )

    applied = False
    if apply_:
        _pc.set_power_template(client, entry_id, power_template=template)
        applied = True

    return {
        "entry_id": entry_id,
        "source_entity": source_entity,
        "attribute": attribute,
        "baseline_mean_w": baseline["mean"],
        "steps": steps,
        "template": template,
        "applied": applied,
    }


# ── auto-calibrate (passive, historical) ──────────────────────────────────

def _list_state_history(client, entity_id: str, *,
                         hours: float) -> list[dict]:
    """Same as :func:`_history_series` but returns all state changes
    (without minimal_response — we need full attribute payload here)."""
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(hours=hours)
    raw = client.get(
        f"history/period/{start.isoformat()}",
        params={
            "filter_entity_id": entity_id,
            "end_time": end.isoformat(),
        },
    )
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return raw[0]
    return []


def _smart_meter_window_mean(
    series: list[dict],
    window_start_ts: float,
    window_end_ts: float,
) -> float | None:
    """Mean of smart-meter readings within ``[start, end]`` epoch seconds.

    ``series`` is a list of history points (last_changed + state). We
    consider every reading whose ``last_changed`` falls inside the window.
    """
    vals: list[float] = []
    for p in series:
        try:
            ts = datetime.fromisoformat(
                p["last_changed"].replace("Z", "+00:00")
            ).timestamp()
            if window_start_ts <= ts <= window_end_ts:
                vals.append(float(p["state"]))
        except (KeyError, ValueError, TypeError):
            continue
    if not vals:
        return None
    return sum(vals) / len(vals)


def auto_calibrate(
    client,
    *,
    smart_meter: str = DEFAULT_SMART_METER,
    hours: float = 24 * 7,
    pre_window_seconds: float = 30,
    post_window_seconds: float = 30,
    quiet_seconds: float = 10,
    min_samples: int = 5,
    title_contains: str | None = None,
    apply_: bool = False,
) -> dict:
    """Passive calibration from recorder history.

    Walks every powercalc virtual_power entry (optionally filtered by
    ``title_contains``), finds the source entity for each, pulls state-
    change history over the last ``hours`` hours, and computes the
    smart-meter delta around each ON→OFF / OFF→ON transition. Median of
    *clean* transitions (those where no other powercalc source entity
    changed state within ±``quiet_seconds``) is the calibrated wattage.

    Args:
      smart_meter:    sensor whose history is the ground truth.
      hours:          how far back to look (default 7 days).
      pre_window_seconds:  window length for the baseline reading right
                           before each transition.
      post_window_seconds: window length for the load reading right
                           after each transition (and after a brief
                           stabilisation skip equal to ``quiet_seconds``).
      quiet_seconds:  how close other-device transitions can be before
                      the candidate transition is rejected as noisy.
      min_samples:    minimum clean transitions required to suggest a
                      calibration for a device.
      title_contains: case-insensitive substring filter on entry title
                      (default: process every virtual_power entry).
      apply_:         when True, write the median delta into each entry's
                      fixed_power via :func:`powercalc.set_fixed_power`.

    Returns ``{window_hours, smart_meter, candidates: [...], applied: N,
    skipped: N}`` where each candidate carries::

        {
          "entry_id", "title", "source_entity",
          "previous_power_w",        # fixed power on the entry today
          "median_delta_w",          # tier-1 suggestion
          "samples",                 # clean transition count
          "p25_w", "p75_w",          # robustness signal
          "applied": bool,
        }
    """
    entries = _pc.list_entries(client, title_contains=title_contains)
    # Restrict to fixed-mode virtual_power entries. We can't strictly
    # detect mode from the listing alone, so we just take any entry that
    # carries a source_entity in data/options.
    candidates_raw: list[dict] = []
    for e in entries:
        opts = e.get("options") or {}
        data = e.get("data") or {}
        source = opts.get("entity_id") or data.get("entity_id")
        if not source:
            continue
        # Skip group entries (they don't have a source_entity).
        if (e.get("title") or "").startswith("Power · "):
            continue
        candidates_raw.append({
            "entry_id": e["entry_id"],
            "title": e.get("title") or "",
            "source_entity": source,
            "previous_power_w": opts.get("power") or data.get("power"),
        })

    # Pull smart-meter history once — we'll slice windows out of it.
    sm_series = _list_state_history(client, smart_meter, hours=hours)
    if not sm_series:
        return {
            "window_hours": hours,
            "smart_meter": smart_meter,
            "candidates": [],
            "applied": 0,
            "skipped": 0,
            "warning": f"no history for {smart_meter}",
        }

    # Pre-compute every source entity's transition timestamps, so we can
    # cheaply check "any other tracked device change within ±quiet_seconds".
    source_transitions: dict[str, list[float]] = {}
    for c in candidates_raw:
        hist = _list_state_history(client, c["source_entity"], hours=hours)
        ts_list: list[float] = []
        for p in hist:
            try:
                ts = datetime.fromisoformat(
                    p["last_changed"].replace("Z", "+00:00")
                ).timestamp()
                ts_list.append(ts)
            except (KeyError, ValueError, TypeError):
                continue
        source_transitions[c["source_entity"]] = ts_list

    # Flatten the global "any tracked device changed at time T" set
    all_other_ts = {se: sorted(ts) for se, ts in source_transitions.items()}

    def _has_other_change(me: str, t: float) -> bool:
        for other, ts_list in all_other_ts.items():
            if other == me:
                continue
            # binary-search bisect would be faster but Frigate-style lazy
            # is fine for the data sizes we deal with (hours of changes,
            # few thousand points max).
            for ts in ts_list:
                if abs(ts - t) <= quiet_seconds:
                    return True
                if ts > t + quiet_seconds:
                    break
            # short-circuit on sorted list
        return False

    out_candidates: list[dict] = []
    applied_count = 0
    skipped_count = 0

    for c in candidates_raw:
        my_ts = sorted(source_transitions.get(c["source_entity"], []))
        # We want ON-transitions specifically. Approximate by looking at
        # consecutive points where the state goes from off/0 to on/non-0.
        hist = _list_state_history(client, c["source_entity"], hours=hours)
        deltas: list[float] = []
        for i in range(1, len(hist)):
            prev_state = (hist[i - 1].get("state") or "").lower()
            cur_state = (hist[i].get("state") or "").lower()
            # Treat "off" / "0" / "0.0" / "unavailable" → "non-off" as ON.
            was_off = prev_state in ("off", "0", "0.0", "")
            is_on = cur_state in ("on",) or (cur_state not in (
                "off", "0", "0.0", "", "unavailable", "unknown") and was_off)
            if not (was_off and is_on):
                continue
            try:
                ts = datetime.fromisoformat(
                    hist[i]["last_changed"].replace("Z", "+00:00")
                ).timestamp()
            except (KeyError, ValueError, TypeError):
                continue

            if _has_other_change(c["source_entity"], ts):
                continue

            pre_mean = _smart_meter_window_mean(
                sm_series, ts - pre_window_seconds, ts - 1,
            )
            post_mean = _smart_meter_window_mean(
                sm_series, ts + quiet_seconds,
                ts + quiet_seconds + post_window_seconds,
            )
            if pre_mean is None or post_mean is None:
                continue
            deltas.append(post_mean - pre_mean)

        if len(deltas) < min_samples:
            skipped_count += 1
            out_candidates.append({**c,
                                    "median_delta_w": None,
                                    "samples": len(deltas),
                                    "p25_w": None, "p75_w": None,
                                    "applied": False,
                                    "skip_reason": f"only {len(deltas)} clean "
                                                    f"samples (need {min_samples})"})
            continue

        deltas.sort()
        n = len(deltas)
        median = deltas[n // 2] if n % 2 == 1 else \
                 (deltas[n // 2 - 1] + deltas[n // 2]) / 2
        p25 = deltas[max(0, n // 4)]
        p75 = deltas[min(n - 1, (3 * n) // 4)]

        applied = False
        if apply_ and median > 0:
            try:
                _pc.set_fixed_power(client, c["entry_id"],
                                    power=round(median, 1))
                applied = True
                applied_count += 1
            except Exception:
                pass

        out_candidates.append({
            **c,
            "median_delta_w": round(median, 1),
            "samples": n,
            "p25_w": round(p25, 1),
            "p75_w": round(p75, 1),
            "applied": applied,
        })

    return {
        "window_hours": hours,
        "smart_meter": smart_meter,
        "candidates": out_candidates,
        "applied": applied_count,
        "skipped": skipped_count,
    }
