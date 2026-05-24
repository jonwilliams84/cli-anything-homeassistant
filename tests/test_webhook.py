"""Unit tests for cli_anything.homeassistant.core.webhook."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cli_anything.homeassistant.core import webhook


_REGISTERED = [
    {"webhook_id": "abc123", "name": "Door", "domain": "automation",
     "local_only": True, "allowed_methods": ["POST"]},
    {"webhook_id": "xyz999", "name": "Phone", "domain": "mobile_app",
     "local_only": False, "allowed_methods": ["POST", "PUT", "GET"]},
]


class TestWebhookList:

    def test_list_registered_happy(self, fake_client):
        fake_client.set_ws("webhook/list", _REGISTERED)
        result = webhook.list_registered(fake_client)
        assert result == _REGISTERED
        assert fake_client.ws_calls[0]["type"] == "webhook/list"

    def test_list_registered_empty(self, fake_client):
        assert webhook.list_registered(fake_client) == []

    def test_list_automation_webhooks_finds_trigger(self, fake_client):
        fake_client.set("GET", "states", [
            {"entity_id": "automation.door_open", "state": "on",
             "attributes": {"id": "auto-1", "friendly_name": "Door open"}},
            {"entity_id": "light.kitchen", "state": "on", "attributes": {}},
        ])
        fake_client.set("GET", "config/automation/config/auto-1", {
            "alias": "Door open",
            "trigger": [{"platform": "webhook", "webhook_id": "abc123",
                          "allowed_methods": ["POST"], "local_only": True}],
        })
        result = webhook.list_automation_webhooks(fake_client)
        assert len(result) == 1
        row = result[0]
        assert row["webhook_id"] == "abc123"
        assert row["automation_id"] == "auto-1"
        assert row["entity_id"] == "automation.door_open"
        assert row["allowed_methods"] == ["POST"]

    def test_list_automation_webhooks_handles_triggers_plural(self, fake_client):
        # HA newer schema uses "triggers" (plural) — both should work
        fake_client.set("GET", "states", [
            {"entity_id": "automation.foo", "state": "on",
             "attributes": {"id": "auto-9"}},
        ])
        fake_client.set("GET", "config/automation/config/auto-9", {
            "triggers": {"platform": "webhook", "webhook_id": "wid-9"},
        })
        result = webhook.list_automation_webhooks(fake_client)
        assert result[0]["webhook_id"] == "wid-9"

    def test_list_automation_webhooks_skips_non_webhook_triggers(self, fake_client):
        fake_client.set("GET", "states", [
            {"entity_id": "automation.time", "state": "on",
             "attributes": {"id": "auto-2"}},
        ])
        fake_client.set("GET", "config/automation/config/auto-2", {
            "trigger": [{"platform": "time", "at": "08:00"}],
        })
        assert webhook.list_automation_webhooks(fake_client) == []

    def test_list_webhooks_aggregates(self, fake_client):
        fake_client.set_ws("webhook/list", _REGISTERED)
        fake_client.set_ws("mobile_app/list_for_user", [
            {"webhook_id": "mob-1", "device_name": "iphone"},
        ])
        fake_client.set("GET", "states", [
            {"entity_id": "automation.a", "state": "on",
             "attributes": {"id": "aid-1"}},
        ])
        fake_client.set("GET", "config/automation/config/aid-1", {
            "trigger": [{"platform": "webhook", "webhook_id": "auto-wid"}],
        })
        result = webhook.list_webhooks(fake_client)
        assert "registered" in result
        assert "automations" in result
        assert "mobile_app" in result
        # 2 registered + 1 mobile + 1 automation = 4 unique
        assert result["summary"]["total_unique"] == 4

    def test_list_webhooks_skip_automations(self, fake_client):
        fake_client.set_ws("webhook/list", _REGISTERED)
        result = webhook.list_webhooks(fake_client,
                                        include_automations=False,
                                        include_mobile=False)
        assert result["automations"] == []
        assert result["mobile_app"] == []


class TestWebhookTrigger:

    def _fake_session_client(self, registered=None):
        """Build a client object with the methods trigger() needs."""
        client = MagicMock()
        client.base_url = "http://localhost:8123"
        client.timeout = 30
        client.session = MagicMock()
        client.ws_call = MagicMock(return_value=registered or _REGISTERED)
        return client

    def test_trigger_post_happy(self):
        client = self._fake_session_client()
        client.post = MagicMock(return_value={"ack": True})

        out = webhook.trigger(client, webhook_id="abc123",
                               method="POST", body={"x": 1})
        assert out["ok"] is True
        assert out["webhook_id"] == "abc123"
        assert out["method"] == "POST"
        client.post.assert_called_once_with("webhook/abc123", {"x": 1})

    def test_trigger_unknown_webhook_id_guarded(self):
        client = self._fake_session_client(registered=_REGISTERED)
        with pytest.raises(ValueError, match="not in the registered list"):
            webhook.trigger(client, webhook_id="nope-id")

    def test_trigger_unknown_webhook_id_unguarded(self):
        client = self._fake_session_client()
        client.post = MagicMock(return_value={"ack": True})
        out = webhook.trigger(client, webhook_id="nope-id",
                               guard_registered=False)
        assert out["ok"] is True
        client.post.assert_called_once_with("webhook/nope-id", None)

    def test_trigger_bad_method(self):
        client = self._fake_session_client()
        with pytest.raises(ValueError, match="method"):
            webhook.trigger(client, webhook_id="abc123",
                             method="DELETE", guard_registered=False)

    def test_trigger_missing_webhook_id(self):
        with pytest.raises(ValueError, match="webhook_id"):
            webhook.trigger(MagicMock(), webhook_id="")

    def test_trigger_get_via_session(self):
        client = self._fake_session_client()
        resp = SimpleNamespace(
            ok=True, status_code=200,
            content=b'{"ok":true}',
            text='{"ok":true}',
            json=lambda: {"ok": True},
            headers={},
        )
        client.session.get = MagicMock(return_value=resp)
        out = webhook.trigger(client, webhook_id="abc123",
                               method="GET", guard_registered=False)
        assert out["status"] == 200
        assert out["response"] == {"ok": True}
        client.session.get.assert_called_once()


class TestWebhookMisc:

    def test_generate_id_returns_token(self):
        out = webhook.generate_id()
        assert "webhook_id" in out
        assert isinstance(out["webhook_id"], str)
        assert len(out["webhook_id"]) >= 24

    def test_generate_id_is_unique(self):
        # Two consecutive generations should not collide
        a = webhook.generate_id()["webhook_id"]
        b = webhook.generate_id()["webhook_id"]
        assert a != b


class TestCloudhooks:

    def test_cloudhooks_dict_shape_flattens(self, fake_client):
        fake_client.set_ws("cloud/cloudhooks", {
            "abc123": {"cloudhook_url": "https://hooks.nabu.casa/abc123",
                        "cloudhook_id": "cid-1"},
            "xyz999": "https://hooks.nabu.casa/xyz999",
        })
        result = webhook.cloudhooks(fake_client)
        assert len(result) == 2
        rows = {r["webhook_id"]: r for r in result}
        assert rows["abc123"]["cloudhook_url"] == "https://hooks.nabu.casa/abc123"
        assert rows["xyz999"]["cloudhook_url"] == "https://hooks.nabu.casa/xyz999"

    def test_cloudhooks_empty(self, fake_client):
        # No cloud component → ws_call returns the default [] response
        assert webhook.cloudhooks(fake_client) == []

    def test_cloudhook_create_payload(self, fake_client):
        fake_client.set_ws("cloud/cloudhook/create", {
            "webhook_id": "abc123", "cloudhook_url": "https://..."
        })
        webhook.cloudhook_create(fake_client, "abc123")
        assert fake_client.ws_calls[0]["type"] == "cloud/cloudhook/create"
        assert fake_client.ws_calls[0]["payload"] == {"webhook_id": "abc123"}

    def test_cloudhook_create_no_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="webhook_id"):
            webhook.cloudhook_create(fake_client, "")

    def test_cloudhook_delete_payload(self, fake_client):
        fake_client.set_ws("cloud/cloudhook/delete", None)
        webhook.cloudhook_delete(fake_client, "abc123")
        assert fake_client.ws_calls[0]["type"] == "cloud/cloudhook/delete"
        assert fake_client.ws_calls[0]["payload"] == {"webhook_id": "abc123"}

    def test_cloudhook_delete_no_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="webhook_id"):
            webhook.cloudhook_delete(fake_client, "")
