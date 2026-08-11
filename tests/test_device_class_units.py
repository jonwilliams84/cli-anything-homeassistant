"""Unit tests for `core/device_class_units.py`.

Covers the sensor/number display-unit conversion lookups that gate an
`entity update --options {"sensor": {"unit_of_measurement": ...}}` write.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import device_class_units as dcu


class TestConvertibleUnits:
    def test_sensor_units_sorted(self, fake_client):
        fake_client.set_ws(
            "sensor/device_class_convertible_units", {"units": ["°F", "K", "°C"]}
        )
        assert dcu.sensor_convertible_units(fake_client, "temperature") == ["K", "°C", "°F"]
        assert fake_client.ws_calls[-1] == {
            "type": "sensor/device_class_convertible_units",
            "payload": {"device_class": "temperature"},
        }

    def test_number_units_use_number_command(self, fake_client):
        fake_client.set_ws("number/device_class_convertible_units", {"units": ["°C"]})
        assert dcu.number_convertible_units(fake_client, "temperature") == ["°C"]
        assert fake_client.ws_calls[-1]["type"] == "number/device_class_convertible_units"

    def test_unknown_device_class_is_empty(self, fake_client):
        fake_client.set_ws("sensor/device_class_convertible_units", {"units": []})
        assert dcu.sensor_convertible_units(fake_client, "mystery") == []

    def test_non_dict_result_is_empty(self, fake_client):
        fake_client.set_ws("sensor/device_class_convertible_units", None)
        assert dcu.sensor_convertible_units(fake_client, "temperature") == []

    def test_dispatch_defaults_to_sensor(self, fake_client):
        fake_client.set_ws("sensor/device_class_convertible_units", {"units": ["Pa"]})
        assert dcu.convertible_units(fake_client, "pressure") == ["Pa"]

    def test_dispatch_to_number(self, fake_client):
        fake_client.set_ws("number/device_class_convertible_units", {"units": ["Pa"]})
        assert dcu.convertible_units(fake_client, "pressure", domain="number") == ["Pa"]

    def test_dispatch_rejects_other_domains(self, fake_client):
        with pytest.raises(ValueError, match="domain must be one of"):
            dcu.convertible_units(fake_client, "pressure", domain="light")

    @pytest.mark.parametrize("bad", ["", "   ", None])
    def test_requires_device_class(self, fake_client, bad):
        with pytest.raises(ValueError, match="device_class is required"):
            dcu.sensor_convertible_units(fake_client, bad)


class TestNumericDeviceClasses:
    def test_sorted_list(self, fake_client):
        fake_client.set_ws(
            "sensor/numeric_device_classes",
            {"numeric_device_classes": ["temperature", "battery"]},
        )
        assert dcu.numeric_device_classes(fake_client) == ["battery", "temperature"]

    def test_empty_when_missing(self, fake_client):
        fake_client.set_ws("sensor/numeric_device_classes", {})
        assert dcu.numeric_device_classes(fake_client) == []

    def test_non_dict_result(self, fake_client):
        fake_client.set_ws("sensor/numeric_device_classes", ["nope"])
        assert dcu.numeric_device_classes(fake_client) == []

    def test_is_numeric_true(self, fake_client):
        fake_client.set_ws(
            "sensor/numeric_device_classes", {"numeric_device_classes": ["power"]}
        )
        assert dcu.is_numeric_device_class(fake_client, "power") is True

    def test_is_numeric_false(self, fake_client):
        fake_client.set_ws(
            "sensor/numeric_device_classes", {"numeric_device_classes": ["power"]}
        )
        assert dcu.is_numeric_device_class(fake_client, "enum") is False


class TestCanConvertTo:
    def test_true_for_listed_unit(self, fake_client):
        fake_client.set_ws("sensor/device_class_convertible_units", {"units": ["°C", "°F"]})
        assert dcu.can_convert_to(fake_client, "temperature", "°F") is True

    def test_false_for_unlisted_unit(self, fake_client):
        fake_client.set_ws("sensor/device_class_convertible_units", {"units": ["°C", "°F"]})
        assert dcu.can_convert_to(fake_client, "temperature", "kWh") is False

    def test_number_domain(self, fake_client):
        fake_client.set_ws("number/device_class_convertible_units", {"units": ["°C"]})
        assert dcu.can_convert_to(fake_client, "temperature", "°C", domain="number") is True

    def test_requires_unit(self, fake_client):
        with pytest.raises(ValueError, match="unit is required"):
            dcu.can_convert_to(fake_client, "temperature", "")


# ────────────────────────────────────────────────── entity-level display options

def _arm(fake_client, *, device_class="temperature", units=("°C", "°F"), options=None):
    fake_client.set("GET", "states/sensor.t", {
        "entity_id": "sensor.t",
        "state": "21.0",
        "attributes": {"device_class": device_class} if device_class else {},
    })
    fake_client.set_ws("sensor/device_class_convertible_units", {"units": list(units)})
    fake_client.set_ws(
        "config/entity_registry/get",
        {"entity_entry": {"entity_id": "sensor.t", "options": options or {}}},
    )
    fake_client.set_ws("config/entity_registry/update", {"entity_entry": {"entity_id": "sensor.t"}})
    return fake_client


class TestEntityHelpers:
    def test_entity_device_class(self, fake_client):
        _arm(fake_client)
        assert dcu.entity_device_class(fake_client, "sensor.t") == "temperature"

    def test_entity_device_class_missing(self, fake_client):
        _arm(fake_client, device_class=None)
        assert dcu.entity_device_class(fake_client, "sensor.t") is None

    def test_rejects_unsupported_domain(self, fake_client):
        with pytest.raises(ValueError, match="display options only apply"):
            dcu.entity_device_class(fake_client, "light.kitchen")

    def test_rejects_bad_entity_id(self, fake_client):
        with pytest.raises(ValueError, match="domain.object_id"):
            dcu.entity_device_class(fake_client, "nodot")

    def test_entity_convertible_units(self, fake_client):
        _arm(fake_client)
        out = dcu.entity_convertible_units(fake_client, "sensor.t")
        assert out["device_class"] == "temperature"
        assert out["units"] == ["°C", "°F"]

    def test_entity_convertible_units_without_device_class(self, fake_client):
        _arm(fake_client, device_class=None)
        out = dcu.entity_convertible_units(fake_client, "sensor.t")
        assert out["units"] == []
        assert out["device_class"] is None

    def test_display_options_reads_domain_slice(self, fake_client):
        _arm(fake_client, options={"sensor": {"display_precision": 2}, "other": {"x": 1}})
        assert dcu.display_options(fake_client, "sensor.t") == {"display_precision": 2}

    def test_display_options_empty(self, fake_client):
        _arm(fake_client)
        assert dcu.display_options(fake_client, "sensor.t") == {}

    def test_display_options_bare_entry_shape(self, fake_client):
        _arm(fake_client)
        fake_client.set_ws(
            "config/entity_registry/get",
            {"entity_id": "sensor.t", "options": {"sensor": {"display_precision": 1}}},
        )
        assert dcu.display_options(fake_client, "sensor.t") == {"display_precision": 1}


class TestSetDisplayOptions:
    def test_sends_options_with_domain(self, fake_client):
        _arm(fake_client)
        out = dcu.set_display_options(fake_client, "sensor.t", unit_of_measurement="°F")
        call = fake_client.ws_calls[-1]
        assert call["type"] == "config/entity_registry/update"
        assert call["payload"]["options_domain"] == "sensor"
        assert call["payload"]["options"] == {"unit_of_measurement": "°F"}
        assert out["previous"] == {}

    def test_merges_existing_options(self, fake_client):
        _arm(fake_client, options={"sensor": {"display_precision": 2}})
        out = dcu.set_display_options(fake_client, "sensor.t", unit_of_measurement="°F")
        assert out["options"] == {"display_precision": 2, "unit_of_measurement": "°F"}
        assert out["previous"] == {"display_precision": 2}

    def test_replace_mode_drops_existing(self, fake_client):
        _arm(fake_client, options={"sensor": {"display_precision": 2}})
        out = dcu.set_display_options(
            fake_client, "sensor.t", unit_of_measurement="°F", merge=False
        )
        assert out["options"] == {"unit_of_measurement": "°F"}

    def test_precision_only(self, fake_client):
        _arm(fake_client)
        out = dcu.set_display_options(fake_client, "sensor.t", display_precision=3)
        assert out["options"] == {"display_precision": 3}

    def test_rejects_unconvertible_unit(self, fake_client):
        _arm(fake_client, units=("°C",))
        with pytest.raises(ValueError, match="not a convertible unit"):
            dcu.set_display_options(fake_client, "sensor.t", unit_of_measurement="kWh")

    def test_rejects_unit_without_device_class(self, fake_client):
        _arm(fake_client, device_class=None)
        with pytest.raises(ValueError, match="no device_class"):
            dcu.set_display_options(fake_client, "sensor.t", unit_of_measurement="°F")

    def test_no_validate_skips_the_check(self, fake_client):
        _arm(fake_client, units=("°C",))
        out = dcu.set_display_options(
            fake_client, "sensor.t", unit_of_measurement="kWh", validate_unit=False
        )
        assert out["options"] == {"unit_of_measurement": "kWh"}

    def test_requires_a_field(self, fake_client):
        _arm(fake_client)
        with pytest.raises(ValueError, match="supply unit_of_measurement"):
            dcu.set_display_options(fake_client, "sensor.t")

    def test_rejects_negative_precision(self, fake_client):
        _arm(fake_client)
        with pytest.raises(ValueError, match="display_precision must be"):
            dcu.set_display_options(fake_client, "sensor.t", display_precision=-1)
