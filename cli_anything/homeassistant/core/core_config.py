"""The instance's own idea of where and what it is — read, detect, change, check.

`system config` could already PRINT `/api/config`. Nothing could change it, ask
HA what it thinks the answer should be, or validate `configuration.yaml`
without waiting on a notification. Those three are here.

WHY THIS MATTERS MORE THAN IT LOOKS

    Latitude/longitude and time zone are not cosmetic. `sun.sun`, every
    `sun`-triggered automation, weather forecasts, energy-tariff day
    boundaries, and every `now()` in a template are computed from them. An
    instance that is an hour off, or sitting on HA's default coordinates in
    Belgium, produces automations that fire at the wrong time and a forecast
    for the wrong continent — and it looks like a bug in each of them
    separately.

THREE THINGS READ OUT OF HA'S SOURCE (`components/config/core.py`)

    1. `config/core/update` IS A PARTIAL UPDATE, NOT A REPLACE. HA pops `id`
       and `type` off the message and passes the REST to
       `hass.config.async_update(**data)`, so an omitted key keeps its value.
       That is the opposite of the options-flow footgun that `powercalc` has to
       work around, and it means a one-field change is safe to send alone.
       `update()` still reads before and after and reports the diff, because a
       silently-ignored key is otherwise invisible.

    2. `unit_system` ACCEPTS EXACTLY TWO VALUES — `metric` and `us_customary`.
       `imperial` is silently rewritten to `us_customary` by HA's own
       `_deprecated_unit_system`; anything else is a voluptuous error naming
       the schema rather than the mistake. Rejected here with the two legal
       values in the message.

    3. `update_units` IS A SEPARATE FLAG AND IT IS NOT THE UNIT SYSTEM.
       HA pops it before the update and, when true, calls
       `async_update_suggested_units()` — which re-derives the DISPLAY unit of
       every sensor from the new system. Change `unit_system` without it and
       existing sensors keep showing °F on a metric instance.

AND ONE ABOUT THE CHECK

    `POST /api/config/core/check_config` runs the real
    `check_config.async_check_ha_config_file` and answers synchronously with
    `{result, errors, warnings}`. The harness already had `system check-config`,
    which calls the `homeassistant.check_config` SERVICE and then polls for the
    `persistent_notification.config_check_failed` entity — a real technique,
    but it waits ~8s, it reports nothing on success beyond "valid", and it
    reports WARNINGS not at all, because the notification is only written for
    errors. This endpoint returns the error text and the warning text. It is
    admin-only; a non-admin token gets a 401 that says nothing about that.

A CAVEAT THAT IS HA'S, NOT THIS HARNESS'S

    Core config lives in `.storage/core.config`, but keys set in the
    `homeassistant:` block of `configuration.yaml` are re-applied at startup.
    So a change made here to a key that YAML also sets survives until the next
    restart and then reverts. `update()` cannot see YAML, so it says so in the
    result rather than pretending the write is final.
"""

from __future__ import annotations

import logging
from typing import Any

from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

#: The only two values `homeassistant.util.unit_system.validate_unit_system`
#: accepts. `imperial` is accepted by HA but rewritten to `us_customary`.
UNIT_SYSTEMS = ("metric", "us_customary")

#: Keys `config/core/update` understands, in the order HA declares them.
UPDATABLE = (
    "country",
    "currency",
    "elevation",
    "external_url",
    "internal_url",
    "language",
    "latitude",
    "location_name",
    "longitude",
    "radius",
    "time_zone",
    "unit_system",
)

#: Keys of `/api/config` that `config/core/update` can actually change. Used to
#: build the before/after diff — `/api/config` also returns `components`,
#: `version`, `config_dir` and friends, which are not settable and would swamp
#: the diff.
_COMPARABLE = UPDATABLE


def show(client) -> dict:
    """The settable half of `/api/config`, without the noise around it.

    `system config` prints the whole thing including the component list. This
    is the subset `set` can change, which is what a before/after wants.
    """
    raw = client.get("config") or {}
    if not isinstance(raw, dict):
        raise ValueError(f"/api/config returned {type(raw).__name__}, expected an object")
    return {key: raw.get(key) for key in _COMPARABLE}


