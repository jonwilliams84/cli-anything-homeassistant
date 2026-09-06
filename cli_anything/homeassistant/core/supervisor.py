"""The Supervisor — add-ons, host, OS, network and the update surface.

THE GAP THIS CLOSES
    Everything this harness could reach lived inside Home Assistant Core. The
    other half of a Home Assistant OS / Supervised install — the Supervisor
    that installs the add-ons, owns the host, and ships the OS updates — had
    no command at all. It is not a REST API on Core's port; it is reached
    through ONE websocket command, `supervisor/api`, which proxies an
    arbitrary Supervisor endpoint, plus the `/api/hassio/…` HTTP proxy for the
    endpoints that answer in plain text (the logs).

    `supervisor/api` was in neither this harness nor its coverage report,
    because the enumeration that produced that report matched
    `vol.Required("type")` as a LITERAL. hassio declares its three commands
    through constants (`vol.Required(WS_TYPE): WS_TYPE_API`), so a
    literal-only scan reports full coverage of a surface it never saw. All
    three — `supervisor/api`, `supervisor/subscribe`, `supervisor/event` —
    were missing.

WHY THE HTTP PROXY IS NOT THE WAY IN
    `/api/hassio/{path}` looks like the obvious door and is almost entirely
    barred. `HassIOView._handle` matches the path against `PATHS_ADMIN` before
    forwarding, and for an authenticated admin that allowlist is only:
    backups by 8-hex slug, `backups/new/upload`, `<component>/logs…`, and
    `addons/<slug>/(logs|changelog|documentation)`. `addons`, `addons/<slug>/
    info`, `supervisor/info`, `host/reboot` — every management endpoint —
    answer **401 with an empty body** through it. The websocket command has no
    such allowlist: it checks `connection.user.is_admin` once and forwards
    anything.

    So this module uses BOTH transports and the split is not cosmetic:

      * websocket `supervisor/api` for everything that answers JSON;
      * HTTP `/api/hassio/<component>/logs` for the logs, which answer
        `text/plain`. Sent over the websocket instead, `send_command` calls
        `response.json()` on a plain-text body, `ContentTypeError` (an
        `aiohttp.ClientError`) is caught, and the failure arrives as
        `unknown_error` — see below for why that is the same symptom as four
        other unrelated faults.

THE ERROR CHANNEL IS ONE BIT WIDE
    `websocket_supervisor_api` reports EVERY failure as `unknown_error`:

      * A Supervisor error is caught as `HassioAPIError` and forwarded with
        the Supervisor's own message — the useful case.
      * An endpoint that does not survive `yarl` normalisation (no leading
        slash, a query string, `..`) raises `HassioAPIError` with **no
        arguments**, so the message is the EMPTY STRING. Refused locally here
        instead: `_normalise_endpoint` is the whole reason this module does
        not just forward what it is given.
      * A Supervisor TIMEOUT or connection error is worse than either.
        `HassIO.send_command` catches `TimeoutError` and `aiohttp.ClientError`
        and then FALLS OFF THE END OF THE FUNCTION — it returns `None` rather
        than re-raising. The handler immediately does `result.get(ATTR_DATA)`,
        which is an `AttributeError` on `None`, and the websocket layer turns
        any unexpected exception into `unknown_error` / "Unknown error". The
        only trace of the real cause is a line in Home Assistant's own log.

    That last one is not an edge case: the proxy's default timeout is TEN
    SECONDS and an add-on install, a core update or a backup takes minutes.
    Hence `--timeout` on every write, and `_explain` below, which names the
    likely causes of a bare `unknown_error` rather than repeating it.

WHY `options` IS DRY-RUN BY DEFAULT
    `POST /addons/<slug>/options` REPLACES the options object; a key left out
    of the payload is a key reset to its add-on default. Same footgun the
    `powercalc` commands wrap. Here it is better than dry-run-by-diff, because
    Supervisor has a real validator — `POST /addons/<slug>/options/validate`
    checks the merged object against the add-on's schema WITHOUT writing it.
    So the dry run reads the current options, merges, shows the diff, and asks
    Supervisor whether the result would be accepted; `--apply` then writes the
    FULL merged object, never the fragment the caller typed.
"""

from __future__ import annotations

import json
import threading

from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

#: The websocket command every JSON call in this module goes through.
WS_API = "supervisor/api"

#: The dispatcher subscription that streams Supervisor progress events.
WS_SUBSCRIBE = "supervisor/subscribe"

