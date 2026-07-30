"""Unit tests for cli_anything.homeassistant.core.lovelace.

Covers the uncovered error paths, validation branches, snapshot
file I/O, and resource CRUD that the existing suite never exercised.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from cli_anything.homeassistant.core import lovelace


# ────────────────────────────────────────────────────────── helpers


class _RecordingClient:
    """Minimal client that records ws_call invocations and returns canned data.

    Supports a sequence of responses: if ws_responses is a list, each ws_call
    pops the next response. Otherwise the same response is returned every time.
    """

    def __init__(self, ws_response=None, ws_responses=None):
        self.ws_calls: list[dict] = []
        self._ws_response = ws_response
        self._ws_responses = ws_responses
        self._ws_idx = 0

    def ws_call(self, msg_type, payload=None):
        self.ws_calls.append({"type": msg_type, "payload": payload})
        if self._ws_responses is not None:
            resp = self._ws_responses[self._ws_idx]
            self._ws_idx += 1
            if isinstance(resp, Exception):
                raise resp
            return resp
        if isinstance(self._ws_response, Exception):
            raise self._ws_response
        return self._ws_response


# ────────────────────────────────────────────────────────── dashboards


class TestCreateDashboard:
    def test_requires_url_path(self):
        with pytest.raises(ValueError, match="url_path is required"):
            lovelace.create_dashboard(_RecordingClient(), "", "Title")

    def test_requires_title(self):
        with pytest.raises(ValueError, match="title is required"):
            lovelace.create_dashboard(_RecordingClient(), "mobile", "")

    def test_minimal_payload_omits_optional_fields(self):
        client = _RecordingClient(ws_response={"id": "1"})
        lovelace.create_dashboard(client, "mobile", "Mobile")
        call = client.ws_calls[0]
        assert call["type"] == "lovelace/dashboards/create"
        payload = call["payload"]
        assert payload["url_path"] == "mobile"
        assert payload["title"] == "Mobile"
        assert payload["mode"] == "storage"
        assert "icon" not in payload
        assert "filename" not in payload

    def test_includes_icon_and_filename_when_provided(self):
        client = _RecordingClient(ws_response={"id": "1"})
        lovelace.create_dashboard(
            client, "yaml-dash", "YAML Dash",
            mode="yaml", icon="mdi:view-dashboard", filename="dash.yaml",
        )
        payload = client.ws_calls[0]["payload"]
        assert payload["icon"] == "mdi:view-dashboard"
        assert payload["filename"] == "dash.yaml"
        assert payload["mode"] == "yaml"


class TestUpdateDashboard:
    def test_requires_dashboard_id(self):
        with pytest.raises(ValueError, match="dashboard_id is required"):
            lovelace.update_dashboard(_RecordingClient(), "")

    def test_requires_at_least_one_field(self):
        with pytest.raises(ValueError, match="at least one updatable field"):
            lovelace.update_dashboard(_RecordingClient(), "abc")

    def test_filters_disallowed_and_none_fields(self):
        client = _RecordingClient(ws_response={})
        lovelace.update_dashboard(
            client, "abc",
            title="New Title",
            icon=None,            # should be skipped (None)
            bogus="nope",         # should be skipped (not in allowed set)
            show_in_sidebar=True,
        )
        payload = client.ws_calls[0]["payload"]
        assert payload["dashboard_id"] == "abc"
        assert payload["title"] == "New Title"
        assert payload["show_in_sidebar"] is True
        assert "icon" not in payload
        assert "bogus" not in payload


class TestDeleteDashboard:
    def test_requires_dashboard_id(self):
        with pytest.raises(ValueError, match="dashboard_id is required"):
            lovelace.delete_dashboard(_RecordingClient(), "")

    def test_sends_delete_payload(self):
        client = _RecordingClient(ws_response={})
        lovelace.delete_dashboard(client, "dash-1")
        assert client.ws_calls[0] == {
            "type": "lovelace/dashboards/delete",
            "payload": {"dashboard_id": "dash-1"},
        }


# ────────────────────────────────────────────────────────── config save


class TestSaveDashboardConfig:
    def test_requires_url_path(self):
        with pytest.raises(ValueError, match="url_path is required"):
            lovelace.save_dashboard_config(_RecordingClient(), "", {"a": 1})

    def test_requires_dict_config(self):
        with pytest.raises(ValueError, match="config must be a dict"):
            lovelace.save_dashboard_config(_RecordingClient(), "mobile", "not a dict")

    def test_save_without_snapshot(self):
        client = _RecordingClient(ws_response={})
        lovelace.save_dashboard_config(client, "mobile", {"views": []})
        assert client.ws_calls[0]["type"] == "lovelace/config/save"
        assert client.ws_calls[0]["payload"] == {
            "url_path": "mobile", "config": {"views": []},
        }

    def test_save_with_snapshot_writes_file(self, tmp_path):
        """Snapshot=True writes a JSON file of the pre-save config."""
        client = _RecordingClient(ws_response={"views": [{"title": "old"}]})
        lovelace.save_dashboard_config(
            client, "mobile", {"views": [{"title": "new"}]},
            snapshot=True, snapshot_dir=str(tmp_path),
        )
        files = list(tmp_path.glob("mobile-*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["url_path"] == "mobile"
        assert data["config"] == {"views": [{"title": "old"}]}

    def test_save_with_snapshot_failure_still_saves(self, tmp_path):
        """If reading current config fails, the save still proceeds."""
        # First ws_call (get_dashboard_config) raises, second (save) returns {}.
        client = _RecordingClient(ws_responses=[RuntimeError("connection lost"), {}])
        lovelace.save_dashboard_config(
            client, "mobile", {"views": []},
            snapshot=True, snapshot_dir=str(tmp_path),
        )
        # The save ws_call should still have been made.
        assert client.ws_calls[-1]["type"] == "lovelace/config/save"
        # The snapshot file should contain the error placeholder.
        files = list(tmp_path.glob("mobile-*.json"))
        assert len(files) == 1
        snap = json.loads(files[0].read_text())
        assert "_error" in snap["config"]


# ────────────────────────────────────────────────────────── snapshots


class TestSnapshotDashboard:
    def test_snapshot_uses_lovelace_key_for_none_url(self, tmp_path):
        client = _RecordingClient(ws_response={"views": []})
        path = lovelace.snapshot_dashboard(
            client, url_path=None, snapshot_dir=str(tmp_path),
        )
        assert Path(path).exists()
        assert Path(path).name.startswith("lovelace-")

    def test_snapshot_uses_url_path_as_key(self, tmp_path):
        client = _RecordingClient(ws_response={"views": []})
        path = lovelace.snapshot_dashboard(
            client, url_path="mobile", snapshot_dir=str(tmp_path),
        )
        assert Path(path).exists()
        assert Path(path).name.startswith("mobile-")


class TestListSnapshots:
    def test_returns_empty_for_missing_dir(self, tmp_path):
        result = lovelace.list_snapshots(snapshot_dir=str(tmp_path / "nonexistent"))
        assert result == []

    def test_lists_and_filters_by_url_path(self, tmp_path):
        # Create two snapshots for "mobile" and one for "tablet".
        for ts in ["20250101-120000", "20250102-130000"]:
            (tmp_path / f"mobile-{ts}.json").write_text(
                json.dumps({"url_path": "mobile", "timestamp": ts, "config": {}})
            )
        (tmp_path / "tablet-20250101-140000.json").write_text(
            json.dumps({"url_path": "tablet", "timestamp": "20250101-140000", "config": {}})
        )
        # Also a non-json file that should be ignored.
        (tmp_path / "readme.txt").write_text("ignore me")

        all_snaps = lovelace.list_snapshots(snapshot_dir=str(tmp_path))
        assert len(all_snaps) == 3

        mobile_only = lovelace.list_snapshots(snapshot_dir=str(tmp_path), url_path="mobile")
        assert len(mobile_only) == 2
        assert all(s["url_path"] == "mobile" for s in mobile_only)

    def test_parses_timestamp_from_filename(self, tmp_path):
        (tmp_path / "mobile-20250101-120000.json").write_text(
            json.dumps({"config": {}})
        )
        snaps = lovelace.list_snapshots(snapshot_dir=str(tmp_path))
        assert snaps[0]["timestamp"] == "20250101-120000"
        assert snaps[0]["url_path"] == "mobile"
        assert snaps[0]["bytes"] > 0

    def test_malformed_filename_still_listed(self, tmp_path):
        """A file without the expected timestamp pattern is still listed."""
        (tmp_path / "no-timestamp.json").write_text("{}")
        snaps = lovelace.list_snapshots(snapshot_dir=str(tmp_path))
        assert len(snaps) == 1
        assert snaps[0]["url_path"] == "no-timestamp"
        assert snaps[0]["timestamp"] == ""


class TestRestoreSnapshot:
    def test_restores_config_to_ws_call(self, tmp_path):
        snap_path = tmp_path / "mobile-20250101-120000.json"
        snap_path.write_text(json.dumps({
            "url_path": "mobile", "config": {"views": [{"title": "restored"}]},
        }))
        client = _RecordingClient(ws_response={})
        lovelace.restore_dashboard_snapshot(client, str(snap_path))
        assert client.ws_calls[0] == {
            "type": "lovelace/config/save",
            "payload": {"url_path": "mobile", "config": {"views": [{"title": "restored"}]}},
        }

    def test_raises_for_missing_config(self, tmp_path):
        snap_path = tmp_path / "bad.json"
        snap_path.write_text(json.dumps({"url_path": "mobile"}))
        with pytest.raises(ValueError, match="has no .config. dict"):
            lovelace.restore_dashboard_snapshot(_RecordingClient(), str(snap_path))

    def test_raises_when_no_url_path_and_no_override(self, tmp_path):
        snap_path = tmp_path / "lovelace-20250101-120000.json"
        snap_path.write_text(json.dumps({
            "url_path": "lovelace", "config": {"views": []},
        }))
        with pytest.raises(ValueError, match="snapshot has no url_path"):
            lovelace.restore_dashboard_snapshot(_RecordingClient(), str(snap_path))

    def test_url_path_override_takes_precedence(self, tmp_path):
        snap_path = tmp_path / "mobile-20250101-120000.json"
        snap_path.write_text(json.dumps({
            "url_path": "mobile", "config": {"views": []},
        }))
        client = _RecordingClient(ws_response={})
        lovelace.restore_dashboard_snapshot(
            client, str(snap_path), url_path_override="tablet",
        )
        assert client.ws_calls[0]["payload"]["url_path"] == "tablet"


# ────────────────────────────────────────────────────────── resources


class TestResources:
    def test_list_resources_returns_list(self):
        client = _RecordingClient(ws_response=[{"id": "r1"}, {"id": "r2"}])
        result = lovelace.list_resources(client)
        assert result == [{"id": "r1"}, {"id": "r2"}]

    def test_list_resources_non_list_returns_empty(self):
        client = _RecordingClient(ws_response={"not": "a list"})
        assert lovelace.list_resources(client) == []

    def test_delete_resource_requires_id(self):
        with pytest.raises(ValueError, match="resource_id is required"):
            lovelace.delete_resource(_RecordingClient(), "")

    def test_create_resource_requires_url(self):
        with pytest.raises(ValueError, match="url is required"):
            lovelace.create_resource(_RecordingClient(), "")

    def test_create_resource_sends_payload(self):
        client = _RecordingClient(ws_response={})
        lovelace.create_resource(client, "https://example.com/card.js", "module")
        assert client.ws_calls[0] == {
            "type": "lovelace/resources/create",
            "payload": {"url": "https://example.com/card.js", "res_type": "module"},
        }

    def test_update_resource_requires_id(self):
        with pytest.raises(ValueError, match="resource_id is required"):
            lovelace.update_resource(_RecordingClient(), "", "https://example.com/card.js")

    def test_update_resource_sends_payload(self):
        client = _RecordingClient(ws_response={})
        lovelace.update_resource(client, "r1", "https://example.com/v2.js", "css")
        assert client.ws_calls[0] == {
            "type": "lovelace/resources/update",
            "payload": {"resource_id": "r1", "url": "https://example.com/v2.js", "res_type": "css"},
        }


# ────────────────────────────────────────────────────────── list dashboards


class TestListDashboards:
    def test_returns_list(self):
        client = _RecordingClient(ws_response=[{"id": "d1"}])
        assert lovelace.list_dashboards(client) == [{"id": "d1"}]

    def test_non_list_returns_empty(self):
        client = _RecordingClient(ws_response={"not": "a list"})
        assert lovelace.list_dashboards(client) == []


class TestGetDashboardConfig:
    def test_no_url_path_sends_empty_payload(self):
        client = _RecordingClient(ws_response={"views": []})
        lovelace.get_dashboard_config(client)
        assert client.ws_calls[0] == {"type": "lovelace/config", "payload": {}}

    def test_with_url_path_sends_it(self):
        client = _RecordingClient(ws_response={"views": []})
        lovelace.get_dashboard_config(client, "mobile")
        assert client.ws_calls[0] == {"type": "lovelace/config", "payload": {"url_path": "mobile"}}
