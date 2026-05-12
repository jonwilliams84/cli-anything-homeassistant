"""Trace debugger — breakpoints and step/continue/stop for running scripts/automations.

Wraps the seven HA WebSocket commands that power the in-flight script debugger.
These operate on *running* (or paused) executions, complementing the
persisted-trace commands in ``trace_debug.py`` (trace/list, trace/get,
trace/contexts).

Supported WS message types
---------------------------
trace/debug/breakpoint/list       — list_breakpoints
trace/debug/breakpoint/subscribe  — subscribe_breakpoints  (streaming)
trace/debug/breakpoint/set        — set_breakpoint
trace/debug/breakpoint/clear      — clear_breakpoint
trace/debug/step                  — step_execution
trace/debug/continue              — continue_execution
trace/debug/stop                  — stop_execution

Streaming note
--------------
``subscribe_breakpoints`` sends a single ``trace/debug/breakpoint/subscribe``
WS message.  In a live HA WebSocket connection the server acknowledges
immediately with ``{"type": "result", "success": true}`` and then pushes
``{"type": "event", ...}`` messages containing ``{domain, item_id, run_id,
node}`` each time a breakpoint is hit.  The FakeClient used in tests records
the subscription message in ``ws_calls`` but does not simulate the event
stream — callers integrating against real HA must handle the event stream
themselves (e.g. via an async WebSocket loop).

Domain validation
-----------------
``domain`` must be ``"automation"`` or ``"script"`` for all commands that
accept it.  Non-empty validation is applied to all string parameters;
``run_id``, ``item_id``, and ``node`` must never be empty strings.
"""

from __future__ import annotations

_VALID_DOMAINS = frozenset({"automation", "script"})


# ────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ────────────────────────────────────────────────────────────────────────────

def _validate_domain(domain: str) -> None:
    if domain not in _VALID_DOMAINS:
        raise ValueError(
            f"domain must be one of {sorted(_VALID_DOMAINS)}, got {domain!r}"
        )


def _validate_nonempty(value: str, name: str) -> None:
    if not value:
        raise ValueError(f"{name} must be a non-empty string")


# ────────────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────────────

def list_breakpoints(client) -> list[dict]:
    """Return all currently registered breakpoints via ``trace/debug/breakpoint/list``.

    HA returns a list of dicts, each with ``domain``, ``item_id``, ``node``,
    and optionally ``run_id``.

    Returns an empty list when HA returns a non-list response.
    """
    result = client.ws_call("trace/debug/breakpoint/list", {})
    return result if isinstance(result, list) else []


def subscribe_breakpoints(client) -> dict:
    """Subscribe to breakpoint-hit events via ``trace/debug/breakpoint/subscribe``.

    Sends the subscription WS message and returns whatever the underlying
    transport delivers synchronously (the initial ACK in a real connection,
    or the FakeClient stub response in tests).

    Streaming: after the initial ACK, HA pushes ``event`` messages with
    ``{domain, item_id, run_id, node}`` each time a running script/automation
    hits a registered breakpoint.  The caller is responsible for consuming
    those event messages.

    Unsubscribing (closing the connection) causes HA to clear all breakpoints
    and send a ``SCRIPT_DEBUG_CONTINUE_ALL`` signal, resuming any paused runs.
    """
    result = client.ws_call("trace/debug/breakpoint/subscribe", {})
    return result if isinstance(result, dict) else {}


def set_breakpoint(
    client,
    *,
    domain: str,
    item_id: str,
    node: str,
    run_id: str | None = None,
) -> dict:
    """Register a breakpoint via ``trace/debug/breakpoint/set``.

    Parameters
    ----------
    domain:   ``"automation"`` or ``"script"``.
    item_id:  Slug/id of the automation or script (e.g. ``"morning_lights"``).
    node:     The trace-node path at which to break (e.g. ``"action/0"``).
    run_id:   Optional — restrict the breakpoint to a specific run.

    HA requires an active ``trace/debug/breakpoint/subscribe`` subscription
    before accepting ``set`` calls; without one it returns an error.

    Returns the dict sent back by HA (typically ``{"result": true}``).
    """
    _validate_domain(domain)
    _validate_nonempty(item_id, "item_id")
    _validate_nonempty(node, "node")
    if run_id is not None:
        _validate_nonempty(run_id, "run_id")
    payload: dict = {"domain": domain, "item_id": item_id, "node": node}
    if run_id is not None:
        payload["run_id"] = run_id
    result = client.ws_call("trace/debug/breakpoint/set", payload)
    return result if isinstance(result, dict) else {}


