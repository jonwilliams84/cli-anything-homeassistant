"""Live-config preview WebSocket commands for config-flow helpers.

Each of the seven helper domains below registers a ``<domain>/start_preview``
WS subscription command in its config flow.  When called, HA begins streaming
``event`` messages back to the caller containing the preview state of a helper
entity **before** the flow is committed.

This module wraps those subscription commands as one-shot WS sends (the
initial subscription message is recorded in ``client.ws_calls`` for
testability).

**Streaming note** — these are *subscribe* commands, not simple request/
response calls.  The functions here send only the *initial* subscription
message.  Callers that want the live event stream must consume it via
``client.ws_subscribe`` (or equivalent).  Example::

    sub_id = client.ws_subscribe(
        "group/start_preview",
        {
            "flow_id": flow_id,
            "flow_type": "config_flow",
            "user_input": user_input,
        },
        callback=on_event,
    )

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


def _send_preview(client, msg_type: str, flow_id: str,
                  flow_type: str, user_input: dict) -> dict:
    """Validate, build payload, and dispatch the WS subscription message."""
    _validate_preview_args(flow_id, flow_type, user_input)
    payload = {
        "flow_id": flow_id,
        "flow_type": flow_type,
        "user_input": user_input,
    }
    return client.ws_call(msg_type, payload)


# ════════════════════════════════════════════════════════════════════════
# Per-domain preview wrappers
# ════════════════════════════════════════════════════════════════════════

def start_group_preview(
    client,
    *,
    flow_id: str,
    flow_type: str,
    user_input: dict,
) -> dict:
    """Start a live group-helper preview via WS ``group/start_preview``.

    HA schema requires ``flow_id``, ``flow_type``, and ``user_input``.
    ``flow_type`` must be ``"config_flow"`` or ``"options_flow"``.

    Returns the raw WS response (an empty dict from FakeClient; a
    subscription-ack from a real HA instance).  Full streaming of preview
    events requires ``client.ws_subscribe``; see module docstring.
    """
    return _send_preview(client, "group/start_preview",
                         flow_id, flow_type, user_input)


def start_generic_camera_preview(
    client,
    *,
    flow_id: str,
    flow_type: str,
    user_input: dict,
) -> dict:
    """Start a live generic-camera preview via WS ``generic_camera/start_preview``.

    HA schema: ``flow_id`` is Required; ``flow_type`` and ``user_input`` are
    Optional in the HA source (defaults to config_flow / empty dict).  This
    wrapper requires all three for consistency with the other helpers.

    ``flow_type`` must be ``"config_flow"`` or ``"options_flow"``.

    Returns the raw WS response.  Full streaming requires ``client.ws_subscribe``.
    """
    return _send_preview(client, "generic_camera/start_preview",
                         flow_id, flow_type, user_input)


def start_mold_indicator_preview(
    client,
    *,
    flow_id: str,
    flow_type: str,
    user_input: dict,
) -> dict:
    """Start a live mold-indicator preview via WS ``mold_indicator/start_preview``.

    HA schema requires ``flow_id``, ``flow_type``, and ``user_input``.
    ``flow_type`` must be ``"config_flow"`` or ``"options_flow"``.

    Returns the raw WS response.  Full streaming requires ``client.ws_subscribe``.
    """
    return _send_preview(client, "mold_indicator/start_preview",
                         flow_id, flow_type, user_input)


def start_statistics_preview(
    client,
    *,
    flow_id: str,
    flow_type: str,
    user_input: dict,
) -> dict:
    """Start a live statistics-sensor preview via WS ``statistics/start_preview``.

    HA schema requires ``flow_id``, ``flow_type``, and ``user_input``.
    ``flow_type`` must be ``"config_flow"`` or ``"options_flow"``.

    Returns the raw WS response.  Full streaming requires ``client.ws_subscribe``.
    """
    return _send_preview(client, "statistics/start_preview",
                         flow_id, flow_type, user_input)


def start_threshold_preview(
    client,
    *,
    flow_id: str,
    flow_type: str,
    user_input: dict,
) -> dict:
    """Start a live threshold binary-sensor preview via WS ``threshold/start_preview``.

    HA schema requires ``flow_id``, ``flow_type``, and ``user_input``.
    ``flow_type`` must be ``"config_flow"`` or ``"options_flow"``.

    Returns the raw WS response.  Full streaming requires ``client.ws_subscribe``.
    """
    return _send_preview(client, "threshold/start_preview",
                         flow_id, flow_type, user_input)


def start_time_date_preview(
    client,
    *,
    flow_id: str,
    flow_type: str,
    user_input: dict,
) -> dict:
    """Start a live time/date sensor preview via WS ``time_date/start_preview``.

    HA schema requires ``flow_id``, ``flow_type``, and ``user_input``.
    ``flow_type`` must be ``"config_flow"`` or ``"options_flow"``.

    Note: the HA source for this component only accepts ``"config_flow"`` in
    its voluptuous schema (no options flow).  This wrapper still validates
    against the standard set ``{"config_flow", "options_flow"}`` so callers
    get consistent errors; HA itself will reject ``"options_flow"`` at the
    server side.

    Returns the raw WS response.  Full streaming requires ``client.ws_subscribe``.
    """
    return _send_preview(client, "time_date/start_preview",
                         flow_id, flow_type, user_input)


def start_switch_as_x_preview(
    client,
    *,
    flow_id: str,
    flow_type: str,
    user_input: dict,
) -> dict:
    """Start a live switch-as-x preview via WS ``switch_as_x/start_preview``.

    HA schema requires ``flow_id``, ``flow_type``, and ``user_input``.
    ``flow_type`` must be ``"config_flow"`` or ``"options_flow"``.

    Returns the raw WS response.  Full streaming requires ``client.ws_subscribe``.
    """
    return _send_preview(client, "switch_as_x/start_preview",
                         flow_id, flow_type, user_input)


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
) -> dict:
    """Dispatch a ``<domain>/start_preview`` WS subscription message.

    A generic alternative to calling the per-domain functions directly.
    ``domain`` must be one of the seven supported preview domains:

      group, generic_camera, mold_indicator, statistics,
      threshold, time_date, switch_as_x

    Raises ``ValueError`` for an unsupported domain or invalid arguments.

    Returns the raw WS response.  Full streaming requires ``client.ws_subscribe``.
    """
    if domain not in _PREVIEW_DOMAINS:
        raise ValueError(
            f"domain {domain!r} is not a supported preview domain; "
            f"must be one of {sorted(_PREVIEW_DOMAINS)}"
        )
    return _send_preview(client, f"{domain}/start_preview",
                         flow_id, flow_type, user_input)
