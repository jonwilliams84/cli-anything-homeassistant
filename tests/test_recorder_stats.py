"""Tests for recorder introspection: entity_stats, batch_stats,
find_unrecorded, purge_entities edge cases, and top_entities.

These exercise the HTTP-history parsing, span calculation, error
swallowing, and ranking logic that was previously uncovered.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import recorder as recorder_core


def _make_history_client(fake_client, history_data, states_data=None):
    """Wrap a FakeClient so dynamic-timestamp history paths resolve.

    entity_stats / top_entities call ``client.get("history/period/<iso>")``
    with a timestamp we can't predict at test-write time.  This helper
    patches ``get`` to match any path starting with ``history/period/``.
    """
    original_get = fake_client.get

    def smart_get(path, params=None):
        if path.startswith("history/period/"):
            return history_data
        if states_data is not None and path == "states":
            return states_data
        return original_get(path, params)

    fake_client.get = smart_get
    return fake_client


# ─── entity_stats ──────────────────────────────────────────────────────────

class TestEntityStats:
    def test_empty_entity_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="entity_id is required"):
            recorder_core.entity_stats(fake_client, "")

    def test_live_state_error_returns_none(self, fake_client):
        """When the states/ endpoint raises, live fields are None."""
        original_get = fake_client.get

        def error_on_states(path, params=None):
            if path.startswith("states/"):
                raise RuntimeError("boom")
            if path.startswith("history/period/"):
                return [[
                    {"last_changed": "2024-01-01T00:00:00+00:00"},
                    {"last_changed": "2024-01-01T01:00:00+00:00"},
                ]]
            return original_get(path, params)

        fake_client.get = error_on_states
        out = recorder_core.entity_stats(fake_client, "sensor.foo")
        assert out["live_state"] is None
        assert out["live_last_changed"] is None
        assert out["is_recorded"] is True

    def test_history_span_calculated(self, fake_client):
        """Span is the difference between first and last last_changed."""
        fake_client.set("GET", "states/sensor.temp", {"state": "23.5", "last_changed": "2024-01-01T00:00:00+00:00"})
        client = _make_history_client(fake_client, [[
            {"last_changed": "2024-01-01T00:00:00+00:00"},
            {"last_changed": "2024-01-01T02:00:00+00:00"},
        ]])
        out = recorder_core.entity_stats(client, "sensor.temp")
        assert out["history_points_24h"] == 2
        assert out["history_span_hours"] == pytest.approx(2.0)
        assert out["live_state"] == "23.5"
        assert out["is_recorded"] is True

    def test_history_span_with_z_suffix(self, fake_client):
        """ISO timestamps with 'Z' suffix are parsed correctly."""
        fake_client.set("GET", "states/sensor.temp", {"state": "1"})
        client = _make_history_client(fake_client, [[
            {"last_changed": "2024-01-01T00:00:00Z"},
            {"last_changed": "2024-01-01T03:30:00Z"},
        ]])
        out = recorder_core.entity_stats(client, "sensor.temp")
        assert out["history_span_hours"] == pytest.approx(3.5)

    def test_history_span_invalid_timestamps_returns_none(self, fake_client):
        """When timestamps can't be parsed, span_h is None."""
        fake_client.set("GET", "states/sensor.x", {"state": "1"})
        client = _make_history_client(fake_client, [[
            {"last_changed": "not-a-date"},
            {"last_changed": "also-not-a-date"},
        ]])
        out = recorder_core.entity_stats(client, "sensor.x")
        assert out["history_span_hours"] is None
        assert out["is_recorded"] is True

    def test_no_history_points(self, fake_client):
        """Empty history list → is_recorded False, points 0."""
        fake_client.set("GET", "states/sensor.x", {"state": "off"})
        client = _make_history_client(fake_client, [[]])
        out = recorder_core.entity_stats(client, "sensor.x")
        assert out["history_points_24h"] == 0
        assert out["is_recorded"] is False
        assert out["history_first"] is None
        assert out["history_last"] is None

    def test_history_not_nested_list(self, fake_client):
        """When raw is a list but not list-of-lists, points stays empty."""
        fake_client.set("GET", "states/sensor.x", {"state": "off"})
        client = _make_history_client(fake_client, [{"unexpected": "shape"}])
        out = recorder_core.entity_stats(client, "sensor.x")
        assert out["history_points_24h"] == 0
        assert out["is_recorded"] is False


# ─── batch_stats / find_unrecorded ─────────────────────────────────────────

class TestBatchStats:
    def test_batch_stats_returns_list(self, fake_client):
        fake_client.set("GET", "states/sensor.a", {"state": "1"})
        fake_client.set("GET", "states/sensor.b", {"state": "2"})
        client = _make_history_client(fake_client, [[{"last_changed": "2024-01-01T00:00:00+00:00"}]])
        results = recorder_core.batch_stats(client, ["sensor.a", "sensor.b"])
        assert len(results) == 2
        assert all(r["entity_id"] in ("sensor.a", "sensor.b") for r in results)

    def test_find_unrecorded_filters_zero_points(self, fake_client):
        """Only entities with zero history points are returned."""
        fake_client.set("GET", "states/sensor.recorded", {"state": "1"})
        fake_client.set("GET", "states/sensor.unrecorded", {"state": "2"})
        call_count = [0]
        original_get = fake_client.get

        def selective_get(path, params=None):
            if "history" in path:
                call_count[0] += 1
                if call_count[0] == 1:
                    return [[{"last_changed": "2024-01-01T00:00:00+00:00"}]]
                else:
                    return [[]]
            return original_get(path, params)

        fake_client.get = selective_get
        unrecorded = recorder_core.find_unrecorded(fake_client, ["sensor.recorded", "sensor.unrecorded"])
        assert "sensor.unrecorded" in unrecorded
        assert "sensor.recorded" not in unrecorded


