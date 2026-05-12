"""Unit tests for cli_anything.homeassistant.core.diagnostics_dl."""

from __future__ import annotations

import json
import warnings

import pytest

from cli_anything.homeassistant.core import diagnostics_dl


class TestDiagnosticsDl:
    # ── download_config_entry_diagnostics ──────────────────────────────────
    # Route is /api/diagnostics/config_entry/{entry_id} (NO domain segment).
    # The buggy old form /api/diagnostics/config_entry/{domain}/{entry_id}
    # returned 404 in production — what this module fixes.

    def test_download_config_entry_happy(self, fake_client):
        payload = {"home_assistant": {}, "data": {"key": "value"}}
        fake_client.set("GET", "diagnostics/config_entry/abc123", payload)
        result = diagnostics_dl.download_config_entry_diagnostics(
            fake_client, entry_id="abc123",
        )
        assert result == payload
        last = fake_client.calls[-1]
        assert last["verb"] == "GET"
        # The correct URL — no domain segment.
        assert last["path"] == "diagnostics/config_entry/abc123"

    def test_download_config_entry_empty_entry_id(self, fake_client):
        with pytest.raises(ValueError, match="entry_id"):
            diagnostics_dl.download_config_entry_diagnostics(
                fake_client, entry_id="",
            )

    def test_download_config_entry_legacy_domain_warns(self, fake_client):
        """The legacy `domain` kwarg is accepted but emits DeprecationWarning."""
        fake_client.set("GET", "diagnostics/config_entry/eid-999",
                          {"ok": True})
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = diagnostics_dl.download_config_entry_diagnostics(
                fake_client, domain="zwave_js", entry_id="eid-999",
            )
        assert result == {"ok": True}
        # URL must NOT include the domain — even when passed.
        assert fake_client.calls[-1]["path"] == "diagnostics/config_entry/eid-999"
        assert any(
            issubclass(w.category, DeprecationWarning)
            and "domain" in str(w.message)
            for w in caught
        )

    def test_download_config_entry_return_shape(self, fake_client):
        payload = {"home_assistant": {"version": "2024.1.0"}, "data": {}}
        fake_client.set("GET", "diagnostics/config_entry/eid-999", payload)
        result = diagnostics_dl.download_config_entry_diagnostics(
            fake_client, entry_id="eid-999",
        )
        assert isinstance(result, dict)
        assert "home_assistant" in result

    # ── download_device_diagnostics ────────────────────────────────────────

    def test_download_device_happy(self, fake_client):
        payload = {"home_assistant": {}, "data": {"device": "info"}}
        fake_client.set(
            "GET", "diagnostics/config_entry/abc123/device/dev-456", payload,
        )
        result = diagnostics_dl.download_device_diagnostics(
            fake_client, entry_id="abc123", device_id="dev-456",
        )
        assert result == payload
        assert fake_client.calls[-1]["path"] == (
            "diagnostics/config_entry/abc123/device/dev-456"
        )

    def test_download_device_empty_entry_id(self, fake_client):
        with pytest.raises(ValueError, match="entry_id"):
            diagnostics_dl.download_device_diagnostics(
                fake_client, entry_id="", device_id="dev-456",
            )

    def test_download_device_empty_device_id(self, fake_client):
        with pytest.raises(ValueError, match="device_id"):
            diagnostics_dl.download_device_diagnostics(
                fake_client, entry_id="abc123", device_id="",
            )

    def test_download_device_legacy_domain_warns(self, fake_client):
        fake_client.set(
            "GET", "diagnostics/config_entry/eid-1/device/dv-1",
            {"data": {"serial": "X1"}},
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = diagnostics_dl.download_device_diagnostics(
                fake_client, domain="matter", entry_id="eid-1",
                device_id="dv-1",
            )
        assert "data" in result
        assert fake_client.calls[-1]["path"] == (
            "diagnostics/config_entry/eid-1/device/dv-1"
        )
        assert any(
            issubclass(w.category, DeprecationWarning) for w in caught
        )

    def test_download_device_return_shape(self, fake_client):
        payload = {"home_assistant": {"version": "2024.1.0"},
                     "data": {"serial": "X1"}}
        fake_client.set(
            "GET", "diagnostics/config_entry/eid-1/device/dv-1", payload,
        )
        result = diagnostics_dl.download_device_diagnostics(
            fake_client, entry_id="eid-1", device_id="dv-1",
        )
        assert isinstance(result, dict)
        assert "data" in result

    # ── save_diagnostics_to_file ───────────────────────────────────────────

    def test_save_writes_file_and_returns_byte_count(self, tmp_path):
        data = {"home_assistant": {"version": "2024.1.0"}, "data": {"x": 1}}
        out = tmp_path / "diag.json"
        n = diagnostics_dl.save_diagnostics_to_file(data, str(out))
        assert out.exists()
        assert n > 0
        loaded = json.loads(out.read_text())
        assert loaded == data

    def test_save_returns_correct_byte_count(self, tmp_path):
        data = {"a": "b"}
        out = tmp_path / "small.json"
        n = diagnostics_dl.save_diagnostics_to_file(data, str(out))
        written = len(json.dumps(data, indent=2, default=str).encode("utf-8"))
        assert n == written

    def test_save_empty_path_raises(self):
        with pytest.raises(ValueError, match="path"):
            diagnostics_dl.save_diagnostics_to_file({"x": 1}, "")

    def test_save_pretty_json(self, tmp_path):
        data = {"nested": {"key": "val"}}
        out = tmp_path / "pretty.json"
        diagnostics_dl.save_diagnostics_to_file(data, str(out))
        text = out.read_text()
        assert "\n" in text
        assert "  " in text
