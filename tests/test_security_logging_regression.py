"""Regression tests for the B110/B112 security fixes.

Each of the three flagged sites previously swallowed exceptions silently
(``except: pass`` / ``except: continue``). They now emit a ``DEBUG`` log
record describing the failure so it is observable, while preserving the
original control flow. These tests assert that *behaviour* — a log record
is produced — rather than any source-text detail.
"""
from __future__ import annotations

import logging

import pytest

from cli_anything.homeassistant.core import backup as backup_core
from cli_anything.homeassistant.core import config_entries as config_entries_core
from cli_anything.homeassistant.core import helpers
from tests.conftest import FakeClient


# ───────────────────────────────────────────── backup.remove (B112)

class TestBackupRemoveLogsFallback:
    """``backup.remove`` tries ``backup/delete`` then ``backup/remove``.

    When the first message type raises, the fallback must still be tried
    (B112 previously did ``except: continue`` silently). The fix logs the
    failure at DEBUG before continuing.
    """

    def test_remove_logs_first_failure_then_falls_back(self, fake_client, caplog):
        # First ws_call raises, second succeeds.
        calls = {"n": 0}

        def ws_call(msg_type, payload=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("backup/delete not supported")
            return {"ok": True}

        fake_client.ws_call = ws_call  # type: ignore[assignment]

        with caplog.at_level(logging.DEBUG, logger=backup_core.__name__):
            result = backup_core.remove(fake_client, "bk-1")

        assert result == {"ok": True}
        # A DEBUG record mentioning the failed msg type was emitted.
        assert any(
            "backup/delete" in r.message and r.levelno == logging.DEBUG
            for r in caplog.records
        ), [r.message for r in caplog.records]

    def test_remove_raises_when_all_fail(self, fake_client, caplog):
        def ws_call(msg_type, payload=None):
            raise RuntimeError(f"boom-{msg_type}")

        fake_client.ws_call = ws_call  # type: ignore[assignment]

        with caplog.at_level(logging.DEBUG, logger=backup_core.__name__):
            with pytest.raises(RuntimeError, match="not supported"):
                backup_core.remove(fake_client, "bk-1")

        # Both attempts were logged.
        msgs = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("backup/delete" in m for m in msgs)
        assert any("backup/remove" in m for m in msgs)


# ───────────────────────────────────── config_entries.walk (B110)

class TestWalkLogsAbortFailure:
    """``walk`` aborts the flow when a configure step raises.

    If the cleanup ``flow_abort`` itself raises, that was previously
    swallowed with ``except: pass``. The fix logs the abort failure at
    DEBUG while still returning the error history.
    """

    def test_walk_logs_when_abort_also_fails(self, fake_client, monkeypatch, caplog):
        fake_client.set(
            "POST", "config/config_entries/flow",
            {"flow_id": "fid1", "type": "form", "step_id": "user"},
        )

        def boom(c, fid, payload):
            raise RuntimeError("network down")

        def abort_boom(c, fid):
            raise RuntimeError("abort failed too")

        monkeypatch.setattr(config_entries_core, "flow_configure", boom)
        monkeypatch.setattr(config_entries_core, "flow_abort", abort_boom)

        with caplog.at_level(logging.DEBUG, logger=config_entries_core.__name__):
            out = config_entries_core.walk(fake_client, "demo", steps=[{"x": 1}])

        # Original behaviour preserved: not completed, error recorded.
        assert out["completed"] is False
        assert any("error" in h for h in out["history"])
        # The abort failure is now logged at DEBUG.
        assert any(
            "flow_abort failed" in r.message and r.levelno == logging.DEBUG
            for r in caplog.records
        ), [r.message for r in caplog.records]


# ───────────────────────────────────── helpers.input_select_update (B110)

class TestInputSelectUpdateLogsBackfillFailure:
    """``input_select_update`` best-effort backfills name/icon from state.

    When the state lookup raises, it was previously swallowed with
    ``except: pass``. The fix logs the failure at DEBUG; the update still
    proceeds (name/icon simply remain unset / None).
    """

    def test_update_logs_when_state_backfill_fails(self, caplog):
        c = FakeClient()
        # No state registered → _get_state raises ValueError.
        c.set_ws("input_select/update", {"id": "voice", "name": None})

        with caplog.at_level(logging.DEBUG, logger=helpers.__name__):
            # options-only update triggers the backfill path (name is None).
            helpers.input_select_update(
                c, "input_select.voice", options=["A", "B"],
            )

        # The update WS call still happened.
        assert c.ws_calls
        assert c.ws_calls[0]["type"] == "input_select/update"
        # The backfill failure was logged at DEBUG.
        assert any(
            "backfill" in r.message and r.levelno == logging.DEBUG
            for r in caplog.records
        ), [r.message for r in caplog.records]
