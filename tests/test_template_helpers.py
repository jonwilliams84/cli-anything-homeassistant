"""Unit tests for cli_anything.homeassistant.core.template_helpers.

Covers create/update/show config-flow logic, validation, schema parsing,
and entity-registry resolution — all the uncovered branches.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import template_helpers


FLOW_ID = "flow-abc123"
ENTRY_ID = "01JENTRYID"


# ── create ───────────────────────────────────────────────────────────────────


class TestCreate:
    def test_full_sensor_creation_flow(self, fake_client):
        """create() initiates flow, picks type, submits config with all fields."""
        fake_client.set("POST", "config/config_entries/flow", {"flow_id": FLOW_ID})
        fake_client.set("POST", f"config/config_entries/flow/{FLOW_ID}",
                        {"type": "create_entry", "title": "My Sensor"})

        result = template_helpers.create(
            fake_client,
            name="My Sensor",
            state_template="{{ states('sensor.x') }}",
            template_type="sensor",
            unit_of_measurement="%",
            device_class="power_factor",
            state_class="measurement",
        )

        assert result["type"] == "create_entry"
        # Three POST calls: init, type-select, submit
        posts = [c for c in fake_client.calls if c["verb"] == "POST"]
        assert len(posts) == 3
        # Step 1: init with handler
        assert posts[0]["payload"] == {"handler": "template", "show_advanced_options": False}
        # Step 2: type selection
        assert posts[1]["payload"] == {"next_step_id": "sensor"}
        # Step 3: final config
        submit = posts[2]["payload"]
        assert submit["name"] == "My Sensor"
        assert submit["state"] == "{{ states('sensor.x') }}"
        assert submit["unit_of_measurement"] == "%"
        assert submit["device_class"] == "power_factor"
        assert submit["state_class"] == "measurement"

    def test_state_template_is_stripped(self, fake_client):
        """Whitespace around the template is stripped before submission."""
        fake_client.set("POST", "config/config_entries/flow", {"flow_id": FLOW_ID})
        fake_client.set("POST", f"config/config_entries/flow/{FLOW_ID}", {})

        template_helpers.create(
            fake_client,
            name="S",
            state_template="  {{ value }}  ",
        )
        posts = [c for c in fake_client.calls if c["verb"] == "POST"]
        assert posts[-1]["payload"]["state"] == "{{ value }}"

    def test_extra_fields_merged(self, fake_client):
        """Extra dict fields are merged into the submit payload."""
        fake_client.set("POST", "config/config_entries/flow", {"flow_id": FLOW_ID})
        fake_client.set("POST", f"config/config_entries/flow/{FLOW_ID}", {})

        template_helpers.create(
            fake_client,
            name="Binary",
            state_template="{{ 1 }}",
            template_type="binary_sensor",
            extra={"delay_on": "00:00:30", "delay_off": "00:00:10"},
        )
        submit = [c for c in fake_client.calls if c["verb"] == "POST"][-1]["payload"]
        assert submit["delay_on"] == "00:00:30"
        assert submit["delay_off"] == "00:00:10"

    def test_invalid_template_type_raises(self, fake_client):
        with pytest.raises(ValueError, match="template_type must be one of"):
            template_helpers.create(
                fake_client, name="X", state_template="{{ 1 }}",
                template_type="invalid_type",
            )

    def test_empty_name_raises(self, fake_client):
        with pytest.raises(ValueError, match="name is required"):
            template_helpers.create(fake_client, name="", state_template="{{ 1 }}")

    def test_empty_state_template_raises(self, fake_client):
        with pytest.raises(ValueError, match="state_template is required"):
            template_helpers.create(fake_client, name="X", state_template="")

    def test_flow_init_failure_raises_runtime_error(self, fake_client):
        """If the init response has no flow_id, RuntimeError is raised."""
        fake_client.set("POST", "config/config_entries/flow", {"type": "abort"})
        with pytest.raises(RuntimeError, match="template flow init failed"):
            template_helpers.create(
                fake_client, name="X", state_template="{{ 1 }}",
            )


# ── update ───────────────────────────────────────────────────────────────────


class TestUpdate:
    def test_update_preserves_current_options(self, fake_client):
        """Fields not overridden are preserved from the schema's suggested_values."""
        fake_client.set("POST", "config/config_entries/options/flow", {
            "flow_id": FLOW_ID,
            "data_schema": [
                {"name": "name", "description": {"suggested_value": "Old Name"}},
                {"name": "state", "description": {"suggested_value": "{{ old }}"}},
                {"name": "unit_of_measurement", "description": {"suggested_value": "W"}},
            ],
        })
        fake_client.set("POST", f"config/config_entries/flow/{FLOW_ID}", {})

        template_helpers.update(
            fake_client, ENTRY_ID,
            state_template="{{ new }}",
        )
        submit = [c for c in fake_client.calls if c["verb"] == "POST"][-1]["payload"]
        # name preserved from schema
        assert submit["name"] == "Old Name"
        # state overridden
        assert submit["state"] == "{{ new }}"
        # unit preserved from schema
        assert submit["unit_of_measurement"] == "W"

    def test_update_overrides_all_fields(self, fake_client):
        fake_client.set("POST", "config/config_entries/options/flow", {
            "flow_id": FLOW_ID,
            "data_schema": [
                {"name": "name", "description": {"suggested_value": "Old"}},
                {"name": "state", "description": {"suggested_value": "{{ old }}"}},
            ],
        })
        fake_client.set("POST", f"config/config_entries/flow/{FLOW_ID}", {})

        template_helpers.update(
            fake_client, ENTRY_ID,
            name="New Name",
            state_template="{{ new }}",
            unit_of_measurement="kW",
            device_class="power",
            state_class="measurement",
            extra={"min": 0},
        )
        submit = [c for c in fake_client.calls if c["verb"] == "POST"][-1]["payload"]
        assert submit["name"] == "New Name"
        assert submit["state"] == "{{ new }}"
        assert submit["unit_of_measurement"] == "kW"
        assert submit["device_class"] == "power"
        assert submit["state_class"] == "measurement"
        assert submit["min"] == 0

    def test_update_empty_entry_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="entry_id is required"):
            template_helpers.update(fake_client, "")

    def test_update_flow_init_failure_raises(self, fake_client):
        fake_client.set("POST", "config/config_entries/options/flow", {"type": "abort"})
        with pytest.raises(RuntimeError, match="options flow init failed"):
            template_helpers.update(fake_client, ENTRY_ID)

    def test_update_with_empty_schema(self, fake_client):
        """When schema is empty, only caller-provided fields are submitted."""
        fake_client.set("POST", "config/config_entries/options/flow", {
            "flow_id": FLOW_ID,
            "data_schema": [],
        })
        fake_client.set("POST", f"config/config_entries/flow/{FLOW_ID}", {})

        template_helpers.update(fake_client, ENTRY_ID, name="Only Name")
        submit = [c for c in fake_client.calls if c["verb"] == "POST"][-1]["payload"]
        assert submit == {"name": "Only Name"}


