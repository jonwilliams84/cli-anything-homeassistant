"""Unit tests for cli_anything.homeassistant.core.statistics_admin.

All tests run without a real Home Assistant instance; the FakeClient
fixture from conftest.py provides WS call recording and canned responses.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import statistics_admin


class TestStatisticsAdmin:

    # ────────────────────────────────────────────────────────────────────
    # adjust_sum_statistics
    # ────────────────────────────────────────────────────────────────────

    def test_adjust_sum_statistics_happy_path(self, fake_client):
        """adjust_sum_statistics sends the expected WS payload."""
        fake_client.set_ws("recorder/adjust_sum_statistics", {"result": "ok"})
        statistics_admin.adjust_sum_statistics(
            fake_client,
            statistic_id="sensor.energy_total",
            start_time="2024-01-01T00:00:00+00:00",
            adjustment=5.5,
            adjustment_unit_of_measurement="kWh",
        )
        assert fake_client.ws_calls[-1]["type"] == "recorder/adjust_sum_statistics"
        assert fake_client.ws_calls[-1]["payload"] == {
            "statistic_id": "sensor.energy_total",
            "start_time": "2024-01-01T00:00:00+00:00",
            "adjustment": 5.5,
            "adjustment_unit_of_measurement": "kWh",
        }

    def test_adjust_sum_statistics_no_unit(self, fake_client):
        """adjustment_unit_of_measurement is omitted from payload when not supplied."""
        statistics_admin.adjust_sum_statistics(
            fake_client,
            statistic_id="sensor.gas_meter",
            start_time="2024-06-01T00:00:00+00:00",
            adjustment=-1.0,
        )
        assert "adjustment_unit_of_measurement" not in fake_client.ws_calls[-1]["payload"]

    def test_adjust_sum_statistics_returns_response(self, fake_client):
        """Return value is whatever the server sends back."""
        fake_client.set_ws("recorder/adjust_sum_statistics", {"status": "queued"})
        result = statistics_admin.adjust_sum_statistics(
            fake_client,
            statistic_id="sensor.x",
            start_time="2024-01-01T00:00:00+00:00",
            adjustment=1.0,
        )
        assert result == {"status": "queued"}

    def test_adjust_sum_statistics_empty_statistic_id(self, fake_client):
        with pytest.raises(ValueError, match="statistic_id"):
            statistics_admin.adjust_sum_statistics(
                fake_client,
                statistic_id="",
                start_time="2024-01-01T00:00:00+00:00",
                adjustment=1.0,
            )

    def test_adjust_sum_statistics_empty_start_time(self, fake_client):
        with pytest.raises(ValueError, match="start_time"):
            statistics_admin.adjust_sum_statistics(
                fake_client,
                statistic_id="sensor.x",
                start_time="",
                adjustment=1.0,
            )

    # ────────────────────────────────────────────────────────────────────
    # change_statistics_unit
    # ────────────────────────────────────────────────────────────────────

    def test_change_statistics_unit_happy_path(self, fake_client):
        """change_statistics_unit sends the expected WS payload."""
        fake_client.set_ws("recorder/change_statistics_unit", {})
        statistics_admin.change_statistics_unit(
            fake_client,
            statistic_id="sensor.energy_meter",
            new_unit_of_measurement="Wh",
            old_unit_of_measurement="kWh",
        )
        assert fake_client.ws_calls[-1]["type"] == "recorder/change_statistics_unit"
        assert fake_client.ws_calls[-1]["payload"] == {
            "statistic_id": "sensor.energy_meter",
            "new_unit_of_measurement": "Wh",
            "old_unit_of_measurement": "kWh",
        }

    def test_change_statistics_unit_returns_response(self, fake_client):
        """Return value passes through."""
        fake_client.set_ws("recorder/change_statistics_unit", {"changed": True})
        result = statistics_admin.change_statistics_unit(
            fake_client,
            statistic_id="sensor.energy_meter",
            new_unit_of_measurement="Wh",
            old_unit_of_measurement="kWh",
        )
        assert result == {"changed": True}

    def test_change_statistics_unit_empty_statistic_id(self, fake_client):
        with pytest.raises(ValueError, match="statistic_id"):
            statistics_admin.change_statistics_unit(
                fake_client,
                statistic_id="",
                new_unit_of_measurement="Wh",
                old_unit_of_measurement="kWh",
            )

    def test_change_statistics_unit_empty_new_unit(self, fake_client):
        with pytest.raises(ValueError, match="new_unit_of_measurement"):
            statistics_admin.change_statistics_unit(
                fake_client,
                statistic_id="sensor.x",
                new_unit_of_measurement="",
                old_unit_of_measurement="kWh",
            )

    def test_change_statistics_unit_empty_old_unit(self, fake_client):
        with pytest.raises(ValueError, match="old_unit_of_measurement"):
            statistics_admin.change_statistics_unit(
                fake_client,
                statistic_id="sensor.x",
                new_unit_of_measurement="Wh",
                old_unit_of_measurement="",
            )

    # ────────────────────────────────────────────────────────────────────
    # validate_statistics
    # ────────────────────────────────────────────────────────────────────

    def test_validate_statistics_happy_path(self, fake_client):
        """validate_statistics sends recorder/validate_statistics with empty payload."""
        canned = {
            "sensor.broken": [
                {"type": "unsupported_state_class", "data": {"state_class": "total"}}
            ]
        }
        fake_client.set_ws("recorder/validate_statistics", canned)
        result = statistics_admin.validate_statistics(fake_client)
        assert fake_client.ws_calls[-1]["type"] == "recorder/validate_statistics"
        assert fake_client.ws_calls[-1]["payload"] == {}
        assert "sensor.broken" in result

    def test_validate_statistics_returns_dict(self, fake_client):
        """Return value is always a dict (even when server returns empty)."""
        fake_client.set_ws("recorder/validate_statistics", {})
        result = statistics_admin.validate_statistics(fake_client)
        assert isinstance(result, dict)

    def test_validate_statistics_non_dict_response_gives_empty_dict(self, fake_client):
        """If the server returns a non-dict (unexpected), we return {}."""
        fake_client.set_ws("recorder/validate_statistics", None)
        result = statistics_admin.validate_statistics(fake_client)
        assert result == {}

    # ────────────────────────────────────────────────────────────────────
    # update_statistics_issues
    # ────────────────────────────────────────────────────────────────────

    def test_update_statistics_issues_happy_path(self, fake_client):
        """update_statistics_issues sends the expected WS payload."""
        fake_client.set_ws("recorder/update_statistics_issues", {})
        statistics_admin.update_statistics_issues(
            fake_client,
            issue_type="unsupported_state_class",
            statistic_id="sensor.broken",
        )
        assert fake_client.ws_calls[-1]["type"] == "recorder/update_statistics_issues"
        assert fake_client.ws_calls[-1]["payload"] == {
            "statistic_id": "sensor.broken",
            "type": "unsupported_state_class",
        }

    def test_update_statistics_issues_returns_response(self, fake_client):
        """Return value passes through from the server."""
        fake_client.set_ws("recorder/update_statistics_issues", {"cleared": True})
        result = statistics_admin.update_statistics_issues(
            fake_client,
            issue_type="units_changed",
            statistic_id="sensor.foo",
        )
        assert result == {"cleared": True}

    def test_update_statistics_issues_empty_statistic_id(self, fake_client):
        with pytest.raises(ValueError, match="statistic_id"):
            statistics_admin.update_statistics_issues(
                fake_client,
                issue_type="unsupported_state_class",
                statistic_id="",
            )

    def test_update_statistics_issues_empty_type(self, fake_client):
        with pytest.raises(ValueError, match="issue_type"):
            statistics_admin.update_statistics_issues(
                fake_client,
                issue_type="",
                statistic_id="sensor.foo",
            )

    # ────────────────────────────────────────────────────────────────────
    # update_statistics_metadata
    # ────────────────────────────────────────────────────────────────────

    def test_update_statistics_metadata_happy_path(self, fake_client):
        """update_statistics_metadata sends the expected WS payload."""
        fake_client.set_ws("recorder/update_statistics_metadata", {})
        statistics_admin.update_statistics_metadata(
            fake_client,
            statistic_id="sensor.energy_total",
            unit_of_measurement="kWh",
        )
        assert fake_client.ws_calls[-1]["type"] == "recorder/update_statistics_metadata"
        assert fake_client.ws_calls[-1]["payload"] == {
            "statistic_id": "sensor.energy_total",
            "unit_of_measurement": "kWh",
        }

    def test_update_statistics_metadata_clears_unit(self, fake_client):
        """Passing unit_of_measurement=None sends None in the payload."""
        statistics_admin.update_statistics_metadata(
            fake_client,
            statistic_id="sensor.dimensionless",
            unit_of_measurement=None,
        )
        assert fake_client.ws_calls[-1]["payload"]["unit_of_measurement"] is None

    def test_update_statistics_metadata_returns_response(self, fake_client):
        """Return value passes through from the server."""
        fake_client.set_ws("recorder/update_statistics_metadata", {"updated": True})
        result = statistics_admin.update_statistics_metadata(
            fake_client,
            statistic_id="sensor.x",
            unit_of_measurement="W",
        )
        assert result == {"updated": True}

    def test_update_statistics_metadata_empty_statistic_id(self, fake_client):
        with pytest.raises(ValueError, match="statistic_id"):
            statistics_admin.update_statistics_metadata(
                fake_client,
                statistic_id="",
                unit_of_measurement="kWh",
            )

    # ────────────────────────────────────────────────────────────────────
    # import_statistics
    # ────────────────────────────────────────────────────────────────────

    def test_import_statistics_happy_path(self, fake_client):
        """import_statistics sends the expected WS payload."""
        meta = {
            "statistic_id": "myintegration:energy",
            "source": "myintegration",
            "name": "Energy Import",
            "unit_of_measurement": "kWh",
            "has_mean": False,
            "has_sum": True,
        }
        rows = [
            {"start": "2024-01-01T00:00:00+00:00", "sum": 100.0},
            {"start": "2024-01-01T01:00:00+00:00", "sum": 101.5},
        ]
        fake_client.set_ws("recorder/import_statistics", {})
        statistics_admin.import_statistics(fake_client, metadata=meta, stats=rows)
        assert fake_client.ws_calls[-1]["type"] == "recorder/import_statistics"
        assert fake_client.ws_calls[-1]["payload"] == {
            "metadata": meta,
            "stats": rows,
        }

    def test_import_statistics_returns_response(self, fake_client):
        """Return value passes through."""
        meta = {
            "statistic_id": "sensor.power",
            "source": "recorder",
            "name": None,
            "unit_of_measurement": "W",
            "has_mean": True,
            "has_sum": False,
        }
        rows = [{"start": "2024-01-01T00:00:00+00:00", "mean": 250.0}]
        fake_client.set_ws("recorder/import_statistics", {"imported": 1})
        result = statistics_admin.import_statistics(
            fake_client, metadata=meta, stats=rows
        )
        assert result == {"imported": 1}

    def test_import_statistics_empty_statistic_id(self, fake_client):
        meta = {
            "statistic_id": "",
            "source": "test",
            "name": None,
            "unit_of_measurement": None,
            "has_mean": False,
            "has_sum": True,
        }
        with pytest.raises(ValueError, match="statistic_id"):
            statistics_admin.import_statistics(
                fake_client,
                metadata=meta,
                stats=[{"start": "2024-01-01T00:00:00+00:00", "sum": 1.0}],
            )

    def test_import_statistics_empty_stats_list(self, fake_client):
        meta = {
            "statistic_id": "sensor.power",
            "source": "recorder",
            "name": None,
            "unit_of_measurement": "W",
            "has_mean": True,
            "has_sum": False,
        }
        with pytest.raises(ValueError, match="stats"):
            statistics_admin.import_statistics(
                fake_client, metadata=meta, stats=[]
            )

    def test_import_statistics_metadata_none_raises(self, fake_client):
        """import_statistics raises ValueError when metadata is None."""
        with pytest.raises(ValueError, match="metadata must be a dict"):
            statistics_admin.import_statistics(
                fake_client,
                metadata=None,
                stats=[{"start": "2024-01-01T00:00:00+00:00", "sum": 1.0}],
            )

    def test_import_statistics_metadata_non_dict_raises(self, fake_client):
        """import_statistics raises ValueError when metadata is not a dict."""
        with pytest.raises(ValueError, match="metadata must be a dict"):
            statistics_admin.import_statistics(
                fake_client,
                metadata="sensor.energy",
                stats=[{"start": "2024-01-01T00:00:00+00:00", "sum": 1.0}],
            )
