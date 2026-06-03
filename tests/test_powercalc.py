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


# ── group_custom form helpers ──────────────────────────────────────────────

def _field(name, val):
    """A data_schema field carrying its current value where powercalc puts it:
    under description.suggested_value (NOT top-level — the bug we fixed)."""
    f = {"name": name}
    if val is not None:
        f["description"] = {"suggested_value": val}
    return f


def group_form(flow_id="f1", member=None, power=None, energy=None, sub=None):
    return {"flow_id": flow_id, "type": "form", "step_id": "group_custom",
            "data_schema": [
                _field("group_member_sensors", member),
                _field("group_power_entities", power),
                _field("group_energy_entities", energy),
                _field("sub_groups", sub),
            ]}


def _menu():
    return {"flow_id": "f1", "type": "menu",
            "menu_options": ["basic_options", "group_custom"]}


def _final_submit_payload(client):
    """Payload of the POST that submits the membership form (the one whose
    payload carries the group_* lists)."""
    for c in reversed(client.calls):
        if c["verb"] == "POST" and isinstance(c.get("payload"), dict) \
                and any(k.startswith("group_") for k in c["payload"]):
            return c["payload"]
    raise AssertionError(f"no membership submit found in {client.calls}")


# ── get_group_config ────────────────────────────────────────────────────────

class TestGetGroupConfig:
    def test_reads_suggested_value_from_description(self, flow_client):
        flow_client.queue_posts(
            _menu(),
            group_form(power=["sensor.a_power"], energy=["sensor.a_energy"],
                       member=["m1"]),
        )
        cfg = powercalc.get_group_config(flow_client, "E1")
        assert cfg["group_power_entities"] == ["sensor.a_power"]
        assert cfg["group_energy_entities"] == ["sensor.a_energy"]
        assert cfg["group_member_sensors"] == ["m1"]
        assert cfg["sub_groups"] == []
        # flow is aborted (read-only)
        assert any(c["verb"] == "DELETE" for c in flow_client.calls)


# ── set_group_members — preserve-on-write + verify ──────────────────────────

class TestSetGroupMembers:
    def test_empty_entry_id_raises(self, flow_client):
        with pytest.raises(ValueError, match="entry_id is required"):
            powercalc.set_group_members(
                flow_client, "", power_entities=["sensor.x_power"],
            )

    def test_no_fields_raises(self, flow_client):
        with pytest.raises(ValueError, match="at least one of"):
            powercalc.set_group_members(flow_client, "abc")

    def test_omitted_fields_are_resent_not_blanked(self, flow_client):
        """The headline fix for the spot-loss bug: setting only energy must
        RESEND the existing member + power lists, never blank them."""
        flow_client.queue_posts(
            _menu(),
            group_form(member=["m1", "m2"], power=["sensor.a_power"]),  # open
            {"type": "create_entry"},                                   # submit
            {},                                                          # reload
            _menu(),                                                     # verify open
            group_form(member=["m1", "m2"], power=["sensor.a_power"],
                       energy=["sensor.a_energy"]),                      # verify read
        )
        powercalc.set_group_members(
            flow_client, "E1", energy_entities=["sensor.a_energy"],
        )
        submit = _final_submit_payload(flow_client)
        assert submit["group_member_sensors"] == ["m1", "m2"]   # preserved
        assert submit["group_power_entities"] == ["sensor.a_power"]  # preserved
        assert submit["group_energy_entities"] == ["sensor.a_energy"]  # new

    def test_reloads_after_write(self, flow_client):
        flow_client.queue_posts(
            _menu(), group_form(power=["sensor.a_power"]),
            {"type": "create_entry"}, {},
            _menu(), group_form(power=["sensor.b_power"]),
        )
        powercalc.set_group_members(
            flow_client, "E1", power_entities=["sensor.b_power"],
        )
        assert any(c.get("path", "").endswith("/reload")
                   for c in flow_client.calls)

    def test_verify_raises_when_write_does_not_persist(self, flow_client):
        """If the read-back doesn't match what we asked for, raise — this is
        the silent non-persistence that bit us across an HA restart."""
        flow_client.queue_posts(
            _menu(), group_form(power=["sensor.a_power"]),
            {"type": "create_entry"}, {},
            _menu(), group_form(power=["sensor.a_power"]),  # stored != wanted
        )
        with pytest.raises(RuntimeError, match="did not persist"):
            powercalc.set_group_members(
                flow_client, "E1", power_entities=["sensor.b_power"],
            )

    def test_no_verify_skips_readback(self, flow_client):
        flow_client.queue_posts(
            _menu(), group_form(power=["sensor.a_power"]),
            {"type": "create_entry"}, {},
        )
        powercalc.set_group_members(
            flow_client, "E1", power_entities=["sensor.b_power"],
            verify=False,
        )
        # only one group_custom open (no verify re-read)
        opens = [c for c in flow_client.calls
                 if c.get("payload") == {"next_step_id": "group_custom"}]
        assert len(opens) == 1

    def test_no_menu_raises_if_group_custom_missing(self, flow_client):
        flow_client.queue_posts(
            {"flow_id": "f1", "type": "menu",
             "menu_options": ["basic_options"]},
        )
        with pytest.raises(RuntimeError, match="no `group_custom` step"):
            powercalc.set_group_members(
                flow_client, "entry-xyz", power_entities=[],
            )


