"""Unit tests for cli_anything.homeassistant.core.energy_advanced.

All tests run without a real Home Assistant instance; the FakeClient
fixture from conftest.py provides WS call recording and canned responses.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import energy_advanced


class TestEnergyAdvanced:

    # ────────────────────────────────────────────────────────────────────
    # validate_energy_prefs
    # ────────────────────────────────────────────────────────────────────

    def test_validate_energy_prefs_happy_path(self, fake_client):
        """validate_energy_prefs sends energy/validate with no payload."""
        canned = {
            "sensor.solar_production": [
                {"type": "entity_not_defined", "data": {}}
            ]
        }
        fake_client.set_ws("energy/validate", canned)
        result = energy_advanced.validate_energy_prefs(fake_client)
        assert fake_client.ws_calls[-1]["type"] == "energy/validate"
        assert fake_client.ws_calls[-1]["payload"] is None
        assert "sensor.solar_production" in result

    def test_validate_energy_prefs_returns_dict(self, fake_client):
        """Return value is always a dict."""
        fake_client.set_ws("energy/validate", {"ok": True})
        result = energy_advanced.validate_energy_prefs(fake_client)
        assert isinstance(result, dict)

    def test_validate_energy_prefs_non_dict_response_gives_empty_dict(self, fake_client):
        """Non-dict server response is normalised to {}."""
        fake_client.set_ws("energy/validate", None)
        result = energy_advanced.validate_energy_prefs(fake_client)
        assert result == {}

    # ────────────────────────────────────────────────────────────────────
    # solar_forecast
    # ────────────────────────────────────────────────────────────────────

    def test_solar_forecast_happy_path(self, fake_client):
        """solar_forecast sends energy/solar_forecast with no payload."""
        canned = {
            "abc123": {
                "wh_hours": {"2024-06-15T12:00:00+00:00": 1200}
            }
        }
        fake_client.set_ws("energy/solar_forecast", canned)
        result = energy_advanced.solar_forecast(fake_client)
        assert fake_client.ws_calls[-1]["type"] == "energy/solar_forecast"
        assert fake_client.ws_calls[-1]["payload"] is None
        assert "abc123" in result
        assert result["abc123"]["wh_hours"]["2024-06-15T12:00:00+00:00"] == 1200

    def test_solar_forecast_returns_dict(self, fake_client):
        """Return value is always a dict."""
        fake_client.set_ws("energy/solar_forecast", {})
        result = energy_advanced.solar_forecast(fake_client)
        assert isinstance(result, dict)

    def test_solar_forecast_non_dict_response_gives_empty_dict(self, fake_client):
        """Non-dict server response is normalised to {}."""
        fake_client.set_ws("energy/solar_forecast", None)
        result = energy_advanced.solar_forecast(fake_client)
        assert result == {}

    # ────────────────────────────────────────────────────────────────────
    # fossil_energy_consumption
    # ────────────────────────────────────────────────────────────────────

    def test_fossil_energy_consumption_happy_path(self, fake_client):
        """fossil_energy_consumption sends the exact expected WS payload."""
        canned = {"2024-06-01T00:00:00+00:00": 3.5, "2024-06-01T01:00:00+00:00": 2.1}
        fake_client.set_ws("energy/fossil_energy_consumption", canned)
        result = energy_advanced.fossil_energy_consumption(
            fake_client,
            start_time="2024-06-01T00:00:00+00:00",
            end_time="2024-06-01T02:00:00+00:00",
            energy_statistic_ids=["sensor:grid_import_energy"],
            co2_statistic_id="co2signal:co2_intensity_de",
            period="hour",
        )
        assert fake_client.ws_calls[-1]["type"] == "energy/fossil_energy_consumption"
        assert fake_client.ws_calls[-1]["payload"] == {
            "start_time": "2024-06-01T00:00:00+00:00",
            "end_time": "2024-06-01T02:00:00+00:00",
            "energy_statistic_ids": ["sensor:grid_import_energy"],
            "co2_statistic_id": "co2signal:co2_intensity_de",
            "period": "hour",
        }

    def test_fossil_energy_consumption_returns_dict(self, fake_client):
        """Return value is the canned dict from the server."""
        canned = {"2024-06-01T00:00:00+00:00": 5.0}
        fake_client.set_ws("energy/fossil_energy_consumption", canned)
        result = energy_advanced.fossil_energy_consumption(
            fake_client,
            start_time="2024-06-01T00:00:00+00:00",
            end_time="2024-06-01T01:00:00+00:00",
            energy_statistic_ids=["sensor:grid_import"],
            co2_statistic_id="co2signal:co2_intensity_gb",
        )
        assert result == canned

    def test_fossil_energy_consumption_default_period_is_hour(self, fake_client):
        """period defaults to 'hour' when not specified."""
        energy_advanced.fossil_energy_consumption(
            fake_client,
            start_time="2024-06-01T00:00:00+00:00",
            end_time="2024-06-01T01:00:00+00:00",
            energy_statistic_ids=["sensor:grid"],
            co2_statistic_id="co2signal:co2_intensity",
        )
        assert fake_client.ws_calls[-1]["payload"]["period"] == "hour"

    def test_fossil_energy_consumption_all_valid_periods(self, fake_client):
        """All accepted period values are forwarded without error."""
        for p in ("5minute", "hour", "day", "week", "month"):
            energy_advanced.fossil_energy_consumption(
                fake_client,
                start_time="2024-06-01T00:00:00+00:00",
                end_time="2024-06-02T00:00:00+00:00",
                energy_statistic_ids=["sensor:grid"],
                co2_statistic_id="co2signal:co2_intensity",
                period=p,
            )
            assert fake_client.ws_calls[-1]["payload"]["period"] == p

    def test_fossil_energy_consumption_empty_start_time_raises(self, fake_client):
        with pytest.raises(ValueError, match="start_time"):
            energy_advanced.fossil_energy_consumption(
                fake_client,
                start_time="",
                end_time="2024-06-01T01:00:00+00:00",
                energy_statistic_ids=["sensor:grid"],
                co2_statistic_id="co2signal:co2_intensity",
            )

    def test_fossil_energy_consumption_empty_end_time_raises(self, fake_client):
        with pytest.raises(ValueError, match="end_time"):
            energy_advanced.fossil_energy_consumption(
                fake_client,
                start_time="2024-06-01T00:00:00+00:00",
                end_time="",
                energy_statistic_ids=["sensor:grid"],
                co2_statistic_id="co2signal:co2_intensity",
            )

    def test_fossil_energy_consumption_empty_statistic_ids_raises(self, fake_client):
        with pytest.raises(ValueError, match="energy_statistic_ids"):
            energy_advanced.fossil_energy_consumption(
                fake_client,
                start_time="2024-06-01T00:00:00+00:00",
                end_time="2024-06-01T01:00:00+00:00",
                energy_statistic_ids=[],
                co2_statistic_id="co2signal:co2_intensity",
            )

    def test_fossil_energy_consumption_empty_co2_statistic_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="co2_statistic_id"):
            energy_advanced.fossil_energy_consumption(
                fake_client,
                start_time="2024-06-01T00:00:00+00:00",
                end_time="2024-06-01T01:00:00+00:00",
                energy_statistic_ids=["sensor:grid"],
                co2_statistic_id="",
            )

    def test_fossil_energy_consumption_invalid_period_raises(self, fake_client):
        with pytest.raises(ValueError, match="period"):
            energy_advanced.fossil_energy_consumption(
                fake_client,
                start_time="2024-06-01T00:00:00+00:00",
                end_time="2024-06-01T01:00:00+00:00",
                energy_statistic_ids=["sensor:grid"],
                co2_statistic_id="co2signal:co2_intensity",
                period="quarterly",
            )

    def test_fossil_energy_consumption_non_dict_response_gives_empty_dict(self, fake_client):
        """Non-dict server response is normalised to {}."""
        fake_client.set_ws("energy/fossil_energy_consumption", None)
        result = energy_advanced.fossil_energy_consumption(
            fake_client,
            start_time="2024-06-01T00:00:00+00:00",
            end_time="2024-06-01T01:00:00+00:00",
            energy_statistic_ids=["sensor:grid"],
            co2_statistic_id="co2signal:co2_intensity",
        )
        assert result == {}

    # ────────────────────────────────────────────────────────────────────
    # save_prefs
    # ────────────────────────────────────────────────────────────────────

    def test_save_prefs_happy_path_energy_sources_only(self, fake_client):
        """save_prefs sends energy/save_prefs with exact payload (no optionals)."""
        sources = [
            {"type": "solar", "stat_energy_from": "sensor.solar_energy"}
        ]
        canned = {"energy_sources": sources, "device_consumption": []}
        fake_client.set_ws("energy/save_prefs", canned)
        result = energy_advanced.save_prefs(fake_client, energy_sources=sources)
        assert fake_client.ws_calls[-1]["type"] == "energy/save_prefs"
        assert fake_client.ws_calls[-1]["payload"] == {
            "energy_sources": sources,
        }
        assert result == canned

    def test_save_prefs_with_all_optional_fields(self, fake_client):
        """save_prefs includes optional fields when provided."""
        sources = [{"type": "grid", "flow_from": [], "flow_to": []}]
        devices = [{"stat_consumption": "sensor.washing_machine"}]
        manual_ids = ["myintegration:imported_energy"]
        fake_client.set_ws("energy/save_prefs", {"energy_sources": sources})
        energy_advanced.save_prefs(
            fake_client,
            energy_sources=sources,
            device_consumption=devices,
            manual_configured_statistic_ids=manual_ids,
        )
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["energy_sources"] == sources
        assert payload["device_consumption"] == devices
        assert payload["manual_configured_statistic_ids"] == manual_ids

    def test_save_prefs_device_consumption_none_omitted(self, fake_client):
        """device_consumption=None means the key is absent from the payload."""
        sources = [{"type": "solar", "stat_energy_from": "sensor.solar"}]
        energy_advanced.save_prefs(
            fake_client,
            energy_sources=sources,
            device_consumption=None,
        )
        assert "device_consumption" not in fake_client.ws_calls[-1]["payload"]

    def test_save_prefs_manual_ids_none_omitted(self, fake_client):
        """manual_configured_statistic_ids=None means the key is absent."""
        sources = [{"type": "solar", "stat_energy_from": "sensor.solar"}]
        energy_advanced.save_prefs(
            fake_client,
            energy_sources=sources,
            manual_configured_statistic_ids=None,
        )
        assert "manual_configured_statistic_ids" not in fake_client.ws_calls[-1]["payload"]

    def test_save_prefs_returns_dict(self, fake_client):
        """Return value is the server response dict."""
        sources = [{"type": "solar", "stat_energy_from": "sensor.solar"}]
        canned = {"energy_sources": sources, "device_consumption": []}
        fake_client.set_ws("energy/save_prefs", canned)
        result = energy_advanced.save_prefs(fake_client, energy_sources=sources)
        assert isinstance(result, dict)
        assert result == canned

    def test_save_prefs_empty_energy_sources_raises(self, fake_client):
        with pytest.raises(ValueError, match="energy_sources"):
            energy_advanced.save_prefs(fake_client, energy_sources=[])

    def test_save_prefs_non_list_energy_sources_raises(self, fake_client):
        with pytest.raises(ValueError, match="energy_sources"):
            energy_advanced.save_prefs(
                fake_client,
                energy_sources={"type": "solar"},  # type: ignore[arg-type]
            )

    def test_save_prefs_non_dict_response_gives_empty_dict(self, fake_client):
        """Non-dict server response is normalised to {}."""
        fake_client.set_ws("energy/save_prefs", None)
        result = energy_advanced.save_prefs(
            fake_client,
            energy_sources=[{"type": "solar", "stat_energy_from": "sensor.solar"}],
        )
        assert result == {}
