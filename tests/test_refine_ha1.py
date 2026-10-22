"""CLI wiring tests for the ha-1 refine pass.

Covers:
  * `backup create` — the 2026.10 payload (required `agent_ids`,
    `include_database` instead of `database_included`)   — fixes #52
  * `service call --raw` — a value sent VERBATIM as a string
  * `lovelace prune --entity-prefix` — picture-elements `elements: [...]`
    and the entries of an `entities: [...]` list
  * the destructive commands' `--yes` escape hatch, and `automation delete`
    accepting an automation's numeric config id
  * `http config` / `http set` / `http promote`
  * `repairs ignore DOMAIN ISSUE_ID`
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from cli_anything.homeassistant import homeassistant_cli as cli_mod


@pytest.fixture
def runner(monkeypatch, fake_client):
    monkeypatch.setattr(cli_mod, "make_client", lambda ctx: fake_client)
    return CliRunner()


def _invoke(runner, *args, json_out=True, input=None):
    full = ["--json"] + list(args) if json_out else list(args)
    return runner.invoke(
        cli_mod.cli,
        full,
        obj={
            "url": "http://x", "token": "t", "verify_ssl": False,
            "timeout": 5, "as_json": json_out, "config_path": None,
        },
        input=input,
    )


# ─────────────────────────────────────────────────────────── backup create (#52)


class TestBackupCreate:
    def test_agent_ids_default_to_every_agent(self, runner, fake_client):
        fake_client.set_ws(
            "backup/agents/info",
            {"agents": [{"agent_id": "backup.local"}, {"agent_id": "backup.cloud"}]},
        )
        fake_client.set_ws("backup/generate", {"job_id": "j1"})
        r = _invoke(runner, "backup", "create")
        assert r.exit_code == 0, r.output
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["agent_ids"] == ["backup.local", "backup.cloud"]
        assert payload["include_database"] is True
        assert "database_included" not in payload

    def test_no_database(self, runner, fake_client):
        fake_client.set_ws("backup/agents/info", {"agents": [{"agent_id": "backup.local"}]})
        fake_client.set_ws("backup/generate", {"job_id": "j1"})
        r = _invoke(runner, "backup", "create", "--no-database")
        assert r.exit_code == 0, r.output
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["include_database"] is False
        assert "database_included" not in payload

    def test_explicit_agent(self, runner, fake_client):
        fake_client.set_ws("backup/agents/info", {"agents": [{"agent_id": "backup.local"}]})
        fake_client.set_ws("backup/generate", {"job_id": "j1"})
        r = _invoke(runner, "backup", "create", "--agent", "backup.cloud")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"]["agent_ids"] == ["backup.cloud"]

    def test_no_agents_is_a_clean_error(self, runner, fake_client):
        fake_client.set_ws("backup/agents/info", {"agents": []})
        r = _invoke(runner, "backup", "create")
        assert r.exit_code != 0
        assert "no backup agents" in r.output


# ─────────────────────────────────────────────────────────────── service --raw


class TestServiceRaw:
    def test_raw_value_is_sent_verbatim(self, runner, fake_client):
        fake_client.set_service("mqtt", "publish", {})
        r = _invoke(
            runner, "service", "call", "mqtt", "publish",
            "--raw", 'payload={"id":"x"}',
        )
        assert r.exit_code == 0, r.output
        body = fake_client.calls[-1]
        assert body["verb"] == "POST"
        assert body["payload"]["payload"] == '{"id":"x"}'
        assert isinstance(body["payload"]["payload"], str)

    def test_data_still_json_decodes(self, runner, fake_client):
        fake_client.set_service("mqtt", "publish", {})
        r = _invoke(runner, "service", "call", "mqtt", "publish", "-D", "qos=1")
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["payload"]["qos"] == 1

    def test_raw_overrides_data(self, runner, fake_client):
        fake_client.set_service("mqtt", "publish", {})
        r = _invoke(
            runner, "service", "call", "mqtt", "publish",
            "-D", "payload=123",
            "--raw", "payload=123",
        )
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["payload"]["payload"] == "123"

    def test_dry_run_shows_the_raw_value(self, runner, fake_client):
        r = _invoke(
            runner, "service", "call", "mqtt", "publish",
            "--raw", 'payload={"id":"x"}',
            "--dry-run",
        )
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["service_data"]["payload"] == '{"id":"x"}'

    def test_bad_raw_pair_is_rejected(self, runner, fake_client):
        r = _invoke(runner, "service", "call", "mqtt", "publish", "--raw", "nope")
        assert r.exit_code != 0
        assert "key=value" in r.output

    def test_mqtt_publish_sends_a_string_payload(self, runner, fake_client):
        fake_client.set_service("mqtt", "publish", {})
        r = _invoke(runner, "mqtt", "publish", "home/x", '{"id":"x"}', "--retain", "--qos", "1")
        assert r.exit_code == 0, r.output
        data = fake_client.calls[-1]["payload"]
        assert data["topic"] == "home/x"
        assert data["payload"] == '{"id":"x"}'
        assert data["retain"] is True
        assert data["qos"] == 1


# ─────────────────────────────────────────────────────── lovelace prune (items)


class TestLovelacePruneEntities:
    def _cfg(self):
        return {
            "views": [
                {
                    "cards": [
                        {
                            "type": "picture-elements",
                            "image": "/local/x.png",
                            "elements": [
                                {"type": "entity", "entity": "sensor.old_1"},
                                {"type": "entity", "entity": "sensor.new_1"},
                            ],
                        },
                        {"type": "entities", "entities": ["sensor.old_2", "sensor.new_2"]},
                    ]
                }
            ]
        }

    def test_picture_elements_and_entities_entries_removed(self, runner, fake_client):
        cfg = self._cfg()
        fake_client.set_ws("lovelace/config", cfg)
        fake_client.set_ws("lovelace/config/save", {"saved": True})
        r = _invoke(
            runner, "lovelace", "prune", "gem-mobile", "--entity-prefix", "sensor.old_",
        )
        assert r.exit_code == 0, r.output
        saved = fake_client.ws_calls[-1]["payload"]["config"]
        cards = saved["views"][0]["cards"]
        assert cards[0]["elements"] == [{"type": "entity", "entity": "sensor.new_1"}]
        assert cards[1]["entities"] == ["sensor.new_2"]
        out = json.loads(r.output)
        assert out["removed_elements"] == 1
        assert out["removed_entities"] == 1


# ───────────────────────────────────────────────── destructive commands + --yes


class TestDestructiveYes:
    def test_automation_delete_with_yes_and_config_id(self, runner, fake_client):
        fake_client.set("DELETE", "config/automation/config/1723456789", {"ok": True})
        r = _invoke(runner, "automation", "delete", "1723456789", "--yes")
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["path"] == "config/automation/config/1723456789"
        assert json.loads(r.output)["deleted"] == "1723456789"

    def test_automation_delete_prompts_without_yes(self, runner, fake_client):
        r = _invoke(runner, "automation", "delete", "automation.x", input="n\n")
        assert r.exit_code != 0
        assert not [c for c in fake_client.calls if c["verb"] == "DELETE"]

    def test_automation_delete_rejects_a_bad_id(self, runner, fake_client):
        r = _invoke(runner, "automation", "delete", "not-an-automation", "--yes")
        assert r.exit_code != 0
        assert "entity_id" in r.output

    def test_config_entry_delete_with_yes(self, runner, fake_client):
        fake_client.set("DELETE", "config/config_entries/entry/entry1", {"ok": True})
        r = _invoke(runner, "config-entry", "delete", "entry1", "--yes")
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["verb"] == "DELETE"

    def test_config_entry_remove_device_with_yes(self, runner, fake_client):
        fake_client.set_ws("config/device_registry/remove_config_entry", {"ok": True})
        r = _invoke(runner, "config-entry", "remove-device", "entry1", "dev1", "--yes")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["type"] == "config/device_registry/remove_config_entry"

    def test_lovelace_config_save_with_yes(self, runner, fake_client, tmp_path):
        path = tmp_path / "cfg.json"
        path.write_text(json.dumps({"views": []}))
        fake_client.set_ws("lovelace/config", {"views": []})
        fake_client.set_ws("lovelace/config/save", {"saved": True})
        r = _invoke(runner, "lovelace", "config", "save", "gem-mobile", str(path), "--yes")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["type"] == "lovelace/config/save"


# ────────────────────────────────────────────────────────────── http config


class TestHttpConfig:
    def test_http_config_reads_the_websocket(self, runner, fake_client):
        fake_client.set_ws(
            "http/config",
            {
                "stable": {"server_port": 8123},
                "pending": None,
                "default": {"server_port": 8123},
                "active_config_type": "stable",
                "revert_at": None,
            },
        )
        r = _invoke(runner, "http", "config")
        assert r.exit_code == 0, r.output
        out = json.loads(r.output)
        assert out["stable"] == {"server_port": 8123}
        assert out["pending"] is None
        assert out["active_config_type"] == "stable"

    def test_http_set_merges_into_the_current_config(self, runner, fake_client):
        fake_client.set_ws(
            "http/config",
            {"stable": {"server_port": 8123, "ip_ban_enabled": True}, "pending": None},
        )
        fake_client.set_ws("http/config/configure", {"restart": True})
        r = _invoke(runner, "http", "set", "server_port=8124", "--yes")
        assert r.exit_code == 0, r.output
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["config"]["server_port"] == 8124
        assert payload["config"]["ip_ban_enabled"] is True
        assert json.loads(r.output) == {"restart": True}

    def test_http_set_wraps_a_single_list_value(self, runner, fake_client):
        fake_client.set_ws("http/config", {"stable": {}, "pending": None})
        fake_client.set_ws("http/config/configure", {"restart": True})
        r = _invoke(runner, "http", "set", "server_host=0.0.0.0", "--yes")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"]["config"]["server_host"] == ["0.0.0.0"]

    def test_http_set_rejects_an_unknown_key(self, runner, fake_client):
        r = _invoke(runner, "http", "set", "server_portz=8124", "--yes")
        assert r.exit_code != 0
        assert "server_port" in r.output

    def test_http_promote(self, runner, fake_client):
        fake_client.set_ws("http/config/promote", {})
        r = _invoke(runner, "http", "promote", "--yes")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["type"] == "http/config/promote"


# ─────────────────────────────────────────────────────────────── repairs ignore


class TestRepairsIgnore:
    def test_domain_and_issue_id_positionally(self, runner, fake_client):
        fake_client.set_ws("repairs/ignore_issue", {})
        r = _invoke(runner, "repairs", "ignore", "light", "abc")
        assert r.exit_code == 0, r.output
        call = fake_client.ws_calls[-1]
        assert call["type"] == "repairs/ignore_issue"
        assert call["payload"] == {"issue_id": "abc", "domain": "light", "ignore": True}

    def test_issue_id_with_domain_option(self, runner, fake_client):
        fake_client.set_ws("repairs/ignore_issue", {})
        r = _invoke(runner, "repairs", "ignore", "abc", "--domain", "light")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"]["domain"] == "light"

    def test_missing_domain_is_rejected(self, runner, fake_client):
        r = _invoke(runner, "repairs", "ignore", "abc")
        assert r.exit_code != 0
        assert "domain" in r.output