# ── add_group_members — read-config-merge (not sensor-attr) ─────────────────

class TestAddGroupMembers:
    def test_merges_member_sensors_from_config(self, flow_client):
        """ADD must not REPLACE, and must read the CONFIGURED list (not the
        resolved leaf list, which was the never-persisting bug)."""
        flow_client.queue_posts(
            _menu(), group_form(member=["m1", "m2"]),     # read config
            _menu(), group_form(member=["m1", "m2"]),     # set: open
            {"type": "create_entry"}, {},                  # submit + reload
            _menu(), group_form(member=["m1", "m2", "m3"]),  # verify
        )
        powercalc.add_group_members(
            flow_client, "E1", member_sensors=["m3"],
        )
        submit = _final_submit_payload(flow_client)
        assert submit["group_member_sensors"] == ["m1", "m2", "m3"]

    def test_adds_power_and_energy_together(self, flow_client):
        flow_client.queue_posts(
            _menu(), group_form(power=["sensor.a_power"],
                                energy=["sensor.a_energy"]),
            _menu(), group_form(power=["sensor.a_power"],
                                energy=["sensor.a_energy"]),
            {"type": "create_entry"}, {},
            _menu(), group_form(power=["sensor.a_power", "sensor.b_power"],
                                energy=["sensor.a_energy", "sensor.b_energy"]),
        )
        powercalc.add_group_members(
            flow_client, "E1",
            power_entities=["sensor.b_power"],
            energy_entities=["sensor.b_energy"],
        )
        submit = _final_submit_payload(flow_client)
        assert submit["group_power_entities"] == [
            "sensor.a_power", "sensor.b_power"]
        assert submit["group_energy_entities"] == [
            "sensor.a_energy", "sensor.b_energy"]

    def test_dedup_preserves_existing_order(self, flow_client):
        flow_client.queue_posts(
            _menu(), group_form(power=["sensor.a", "sensor.b"]),
            _menu(), group_form(power=["sensor.a", "sensor.b"]),
            {"type": "create_entry"}, {},
            _menu(), group_form(power=["sensor.a", "sensor.b", "sensor.c"]),
        )
        powercalc.add_group_members(
            flow_client, "E1", power_entities=["sensor.a", "sensor.c"],
        )
        submit = _final_submit_payload(flow_client)
        assert submit["group_power_entities"] == [
            "sensor.a", "sensor.b", "sensor.c"]

    def test_nothing_to_add_raises(self, flow_client):
        with pytest.raises(ValueError, match="at least one of"):
            powercalc.add_group_members(flow_client, "E1")


# ── remove_group_members ───────────────────────────────────────────────────

