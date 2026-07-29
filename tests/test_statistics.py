"""Tests for statistics.py — the long-term-statistics helpers.

Covers validation paths, payload construction, and the info/clear/update
functions that were previously untested.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import statistics as stats


class TestListStatisticIds:
    def test_no_filter_sends_none_payload(self, fake_client):
        fake_client.set_ws("recorder/list_statistic_ids", [{"statistic_id": "sensor.x"}])
        rows = stats.list_statistic_ids(fake_client)
        assert len(rows) == 1
        last = fake_client.ws_calls[-1]
        assert last["payload"] is None

    def test_mean_filter(self, fake_client):
        fake_client.set_ws("recorder/list_statistic_ids", [])
        stats.list_statistic_ids(fake_client, statistic_type="mean")
        assert fake_client.ws_calls[-1]["payload"] == {"statistic_type": "mean"}

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError, match="statistic_type must be"):
            stats.list_statistic_ids(None, statistic_type="median")

    def test_non_list_response_returns_empty(self, fake_client):
        """When the server returns a non-list, we get [] not a crash."""
        fake_client.set_ws("recorder/list_statistic_ids", {"unexpected": "dict"})
        assert stats.list_statistic_ids(fake_client) == []


class TestGetMetadata:
    def test_with_ids_sends_payload(self, fake_client):
        fake_client.set_ws("recorder/get_statistics_metadata", [{"statistic_id": "sensor.x"}])
        stats.get_metadata(fake_client, statistic_ids=["sensor.x", "sensor.y"])
        last = fake_client.ws_calls[-1]
        assert last["payload"] == {"statistic_ids": ["sensor.x", "sensor.y"]}

    def test_non_list_response_returns_empty(self, fake_client):
        fake_client.set_ws("recorder/get_statistics_metadata", None)
        assert stats.get_metadata(fake_client) == []


class TestStatisticsDuringPeriod:
    def test_end_time_included_in_payload(self, fake_client):
        fake_client.set_ws("recorder/statistics_during_period", {"data": 1})
        stats.statistics_during_period(
            fake_client,
            statistic_ids=["sensor.x"],
            start_time="2024-01-01T00:00:00+00:00",
            end_time="2024-01-02T00:00:00+00:00",
        )
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["end_time"] == "2024-01-02T00:00:00+00:00"

    def test_types_included_in_payload(self, fake_client):
        fake_client.set_ws("recorder/statistics_during_period", {})
        stats.statistics_during_period(
            fake_client,
            statistic_ids=["sensor.x"],
            start_time="2024-01-01T00:00:00+00:00",
            types=["mean", "sum"],
        )
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["types"] == ["mean", "sum"]

    def test_units_included_in_payload(self, fake_client):
        fake_client.set_ws("recorder/statistics_during_period", {})
        units = {"sensor.x": "kWh"}
        stats.statistics_during_period(
            fake_client,
            statistic_ids=["sensor.x"],
            start_time="2024-01-01T00:00:00+00:00",
            units=units,
        )
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["units"] == units

    def test_all_valid_periods(self, fake_client):
        """Every period in VALID_PERIODS is accepted."""
        fake_client.set_ws("recorder/statistics_during_period", {})
        for period in stats.VALID_PERIODS:
            stats.statistics_during_period(
                fake_client,
                statistic_ids=["sensor.x"],
                start_time="2024-01-01T00:00:00+00:00",
                period=period,
            )
            assert fake_client.ws_calls[-1]["payload"]["period"] == period

    def test_none_response_returns_empty_dict(self, fake_client):
        """When ws_call returns None, we get {} not None."""
        fake_client.set_ws("recorder/statistics_during_period", None)
        result = stats.statistics_during_period(
            fake_client,
            statistic_ids=["sensor.x"],
            start_time="2024-01-01T00:00:00+00:00",
        )
        assert result == {}


class TestUpdateMetadata:
    def test_with_unit(self, fake_client):
        fake_client.set_ws("recorder/update_statistics_metadata", {"ok": True})
        stats.update_metadata(fake_client, statistic_id="sensor.x", unit_of_measurement="kWh")
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload == {"statistic_id": "sensor.x", "unit_of_measurement": "kWh"}

    def test_without_unit(self, fake_client):
        fake_client.set_ws("recorder/update_statistics_metadata", {})
        stats.update_metadata(fake_client, statistic_id="sensor.x")
        payload = fake_client.ws_calls[-1]["payload"]
        assert "unit_of_measurement" not in payload
        assert payload["statistic_id"] == "sensor.x"

    def test_empty_id_raises(self):
        with pytest.raises(ValueError, match="statistic_id is required"):
            stats.update_metadata(None, statistic_id="")


class TestClear:
    def test_sends_correct_payload(self, fake_client):
        fake_client.set_ws("recorder/clear_statistics", {"deleted": 2})
        result = stats.clear(fake_client, ["sensor.a", "sensor.b"])
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload == {"statistic_ids": ["sensor.a", "sensor.b"]}
        assert result == {"deleted": 2}


class TestInfo:
    def test_returns_dict(self, fake_client):
        fake_client.set_ws("recorder/info", {"recording": True, "backlog": 0})
        result = stats.info(fake_client)
        assert result["recording"] is True
        assert result["backlog"] == 0

    def test_none_response_returns_empty_dict(self, fake_client):
        fake_client.set_ws("recorder/info", None)
        assert stats.info(fake_client) == {}

    def test_statistics_info_alias(self):
        """statistics_info is an alias for info."""
        assert stats.statistics_info is stats.info
