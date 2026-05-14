"""Tests for cli_anything.homeassistant.core.history_ext."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from cli_anything.homeassistant.core import history_ext


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _states(entity_id, rows):
    """Helper to build a /api/history/period response."""
    return [
        [{"entity_id": entity_id, "state": str(v), "last_changed": t.isoformat()}
         for t, v in rows]
    ]


def _stats(entity_id, rows, field="mean"):
    """Helper to build a recorder/statistics_during_period response."""
    return {
        entity_id: [
            {"start": _ms(t), "end": _ms(t + timedelta(hours=1)), field: v}
            for t, v in rows
        ]
    }


# ── statistics_to_samples ────────────────────────────────────────────────


class TestStatisticsToSamples:
    def test_converts_buckets_to_flat_samples(self):
        t0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        resp = _stats("sensor.foo", [(t0, 50.0), (t0 + timedelta(hours=1), 51.5)])
        out = history_ext.statistics_to_samples(resp, statistic_id="sensor.foo")
        assert len(out) == 2
        assert out[0]["when"] == t0
        assert out[0]["value"] == 50.0
        assert out[0]["source"] == "statistics"

    def test_empty_when_id_missing(self):
        resp = {"sensor.bar": []}
        out = history_ext.statistics_to_samples(resp, statistic_id="sensor.foo")
        assert out == []

    def test_value_field_max(self):
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        resp = {
            "sensor.foo": [
                {"start": _ms(t0), "end": _ms(t0 + timedelta(hours=1)),
                 "mean": 50.0, "max": 75.0, "min": 40.0}
            ]
        }
        out = history_ext.statistics_to_samples(
            resp, statistic_id="sensor.foo", value_field="max")
        assert out[0]["value"] == 75.0

    def test_value_field_invalid_raises(self):
        with pytest.raises(ValueError, match="invalid value_field"):
            history_ext.statistics_to_samples({}, statistic_id="sensor.foo", value_field="bogus")

    def test_missing_statistic_id_raises(self):
        with pytest.raises(ValueError, match="statistic_id is required"):
            history_ext.statistics_to_samples({}, statistic_id="")

    def test_skips_non_numeric_values(self):
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        resp = {
            "sensor.foo": [
                {"start": _ms(t0), "mean": None},
                {"start": _ms(t0 + timedelta(hours=1)), "mean": "not a number"},
                {"start": _ms(t0 + timedelta(hours=2)), "mean": 50.0},
            ]
        }
        out = history_ext.statistics_to_samples(resp, statistic_id="sensor.foo")
        assert len(out) == 1
        assert out[0]["value"] == 50.0


# ── history_with_stats_fallback ──────────────────────────────────────────


class TestHistoryWithStatsFallback:
    def test_recorder_only_when_window_within_retention(self, fake_client):
        """If the recorder has data covering `start`, no stats call needed."""
        now = datetime.now(timezone.utc)
        # Recorder returns the full window
        recorder_rows = [
            (now - timedelta(hours=3), 100.0),
            (now - timedelta(hours=2), 110.0),
            (now - timedelta(hours=1), 120.0),
        ]
        fake_client.set(
            "GET", "history/period/" + (now - timedelta(hours=4)).isoformat(),
            _states("sensor.foo", recorder_rows),
        )
        # If stats is called, return empty so we can detect
        fake_client.set_ws("recorder/statistics_during_period", {})

        result = history_ext.history_with_stats_fallback(
            fake_client,
            entity_id="sensor.foo",
            start=now - timedelta(hours=4),
            end=now,
        )
        # All from recorder
        assert all(s["source"] == "recorder" for s in result)
        assert len(result) == 3

    def test_stats_backfill_when_recorder_short(self, fake_client):
        """Recorder only has the most recent portion → stats fills the rest."""
        now = datetime.now(timezone.utc).replace(microsecond=0)
        # Recorder has from 24h ago to now
        recorder_start = now - timedelta(hours=24)
        recorder_rows = [(now - timedelta(hours=6), 100.0)]
        # But we ask for the last 7 days
        requested_start = now - timedelta(days=7)
        # GET path is built from requested_start
        fake_client.set(
            "GET", f"history/period/{requested_start.isoformat()}",
            _states("sensor.foo", recorder_rows),
        )
        # Stats covers days 7-1 (the older part)
        stats_rows = [(requested_start + timedelta(hours=i*24), 50.0 + i)
                       for i in range(6)]
        fake_client.set_ws(
            "recorder/statistics_during_period",
            _stats("sensor.foo", stats_rows),
        )

        result = history_ext.history_with_stats_fallback(
            fake_client,
            entity_id="sensor.foo",
            start=requested_start,
            end=now,
        )
        # Stats samples + recorder samples, chronological
        sources = [s["source"] for s in result]
        # First samples are stats, then transition to recorder
        assert "statistics" in sources
        assert "recorder" in sources
        # Stats come first chronologically (older)
        first_stats_idx = sources.index("statistics")
        last_stats_idx = len(sources) - 1 - sources[::-1].index("statistics")
        first_recorder_idx = sources.index("recorder")
        assert last_stats_idx < first_recorder_idx

    def test_only_stats_when_recorder_empty(self, fake_client):
        now = datetime.now(timezone.utc)
        requested_start = now - timedelta(days=30)
        fake_client.set(
            "GET", f"history/period/{requested_start.isoformat()}",
            [],  # recorder returns nothing
        )
        stats_rows = [(requested_start + timedelta(days=i), 100.0 + i)
                       for i in range(5)]
        fake_client.set_ws(
            "recorder/statistics_during_period",
            _stats("sensor.foo", stats_rows),
        )
        result = history_ext.history_with_stats_fallback(
            fake_client,
            entity_id="sensor.foo",
            start=requested_start,
            end=now,
        )
        assert len(result) == 5
        assert all(s["source"] == "statistics" for s in result)

    def test_empty_entity_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="entity_id is required"):
            history_ext.history_with_stats_fallback(
                fake_client, entity_id="",
                start=datetime.now(timezone.utc) - timedelta(hours=1),
            )

    def test_start_after_end_raises(self, fake_client):
        now = datetime.now(timezone.utc)
        with pytest.raises(ValueError, match="start must be before end"):
            history_ext.history_with_stats_fallback(
                fake_client, entity_id="sensor.foo",
                start=now, end=now - timedelta(hours=1),
            )

    def test_result_is_chronological(self, fake_client):
        """Merged output must be sorted chronologically regardless of source order."""
        now = datetime.now(timezone.utc).replace(microsecond=0)
        requested_start = now - timedelta(days=3)
        # Recorder rows interleaved chronologically
        recorder_rows = [
            (now - timedelta(hours=2), 200.0),
            (now - timedelta(hours=1), 210.0),
        ]
        fake_client.set(
            "GET", f"history/period/{requested_start.isoformat()}",
            _states("sensor.foo", recorder_rows),
        )
        stats_rows = [
            (requested_start, 100.0),
            (requested_start + timedelta(hours=12), 110.0),
            (requested_start + timedelta(hours=24), 120.0),
        ]
        fake_client.set_ws(
            "recorder/statistics_during_period",
            _stats("sensor.foo", stats_rows),
        )
        result = history_ext.history_with_stats_fallback(
            fake_client, entity_id="sensor.foo",
            start=requested_start, end=now,
        )
        whens = [s["when"] for s in result]
        assert whens == sorted(whens)


# ── recorder_retention_estimate ──────────────────────────────────────────


class TestRecorderRetentionEstimate:
    def test_empty_recorder_returns_zero(self, fake_client, monkeypatch):
        monkeypatch.setattr(history_ext._history, "history",
                              lambda *a, **kw: [])
        est = history_ext.recorder_retention_estimate(
            fake_client, entity_id="sensor.foo", probe_days=60)
        assert est["sample_count"] == 0
        assert est["retention_days"] == 0.0
        assert est["first_sample"] is None

    def test_reports_first_sample_age(self, fake_client, monkeypatch):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        rows = [
            (now - timedelta(days=25), 50.0),
            (now - timedelta(hours=1), 60.0),
        ]
        monkeypatch.setattr(
            history_ext._history, "history",
            lambda *a, **kw: _states("sensor.foo", rows),
        )
        est = history_ext.recorder_retention_estimate(
            fake_client, entity_id="sensor.foo", probe_days=60)
        assert est["sample_count"] == 2
        assert 24.9 < est["retention_days"] < 25.1  # roughly 25 days

    def test_empty_entity_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="entity_id is required"):
            history_ext.recorder_retention_estimate(fake_client, entity_id="")