# ── show ──────────────────────────────────────────────────────────────────────


class TestShow:
    def test_show_by_entry_id(self, fake_client):
        """When ident has no dot, it's treated as a config entry id directly."""
        fake_client.set("POST", "config/config_entries/options/flow", {
            "flow_id": FLOW_ID,
            "data_schema": [
                {"name": "name", "description": {"suggested_value": "My Helper"}},
                {"name": "state", "description": {"suggested_value": "{{ states('sensor.x') }}"}},
            ],
        })
        fake_client.set_ws("config_entries/get", {"title": "My Helper", "domain": "template"})

        result = template_helpers.show(fake_client, ENTRY_ID)

        assert result["entry_id"] == ENTRY_ID
        assert result["title"] == "My Helper"
        assert result["domain"] == "template"
        assert result["options"]["name"] == "My Helper"
        assert result["options"]["state"] == "{{ states('sensor.x') }}"

    def test_show_by_entity_id_resolves_via_registry(self, fake_client):
        """When ident contains a dot, it's resolved via entity registry."""
        entity_id = "sensor.my_template"
        fake_client.set_ws("config/entity_registry/list", [
            {"entity_id": "sensor.other", "config_entry_id": "other-id"},
            {"entity_id": entity_id, "config_entry_id": ENTRY_ID},
        ])
        fake_client.set("POST", "config/config_entries/options/flow", {
            "flow_id": FLOW_ID,
            "data_schema": [
                {"name": "state", "description": {"suggested_value": "{{ 42 }}"}},
            ],
        })
        fake_client.set_ws("config_entries/get", {"title": "T", "domain": "template"})

        result = template_helpers.show(fake_client, entity_id)
        assert result["entry_id"] == ENTRY_ID
        assert result["title"] == "T"

    def test_show_entity_id_not_found_raises_keyerror(self, fake_client):
        """When entity_id is not in the registry, KeyError is raised."""
        fake_client.set_ws("config/entity_registry/list", [
            {"entity_id": "sensor.other", "config_entry_id": "x"},
        ])
        with pytest.raises(KeyError, match="no config_entry_id linked to entity"):
            template_helpers.show(fake_client, "sensor.missing")

    def test_show_empty_ident_raises(self, fake_client):
        with pytest.raises(ValueError, match="ident is required"):
            template_helpers.show(fake_client, "")

    def test_show_returns_empty_options_when_schema_empty(self, fake_client):
        fake_client.set("POST", "config/config_entries/options/flow", {
            "flow_id": FLOW_ID,
            "data_schema": [],
        })
        fake_client.set_ws("config_entries/get", {})
        result = template_helpers.show(fake_client, ENTRY_ID)
        assert result["options"] == {}
        assert result["entry_id"] == ENTRY_ID