#: `unknown_command` means the `hassio` integration is not loaded, which means
#: this is a Core or Container install and there is no Supervisor to talk to.
ABSENT_CODES = ("unknown_command",)

_ABSENT_NOTE = (
    "This Home Assistant has no Supervisor. The `supervisor` commands need a "
    "Home Assistant OS or Home Assistant Supervised install — the two "
    "installation types that manage add-ons, the host and the OS; Core and "
    "Container installs have neither, by design. Confirm it independently "
    "with `system components`: the `hassio` integration is what registers "
    "both the `supervisor/api` websocket command and the `/api/hassio/…` "
    "proxy, so its absence from that list IS the absence of a Supervisor."
)

#: HA passes `method` straight to `aiohttp.ClientSession.request`, so anything
#: is accepted on the wire and a typo becomes a Supervisor 405 wrapped in an
#: `unknown_error`. Restricted here to what Supervisor actually serves.
METHODS = ("get", "post", "put", "delete")

#: The components whose journal the HTTP proxy will hand over. Taken from
#: `PATHS_LOGS` in `homeassistant/components/hassio/http.py` — a component not
#: in this list is a 401 with an empty body, not a 404.
LOG_COMPONENTS = (
    "audio",
    "cli",
    "core",
    "dns",
    "host",
    "multicast",
    "observer",
    "supervisor",
)

#: Components that answer `/<component>/info` and `/<component>/stats`.
#: `host` and `network` have info but no stats; `os` has neither stats nor a
#: container behind it.
STATS_COMPONENTS = ("supervisor", "core", "audio", "dns", "multicast", "observer")

#: Add-on lifecycle verbs this module will POST. `install`/`uninstall` are
#: deliberately absent: both are minutes-long and irreversible in opposite
#: directions, and both are reachable through `supervisor api` for a caller
#: who has read what it does.
ADDON_ACTIONS = ("start", "stop", "restart", "rebuild", "update")

#: Default Supervisor-side timeout, in seconds — the value HA itself uses when
#: the message omits one.
DEFAULT_TIMEOUT = 10.0

#: What a long write needs instead. An add-on restart is `timeout=None` in
#: Supervisor's own client; an update is minutes.
SLOW_TIMEOUT = 300.0


def _absent(exc: HomeAssistantError) -> bool:
    return getattr(exc, "code", None) in ABSENT_CODES


def _normalise_endpoint(endpoint: str) -> str:
    """Return a Supervisor path HA's own normalisation will accept.

    `HassIO.send_command` builds `self._base_url.with_path(command)` and then
    refuses the call if `joined_url.raw_path != command`. Every difference
    between what you typed and what `yarl` produces is therefore a rejection —
    reported as an `unknown_error` whose message is the empty string, because
    the `HassioAPIError` it raises is constructed with no arguments.

    The differences that bite, all refused here by name instead:

    * no leading slash — `with_path("addons")` yields `/addons`;
    * a query string — `with_path` drops it, and `raw_path` never had it;
    * `.` / `..` segments — normalised away (this check is HA's path-traversal
      guard, and the only one of the four it was written for);
    * characters `yarl` would percent-encode, e.g. a space.
    """
    if endpoint is None or not str(endpoint).strip():
        raise ValueError(
            "endpoint cannot be empty — it is the Supervisor path to call, "
            "e.g. `/supervisor/info` or `/addons/core_ssh/info`."
        )
    path = str(endpoint).strip()
    if not path.startswith("/"):
        raise ValueError(
            f"endpoint must start with '/': got {path!r}. Home Assistant "
            f"compares the path you send against its own normalisation of it "
            f"and refuses any difference — with an EMPTY error message. Try "
            f"'/{path}'."
        )
    if "?" in path or "#" in path:
        raise ValueError(
            f"endpoint must not carry a query string or fragment: got {path!r}. "
            "The proxy compares raw PATHS, so anything after '?' guarantees a "
            "mismatch. Supervisor endpoints that take arguments take them in "
            "the body — pass them with --data."
        )
    segments = path.split("/")
    if any(seg in (".", "..") for seg in segments):
        raise ValueError(
            f"endpoint must not contain '.' or '..' segments: got {path!r}. "
            "Home Assistant refuses these outright; it is the path-traversal "
            "check on the proxy."
        )
    bad = [ch for ch in path if ch.isspace() or ord(ch) > 126 or ch == "%"]
    if bad:
        raise ValueError(
            f"endpoint must be plain ASCII with no spaces or percent-escapes: "
            f"got {path!r}. Home Assistant re-encodes the path and then "
            "rejects it for not matching what you sent."
        )
    return path


