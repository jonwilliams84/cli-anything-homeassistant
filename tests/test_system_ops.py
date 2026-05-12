"""Unit tests for cli_anything.homeassistant.core.system_ops.

All tests use FakeClient from conftest.py — no real Home Assistant required.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import system_ops


# ---------------------------------------------------------------------------
# Shared fixtures / constants
# ---------------------------------------------------------------------------

DOMAIN = "some_integration"
ISSUE_ID = "critical_alert"
INTEGRATION = "mqtt"
DEVICE_ID = "abc123device"
CONFIG_ENTRY_ID = "entry_xyz"
TOPIC = "home/temperature"


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestSystemOps:

    # ──────────────────────────────────────────────────── backup_start

    def test_backup_start_happy_path(self, fake_client):
        """backup_start sends backup/start WS command."""
        fake_client.set_ws("backup/start", {})
        result = system_ops.backup_start(fake_client)
        assert fake_client.ws_calls == [
            {"type": "backup/start", "payload": None}
        ]

    def test_backup_start_returns_dict(self, fake_client):
        """backup_start returns a dict."""
        fake_client.set_ws("backup/start", {"status": "ok"})
        result = system_ops.backup_start(fake_client)
        assert isinstance(result, dict)

    # ──────────────────────────────────────────────────── backup_end

    def test_backup_end_happy_path(self, fake_client):
        """backup_end sends backup/end WS command."""
        fake_client.set_ws("backup/end", {})
        result = system_ops.backup_end(fake_client)
        assert fake_client.ws_calls == [
            {"type": "backup/end", "payload": None}
        ]

    def test_backup_end_returns_dict(self, fake_client):
        """backup_end returns a dict."""
        fake_client.set_ws("backup/end", {"status": "ok"})
        result = system_ops.backup_end(fake_client)
        assert isinstance(result, dict)

    # ──────────────────────────────────────────────────── backup_subscribe_events

    def test_backup_subscribe_events_happy_path(self, fake_client):
        """backup_subscribe_events sends backup/subscribe_events WS command."""
        fake_client.set_ws("backup/subscribe_events", {})
        result = system_ops.backup_subscribe_events(fake_client)
        assert fake_client.ws_calls == [
            {"type": "backup/subscribe_events", "payload": None}
        ]

    def test_backup_subscribe_events_returns_dict(self, fake_client):
        """backup_subscribe_events returns a dict."""
        fake_client.set_ws("backup/subscribe_events", {"subscribed": True})
        result = system_ops.backup_subscribe_events(fake_client)
        assert isinstance(result, dict)

    # ──────────────────────────────────────────────────── get_issue_data

    def test_get_issue_data_happy_path(self, fake_client):
        """get_issue_data sends repairs/get_issue_data with domain and issue_id."""
        fake_client.set_ws(
            "repairs/get_issue_data",
            {"issue_data": {"key": "value"}},
        )
        result = system_ops.get_issue_data(
            fake_client, domain=DOMAIN, issue_id=ISSUE_ID
        )
        assert fake_client.ws_calls == [
            {
                "type": "repairs/get_issue_data",
                "payload": {"domain": DOMAIN, "issue_id": ISSUE_ID},
            }
        ]

    def test_get_issue_data_returns_dict(self, fake_client):
        """get_issue_data returns a dict."""
        issue_data = {"severity": "critical", "title": "Test Issue"}
        fake_client.set_ws("repairs/get_issue_data", {"issue_data": issue_data})
        result = system_ops.get_issue_data(
            fake_client, domain=DOMAIN, issue_id=ISSUE_ID
        )
        assert isinstance(result, dict)
        assert "issue_data" in result

    def test_get_issue_data_empty_domain_raises(self, fake_client):
        """get_issue_data raises ValueError when domain is empty."""
        with pytest.raises(ValueError, match="domain"):
            system_ops.get_issue_data(fake_client, domain="", issue_id=ISSUE_ID)

    def test_get_issue_data_none_domain_raises(self, fake_client):
        """get_issue_data raises ValueError when domain is None."""
        with pytest.raises(ValueError, match="domain"):
            system_ops.get_issue_data(fake_client, domain=None, issue_id=ISSUE_ID)

    def test_get_issue_data_empty_issue_id_raises(self, fake_client):
        """get_issue_data raises ValueError when issue_id is empty."""
        with pytest.raises(ValueError, match="issue_id"):
            system_ops.get_issue_data(fake_client, domain=DOMAIN, issue_id="")

    def test_get_issue_data_none_issue_id_raises(self, fake_client):
        """get_issue_data raises ValueError when issue_id is None."""
        with pytest.raises(ValueError, match="issue_id"):
            system_ops.get_issue_data(fake_client, domain=DOMAIN, issue_id=None)

    # ──────────────────────────────────────────────────── ignore_issue

    def test_ignore_issue_happy_path_default_true(self, fake_client):
        """ignore_issue sends repairs/ignore_issue with ignore=True by default."""
        fake_client.set_ws("repairs/ignore_issue", {})
        result = system_ops.ignore_issue(
            fake_client, domain=DOMAIN, issue_id=ISSUE_ID
        )
        assert fake_client.ws_calls == [
            {
                "type": "repairs/ignore_issue",
                "payload": {"domain": DOMAIN, "issue_id": ISSUE_ID, "ignore": True},
            }
        ]

    def test_ignore_issue_happy_path_explicit_false(self, fake_client):
        """ignore_issue sends ignore=False when specified."""
        fake_client.set_ws("repairs/ignore_issue", {})
        result = system_ops.ignore_issue(
            fake_client, domain=DOMAIN, issue_id=ISSUE_ID, ignore=False
        )
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["ignore"] is False

    def test_ignore_issue_returns_dict(self, fake_client):
        """ignore_issue returns a dict."""
        fake_client.set_ws("repairs/ignore_issue", {"status": "ok"})
        result = system_ops.ignore_issue(
            fake_client, domain=DOMAIN, issue_id=ISSUE_ID
        )
        assert isinstance(result, dict)

    def test_ignore_issue_empty_domain_raises(self, fake_client):
        """ignore_issue raises ValueError when domain is empty."""
        with pytest.raises(ValueError, match="domain"):
            system_ops.ignore_issue(fake_client, domain="", issue_id=ISSUE_ID)

    def test_ignore_issue_empty_issue_id_raises(self, fake_client):
        """ignore_issue raises ValueError when issue_id is empty."""
        with pytest.raises(ValueError, match="issue_id"):
            system_ops.ignore_issue(fake_client, domain=DOMAIN, issue_id="")

    # ──────────────────────────────────────────────────── get_manifest

    def test_get_manifest_happy_path(self, fake_client):
        """get_manifest sends manifest/get with integration name."""
        fake_client.set_ws(
            "manifest/get",
            {"version": "2024.5", "requirements": []},
        )
        result = system_ops.get_manifest(fake_client, integration=INTEGRATION)
        assert fake_client.ws_calls == [
            {"type": "manifest/get", "payload": {"integration": INTEGRATION}}
        ]

    def test_get_manifest_returns_dict(self, fake_client):
        """get_manifest returns the manifest dict."""
        manifest = {
            "version": "2024.5",
            "requirements": ["paho-mqtt>=1.0"],
            "domain": "mqtt",
        }
        fake_client.set_ws("manifest/get", manifest)
        result = system_ops.get_manifest(fake_client, integration=INTEGRATION)
        assert isinstance(result, dict)
        assert result.get("version") == "2024.5"

    def test_get_manifest_empty_integration_raises(self, fake_client):
        """get_manifest raises ValueError when integration is empty."""
        with pytest.raises(ValueError, match="integration"):
            system_ops.get_manifest(fake_client, integration="")

    def test_get_manifest_none_integration_raises(self, fake_client):
        """get_manifest raises ValueError when integration is None."""
        with pytest.raises(ValueError, match="integration"):
            system_ops.get_manifest(fake_client, integration=None)

    # ──────────────────────────────────────────────────── list_manifests

    def test_list_manifests_happy_path(self, fake_client):
        """list_manifests sends manifest/list with no payload."""
        fake_client.set_ws(
            "manifest/list",
            {"mqtt": {"version": "2024.5"}, "zwave": {"version": "2024.5"}},
        )
        result = system_ops.list_manifests(fake_client)
        assert fake_client.ws_calls == [
            {"type": "manifest/list", "payload": None}
        ]

    def test_list_manifests_returns_dict(self, fake_client):
        """list_manifests returns a dict of manifests."""
        manifests = {
            "mqtt": {"version": "2024.5", "domain": "mqtt"},
            "zwave": {"version": "2024.5", "domain": "zwave"},
        }
        fake_client.set_ws("manifest/list", manifests)
        result = system_ops.list_manifests(fake_client)
        assert isinstance(result, dict)
        assert "mqtt" in result
        assert result["mqtt"]["version"] == "2024.5"

    # ──────────────────────────────────────────────────── get_analytics

    def test_get_analytics_happy_path(self, fake_client):
        """get_analytics sends analytics WS command with no payload."""
        fake_client.set_ws(
            "analytics",
            {"preferences": {"uuid": "abc"}, "onboarded": True},
        )
        result = system_ops.get_analytics(fake_client)
        assert fake_client.ws_calls == [
            {"type": "analytics", "payload": None}
        ]

    def test_get_analytics_returns_dict_with_preferences(self, fake_client):
        """get_analytics returns dict with preferences and onboarded."""
        analytics_data = {
            "preferences": {"uuid": "xyz123"},
            "onboarded": True,
        }
        fake_client.set_ws("analytics", analytics_data)
        result = system_ops.get_analytics(fake_client)
        assert isinstance(result, dict)
        assert "preferences" in result
        assert "onboarded" in result

    # ──────────────────────────────────────────────────── set_analytics_preferences

    def test_set_analytics_preferences_happy_path(self, fake_client):
        """set_analytics_preferences sends analytics/preferences with dict."""
        prefs = {"uuid": "new-uuid"}
        fake_client.set_ws("analytics/preferences", {})
        result = system_ops.set_analytics_preferences(fake_client, preferences=prefs)
        assert fake_client.ws_calls == [
            {
                "type": "analytics/preferences",
                "payload": {"preferences": prefs},
            }
        ]

    def test_set_analytics_preferences_returns_dict(self, fake_client):
        """set_analytics_preferences returns a dict."""
        prefs = {"uuid": "test-uuid"}
        fake_client.set_ws("analytics/preferences", {"status": "ok"})
        result = system_ops.set_analytics_preferences(fake_client, preferences=prefs)
        assert isinstance(result, dict)

    def test_set_analytics_preferences_non_dict_raises(self, fake_client):
        """set_analytics_preferences raises ValueError if preferences is not a dict."""
        with pytest.raises(ValueError, match="preferences must be a dict"):
            system_ops.set_analytics_preferences(fake_client, preferences="invalid")

    def test_set_analytics_preferences_empty_dict_raises(self, fake_client):
        """set_analytics_preferences raises ValueError if preferences dict is empty."""
        with pytest.raises(ValueError, match="cannot be empty"):
            system_ops.set_analytics_preferences(fake_client, preferences={})

    # ──────────────────────────────────────────────────── application_credentials_config

    def test_application_credentials_config_happy_path(self, fake_client):
        """application_credentials_config sends application_credentials/config."""
        fake_client.set_ws(
            "application_credentials/config",
            {"integrations": ["oauth2", "custom"]},
        )
        result = system_ops.application_credentials_config(fake_client)
        assert fake_client.ws_calls == [
            {"type": "application_credentials/config", "payload": None}
        ]

    def test_application_credentials_config_returns_dict(self, fake_client):
        """application_credentials_config returns a dict."""
        fake_client.set_ws(
            "application_credentials/config",
            {"integrations": ["google", "github"]},
        )
        result = system_ops.application_credentials_config(fake_client)
        assert isinstance(result, dict)

    # ──────────────────────────────────────────────────── application_credentials_config_entry

    def test_application_credentials_config_entry_happy_path(self, fake_client):
        """application_credentials_config_entry sends with config_entry_id."""
        fake_client.set_ws(
            "application_credentials/config_entry",
            {"oauth": {"client_id": "xyz"}},
        )
        result = system_ops.application_credentials_config_entry(
            fake_client, config_entry_id=CONFIG_ENTRY_ID
        )
        assert fake_client.ws_calls == [
            {
                "type": "application_credentials/config_entry",
                "payload": {"config_entry_id": CONFIG_ENTRY_ID},
            }
        ]

    def test_application_credentials_config_entry_returns_dict(self, fake_client):
        """application_credentials_config_entry returns a dict."""
        fake_client.set_ws("application_credentials/config_entry", {"data": {}})
        result = system_ops.application_credentials_config_entry(
            fake_client, config_entry_id=CONFIG_ENTRY_ID
        )
        assert isinstance(result, dict)

    def test_application_credentials_config_entry_empty_id_raises(self, fake_client):
        """application_credentials_config_entry raises ValueError for empty id."""
        with pytest.raises(ValueError, match="config_entry_id"):
            system_ops.application_credentials_config_entry(
                fake_client, config_entry_id=""
            )

    def test_application_credentials_config_entry_none_id_raises(self, fake_client):
        """application_credentials_config_entry raises ValueError for None id."""
        with pytest.raises(ValueError, match="config_entry_id"):
            system_ops.application_credentials_config_entry(
                fake_client, config_entry_id=None
            )

    # ──────────────────────────────────────────────────── mqtt_subscribe

    def test_mqtt_subscribe_happy_path_default_qos(self, fake_client):
        """mqtt_subscribe sends mqtt/subscribe with default qos=0."""
        fake_client.set_ws("mqtt/subscribe", {})
        result = system_ops.mqtt_subscribe(fake_client, topic=TOPIC)
        assert fake_client.ws_calls == [
            {"type": "mqtt/subscribe", "payload": {"topic": TOPIC, "qos": 0}}
        ]

    def test_mqtt_subscribe_happy_path_explicit_qos(self, fake_client):
        """mqtt_subscribe accepts qos 0, 1, or 2."""
        fake_client.set_ws("mqtt/subscribe", {})
        for qos_val in (0, 1, 2):
            fake_client.ws_calls.clear()
            result = system_ops.mqtt_subscribe(fake_client, topic=TOPIC, qos=qos_val)
            payload = fake_client.ws_calls[-1]["payload"]
            assert payload["qos"] == qos_val

    def test_mqtt_subscribe_returns_dict(self, fake_client):
        """mqtt_subscribe returns a dict."""
        fake_client.set_ws("mqtt/subscribe", {"subscribed": True})
        result = system_ops.mqtt_subscribe(fake_client, topic=TOPIC)
        assert isinstance(result, dict)

    def test_mqtt_subscribe_empty_topic_raises(self, fake_client):
        """mqtt_subscribe raises ValueError when topic is empty."""
        with pytest.raises(ValueError, match="topic"):
            system_ops.mqtt_subscribe(fake_client, topic="")

    def test_mqtt_subscribe_none_topic_raises(self, fake_client):
        """mqtt_subscribe raises ValueError when topic is None."""
        with pytest.raises(ValueError, match="topic"):
            system_ops.mqtt_subscribe(fake_client, topic=None)

    def test_mqtt_subscribe_invalid_qos_raises(self, fake_client):
        """mqtt_subscribe raises ValueError for qos not in {0,1,2}."""
        with pytest.raises(ValueError, match="qos must be 0, 1, or 2"):
            system_ops.mqtt_subscribe(fake_client, topic=TOPIC, qos=3)

        with pytest.raises(ValueError, match="qos must be 0, 1, or 2"):
            system_ops.mqtt_subscribe(fake_client, topic=TOPIC, qos=-1)

    # ──────────────────────────────────────────────────── mqtt_device_debug_info

    def test_mqtt_device_debug_info_happy_path(self, fake_client):
        """mqtt_device_debug_info sends mqtt/device/debug_info with device_id."""
        fake_client.set_ws(
            "mqtt/device/debug_info",
            {"device_id": DEVICE_ID, "entities": []},
        )
        result = system_ops.mqtt_device_debug_info(
            fake_client, device_id=DEVICE_ID
        )
        assert fake_client.ws_calls == [
            {
                "type": "mqtt/device/debug_info",
                "payload": {"device_id": DEVICE_ID},
            }
        ]

    def test_mqtt_device_debug_info_returns_dict(self, fake_client):
        """mqtt_device_debug_info returns a dict with device info."""
        debug_info = {
            "device_id": DEVICE_ID,
            "entities": [
                {"entity_id": "sensor.test", "discovery_hash": None}
            ],
        }
        fake_client.set_ws("mqtt/device/debug_info", debug_info)
        result = system_ops.mqtt_device_debug_info(
            fake_client, device_id=DEVICE_ID
        )
        assert isinstance(result, dict)
        assert result.get("device_id") == DEVICE_ID

    def test_mqtt_device_debug_info_empty_device_id_raises(self, fake_client):
        """mqtt_device_debug_info raises ValueError when device_id is empty."""
        with pytest.raises(ValueError, match="device_id"):
            system_ops.mqtt_device_debug_info(fake_client, device_id="")

    def test_mqtt_device_debug_info_none_device_id_raises(self, fake_client):
        """mqtt_device_debug_info raises ValueError when device_id is None."""
        with pytest.raises(ValueError, match="device_id"):
            system_ops.mqtt_device_debug_info(fake_client, device_id=None)
