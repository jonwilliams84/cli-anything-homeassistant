"""System operations grab-bag: backup hooks, repairs detail, manifest, analytics,
application credentials, MQTT debug.

This module wraps WebSocket commands that don't fit neatly into a single domain
(e.g. backup/start and backup/end are lifecycle hooks; analytics and MQTT debug
are standalone utilities).
"""

from __future__ import annotations

import threading
from typing import Callable

from cli_anything.homeassistant.core._ws_subscribe_utils import (
    resolve_stop_event as _resolve_stop_event,
    wrap_with_max_events as _wrap_with_max_events,
)


# ════════════════════════════════════════════════════════════════════════
# Backup hooks — lifecycle markers
# ════════════════════════════════════════════════════════════════════════

def backup_start(client) -> dict:
    """Mark backup as in-progress. WS ``backup/start``."""
    return client.ws_call("backup/start", {})


def backup_end(client) -> dict:
    """Mark backup as complete. WS ``backup/end``."""
    return client.ws_call("backup/end", {})


def backup_subscribe_events(
    client,
    *,
    on_event: Callable,
    stop_event: threading.Event | None = None,
    max_events: int | None = None,
) -> None:
    """Subscribe to backup state-change events. WS ``backup/subscribe_events``.

    Blocks until ``stop_event`` is set or ``max_events`` have been received.

    Parameters
    ----------
    client:
        Home Assistant client instance exposing ``ws_subscribe``.
    on_event:
        Callable invoked with each backup event dict received from HA.
    stop_event:
        :class:`threading.Event` whose set-state terminates the loop. At
        least one of ``stop_event`` or ``max_events`` must be supplied.
    max_events:
        Stop automatically after this many events. Ignored when
        ``stop_event`` is also supplied.

    Raises
    ------
    ValueError
        If neither ``stop_event`` nor ``max_events`` is provided, or if
        ``on_event`` is not callable.
    """
    if not callable(on_event):
        raise ValueError("on_event must be callable")
    stop, owns_stop = _resolve_stop_event(stop_event, max_events)
    wrapper = _wrap_with_max_events(on_event, stop, owns_stop, max_events)
    client.ws_subscribe("backup/subscribe_events", None, wrapper, stop)


# ════════════════════════════════════════════════════════════════════════
# Repairs — issue management
# ════════════════════════════════════════════════════════════════════════

def get_issue_data(client, *, domain: str, issue_id: str) -> dict:
    """Fetch issue data (problem details) for a domain/issue_id pair.

    WS ``repairs/get_issue_data``. Returns a dict with ``issue_data`` key.
    """
    if not domain:
        raise ValueError("domain required")
    if not issue_id:
        raise ValueError("issue_id required")
    return client.ws_call("repairs/get_issue_data",
                          {"domain": domain, "issue_id": issue_id})


def ignore_issue(client, *, domain: str, issue_id: str, ignore: bool = True) -> dict:
    """Mark (or unmark) an issue as ignored. WS ``repairs/ignore_issue``.

    Returns a confirmation dict (exact structure varies by HA version).
    """
    if not domain:
        raise ValueError("domain required")
    if not issue_id:
        raise ValueError("issue_id required")
    return client.ws_call("repairs/ignore_issue",
                          {"domain": domain, "issue_id": issue_id,
                           "ignore": ignore})


# ════════════════════════════════════════════════════════════════════════
# Manifest — integration metadata
# ════════════════════════════════════════════════════════════════════════

def get_manifest(client, *, integration: str) -> dict:
    """Fetch manifest (integration metadata) for a given integration domain.

    WS ``manifest/get``. Returns the manifest dict (version, requirements, etc.).
    """
    if not integration:
        raise ValueError("integration required")
    return client.ws_call("manifest/get", {"integration": integration})


def list_manifests(client) -> dict:
    """List all available integration manifests. WS ``manifest/list``.

    Returns a dict mapping domain → manifest object.
    """
    return client.ws_call("manifest/list", {})


