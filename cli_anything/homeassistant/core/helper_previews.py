"""Live-config preview WebSocket subscriptions for config-flow helpers.

Each of the seven helper domains below registers a ``<domain>/start_preview``
WS subscription command in its config flow.  When called, HA begins streaming
``event`` messages back to the caller containing the preview state of a helper
entity **before** the flow is committed.

This module wraps those subscription commands as proper ``ws_subscribe`` calls
so callers receive the live event stream.

WS subscription commands covered:
  group/start_preview
  generic_camera/start_preview
  mold_indicator/start_preview
  statistics/start_preview
  threshold/start_preview
  time_date/start_preview
  switch_as_x/start_preview
"""

from __future__ import annotations

import threading
from typing import Callable

from cli_anything.homeassistant.core._ws_subscribe_utils import (
    resolve_stop_event as _resolve_stop_event,
    wrap_with_max_events as _wrap_with_max_events,
)

# Valid flow_type values accepted by all domains.
_VALID_FLOW_TYPES = frozenset({"config_flow", "options_flow"})

# Domains supported by start_helper_preview (the generic dispatcher).
_PREVIEW_DOMAINS = frozenset({
    "group",
    "generic_camera",
    "mold_indicator",
    "statistics",
    "threshold",
    "time_date",
    "switch_as_x",
})


def _validate_preview_args(flow_id: str, flow_type: str, user_input: dict) -> None:
    """Validate the three common preview arguments.

    Raises ``ValueError`` on any of:
      - *flow_type* not in ``{"config_flow", "options_flow"}``
      - *flow_id* is empty
      - *user_input* is not a non-empty dict
    """
    if flow_type not in _VALID_FLOW_TYPES:
        raise ValueError(
            f"flow_type must be 'config_flow' or 'options_flow', got {flow_type!r}"
        )
    if not flow_id:
        raise ValueError("flow_id must be a non-empty string")
    if not isinstance(user_input, dict) or not user_input:
        raise ValueError("user_input must be a non-empty dict")


def _subscribe_preview(
    client,
    msg_type: str,
    flow_id: str,
    flow_type: str,
    user_input: dict,
    on_event: Callable,
    stop_event: threading.Event | None,
    max_events: int | None,
) -> None:
    """Validate, build payload, and start a WS subscription for a preview command."""
    _validate_preview_args(flow_id, flow_type, user_input)
    if not callable(on_event):
        raise ValueError("on_event must be callable")
    payload = {
        "flow_id": flow_id,
        "flow_type": flow_type,
        "user_input": user_input,
    }
    stop, owns_stop = _resolve_stop_event(stop_event, max_events)
    wrapper = _wrap_with_max_events(on_event, stop, owns_stop, max_events)
    client.ws_subscribe(msg_type, payload, wrapper, stop)


# ════════════════════════════════════════════════════════════════════════
# Per-domain preview wrappers
# ════════════════════════════════════════════════════════════════════════

def start_group_preview(
    client,
    *,
    flow_id: str,
    flow_type: str,
    user_input: dict,
    on_event: Callable,
    stop_event: threading.Event | None = None,
    max_events: int | None = None,
) -> None:
    """Start a live group-helper preview via WS ``group/start_preview``.

    HA schema requires ``flow_id``, ``flow_type``, and ``user_input``.
    ``flow_type`` must be ``"config_flow"`` or ``"options_flow"``.

    Blocks until ``stop_event`` is set or ``max_events`` preview events are
    received and forwarded to ``on_event``.

    Raises
    ------
    ValueError
        For invalid ``flow_type``, empty ``flow_id``, non-dict ``user_input``,
        non-callable ``on_event``, or missing ``stop_event`` / ``max_events``.
    """
    _subscribe_preview(client, "group/start_preview",
                       flow_id, flow_type, user_input,
                       on_event, stop_event, max_events)


def start_generic_camera_preview(
    client,
    *,
    flow_id: str,
    flow_type: str,
    user_input: dict,
    on_event: Callable,
    stop_event: threading.Event | None = None,
    max_events: int | None = None,
) -> None:
    """Start a live generic-camera preview via WS ``generic_camera/start_preview``.

    HA schema: ``flow_id`` is Required; ``flow_type`` and ``user_input`` are
    Optional in the HA source (defaults to config_flow / empty dict).  This
    wrapper requires all three for consistency with the other helpers.

    ``flow_type`` must be ``"config_flow"`` or ``"options_flow"``.

    Raises
    ------
    ValueError
        For invalid args or missing stop/max.
    """
    _subscribe_preview(client, "generic_camera/start_preview",
                       flow_id, flow_type, user_input,
                       on_event, stop_event, max_events)


