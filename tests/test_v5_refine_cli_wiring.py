"""CLI wiring tests for the v1.36.0 refine pass — powercalc group, entity
restored/orphans/prune commands, recorder top, and backup size promotion."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from cli_anything.homeassistant import homeassistant_cli as cli_mod


@pytest.fixture
def runner(monkeypatch, fake_client):
    monkeypatch.setattr(cli_mod, "make_client", lambda ctx: fake_client)
    return CliRunner()


def _invoke(runner, *args, json_out=True, input_text=None):
    full = ["--json"] + list(args) if json_out else list(args)
    return runner.invoke(
        cli_mod.cli, full,
        obj={"url": "http://x", "token": "t", "verify_ssl": False,
             "timeout": 5, "as_json": json_out, "config_path": None},
        input=input_text,
    )


# ──────────────────────────────────────────────────────── powercalc CLI

class TestPowercalcCli:
    def test_list(self, runner, fake_client):
        fake_client.set_ws("config_entries/get", [
            {"entry_id": "e1", "domain": "powercalc", "title": "Dining Fan",
             "state": "loaded"},
        ])
        r = _invoke(runner, "powercalc", "list", "--title-contains", "fan")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data[0]["entry_id"] == "e1"

    def test_set_template(self, runner, fake_client):
        # Wire menu→fixed→submit flow
        fake_client.responses[
            ("POST", "config/config_entries/options/flow")
        ] = {"flow_id": "FID", "type": "menu", "menu_options": ["fixed"]}
        fake_client.responses[
            ("POST", "config/config_entries/options/flow/FID")
        ] = {"flow_id": "FID", "type": "form", "step_id": "fixed"}
        r = _invoke(runner, "powercalc", "set-template", "ENTRY",
                    "{{ 42 if is_state('fan.x','on') else 0 }}")
        assert r.exit_code == 0, r.output
        last = fake_client.calls[-1]
        assert last["payload"] == {
            "power_template": "{{ 42 if is_state('fan.x','on') else 0 }}",
        }

    def test_set_power(self, runner, fake_client):
        fake_client.responses[
            ("POST", "config/config_entries/options/flow")
        ] = {"flow_id": "FID", "type": "menu", "menu_options": ["fixed"]}
        fake_client.responses[
            ("POST", "config/config_entries/options/flow/FID")
        ] = {"flow_id": "FID", "type": "form", "step_id": "fixed"}
        r = _invoke(runner, "powercalc", "set-power", "ENTRY", "25")
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["payload"] == {"power": 25.0}

    def test_reload_multi(self, runner, fake_client):
        r = _invoke(runner, "powercalc", "reload", "ent_a", "ent_b")
        assert r.exit_code == 0, r.output
        paths = [c["path"] for c in fake_client.calls[-2:]]
        assert paths == [
            "config/config_entries/entry/ent_a/reload",
            "config/config_entries/entry/ent_b/reload",
        ]

    def test_group_members(self, runner, fake_client):
        fake_client.set("GET", "states/sensor.power_dining",
                        {"state": "12", "attributes":
                            {"entities": ["sensor.a", "sensor.b"]}})
        r = _invoke(runner, "powercalc", "group", "members",
                    "sensor.power_dining")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output) == ["sensor.a", "sensor.b"]

    def test_group_add_members_uses_safe_merge(self, runner, fake_client):
        # current group state
        fake_client.set("GET", "states/sensor.power_dining",
                        {"state": "1", "attributes":
                            {"entities": ["sensor.existing"]}})
        # group options-flow open returns the group_custom menu
        fake_client.responses[
            ("POST", "config/config_entries/options/flow")
        ] = {"flow_id": "FID", "type": "menu",
             "menu_options": ["group_custom"]}
        fake_client.responses[
            ("POST", "config/config_entries/options/flow/FID")
        ] = {"flow_id": "FID", "type": "form"}
        r = _invoke(runner, "powercalc", "group", "add-members",
                    "--entry-id", "GE",
                    "--sensor", "sensor.power_dining",
                    "--member", "sensor.new1",
                    "--member", "sensor.new2")
        assert r.exit_code == 0, r.output
        # Final POST should submit the MERGED list, not just the new ones
        last = fake_client.calls[-1]
        assert last["payload"] == {
            "group_power_entities": ["sensor.existing", "sensor.new1",
                                     "sensor.new2"],
        }

    def test_group_set_members_requires_confirm(self, runner, fake_client):
        # No --yes / no piped 'y' → aborts
        r = _invoke(runner, "powercalc", "group", "set-members",
                    "--entry-id", "GE",
                    "--power-entity", "sensor.x")
        assert r.exit_code != 0


# ──────────────────────────────────────────────────────── entity restored/orphans/prune

class TestEntityAuditCli:
    def test_restored_summary(self, runner, fake_client):
        fake_client.set_ws("config/entity_registry/list", [
            {"entity_id": "sensor.a", "platform": "template",
             "config_entry_id": None},
            {"entity_id": "sensor.b", "platform": "wled",
             "config_entry_id": "x"},
        ])
        fake_client.set("GET", "states", [
            {"entity_id": "sensor.a", "state": "1",
             "attributes": {"restored": True}},
            {"entity_id": "sensor.b", "state": "2",
             "attributes": {"restored": True}},
        ])
        r = _invoke(runner, "entity", "restored")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        # JSON mode → full list (not summary)
        assert {row["entity_id"] for row in data} == {"sensor.a", "sensor.b"}

    def test_restored_platform_filter(self, runner, fake_client):
        fake_client.set_ws("config/entity_registry/list", [
            {"entity_id": "sensor.a", "platform": "template"},
            {"entity_id": "sensor.b", "platform": "wled"},
        ])
        fake_client.set("GET", "states", [
            {"entity_id": "sensor.a", "attributes": {"restored": True}},
            {"entity_id": "sensor.b", "attributes": {"restored": True}},
        ])
        r = _invoke(runner, "entity", "restored", "--platform", "template")
        data = json.loads(r.output)
        assert [d["entity_id"] for d in data] == ["sensor.a"]

    def test_orphans(self, runner, fake_client):
        fake_client.set_ws("config/entity_registry/list", [
            {"entity_id": "sensor.a", "config_entry_id": "exists"},
            {"entity_id": "sensor.b", "config_entry_id": "gone"},
        ])
        fake_client.set_ws("config_entries/get", [
            {"entry_id": "exists", "domain": "x"},
        ])
        r = _invoke(runner, "entity", "orphans")
        data = json.loads(r.output)
        assert [d["entity_id"] for d in data] == ["sensor.b"]
        assert data[0]["_orphan_reason"] == "missing"


class TestEntityPruneCli:
    def test_prune_dry_run_default(self, runner, fake_client):
        fake_client.set_ws("config/entity_registry/list", [
            {"entity_id": "sensor.a", "platform": "unifi",
             "disabled_by": "integration"},
            {"entity_id": "sensor.b", "platform": "unifi",
             "disabled_by": "integration"},
            {"entity_id": "sensor.c", "platform": "mqtt",
             "disabled_by": None},
        ])
        r = _invoke(runner, "entity", "prune", "--platform", "unifi",
                    "--disabled-by", "integration")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["dry_run"] is True
        assert data["total"] == 2
        assert data["removed_count"] == 2
        # No actual remove WS calls fired
        removes = [c for c in fake_client.ws_calls
                   if c["type"] == "config/entity_registry/remove"]
        assert removes == []

    def test_prune_apply_calls_remove(self, runner, fake_client):
        fake_client.set_ws("config/entity_registry/list", [
            {"entity_id": "sensor.a", "platform": "unifi",
             "disabled_by": "integration"},
        ])
        r = _invoke(runner, "entity", "prune", "--platform", "unifi",
                    "--disabled-by", "integration", "--apply")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["dry_run"] is False
        removes = [c for c in fake_client.ws_calls
                   if c["type"] == "config/entity_registry/remove"]
        assert len(removes) == 1
        assert removes[0]["payload"] == {"entity_id": "sensor.a"}

    def test_prune_protects_user_disabled(self, runner, fake_client):
        fake_client.set_ws("config/entity_registry/list", [
            {"entity_id": "sensor.a", "platform": "unifi",
             "disabled_by": "user"},   # user deliberately disabled
            {"entity_id": "sensor.b", "platform": "unifi",
             "disabled_by": "integration"},
        ])
        # disabled-by=any would otherwise sweep both — but user-protect must win
        r = _invoke(runner, "entity", "prune", "--platform", "unifi",
                    "--disabled-by", "any", "--apply")
        data = json.loads(r.output)
        assert data["removed_count"] == 1
        # sensor.a (user-disabled) was protected
        removes = [c for c in fake_client.ws_calls
                   if c["type"] == "config/entity_registry/remove"]
        assert removes[0]["payload"] == {"entity_id": "sensor.b"}

    def test_prune_explicit_entity_id_overrides_filters(self, runner,
                                                         fake_client):
        r = _invoke(runner, "entity", "prune",
                    "--entity-id", "sensor.x",
                    "--entity-id", "sensor.y",
                    "--apply")
        data = json.loads(r.output)
        assert data["total"] == 2
        removes = [c["payload"]["entity_id"] for c in fake_client.ws_calls
                   if c["type"] == "config/entity_registry/remove"]
        assert removes == ["sensor.x", "sensor.y"]


# ──────────────────────────────────────────────────────── recorder top

class TestRecorderTopCli:
    def test_top_default(self, runner, fake_client, monkeypatch):
        # Stub top_entities so we don't have to wire the per-entity history calls
        called = {}
        def fake_top(client, **kw):
            called.update(kw)
            return [{"entity_id": "sensor.x", "changes": 100,
                     "changes_per_hour": 4.17, "domain": "sensor",
                     "friendly_name": "X"}]
        monkeypatch.setattr("cli_anything.homeassistant.core.recorder.top_entities",
                            fake_top)
        r = _invoke(runner, "recorder", "top", "--hours", "24",
                    "--domain", "sensor", "--limit", "10")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data[0]["entity_id"] == "sensor.x"
        assert called["hours"] == 24.0
        assert called["domains"] == ["sensor"]
        assert called["limit"] == 10
        assert called["by"] == "changes"


# ──────────────────────────────────────────────────────── backup size promotion via CLI

class TestBackupListSize:
    def test_backup_list_promotes_size(self, runner, fake_client):
        fake_client.set_ws("backup/info", {
            "backups": [
                {"backup_id": "B1", "name": "test", "date": "2026-05-24",
                 "agents": {"backup.local": {"size": 1048576,
                                             "protected": False}}},
            ],
        })
        r = _invoke(runner, "backup", "list")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data[0]["size_mb"] == 1.0          # 1 MiB
        assert data[0]["agents"] == ["backup.local"]
        assert data[0]["protected"] is False