class TestRemoveGroupMembers:
    def test_removes_only_named_from_config(self, flow_client):
        flow_client.queue_posts(
            _menu(), group_form(power=["sensor.a_power", "sensor.b_power",
                                       "sensor.c_power"]),               # read
            _menu(), group_form(power=["sensor.a_power", "sensor.b_power",
                                       "sensor.c_power"]),               # set open
            {"type": "create_entry"}, {},
            _menu(), group_form(power=["sensor.a_power", "sensor.c_power"]),
        )
        powercalc.remove_group_members(
            flow_client, "E1", power_entities=["sensor.b_power"],
        )
        submit = _final_submit_payload(flow_client)
        assert submit["group_power_entities"] == [
            "sensor.a_power", "sensor.c_power"]

    def test_nothing_to_remove_raises(self, flow_client):
        with pytest.raises(ValueError, match="at least one of"):
            powercalc.remove_group_members(flow_client, "E1")


# ── energy_siblings_for ─────────────────────────────────────────────────────

class TestEnergySiblings:
    def test_pairs_existing_energy_sensor(self, flow_client):
        states = [
            {"entity_id": "sensor.spot_1_energy",
             "attributes": {"device_class": "energy"}},
            {"entity_id": "sensor.ev_charger_energy",
             "attributes": {"device_class": "power"}},  # wrong dc → not a twin
        ]
        out = powercalc.energy_siblings_for(
            flow_client,
            ["sensor.spot_1_power", "sensor.ev_charger_power",
             "sensor.no_such_power"],
            states=states,
        )
        assert out["siblings"] == {
            "sensor.spot_1_power": "sensor.spot_1_energy"}
        assert set(out["no_sibling"]) == {
            "sensor.ev_charger_power", "sensor.no_such_power"}


# ── find_groups_containing ──────────────────────────────────────────────────

class TestFindGroupsContaining:
    def test_matches_member_and_power(self, flow_client, monkeypatch):
        monkeypatch.setattr(powercalc, "list_entries", lambda c, **k: [
            {"entry_id": "G1", "title": "Kitchen"},
            {"entry_id": "G2", "title": "Lighting"},
            {"entry_id": "G3", "title": "Unrelated"},
        ])
        cfgs = {
            "G1": {"group_member_sensors": ["LEAF"], "group_power_entities": [],
                   "group_energy_entities": [], "sub_groups": []},
            "G2": {"group_member_sensors": [],
                   "group_power_entities": ["sensor.leaf_power"],
                   "group_energy_entities": [], "sub_groups": []},
            "G3": {"group_member_sensors": ["other"],
                   "group_power_entities": [], "group_energy_entities": [],
                   "sub_groups": []},
        }
        monkeypatch.setattr(powercalc, "get_group_config",
                            lambda c, eid: cfgs[eid])
        out = powercalc.find_groups_containing(
            flow_client, entry_ids=["LEAF"],
            power_entities=["sensor.leaf_power"],
        )
        ids = {g["entry_id"] for g in out}
        assert ids == {"G1", "G2"}


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


# ── set-power / set-template hardening (v1.41) ──────────────────────────────

def _posts(client):
    return [c for c in client.calls if c["verb"] == "POST"]


class TestSetFixedPowerHardening:
    def test_clears_template_and_reloads(self, flow_client):
        flow_client.queue_posts(
            {"flow_id": "F1", "type": "menu",
             "menu_options": ["basic_options", "fixed", "advanced_options"]},
            {"type": "form", "step_id": "fixed"},
            {"type": "create_entry"},
            {"require_restart": False},          # reload
        )
        powercalc.set_fixed_power(flow_client, "E1", power=7.4)
        p = _posts(flow_client)
        submit = p[2]["payload"]
        assert submit["power"] == 7.4
        assert submit["power_template"] == ""        # sibling cleared
        assert p[-1]["path"] == "config/config_entries/entry/E1/reload"

    def test_reload_can_be_disabled(self, flow_client):
        flow_client.queue_posts(
            {"flow_id": "F1", "type": "menu", "menu_options": ["fixed"]},
            {"type": "form"},
            {"type": "create_entry"},
        )
        powercalc.set_fixed_power(flow_client, "E1", power=5, reload=False)
        assert all("/reload" not in c.get("path", "") for c in flow_client.calls)


