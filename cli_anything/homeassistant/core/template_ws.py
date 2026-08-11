"""Template rendering over the WebSocket API — typed results + dependencies.

The REST endpoint behind ``template render`` (:mod:`core.template`) returns the
rendered template as **text** and tells you nothing about what it depends on.
The WebSocket ``render_template`` command — the one the template editor and the
template helper preview use — is strictly richer:

* the result keeps its **native type** (``int``, ``float``, ``bool``, ``list``,
  ``dict``), because HA renders with ``strict``/native typing and sends it as
  JSON rather than stringifying it;
* every render carries a **listeners** block: the exact entity ids, domains and
  time triggers the template subscribed to. That is the dependency graph of the
  template — the thing you need to answer "why did my template sensor not
  update?" — and it is not obtainable any other way;
* the subscription **re-renders live**, so a template can be watched like a
  sensor without creating a template helper first.

WS commands wrapped
-------------------
* ``render_template`` — subscribe, render, and stream re-renders. HA replies
  with an ack ``result`` and then event messages shaped
  ``{"result": <value>, "listeners": {"all": bool, "entities": [...],
  "domains": [...], "time": bool}}``. With ``report_errors`` on, a failing
  template instead yields ``{"error": "...", "level": "ERROR"}``.

Public API
----------
* :func:`render`
* :func:`render_value`
* :func:`listeners`
* :func:`entities_used`
* :func:`depends_on`
* :func:`validate`
* :func:`watch`
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from cli_anything.homeassistant.core._ws_subscribe_utils import (
    resolve_stop_event as _resolve_stop_event,
    validate_callable as _validate_callable,
    wrap_with_max_events as _wrap_with_max_events,
)

WS_RENDER_TEMPLATE = "render_template"

_EMPTY_LISTENERS: dict[str, Any] = {
    "all": False,
    "entities": [],
    "domains": [],
    "time": False,
}


# ────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ────────────────────────────────────────────────────────────────────────────


def _validate_template(template: str) -> str:
    if not isinstance(template, str) or not template.strip():
        raise ValueError("template must be a non-empty string")
    return template


def _validate_variables(variables: Any) -> dict | None:
    if variables is None:
        return None
    if not isinstance(variables, dict):
        raise ValueError("variables must be a mapping")
    return variables or None


def _validate_timeout(timeout_seconds: float) -> None:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be > 0")


def build_payload(
    template: str,
    *,
    variables: dict | None = None,
    strict: bool = False,
    report_errors: bool = True,
    timeout: float | None = None,
) -> dict:
    """Return the ``render_template`` WS payload for *template*.

    Exposed so callers (and ``--dry-run``) can inspect exactly what would be
    sent without opening a socket.
    """
    payload: dict[str, Any] = {"template": _validate_template(template)}
    variables = _validate_variables(variables)
    if variables is not None:
        payload["variables"] = variables
    if strict:
        payload["strict"] = True
    if report_errors:
        payload["report_errors"] = True
    if timeout is not None:
        if timeout <= 0:
            raise ValueError("timeout must be > 0")
        payload["timeout"] = float(timeout)
    return payload


def _first_event(client, payload: dict, timeout_seconds: float) -> dict:
    """Open the subscription, return its first event, then unsubscribe.

    ``ws_subscribe`` blocks until the stop event is set, so it runs on a
    worker thread; the first event sets the stop flag and the worker unwinds
    (sending ``unsubscribe_events`` on its way out).
    """
    _validate_timeout(timeout_seconds)
    events: list[Any] = []
    errors: list[BaseException] = []
    stop = threading.Event()

    def on_message(event: Any) -> None:
        events.append(event)
        stop.set()

    def run() -> None:
        try:
            client.ws_subscribe(WS_RENDER_TEMPLATE, payload, on_message, stop)
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller's thread
            errors.append(exc)
            stop.set()

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout=timeout_seconds)
    stop.set()

    if events:
        first = events[0]
        return first if isinstance(first, dict) else {"result": first}
    if errors:
        raise errors[0]
    raise TimeoutError(f"render_template produced no result within {timeout_seconds}s")


def normalize_listeners(raw: Any) -> dict:
    """Return a listeners block with stable keys and sorted lists."""
    if not isinstance(raw, dict):
        return dict(_EMPTY_LISTENERS)
    entities = raw.get("entities") or []
    domains = raw.get("domains") or []
    return {
        "all": bool(raw.get("all", False)),
        "entities": sorted(str(e) for e in entities),
        "domains": sorted(str(d) for d in domains),
        "time": bool(raw.get("time", False)),
    }


# ────────────────────────────────────────────────────────────────────────────
# Public functions
# ────────────────────────────────────────────────────────────────────────────


def render(
    client,
    template: str,
    *,
    variables: dict | None = None,
    strict: bool = False,
    report_errors: bool = True,
    timeout_seconds: float = 10.0,
) -> dict:
    """Render *template* once and return ``{"result", "listeners"}``.

    Parameters
    ----------
    client:
        Home Assistant client exposing ``ws_subscribe``.
    template:
        The Jinja2 template source.
    variables:
        Optional variables made available to the template.
    strict:
        Fail on undefined variables instead of rendering them empty.
    report_errors:
        Ask HA to send template errors as events (default) so they surface as
        a :exc:`ValueError` here rather than a dropped subscription.
    timeout_seconds:
        How long to wait for the first render.

    Returns
    -------
    dict
        ``{"result": <native value>, "listeners": {...}}``.

    Raises
    ------
    ValueError
        If the template is empty, or HA reported a template error.
    TimeoutError
        If HA sent no render within *timeout_seconds*.
    """
    payload = build_payload(
        template, variables=variables, strict=strict, report_errors=report_errors
    )
    event = _first_event(client, payload, timeout_seconds)
    if "error" in event and "result" not in event:
        raise ValueError(f"template error: {event['error']}")
    return {
        "result": event.get("result"),
        "listeners": normalize_listeners(event.get("listeners")),
    }


def render_value(
    client,
    template: str,
    *,
    variables: dict | None = None,
    strict: bool = False,
    timeout_seconds: float = 10.0,
) -> Any:
    """Return just the rendered value, keeping its native JSON type."""
    return render(
        client,
        template,
        variables=variables,
        strict=strict,
        timeout_seconds=timeout_seconds,
    )["result"]


def listeners(
    client,
    template: str,
    *,
    variables: dict | None = None,
    timeout_seconds: float = 10.0,
) -> dict:
    """Return the dependency block for *template* (entities / domains / time).

    ``all: true`` means the template listens to *every* state change (usually a
    ``states`` iteration) — the expensive case worth knowing about before you
    turn the template into a helper.
    """
    return render(client, template, variables=variables, timeout_seconds=timeout_seconds)[
        "listeners"
    ]


def entities_used(
    client,
    template: str,
    *,
    variables: dict | None = None,
    timeout_seconds: float = 10.0,
) -> list[str]:
    """Return the sorted entity ids *template* re-renders on."""
    return listeners(client, template, variables=variables, timeout_seconds=timeout_seconds)[
        "entities"
    ]


def depends_on(
    client,
    template: str,
    entity_id: str,
    *,
    variables: dict | None = None,
    timeout_seconds: float = 10.0,
) -> bool:
    """Return ``True`` if *template* re-renders when *entity_id* changes.

    Covers the three ways HA can subscribe: the explicit entity id, the
    entity's whole domain, or the catch-all ``all`` listener.
    """
    if not entity_id or "." not in entity_id:
        raise ValueError(f"entity_id must look like 'domain.object_id', got: {entity_id!r}")
    block = listeners(client, template, variables=variables, timeout_seconds=timeout_seconds)
    if block["all"]:
        return True
    if entity_id in block["entities"]:
        return True
    return entity_id.split(".", 1)[0] in block["domains"]


def validate(
    client,
    template: str,
    *,
    variables: dict | None = None,
    strict: bool = False,
    timeout_seconds: float = 10.0,
) -> dict:
    """Check that *template* renders, without raising.

    Returns ``{"valid": bool, "error": str|None, "result": ..., "listeners": ...}``
    — the pre-flight for ``template-helper create``.
    """
    try:
        rendered = render(
            client,
            template,
            variables=variables,
            strict=strict,
            timeout_seconds=timeout_seconds,
        )
    except ValueError as exc:
        return {"valid": False, "error": str(exc), "result": None, "listeners": None}
    except TimeoutError as exc:
        return {"valid": False, "error": str(exc), "result": None, "listeners": None}
    return {
        "valid": True,
        "error": None,
        "result": rendered["result"],
        "listeners": rendered["listeners"],
    }


def watch(
    client,
    template: str,
    on_render: Callable,
    *,
    variables: dict | None = None,
    strict: bool = False,
    report_errors: bool = True,
    stop_event: threading.Event | None = None,
    max_events: int | None = None,
) -> None:
    """Stream re-renders of *template* to *on_render* until stopped.

    Each callback argument is the raw event dict: ``{"result", "listeners"}``
    or, when ``report_errors`` is on and the template blows up,
    ``{"error", "level"}``.

    Raises
    ------
    ValueError
        If *on_render* is not callable, or neither ``stop_event`` nor
        ``max_events`` was supplied.
    """
    _validate_callable(on_render, "on_render")
    payload = build_payload(
        template, variables=variables, strict=strict, report_errors=report_errors
    )
    stop, owns_stop = _resolve_stop_event(stop_event, max_events)
    wrapper = _wrap_with_max_events(on_render, stop, owns_stop, max_events)
    client.ws_subscribe(WS_RENDER_TEMPLATE, payload, wrapper, stop)
