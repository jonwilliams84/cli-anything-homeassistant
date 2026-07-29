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
        fake_client.set_ws("backup/generate", {"job_id": "job-1"})
        result = backup.generate(fake_client)
        assert result == {"job_id": "job-1"}
        # Payload should be empty when no options given
        assert fake_client.ws_calls[-1]["payload"] == {}

    def test_full_payload(self, fake_client):
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
        assert payload["addons_included"] == ["core"]
        assert payload["folders_included"] == ["config"]
        assert payload["database_included"] is False
        assert payload["agent_ids"] == ["local"]

    def test_database_included_true_omitted(self, fake_client):
        """When database_included is True (default), it's not in the payload."""
        fake_client.set_ws("backup/generate", {})
        backup.generate(fake_client, name="X")
        payload = fake_client.ws_calls[-1]["payload"]
        assert "database_included" not in payload

    def test_empty_response_returns_empty_dict(self, fake_client):
        fake_client.set_ws("backup/generate", None)
        assert backup.generate(fake_client) == {}


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
