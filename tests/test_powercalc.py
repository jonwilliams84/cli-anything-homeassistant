"""Tests for cli_anything.homeassistant.core.powercalc.

The two safety properties we care about most:
  (A) Group-membership operations never accidentally REPLACE when the caller
      meant ADD. (Lost 92+ entities to this bug on 2026-05-12.)
  (B) Creating fixed-mode virtual_power against a binary_sensor source raises
      a clear error rather than silently producing a 0 W sensor.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import powercalc


# ── flow-replay fake client ────────────────────────────────────────────────

class FlowFakeClient:
    """Minimal fake that replays a queued list of POST responses in order.

    The real options/config flow API makes several POSTs to the same path
    (``config/config_entries/flow/{flow_id}``), so a key-by-path response
    map isn't enough. We queue responses and pop them in FIFO order; tests
    can inspect every recorded call afterwards.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.post_queue: list = []
        self.get_responses: dict[str, object] = {}

    def queue_posts(self, *responses) -> None:
        self.post_queue.extend(responses)

    def set_get(self, path: str, response) -> None:
        self.get_responses[path.lstrip("/")] = response

    def get(self, path: str, params: dict | None = None):
        path = path.lstrip("/")
        self.calls.append({"verb": "GET", "path": path, "params": params})
        return self.get_responses.get(path, {})

    def post(self, path: str, payload=None):
        path = path.lstrip("/")
        self.calls.append({"verb": "POST", "path": path, "payload": payload})
        if not self.post_queue:
            raise AssertionError(
                f"POST {path} with no queued response — unexpected call. "
                f"Calls so far: {self.calls}",
            )
        return self.post_queue.pop(0)

    def delete(self, path: str):
        path = path.lstrip("/")
        self.calls.append({"verb": "DELETE", "path": path})
        return {}


@pytest.fixture
def flow_client() -> FlowFakeClient:
    return FlowFakeClient()


# ── get_group_members ──────────────────────────────────────────────────────

class TestGetGroupMembers:
    def test_returns_entities_attribute(self, flow_client):
        flow_client.set_get("states/sensor.power_kitchen_power", {
            "state": "85.0",
            "attributes": {"entities": ["sensor.a_power", "sensor.b_power"]},
        })
        result = powercalc.get_group_members(
            flow_client, "sensor.power_kitchen_power",
        )
        assert result == ["sensor.a_power", "sensor.b_power"]

    def test_missing_entities_attr_returns_empty(self, flow_client):
        flow_client.set_get("states/sensor.power_x_power", {
            "state": "0", "attributes": {},
        })
        assert powercalc.get_group_members(
            flow_client, "sensor.power_x_power",
        ) == []

    def test_empty_entity_id_raises(self, flow_client):
        with pytest.raises(ValueError, match="sensor_entity_id is required"):
            powercalc.get_group_members(flow_client, "")


# ── set_group_members ──────────────────────────────────────────────────────

class TestSetGroupMembers:
    def test_empty_entry_id_raises(self, flow_client):
        with pytest.raises(ValueError, match="entry_id is required"):
            powercalc.set_group_members(
                flow_client, "", power_entities=["sensor.x_power"],
            )

    def test_no_fields_raises(self, flow_client):
        with pytest.raises(ValueError, match="at least one of"):
            powercalc.set_group_members(flow_client, "abc")

    def test_submits_only_provided_fields(self, flow_client):
        # init returns a menu; advance step returns a form; submit returns create_entry
        flow_client.queue_posts(
            {"flow_id": "f1", "type": "menu",
             "menu_options": ["basic_options", "group_custom"]},
            {"flow_id": "f1", "type": "form", "step_id": "group_custom"},
            {"flow_id": "f1", "type": "create_entry"},
        )
        powercalc.set_group_members(
            flow_client, "entry-xyz",
            power_entities=["sensor.a_power", "sensor.b_power"],
        )
        # Final POST should contain ONLY group_power_entities.
        final = flow_client.calls[-1]
        assert final["payload"] == {
            "group_power_entities": ["sensor.a_power", "sensor.b_power"],
        }

    def test_sub_groups_uses_correct_field_name(self, flow_client):
        flow_client.queue_posts(
            {"flow_id": "f1", "type": "menu",
             "menu_options": ["basic_options", "group_custom"]},
            {"flow_id": "f1", "type": "form", "step_id": "group_custom"},
            {"flow_id": "f1", "type": "create_entry"},
        )
        powercalc.set_group_members(
            flow_client, "entry-xyz", sub_groups=["entry-a", "entry-b"],
        )
        final = flow_client.calls[-1]
        assert final["payload"] == {"sub_groups": ["entry-a", "entry-b"]}

    def test_no_menu_raises_if_group_custom_missing(self, flow_client):
        flow_client.queue_posts(
            {"flow_id": "f1", "type": "menu",
             "menu_options": ["basic_options"]},
        )
        with pytest.raises(RuntimeError, match="no `group_custom` step"):
            powercalc.set_group_members(
                flow_client, "entry-xyz", power_entities=[],
            )


