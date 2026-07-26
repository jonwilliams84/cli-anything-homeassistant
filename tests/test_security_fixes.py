"""Regression tests for Bandit B110/B112 security fixes.

These tests verify the *behaviour* introduced by the fixes: instead of
silently swallowing exceptions (try/except/pass and try/except/continue),
the code now logs a record via the module logger.  The tests assert on
the emitted log records, not on source text or comments.
"""

from __future__ import annotations

import logging

import pytest

from cli_anything.homeassistant.core import powercalc


# ── helpers ─────────────────────────────────────────────────────────────────

class _RaisingReloadClient:
    """Fake client whose ``post`` raises on the reload endpoint."""

    def __init__(self, *, post_responses: dict | None = None) -> None:
        self.calls: list[dict] = []
        self._post_responses = post_responses or {}

    def get(self, path: str, params: dict | None = None):
        self.calls.append({"verb": "GET", "path": path, "params": params})
        return {}

    def post(self, path: str, payload=None):
        self.calls.append({"verb": "POST", "path": path, "payload": payload})
        if path.rstrip("/").endswith("/reload"):
            raise RuntimeError("reload failed — HA unreachable")
        return self._post_responses.get(path, {})

    def delete(self, path: str):
        self.calls.append({"verb": "DELETE", "path": path})
        return {}


class _RaisingGroupConfigClient:
    """Fake client whose ``get_group_config`` path raises for some entries."""

    def __init__(self, *, bad_entry_ids: set[str] | None = None) -> None:
        self.calls: list[dict] = []
        self._bad_entry_ids = bad_entry_ids or set()

    def get(self, path: str, params: dict | None = None):
        self.calls.append({"verb": "GET", "path": path, "params": params})
        return {}

    def post(self, path: str, payload=None):
        self.calls.append({"verb": "POST", "path": path, "payload": payload})
        return {}

    def delete(self, path: str):
        self.calls.append({"verb": "DELETE", "path": path})
        return {}

    def ws_call(self, msg_type: str, payload: dict | None = None):
        self.calls.append({"verb": "WS", "msg_type": msg_type, "payload": payload})
        return {}


# ── B110: set_group_members reload failure logs ─────────────────────────────

class TestSetGroupMembersLogsReloadFailure:
    def test_logs_debug_when_reload_fails(self, caplog, monkeypatch):
        """B110 fix: a failing reload is logged, not silently swallowed."""
        client = _RaisingReloadClient(post_responses={
            "config/config_entries/options/flow": {
                "flow_id": "f1",
                "type": "form",
                "step_id": "group_custom",
                "data_schema": [
                    {"name": "group_member_sensors"},
                    {"name": "group_power_entities"},
                    {"name": "group_energy_entities"},
                    {"name": "sub_groups"},
                ],
            },
            "config/config_entries/options/flow/f1": {"type": "create_entry"},
        })

        with caplog.at_level(logging.DEBUG, logger=powercalc._LOGGER.name):
            powercalc.set_group_members(
                client, "E1", power_entities=["sensor.a_power"], verify=False,
            )

        debugs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("reload" in r.getMessage().lower() for r in debugs), (
            "expected a DEBUG log about the failed reload"
        )


# ── B112: find_groups_containing group-config read failure logs ─────────────

class TestFindGroupsContainingLogsGroupReadFailure:
    def test_logs_debug_when_group_config_read_fails(self, caplog, monkeypatch):
        """B112 fix: a failing per-group config read is logged, not silently
        skipped via try/except/continue."""
        client = _RaisingGroupConfigClient()

        monkeypatch.setattr(
            powercalc, "list_entries", lambda c: [
                {"entry_id": "G1"},
                {"entry_id": "G2"},
            ],
        )

        def fake_get_group_config(c, eid):
            if eid == "G1":
                raise RuntimeError("group config unreadable")
            return {
                "group_member_sensors": ["sensor.leaf"],
                "group_power_entities": [],
                "group_energy_entities": [],
                "sub_groups": [],
                "area": None,
                "floor": None,
            }

        monkeypatch.setattr(powercalc, "get_group_config", fake_get_group_config)

        with caplog.at_level(logging.DEBUG, logger=powercalc._LOGGER.name):
            result = powercalc.find_groups_containing(
                client, entry_ids=["sensor.leaf"],
            )

        # G1 is skipped (not in result) …
        assert all(g["entry_id"] != "G1" for g in result)
        # … but a DEBUG record was emitted mentioning G1.
        debugs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("G1" in r.getMessage() for r in debugs), (
            "expected a DEBUG log mentioning the skipped entry G1"
        )


# ── B110: set_power_template reload failure logs ─────────────────────────────

class TestSetPowerTemplateLogsReloadFailure:
    def test_logs_debug_when_reload_fails(self, caplog, monkeypatch):
        """B110 fix: a failing reload is logged, not silently swallowed."""
        client = _RaisingReloadClient()

        def fake_open_fixed_step(c, eid):
            return {"flow_id": "f1", "type": "form", "step_id": "power_advanced"}

        monkeypatch.setattr(powercalc, "_open_fixed_step", fake_open_fixed_step)

        def fake_options_flow_configure(c, flow_id, data):
            return {"type": "create_entry"}

        monkeypatch.setattr(powercalc._ce, "options_flow_configure", fake_options_flow_configure)

        with caplog.at_level(logging.DEBUG, logger=powercalc._LOGGER.name):
            powercalc.set_power_template(
                client, "E1", power_template="{{ 1 }}",
            )

        debugs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("reload" in r.getMessage().lower() for r in debugs), (
            "expected a DEBUG log about the failed reload"
        )
