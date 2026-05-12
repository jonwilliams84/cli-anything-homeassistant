"""Unit tests for cli_anything.homeassistant.core.backup_advanced.

All tests use FakeClient from conftest.py — no real Home Assistant required.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import backup_advanced


# ---------------------------------------------------------------------------
# Shared fixtures / constants
# ---------------------------------------------------------------------------

BACKUP_ID = "abc123backup"
AGENT_ID = "backup.local"
PASSWORD = "s3cret"


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestBackupAdvanced:

    # ──────────────────────────────────────────────────── details

    def test_details_happy_path(self, fake_client):
        """details sends backup/details with backup_id payload."""
        fake_client.set_ws(
            "backup/details",
            {"backup": {"backup_id": BACKUP_ID, "name": "Morning backup"},
             "agent_errors": {}},
        )
        result = backup_advanced.details(fake_client, backup_id=BACKUP_ID)
        assert fake_client.ws_calls == [
            {"type": "backup/details", "payload": {"backup_id": BACKUP_ID}}
        ]

    def test_details_returns_dict(self, fake_client):
        """details always returns a dict."""
        fake_client.set_ws(
            "backup/details",
            {"backup": {"backup_id": BACKUP_ID}, "agent_errors": {}},
        )
        result = backup_advanced.details(fake_client, backup_id=BACKUP_ID)
        assert isinstance(result, dict)
        assert "backup" in result
        assert "agent_errors" in result

    def test_details_empty_backup_id_raises(self, fake_client):
        """details raises ValueError when backup_id is empty."""
        with pytest.raises(ValueError, match="backup_id"):
            backup_advanced.details(fake_client, backup_id="")

    def test_details_none_backup_id_raises(self, fake_client):
        """details raises ValueError when backup_id is None."""
        with pytest.raises(ValueError, match="backup_id"):
            backup_advanced.details(fake_client, backup_id=None)

    # ──────────────────────────────────────────────────── delete

    def test_delete_happy_path(self, fake_client):
        """delete sends backup/delete with backup_id."""
        fake_client.set_ws("backup/delete", {"agent_errors": {}})
        result = backup_advanced.delete(fake_client, backup_id=BACKUP_ID)
        assert fake_client.ws_calls == [
            {"type": "backup/delete", "payload": {"backup_id": BACKUP_ID}}
        ]

    def test_delete_returns_dict(self, fake_client):
        """delete returns a dict with agent_errors key on success."""
        fake_client.set_ws("backup/delete", {"agent_errors": {}})
        result = backup_advanced.delete(fake_client, backup_id=BACKUP_ID)
        assert isinstance(result, dict)
        assert result.get("agent_errors") == {}

    def test_delete_empty_backup_id_raises(self, fake_client):
        """delete raises ValueError when backup_id is empty."""
        with pytest.raises(ValueError, match="backup_id"):
            backup_advanced.delete(fake_client, backup_id="")

    # ──────────────────────────────────────────────────── restore

    def test_restore_happy_path_minimal(self, fake_client):
        """restore sends backup/restore with required fields only."""
        fake_client.set_ws("backup/restore", {})
        backup_advanced.restore(
            fake_client, backup_id=BACKUP_ID, agent_id=AGENT_ID
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "backup/restore"
        payload = call["payload"]
        assert payload["backup_id"] == BACKUP_ID
        assert payload["agent_id"] == AGENT_ID
        assert payload["restore_database"] is True
        assert payload["restore_homeassistant"] is True
        assert "password" not in payload

    def test_restore_happy_path_full(self, fake_client):
        """restore includes all optional fields when supplied."""
        fake_client.set_ws("backup/restore", {})
        backup_advanced.restore(
            fake_client,
            backup_id=BACKUP_ID,
            agent_id=AGENT_ID,
            password=PASSWORD,
            restore_addons=["addon_a", "addon_b"],
            restore_database=False,
            restore_folders=["media", "share"],
            restore_homeassistant=False,
        )
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["password"] == PASSWORD
        assert payload["restore_addons"] == ["addon_a", "addon_b"]
        assert payload["restore_database"] is False
        assert payload["restore_folders"] == ["media", "share"]
        assert payload["restore_homeassistant"] is False

    def test_restore_returns_dict(self, fake_client):
        """restore returns a dict."""
        fake_client.set_ws("backup/restore", {})
        result = backup_advanced.restore(
            fake_client, backup_id=BACKUP_ID, agent_id=AGENT_ID
        )
        assert isinstance(result, dict)

    def test_restore_empty_backup_id_raises(self, fake_client):
        """restore raises ValueError when backup_id is empty."""
        with pytest.raises(ValueError, match="backup_id"):
            backup_advanced.restore(fake_client, backup_id="", agent_id=AGENT_ID)

    def test_restore_empty_agent_id_raises(self, fake_client):
        """restore raises ValueError when agent_id is empty."""
        with pytest.raises(ValueError, match="agent_id"):
            backup_advanced.restore(
                fake_client, backup_id=BACKUP_ID, agent_id=""
            )

    # ──────────────────────────────────────────────────── generate_with_automatic_settings

    def test_generate_with_automatic_settings_happy_path(self, fake_client):
        """generate_with_automatic_settings sends backup/generate_with_automatic_settings."""
        fake_client.set_ws(
            "backup/generate_with_automatic_settings",
            {"backup_job_id": "job-42"},
        )
        backup_advanced.generate_with_automatic_settings(fake_client)
        assert fake_client.ws_calls == [
            {"type": "backup/generate_with_automatic_settings", "payload": {}}
        ]

    def test_generate_with_automatic_settings_returns_dict(self, fake_client):
        """generate_with_automatic_settings returns a dict."""
        fake_client.set_ws(
            "backup/generate_with_automatic_settings",
            {"backup_job_id": "job-42"},
        )
        result = backup_advanced.generate_with_automatic_settings(fake_client)
        assert isinstance(result, dict)
        assert result.get("backup_job_id") == "job-42"

    # ──────────────────────────────────────────────────── list_agents

    def test_list_agents_happy_path(self, fake_client):
        """list_agents sends backup/agents/info and returns agent list."""
        agents_payload = {"agents": [{"agent_id": "backup.local"}, {"agent_id": "backup.cloud"}]}
        fake_client.set_ws("backup/agents/info", agents_payload)
        result = backup_advanced.list_agents(fake_client)
        assert fake_client.ws_calls == [
            {"type": "backup/agents/info", "payload": {}}
        ]

    def test_list_agents_returns_list(self, fake_client):
        """list_agents unwraps the agents array from the response envelope."""
        agents = [{"agent_id": "backup.local"}, {"agent_id": "backup.google_drive"}]
        fake_client.set_ws("backup/agents/info", {"agents": agents})
        result = backup_advanced.list_agents(fake_client)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["agent_id"] == "backup.local"
        assert result[1]["agent_id"] == "backup.google_drive"

    def test_list_agents_empty_response(self, fake_client):
        """list_agents returns empty list when no agents are configured."""
        fake_client.set_ws("backup/agents/info", {"agents": []})
        result = backup_advanced.list_agents(fake_client)
        assert result == []

    # ──────────────────────────────────────────────────── get_config

    def test_get_config_happy_path(self, fake_client):
        """get_config sends backup/config/info."""
        config_data = {
            "config": {
                "schedule": {"state": "daily"},
                "retention": {"copies": 3, "days": None},
            }
        }
        fake_client.set_ws("backup/config/info", config_data)
        backup_advanced.get_config(fake_client)
        assert fake_client.ws_calls == [
            {"type": "backup/config/info", "payload": None}
        ]

    def test_get_config_returns_dict(self, fake_client):
        """get_config returns the full config dict including nested config key."""
        config_data = {
            "config": {
                "schedule": {"state": "daily"},
                "retention": {"copies": 3, "days": None},
            }
        }
        fake_client.set_ws("backup/config/info", config_data)
        result = backup_advanced.get_config(fake_client)
        assert isinstance(result, dict)
        assert "config" in result
        assert result["config"]["schedule"]["state"] == "daily"

    # ──────────────────────────────────────────────────── update_config

    def test_update_config_schedule(self, fake_client):
        """update_config sends backup/config/update with schedule payload."""
        fake_client.set_ws("backup/config/update", {})
        backup_advanced.update_config(
            fake_client, schedule={"state": "daily"}
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "backup/config/update"
        assert call["payload"]["schedule"] == {"state": "daily"}

    def test_update_config_retention(self, fake_client):
        """update_config sends retention dict correctly."""
        fake_client.set_ws("backup/config/update", {})
        backup_advanced.update_config(
            fake_client, retention={"copies": 5, "days": 30}
        )
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["retention"] == {"copies": 5, "days": 30}

    def test_update_config_create_backup(self, fake_client):
        """update_config sends create_backup settings dict."""
        fake_client.set_ws("backup/config/update", {})
        cb = {"agent_ids": [AGENT_ID], "include_database": True}
        backup_advanced.update_config(fake_client, create_backup=cb)
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["create_backup"] == cb

    def test_update_config_multiple_fields(self, fake_client):
        """update_config sends all supplied fields in one payload."""
        fake_client.set_ws("backup/config/update", {})
        backup_advanced.update_config(
            fake_client,
            schedule={"state": "weekly"},
            retention={"copies": 2, "days": None},
            automatic_backups_configured=True,
        )
        payload = fake_client.ws_calls[-1]["payload"]
        assert "schedule" in payload
        assert "retention" in payload
        assert payload["automatic_backups_configured"] is True

    def test_update_config_last_attempted(self, fake_client):
        """update_config sends last_attempted_automatic_backup timestamp."""
        fake_client.set_ws("backup/config/update", {})
        ts = "2026-05-11T03:00:00+00:00"
        backup_advanced.update_config(
            fake_client, last_attempted_automatic_backup=ts
        )
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["last_attempted_automatic_backup"] == ts

    def test_update_config_no_fields_raises(self, fake_client):
        """update_config raises ValueError when no fields are provided."""
        with pytest.raises(ValueError, match="at least one field"):
            backup_advanced.update_config(fake_client)

    def test_update_config_returns_dict(self, fake_client):
        """update_config returns a dict."""
        fake_client.set_ws("backup/config/update", {})
        result = backup_advanced.update_config(
            fake_client, schedule={"state": "daily"}
        )
        assert isinstance(result, dict)

    # ──────────────────────────────────────────────────── can_decrypt_on_download

    def test_can_decrypt_on_download_happy_path(self, fake_client):
        """can_decrypt_on_download sends correct WS payload."""
        fake_client.set_ws(
            "backup/can_decrypt_on_download", {"can_decrypt": True}
        )
        backup_advanced.can_decrypt_on_download(
            fake_client,
            backup_id=BACKUP_ID,
            agent_id=AGENT_ID,
            password=PASSWORD,
        )
        assert fake_client.ws_calls == [
            {
                "type": "backup/can_decrypt_on_download",
                "payload": {
                    "backup_id": BACKUP_ID,
                    "agent_id": AGENT_ID,
                    "password": PASSWORD,
                },
            }
        ]

    def test_can_decrypt_on_download_returns_dict(self, fake_client):
        """can_decrypt_on_download returns a dict with can_decrypt key."""
        fake_client.set_ws(
            "backup/can_decrypt_on_download", {"can_decrypt": True}
        )
        result = backup_advanced.can_decrypt_on_download(
            fake_client,
            backup_id=BACKUP_ID,
            agent_id=AGENT_ID,
            password=PASSWORD,
        )
        assert isinstance(result, dict)
        assert result.get("can_decrypt") is True

    def test_can_decrypt_empty_backup_id_raises(self, fake_client):
        """can_decrypt_on_download raises ValueError when backup_id is empty."""
        with pytest.raises(ValueError, match="backup_id"):
            backup_advanced.can_decrypt_on_download(
                fake_client, backup_id="", agent_id=AGENT_ID, password=PASSWORD
            )

    def test_can_decrypt_empty_agent_id_raises(self, fake_client):
        """can_decrypt_on_download raises ValueError when agent_id is empty."""
        with pytest.raises(ValueError, match="agent_id"):
            backup_advanced.can_decrypt_on_download(
                fake_client,
                backup_id=BACKUP_ID,
                agent_id="",
                password=PASSWORD,
            )

    def test_can_decrypt_empty_password_raises(self, fake_client):
        """can_decrypt_on_download raises ValueError when password is empty."""
        with pytest.raises(ValueError, match="password"):
            backup_advanced.can_decrypt_on_download(
                fake_client,
                backup_id=BACKUP_ID,
                agent_id=AGENT_ID,
                password="",
            )