def _check_timeout(timeout) -> float | None:
    """Validate the Supervisor-side timeout. `None` means 'wait forever'."""
    if timeout is None:
        return None
    try:
        value = float(timeout)
    except (TypeError, ValueError):
        raise ValueError(f"timeout must be a number of seconds or None, got {timeout!r}") from None
    if value <= 0:
        raise ValueError(
            f"timeout must be positive, got {value}. Pass None (`--no-timeout`) "
            "for no Supervisor-side limit at all — but note the websocket "
            "still gives up after the client's own --timeout."
        )
    return value


def _explain(exc: HomeAssistantError, endpoint: str, timeout: float | None) -> HomeAssistantError:
    """Turn the one error code the proxy emits back into a cause.

    `unknown_error` arrives for a Supervisor error (with a message worth
    printing), for a rejected path (empty message) and for a Supervisor
    timeout or connection failure (the literal string "Unknown error", because
    the handler crashed on a `None` it was never meant to get). Only the first
    of those explains itself.
    """
    code = getattr(exc, "code", None)
    if code == "unauthorized":
        return HomeAssistantError(
            f"Not allowed to call {endpoint}. The Supervisor proxy requires an "
            "ADMIN user for every endpoint except `/ingress/session`, "
            "`/ingress/validate_session` and `/addons/<slug>/info`. Check the "
            "token's user with `whoami`.",
            code=code,
        )
    if code != "unknown_error":
        return exc
    message = str(exc)
    tail = message.split("unknown_error", 1)[-1].strip()
    if tail and tail.lower() not in ("unknown error", ""):
        return HomeAssistantError(f"Supervisor refused {endpoint}: {tail}", code=code)
    limit = "no limit" if timeout is None else f"{timeout:g}s"
    return HomeAssistantError(
        f"Supervisor gave no answer for {endpoint} (Supervisor-side timeout: "
        f"{limit}).\n"
        "Home Assistant reports a Supervisor timeout, a connection failure and "
        "a non-JSON response with this same empty error — the real cause is "
        "only in Home Assistant's own log (`system error-log`).\n"
        "Most likely: the call took longer than the timeout. Installs, "
        "updates, rebuilds and backups take minutes; the default is 10 "
        "seconds. Retry with --timeout 300.\n"
        "If the endpoint answers plain text rather than JSON (any `…/logs`), "
        "it cannot be read this way at all — use `supervisor logs`.",
        code=code,
    )


def api(
    client,
    endpoint: str,
    *,
    method: str = "get",
    data: dict | None = None,
    timeout: float | None = DEFAULT_TIMEOUT,
) -> dict:
    """Call one Supervisor endpoint and return its `data` object.

    The raw escape hatch every other function here is built on, and the only
    way to reach the parts of Supervisor this module does not name.

    The result is ALREADY UNWRAPPED: Supervisor answers
    `{"result": "ok", "data": {…}}` and the handler returns `result["data"]`,
    so an endpoint that carries no payload — every lifecycle action — succeeds
    with an EMPTY DICT. Empty is success here, not "nothing happened"; the
    callers below say so explicitly rather than printing `{}`.
    """
    path = _normalise_endpoint(endpoint)
    verb = str(method or "get").strip().lower()
    if verb not in METHODS:
        raise ValueError(f"method must be one of {', '.join(METHODS)}, got {method!r}")
    if data is not None and not isinstance(data, dict):
        raise ValueError(
            f"data must be a JSON object, got {type(data).__name__}. Home "
            "Assistant validates it as a dict and refuses anything else."
        )
    limit = _check_timeout(timeout)
    payload: dict = {"endpoint": path, "method": verb}
    if data is not None:
        payload["data"] = data
    # `timeout` is `vol.Any(Number, None)`: sending an explicit null is how
    # you ask for no Supervisor-side limit, and it is NOT the same as omitting
    # the key (which defaults to 10s).
    payload["timeout"] = limit
    try:
        result = client.ws_call(WS_API, payload)
    except HomeAssistantError as exc:
        if _absent(exc):
            raise HomeAssistantError(_ABSENT_NOTE, code=getattr(exc, "code", None)) from exc
        raise _explain(exc, path, limit) from exc
    return result if isinstance(result, dict) else {"result": result}


