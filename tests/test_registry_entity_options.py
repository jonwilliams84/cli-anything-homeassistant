"""Regression tests for `registry.update_entity` entity-options handling.

HA declares `options` / `options_domain` as an inclusive pair
(`vol.Inclusive(...)` in `config/entity_registry/update`): sending `options`
alone is rejected by the schema, so the old signature could never write an
entity option successfully.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import registry as reg


class TestUpdateEntityOptions:
    def test_options_and_domain_are_sent_together(self, fake_client):
        fake_client.set_ws("config/entity_registry/update", {"entity_entry": {}})
        reg.update_entity(
            fake_client,
            "sensor.t",
            options={"unit_of_measurement": "°F"},
            options_domain="sensor",
        )
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["options_domain"] == "sensor"
        assert payload["options"] == {"unit_of_measurement": "°F"}

    def test_options_without_domain_is_rejected_locally(self, fake_client):
        with pytest.raises(ValueError, match="options_domain is required"):
            reg.update_entity(fake_client, "sensor.t", options={"a": 1})
        assert fake_client.ws_calls == []

    def test_domain_without_options_is_rejected(self, fake_client):
        with pytest.raises(ValueError, match="options_domain requires options"):
            reg.update_entity(fake_client, "sensor.t", options_domain="sensor")

    def test_other_fields_still_work_without_options(self, fake_client):
        fake_client.set_ws("config/entity_registry/update", {"entity_entry": {}})
        reg.update_entity(fake_client, "sensor.t", name="Temp")
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload == {"entity_id": "sensor.t", "name": "Temp"}
        assert "options" not in payload
