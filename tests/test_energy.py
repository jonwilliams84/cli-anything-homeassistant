"""Unit tests for cli_anything.homeassistant.core.energy — no real HA required."""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import energy


class TestGetPrefs:
    def test_returns_dict(self, fake_client):
        fake_client.set_ws("energy/get_prefs", {"energy_flow": "grid"})
        assert energy.get_prefs(fake_client) == {"energy_flow": "grid"}

    def test_none_response_returns_empty_dict(self, fake_client):
        fake_client.set_ws("energy/get_prefs", None)
        assert energy.get_prefs(fake_client) == {}


class TestSavePrefs:
    def test_sends_prefs(self, fake_client):
        fake_client.set_ws("energy/save_prefs", {"ok": True})
        result = energy.save_prefs(fake_client, {"energy_flow": "grid"})
        assert result == {"ok": True}
        assert fake_client.ws_calls[-1]["type"] == "energy/save_prefs"
        assert fake_client.ws_calls[-1]["payload"] == {"energy_flow": "grid"}

    def test_non_dict_prefs_raises(self, fake_client):
        with pytest.raises(ValueError, match="prefs must be a dict"):
            energy.save_prefs(fake_client, "not a dict")

    def test_none_response_returns_empty_dict(self, fake_client):
        fake_client.set_ws("energy/save_prefs", None)
        assert energy.save_prefs(fake_client, {}) == {}


class TestInfo:
    def test_returns_dict(self, fake_client):
        fake_client.set_ws("energy/info", {"cost_sensors_enabled": True})
        assert energy.info(fake_client) == {"cost_sensors_enabled": True}

    def test_none_response_returns_empty_dict(self, fake_client):
        fake_client.set_ws("energy/info", None)
        assert energy.info(fake_client) == {}

    def test_energy_info_alias_works(self, fake_client):
        """energy_info is an alias for info."""
        fake_client.set_ws("energy/info", {"ok": True})
        assert energy.energy_info(fake_client) == {"ok": True}


class TestFossilEnergyConsumption:
    def test_happy_path_with_end_time(self, fake_client):
        fake_client.set_ws("energy/fossil_energy_consumption", {"kwh": 5.0})
        result = energy.fossil_energy_consumption(
            fake_client,
            energy_statistic_ids=["sensor.grid"],
            co2_signal_entity="sensor.co2",
            start_time="2024-01-01T00:00:00+00:00",
            end_time="2024-01-02T00:00:00+00:00",
        )
        assert result == {"kwh": 5.0}
        assert fake_client.ws_calls[-1]["payload"] == {
            "energy_statistic_ids": ["sensor.grid"],
            "co2_signal_entity": "sensor.co2",
            "start_time": "2024-01-01T00:00:00+00:00",
            "end_time": "2024-01-02T00:00:00+00:00",
            "period": "hour",
        }

    def test_without_end_time_omits_it(self, fake_client):
        fake_client.set_ws("energy/fossil_energy_consumption", {})
        energy.fossil_energy_consumption(
            fake_client,
            energy_statistic_ids=["sensor.grid"],
            co2_signal_entity="sensor.co2",
            start_time="2024-01-01T00:00:00+00:00",
        )
        assert "end_time" not in fake_client.ws_calls[-1]["payload"]

    def test_empty_statistic_ids_raises(self, fake_client):
        with pytest.raises(ValueError, match="energy_statistic_ids must not be empty"):
            energy.fossil_energy_consumption(
                fake_client,
                energy_statistic_ids=[],
                co2_signal_entity="sensor.co2",
                start_time="2024-01-01T00:00:00+00:00",
            )

    def test_invalid_period_raises(self, fake_client):
        with pytest.raises(ValueError, match="invalid period"):
            energy.fossil_energy_consumption(
                fake_client,
                energy_statistic_ids=["sensor.grid"],
                co2_signal_entity="sensor.co2",
                start_time="2024-01-01T00:00:00+00:00",
                period="year",
            )

    def test_all_valid_periods(self, fake_client):
        fake_client.set_ws("energy/fossil_energy_consumption", {})
        for p in ("5minute", "hour", "day", "week", "month"):
            energy.fossil_energy_consumption(
                fake_client,
                energy_statistic_ids=["sensor.grid"],
                co2_signal_entity="sensor.co2",
                start_time="2024-01-01T00:00:00+00:00",
                period=p,
            )
            assert fake_client.ws_calls[-1]["payload"]["period"] == p

    def test_none_response_returns_empty_dict(self, fake_client):
        fake_client.set_ws("energy/fossil_energy_consumption", None)
        assert energy.fossil_energy_consumption(
            fake_client,
            energy_statistic_ids=["sensor.grid"],
            co2_signal_entity="sensor.co2",
            start_time="2024-01-01T00:00:00+00:00",
        ) == {}

    def test_statistic_ids_copied_as_list(self, fake_client):
        """energy_statistic_ids is converted to a list copy so the caller's list isn't mutated."""
        fake_client.set_ws("energy/fossil_energy_consumption", {})
        original = ["sensor.a", "sensor.b"]
        energy.fossil_energy_consumption(
            fake_client,
            energy_statistic_ids=original,
            co2_signal_entity="sensor.co2",
            start_time="2024-01-01T00:00:00+00:00",
        )
        sent = fake_client.ws_calls[-1]["payload"]["energy_statistic_ids"]
        assert sent == ["sensor.a", "sensor.b"]
        assert sent is not original
