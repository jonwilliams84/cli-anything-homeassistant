"""Unit tests for cli_anything.homeassistant.core.backup.

Covers _enrich, info, list_backups, details, generate, remove, restore,
agents_info, config_info — all the uncovered branches.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import backup
from cli_anything.homeassistant.core.backup import _enrich


# ── _enrich ───────────────────────────────────────────────────────────────────


class TestEnrich:
    def test_promotes_size_and_protected(self):
        b = {
            "slug": "abc",
            "agents": {
                "local": {"size": 1000, "protected": True},
                "cloud": {"size": 2000, "protected": False},
            },
        }
        out = _enrich(b)
        assert out["size_bytes"] == 3000
        assert out["agent_ids"] == ["local", "cloud"]
        assert out["protected"] is True

    def test_no_agents(self):
        b = {"slug": "abc"}
        out = _enrich(b)
        assert out["size_bytes"] is None
        assert out["agent_ids"] == []
        assert out["protected"] is False

    def test_none_size_skipped(self):
        b = {"agents": {"local": {"size": None}, "cloud": {"size": 500}}}
        out = _enrich(b)
        assert out["size_bytes"] == 500

    def test_all_none_sizes(self):
        b = {"agents": {"local": {"size": None}}}
        out = _enrich(b)
        assert out["size_bytes"] is None

    def test_non_dict_returns_unchanged(self):
        assert _enrich("not a dict") == "not a dict"
        assert _enrich(None) is None
        assert _enrich([1, 2]) == [1, 2]

    def test_does_not_mutate_input(self):
        b = {"slug": "x", "agents": {"local": {"size": 10, "protected": True}}}
        original = dict(b)
        _enrich(b)
        assert b == original


# ── info ──────────────────────────────────────────────────────────────────────


class TestInfo:
    def test_enriches_backups_list(self, fake_client):
        fake_client.set_ws("backup/info", {
            "backups": [
                {"slug": "b1", "agents": {"local": {"size": 100, "protected": True}}},
                {"slug": "b2", "agents": {"cloud": {"size": 200, "protected": False}}},
            ],
            "last_completed": "2026-01-01",
        })
        result = backup.info(fake_client)
        assert result["last_completed"] == "2026-01-01"
        assert result["backups"][0]["size_bytes"] == 100
        assert result["backups"][0]["protected"] is True
        assert result["backups"][1]["size_bytes"] == 200
        assert result["backups"][1]["protected"] is False

    def test_non_dict_response_returns_raw(self, fake_client):
        fake_client.set_ws("backup/info", "not a dict")
        result = backup.info(fake_client)
        assert result == {"raw": "not a dict"}

    def test_no_backups_key(self, fake_client):
        fake_client.set_ws("backup/info", {"last_completed": None})
        result = backup.info(fake_client)
        assert result == {"last_completed": None}

    def test_empty_response(self, fake_client):
        fake_client.set_ws("backup/info", {})
        result = backup.info(fake_client)
        assert result == {}


# ── list_backups ──────────────────────────────────────────────────────────────


class TestListBackups:
    def test_returns_enriched_list(self, fake_client):
        fake_client.set_ws("backup/info", {
            "backups": [
                {"slug": "b1", "agents": {"local": {"size": 100, "protected": True}}},
            ],
        })
        result = backup.list_backups(fake_client)
        assert len(result) == 1
        assert result[0]["size_bytes"] == 100
        assert result[0]["protected"] is True

    def test_empty_when_no_backups(self, fake_client):
        fake_client.set_ws("backup/info", {})
        assert backup.list_backups(fake_client) == []

    def test_empty_when_response_not_dict(self, fake_client):
        fake_client.set_ws("backup/info", "not a dict")
        assert backup.list_backups(fake_client) == []


# ── details ───────────────────────────────────────────────────────────────────


class TestDetails:
    def test_flat_dict_enriched(self, fake_client):
        fake_client.set_ws("backup/details", {
            "slug": "b1",
            "agents": {"local": {"size": 500, "protected": True}},
        })
        result = backup.details(fake_client, "b1")
        assert result["size_bytes"] == 500
        assert result["protected"] is True

    def test_nested_backup_key_enriched(self, fake_client):
        fake_client.set_ws("backup/details", {
            "backup": {
                "slug": "b1",
                "agents": {"local": {"size": 500, "protected": True}},
            },
        })
        result = backup.details(fake_client, "b1")
        assert result["backup"]["size_bytes"] == 500
        assert result["backup"]["protected"] is True

    def test_empty_backup_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="backup_id is required"):
            backup.details(fake_client, "")

    def test_falls_back_to_slug_on_exception(self, fake_client):
        """When backup_id fails, slug is tried as fallback."""
        # Make the first ws_call raise, then return data for the second
        call_count = [0]
        original_ws = fake_client.ws_call

        def ws_call(msg_type, payload=None):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("not found")
            return {"slug": "b1", "agents": {"local": {"size": 300}}}

        fake_client.ws_call = ws_call
        result = backup.details(fake_client, "b1")
        assert result["size_bytes"] == 300
        assert call_count[0] == 2


# ── generate ─────────────────────────────────────────────────────────────────


class TestGenerate:
    def test_minimal_payload(self, fake_client):
        """HA requires agent_ids; with none given, every agent is used."""
        fake_client.set_ws("backup/agents/info", {"agents": [{"agent_id": "backup.local"}]})
        fake_client.set_ws("backup/generate", {"job_id": "job-1"})
        result = backup.generate(fake_client)
        assert result == {"job_id": "job-1"}
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["agent_ids"] == ["backup.local"]
        assert payload["include_database"] is True

    def test_full_payload(self, fake_client):
        fake_client.set_ws("backup/agents/info", {"agents": [{"agent_id": "backup.local"}]})
        fake_client.set_ws("backup/generate", {})
        backup.generate(
            fake_client,
            name="Weekly Backup",
            password="secret",
            addons_included=["core"],
            folders_included=["config"],
            database_included=False,
            agent_ids=["local"],
        )
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["name"] == "Weekly Backup"
        assert payload["password"] == "secret"
        assert payload["include_addons"] == ["core"]
        assert payload["include_folders"] == ["config"]
        assert payload["include_database"] is False
        assert payload["agent_ids"] == ["local"]

    def test_database_included_true_omitted(self, fake_client):
        """The database flag is sent as `include_database` — never as
        `database_included`, which HA rejects as an extra key."""
        fake_client.set_ws("backup/agents/info", {"agents": [{"agent_id": "backup.local"}]})
        fake_client.set_ws("backup/generate", {})
        backup.generate(fake_client, name="X")
        payload = fake_client.ws_calls[-1]["payload"]
        assert "database_included" not in payload
        assert payload["include_database"] is True

    def test_no_database_uses_include_database_false(self, fake_client):
        """--no-database sends include_database=False, not the old name."""
        fake_client.set_ws("backup/agents/info", {"agents": [{"agent_id": "backup.local"}]})
        fake_client.set_ws("backup/generate", {})
        backup.generate(fake_client, database_included=False)
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["include_database"] is False
        assert "database_included" not in payload

    def test_explicit_agent_ids_win(self, fake_client):
        """An explicit --agent is used verbatim, agents/info is not consulted."""
        fake_client.set_ws("backup/agents/info", {"agents": [{"agent_id": "backup.local"}]})
        fake_client.set_ws("backup/generate", {})
        backup.generate(fake_client, agent_ids=["backup.cloud"])
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["agent_ids"] == ["backup.cloud"]

    def test_all_agents_used_by_default(self, fake_client):
        """Without an explicit agent, EVERY configured agent is included."""
        fake_client.set_ws(
            "backup/agents/info",
            {"agents": [{"agent_id": "backup.local"}, {"agent_id": "backup.cloud"}]},
        )
        fake_client.set_ws("backup/generate", {})
        backup.generate(fake_client)
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["agent_ids"] == ["backup.local", "backup.cloud"]

    def test_no_agents_raises(self, fake_client):
        """No agents configured → a clear error, not a schema error from HA."""
        fake_client.set_ws("backup/agents/info", {"agents": []})
        with pytest.raises(ValueError, match="no backup agents"):
            backup.generate(fake_client)

    def test_empty_response_returns_empty_dict(self, fake_client):
        fake_client.set_ws("backup/agents/info", {"agents": [{"agent_id": "backup.local"}]})
        fake_client.set_ws("backup/generate", None)
        assert backup.generate(fake_client) == {}

    def test_legacy_schema_falls_back(self, fake_client):
        """HA older than 2025.1 rejects agent_ids/include_database — retry with
        the pre-2025 field names."""
        fake_client.set_ws("backup/agents/info", {"agents": [{"agent_id": "backup.local"}]})

        calls = []

        def ws_call(msg_type, payload=None):
            calls.append((msg_type, payload))
            if msg_type == "backup/agents/info":
                return {"agents": [{"agent_id": "backup.local"}]}
            if msg_type == "backup/generate" and "agent_ids" in (payload or {}):
                raise RuntimeError("extra keys not allowed @ data['agent_ids']")
            return {"ok": True}

        fake_client.ws_call = ws_call
        backup.generate(fake_client, database_included=False)
        legacy = calls[-1][1]
        assert "agent_ids" not in legacy
        assert "include_database" not in legacy
        assert legacy["database_included"] is False


# ── list_agent_ids ───────────────────────────────────────────────────────────


class TestListAgentIds:
    def test_dict_shape(self, fake_client):
        fake_client.set_ws("backup/agents/info", {"agents": [{"agent_id": "backup.local"}]})
        assert backup.list_agent_ids(fake_client) == ["backup.local"]

    def test_id_key_fallback(self, fake_client):
        fake_client.set_ws("backup/agents/info", {"agents": [{"id": "backup.cloud"}]})
        assert backup.list_agent_ids(fake_client) == ["backup.cloud"]

    def test_plain_strings(self, fake_client):
        fake_client.set_ws("backup/agents/info", {"agents": ["backup.local"]})
        assert backup.list_agent_ids(fake_client) == ["backup.local"]

    def test_bare_list_response(self, fake_client):
        fake_client.set_ws("backup/agents/info", ["backup.local"])
        assert backup.list_agent_ids(fake_client) == ["backup.local"]

    def test_empty(self, fake_client):
        fake_client.set_ws("backup/agents/info", {"agents": []})
        assert backup.list_agent_ids(fake_client) == []


# ── remove ───────────────────────────────────────────────────────────────────


class TestRemove:
    def test_delete_succeeds(self, fake_client):
        fake_client.set_ws("backup/delete", {"success": True})
        result = backup.remove(fake_client, "b1")
        assert result == {"success": True}
        assert fake_client.ws_calls[-1]["type"] == "backup/delete"
        assert fake_client.ws_calls[-1]["payload"] == {"backup_id": "b1"}

    def test_agent_ids_included(self, fake_client):
        fake_client.set_ws("backup/delete", {})
        backup.remove(fake_client, "b1", agent_ids=["local", "cloud"])
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["agent_ids"] == ["local", "cloud"]

    def test_falls_back_to_remove_on_exception(self, fake_client):
        """When backup/delete fails, backup/remove is tried."""
        call_count = [0]
        original_ws = fake_client.ws_call

        def ws_call(msg_type, payload=None):
            call_count[0] += 1
            if msg_type == "backup/delete":
                raise RuntimeError("not supported")
            return {"success": True}

        fake_client.ws_call = ws_call
        result = backup.remove(fake_client, "b1")
        assert result == {"success": True}
        assert call_count[0] == 2

    def test_both_fail_raises_runtime_error(self, fake_client):
        """When both backup/delete and backup/remove fail, RuntimeError is raised."""
        def ws_call(msg_type, payload=None):
            raise RuntimeError("not supported")

        fake_client.ws_call = ws_call
        with pytest.raises(RuntimeError, match="backup delete is not supported"):
            backup.remove(fake_client, "b1")

    def test_empty_backup_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="backup_id is required"):
            backup.remove(fake_client, "")


# ── restore ───────────────────────────────────────────────────────────────────


class TestRestore:
    def test_minimal_payload(self, fake_client):
        fake_client.set_ws("backup/restore", {"job_id": "j1"})
        result = backup.restore(fake_client, "b1")
        assert result == {"job_id": "j1"}
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload == {"backup_id": "b1"}

    def test_full_payload(self, fake_client):
        fake_client.set_ws("backup/restore", {})
        backup.restore(
            fake_client, "b1",
            password="pw",
            restore_database=False,
            restore_folders=["config"],
            restore_addons=["core"],
            agent_id="local",
        )
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["password"] == "pw"
        assert payload["restore_database"] is False
        assert payload["restore_folders"] == ["config"]
        assert payload["restore_addons"] == ["core"]
        assert payload["agent_id"] == "local"

    def test_restore_database_true_omitted(self, fake_client):
        """When restore_database is True (default), it's not in the payload."""
        fake_client.set_ws("backup/restore", {})
        backup.restore(fake_client, "b1")
        payload = fake_client.ws_calls[-1]["payload"]
        assert "restore_database" not in payload

    def test_empty_backup_id_raises(self, fake_client):
        with pytest.raises(ValueError, match="backup_id is required"):
            backup.restore(fake_client, "")

    def test_empty_response_returns_empty_dict(self, fake_client):
        fake_client.set_ws("backup/restore", None)
        assert backup.restore(fake_client, "b1") == {}


