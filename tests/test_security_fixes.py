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


# ── B112: recorder.top_entities history-fetch failure logs ──────────────────

class _RaisingHistoryClient:
    """Fake client whose ``get`` raises for history/period paths."""

    def __init__(self):
        self.calls: list[dict] = []

    def get(self, path: str, params: dict | None = None):
        self.calls.append({"verb": "GET", "path": path, "params": params})
        if path.startswith("history/period/"):
            raise RuntimeError("history endpoint unreachable")
        if path == "states":
            return [{"entity_id": "sensor.bad", "attributes": {}}]
        return []

    def post(self, path: str, payload=None):
        self.calls.append({"verb": "POST", "path": path, "payload": payload})
        return {}

    def delete(self, path: str):
        self.calls.append({"verb": "DELETE", "path": path})
        return {}

    def ws_call(self, msg_type: str, payload: dict | None = None):
        self.calls.append({"verb": "WS", "msg_type": msg_type, "payload": payload})
        return {}


class TestTopEntitiesLogsHistoryFetchFailure:
    def test_logs_debug_when_history_fetch_fails(self, caplog):
        """B112 fix: a failing per-entity history fetch is logged, not
        silently skipped via try/except/continue."""
        from cli_anything.homeassistant.core import recorder as recorder_core

        client = _RaisingHistoryClient()

        with caplog.at_level(logging.DEBUG, logger=recorder_core._LOGGER.name):
            result = recorder_core.top_entities(client, entity_ids=["sensor.bad"])

        # The failing entity is not in the result …
        assert all(r["entity_id"] != "sensor.bad" for r in result)
        # … but a DEBUG record was emitted mentioning the entity.
        debugs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("sensor.bad" in r.getMessage() for r in debugs), (
            "expected a DEBUG log mentioning the skipped entity sensor.bad"
        )


# ── B112: references._ui_configs config-fetch failure logs ──────────────────

class _RaisingConfigClient:
    """Fake client whose ``get`` raises for config/<domain>/config paths."""

    def __init__(self, *, bad_cfg_ids: set[str] | None = None):
        self.calls: list[dict] = []
        self._bad_cfg_ids = bad_cfg_ids or set()

    def get(self, path: str, params: dict | None = None):
        self.calls.append({"verb": "GET", "path": path, "params": params})
        if path == "states":
            return [
                {"entity_id": "automation.good", "attributes": {"id": "good"}},
                {"entity_id": "automation.bad", "attributes": {"id": "bad"}},
            ]
        if path.startswith("config/automation/config/"):
            cfg_id = path.rsplit("/", 1)[-1]
            if cfg_id in self._bad_cfg_ids:
                raise RuntimeError("config endpoint unreadable")
            return {"id": cfg_id, "triggers": []}
        return []

    def post(self, path: str, payload=None):
        self.calls.append({"verb": "POST", "path": path, "payload": payload})
        return {}

    def delete(self, path: str):
        self.calls.append({"verb": "DELETE", "path": path})
        return {}

    def ws_call(self, msg_type: str, payload: dict | None = None):
        self.calls.append({"verb": "WS", "msg_type": msg_type, "payload": payload})
        return []


class TestUiConfigsLogsConfigFetchFailure:
    def test_logs_debug_when_config_fetch_fails(self, caplog):
        """B112 fix: a failing per-entity config fetch is logged, not
        silently skipped via try/except/continue."""
        from cli_anything.homeassistant.core import references as references_core

        client = _RaisingConfigClient(bad_cfg_ids={"bad"})

        with caplog.at_level(logging.DEBUG, logger=references_core._LOGGER.name):
            result = references_core._ui_configs(client, "automation")

        # The failing automation is not in the result …
        assert all(eid != "automation.bad" for eid, _cfg in result)
        # … but a DEBUG record was emitted mentioning it.
        debugs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("bad" in r.getMessage() for r in debugs), (
            "expected a DEBUG log mentioning the skipped config id 'bad'"
        )