def detect(client) -> dict:
    """What HA's own geo-IP lookup says this instance's location is.

    Backed by `config/core/detect`, which asks
    `homeassistant.util.location.async_detect_location_info` — the same call
    onboarding uses to prefill the map. It reaches the internet from the HA
    host, so it describes where the SERVER appears to be, not the caller.

    An EMPTY dict is a real answer: HA returns `{}` when the lookup fails
    (no internet, or the service refused), and that is not distinguishable
    from "no data" at the protocol level. Reported as `detected: false` rather
    than as an error.

    A FAILED LOOKUP IS NOT ALWAYS `{}` — SOMETIMES IT IS `unknown_error`
        HA only converts the lookup into `{}` for the failures it anticipated:
        `_get_whoami` catches `aiohttp.ClientError` and `TimeoutError`. Any
        OTHER exception escapes the handler and comes back as the websocket
        error `unknown_error`, with the reason visible only in HA's own log.
        Measured: on a host whose DNS resolver is incompatible with its
        aiohttp, the lookup raises `TypeError` and this command failed with an
        opaque `unknown_error` — the SAME condition as the `{}` case (geo-IP
        did not work) presented as a crash.

        So `unknown_error` is folded into the same named answer, with
        `lookup_failed: true` distinguishing it from a clean empty. Every
        other code — `unauthorized`, `unknown_command` — still raises, because
        those mean the command is unusable rather than the lookup unlucky.
    """
    lookup_error = None
    try:
        info = client.ws_call("config/core/detect") or {}
    except HomeAssistantError as exc:
        if getattr(exc, "code", None) != "unknown_error":
            raise
        info, lookup_error = {}, str(exc)
    if not isinstance(info, dict):
        info = {}
    return {
        "detected": bool(info),
        "lookup_failed": lookup_error is not None,
        "error": lookup_error,
        "info": info,
        "note": (
            "Geo-IP from the Home Assistant host. An empty result means the "
            "lookup failed (usually no outbound internet), not that the "
            "location is unknown."
            if lookup_error is None
            else (
                "The geo-IP lookup raised on the Home Assistant host rather "
                "than returning empty — HA reports that as `unknown_error` and "
                "logs the reason server-side only. Check HA's log "
                "(`system error-log`). Treated as 'not detected'."
            )
        ),
    }


def drift(client) -> dict:
    """Compare what HA is configured with against what it detects.

    The pairing is the point: `detect` alone is trivia and `show` alone cannot
    tell you it is wrong. Every key present in BOTH is compared, and the
    mismatches are named.

    `latitude`/`longitude` are compared with a tolerance, because geo-IP is
    city-accurate at best — an exact-match test on a float would report drift
    on every instance that ever set its location precisely. The default 0.5°
    is roughly 55km of latitude: far enough to ignore "same town", close
    enough to catch "wrong country".
    """
    configured = show(client)
    detected = detect(client)
    info = detected["info"]
    mismatches = []
    for key, detected_value in sorted(info.items()):
        if key not in configured:
            continue
        current = configured.get(key)
        if key in ("latitude", "longitude"):
            try:
                if abs(float(current) - float(detected_value)) <= 0.5:
                    continue
            except (TypeError, ValueError):
                pass
        elif current == detected_value:
            continue
        mismatches.append({"key": key, "configured": current, "detected": detected_value})
    return {
        "configured": configured,
        "detected": info,
        "detected_ok": detected["detected"],
        "mismatches": mismatches,
        "drifted": bool(mismatches),
        "note": (
            "Coordinates are compared with a 0.5 degree tolerance — geo-IP is "
            "city-accurate at best. An empty `detected` means the lookup "
            "failed, so `drifted: false` says nothing."
            if not detected["detected"]
            else "Coordinates are compared with a 0.5 degree tolerance."
        ),
    }


#: The only two keys whose schema is `vol.Any(cv.url_no_path, None)` — i.e. the
#: only two that can be CLEARED. Every other key is typed, and sending null
#: fails voluptuous with a message about the schema.
CLEARABLE = ("external_url", "internal_url")


def _clean(key: str, value: Any) -> Any:
    """An empty string means "clear it" — but only where HA allows null."""
    if value != "":
        return value
    if key not in CLEARABLE:
        raise ValueError(
            f"{key} cannot be cleared — HA's schema has no null for it. Only "
            f"{' and '.join(CLEARABLE)} accept an empty value."
        )
    return None


def build_update(**fields: Any) -> dict:
    """Validate a partial core-config update and return the payload to send.

    Split out from `update()` so a dry run validates exactly what a real one
    would send. Only keys whose value is not None are included — HA treats
    every key as optional and an omitted key keeps its value, so passing
    nothing for a field is genuinely different from clearing it.
    """
    unknown = sorted(set(fields) - set(UPDATABLE))
    if unknown:
        raise ValueError(
            f"Not a core-config field: {', '.join(unknown)}. Settable: {', '.join(UPDATABLE)}."
        )
    payload: dict[str, Any] = {}
    for key in UPDATABLE:
        value = fields.get(key)
        if value is None:
            continue
        payload[key] = _clean(key, value)

    if "unit_system" in payload:
        raw = str(payload["unit_system"]).lower()
        if raw == "imperial":
            raw = "us_customary"
        if raw not in UNIT_SYSTEMS:
            raise ValueError(
                f"unit_system must be one of {', '.join(UNIT_SYSTEMS)} "
                f"(got {payload['unit_system']!r}). HA also accepts the "
                "deprecated 'imperial' and rewrites it to 'us_customary'."
            )
        payload["unit_system"] = raw

    for key, low, high in (("latitude", -90.0, 90.0), ("longitude", -180.0, 180.0)):
        if key in payload and payload[key] is not None:
            try:
                number = float(payload[key])
            except (TypeError, ValueError):
                raise ValueError(f"{key} must be a number, got {payload[key]!r}") from None
            if not low <= number <= high:
                raise ValueError(f"{key} must be between {low} and {high}, got {number}")
            payload[key] = number

    if "elevation" in payload and payload["elevation"] is not None:
        try:
            payload["elevation"] = int(payload["elevation"])
        except (TypeError, ValueError):
            raise ValueError(
                f"elevation must be a whole number of metres, got {payload['elevation']!r}"
            ) from None

    if "radius" in payload and payload["radius"] is not None:
        try:
            payload["radius"] = int(payload["radius"])
        except (TypeError, ValueError):
            raise ValueError(
                f"radius must be a positive integer, got {payload['radius']!r}"
            ) from None
        if payload["radius"] < 0:
            raise ValueError(f"radius must be a positive integer, got {payload['radius']}")

    if not payload:
        raise ValueError(
            "Nothing to set. Pass at least one of: "
            + ", ".join(f"--{key.replace('_', '-')}" for key in UPDATABLE)
            + ". (Pass an empty string to CLEAR external-url / internal-url.)"
        )
    return payload


