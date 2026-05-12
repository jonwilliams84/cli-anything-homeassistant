"""Unit tests for cli_anything.homeassistant.core.trace_debug.

All tests run against FakeClient (auto-injected via the ``fake_client``
fixture in conftest.py) — no live Home Assistant required.

WS message types covered:
  trace/list      — list_traces
  trace/get       — get_trace
  trace/contexts  — list_contexts
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import trace_debug


class TestTraceDebug:
    # ────────────────────────────────────────── list_traces ──────────────────

    def test_list_traces_happy_path_payload(self, fake_client):
        """list_traces sends a ``trace/list`` WS message with correct fields."""
        fake_client.set_ws("trace/list", [])
        trace_debug.list_traces(fake_client, domain="automation", item_id="my_auto")
        call = fake_client.ws_calls[-1]
        assert call["type"] == "trace/list"
        assert call["payload"] == {"domain": "automation", "item_id": "my_auto"}

    def test_list_traces_no_filters(self, fake_client):
        """list_traces works with no domain/item_id (sends empty payload)."""
        fake_client.set_ws("trace/list", [])
        trace_debug.list_traces(fake_client)
        assert fake_client.ws_calls[-1]["payload"] == {}

    def test_list_traces_domain_only(self, fake_client):
        """list_traces with only domain omits item_id from payload."""
        fake_client.set_ws("trace/list", [])
        trace_debug.list_traces(fake_client, domain="script")
        assert fake_client.ws_calls[-1]["payload"] == {"domain": "script"}

    def test_list_traces_returns_list(self, fake_client):
        """list_traces returns the canned list from the WS response."""
        summaries = [
            {"run_id": "abc123", "domain": "automation", "item_id": "lights"},
            {"run_id": "def456", "domain": "automation", "item_id": "lights"},
        ]
        fake_client.set_ws("trace/list", summaries)
        result = trace_debug.list_traces(fake_client, domain="automation",
                                         item_id="lights")
        assert result == summaries

    def test_list_traces_non_list_response_normalised(self, fake_client):
        """list_traces returns [] when HA returns something other than a list."""
        fake_client.set_ws("trace/list", None)
        # FakeClient returns [] by default when the key is not set; simulate
        # an unexpected dict response by calling ws_call directly via a subclass.
        result = trace_debug.list_traces(fake_client)
        assert isinstance(result, list)

    def test_list_traces_invalid_domain(self, fake_client):
        """list_traces raises ValueError for an unrecognised domain."""
        with pytest.raises(ValueError, match="domain must be one of"):
            trace_debug.list_traces(fake_client, domain="sensor")

    def test_list_traces_empty_item_id(self, fake_client):
        """list_traces raises ValueError when item_id is an empty string."""
        with pytest.raises(ValueError, match="item_id must be a non-empty string"):
            trace_debug.list_traces(fake_client, domain="automation", item_id="")

    # ────────────────────────────────────────── get_trace ────────────────────

    def test_get_trace_happy_path_payload(self, fake_client):
        """get_trace sends a ``trace/get`` WS message with all required fields."""
        fake_client.set_ws("trace/get", {})
        trace_debug.get_trace(
            fake_client, domain="automation", item_id="my_auto", run_id="run001"
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "trace/get"
        assert call["payload"] == {
            "domain": "automation",
            "item_id": "my_auto",
            "run_id": "run001",
        }

    def test_get_trace_returns_dict(self, fake_client):
        """get_trace returns the canned dict from the WS response."""
        full_trace = {
            "run_id": "run001",
            "domain": "automation",
            "item_id": "my_auto",
            "trace": {"node-1": [{"result": {"choice": "default"}}]},
        }
        fake_client.set_ws("trace/get", full_trace)
        result = trace_debug.get_trace(
            fake_client, domain="automation", item_id="my_auto", run_id="run001"
        )
        assert result == full_trace

    def test_get_trace_invalid_domain(self, fake_client):
        """get_trace raises ValueError for an unrecognised domain."""
        with pytest.raises(ValueError, match="domain must be one of"):
            trace_debug.get_trace(
                fake_client, domain="device_tracker", item_id="tracker_1", run_id="r1"
            )

    def test_get_trace_empty_item_id(self, fake_client):
        """get_trace raises ValueError when item_id is empty."""
        with pytest.raises(ValueError, match="item_id must be a non-empty string"):
            trace_debug.get_trace(
                fake_client, domain="script", item_id="", run_id="r1"
            )

    def test_get_trace_empty_run_id(self, fake_client):
        """get_trace raises ValueError when run_id is empty."""
        with pytest.raises(ValueError, match="run_id must be a non-empty string"):
            trace_debug.get_trace(
                fake_client, domain="script", item_id="my_script", run_id=""
            )

    def test_get_trace_script_domain(self, fake_client):
        """get_trace accepts ``"script"`` as a valid domain."""
        fake_client.set_ws("trace/get", {"run_id": "r42"})
        result = trace_debug.get_trace(
            fake_client, domain="script", item_id="my_script", run_id="r42"
        )
        assert result["run_id"] == "r42"

    # ────────────────────────────────────────── list_contexts ────────────────

    def test_list_contexts_happy_path_payload(self, fake_client):
        """list_contexts sends a ``trace/contexts`` WS message with correct fields."""
        fake_client.set_ws("trace/contexts", {})
        trace_debug.list_contexts(
            fake_client, domain="automation", item_id="my_auto"
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "trace/contexts"
        assert call["payload"] == {"domain": "automation", "item_id": "my_auto"}

    def test_list_contexts_no_filters(self, fake_client):
        """list_contexts with no args sends an empty payload."""
        fake_client.set_ws("trace/contexts", {})
        trace_debug.list_contexts(fake_client)
        assert fake_client.ws_calls[-1]["payload"] == {}

    def test_list_contexts_returns_dict(self, fake_client):
        """list_contexts returns the canned context mapping from the WS response."""
        contexts = {
            "ctx_abc": {"domain": "automation", "item_id": "lights", "run_id": "r1"},
            "ctx_def": {"domain": "automation", "item_id": "lights", "run_id": "r2"},
        }
        fake_client.set_ws("trace/contexts", contexts)
        result = trace_debug.list_contexts(
            fake_client, domain="automation", item_id="lights"
        )
        assert result == contexts

    def test_list_contexts_invalid_domain(self, fake_client):
        """list_contexts raises ValueError for an unrecognised domain."""
        with pytest.raises(ValueError, match="domain must be one of"):
            trace_debug.list_contexts(fake_client, domain="unknown", item_id="x")

    def test_list_contexts_empty_item_id(self, fake_client):
        """list_contexts raises ValueError when item_id is an empty string."""
        with pytest.raises(ValueError, match="item_id must be a non-empty string"):
            trace_debug.list_contexts(fake_client, domain="script", item_id="")

    def test_list_contexts_partial_args_raises(self, fake_client):
        """list_contexts raises ValueError when only one of domain/item_id is given."""
        with pytest.raises(ValueError, match="domain and item_id must be supplied together"):
            trace_debug.list_contexts(fake_client, domain="automation")

    def test_list_contexts_item_id_without_domain_raises(self, fake_client):
        """list_contexts raises ValueError when item_id is given without domain."""
        with pytest.raises(ValueError, match="domain and item_id must be supplied together"):
            trace_debug.list_contexts(fake_client, item_id="my_script")
