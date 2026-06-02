"""Unit tests for the v1.36.0 refine pass — powercalc CLI helpers,
registry orphan/prune helpers, recorder top, and the backup size-surfacing
enrichment.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import (
    backup as backup_core,
    powercalc as powercalc_core,
    recorder as recorder_core,
    registry as registry_core,
)


# ──────────────────────────────────────────────────────────── backup._enrich

class TestBackupEnrich:
    def test_enrich_sums_agent_sizes(self):
        out = backup_core._enrich({
            "backup_id": "abc", "name": "x",
            "agents": {
                "backup.local": {"size": 100, "protected": False},
                "backup.cloud": {"size": 200, "protected": True},
            },
        })
        assert out["size_bytes"] == 300
        assert sorted(out["agent_ids"]) == ["backup.cloud", "backup.local"]
        assert out["protected"] is True

    def test_enrich_no_agents(self):
        out = backup_core._enrich({"backup_id": "abc", "agents": {}})
        assert out["size_bytes"] is None
        assert out["agent_ids"] == []
        assert out["protected"] is False

    def test_enrich_size_none_for_pending_backup(self):
        out = backup_core._enrich({
            "backup_id": "abc",
            "agents": {"backup.local": {"size": None, "protected": False}},
        })
        assert out["size_bytes"] is None
        assert out["agent_ids"] == ["backup.local"]

    def test_info_promotes_fields(self, fake_client):
        fake_client.set_ws("backup/info", {
            "backups": [
                {"backup_id": "a", "name": "n",
                 "agents": {"local": {"size": 100}}},
                {"backup_id": "b", "name": "m",
                 "agents": {"local": {"size": 50}, "cloud": {"size": 75}}},
            ],
        })
        d = backup_core.info(fake_client)
        assert d["backups"][0]["size_bytes"] == 100
        assert d["backups"][1]["size_bytes"] == 125
        assert sorted(d["backups"][1]["agent_ids"]) == ["cloud", "local"]


# ──────────────────────────────────────────────────────────── powercalc list/reload/template

class TestPowercalcListEntries:
    def test_filters_to_powercalc_domain(self, fake_client):
        """Powercalc filtering is delegated to the WS server via the
        config_entries/get domain payload; verify the right payload is sent."""
        # Real HA would return only the matching domain; the fake echoes
        # whatever we configure, so we pre-filter to mimic HA's response.
        fake_client.set_ws("config_entries/get", [
            {"entry_id": "a", "domain": "powercalc", "title": "Fan",
             "state": "loaded"},
        ])
        rows = powercalc_core.list_entries(fake_client)
        assert len(rows) == 1
        assert rows[0]["entry_id"] == "a"
        # And the WS payload requests the powercalc domain.
        assert fake_client.ws_calls[-1]["type"] == "config_entries/get"
        assert fake_client.ws_calls[-1]["payload"] == {"domain": "powercalc"}

    def test_title_contains_filter(self, fake_client):
        fake_client.set_ws("config_entries/get", [
            {"entry_id": "a", "domain": "powercalc",
             "title": "Dining Room Fan", "state": "loaded"},
            {"entry_id": "b", "domain": "powercalc",
             "title": "Kitchen Lamp", "state": "loaded"},
        ])
        rows = powercalc_core.list_entries(fake_client,
                                           title_contains="dining")
        assert len(rows) == 1
        assert rows[0]["entry_id"] == "a"

    def test_state_filter(self, fake_client):
        fake_client.set_ws("config_entries/get", [
            {"entry_id": "a", "domain": "powercalc", "title": "X",
             "state": "loaded"},
            {"entry_id": "b", "domain": "powercalc", "title": "Y",
             "state": "not_loaded"},
        ])
        rows = powercalc_core.list_entries(fake_client, state="not_loaded")
        assert len(rows) == 1
        assert rows[0]["entry_id"] == "b"


class TestPowercalcReload:
    def test_reload_entry_hits_rest_endpoint(self, fake_client):
        powercalc_core.reload_entry(fake_client, "abc")
        c = fake_client.calls[-1]
        assert c["verb"] == "POST"
        assert c["path"] == "config/config_entries/entry/abc/reload"

    def test_reload_entry_requires_id(self, fake_client):
        with pytest.raises(ValueError, match="entry_id"):
            powercalc_core.reload_entry(fake_client, "")

    def test_reload_groups_for_member_iterates(self, fake_client):
        out = powercalc_core.reload_groups_for_member(
            fake_client, parent_entry_ids=["a", "b", "c"],
        )
        paths = [c["path"] for c in fake_client.calls[-3:]]
        assert paths == [
            "config/config_entries/entry/a/reload",
            "config/config_entries/entry/b/reload",
            "config/config_entries/entry/c/reload",
        ]
        assert set(out.keys()) == {"a", "b", "c"}


class TestPowercalcSetTemplate:
    def _wire_fixed_menu(self, fake_client):
        """Wire fake responses for the options-flow → fixed step traversal."""
        fake_client.responses[("POST", "config/config_entries/options/flow")] = {
            "flow_id": "FID", "type": "menu",
            "menu_options": ["basic_options", "fixed", "advanced_options"],
        }
        # First options-configure (next_step_id=fixed) → form
        fake_client.responses[
            ("POST", "config/config_entries/options/flow/FID")
        ] = {"flow_id": "FID", "type": "form", "step_id": "fixed",
             "data_schema": [{"name": "power_template"}]}

    def test_set_power_template_full_flow(self, fake_client):
        self._wire_fixed_menu(fake_client)
        powercalc_core.set_power_template(
            fake_client, "ENTRY",
            power_template="{{ 30 if is_state('fan.x','on') else 0 }}",
        )
        # Four POSTs: open flow, advance to fixed, submit template, reload
        path_seq = [c["path"] for c in fake_client.calls if c["verb"] == "POST"]
        assert path_seq[-4:] == [
            "config/config_entries/options/flow",
            "config/config_entries/options/flow/FID",
            "config/config_entries/options/flow/FID",
            "config/config_entries/entry/ENTRY/reload",
        ]
        # The template submission is the POST before the reload
        submit = [c for c in fake_client.calls if c["verb"] == "POST"][-2]
        assert submit["payload"] == {
            "power_template": "{{ 30 if is_state('fan.x','on') else 0 }}",
        }

    def test_set_power_template_rejects_empty(self, fake_client):
        with pytest.raises(ValueError, match="power_template"):
            powercalc_core.set_power_template(fake_client, "ENTRY",
                                              power_template="")

    def test_set_power_template_rejects_missing_entry_id(self, fake_client):
        with pytest.raises(ValueError, match="entry_id"):
            powercalc_core.set_power_template(fake_client, "",
                                              power_template="{{ 1 }}")

    def test_set_power_template_rejects_non_fixed_menu(self, fake_client):
        # No 'fixed' option in the menu — should raise
        fake_client.responses[("POST", "config/config_entries/options/flow")] = {
            "flow_id": "FID", "type": "menu",
            "menu_options": ["group_custom"],   # this is a group entry
        }
        with pytest.raises(RuntimeError, match="fixed"):
            powercalc_core.set_power_template(fake_client, "ENTRY",
                                              power_template="{{ 1 }}")

    def test_set_fixed_power_submits_number(self, fake_client):
        self._wire_fixed_menu(fake_client)
        powercalc_core.set_fixed_power(fake_client, "ENTRY", power=42.5)
        posts = [c for c in fake_client.calls if c["verb"] == "POST"]
        # submit clears any stale template (it would otherwise shadow the
        # constant); a reload follows so the change lands on the sensor.
        assert posts[-2]["payload"] == {"power": 42.5, "power_template": ""}
        assert posts[-1]["path"] == "config/config_entries/entry/ENTRY/reload"


# ──────────────────────────────────────────────────────────── registry: remove + bulk

class TestRegistryRemove:
    def test_remove_entity_ws_shape(self, fake_client):
        registry_core.remove_entity(fake_client, "light.kitchen")
        last = fake_client.ws_calls[-1]
        assert last["type"] == "config/entity_registry/remove"
        assert last["payload"] == {"entity_id": "light.kitchen"}

    def test_remove_requires_id(self, fake_client):
        with pytest.raises(ValueError, match="entity_id"):
            registry_core.remove_entity(fake_client, "")


class TestBulkRemove:
    def test_dry_run_does_not_call_ws(self, fake_client):
        out = registry_core.bulk_remove_entities(
            fake_client, entity_ids=["a", "b", "c"], dry_run=True,
        )
        assert out == {"removed": ["a", "b", "c"], "failed": [],
                       "dry_run": True, "total": 3}
        # No remove WS calls
        removes = [c for c in fake_client.ws_calls
                   if c["type"] == "config/entity_registry/remove"]
        assert removes == []

    def test_per_entity_error_does_not_abort(self, fake_client, monkeypatch):
        """One bad entity must not stop the loop."""
        calls = []

        def fake_remove(client, eid):
            calls.append(eid)
            if eid == "b":
                raise RuntimeError("boom")
            return {}

        monkeypatch.setattr(registry_core, "remove_entity", fake_remove)
        out = registry_core.bulk_remove_entities(
            fake_client, entity_ids=["a", "b", "c", "d"], dry_run=False,
        )
        assert calls == ["a", "b", "c", "d"]
        assert out["removed"] == ["a", "c", "d"]
        assert len(out["failed"]) == 1
        assert out["failed"][0]["entity_id"] == "b"
        assert "boom" in out["failed"][0]["error"]

    def test_progress_callback_invoked(self, fake_client):
        seen = []

        def cb(done, total, ok, errs):
            seen.append((done, total, ok, errs))

        registry_core.bulk_remove_entities(
            fake_client, entity_ids=["a", "b"], dry_run=True,
            progress_every=1, on_progress=cb,
        )
        # Called at i=1 and i=2 (final)
        assert seen == [(1, 2, 1, 0), (2, 2, 2, 0)]


# ──────────────────────────────────────────────────────────── registry: find_restored / find_orphan

class TestFindRestored:
    def test_returns_only_restored_true(self, fake_client):
        fake_client.set_ws("config/entity_registry/list", [
            {"entity_id": "sensor.a", "platform": "template",
             "config_entry_id": None},
            {"entity_id": "sensor.b", "platform": "wled",
             "config_entry_id": "cfg1"},
            {"entity_id": "sensor.c", "platform": "template",
             "config_entry_id": None},
        ])
        fake_client.set("GET", "states", [
            {"entity_id": "sensor.a", "state": "1",
             "attributes": {"restored": True, "friendly_name": "A"}},
            {"entity_id": "sensor.b", "state": "2",
             "attributes": {}},
            {"entity_id": "sensor.c", "state": "unavailable",
             "attributes": {"restored": True}},
        ])
        out = registry_core.find_restored_entities(fake_client)
        assert {r["entity_id"] for r in out} == {"sensor.a", "sensor.c"}
        # _state and _friendly_name are added
        by_id = {r["entity_id"]: r for r in out}
        assert by_id["sensor.a"]["_state"] == "1"
        assert by_id["sensor.a"]["_friendly_name"] == "A"


class TestFindOrphan:
    def test_classifies_missing_vs_no_cfg(self, fake_client):
        fake_client.set_ws("config/entity_registry/list", [
            {"entity_id": "sensor.a", "config_entry_id": "exists"},
            {"entity_id": "sensor.b", "config_entry_id": "gone"},
            {"entity_id": "sensor.c", "config_entry_id": None},
        ])
        fake_client.set_ws("config_entries/get", [
            {"entry_id": "exists", "domain": "x"},
        ])
        out = registry_core.find_orphan_entities(fake_client)
        by_id = {r["entity_id"]: r["_orphan_reason"] for r in out}
        assert by_id == {"sensor.b": "missing", "sensor.c": "no_config_entry"}


# ──────────────────────────────────────────────────────────── recorder.top_entities

class TestRecorderTop:
    def test_orders_by_change_count(self, fake_client):
        fake_client.set("GET", "states", [
            {"entity_id": "sensor.a",
             "attributes": {"friendly_name": "A"}},
            {"entity_id": "sensor.b",
             "attributes": {"friendly_name": "B"}},
            {"entity_id": "switch.c",
             "attributes": {"friendly_name": "C"}},
        ])
        # Each /api/history/period/... call returns [[point, point, …]]
        # sensor.a → 5 points; sensor.b → 20; switch.c → 2
        def fake_get(path, params=None):
            fake_client.calls.append({"verb": "GET", "path": path,
                                       "params": params})
            if path == "states":
                return fake_client.responses.get(("GET", "states"), [])
            eid = (params or {}).get("filter_entity_id")
            counts = {"sensor.a": 5, "sensor.b": 20, "switch.c": 2}
            return [[{"state": "v"}] * counts.get(eid, 0)]
        fake_client.get = fake_get   # type: ignore[method-assign]

        rows = recorder_core.top_entities(fake_client, hours=10, limit=10)
        assert [r["entity_id"] for r in rows] == [
            "sensor.b", "sensor.a", "switch.c",
        ]
        assert rows[0]["changes"] == 20
        assert rows[0]["changes_per_hour"] == 2.0  # 20/10

    def test_domains_filter(self, fake_client):
        fake_client.set("GET", "states", [
            {"entity_id": "sensor.a", "attributes": {}},
            {"entity_id": "switch.c", "attributes": {}},
        ])
        def fake_get(path, params=None):
            fake_client.calls.append({"verb": "GET", "path": path,
                                       "params": params})
            if path == "states":
                return fake_client.responses.get(("GET", "states"), [])
            return [[{"state": "v"}, {"state": "v"}]]
        fake_client.get = fake_get   # type: ignore[method-assign]

        rows = recorder_core.top_entities(
            fake_client, hours=1, domains=["switch"], limit=5,
        )
        assert {r["entity_id"] for r in rows} == {"switch.c"}

    def test_limit_caps_results(self, fake_client):
        fake_client.set("GET", "states", [
            {"entity_id": f"sensor.{i}", "attributes": {}}
            for i in range(10)
        ])
        def fake_get(path, params=None):
            fake_client.calls.append({"verb": "GET", "path": path,
                                       "params": params})
            if path == "states":
                return fake_client.responses.get(("GET", "states"), [])
            eid = (params or {}).get("filter_entity_id")
            n = int(eid.split(".")[1])
            return [[{"state": "v"}] * n]
        fake_client.get = fake_get   # type: ignore[method-assign]

        rows = recorder_core.top_entities(fake_client, hours=1, limit=3)
        # entity 0 has 0 points (filtered out); 1..9 → top 3 are 9, 8, 7
        assert [r["entity_id"] for r in rows] == [
            "sensor.9", "sensor.8", "sensor.7",
        ]

    def test_unknown_by_raises(self, fake_client):
        with pytest.raises(ValueError, match="by"):
            recorder_core.top_entities(fake_client, by="bytes")