# ── add_group_members — the headline safety guarantee ──────────────────────

class TestAddGroupMembers:
    def test_merges_with_existing_members(self, flow_client):
        """The critical property: ADD must not REPLACE.

        Existing members: [a, b, c]. Caller adds [d]. Final POST must
        contain [a, b, c, d], not just [d].
        """
        flow_client.set_get("states/sensor.power_kitchen_power", {
            "state": "0", "attributes": {
                "entities": ["sensor.a_power", "sensor.b_power", "sensor.c_power"],
            },
        })
        flow_client.queue_posts(
            {"flow_id": "f1", "type": "menu",
             "menu_options": ["basic_options", "group_custom"]},
            {"flow_id": "f1", "type": "form", "step_id": "group_custom"},
            {"flow_id": "f1", "type": "create_entry"},
        )
        powercalc.add_group_members(
            flow_client, "kitchen-entry",
            sensor_entity_id="sensor.power_kitchen_power",
            entities=["sensor.d_power"],
        )
        final_payload = flow_client.calls[-1]["payload"]
        assert final_payload["group_power_entities"] == [
            "sensor.a_power", "sensor.b_power",
            "sensor.c_power", "sensor.d_power",
        ]

    def test_dedup_preserves_existing_order(self, flow_client):
        flow_client.set_get("states/sensor.power_x_power", {
            "attributes": {"entities": ["sensor.a", "sensor.b"]},
        })
        flow_client.queue_posts(
            {"flow_id": "f1", "type": "menu",
             "menu_options": ["group_custom"]},
            {"flow_id": "f1", "type": "form", "step_id": "group_custom"},
            {"flow_id": "f1", "type": "create_entry"},
        )
        # Asking to add `a` (already present) + `c` (new) — order preserved,
        # `a` not duplicated.
        powercalc.add_group_members(
            flow_client, "x", sensor_entity_id="sensor.power_x_power",
            entities=["sensor.a", "sensor.c"],
        )
        final = flow_client.calls[-1]["payload"]["group_power_entities"]
        assert final == ["sensor.a", "sensor.b", "sensor.c"]

    def test_empty_entities_raises(self, flow_client):
        with pytest.raises(ValueError, match="non-empty"):
            powercalc.add_group_members(
                flow_client, "x",
                sensor_entity_id="sensor.power_x_power", entities=[],
            )

    def test_empty_sensor_entity_raises(self, flow_client):
        with pytest.raises(ValueError, match="sensor_entity_id"):
            powercalc.add_group_members(
                flow_client, "x", sensor_entity_id="",
                entities=["sensor.a"],
            )


# ── remove_group_members ───────────────────────────────────────────────────

class TestRemoveGroupMembers:
    def test_removes_only_named_entities(self, flow_client):
        flow_client.set_get("states/sensor.power_x_power", {
            "attributes": {"entities": [
                "sensor.a_power", "sensor.b_power", "sensor.c_power",
            ]},
        })
        flow_client.queue_posts(
            {"flow_id": "f1", "type": "menu",
             "menu_options": ["group_custom"]},
            {"flow_id": "f1", "type": "form", "step_id": "group_custom"},
            {"flow_id": "f1", "type": "create_entry"},
        )
        powercalc.remove_group_members(
            flow_client, "x", sensor_entity_id="sensor.power_x_power",
            entities=["sensor.b_power"],
        )
        final = flow_client.calls[-1]["payload"]["group_power_entities"]
        assert final == ["sensor.a_power", "sensor.c_power"]

    def test_removing_all_yields_empty_list(self, flow_client):
        flow_client.set_get("states/sensor.power_x_power", {
            "attributes": {"entities": ["sensor.a_power"]},
        })
        flow_client.queue_posts(
            {"flow_id": "f1", "type": "menu",
             "menu_options": ["group_custom"]},
            {"flow_id": "f1", "type": "form", "step_id": "group_custom"},
            {"flow_id": "f1", "type": "create_entry"},
        )
        powercalc.remove_group_members(
            flow_client, "x", sensor_entity_id="sensor.power_x_power",
            entities=["sensor.a_power"],
        )
        final = flow_client.calls[-1]["payload"]["group_power_entities"]
        assert final == []