# ─── purge_entities edge cases ─────────────────────────────────────────────

class TestPurgeEntitiesEdgeCases:
    def test_purge_entities_only_domains(self, fake_client):
        """Purging by domains alone (no entity_ids) works."""
        fake_client.set_service("recorder", "purge_entities", {"ok": True})
        recorder_core.purge_entities(fake_client, entity_ids=[], domains=["sensor"])
        last = fake_client.service_calls[-1]
        assert last["service_data"]["domains"] == ["sensor"]
        assert "entity_id" not in last["service_data"]

    def test_purge_entities_only_globs(self, fake_client):
        fake_client.set_service("recorder", "purge_entities", {})
        recorder_core.purge_entities(fake_client, entity_ids=[], entity_globs=["sensor.test_*"])
        last = fake_client.service_calls[-1]
        assert last["service_data"]["entity_globs"] == ["sensor.test_*"]

    def test_purge_entities_no_args_raises(self, fake_client):
        """When no filter args are provided at all, a ValueError is raised."""
        with pytest.raises(ValueError, match="provide at least one"):
            recorder_core.purge_entities(fake_client, entity_ids=[])

    def test_purge_entities_days_alone_works(self, fake_client):
        """days alone is sufficient — it populates the service data."""
        fake_client.set_service("recorder", "purge_entities", {})
        recorder_core.purge_entities(fake_client, entity_ids=[], days=3)
        last = fake_client.service_calls[-1]
        assert last["service_data"]["days"] == 3


# ─── top_entities ──────────────────────────────────────────────────────────

class TestTopEntities:
    def test_invalid_by_raises(self, fake_client):
        with pytest.raises(ValueError, match="by must be 'changes'"):
            recorder_core.top_entities(fake_client, by="bytes")

    def test_ranks_by_change_count(self, fake_client):
        """Entities are ranked by descending state-change count."""
        states = [
            {"entity_id": "sensor.quiet", "attributes": {"friendly_name": "Quiet"}},
            {"entity_id": "sensor.busy", "attributes": {"friendly_name": "Busy"}},
        ]
        call_idx = [0]

        def selective_get(path, params=None):
            if "history" in path:
                call_idx[0] += 1
                if call_idx[0] == 1:
                    return [[{"state": "a"}, {"state": "b"}, {"state": "c"}]]
                else:
                    return [[{"state": "x"}, {"state": "y"}]]
            if path == "states":
                return states
            return fake_client.responses.get(("GET", path.split("?")[0]), [])

        fake_client.get = selective_get
        rows = recorder_core.top_entities(fake_client, hours=1, limit=10)
        assert len(rows) == 2
        assert rows[0]["entity_id"] == "sensor.quiet"
        assert rows[0]["changes"] == 3
        assert rows[0]["changes_per_hour"] == pytest.approx(3.0)
        assert rows[0]["friendly_name"] == "Quiet"
        assert rows[0]["domain"] == "sensor"

    def test_domain_filter(self, fake_client):
        """Domains filter restricts which entities are sampled."""
        states = [
            {"entity_id": "sensor.included", "attributes": {}},
            {"entity_id": "light.excluded", "attributes": {}},
        ]
        client = _make_history_client(fake_client, [[{"state": "a"}]], states_data=states)
        rows = recorder_core.top_entities(client, domains=["sensor"], hours=1)
        assert len(rows) == 1
        assert rows[0]["entity_id"] == "sensor.included"

    def test_explicit_entity_ids(self, fake_client):
        """When entity_ids is provided, /states is not fetched."""
        client = _make_history_client(fake_client, [[{"state": "a"}, {"state": "b"}]])
        rows = recorder_core.top_entities(client, entity_ids=["sensor.x"], hours=2)
        assert len(rows) == 1
        assert rows[0]["changes"] == 2
        assert rows[0]["changes_per_hour"] == pytest.approx(1.0)
        assert not any(c["path"] == "states" for c in fake_client.calls)

    def test_history_error_skips_entity(self, fake_client):
        """When history fetch raises, the entity is silently skipped."""
        states = [
            {"entity_id": "sensor.error", "attributes": {}},
            {"entity_id": "sensor.ok", "attributes": {}},
        ]
        call_idx = [0]

        def selective_get(path, params=None):
            if "history" in path:
                call_idx[0] += 1
                if call_idx[0] == 1:
                    raise RuntimeError("network error")
                return [[{"state": "a"}]]
            if path == "states":
                return states
            return fake_client.responses.get(("GET", path.split("?")[0]), [])

        fake_client.get = selective_get
        rows = recorder_core.top_entities(fake_client, hours=1)
        assert len(rows) == 1
        assert rows[0]["entity_id"] == "sensor.ok"

    def test_zero_points_skipped(self, fake_client):
        """Entities with zero history points are excluded from results."""
        states = [{"entity_id": "sensor.empty", "attributes": {}}]
        client = _make_history_client(fake_client, [[]], states_data=states)
        rows = recorder_core.top_entities(client, hours=1)
        assert len(rows) == 0

    def test_limit_truncates(self, fake_client):
        """limit caps the number of returned rows."""
        states = [{"entity_id": f"sensor.{i}", "attributes": {}} for i in range(5)]
        client = _make_history_client(fake_client, [[{"state": "a"}]], states_data=states)
        rows = recorder_core.top_entities(client, limit=2)
        assert len(rows) == 2
