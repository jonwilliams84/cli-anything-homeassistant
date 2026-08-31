"""Turn Home Assistant's silent service failures back into reasons.

Every entity-control command in this harness is a `POST
/api/services/<domain>/<service>`. When that call fails, Home Assistant
answers with a STATUS AND ALMOST NOTHING ELSE — the reason is written to
Home Assistant's own log and never travels back over REST:

* **400** — `APIDomainServicesView.post` does
  `raise HTTPBadRequest from ServiceNotFound(domain, service)` when the
  service is not in the registry, so the body is aiohttp's stock
  `400: Bad Request`. A schema rejection (voluptuous) lands here too.
  In both cases **the handler never ran**.
* **500** — the handler ran and raised. `HomeAssistantError` and
  `ServiceNotSupported` are not translated by the view at all: they escape to
  aiohttp, which answers `500 Internal Server Error / Server got itself in
  trouble`. The real sentence — "camera.demo_camera does not support record
  service", "Cannot write `/etc/x.jpg`, no access to path;
  `allowlist_external_dirs` may need to be adjusted" — is in the log only.

The **websocket** `call_service` command does not lose it. The same failures
come back as a `result` with `success: false`, carrying HA's machine-readable
code (`not_found`, `invalid_format`, `service_validation_error`,
`home_assistant_error`) and the full message. Measured against 2025.1.4:

    REST  POST services/camera/record          -> 500, body "Server got itself in trouble"
    WS    call_service camera.record           -> home_assistant_error
                                                 "camera.demo_camera does not support record service"

So this module uses **REST for the result and the websocket for the reason**.
REST is kept for the happy path because it returns the list of CHANGED STATES,
which the websocket does not (it returns a context id and nothing else) —
that list is what every command in this harness prints.

Re-issuing a failed call over the websocket means CALLING THE SERVICE A SECOND
TIME, so it is never automatic:

* A **400** is safe to re-issue and is re-issued when asked: nothing ran.
* A **500** means the handler already ran and may have had a partial effect,
  so `call()` never re-issues one on its own. `explain()` will, if the caller
  explicitly asks for it — it is spelled as its own verb precisely so that
  "run this again to find out why" is a decision, not a side effect.

Everything here also does the checks that cost nothing and cannot fail: is the
service in this instance's registry at all (a plain GET), does the entity
exist, is it `unavailable`.
"""

from __future__ import annotations

from typing import Any

from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

# HA's websocket error codes, and what each one actually means for a service
# call. Taken from `homeassistant/components/websocket_api/commands.py`'s
# `handle_call_service` — which maps ServiceNotFound -> not_found,
# vol.Invalid -> invalid_format, ServiceValidationError ->
# service_validation_error and HomeAssistantError -> home_assistant_error.
_CODE_MEANING: dict[str, str] = {
    "not_found": (
        "the service is not registered on this instance — the integration that "
        "provides it is not loaded, or the service was removed in this HA version"
    ),
    "invalid_format": (
        "the arguments did not pass the service's schema — a value has the "
        "wrong type or format"
    ),
    "service_validation_error": (
        "the service exists but this entity does not support it "
        "(its supported_features do not include the required flag)"
    ),
    "home_assistant_error": (
        "the service ran and its handler raised — the message is the handler's own"
    ),
    "unauthorized": "the token's user is not permitted to call this service",
}


def registered_services(client) -> dict[str, list[str]]:
    """Return `{domain: [service, ...]}` for THIS instance's registry.

    `GET /api/services`. This is the authoritative list — a domain's
    `services.yaml` is documentation and can describe services that are not
    registered. On 2025.1.4 `vacuum/services.yaml` documents `turn_on`,
    `turn_off`, `toggle` and `start_pause`, and none of the four is registered;
    calling one is a bare 400.
    """
    data = client.get("services")
    if not isinstance(data, list):
        return {}
    out: dict[str, list[str]] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        domain = entry.get("domain")
        services = entry.get("services")
        if not domain or not isinstance(services, dict):
            continue
        out[str(domain)] = sorted(services.keys())
    return out


def is_registered(client, domain: str, service: str) -> bool:
    """True when `domain.service` is in this instance's service registry."""
    if not domain or not service:
        raise ValueError("domain and service are required")
    return service in registered_services(client).get(domain, [])


def assert_registered(client, domain: str, service: str) -> None:
    """Raise a ValueError naming the miss if `domain.service` is not registered.

    Cheap (one GET) and side-effect free, which is why it can run BEFORE a
    call rather than after a failure.
    """
    registry = registered_services(client)
    if service in registry.get(domain, []):
        return
    if domain not in registry:
        raise ValueError(
            f"no service domain {domain!r} on this instance — the integration "
            f"that provides it is not loaded"
        )
    available = ", ".join(registry[domain]) or "(none)"
    raise ValueError(
        f"{domain}.{service} is not registered on this instance. "
        f"{domain} provides: {available}"
    )