# ── create_virtual_power — the second safety guarantee ─────────────────────

class TestCreateVirtualPower:
    def test_binary_sensor_with_power_raises(self, flow_client):
        """The headline safety: fixed-mode + binary_sensor source = error.

        Powercalc accepts this combination but the resulting sensor is
        stuck at 0 W — the bug that hid a 3 900 W immersion-heater cycle
        from the dashboard.
        """
        with pytest.raises(ValueError, match="binary_sensor"):
            powercalc.create_virtual_power(
                flow_client,
                source_entity="binary_sensor.relay",
                name="X",
                power=3000,
            )

    def test_binary_sensor_with_power_error_suggests_template(self, flow_client):
        """Error message must include a copy-pasteable template fix."""
        with pytest.raises(ValueError, match=r"power_template="):
            powercalc.create_virtual_power(
                flow_client,
                source_entity="binary_sensor.relay",
                name="X",
                power=3000,
            )

    def test_binary_sensor_with_template_is_allowed(self, flow_client):
        """The escape hatch — template-based gating works."""
        flow_client.queue_posts(
            {"flow_id": "f1"},                                # init menu
            {"flow_id": "f1"},                                # next_step_id
            {"flow_id": "f1"},                                # user step
            {"flow_id": "f1", "step_id": "assign_groups"},   # fixed step
            {"flow_id": "f1", "step_id": "power_advanced",
             "type": "form"},                                 # assign_groups submit
            {"type": "create_entry",
             "result": {"entry_id": "new-entry"}},            # power_advanced submit
        )
        result = powercalc.create_virtual_power(
            flow_client,
            source_entity="binary_sensor.relay",
            name="Immersion",
            power_template="{{ 3000 if is_state('binary_sensor.relay', 'on') else 0 }}",
        )
        assert result.get("type") == "create_entry"
        assert result.get("result", {}).get("entry_id") == "new-entry"

    def test_switch_source_with_power_is_allowed(self, flow_client):
        """Sanity: switch-domain sources DO work with fixed power."""
        flow_client.queue_posts(
            {"flow_id": "f1"},
            {"flow_id": "f1"},
            {"flow_id": "f1"},
            {"flow_id": "f1", "step_id": "assign_groups"},
            {"flow_id": "f1", "type": "form",
             "step_id": "power_advanced"},
            {"type": "create_entry",
             "result": {"entry_id": "entry-y"}},
        )
        result = powercalc.create_virtual_power(
            flow_client, source_entity="switch.kettle",
            name="Kettle", power=2200,
        )
        assert result.get("type") == "create_entry"

    def test_both_power_and_template_raises(self, flow_client):
        with pytest.raises(ValueError, match="only one of"):
            powercalc.create_virtual_power(
                flow_client, source_entity="switch.x", name="X",
                power=100, power_template="{{ 100 }}",
            )

    def test_neither_power_nor_template_raises(self, flow_client):
        with pytest.raises(ValueError, match="either power="):
            powercalc.create_virtual_power(
                flow_client, source_entity="switch.x", name="X",
            )

    def test_missing_source_entity_raises(self, flow_client):
        with pytest.raises(ValueError, match="source_entity"):
            powercalc.create_virtual_power(
                flow_client, source_entity="", name="X", power=100,
            )

    def test_missing_name_raises(self, flow_client):
        with pytest.raises(ValueError, match="name"):
            powercalc.create_virtual_power(
                flow_client, source_entity="switch.x", name="", power=100,
            )

    def test_groups_passed_to_assign_groups_step(self, flow_client):
        """The groups= list must reach the assign_groups submission."""
        flow_client.queue_posts(
            {"flow_id": "f1"},                                # init
            {"flow_id": "f1"},                                # next_step_id
            {"flow_id": "f1"},                                # user step
            {"flow_id": "f1", "step_id": "assign_groups"},   # fixed step
            {"flow_id": "f1", "type": "form",
             "step_id": "power_advanced"},                    # assign_groups submit
            {"type": "create_entry",
             "result": {"entry_id": "e"}},                    # power_advanced submit
        )
        powercalc.create_virtual_power(
            flow_client, source_entity="switch.x", name="X",
            power=10, groups=["group-a", "group-b"],
        )
        # The 5th POST is the assign_groups submission.
        assign_call = flow_client.calls[4]
        assert assign_call["payload"] == {"group": ["group-a", "group-b"]}