# ── agents_info ───────────────────────────────────────────────────────────────


class TestAgentsInfo:
    def test_returns_agents_list(self, fake_client):
        fake_client.set_ws("backup/agents/info", {
            "agents": [{"agent_id": "local"}, {"agent_id": "cloud"}],
        })
        result = backup.agents_info(fake_client)
        assert len(result) == 2
        assert result[0]["agent_id"] == "local"

    def test_empty_when_no_agents_key(self, fake_client):
        fake_client.set_ws("backup/agents/info", {})
        assert backup.agents_info(fake_client) == []

    def test_empty_when_response_not_dict(self, fake_client):
        fake_client.set_ws("backup/agents/info", "not a dict")
        assert backup.agents_info(fake_client) == []


# ── config_info ───────────────────────────────────────────────────────────────


class TestConfigInfo:
    def test_returns_config(self, fake_client):
        fake_client.set_ws("backup/config/info", {"schedule": "daily"})
        result = backup.config_info(fake_client)
        assert result == {"schedule": "daily"}

    def test_empty_response(self, fake_client):
        fake_client.set_ws("backup/config/info", None)
        assert backup.config_info(fake_client) == {}


# ── backup_info alias ─────────────────────────────────────────────────────────


class TestBackupInfoAlias:
    def test_backup_info_is_info(self):
        assert backup.backup_info is backup.info