def _entity_note(client, entity_id: str | None) -> str | None:
    """A safe, read-only observation about the target entity, or None."""
    if not entity_id or "." not in entity_id:
        return None
    try:
        state = client.get(f"states/{entity_id}")
    except HomeAssistantError:
        return f"{entity_id} does not exist in the state machine"
    if not isinstance(state, dict):
        return None
    if state.get("state") == "unavailable":
        return f"{entity_id} is currently unavailable"
    return None


def _first_entity_id(payload: dict | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("entity_id")
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)) and value:
        first = value[0]
        return first if isinstance(first, str) else None
    return None


def explain(
    client,
    domain: str,
    service: str,
    service_data: dict | None = None,
) -> dict:
    """Call `domain.service` over the WEBSOCKET and report what HA said.

    **This runs the service.** It is the diagnostic verb: use it when a REST
    call came back as a bare 400/500 and the reason is needed.

    Returns `{"ok": True, "context": …}` on success, or `{"ok": False,
    "code": …, "message": …, "meaning": …}` on failure — `code` being HA's own
    machine-readable code, not a substring match on prose.
    """
    if not domain or not service:
        raise ValueError("domain and service are required")
    payload: dict[str, Any] = {"domain": domain, "service": service}
    if service_data:
        payload["service_data"] = dict(service_data)
    try:
        result = client.ws_call("call_service", payload)
    except HomeAssistantError as exc:
        code = getattr(exc, "code", None)
        message = str(exc)
        # `ws_call` prefixes with "WS command call_service failed: <code> ";
        # strip it so the caller sees HA's sentence, not the transport's.
        marker = f"failed: {code} " if code else None
        if marker and marker in message:
            message = message.split(marker, 1)[1]
        return {
            "ok": False,
            "service": f"{domain}.{service}",
            "code": code,
            "message": message,
            "meaning": _CODE_MEANING.get(code or "", None),
        }
    return {"ok": True, "service": f"{domain}.{service}", "context": result}


def call(
    client,
    domain: str,
    service: str,
    payload: dict | None = None,
    *,
    explain_failures: bool = False,
) -> Any:
    """POST a service call and, when it fails, say why.

    On success this is exactly `client.post("services/<domain>/<service>",
    payload)` — the list of changed states, unchanged.

    On failure the bare status is replaced by a message that names the cause.
    A 400 is diagnosed from the registry (free, and the answer is usually
    "that service does not exist here"); with `explain_failures` it is also
    re-issued over the websocket, which is safe because a 400 means nothing
    ran. A 500 is never re-issued automatically — the handler already ran.
    """
    try:
        return client.post(f"services/{domain}/{service}", payload)
    except HomeAssistantError as exc:
        status = getattr(exc, "status", None)
        if status not in (400, 500):
            raise
        raise _enriched(
            client, domain, service, payload, exc, status, explain_failures
        ) from exc


def _enriched(
    client,
    domain: str,
    service: str,
    payload: dict | None,
    exc: HomeAssistantError,
    status: int | None,
    explain_failures: bool,
) -> HomeAssistantError:
    """Build the replacement error for a bare 400/500 from the service view."""
    lines: list[str] = []
    if status == 400:
        lines.append(
            f"{domain}.{service} was REFUSED BEFORE IT RAN (HTTP 400, no body). "
            f"Either the service is not registered on this instance or the "
            f"arguments failed its schema."
        )
    else:
        lines.append(
            f"{domain}.{service} RAN AND ITS HANDLER RAISED (HTTP 500, no body). "
            f"Home Assistant logged the reason and does not return it over REST."
        )

    # Free, side-effect-free checks.
    try:
        registry = registered_services(client)
    except HomeAssistantError:
        registry = {}
    if registry:
        if domain not in registry:
            lines.append(
                f"there is no {domain!r} service domain on this instance "
                f"(the integration is not loaded)"
            )
        elif service not in registry[domain]:
            lines.append(
                f"{domain}.{service} is NOT in this instance's registry; "
                f"{domain} provides: {', '.join(registry[domain]) or '(none)'}"
            )
    note = _entity_note(client, _first_entity_id(payload))
    if note:
        lines.append(note)

    if explain_failures and status == 400:
        detail = explain(client, domain, service, payload)
        if not detail.get("ok") and detail.get("message"):
            lines.append(f"HA says: {detail['message']} [{detail.get('code')}]")
    elif status == 500:
        lines.append(
            f"re-run `service explain {domain} {service}` to obtain HA's own "
            f"message over the websocket — note that this CALLS THE SERVICE AGAIN"
        )

    return HomeAssistantError("; ".join(lines), status=status)