def start_mold_indicator_preview(
    client,
    *,
    flow_id: str,
    flow_type: str,
    user_input: dict,
    on_event: Callable,
    stop_event: threading.Event | None = None,
    max_events: int | None = None,
) -> None:
    """Start a live mold-indicator preview via WS ``mold_indicator/start_preview``.

    HA schema requires ``flow_id``, ``flow_type``, and ``user_input``.
    ``flow_type`` must be ``"config_flow"`` or ``"options_flow"``.

    Raises
    ------
    ValueError
        For invalid args or missing stop/max.
    """
    _subscribe_preview(client, "mold_indicator/start_preview",
                       flow_id, flow_type, user_input,
                       on_event, stop_event, max_events)


def start_statistics_preview(
    client,
    *,
    flow_id: str,
    flow_type: str,
    user_input: dict,
    on_event: Callable,
    stop_event: threading.Event | None = None,
    max_events: int | None = None,
) -> None:
    """Start a live statistics-sensor preview via WS ``statistics/start_preview``.

    HA schema requires ``flow_id``, ``flow_type``, and ``user_input``.
    ``flow_type`` must be ``"config_flow"`` or ``"options_flow"``.

    Raises
    ------
    ValueError
        For invalid args or missing stop/max.
    """
    _subscribe_preview(client, "statistics/start_preview",
                       flow_id, flow_type, user_input,
                       on_event, stop_event, max_events)


def start_threshold_preview(
    client,
    *,
    flow_id: str,
    flow_type: str,
    user_input: dict,
    on_event: Callable,
    stop_event: threading.Event | None = None,
    max_events: int | None = None,
) -> None:
    """Start a live threshold binary-sensor preview via WS ``threshold/start_preview``.

    HA schema requires ``flow_id``, ``flow_type``, and ``user_input``.
    ``flow_type`` must be ``"config_flow"`` or ``"options_flow"``.

    Raises
    ------
    ValueError
        For invalid args or missing stop/max.
    """
    _subscribe_preview(client, "threshold/start_preview",
                       flow_id, flow_type, user_input,
                       on_event, stop_event, max_events)


def start_time_date_preview(
    client,
    *,
    flow_id: str,
    flow_type: str,
    user_input: dict,
    on_event: Callable,
    stop_event: threading.Event | None = None,
    max_events: int | None = None,
) -> None:
    """Start a live time/date sensor preview via WS ``time_date/start_preview``.

    HA schema requires ``flow_id``, ``flow_type``, and ``user_input``.
    ``flow_type`` must be ``"config_flow"`` or ``"options_flow"``.

    Note: the HA source for this component only accepts ``"config_flow"`` in
    its voluptuous schema (no options flow).  This wrapper still validates
    against the standard set ``{"config_flow", "options_flow"}`` so callers
    get consistent errors; HA itself will reject ``"options_flow"`` at the
    server side.

    Raises
    ------
    ValueError
        For invalid args or missing stop/max.
    """
    _subscribe_preview(client, "time_date/start_preview",
                       flow_id, flow_type, user_input,
                       on_event, stop_event, max_events)


def start_switch_as_x_preview(
    client,
    *,
    flow_id: str,
    flow_type: str,
    user_input: dict,
    on_event: Callable,
    stop_event: threading.Event | None = None,
    max_events: int | None = None,
) -> None:
    """Start a live switch-as-x preview via WS ``switch_as_x/start_preview``.

    HA schema requires ``flow_id``, ``flow_type``, and ``user_input``.
    ``flow_type`` must be ``"config_flow"`` or ``"options_flow"``.

    Raises
    ------
    ValueError
        For invalid args or missing stop/max.
    """
    _subscribe_preview(client, "switch_as_x/start_preview",
                       flow_id, flow_type, user_input,
                       on_event, stop_event, max_events)


# ════════════════════════════════════════════════════════════════════════
# Generic dispatcher
# ════════════════════════════════════════════════════════════════════════

def start_helper_preview(
    client,
    *,
    domain: str,
    flow_id: str,
    flow_type: str,
    user_input: dict,
    on_event: Callable,
    stop_event: threading.Event | None = None,
    max_events: int | None = None,
) -> None:
    """Dispatch a ``<domain>/start_preview`` WS subscription.

    A generic alternative to calling the per-domain functions directly.
    ``domain`` must be one of the seven supported preview domains:

      group, generic_camera, mold_indicator, statistics,
      threshold, time_date, switch_as_x

    Raises ``ValueError`` for an unsupported domain or invalid arguments.

    Blocks until ``stop_event`` is set or ``max_events`` events are received.
    """
    if domain not in _PREVIEW_DOMAINS:
        raise ValueError(
            f"domain {domain!r} is not a supported preview domain; "
            f"must be one of {sorted(_PREVIEW_DOMAINS)}"
        )
    _subscribe_preview(client, f"{domain}/start_preview",
                       flow_id, flow_type, user_input,
                       on_event, stop_event, max_events)
