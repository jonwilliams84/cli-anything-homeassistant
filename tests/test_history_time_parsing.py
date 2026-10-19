"""Regression tests for GitHub issue #50.

``history-ext with-stats-fallback`` crashed with
``TypeError: can't compare offset-naive and offset-aware datetimes`` when
``--start`` had no timezone and ``--end`` was left at its aware default
(``now()``). These tests lock in the shared time parsing
(``core/timeparse.py``) that makes naive, aware and mixed ``--start``/
``--end`` behave consistently across the ``history`` command and every
``history-ext`` / ``history-logbook`` entry point that parses times.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from click.testing import CliRunner

from cli_anything.homeassistant import homeassistant_cli as cli_mod
from cli_anything.homeassistant.core import history_ext
from cli_anything.homeassistant.core.timeparse import parse_time_arg, parse_time_range


# ── shared parser: parse_time_arg ────────────────────────────────────────


class TestParseTimeArg:
    def test_naive_is_treated_as_utc(self):
        dt = parse_time_arg("2026-05-01T00:00:00", field="--start")
        assert dt.tzinfo is not None
        assert dt.utcoffset() == timedelta(0)
        assert dt.replace(tzinfo=None) == datetime(2026, 5, 1)

    def test_aware_offset_is_preserved(self):
        dt = parse_time_arg("2026-05-01T00:00:00+02:00", field="--start")
        assert dt.utcoffset() == timedelta(hours=2)

    def test_z_suffix_accepted(self):
        dt = parse_time_arg("2026-05-01T00:00:00Z", field="--end")
        assert dt == datetime(2026, 5, 1, tzinfo=timezone.utc)

    def test_none_returns_default(self):
        sentinel = datetime(2026, 10, 19, tzinfo=timezone.utc)
        assert parse_time_arg(None, default=sentinel) is sentinel
        assert parse_time_arg(None) is None

    def test_empty_string_returns_default(self):
        assert parse_time_arg("  ", field="--start", default=None) is None

    def test_datetime_passthrough(self):
        aware = datetime(2026, 5, 1, tzinfo=timezone.utc)
        assert parse_time_arg(aware) is aware

    def test_invalid_string_raises_with_field_name(self):
        with pytest.raises(ValueError, match="invalid --start"):
            parse_time_arg("not-a-date", field="--start")

    def test_invalid_string_raises_with_end_field_name(self):
        with pytest.raises(ValueError, match="invalid --end"):
            parse_time_arg("yesterday-ish", field="--end")


# ── shared parser: parse_time_range (mixed naive/aware is issue #50) ─────


class TestParseTimeRange:
    def test_naive_start_with_aware_default_end(self):
        """The exact issue #50 input: naive --start, no --end."""
        start, end = parse_time_range("2026-05-01T00:00:00", None)
        assert start.tzinfo is not None
        assert end is not None and end.tzinfo is not None
        assert start < end  # no offset-naive/aware TypeError

    def test_naive_start_with_aware_end(self):
        aware_end = datetime(2026, 5, 2, tzinfo=timezone.utc)
        start, end = parse_time_range("2026-05-01T00:00:00", None,
                                      default_end=aware_end)
        assert start < end

    def test_aware_start_with_naive_end(self):
        aware_start = datetime(2026, 5, 1, tzinfo=timezone.utc)
        start, end = parse_time_range("2026-05-01T00:00:00Z",
                                      "2026-05-02T00:00:00")
        assert start == aware_start
        assert end == datetime(2026, 5, 2, tzinfo=timezone.utc)

    def test_both_naive(self):
        start, end = parse_time_range("2026-05-01T00:00:00",
                                      "2026-05-02T00:00:00")
        assert start < end
        assert start.tzinfo is not None and end.tzinfo is not None

    def test_start_after_end_raises(self):
        with pytest.raises(ValueError, match="must be before"):
            parse_time_range("2026-05-02T00:00:00", "2026-05-01T00:00:00")

    def test_missing_start_raises(self):
        with pytest.raises(ValueError, match="--start is required"):
            parse_time_range(None, None)


# ── core regression: naive start vs aware default end (issue #50) ────────


class TestFallbackNaiveAwareMixes:
    def _stats(self, entity_id, rows, field="mean"):
        return {
            entity_id: [
                {"start": int(t.timestamp() * 1000),
                 "end": int((t + timedelta(hours=1)).timestamp() * 1000),
                 field: v}
                for t, v in rows
            ]
        }

    def test_naive_start_default_end_no_crash(self, fake_client, monkeypatch):
        """Issue #50: naive --start, aware default --end → TypeError."""
        naive_start = datetime.now(timezone.utc).replace(
            tzinfo=None) - timedelta(hours=2)
        stats_rows = [(naive_start - timedelta(hours=3), 40.0),
                      (naive_start - timedelta(hours=2), 42.0)]
        monkeypatch.setattr(history_ext._history, "history",
                            lambda *a, **kw: [])
        monkeypatch.setattr(
            history_ext._statistics, "statistics_during_period",
            lambda *a, **kw: self._stats("sensor.foo", stats_rows),
        )
        result = history_ext.history_with_stats_fallback(
            fake_client, entity_id="sensor.foo", start=naive_start)
        assert [s["value"] for s in result] == [40.0, 42.0]
        assert all(s["source"] == "statistics" for s in result)

    def test_naive_start_aware_end(self, fake_client, monkeypatch):
        naive_start = datetime.now(timezone.utc).replace(
            tzinfo=None) - timedelta(hours=2)
        aware_end = datetime.now(timezone.utc)
        monkeypatch.setattr(history_ext._history, "history",
                            lambda *a, **kw: [])
        monkeypatch.setattr(
            history_ext._statistics, "statistics_during_period",
            lambda *a, **kw: self._stats("sensor.foo", [(naive_start, 7.0)]),
        )
        result = history_ext.history_with_stats_fallback(
            fake_client, entity_id="sensor.foo", start=naive_start,
            end=aware_end)
        assert result[0]["value"] == 7.0

    def test_aware_start_naive_end(self, fake_client, monkeypatch):
        aware_start = datetime.now(timezone.utc) - timedelta(hours=2)
        naive_end = (aware_start + timedelta(hours=1)).replace(tzinfo=None)
        monkeypatch.setattr(history_ext._history, "history",
                            lambda *a, **kw: [])
        monkeypatch.setattr(
            history_ext._statistics, "statistics_during_period",
            lambda *a, **kw: self._stats("sensor.foo", [(aware_start, 3.0)]),
        )
        result = history_ext.history_with_stats_fallback(
            fake_client, entity_id="sensor.foo", start=aware_start,
            end=naive_end)
        assert result[0]["value"] == 3.0

    def test_both_naive_no_crash(self, fake_client, monkeypatch):
        start = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=3)
        end = start + timedelta(hours=2)
        monkeypatch.setattr(history_ext._history, "history",
                            lambda *a, **kw: [])
        monkeypatch.setattr(
            history_ext._statistics, "statistics_during_period",
            lambda *a, **kw: self._stats("sensor.foo", [(start, 1.0)]),
        )
        result = history_ext.history_with_stats_fallback(
            fake_client, entity_id="sensor.foo", start=start, end=end)
        assert result[0]["value"] == 1.0