def available(client) -> dict:
    """Is there a Supervisor at all? A READ — 'no' is an answer, not an error.

    Every other command in this group needs one, so this is what a script
    should branch on instead of catching an error string.
    """
    try:
        data = api(client, "/supervisor/info")
    except HomeAssistantError as exc:
        if str(exc) == _ABSENT_NOTE:
            return {"available": False, "version": None, "note": _ABSENT_NOTE}
        raise
    return {
        "available": True,
        "version": data.get("version"),
        "version_latest": data.get("version_latest"),
        "update_available": bool(data.get("update_available")),
        "channel": data.get("channel"),
        "note": "Supervisor is reachable; every `supervisor` command works here.",
    }


def info(client) -> dict:
    """`/supervisor/info` — the Supervisor's own version, channel and add-ons.

    The add-on list embedded here is a SUMMARY (slug, name, version, state);
    `addon_list` reads the full `/addons` view.
    """
    data = api(client, "/supervisor/info")
    addons = data.get("addons") or []
    return {
        "version": data.get("version"),
        "version_latest": data.get("version_latest"),
        "update_available": bool(data.get("update_available")),
        "channel": data.get("channel"),
        "arch": data.get("arch"),
        "supported": data.get("supported"),
        "healthy": data.get("healthy"),
        "diagnostics": data.get("diagnostics"),
        "timezone": data.get("timezone"),
        "addons_installed": len(addons),
        "addons": sorted(
            (
                {
                    "slug": a.get("slug"),
                    "name": a.get("name"),
                    "version": a.get("version"),
                    "state": a.get("state"),
                }
                for a in addons
            ),
            key=lambda row: str(row.get("slug") or ""),
        ),
        "note": (
            "`supported: false` means Supervisor has flagged this install "
            "(custom container, unsupported OS, …) and will refuse some "
            "operations — `supervisor resolution` lists exactly which flags."
        ),
    }


def component_info(client, component: str) -> dict:
    """`/<component>/info` for host, os, core or network.

    Four different endpoints, one shape, because the interesting question —
    "what version is it and is there a newer one" — is the same for all of
    them and nobody should have to remember which noun HA uses.
    """
    allowed = ("host", "os", "core", "network", "supervisor")
    name = str(component or "").strip().lower()
    if name not in allowed:
        raise ValueError(f"component must be one of {', '.join(allowed)}, got {component!r}")
    data = api(client, f"/{name}/info")
    out = {"component": name, **data}
    if "update_available" in data:
        out["update_available"] = bool(data.get("update_available"))
    return out


def stats(client, component: str) -> dict:
    """`/<component>/stats` — CPU, memory and network for one container.

    Accepts an add-on slug as well as a Supervisor component: they share the
    endpoint shape, and "how much memory is that add-on using" is the question
    people actually have.
    """
    name = str(component or "").strip().lower()
    if not name:
        raise ValueError(
            f"component cannot be empty — pass one of {', '.join(STATS_COMPONENTS)} "
            "or an add-on slug."
        )
    endpoint = f"/{name}/stats" if name in STATS_COMPONENTS else f"/addons/{name}/stats"
    data = api(client, endpoint)
    percent = data.get("memory_percent")
    return {
        "component": name,
        "endpoint": endpoint,
        "cpu_percent": data.get("cpu_percent"),
        "memory_usage": data.get("memory_usage"),
        "memory_limit": data.get("memory_limit"),
        "memory_percent": percent,
        "network_rx": data.get("network_rx"),
        "network_tx": data.get("network_tx"),
        "blk_read": data.get("blk_read"),
        "blk_write": data.get("blk_write"),
    }


def resolution(client) -> dict:
    """`/resolution/info` — the issues Supervisor has found and can fix.

    The machine-readable counterpart to the repair notices in the UI. Each
    unhealthy/unsupported reason here is why an operation gets refused with an
    otherwise unexplained error.
    """
    data = api(client, "/resolution/info")
    issues = data.get("issues") or []
    suggestions = data.get("suggestions") or []
    return {
        "unsupported": data.get("unsupported") or [],
        "unhealthy": data.get("unhealthy") or [],
        "issues": issues,
        "suggestions": suggestions,
        "checks": data.get("checks") or [],
        "issue_count": len(issues),
        "suggestion_count": len(suggestions),
        "note": (
            "Apply a suggestion with `supervisor api /resolution/suggestion/"
            "<uuid> --method post`. `unhealthy` entries block add-on installs "
            "and updates outright."
        ),
    }