def clear_breakpoint(
    client,
    *,
    domain: str,
    item_id: str,
    node: str,
    run_id: str | None = None,
) -> dict:
    """Remove a breakpoint via ``trace/debug/breakpoint/clear``.

    Parameters match ``set_breakpoint``.  ``run_id`` must match the value
    used when setting the breakpoint (or be omitted if none was given).

    Returns the dict sent back by HA (typically ``{"result": true}``).
    """
    _validate_domain(domain)
    _validate_nonempty(item_id, "item_id")
    _validate_nonempty(node, "node")
    if run_id is not None:
        _validate_nonempty(run_id, "run_id")
    payload: dict = {"domain": domain, "item_id": item_id, "node": node}
    if run_id is not None:
        payload["run_id"] = run_id
    result = client.ws_call("trace/debug/breakpoint/clear", payload)
    return result if isinstance(result, dict) else {}


def step_execution(
    client,
    *,
    domain: str,
    item_id: str,
    run_id: str,
) -> dict:
    """Advance a paused run by one step via ``trace/debug/step``.

    The run must already be paused at a breakpoint.  HA advances execution
    to the next action node and re-pauses, firing another breakpoint-hit
    event.

    Parameters
    ----------
    domain:   ``"automation"`` or ``"script"``.
    item_id:  Slug/id of the automation or script.
    run_id:   The run to step (required; obtained from a breakpoint-hit event).

    Returns the dict sent back by HA.
    """
    _validate_domain(domain)
    _validate_nonempty(item_id, "item_id")
    _validate_nonempty(run_id, "run_id")
    result = client.ws_call(
        "trace/debug/step",
        {"domain": domain, "item_id": item_id, "run_id": run_id},
    )
    return result if isinstance(result, dict) else {}


def continue_execution(
    client,
    *,
    domain: str,
    item_id: str,
    run_id: str,
) -> dict:
    """Resume a paused run until the next breakpoint via ``trace/debug/continue``.

    The run must already be paused at a breakpoint.  Execution resumes and
    will pause again at the next registered breakpoint, or run to completion.

    Parameters
    ----------
    domain:   ``"automation"`` or ``"script"``.
    item_id:  Slug/id of the automation or script.
    run_id:   The run to resume (required).

    Returns the dict sent back by HA.
    """
    _validate_domain(domain)
    _validate_nonempty(item_id, "item_id")
    _validate_nonempty(run_id, "run_id")
    result = client.ws_call(
        "trace/debug/continue",
        {"domain": domain, "item_id": item_id, "run_id": run_id},
    )
    return result if isinstance(result, dict) else {}


def stop_execution(
    client,
    *,
    domain: str,
    item_id: str,
    run_id: str,
) -> dict:
    """Abort a paused run via ``trace/debug/stop``.

    The run must be paused at a breakpoint.  HA terminates the run
    immediately; no further actions execute.

    Parameters
    ----------
    domain:   ``"automation"`` or ``"script"``.
    item_id:  Slug/id of the automation or script.
    run_id:   The run to stop (required).

    Returns the dict sent back by HA.
    """
    _validate_domain(domain)
    _validate_nonempty(item_id, "item_id")
    _validate_nonempty(run_id, "run_id")
    result = client.ws_call(
        "trace/debug/stop",
        {"domain": domain, "item_id": item_id, "run_id": run_id},
    )
    return result if isinstance(result, dict) else {}