# ── CLI regression: history and history-ext with-stats-fallback ──────────


@pytest.fixture
def runner(monkeypatch, fake_client):
    monkeypatch.setattr(cli_mod, "make_client", lambda ctx: fake_client)
    return CliRunner()


def _invoke(runner, *args):
    return runner.invoke(
        cli_mod.cli,
        ["--json", *args],
        obj={
            "url": "http://x", "token": "t", "verify_ssl": False,
            "timeout": 5, "as_json": True, "config_path": None,
        },
    )


class TestCliTimeParsing:
    def test_with_stats_fallback_naive_start(self, runner, fake_client):
        """Issue #50 end-to-end: naive --start must not crash the CLI."""
        naive = "2026-05-01T00:00:00"
        start_aware = datetime(2026, 5, 1, tzinfo=timezone.utc)
        fake_client.set(
            "GET", f"history/period/{start_aware.isoformat()}",
            [[]],
        )
        bucket = {
            "start": int(start_aware.timestamp() * 1000),
            "end": int((start_aware + timedelta(hours=1)).timestamp() * 1000),
            "mean": 11.5,
        }
        fake_client.set_ws("recorder/statistics_during_period",
                           {"sensor.temp": [bucket]})
        r = _invoke(runner, "history-ext", "with-stats-fallback",
                    "sensor.temp", "--start", naive)
        assert r.exit_code == 0, r.output
        out = r.output if isinstance(r.output, str) else r.output.decode()
        assert '"value": 11.5' in out.replace(" ", "") .replace(":", ": ") or "11.5" in out

    def test_with_stats_fallback_naive_start_aware_end(self, runner, fake_client):
        fake_client.set("GET", "history/period/2026-05-01T00:00:00+00:00", [[]])
        fake_client.set_ws("recorder/statistics_during_period", {})
        r = _invoke(runner, "history-ext", "with-stats-fallback",
                    "sensor.temp", "--start", "2026-05-01T00:00:00",
                    "--end", "2026-05-02T00:00:00+00:00")
        assert r.exit_code == 0, r.output

    def test_with_stats_fallback_aware_start_naive_end(self, runner, fake_client):
        fake_client.set("GET", "history/period/2026-05-01T00:00:00+00:00", [[]])
        fake_client.set_ws("recorder/statistics_during_period", {})
        r = _invoke(runner, "history-ext", "with-stats-fallback",
                    "sensor.temp", "--start", "2026-05-01T00:00:00Z",
                    "--end", "2026-05-02T00:00:00")
        assert r.exit_code == 0, r.output

    def test_history_naive_start_and_end(self, runner, fake_client):
        """The `history` command's parsing must stay consistent (naive=UTC)."""
        fake_client.set(
            "GET", "history/period/2026-05-01T00:00:00+00:00",
            [{"entity_id": "sensor.temp", "state": "20",
              "last_changed": "2026-05-01T01:00:00+00:00"}],
        )
        r = _invoke(runner, "history", "-e", "sensor.temp",
                    "--start", "2026-05-01T00:00:00", "--end",
                    "2026-05-02T00:00:00")
        assert r.exit_code == 0, r.output
        params = fake_client.calls[0]["params"]
        assert params["end_time"] == "2026-05-02T00:00:00+00:00"

    def test_history_z_suffix_start(self, runner, fake_client):
        fake_client.set("GET", "history/period/2026-05-01T00:00:00+00:00", [])
        r = _invoke(runner, "history", "-e", "sensor.temp", "--start",
                    "2026-05-01T00:00:00Z")
        assert r.exit_code == 0, r.output

    def test_history_invalid_start_fails_fast(self, runner):
        r = _invoke(runner, "history", "-e", "sensor.temp",
                    "--start", "not-a-date")
        assert r.exit_code != 0
        assert "invalid --start" in r.output

    def test_with_stats_fallback_start_after_end_raises(self, runner):
        r = _invoke(runner, "history-ext", "with-stats-fallback",
                    "sensor.temp", "--start", "2026-05-02T00:00:00",
                    "--end", "2026-05-01T00:00:00")
        assert r.exit_code != 0
        assert "must be before" in r.output