def _addon_row(raw: dict) -> dict:
    return {
        "slug": raw.get("slug"),
        "name": raw.get("name"),
        "version": raw.get("version"),
        "version_latest": raw.get("version_latest"),
        "update_available": bool(raw.get("update_available")),
        "state": raw.get("state"),
        "repository": raw.get("repository"),
        "icon": bool(raw.get("icon")),
    }


def addon_list(client, *, state: str | None = None, updates_only: bool = False) -> dict:
    """`/addons` — every INSTALLED add-on.

    Not the store: `/addons` is what is on this machine. The store catalogue
    is `/store/addons`, reachable through `supervisor api`.
    """
    data = api(client, "/addons")
    rows = [_addon_row(a) for a in (data.get("addons") or [])]
    wanted = str(state).strip().lower() if state else None
    if wanted:
        rows = [r for r in rows if str(r.get("state") or "").lower() == wanted]
    if updates_only:
        rows = [r for r in rows if r["update_available"]]
    rows.sort(key=lambda row: str(row.get("slug") or ""))
    return {
        "addons": rows,
        "count": len(rows),
        "running": sum(1 for r in rows if r.get("state") == "started"),
        "updatable": sum(1 for r in rows if r["update_available"]),
        "filters": {"state": wanted, "updates_only": bool(updates_only)},
    }


def addon_info(client, slug: str, *, reveal_options: bool = False) -> dict:
    """`/addons/<slug>/info` — one add-on in full.

    `options` is withheld unless `--reveal` is passed: an add-on's options are
    where its credentials live (a database password, an MQTT user, an API key
    for a cloud service), and this harness prints to a terminal that is
    frequently logged. `options_keys` says what is set without saying what it
    is set to.
    """
    name = _require_slug(slug)
    data = api(client, f"/addons/{name}/info")
    options = data.get("options")
    out = {
        **_addon_row(data),
        "description": data.get("description"),
        "url": data.get("url"),
        "boot": data.get("boot"),
        "auto_update": data.get("auto_update"),
        "ingress": data.get("ingress"),
        "ingress_url": data.get("ingress_url"),
        "hostname": data.get("hostname"),
        "network": data.get("network"),
        "watchdog": data.get("watchdog"),
        "startup": data.get("startup"),
        "privileged": data.get("privileged") or [],
        "rating": data.get("rating"),
        "options_keys": sorted(options.keys()) if isinstance(options, dict) else [],
    }
    if reveal_options:
        out["options"] = options if isinstance(options, dict) else {}
    else:
        out["options"] = None
        out["note"] = (
            "`options` withheld — add-on options routinely hold passwords and "
            "API keys. Pass --reveal to print them; `options_keys` lists what "
            "is set."
        )
    return out


def _require_slug(slug: str) -> str:
    name = str(slug or "").strip()
    if not name:
        raise ValueError(
            "slug cannot be empty — it names WHICH add-on to act on. "
            "`supervisor addon list` prints the slugs."
        )
    if "/" in name:
        raise ValueError(
            f"slug must not contain '/': got {name!r}. It is one path segment "
            "— `core_ssh`, not `local/core_ssh`."
        )
    return name


def addon_action(
    client,
    slug: str,
    action: str,
    *,
    apply: bool = False,
    timeout: float | None = SLOW_TIMEOUT,
) -> dict:
    """POST one lifecycle verb at an add-on. Dry-run unless `apply=True`.

    The dry run is not decoration. `stop` on the add-on serving this session's
    SSH or VS Code cuts the connection that issued it, `restart` drops
    everything the add-on was doing, and `update` cannot be undone without a
    backup. The dry run reads the add-on first and reports what state it is in
    now and what the verb would do to it — including when the answer is
    "nothing, it is already stopped".
    """
    name = _require_slug(slug)
    verb = str(action or "").strip().lower()
    if verb not in ADDON_ACTIONS:
        raise ValueError(f"action must be one of {', '.join(ADDON_ACTIONS)}, got {action!r}")
    current = api(client, f"/addons/{name}/info")
    state = current.get("state")
    row = _addon_row(current)
    if verb == "update" and not row["update_available"]:
        raise ValueError(
            f"Add-on {name} is already at {row['version']}, the newest version "
            "Supervisor knows about. Refresh the store first with "
            "`supervisor api /store/reload --method post` if you expect a newer one."
        )
    no_op = (verb == "start" and state == "started") or (verb == "stop" and state == "stopped")
    plan = {
        "slug": name,
        "action": verb,
        "state_before": state,
        "version": row["version"],
        "version_latest": row["version_latest"],
        "endpoint": f"/addons/{name}/{verb}",
        "no_op": no_op,
        "applied": False,
    }
    if not apply:
        plan["note"] = (
            f"Dry run — nothing was sent. `{verb}` on {name} would "
            + ("do nothing: it is already in that state." if no_op else f"take it from {state!r}.")
            + " Re-run with --apply to commit."
        )
        return plan
    api(client, f"/addons/{name}/{verb}", method="post", timeout=timeout)
    after = api(client, f"/addons/{name}/info")
    plan["applied"] = True
    plan["state_after"] = after.get("state")
    plan["version_after"] = after.get("version")
    # Every lifecycle endpoint answers `{"result": "ok"}` with no data, so the
    # proxy hands back an empty dict. Success is read from the add-on, not
    # from the (necessarily empty) response.
    plan["note"] = (
        f"{verb} sent. {name} is now {after.get('state')!r} "
        f"(was {state!r}). Supervisor returns no payload for a lifecycle "
        "action, so this state was re-read from /addons/<slug>/info."
    )
    return plan