# ── B110: references._template_helper_entries abort-flow failure logs ────────

class _TemplateFlowClient:
    """Fake client that returns template entries but fails to abort the
    options flow via ``delete``."""

    def __init__(self):
        self.calls: list[dict] = []

    def get(self, path: str, params: dict | None = None):
        self.calls.append({"verb": "GET", "path": path, "params": params})
        return []

    def post(self, path: str, payload=None):
        self.calls.append({"verb": "POST", "path": path, "payload": payload})
        if path == "config/config_entries/options/flow":
            return {
                "flow_id": "flow-1",
                "data_schema": [
                    {"name": "template", "description": {"suggested_value": "{{ 1 }}"}},
                ],
            }
        return {}

    def delete(self, path: str):
        self.calls.append({"verb": "DELETE", "path": path})
        if path.startswith("config/config_entries/options/flow/"):
            raise RuntimeError("cannot abort options flow")
        return {}

    def ws_call(self, msg_type: str, payload: dict | None = None):
        self.calls.append({"verb": "WS", "msg_type": msg_type, "payload": payload})
        if msg_type == "config_entries/get":
            return [{"entry_id": "E1", "domain": "template", "title": "My Template"}]
        return []


class TestTemplateHelperEntriesLogsAbortFlowFailure:
    def test_logs_debug_when_abort_flow_fails(self, caplog):
        """B110 fix: a failing options-flow abort is logged, not silently
        swallowed via try/except/pass."""
        from cli_anything.homeassistant.core import references as references_core

        client = _TemplateFlowClient()

        with caplog.at_level(logging.DEBUG, logger=references_core._LOGGER.name):
            result = references_core._template_helper_entries(client)

        # The entry is still returned (abort failure doesn't block it) …
        assert any(e["entry_id"] == "E1" for e in result)
        # … and a DEBUG record was emitted about the abort failure.
        debugs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("abort" in r.getMessage().lower() for r in debugs), (
            "expected a DEBUG log about the failed options-flow abort"
        )


# ── B112: references._template_helper_entries entry read failure logs ────────

class _TemplateEntryReadFailureClient:
    """Fake client that returns a template entry but raises while reading its
    options flow."""

    def __init__(self):
        self.calls: list[dict] = []

    def get(self, path: str, params: dict | None = None):
        self.calls.append({"verb": "GET", "path": path, "params": params})
        return []

    def post(self, path: str, payload=None):
        self.calls.append({"verb": "POST", "path": path, "payload": payload})
        if path == "config/config_entries/options/flow":
            raise RuntimeError("options flow unavailable")
        return {}

    def delete(self, path: str):
        self.calls.append({"verb": "DELETE", "path": path})
        return {}

    def ws_call(self, msg_type: str, payload: dict | None = None):
        self.calls.append({"verb": "WS", "msg_type": msg_type, "payload": payload})
        if msg_type == "config_entries/get":
            return [{"entry_id": "E2", "domain": "template", "title": "Broken"}]
        return []


class TestTemplateHelperEntriesLogsEntryReadFailure:
    def test_logs_debug_when_entry_read_fails(self, caplog):
        """B112 fix: a failing per-entry options-flow read is logged, not
        silently skipped via try/except/continue."""
        from cli_anything.homeassistant.core import references as references_core

        client = _TemplateEntryReadFailureClient()

        with caplog.at_level(logging.DEBUG, logger=references_core._LOGGER.name):
            result = references_core._template_helper_entries(client)

        # The broken entry is skipped …
        assert not any(e["entry_id"] == "E2" for e in result)
        # … and a DEBUG record was emitted mentioning E2.
        debugs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("E2" in r.getMessage() for r in debugs), (
            "expected a DEBUG log mentioning the skipped entry E2"
        )


# ── B110/B112: references._lovelace_configs fetch failures log ──────────────