# ════════════════════════════════════════════════════════════════════════
# Analytics — user analytics preferences
# ════════════════════════════════════════════════════════════════════════

def get_analytics(client) -> dict:
    """Fetch analytics preferences and onboarded status. WS ``analytics``.

    Returns a dict with ``preferences`` (dict) and ``onboarded`` (bool).
    """
    return client.ws_call("analytics", {})


def set_analytics_preferences(client, *, preferences: dict) -> dict:
    """Update analytics preferences. WS ``analytics/preferences``.

    `preferences` — dict with analytics configuration keys (see HA docs).
    Returns confirmation dict.
    """
    if not isinstance(preferences, dict):
        raise ValueError("preferences must be a dict")
    if not preferences:
        raise ValueError("preferences dict cannot be empty")
    return client.ws_call("analytics/preferences", {"preferences": preferences})


# ════════════════════════════════════════════════════════════════════════
# Application credentials — OAuth integrations
# ════════════════════════════════════════════════════════════════════════

def application_credentials_config(client) -> dict:
    """Fetch supported OAuth integrations. WS ``application_credentials/config``.

    Returns a list of integration domains that support application credentials.
    """
    return client.ws_call("application_credentials/config", {})


def application_credentials_config_entry(client, *, config_entry_id: str) -> dict:
    """Fetch OAuth config for a specific config entry.

    WS ``application_credentials/config_entry``. Returns the entry's OAuth setup.
    """
    if not config_entry_id:
        raise ValueError("config_entry_id required")
    return client.ws_call("application_credentials/config_entry",
                          {"config_entry_id": config_entry_id})


# ════════════════════════════════════════════════════════════════════════
# MQTT debug — topic subscription and device debug info
# ════════════════════════════════════════════════════════════════════════

def mqtt_subscribe(
    client,
    *,
    topic: str,
    qos: int = 0,
    on_event: Callable,
    stop_event: threading.Event | None = None,
    max_events: int | None = None,
) -> None:
    """Subscribe to an MQTT topic. WS ``mqtt/subscribe``.

    Blocks until ``stop_event`` is set or ``max_events`` have been received.

    Parameters
    ----------
    client:
        Home Assistant client instance exposing ``ws_subscribe``.
    topic:
        MQTT topic string (required, non-empty).
    qos:
        Quality of service: 0, 1, or 2 (default: 0).
    on_event:
        Callable invoked with each MQTT message dict received from HA.
    stop_event:
        :class:`threading.Event` whose set-state terminates the loop. At
        least one of ``stop_event`` or ``max_events`` must be supplied.
    max_events:
        Stop automatically after this many events. Ignored when
        ``stop_event`` is also supplied.

    Raises
    ------
    ValueError
        If ``topic`` is empty, ``qos`` is not in {0, 1, 2}, neither
        ``stop_event`` nor ``max_events`` is provided, or ``on_event``
        is not callable.
    """
    if not topic:
        raise ValueError("topic required")
    if qos not in (0, 1, 2):
        raise ValueError(f"qos must be 0, 1, or 2; got {qos!r}")
    if not callable(on_event):
        raise ValueError("on_event must be callable")
    stop, owns_stop = _resolve_stop_event(stop_event, max_events)
    wrapper = _wrap_with_max_events(on_event, stop, owns_stop, max_events)
    client.ws_subscribe("mqtt/subscribe", {"topic": topic, "qos": qos}, wrapper, stop)


def mqtt_device_debug_info(client, *, device_id: str) -> dict:
    """Fetch MQTT debug info for a device. WS ``mqtt/device/debug_info``.

    Returns a dict with MQTT-related metadata for the device.
    """
    if not device_id:
        raise ValueError("device_id required")
    return client.ws_call("mqtt/device/debug_info", {"device_id": device_id})