def addon_options(
    client,
    slug: str,
    values: dict | None = None,
    *,
    remove: tuple = (),
    apply: bool = False,
    validate: bool = True,
) -> dict:
    """Change an add-on's options — MERGED, validated, dry-run by default.

    `POST /addons/<slug>/options` REPLACES the whole options object. Sending
    the one key you meant to change resets every other key to the add-on's
    default, silently, and the add-on restarts into that configuration. So the
    current options are read first and the change is merged into them; what
    gets written is always the FULL object.

    `remove` is how you deliberately unset a key — Supervisor treats a key set
    to `null` as "back to the default", which is a different thing from
    dropping it, so the key is dropped from the merged object instead.

    The dry run asks Supervisor itself whether the result is legal, via
    `POST /addons/<slug>/options/validate`, which checks the object against
    the add-on's schema and writes nothing. An invalid change is refused
    BEFORE it can restart an add-on into a config that will not boot.
    """
    name = _require_slug(slug)
    changes = dict(values or {})
    drops = [str(k) for k in (remove or ())]
    if not changes and not drops:
        raise ValueError(
            "Nothing to change — pass --set key=value or --remove key. "
            "`supervisor addon info <slug> --reveal` shows the current options."
        )
    overlap = sorted(set(changes) & set(drops))
    if overlap:
        raise ValueError(f"Cannot set and remove the same key: {', '.join(overlap)}. Pick one.")
    current_raw = api(client, f"/addons/{name}/info").get("options")
    current = dict(current_raw) if isinstance(current_raw, dict) else {}
    merged = dict(current)
    merged.update(changes)
    missing = [k for k in drops if k not in current]
    for key in drops:
        merged.pop(key, None)
    result = {
        "slug": name,
        "endpoint": f"/addons/{name}/options",
        "keys_set": sorted(changes),
        "keys_removed": sorted(k for k in drops if k in current),
        "keys_not_present": sorted(missing),
        "keys_preserved": sorted(k for k in current if k not in changes and k not in drops),
        "changed": merged != current,
        "applied": False,
        "validated": None,
        "valid": None,
    }
    if validate:
        try:
            check = api(
                client,
                f"/addons/{name}/options/validate",
                method="post",
                data={"options": merged},
            )
        except HomeAssistantError as exc:
            result["validated"] = False
            result["valid"] = None
            result["validation_error"] = str(exc)
        else:
            result["validated"] = True
            result["valid"] = bool(check.get("valid", True))
            result["validation_message"] = check.get("message")
            if not result["valid"]:
                raise ValueError(
                    f"Supervisor rejected these options for {name}: "
                    f"{check.get('message') or 'no reason given'}. Nothing was "
                    "written."
                )
    if not apply:
        result["note"] = (
            "Dry run — nothing was written. "
            + (
                f"{len(result['keys_set'])} key(s) would change and "
                f"{len(result['keys_preserved'])} would be carried over "
                "unchanged (Supervisor REPLACES the options object, so they "
                "are re-sent explicitly). "
            )
            + "Re-run with --apply to commit."
        )
        return result
    api(client, f"/addons/{name}/options", method="post", data={"options": merged})
    result["applied"] = True
    result["note"] = (
        f"Options written for {name}. The add-on keeps running with the OLD "
        "configuration until it is restarted — `supervisor addon restart "
        f"{name} --apply`."
    )
    return result