class _LovelaceFailureClient:
    """Fake client where every lovelace/config call raises."""

    def __init__(self):
        self.calls: list[dict] = []

    def get(self, path: str, params: dict | None = None):
        self.calls.append({"verb": "GET", "path": path, "params": params})
        return []

    def post(self, path: str, payload=None):
        self.calls.append({"verb": "POST", "path": path, "payload": payload})
        return {}

    def delete(self, path: str):
        self.calls.append({"verb": "DELETE", "path": path})
        return {}

    def ws_call(self, msg_type: str, payload: dict | None = None):
        self.calls.append({"verb": "WS", "msg_type": msg_type, "payload": payload})
        if msg_type == "lovelace/dashboards/list":
            return [{"url_path": "mobile"}]
        if msg_type == "lovelace/config":
            raise RuntimeError("lovelace config unavailable")
        return []


class TestLovelaceConfigsLogsFetchFailures:
    def test_logs_debug_when_main_and_dashboard_fetches_fail(self, caplog):
        """B110/B112 fix: failing lovelace config fetches are logged, not
        silently swallowed via try/except/pass or try/except/continue."""
        from cli_anything.homeassistant.core import references as references_core

        client = _LovelaceFailureClient()

        with caplog.at_level(logging.DEBUG, logger=references_core._LOGGER.name):
            result = references_core._lovelace_configs(client)

        # No dashboards are returned …
        assert result == []
        # … but DEBUG records were emitted for the main and per-dashboard failures.
        debugs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("lovelace main config" in r.getMessage().lower() for r in debugs), (
            "expected a DEBUG log about the failed main lovelace config fetch"
        )
        assert any("mobile" in r.getMessage() for r in debugs), (
            "expected a DEBUG log mentioning the failed mobile dashboard fetch"
        )


# ── B110: lovelace lint --check-types logs list_resources failure ──────────

class TestLovelaceLintLogsListResourcesFailure:
    """B110 fix: when lovelace_core.list_resources raises during
    ``lovelace lint --check-types``, the exception is logged (not silently
    swallowed via try/except/pass)."""

    def test_logs_debug_when_list_resources_fails(self, caplog, monkeypatch):
        from click.testing import CliRunner

        from cli_anything.homeassistant import homeassistant_cli as cli_mod
        from cli_anything.homeassistant.core import lovelace as lovelace_core

        # Fake client — only needs to support the calls made by lovelace_lint.
        class _FakeClient:
            def __init__(self):
                self.calls = []

            def get(self, path, params=None):
                self.calls.append(("GET", path))
                return {}

            def ws_call(self, msg_type, payload=None):
                self.calls.append(("WS", msg_type))
                if msg_type == "lovelace/config":
                    return {"views": []}
                if msg_type == "sensor/list" or msg_type == "state/list":
                    return []
                return []

        fake_client = _FakeClient()
        monkeypatch.setattr(cli_mod, "make_client", lambda ctx: fake_client)

        # Make list_states return empty so all_eids is empty.
        monkeypatch.setattr(
            cli_mod.states_core, "list_states", lambda c: []
        )
        # Make list_resources raise — this is the path that used to be
        # try/except/pass.
        def _boom(client):
            raise RuntimeError("list_resources unavailable")

        monkeypatch.setattr(cli_mod.lovelace_core, "list_resources", _boom)

        runner = CliRunner()
        with caplog.at_level(
            logging.DEBUG,
            logger="cli_anything.homeassistant.homeassistant_cli",
        ):
            result = runner.invoke(
                cli_mod.cli,
                ["--json", "lovelace", "lint", "default", "--check-types"],
                obj={
                    "url": "http://x",
                    "token": "t",
                    "verify_ssl": False,
                    "timeout": 5,
                    "as_json": True,
                    "config_path": None,
                },
                catch_exceptions=False,
            )

        # The command should still succeed (exit 0) — the failure is
        # non-fatal, just logged.
        assert result.exit_code == 0, result.output

        debugs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any(
            "lovelace resources" in r.getMessage().lower() for r in debugs
        ), "expected a DEBUG log about the failed list_resources call"
