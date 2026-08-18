"""Unit tests for `core_config` — the instance's own location, units and URLs.

All tests run against FakeClient — no live Home Assistant required. The shapes
come from `homeassistant/components/config/core.py`:

  config/core/update              — core_config.update / safe_set
  config/core/detect              — core_config.detect / drift
  POST config/core/check_config   — core_config.check_config

The behaviours pinned here are HA's, not this harness's: the update is a
PARTIAL merge, `unit_system` takes exactly two values, `update_units` is a
separate flag from the unit system, and a failed geo-IP lookup is `{}` rather
than an error.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import core_config


LIVE = {
    "latitude": 51.5,
    "longitude": -0.12,
    "elevation": 11,
    "location_name": "Home",
    "time_zone": "Europe/London",
    "unit_system": {"length": "km"},
    "currency": "GBP",
    "country": "GB",
    "language": "en-GB",
    "radius": 100,
    "external_url": None,
    "internal_url": "http://ha.local:8123",
    # keys `show()` must drop:
    "components": ["sun", "mqtt"],
    "version": "2026.8.1",
    "config_dir": "/config",
}


@pytest.fixture
def configured(fake_client):
    fake_client.set("GET", "config", dict(LIVE))
    return fake_client


class TestShow:
    def test_only_the_settable_keys_survive(self, configured):
        got = core_config.show(configured)
        assert set(got) == set(core_config.UPDATABLE)
        assert "components" not in got and "version" not in got

    def test_a_key_the_instance_does_not_report_is_none_not_missing(self, fake_client):
        """A before/after diff needs every key present, even the unset ones."""
        fake_client.set("GET", "config", {"latitude": 1.0})
        got = core_config.show(fake_client)
        assert got["currency"] is None
        assert set(got) == set(core_config.UPDATABLE)

    def test_a_non_object_response_is_named(self, fake_client):
        fake_client.set("GET", "config", ["nope"])
        with pytest.raises(ValueError, match="expected an object"):
            core_config.show(fake_client)


class TestBuildUpdate:
    def test_only_the_given_keys_are_sent(self):
        """HA keeps every key that is not in the message — a merge, not a replace."""
        assert core_config.build_update(latitude=1.5, longitude=None) == {"latitude": 1.5}

    def test_an_empty_update_names_every_option(self):
        with pytest.raises(ValueError) as exc:
            core_config.build_update()
        for key in core_config.UPDATABLE:
            assert f"--{key.replace('_', '-')}" in str(exc.value)

    def test_an_unknown_field_is_rejected_before_the_call(self):
        with pytest.raises(ValueError, match="Not a core-config field: tempreture"):
            core_config.build_update(tempreture=20)

    def test_imperial_is_rewritten_the_way_ha_rewrites_it(self):
        assert core_config.build_update(unit_system="Imperial")["unit_system"] == "us_customary"

    def test_a_bad_unit_system_names_the_two_legal_values(self):
        with pytest.raises(ValueError) as exc:
            core_config.build_update(unit_system="metrics")
        assert "metric" in str(exc.value) and "us_customary" in str(exc.value)

    @pytest.mark.parametrize(
        "field,value",
        [("latitude", 91.0), ("latitude", -90.5), ("longitude", 181.0), ("longitude", -200.0)],
    )
    def test_coordinates_out_of_range_are_refused_locally(self, field, value):
        with pytest.raises(ValueError, match="must be between"):
            core_config.build_update(**{field: value})

    def test_coordinates_at_the_boundary_are_allowed(self):
        assert core_config.build_update(latitude=90.0, longitude=-180.0) == {
            "latitude": 90.0,
            "longitude": -180.0,
        }

    def test_a_non_numeric_coordinate_says_so(self):
        with pytest.raises(ValueError, match="latitude must be a number"):
            core_config.build_update(latitude="north")

    def test_a_non_numeric_elevation_says_what_the_unit_is(self):
        with pytest.raises(ValueError, match="whole number of metres"):
            core_config.build_update(elevation="high")

    def test_a_non_numeric_radius_says_so(self):
        with pytest.raises(ValueError, match="radius must be a positive integer"):
            core_config.build_update(radius="wide")

    def test_elevation_and_radius_are_coerced_to_int(self):
        got = core_config.build_update(elevation="11", radius="250")
        assert got == {"elevation": 11, "radius": 250}

    def test_a_negative_radius_is_refused(self):
        with pytest.raises(ValueError, match="positive integer"):
            core_config.build_update(radius=-1)

    def test_the_two_url_keys_can_be_cleared_with_an_empty_string(self):
        assert core_config.build_update(external_url="") == {"external_url": None}

    def test_nothing_else_can_be_cleared_because_ha_has_no_null_for_it(self):
        with pytest.raises(ValueError, match="cannot be cleared"):
            core_config.build_update(currency="")


class TestUpdate:
    def test_a_dry_run_sends_nothing(self, configured):
        got = core_config.update(configured, latitude=52.0)
        assert got["applied"] is False
        assert got["sent"] == {"latitude": 52.0}
        assert configured.ws_calls == []
        assert "DRY RUN" in got["note"]

    def test_a_dry_run_still_reports_the_diff(self, configured):
        got = core_config.update(configured, time_zone="Europe/Paris")
        assert got["changes"] == [
            {"key": "time_zone", "from": "Europe/London", "to": "Europe/Paris"}
        ]
        assert got["no_op"] is False

    def test_setting_a_value_to_what_it_already_is_is_flagged_as_a_no_op(self, configured):
        got = core_config.update(configured, currency="GBP")
        assert got["changes"] == []
        assert got["no_op"] is True

    def test_apply_sends_exactly_the_validated_payload(self, configured):
        core_config.update(configured, apply=True, elevation=25)
        assert configured.ws_calls == [
            {"type": "config/core/update", "payload": {"elevation": 25}}
        ]

    def test_update_units_is_a_separate_flag_and_is_off_by_default(self, configured):
        core_config.update(configured, apply=True, unit_system="metric")
        assert "update_units" not in configured.ws_calls[0]["payload"]

    def test_update_units_rides_along_when_asked(self, configured):
        core_config.update(configured, apply=True, unit_system="metric", update_units=True)
        assert configured.ws_calls[0]["payload"] == {
            "unit_system": "metric",
            "update_units": True,
        }

    def test_a_silently_ignored_key_shows_up_as_took_false(self, configured):
        """The reason an apply re-reads: HA can accept a message and not change."""
        got = core_config.update(configured, apply=True, country="FR")
        assert got["effective"] == [
            {"key": "country", "requested": "FR", "actual": "GB", "took": False}
        ]

    def test_the_yaml_caveat_is_stated_on_a_real_write(self, configured):
        got = core_config.update(configured, apply=True, latitude=52.0)
        assert "configuration.yaml" in got["note"]

    def test_validation_runs_before_anything_is_read_or_sent(self, configured):
        with pytest.raises(ValueError):
            core_config.update(configured, apply=True, latitude=200.0)
        assert configured.ws_calls == []
        assert configured.calls == []


class TestDetect:
    def test_a_detection_is_reported_with_its_source(self, fake_client):
        fake_client.set_ws(
            "config/core/detect",
            {"latitude": 51.5, "longitude": -0.12, "country": "GB", "unit_system": "metric"},
        )
        got = core_config.detect(fake_client)
        assert got["detected"] is True
        assert got["info"]["country"] == "GB"

    def test_a_non_object_detection_is_treated_as_no_detection(self, fake_client):
        """The WS layer returns [] for an absent result; that is not a location."""
        fake_client.set_ws("config/core/detect", ["Europe/London"])
        got = core_config.detect(fake_client)
        assert got == {"detected": False, "info": {}, "note": got["note"]}

    def test_an_empty_result_is_a_failed_lookup_not_an_error(self, fake_client):
        fake_client.set_ws("config/core/detect", {})
        got = core_config.detect(fake_client)
        assert got["detected"] is False
        assert "lookup failed" in got["note"]


class TestDrift:
    def test_a_mismatch_is_named(self, configured):
        configured.set_ws("config/core/detect", {"country": "FR", "currency": "EUR"})
        got = core_config.drift(configured)
        assert got["drifted"] is True
        assert {"key": "country", "configured": "GB", "detected": "FR"} in got["mismatches"]

    def test_coordinates_get_a_tolerance_because_geo_ip_is_city_accurate(self, configured):
        configured.set_ws("config/core/detect", {"latitude": 51.6, "longitude": -0.2})
        got = core_config.drift(configured)
        assert got["mismatches"] == []

    def test_a_coordinate_on_the_wrong_continent_is_still_caught(self, configured):
        configured.set_ws("config/core/detect", {"latitude": 40.7, "longitude": -74.0})
        keys = {m["key"] for m in core_config.drift(configured)["mismatches"]}
        assert keys == {"latitude", "longitude"}

    def test_an_uncomparable_coordinate_falls_back_to_equality(self, configured):
        """A configured latitude of None cannot be subtracted — it is still drift."""
        configured.set("GET", "config", {**LIVE, "latitude": None})
        configured.set_ws("config/core/detect", {"latitude": 51.5})
        got = core_config.drift(configured)
        assert got["mismatches"] == [
            {"key": "latitude", "configured": None, "detected": 51.5}
        ]

    def test_a_key_that_already_agrees_is_not_reported(self, configured):
        configured.set_ws("config/core/detect", {"country": "GB", "currency": "GBP"})
        got = core_config.drift(configured)
        assert got["mismatches"] == [] and got["drifted"] is False

    def test_a_key_ha_detects_but_cannot_set_is_ignored(self, configured):
        configured.set_ws("config/core/detect", {"nonsense": 1})
        assert core_config.drift(configured)["mismatches"] == []

    def test_a_failed_lookup_says_the_verdict_means_nothing(self, configured):
        configured.set_ws("config/core/detect", {})
        got = core_config.drift(configured)
        assert got["detected_ok"] is False
        assert "says nothing" in got["note"]


class TestCheckConfig:
    def test_a_valid_config(self, fake_client):
        fake_client.set(
            "POST", "config/core/check_config",
            {"result": "valid", "errors": None, "warnings": None},
        )
        got = core_config.check_config(fake_client)
        assert got["valid"] is True
        assert got["has_warnings"] is False

    def test_the_error_text_comes_back_which_the_notification_route_never_had(self, fake_client):
        fake_client.set(
            "POST", "config/core/check_config",
            {"result": "invalid", "errors": "Integration 'nope' not found.", "warnings": None},
        )
        got = core_config.check_config(fake_client)
        assert got["valid"] is False
        assert "not found" in got["errors"]

    def test_warnings_are_reported_even_on_a_valid_config(self, fake_client):
        """The service+notification route cannot see these at all."""
        fake_client.set(
            "POST", "config/core/check_config",
            {"result": "valid", "errors": None, "warnings": "Platform x is deprecated"},
        )
        got = core_config.check_config(fake_client)
        assert got["valid"] is True and got["has_warnings"] is True

    def test_a_non_object_response_is_named(self, fake_client):
        fake_client.set("POST", "config/core/check_config", ["nope"])
        with pytest.raises(ValueError, match="expected an object"):
            core_config.check_config(fake_client)


class TestSafeSet:
    def test_a_broken_yaml_blocks_the_write(self, configured):
        configured.set(
            "POST", "config/core/check_config",
            {"result": "invalid", "errors": "bad", "warnings": None},
        )
        got = core_config.safe_set(configured, apply=True, latitude=52.0)
        assert got["applied"] is False
        assert got["blocked_by"] == "check_config"
        assert configured.ws_calls == []

    def test_a_clean_check_lets_the_write_through_and_is_kept(self, configured):
        configured.set(
            "POST", "config/core/check_config",
            {"result": "valid", "errors": None, "warnings": None},
        )
        got = core_config.safe_set(configured, apply=True, latitude=52.0)
        assert got["applied"] is True
        assert got["check"]["valid"] is True
        assert configured.ws_calls[0]["type"] == "config/core/update"

    def test_a_clean_check_still_honours_the_dry_run(self, configured):
        configured.set(
            "POST", "config/core/check_config",
            {"result": "valid", "errors": None, "warnings": None},
        )
        got = core_config.safe_set(configured, latitude=52.0)
        assert got["applied"] is False
        assert configured.ws_calls == []