def _log_path(component: str | None, addon: str | None, boot: int | None) -> str:
    """Build the `/api/hassio/…` path for a journal read, or refuse by name."""
    if addon and component:
        raise ValueError("Pass a component OR an add-on slug, not both.")
    if addon:
        base = f"addons/{_require_slug(addon)}/logs"
    else:
        name = str(component or "").strip().lower()
        if name not in LOG_COMPONENTS:
            raise ValueError(
                f"component must be one of {', '.join(LOG_COMPONENTS)}, got "
                f"{component!r} — or pass --addon <slug> for an add-on's log. "
                "The HTTP proxy matches the path against an allowlist and "
                "answers anything else with a bare 401."
            )
        base = f"{name}/logs"
    if boot is None:
        return base
    return f"{base}/boots/{int(boot)}"


def logs(
    client,
    component: str | None = None,
    *,
    addon: str | None = None,
    lines: int = 100,
    boot: int | None = None,
) -> dict:
    """Read a Supervisor-managed journal over the `/api/hassio/…` proxy.

    NOT over `supervisor/api`: these endpoints answer `text/plain`, and the
    websocket path calls `response.json()` on the body, so the whole read
    comes back as a bare `unknown_error`. The HTTP proxy is the only
    transport that works, and logs are one of the few things its allowlist
    actually permits.

    `lines` is sent as `Range: entries=:-N:` — systemd's journal-gateway
    syntax, which is what Supervisor speaks and what the proxy explicitly
    forwards (`if PATHS_LOGS.match(path) and request.headers.get(RANGE)`).
    There is no query parameter for it.

    `boot` selects an earlier boot: `0` is the current one, `-1` the previous.
    Only `host` accepts the bare `/boots` index (`boot_ids`); for every other
    component the allowlist demands an explicit number.

    `--follow` is deliberately absent. Those paths are in HA's `NO_TIMEOUT`
    list and stream until the client disappears; handed to a blocking read
    they never return.
    """
    path = _log_path(component, addon, boot)
    count = int(lines)
    if count <= 0:
        raise ValueError(f"lines must be positive, got {lines}.")
    headers = {"Range": f"entries=:-{count}:"}
    try:
        body = client.get(f"hassio/{path}", headers=headers)
    except HomeAssistantError as exc:
        raise _explain_log_error(exc, path) from exc
    text = body if isinstance(body, str) else json.dumps(body, default=str)
    entries = [line for line in text.splitlines() if line.strip()]
    return {
        "path": f"/api/hassio/{path}",
        "target": addon or (component or "").lower(),
        "kind": "addon" if addon else "component",
        "boot": boot,
        "lines_requested": count,
        "lines_returned": len(entries),
        "entries": entries,
        "text": text,
    }


def _explain_log_error(exc: HomeAssistantError, path: str) -> HomeAssistantError:
    """The log proxy answers failures with a status and an EMPTY body."""
    status = getattr(exc, "status", None)
    if status == 401:
        return HomeAssistantError(
            f"The Supervisor proxy refused /api/hassio/{path} (401, empty body).\n"
            "It matches the path against an allowlist before forwarding, and a "
            "401 here means the path is not on it — most often an add-on slug "
            "that is not installed, or a component outside "
            f"{', '.join(LOG_COMPONENTS)}.\n"
            "It also means this exactly when the token's user is not an ADMIN; "
            "check with `whoami`.",
            status=status,
        )
    if status == 404:
        return HomeAssistantError(
            f"No Supervisor at /api/hassio/{path} (404). {_ABSENT_NOTE}",
            status=status,
        )
    if status == 502:
        return HomeAssistantError(
            f"Home Assistant could not reach the Supervisor for /api/hassio/{path} "
            "(502). The proxy answers 502 for both a connection error and a "
            "timeout; a very large --lines on a busy journal can cause the "
            "second. Retry with fewer lines.",
            status=status,
        )
    return exc


def boots(client) -> dict:
    """`/host/logs/boots` — the boot ids an earlier journal can be read from.

    Host-only: `PATHS_ADMIN` spells `host/logs(/follow|/boots(/-?\\d+…)?)?`,
    which is the one component whose bare `/boots` index is allowed through.
    Ask any other component for it and the answer is a 401.
    """
    try:
        body = client.get("hassio/host/logs/boots")
    except HomeAssistantError as exc:
        raise _explain_log_error(exc, "host/logs/boots") from exc
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            body = {}
    raw = body.get("data", body) if isinstance(body, dict) else {}
    rows = sorted(
        ({"offset": int(k), "boot_id": v} for k, v in raw.items() if str(k).lstrip("-").isdigit()),
        key=lambda row: row["offset"],
    )
    return {
        "boots": rows,
        "count": len(rows),
        "note": (
            "Pass an offset to `supervisor logs <component> --boot N`: 0 is the "
            "current boot, -1 the one before it. Only `host` publishes this "
            "index; other components take the offset without listing them."
        ),
    }