class TestSetPowerTemplateHardening:
    def test_reloads_after_write(self, flow_client):
        flow_client.queue_posts(
            {"flow_id": "F", "type": "menu", "menu_options": ["fixed"]},
            {"type": "form"},
            {"type": "create_entry"},
            {},                                   # reload
        )
        powercalc.set_power_template(
            flow_client, "E1",
            power_template="{{ 5 if is_state('light.x','on') else 0 }}")
        p = _posts(flow_client)
        assert p[2]["payload"]["power_template"].startswith("{{")
        assert p[-1]["path"].endswith("/reload")

    def test_empty_template_raises(self, flow_client):
        with pytest.raises(ValueError):
            powercalc.set_power_template(flow_client, "E1", power_template="")


# ── set-standby (v1.41) ─────────────────────────────────────────────────────

class TestSetStandby:
    def test_drives_basic_options_resends_source_reloads(self, flow_client):
        flow_client.queue_posts(
            {"flow_id": "F", "type": "menu",
             "menu_options": ["basic_options", "fixed"]},
            {"type": "form", "step_id": "basic_options"},
            {"type": "create_entry"},
            {},                                   # reload
        )
        powercalc.set_standby(flow_client, "E1", standby_power=1.0,
                              source_entity="light.jonlamp")
        p = _posts(flow_client)
        assert p[1]["payload"] == {"next_step_id": "basic_options"}
        submit = p[2]["payload"]
        assert submit["standby_power"] == 1.0
        assert submit["entity_id"] == "light.jonlamp"   # source preserved
        assert p[-1]["path"].endswith("/reload")

    def test_no_basic_step_raises(self, flow_client):
        flow_client.queue_posts(
            {"flow_id": "F", "type": "menu", "menu_options": ["fixed"]},
        )
        with pytest.raises(RuntimeError):
            powercalc.set_standby(flow_client, "E1", standby_power=1.0,
                                  source_entity="light.x", reload=False)

    def test_requires_standby_value(self, flow_client):
        with pytest.raises(ValueError):
            powercalc.set_standby(flow_client, "E1", standby_power=None,
                                  source_entity="light.x")

    def test_unresolvable_source_raises(self, flow_client, monkeypatch):
        # No source passed and resolution finds nothing → refuse rather than
        # blank the entry's source.
        monkeypatch.setattr(powercalc, "list_entries",
                            lambda c, **k: [{"entry_id": "E1", "title": "X"}])
        flow_client.set_get("states", [])
        with pytest.raises(RuntimeError):
            powercalc.set_standby(flow_client, "E1", standby_power=1.0)


# ── read_entry / show (v1.41) ───────────────────────────────────────────────

class TestReadEntry:
    def test_surfaces_live_sensor_attrs(self, flow_client, monkeypatch):
        monkeypatch.setattr(
            powercalc, "list_entries",
            lambda c, **k: [{"entry_id": "E1", "title": "jonlamp",
                             "state": "loaded"}])
        flow_client.set_get("states", [{
            "entity_id": "sensor.jonlamp_power",
            "state": "1.00",
            "attributes": {"integration": "powercalc",
                           "calculation_mode": "fixed",
                           "source_entity": "light.jonlamp",
                           "friendly_name": "jonlamp Power"},
        }])
        # options-flow probes for configured values (best-effort) — let them
        # no-op by returning a flow with no usable flow_id.
        flow_client.queue_posts({"flow_id": None}, {"flow_id": None})
        out = powercalc.read_entry(flow_client, "E1")
        assert out["title"] == "jonlamp"
        assert out["calculation_mode"] == "fixed"
        assert out["source_entity"] == "light.jonlamp"
        assert out["current_power_w"] == 1.0
