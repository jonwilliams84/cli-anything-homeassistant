"""Regression tests for Bandit B110/B112 security fixes.

These tests verify the *behaviour* introduced by the fixes: instead of
silently swallowing exceptions (try/except/pass and try/except/continue),
the code now logs a record via the module logger.  The tests assert on
the emitted log records, not on source text or comments.
"""

from __future__ import annotations

import logging

import pytest

from cli_anything.homeassistant.core import lovelace_card_types as card_types
from cli_anything.homeassistant.core import powercalc


# ── helpers ─────────────────────────────────────────────────────────────────

class _RaisingWSClient:
    """Fake client whose ``ws_call`` raises for specified message types."""

    def __init__(self, *, dashboards: list | None = None,
                 raise_on: set[str] | None = None) -> None:
        self._dashboards = dashboards or []
        self._raise_on = raise_on or set()

    def ws_call(self, msg_type: str, payload: dict | None = None):
        if msg_type in self._raise_on:
            raise RuntimeError(f"ws_call failed for {msg_type}")
        if msg_type == "lovelace/dashboards/list":
            return self._dashboards
        return {}


# ── B112: types_across_dashboards — per-dashboard failure logs ──────────────

class TestTypesAcrossDashboardsLogsOnFailure:
    def test_logs_warning_when_dashboard_config_raises(self, caplog):
        """B112 fix: a failing dashboard config is logged, not silently
        skipped via try/except/continue."""
        client = _RaisingWSClient(
            dashboards=[{"url_path": "broken"}],
            raise_on={"lovelace/config"},
        )
        with caplog.at_level(logging.WARNING, logger=card_types._LOGGER.name):
            result = card_types.types_across_dashboards(client)
        # The broken dashboard is skipped (not in result) …
        assert "broken" not in result
        # … but a WARNING was emitted mentioning the dashboard url.
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("broken" in r.getMessage() for r in warnings), (
            "expected a WARNING log mentioning the skipped dashboard url"
        )


# ── B110: types_across_dashboards — default dashboard failure logs ──────────

class TestTypesAcrossDashboardsLogsDefaultFailure:
    def test_logs_warning_when_default_dashboard_raises(self, caplog):
        """B110 fix: a failing default-dashboard read is logged, not silently
        swallowed via try/except/pass."""
        # No dashboards in the list, but lovelace/config (default) raises.
        client = _RaisingWSClient(
            dashboards=[],
            raise_on={"lovelace/config"},
        )
        with caplog.at_level(logging.WARNING, logger=card_types._LOGGER.name):
            result = card_types.types_across_dashboards(client)
        # Result is empty (no dashboards, default failed) …
        assert result == {}
        # … but a WARNING was emitted about the default dashboard.
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("default" in r.getMessage().lower() for r in warnings), (
            "expected a WARNING log mentioning the default dashboard"
        )


# ── B110: get_group_config — flow-abort failure logs ────────────────────────

class _DeleteRaisingFlowClient:
    """FlowFakeClient whose ``delete`` always raises.

    Reuses the same interface as the FlowFakeClient in test_powercalc.py
    but makes the best-effort abort path fail.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.post_queue: list = []
        self.get_responses: dict[str, object] = {}

    def queue_posts(self, *responses) -> None:
        self.post_queue.extend(responses)

    def set_get(self, path: str, response) -> None:
        self.get_responses[path.lstrip("/")] = response

    def get(self, path: str, params: dict | None = None):
        path = path.lstrip("/")
        self.calls.append({"verb": "GET", "path": path, "params": params})
        return self.get_responses.get(path, {})

    def post(self, path: str, payload=None):
        path = path.lstrip("/")
        self.calls.append({"verb": "POST", "path": path, "payload": payload})
        if not self.post_queue:
            raise AssertionError(
                f"POST {path} with no queued response — unexpected call. "
                f"Calls so far: {self.calls}",
            )
        return self.post_queue.pop(0)

    def delete(self, path: str):
        self.calls.append({"verb": "DELETE", "path": path})
        raise RuntimeError("delete failed — HA unreachable")


def _group_form(flow_id="f1", member=None, power=None, energy=None, sub=None):
    def _field(name, val):
        f = {"name": name}
        if val is not None:
            f["description"] = {"suggested_value": val}
        return f
    return {"flow_id": flow_id, "type": "form", "step_id": "group_custom",
            "data_schema": [
                _field("group_member_sensors", member),
                _field("group_power_entities", power),
                _field("group_energy_entities", energy),
                _field("sub_groups", sub),
            ]}


def _menu():
    return {"flow_id": "f1", "type": "menu",
            "menu_options": ["basic_options", "group_custom"]}


class TestGetGroupConfigLogsAbortFailure:
    def test_logs_debug_when_flow_abort_fails(self, caplog):
        """B110 fix: when the best-effort options-flow abort (DELETE) fails,
        the exception is logged at DEBUG instead of being silently passed."""
        client = _DeleteRaisingFlowClient()
        client.queue_posts(
            _menu(),
            _group_form(power=["sensor.a_power"], energy=["sensor.a_energy"],
                        member=["m1"]),
        )
        with caplog.at_level(logging.DEBUG, logger=powercalc._LOGGER.name):
            # Must not raise — the abort failure is logged, not propagated.
            cfg = powercalc.get_group_config(client, "E1")
        # The config was still read successfully.
        assert cfg["group_power_entities"] == ["sensor.a_power"]
        # A DEBUG record was emitted about the failed abort.
        debugs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("abort" in r.getMessage().lower()
                   or "flow" in r.getMessage().lower() for r in debugs), (
            "expected a DEBUG log about the failed options-flow abort"
        )