def update(
    client,
    *,
    apply: bool = False,
    update_units: bool = False,
    **fields: Any,
) -> dict:
    """Change part of the core config. DRY RUN unless `apply=True`.

    Dry run by default because this is instance-wide and silent: nothing in the
    UI announces that the time zone moved, and every sun-triggered automation
    changes behaviour at once. The dry run performs the same validation and
    reports the same diff, so the only difference is whether the write happens.

    `update_units=True` additionally re-derives every sensor's DISPLAY unit
    from the (possibly new) unit system — see the module docstring. It is a
    no-op without a unit-system change but it is not free, so it is opt-in.
    """
    payload = build_update(**fields)
    before = show(client)
    changes = [
        {"key": key, "from": before.get(key), "to": value}
        for key, value in payload.items()
        if before.get(key) != value
    ]
    result = {
        "applied": False,
        "sent": payload,
        "update_units": bool(update_units),
        "before": before,
        "changes": changes,
        "no_op": not changes,
    }
    if not apply:
        result["note"] = (
            "DRY RUN — nothing was sent. Re-run with apply=True (`--apply`) to "
            "commit. Keys also set in the `homeassistant:` block of "
            "configuration.yaml revert on the next restart."
        )
        return result

    send = dict(payload)
    if update_units:
        send["update_units"] = True
    client.ws_call("config/core/update", send)
    after = show(client)
    result["applied"] = True
    result["after"] = after
    result["effective"] = [
        {"key": key, "requested": value, "actual": after.get(key), "took": after.get(key) == value}
        for key, value in payload.items()
    ]
    result["note"] = (
        "Written to .storage/core.config. Any of these keys ALSO set in the "
        "`homeassistant:` block of configuration.yaml is re-applied on the "
        "next restart and will revert."
    )
    return result


def check_config(client) -> dict:
    """Validate `configuration.yaml` synchronously and return what broke.

    `POST /api/config/core/check_config`. Unlike the service-plus-notification
    route (`control.check_config`, exposed as `system check-config`) this
    answers immediately, returns the actual error TEXT, and returns warnings —
    which the notification never carries, because HA only writes it on failure.

    Admin-only: a non-admin token fails with a 401 that does not mention
    permissions.
    """
    raw = client.post("config/core/check_config") or {}
    if not isinstance(raw, dict):
        raise ValueError(f"check_config returned {type(raw).__name__}, expected an object")
    errors = raw.get("errors")
    warnings = raw.get("warnings")
    return {
        "valid": raw.get("result") == "valid",
        "result": raw.get("result"),
        "errors": errors,
        "warnings": warnings,
        "has_warnings": bool(warnings),
        "source": "POST /api/config/core/check_config",
        "note": (
            "Synchronous, and the only route that reports WARNINGS — the "
            "`homeassistant.check_config` service writes its notification on "
            "failure only. Requires an admin token."
        ),
    }


def safe_set(
    client,
    *,
    apply: bool = False,
    update_units: bool = False,
    **fields: Any,
) -> dict:
    """`update()` with a config check first — refuse to write onto broken YAML.

    A core-config write is stored immediately but several of these keys only
    take full effect after a restart, and restarting an instance whose
    `configuration.yaml` is already invalid is how a small change becomes an
    outage. The check is the same one `check_config()` runs.
    """
    check = check_config(client)
    if not check["valid"]:
        return {
            "applied": False,
            "blocked_by": "check_config",
            "check": check,
            "note": (
                "configuration.yaml does not validate, so nothing was written. "
                "Fix the errors above, or call update() directly to write anyway."
            ),
        }
    result = update(client, apply=apply, update_units=update_units, **fields)
    result["check"] = check
    return result
