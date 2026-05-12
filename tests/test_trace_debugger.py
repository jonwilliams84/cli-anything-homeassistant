"""Unit tests for cli_anything.homeassistant.core.trace_debugger.

All tests run against FakeClient (auto-injected via the ``fake_client``
fixture in conftest.py) — no live Home Assistant required.

WS message types covered:
  trace/debug/breakpoint/list       — list_breakpoints
  trace/debug/breakpoint/subscribe  — subscribe_breakpoints
  trace/debug/breakpoint/set        — set_breakpoint
  trace/debug/breakpoint/clear      — clear_breakpoint
  trace/debug/step                  — step_execution
  trace/debug/continue              — continue_execution
  trace/debug/stop                  — stop_execution
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import trace_debugger


class TestTraceDebugger:

    # ─────────────────────────── list_breakpoints ───────────────────────────

    def test_list_breakpoints_happy_path_payload(self, fake_client):
        """list_breakpoints sends ``trace/debug/breakpoint/list`` with empty payload."""
        fake_client.set_ws("trace/debug/breakpoint/list", [])
        trace_debugger.list_breakpoints(fake_client)
        call = fake_client.ws_calls[-1]
        assert call["type"] == "trace/debug/breakpoint/list"
        assert call["payload"] == {}

    def test_list_breakpoints_returns_list(self, fake_client):
        """list_breakpoints returns the canned list from the WS response."""
        data = [
            {"domain": "automation", "item_id": "lights", "node": "action/0"},
            {"domain": "script", "item_id": "morning", "node": "sequence/1"},
        ]
        fake_client.set_ws("trace/debug/breakpoint/list", data)
        result = trace_debugger.list_breakpoints(fake_client)
        assert result == data

    def test_list_breakpoints_non_list_normalised(self, fake_client):
        """list_breakpoints returns [] when HA returns a non-list."""
        # FakeClient returns [] by default when key not set; register a dict response
        # by subclassing to simulate unexpected payload.
        class _DictClient:
            ws_calls: list[dict] = []

            def ws_call(self, msg_type, payload=None):
                self.ws_calls.append({"type": msg_type, "payload": payload})
                return {"error": "unexpected"}

        result = trace_debugger.list_breakpoints(_DictClient())
        assert result == []

    # ─────────────────────────── subscribe_breakpoints ──────────────────────

    def test_subscribe_breakpoints_happy_path_payload(self, fake_client):
        """subscribe_breakpoints sends ``trace/debug/breakpoint/subscribe``."""
        fake_client.set_ws("trace/debug/breakpoint/subscribe", {"subscribed": True})
        trace_debugger.subscribe_breakpoints(fake_client)
        call = fake_client.ws_calls[-1]
        assert call["type"] == "trace/debug/breakpoint/subscribe"
        assert call["payload"] == {}

    def test_subscribe_breakpoints_returns_dict(self, fake_client):
        """subscribe_breakpoints returns the WS response dict (initial ACK)."""
        fake_client.set_ws("trace/debug/breakpoint/subscribe", {"subscribed": True})
        result = trace_debugger.subscribe_breakpoints(fake_client)
        assert isinstance(result, dict)

    def test_subscribe_breakpoints_non_dict_normalised(self, fake_client):
        """subscribe_breakpoints returns {} when HA returns a non-dict."""
        class _ListClient:
            ws_calls: list[dict] = []

            def ws_call(self, msg_type, payload=None):
                self.ws_calls.append({"type": msg_type, "payload": payload})
                return ["unexpected"]

        result = trace_debugger.subscribe_breakpoints(_ListClient())
        assert result == {}

    # ─────────────────────────── set_breakpoint ─────────────────────────────

    def test_set_breakpoint_happy_path_payload(self, fake_client):
        """set_breakpoint sends correct payload without optional run_id."""
        fake_client.set_ws("trace/debug/breakpoint/set", {"result": True})
        trace_debugger.set_breakpoint(
            fake_client, domain="automation", item_id="lights", node="action/0"
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "trace/debug/breakpoint/set"
        assert call["payload"] == {
            "domain": "automation",
            "item_id": "lights",
            "node": "action/0",
        }

    def test_set_breakpoint_with_run_id(self, fake_client):
        """set_breakpoint includes run_id in payload when supplied."""
        fake_client.set_ws("trace/debug/breakpoint/set", {"result": True})
        trace_debugger.set_breakpoint(
            fake_client,
            domain="script",
            item_id="morning",
            node="sequence/2",
            run_id="run-abc",
        )
        call = fake_client.ws_calls[-1]
        assert call["payload"] == {
            "domain": "script",
            "item_id": "morning",
            "node": "sequence/2",
            "run_id": "run-abc",
        }

    def test_set_breakpoint_returns_dict(self, fake_client):
        """set_breakpoint returns the WS response dict."""
        fake_client.set_ws("trace/debug/breakpoint/set", {"result": True})
        result = trace_debugger.set_breakpoint(
            fake_client, domain="automation", item_id="x", node="action/0"
        )
        assert result == {"result": True}

    def test_set_breakpoint_invalid_domain(self, fake_client):
        """set_breakpoint raises ValueError for an unrecognised domain."""
        with pytest.raises(ValueError, match="domain must be one of"):
            trace_debugger.set_breakpoint(
                fake_client, domain="sensor", item_id="foo", node="action/0"
            )

    def test_set_breakpoint_empty_item_id(self, fake_client):
        """set_breakpoint raises ValueError when item_id is empty."""
        with pytest.raises(ValueError, match="item_id must be a non-empty string"):
            trace_debugger.set_breakpoint(
                fake_client, domain="automation", item_id="", node="action/0"
            )

    def test_set_breakpoint_empty_node(self, fake_client):
        """set_breakpoint raises ValueError when node is empty."""
        with pytest.raises(ValueError, match="node must be a non-empty string"):
            trace_debugger.set_breakpoint(
                fake_client, domain="automation", item_id="lights", node=""
            )

    def test_set_breakpoint_empty_run_id(self, fake_client):
        """set_breakpoint raises ValueError when run_id is explicitly empty."""
        with pytest.raises(ValueError, match="run_id must be a non-empty string"):
            trace_debugger.set_breakpoint(
                fake_client,
                domain="automation",
                item_id="lights",
                node="action/0",
                run_id="",
            )

    # ─────────────────────────── clear_breakpoint ───────────────────────────

    def test_clear_breakpoint_happy_path_payload(self, fake_client):
        """clear_breakpoint sends correct payload without optional run_id."""
        fake_client.set_ws("trace/debug/breakpoint/clear", {"result": True})
        trace_debugger.clear_breakpoint(
            fake_client, domain="automation", item_id="lights", node="action/0"
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "trace/debug/breakpoint/clear"
        assert call["payload"] == {
            "domain": "automation",
            "item_id": "lights",
            "node": "action/0",
        }

    def test_clear_breakpoint_with_run_id(self, fake_client):
        """clear_breakpoint includes run_id in payload when supplied."""
        fake_client.set_ws("trace/debug/breakpoint/clear", {"result": True})
        trace_debugger.clear_breakpoint(
            fake_client,
            domain="script",
            item_id="morning",
            node="sequence/2",
            run_id="run-abc",
        )
        call = fake_client.ws_calls[-1]
        assert call["payload"] == {
            "domain": "script",
            "item_id": "morning",
            "node": "sequence/2",
            "run_id": "run-abc",
        }

    def test_clear_breakpoint_returns_dict(self, fake_client):
        """clear_breakpoint returns the WS response dict."""
        fake_client.set_ws("trace/debug/breakpoint/clear", {"result": True})
        result = trace_debugger.clear_breakpoint(
            fake_client, domain="script", item_id="morning", node="sequence/0"
        )
        assert result == {"result": True}

    def test_clear_breakpoint_invalid_domain(self, fake_client):
        """clear_breakpoint raises ValueError for an unrecognised domain."""
        with pytest.raises(ValueError, match="domain must be one of"):
            trace_debugger.clear_breakpoint(
                fake_client, domain="light", item_id="foo", node="action/0"
            )

    def test_clear_breakpoint_empty_item_id(self, fake_client):
        """clear_breakpoint raises ValueError when item_id is empty."""
        with pytest.raises(ValueError, match="item_id must be a non-empty string"):
            trace_debugger.clear_breakpoint(
                fake_client, domain="script", item_id="", node="action/0"
            )

    def test_clear_breakpoint_empty_node(self, fake_client):
        """clear_breakpoint raises ValueError when node is empty."""
        with pytest.raises(ValueError, match="node must be a non-empty string"):
            trace_debugger.clear_breakpoint(
                fake_client, domain="script", item_id="morning", node=""
            )

    def test_clear_breakpoint_empty_run_id(self, fake_client):
        """clear_breakpoint raises ValueError when run_id is explicitly empty."""
        with pytest.raises(ValueError, match="run_id must be a non-empty string"):
            trace_debugger.clear_breakpoint(
                fake_client,
                domain="automation",
                item_id="lights",
                node="action/0",
                run_id="",
            )

    # ─────────────────────────── step_execution ─────────────────────────────

    def test_step_execution_happy_path_payload(self, fake_client):
        """step_execution sends correct ``trace/debug/step`` payload."""
        fake_client.set_ws("trace/debug/step", {"result": True})
        trace_debugger.step_execution(
            fake_client, domain="automation", item_id="lights", run_id="run-001"
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "trace/debug/step"
        assert call["payload"] == {
            "domain": "automation",
            "item_id": "lights",
            "run_id": "run-001",
        }

    def test_step_execution_returns_dict(self, fake_client):
        """step_execution returns the WS response dict."""
        fake_client.set_ws("trace/debug/step", {"result": True})
        result = trace_debugger.step_execution(
            fake_client, domain="script", item_id="my_script", run_id="run-002"
        )
        assert result == {"result": True}

    def test_step_execution_invalid_domain(self, fake_client):
        """step_execution raises ValueError for an unrecognised domain."""
        with pytest.raises(ValueError, match="domain must be one of"):
            trace_debugger.step_execution(
                fake_client, domain="switch", item_id="foo", run_id="r1"
            )

    def test_step_execution_empty_item_id(self, fake_client):
        """step_execution raises ValueError when item_id is empty."""
        with pytest.raises(ValueError, match="item_id must be a non-empty string"):
            trace_debugger.step_execution(
                fake_client, domain="automation", item_id="", run_id="r1"
            )

    def test_step_execution_empty_run_id(self, fake_client):
        """step_execution raises ValueError when run_id is empty."""
        with pytest.raises(ValueError, match="run_id must be a non-empty string"):
            trace_debugger.step_execution(
                fake_client, domain="automation", item_id="lights", run_id=""
            )

    # ─────────────────────────── continue_execution ─────────────────────────

    def test_continue_execution_happy_path_payload(self, fake_client):
        """continue_execution sends correct ``trace/debug/continue`` payload."""
        fake_client.set_ws("trace/debug/continue", {"result": True})
        trace_debugger.continue_execution(
            fake_client, domain="script", item_id="morning", run_id="run-003"
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "trace/debug/continue"
        assert call["payload"] == {
            "domain": "script",
            "item_id": "morning",
            "run_id": "run-003",
        }

    def test_continue_execution_returns_dict(self, fake_client):
        """continue_execution returns the WS response dict."""
        fake_client.set_ws("trace/debug/continue", {"resumed": True})
        result = trace_debugger.continue_execution(
            fake_client, domain="automation", item_id="lights", run_id="run-004"
        )
        assert result == {"resumed": True}

    def test_continue_execution_invalid_domain(self, fake_client):
        """continue_execution raises ValueError for an unrecognised domain."""
        with pytest.raises(ValueError, match="domain must be one of"):
            trace_debugger.continue_execution(
                fake_client, domain="binary_sensor", item_id="x", run_id="r1"
            )

    def test_continue_execution_empty_item_id(self, fake_client):
        """continue_execution raises ValueError when item_id is empty."""
        with pytest.raises(ValueError, match="item_id must be a non-empty string"):
            trace_debugger.continue_execution(
                fake_client, domain="script", item_id="", run_id="r1"
            )

    def test_continue_execution_empty_run_id(self, fake_client):
        """continue_execution raises ValueError when run_id is empty."""
        with pytest.raises(ValueError, match="run_id must be a non-empty string"):
            trace_debugger.continue_execution(
                fake_client, domain="script", item_id="morning", run_id=""
            )

    # ─────────────────────────── stop_execution ─────────────────────────────

    def test_stop_execution_happy_path_payload(self, fake_client):
        """stop_execution sends correct ``trace/debug/stop`` payload."""
        fake_client.set_ws("trace/debug/stop", {"result": True})
        trace_debugger.stop_execution(
            fake_client, domain="automation", item_id="lights", run_id="run-005"
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "trace/debug/stop"
        assert call["payload"] == {
            "domain": "automation",
            "item_id": "lights",
            "run_id": "run-005",
        }

    def test_stop_execution_returns_dict(self, fake_client):
        """stop_execution returns the WS response dict."""
        fake_client.set_ws("trace/debug/stop", {"stopped": True})
        result = trace_debugger.stop_execution(
            fake_client, domain="script", item_id="morning", run_id="run-006"
        )
        assert result == {"stopped": True}

    def test_stop_execution_invalid_domain(self, fake_client):
        """stop_execution raises ValueError for an unrecognised domain."""
        with pytest.raises(ValueError, match="domain must be one of"):
            trace_debugger.stop_execution(
                fake_client, domain="climate", item_id="x", run_id="r1"
            )

    def test_stop_execution_empty_item_id(self, fake_client):
        """stop_execution raises ValueError when item_id is empty."""
        with pytest.raises(ValueError, match="item_id must be a non-empty string"):
            trace_debugger.stop_execution(
                fake_client, domain="automation", item_id="", run_id="r1"
            )

    def test_stop_execution_empty_run_id(self, fake_client):
        """stop_execution raises ValueError when run_id is empty."""
        with pytest.raises(ValueError, match="run_id must be a non-empty string"):
            trace_debugger.stop_execution(
                fake_client, domain="automation", item_id="lights", run_id=""
            )