def status(client) -> dict:
    """One read that answers "what is this machine running and is it current?"

    Four endpoints — supervisor, core, host, os — reported side by side,
    because the version questions people ask ("is anything out of date", "what
    OS is under this") span all of them and no single Supervisor endpoint
    covers it. Each part degrades on its own: an `os/info` that fails on a
    Supervised install (there is no HA OS under it) leaves the rest intact
    rather than failing the command.
    """
    parts: dict = {}
    errors: dict = {}
    for name in ("supervisor", "core", "host", "os"):
        try:
            parts[name] = api(client, f"/{name}/info")
        except HomeAssistantError as exc:
            if _ABSENT_NOTE in str(exc):
                return {
                    "available": False,
                    "components": {},
                    "updates_available": [],
                    "note": _ABSENT_NOTE,
                }
            errors[name] = str(exc)
    summary = {}
    updates = []
    for name, data in parts.items():
        row = {
            "version": data.get("version"),
            "version_latest": data.get("version_latest"),
            "update_available": bool(data.get("update_available")),
        }
        if name == "host":
            row["operating_system"] = data.get("operating_system")
            row["kernel"] = data.get("kernel")
            row["disk_free"] = data.get("disk_free")
            row["disk_total"] = data.get("disk_total")
        if name == "os":
            row["board"] = data.get("board")
        if name == "supervisor":
            row["channel"] = data.get("channel")
            row["healthy"] = data.get("healthy")
            row["supported"] = data.get("supported")
        summary[name] = row
        if row["update_available"]:
            updates.append(name)
    return {
        "available": True,
        "components": summary,
        "updates_available": sorted(updates),
        "errors": errors,
        "note": (
            "Update a component with `supervisor api /<component>/update "
            "--method post --timeout 600` — they take minutes, and the proxy's "
            "10-second default reports a running update as an error."
            if updates
            else "Everything Supervisor manages is at its newest known version."
        ),
    }


def watch(
    client,
    *,
    duration: float = 30.0,
    max_events: int | None = None,
    on_event=None,
) -> dict:
    """Stream Supervisor progress events (`supervisor/subscribe`).

    The only way to see a long job make progress. `supervisor addon <verb>
    --apply` and every `/…/update` answer NOTHING until they are finished (or
    until the 10-second proxy timeout turns them into an `unknown_error`);
    Supervisor meanwhile dispatches `addon`, `supervisor` and `job` events
    describing what it is doing. Run this in a second shell while the first
    one waits.

    Bounded by BOTH a wall-clock `duration` and an optional `max_events`,
    because a subscription has no natural end: HA forwards the dispatcher
    signal for as long as the socket is open.

    Home Assistant does not schema the payload — it re-emits whatever
    Supervisor sent — so events are collected verbatim.
    """
    seconds = float(duration)
    if seconds <= 0:
        raise ValueError(f"duration must be positive, got {duration}.")
    if max_events is not None and int(max_events) <= 0:
        raise ValueError(f"max_events must be positive when given, got {max_events}.")
    events: list = []
    stop_event = threading.Event()

    def _handle(message) -> None:
        events.append(message)
        if on_event is not None:
            on_event(message)
        if max_events is not None and len(events) >= int(max_events):
            stop_event.set()

    timer = threading.Timer(seconds, stop_event.set)
    timer.daemon = True
    timer.start()
    try:
        client.ws_subscribe(WS_SUBSCRIBE, None, _handle, stop_event)
    except HomeAssistantError as exc:
        if _absent(exc):
            raise HomeAssistantError(_ABSENT_NOTE, code=getattr(exc, "code", None)) from exc
        raise
    finally:
        timer.cancel()
    return {
        "events": events,
        "count": len(events),
        "duration": seconds,
        "max_events": max_events,
        "note": (
            "Nothing was dispatched. Supervisor emits only while something is "
            "happening, so an empty list from an idle instance is the normal "
            "result — start a job first, then watch it."
            if not events
            else "Events are forwarded verbatim; Home Assistant applies no schema."
        ),
    }
