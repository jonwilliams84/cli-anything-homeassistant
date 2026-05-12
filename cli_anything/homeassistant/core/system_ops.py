"""System operations grab-bag: backup hooks, repairs detail, manifest, analytics,
application credentials, MQTT debug.

This module wraps WebSocket commands that don't fit neatly into a single domain
(e.g. backup/start and backup/end are lifecycle hooks; analytics and MQTT debug
are standalone utilities).
"""

from __future__ import annotations


# ════════════════════════════════════════════════════════════════════════
# Backup hooks — lifecycle markers
# ════════════════════════════════════════════════════════════════════════

def backup_start(client) -> dict:
    """Mark backup as in-progress. WS ``backup/start``."""
    return client.ws_call("backup/start", None)


def backup_end(client) -> dict:
    """Mark backup as complete. WS ``backup/end``."""
    return client.ws_call("backup/end", None)


def backup_subscribe_events(client) -> dict:
    """Subscribe to backup state-change events. WS ``backup/subscribe_events``.

    Returns subscription confirmation (exact format depends on HA websocket layer).
    """
    return client.ws_call("backup/subscribe_events", None)


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
    return client.ws_call("manifest/list", None)


# ════════════════════════════════════════════════════════════════════════
# Analytics — user analytics preferences
# ════════════════════════════════════════════════════════════════════════

def get_analytics(client) -> dict:
    """Fetch analytics preferences and onboarded status. WS ``analytics``.

    Returns a dict with ``preferences`` (dict) and ``onboarded`` (bool).
    """
    return client.ws_call("analytics", None)


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
    return client.ws_call("application_credentials/config", None)


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

def mqtt_subscribe(client, *, topic: str, qos: int = 0) -> dict:
    """Subscribe to an MQTT topic. WS ``mqtt/subscribe``.

    `topic` — MQTT topic string (required).
    `qos` — Quality of service: 0, 1, or 2 (default: 0).

    Returns subscription confirmation.
    """
    if not topic:
        raise ValueError("topic required")
    if qos not in (0, 1, 2):
        raise ValueError(f"qos must be 0, 1, or 2; got {qos!r}")
    return client.ws_call("mqtt/subscribe",
                          {"topic": topic, "qos": qos})


def mqtt_device_debug_info(client, *, device_id: str) -> dict:
    """Fetch MQTT debug info for a device. WS ``mqtt/device/debug_info``.

    Returns a dict with MQTT-related metadata for the device.
    """
    if not device_id:
        raise ValueError("device_id required")
    return client.ws_call("mqtt/device/debug_info", {"device_id": device_id})
