"""Regression tests for the B110/B112 security fixes in template_helpers and webhook.

The three flagged sites previously swallowed exceptions silently
(``except: pass`` / ``except: continue``). They now emit a ``WARNING`` log
record describing the failure so it is observable, while preserving the
original control flow. These tests assert that *behaviour* — a log record
is produced — rather than any source-text detail.
"""
from __future__ import annotations

import logging

import pytest

from cli_anything.homeassistant.core import template_helpers
from cli_anything.homeassistant.core import webhook


# ───────────────────────────────────── template_helpers.show (B110)

class TestTemplateHelpersShowLogsAbortFailure:
    """``template_helpers.show`` aborts the options flow after reading it.

    If the cleanup DELETE itself raises, that was previously swallowed with
    ``except: pass``. The fix logs the abort failure at WARNING while still
    returning the current options.
    """

    def test_show_logs_when_abort_fails(self, fake_client, caplog):
        fake_client.set(
            "POST", "config/config_entries/options/flow",
            {
                "flow_id": "flow-1",
                "data_schema": [
                    {"name": "state", "description": {"suggested_value": "{{ 1 }}"}},
                ],
            },
        )
        fake_client.set_ws("config_entries/get", {"title": "T", "domain": "template"})

        def request(method, path):
            raise RuntimeError("DELETE refused")

        fake_client.request = request  # type: ignore[assignment]

        with caplog.at_level(logging.WARNING, logger=template_helpers.__name__):
            out = template_helpers.show(fake_client, "entry-1")

        # Original behaviour preserved: options are still returned.
        assert out["entry_id"] == "entry-1"
        assert out["options"] == {"state": "{{ 1 }}"}
        assert out["title"] == "T"
        assert out["domain"] == "template"
        # The abort failure is now logged at WARNING.
        assert any(
            "flow-1" in r.message and "entry-1" in r.message and r.levelno == logging.WARNING
            for r in caplog.records
        ), [r.message for r in caplog.records]


# ───────────────────────────────────── webhook.list_automation_webhooks (B112)

class TestWebhookAutomationLogsConfigFailure:
    """``webhook.list_automation_webhooks`` skips automations whose config
    cannot be fetched.

    Previously the failure was swallowed with ``except: continue``. The fix
    logs the failure at WARNING before continuing.
    """

    def test_list_automation_webhooks_logs_config_failure(self, fake_client, caplog):
        fake_client.set("GET", "states", [
            {"entity_id": "automation.broken", "state": "on",
             "attributes": {"id": "auto-bad"}},
        ])
        fake_client.set("GET", "config/automation/config/auto-bad", RuntimeError("config endpoint down"))

        def get(path):
            path = path.lstrip("/")
            match_path = path.split("?", 1)[0]
            fake_client.calls.append({"verb": "GET", "path": path})
            resp = fake_client.responses.get(("GET", match_path),
                                             fake_client.responses.get(("GET", path), []))
            if isinstance(resp, BaseException):
                raise resp
            return resp

        fake_client.get = get  # type: ignore[assignment]

        with caplog.at_level(logging.WARNING, logger=webhook.__name__):
            result = webhook.list_automation_webhooks(fake_client)

        # Original behaviour preserved: automation is skipped.
        assert result == []
        # The failure is now logged at WARNING.
        assert any(
            "auto-bad" in r.message and "automation.broken" in r.message
            and r.levelno == logging.WARNING
            for r in caplog.records
        ), [r.message for r in caplog.records]


# ───────────────────────────────────── webhook.list_mobile_app_webhooks (B110)

class TestWebhookMobileAppLogsFallbackFailure:
    """``webhook.list_mobile_app_webhooks`` falls back to an empty list when
    ``mobile_app/list_for_user`` is unavailable.

    Previously the failure was swallowed with ``except: pass``. The fix logs
    the failure at WARNING before returning the empty fallback.
    """

    def test_list_mobile_app_webhooks_logs_ws_failure(self, fake_client, caplog):
        def ws_call(msg_type, payload=None):
            raise RuntimeError("mobile_app not loaded")

        fake_client.ws_call = ws_call  # type: ignore[assignment]

        with caplog.at_level(logging.WARNING, logger=webhook.__name__):
            result = webhook.list_mobile_app_webhooks(fake_client)

        # Original behaviour preserved: empty fallback returned.
        assert result == []
        # The failure is now logged at WARNING.
        assert any(
            "mobile_app/list_for_user" in r.message and r.levelno == logging.WARNING
            for r in caplog.records
        ), [r.message for r in caplog.records]
