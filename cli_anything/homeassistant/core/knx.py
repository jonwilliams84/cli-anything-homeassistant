"""KNX — the ``knx`` integration's WebSocket surface.

THE GAP THIS CLOSES
    This is the last mainstream bus-integration surface in the harness that
    had no command group: ``zwave_js`` (v1.54), ``matter`` (v1.56), the
    Supervisor (v1.52) and ``zha`` all had one, but KNX — the bus protocol
    most European building installations run on — was reachable only through
    raw state reads. Every function below passes through to one of the 14
    WS commands ``homeassistant/components/knx/websocket.py`` registers, plus
    the device registry read the entity store's devices surface through
    (2025.1.x). The integration is admin-only upstream (every command is
    ``@require_admin``); the client does not duplicate the check, it just
    translates what a non-admin connection gets back.

THE FOURTEEN WEBSOCKET COMMANDS
    = information = ===========================================================
    ``knx/info``                 — xknx version, tunnel connection state,
                                   current address, loaded project metadata
    ``knx/group_monitor_info``   — the group monitor's recent telegrams
    ``knx/group_telegrams``      — telegrams per group address
    ``knx/subscribe_telegrams``  — a LIVE telegram feed (a subscription)
    = project (ETS) = =========================================================
    ``knx/get_knx_project``      — the parsed ETS project, whole
    ``knx/project_file_process`` — parse an ETS project file uploaded via
                                   ``file upload``; needs the file's password
    ``knx/project_file_remove``  — drop the stored project
    = entity store = =========================================================
    The KNX panel's entity store: the UI creates and edits ``switch`` and
    ``light`` entities around group addresses, and these commands are what
    its "Entities" view drives. Platforms are limited upstream to
    ``SUPPORTED_PLATFORMS_UI`` — switch and light; anything else is a
    server-side validation error, which every function here surfaces as-is.
    ``knx/validate_entity``     — validate WITHOUT writing (the safe dry run)
    ``knx/create_entity``       — create + load the entity
    ``knx/update_entity``       — update + reload it
    ``knx/delete_entity``       — remove it (destructive; confirmation-gated
                                  in the CLI)
    ``knx/get_entity_entries``  — every entity the store manages
    ``knx/get_entity_config``   — one entity's store configuration
    = devices = ==============================================================
    ``knx/create_device``        — a KNX pseudo-device row to collect entities
                                   under (``knx_vdev_…`` identifier)

THE NAME/DEVICE_INFO SPLIT
    The base entity schema demands ONE of ``name`` or ``device_info`` — a
    bare platform + data is refused server-side with a message
    ("One of `Device` or `Name` is required") that names neither option's
    CLI spelling. :func:`validate_entity` / :func:`create_entity` /
    :func:`update_entity` reject the same case client-side and say what to
    pass; ``validate`` is the always-safe rehearsal for the other two.

WHEN THE INTEGRATION IS NOT LOADED
    With no KNX bus configured, integration setup fails (or never runs) and
    the ``knx/…`` commands are never registered: the websocket layer answers
    ``unknown_command`` — the same code a typo gets. On a Core install the
    absence is doubly real: the integration requires the ``xknx`` and
    ``xknxproject`` packages, and without them it cannot even import. Every
    function raises :data:`ABSENT_NOTE`, which names both routes; the CLI's
    ``knx available`` turns the same condition into an answer with exit 0.
    The one half-loaded edge — the integration registered its commands but
    its module vanished from ``hass.data`` — answers
    ``home_assistant_error`` with the literal message "KNX integration not
    loaded."; the guard re-raises the same note for that too.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from cli_anything.homeassistant.core._ws_subscribe_utils import (
    resolve_stop_event,
    validate_callable,
    wrap_with_max_events,
)
from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

DOMAIN = "knx"

#: ``unknown_command`` means the ``knx`` integration is not loaded: usually no
#: KNX bus is configured; on a Core install the integration additionally needs
#: the ``xknx`` / ``xknxproject`` packages to be importable. Nothing in this
#: group can work without it.
ABSENT_NOTE = (
    "This Home Assistant has no KNX bus configured: the `knx` integration is "
    "not loaded, so it never registered its `knx/…` websocket commands. On a "
    "Core install the integration also needs the `xknx` and `xknxproject` "
    "packages to be importable. Confirm it independently with "
    "`system components` — and set the integration up in the HA UI "
    "(Settings → Devices & Services → Add Integration → KNX) first."
)

#: The literal message HA's ``provide_knx`` decorator sends when the
#: integration IS loaded enough to register its commands but its module is
#: gone from ``hass.data``. Distinct wire code (``home_assistant_error``),
#: same practical meaning as an absent integration.
NOT_LOADED_MESSAGE = "KNX integration not loaded."

#: The platforms the KNX panel's entity store supports upstream.
SUPPORTED_PLATFORMS = ("switch", "light")

#: The two identifiers the base entity schema accepts (one is REQUIRED).
ENTITY_IDENTITY_KEYS = ("name", "device_info")


# ── plumbing ────────────────────────────────────────────────────────────────


def _is_absent(exc: HomeAssistantError) -> bool:
    if exc.code == "unknown_command":
        return True
    # The half-loaded edge: registered commands, missing module.
    return exc.code == "home_assistant_error" and NOT_LOADED_MESSAGE in str(exc)


def _raise_absent() -> None:
    raise HomeAssistantError(ABSENT_NOTE, code="unknown_command")


def _integration_loaded(client) -> bool:
    """Is ``knx`` in the loaded-components list? (the independent read the
    error note points at).

    Returns True when the check itself fails, so the ORIGINAL error is what
    the caller sees rather than a wrong "not loaded" claim.
    """
    try:
        cfg = client.ws_call("get_config") or {}
    except HomeAssistantError:
        return True
    return DOMAIN in (cfg.get("components") or [])


def _ws(client, msg_type: str, payload: dict | None = None) -> Any:
    """One ``knx/…`` websocket call, with the absent-integration guard."""
    try:
        return client.ws_call(msg_type, payload)
    except HomeAssistantError as exc:
        if _is_absent(exc):
            _raise_absent()
        raise


def _error_from(exc: HomeAssistantError, action: str) -> HomeAssistantError:
    """Re-raise a knx server-side validation failure with the action named.

    The entity-store commands answer failures as
    ``home_assistant_error`` with the store's message — knowing WHICH of
    validate/create/update/delete failed matters when several commands were
    batched in a script.
    """
    return HomeAssistantError(f"knx {action}: {exc}", code=exc.code)


# ── availability ────────────────────────────────────────────────────────────


def available(client) -> dict:
    """Is the ``knx`` integration loaded? A READ — 'no' is an answer.

    Checks the integration's presence in the loaded-components list (the same
    independent confirmation the error note points at), so the answer never
    depends on a websocket round-trip to a command that does not exist.
    """
    cfg = client.ws_call("get_config") or {}
    loaded = DOMAIN in (cfg.get("components") or [])
    return {
        "available": loaded,
        "note": ("knx is loaded; every `knx` command works here." if loaded else ABSENT_NOTE),
    }


# ── information ─────────────────────────────────────────────────────────────


def info(client) -> dict:
    """WS ``knx/info`` — xknx version, tunnel state, current address, project.

    Also the cheapest "is the bus actually connected" probe once the
    integration IS loaded: ``connected`` is the tunnel's live state, not the
    config entry's presence.
    """
    return _ws(client, "knx/info")


def group_monitor(client) -> dict:
    """WS ``knx/group_monitor_info`` — the group monitor's recent telegrams.

    What the KNX panel's group monitor boots with: recent telegrams plus
    whether a project is loaded to decode against.
    """
    return _ws(client, "knx/group_monitor_info")


def group_telegrams(client) -> list[dict]:
    """WS ``knx/group_telegrams`` — the latest telegram per group address.

    One row per group address (the most recent wins), unlike
    :func:`group_monitor` which is the recent telegram log.
    """
    return _ws(client, "knx/group_telegrams")


def subscribe_telegrams(
    client,
    on_event: Callable,
    stop_event: threading.Event | None = None,
    max_events: int | None = None,
) -> None:
    """WS ``knx/subscribe_telegrams`` — a LIVE feed of in/out telegrams.

    Unlike every other command here this does not return: it streams each
    telegram dict as the dispatcher publishes it, forwarding to *on_event*,
    until *stop_event* is set (or *max_events* arrived, when *stop_event* is
    owned by this module). The one non-admin subscription — upstream's split,
    not this module's.
    """
    validate_callable(on_event, "on_event")
    stop, owns_stop = resolve_stop_event(stop_event, max_events)
    wrapper = wrap_with_max_events(on_event, stop, owns_stop, max_events)
    try:
        client.ws_subscribe("knx/subscribe_telegrams", {}, wrapper, stop)
    except HomeAssistantError as exc:
        if _is_absent(exc):
            _raise_absent()
        raise


# ── project (ETS) ───────────────────────────────────────────────────────────


def project_get(client) -> dict:
    """WS ``knx/get_knx_project`` — the whole parsed ETS project.

    Large: this is the projection the group monitor decodes against. Use
    ``file upload`` + :func:`project_process` to (re)load one first.
    """
    return _ws(client, "knx/get_knx_project")


def project_process(client, file_id: str, password: str) -> dict:
    """WS ``knx/project_file_process`` — parse an uploaded ETS project file.

    ``file_id`` is the staging-area id ``file upload`` in this harness mints;
    ``password`` is the password the project was exported with. An empty
    string is a legitimate answer for an unprotected export. Failures come
    back as ``home_assistant_error`` carrying the XKNXProject message —
    wrong passwords and malformed projects look identical here.
    """
    if not (file_id or "").strip():
        raise ValueError("file_id is required (`file upload` mints one)")
    result = _ws(
        client,
        "knx/project_file_process",
        {"file_id": file_id, "password": password or ""},
    )
    if result:
        return {"result": result}
    return {
        "result": "ok",
        "note": "project parsed and stored; `knx project-get` reads it back",
    }


def project_remove(client) -> dict:
    """WS ``knx/project_file_remove`` — drop the stored ETS project.

    Group-monitor decoding degrades to raw addresses until another project
    is processed. Success is an empty result; the wrapper says what it means.
    """
    _ws(client, "knx/project_file_remove")
    return {
        "result": "ok",
        "note": "project removed; the group monitor decodes to raw "
        "addresses until `knx project-process` stores another one",
    }


# ── entity store ────────────────────────────────────────────────────────────


def _entity_payload(
    platform: str,
    data: dict,
    name: str | None,
    device_info: str | None,
    entity_category: str | None,
) -> dict:
    """Build the shared entity-store payload and enforce its one-of rule.

    ``validate``/``create``/``update`` share CREATE/UPDATE base schema: a
    platform, the platform's data dict, and one of ``name`` or
    ``device_info``. Enforcing that here (with the CLI spellings of both
    options in the message) front-runs a server-side refusal that names
    neither.
    """
    if not (platform or "").strip():
        raise ValueError("platform is required (knx entity store: switch, light)")
    platform = platform.strip().lower()
    if platform not in SUPPORTED_PLATFORMS:
        raise ValueError(
            f"platform {platform!r} is not one of the KNX entity-store "
            f"platforms ({', '.join(SUPPORTED_PLATFORMS)})"
        )
    if not isinstance(data, dict):
        raise ValueError("data must be a JSON object of platform data")
    if not name and not device_info:
        raise ValueError(
            "one of name or device_info is required — pass --name (the entity's "
            "friendly name) or --device (the device_info uuid the store attaches "
            "the entity to)"
        )
    payload: dict[str, Any] = {"platform": platform, "data": dict(data)}
    if name:
        payload["name"] = name
    if device_info:
        payload["device_info"] = device_info
    if entity_category:
        if entity_category not in ("config", "diagnostic"):
            raise ValueError(
                f"entity_category must be 'config' or 'diagnostic', got {entity_category!r}"
            )
        payload["entity_category"] = entity_category
    return payload


def validate_entity(
    client,
    platform: str,
    data: dict,
    *,
    name: str | None = None,
    device_info: str | None = None,
    entity_category: str | None = None,
) -> Any:
    """WS ``knx/validate_entity`` — check an entity-store payload, write nothing.

    The safe rehearsal for :func:`create_entity` / :func:`update_entity`:
    returns HA's validation result — ``{"success": true}`` or the error dict
    — with no store state touched. Invalid input the server would reject
    comes back structured, not as a raised error, because upstream answers a
    validation failure with send_result, not send_error.
    """
    payload = _entity_payload(platform, data, name, device_info, entity_category)
    return _ws(client, "knx/validate_entity", payload)


def create_entity(
    client,
    platform: str,
    data: dict,
    *,
    name: str | None = None,
    device_info: str | None = None,
    entity_category: str | None = None,
) -> Any:
    """WS ``knx/create_entity`` — create + load the entity in the store.

    A success carries the new entity_id. Invalid input surfaces the same
    structured validation dict :func:`validate_entity` gets; a store failure
    (e.g. an id collision) is raised as ``home_assistant_error``. Rehearse
    with ``knx validate-entity`` first — this WRITES.
    """
    payload = _entity_payload(platform, data, name, device_info, entity_category)
    try:
        return _ws(client, "knx/create_entity", payload)
    except HomeAssistantError as exc:
        raise _error_from(exc, "create-entity") from exc


def update_entity(
    client,
    entity_id: str,
    platform: str,
    data: dict,
    *,
    name: str | None = None,
    device_info: str | None = None,
    entity_category: str | None = None,
) -> Any:
    """WS ``knx/update_entity`` — update + reload an entity from the store.

    ``entity_id`` is the id the store created it under (``knx entities``
    lists them). Like upstream's options flows this REPLACES the platform
    data — a partial ``data`` does not merge with what is stored; ``knx
    entity-config`` reads the current values to build the full payload on.
    """
    entity_id = (entity_id or "").strip()
    if not entity_id:
        raise ValueError("entity_id of the store entity to update is required")
    payload = _entity_payload(platform, data, name, device_info, entity_category)
    payload["entity_id"] = entity_id
    try:
        return _ws(client, "knx/update_entity", payload)
    except HomeAssistantError as exc:
        raise _error_from(exc, "update-entity") from exc


def delete_entity(client, entity_id: str) -> dict:
    """WS ``knx/delete_entity`` — remove the entity from the store.

    Destructive and one-way: the entity and its configuration are gone; the
    group addresses it used are untouched on the bus. Success is an empty
    result; the wrapper says what it means. The CLI confirmation-gates this.
    """
    entity_id = (entity_id or "").strip()
    if not entity_id:
        raise ValueError("entity_id of the store entity to delete is required")
    _ws(client, "knx/delete_entity", {"entity_id": entity_id})
    return {"result": "ok", "note": f"{entity_id} removed from the KNX entity store"}


def list_entities(client) -> list[dict]:
    """WS ``knx/get_entity_entries`` — every entity the store manages."""
    return _ws(client, "knx/get_entity_entries")


def entity_config(client, entity_id: str) -> Any:
    """WS ``knx/get_entity_config`` — one store entity's configuration.

    The full platform data the store holds — the payload to pass back to
    ``knx update-entity`` (which REPLACES rather than merges).
    """
    entity_id = (entity_id or "").strip()
    if not entity_id:
        raise ValueError("entity_id of the store entity is required")
    try:
        return _ws(client, "knx/get_entity_config", {"entity_id": entity_id})
    except HomeAssistantError as exc:
        raise _error_from(exc, "entity-config") from exc


# ── devices ─────────────────────────────────────────────────────────────────


def create_device(client, name: str, *, area_id: str | None = None) -> dict:
    """WS ``knx/create_device`` — a KNX pseudo-device to group entities under.

    Returns the device-registry row (its ``id`` is what ``--device`` /
    ``device_info`` of the entity store attaches to). A success with no KNX
    integration loaded is impossible — the pseudo-device hangs off the
    integration's config entry.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("the device name is required")
    payload: dict[str, Any] = {"name": name}
    if area_id:
        payload["area_id"] = area_id
    return _ws(client, "knx/create_device", payload)
