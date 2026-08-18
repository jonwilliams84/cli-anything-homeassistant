"""CLI wiring tests for the v1.50.0 refine pass (the fifth).

(Named _v5 because tests/test_cli_refine_wiring_v4.py belongs to v1.49.0.)

Covers every new command and every new flag, through CliRunner with a
FakeClient — so the assertions are about the CLI contract (option names, what
reaches the wire, exit codes, prompts) rather than about the core functions,
which `test_core_config.py`, `test_voice.py` and
`test_config_entry_discovery.py` own.

  system core-config / detect-location [--drift] / set-config [--apply]
  system check-config --direct
  tts list --raw / tts engine / tts voices
  assist prepare / stt-engines / wake-words
  config-entry get --direct / config-entry remove-device
  config-flow progress [--raw] / ignore / handlers
  lovelace config delete
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


def _invoke(runner, *args, json_out=True, input_text=None):
    full = ["--json"] + list(args) if json_out else list(args)
    return runner.invoke(
        cli_mod.cli,
        full,
        obj={
            "url": "http://x",
            "token": "t",
            "verify_ssl": False,
            "timeout": 5,
            "as_json": json_out,
            "config_path": None,
        },
        input=input_text,
    )


LIVE_CONFIG = {
    "latitude": 51.5,
    "longitude": -0.12,
    "elevation": 11,
    "location_name": "Home",
    "time_zone": "Europe/London",
    "unit_system": {"length": "km"},
    "currency": "GBP",
    "country": "GB",
    "language": "en-GB",
    "radius": 100,
    "external_url": None,
    "internal_url": "http://ha.local:8123",
    "components": ["sun"],
    "version": "2026.8.1",
}


# ──────────────────────────────────────────────────────────── system core config


class TestSystemCoreConfig:
    def test_core_config_shows_only_the_settable_keys(self, runner, fake_client):
        fake_client.set("GET", "config", dict(LIVE_CONFIG))
        r = _invoke(runner, "system", "core-config")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert "components" not in data
        assert data["time_zone"] == "Europe/London"

    def test_detect_location(self, runner, fake_client):
        fake_client.set_ws("config/core/detect", {"country": "GB"})
        r = _invoke(runner, "system", "detect-location")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["detected"] is True

    def test_detect_location_drift_compares_against_the_live_config(self, runner, fake_client):
        fake_client.set("GET", "config", dict(LIVE_CONFIG))
        fake_client.set_ws("config/core/detect", {"country": "FR"})
        r = _invoke(runner, "system", "detect-location", "--drift")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["drifted"] is True
        assert data["mismatches"][0]["key"] == "country"

    def test_set_config_is_a_dry_run_by_default(self, runner, fake_client):
        fake_client.set("GET", "config", dict(LIVE_CONFIG))
        r = _invoke(runner, "system", "set-config", "--time-zone", "Europe/Paris")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["applied"] is False
        assert fake_client.ws_calls == []

    def test_set_config_apply_writes(self, runner, fake_client):
        fake_client.set("GET", "config", dict(LIVE_CONFIG))
        r = _invoke(
            runner, "system", "set-config", "--elevation", "25", "--update-units", "--apply"
        )
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1] == {
            "type": "config/core/update",
            "payload": {"elevation": 25, "update_units": True},
        }

    def test_set_config_with_no_options_names_them_all(self, runner, fake_client):
        fake_client.set("GET", "config", dict(LIVE_CONFIG))
        r = _invoke(runner, "system", "set-config")
        assert r.exit_code == 1
        assert "--time-zone" in r.output

    def test_set_config_rejects_a_bad_unit_system_at_the_option_level(self, runner, fake_client):
        r = _invoke(runner, "system", "set-config", "--unit-system", "metrics")
        assert r.exit_code != 0
        assert "metrics" in r.output

    def test_set_config_check_first_refuses_to_write_onto_broken_yaml(self, runner, fake_client):
        fake_client.set("GET", "config", dict(LIVE_CONFIG))
        fake_client.set(
            "POST", "config/core/check_config",
            {"result": "invalid", "errors": "boom", "warnings": None},
        )
        r = _invoke(
            runner, "system", "set-config", "--latitude", "52", "--check-first", "--apply"
        )
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["applied"] is False and data["blocked_by"] == "check_config"
        assert fake_client.ws_calls == []

    def test_check_config_direct_uses_the_synchronous_endpoint(self, runner, fake_client):
        fake_client.set(
            "POST", "config/core/check_config",
            {"result": "valid", "errors": None, "warnings": "deprecated platform"},
        )
        r = _invoke(runner, "system", "check-config", "--direct")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["valid"] is True and data["has_warnings"] is True
        assert fake_client.calls[-1]["path"] == "config/core/check_config"

    def test_check_config_without_direct_keeps_the_old_service_route(self, runner, fake_client):
        fake_client.set_service("homeassistant", "check_config", {})
        fake_client.set("GET", "states/persistent_notification.config_check_failed", {})
        r = _invoke(runner, "system", "check-config", "--wait", "0.1")
        assert r.exit_code == 0, r.output
        assert any(c["domain"] == "homeassistant" for c in fake_client.service_calls)


# ──────────────────────────────────────────────────────────────────── voice stack


class TestVoiceWiring:
    def test_tts_list_raw_asks_ha_instead_of_walking_entities(self, runner, fake_client):
        fake_client.set_ws(
            "tts/engine/list",
            {"providers": [{"engine_id": "google_translate", "name": "G", "deprecated": True}]},
        )
        r = _invoke(runner, "tts", "list", "--raw")
        assert r.exit_code == 0, r.output
        rows = json.loads(r.output)
        assert rows[0]["kind"] == "legacy provider"

    def test_tts_list_default_still_walks_entities(self, runner, fake_client):
        fake_client.set("GET", "states", [])
        r = _invoke(runner, "tts", "list")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output) == []

    def test_tts_engine(self, runner, fake_client):
        fake_client.set_ws(
            "tts/engine/get",
            {"provider": {"engine_id": "tts.piper", "supported_languages": ["en_GB"]}},
        )
        r = _invoke(runner, "tts", "engine", "tts.piper")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["language_count"] == 1

    def test_tts_voices(self, runner, fake_client):
        fake_client.set_ws(
            "tts/engine/list",
            {"providers": [{"engine_id": "tts.piper", "supported_languages": ["en_GB"]}]},
        )
        fake_client.set_ws("tts/engine/voices", {"voices": [{"voice_id": "alan"}]})
        r = _invoke(runner, "tts", "voices", "tts.piper", "--language", "en_GB")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["count"] == 1

    def test_tts_voices_requires_a_language(self, runner, fake_client):
        r = _invoke(runner, "tts", "voices", "tts.piper")
        assert r.exit_code != 0
        assert "--language" in r.output

    def test_tts_voices_refuses_an_undeclared_language_cleanly(self, runner, fake_client):
        fake_client.set_ws(
            "tts/engine/list",
            {"providers": [{"engine_id": "tts.piper", "supported_languages": ["en_GB"]}]},
        )
        r = _invoke(runner, "tts", "voices", "tts.piper", "--language", "en-GB")
        assert r.exit_code == 1
        assert "does not declare" in r.output

    def test_tts_voices_no_check_language_sends_it_anyway(self, runner, fake_client):
        fake_client.set_ws(
            "tts/engine/list",
            {"providers": [{"engine_id": "tts.piper", "supported_languages": ["en_GB"]}]},
        )
        fake_client.set_ws("tts/engine/voices", {"voices": []})
        r = _invoke(
            runner, "tts", "voices", "tts.piper", "--language", "en-GB", "--no-check-language"
        )
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["type"] == "tts/engine/voices"

    def test_assist_stt_engines(self, runner, fake_client):
        fake_client.set_ws(
            "stt/engine/list",
            {"providers": [{"engine_id": "stt.whisper", "supported_languages": []}]},
        )
        r = _invoke(runner, "assist", "stt-engines", "--language", "en-GB")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)[0]["supports_requested_language"] is False

    def test_assist_wake_words(self, runner, fake_client):
        fake_client.set_ws("wake_word/info", {"wake_words": [{"id": "ok_nabu"}]})
        r = _invoke(runner, "assist", "wake-words", "wake_word.openwakeword")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["ids"] == ["ok_nabu"]

    def test_assist_wake_words_rejects_a_satellite_entity(self, runner, fake_client):
        r = _invoke(runner, "assist", "wake-words", "assist_satellite.kitchen")
        assert r.exit_code == 1
        assert "assist-satellite config" in r.output

    def test_assist_prepare(self, runner, fake_client):
        r = _invoke(runner, "assist", "prepare", "--agent", "conversation.home")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["prepared"] is True
        assert fake_client.ws_calls[-1]["payload"] == {"agent_id": "conversation.home"}


# ───────────────────────────────────────────────────────── config entries & flows


class TestConfigEntryWiring:
    def test_get_direct_asks_for_the_one_entry(self, runner, fake_client):
        fake_client.set_ws(
            "config_entries/get_single", {"config_entry": {"entry_id": "e1", "domain": "hue"}}
        )
        r = _invoke(runner, "config-entry", "get", "e1", "--direct")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["domain"] == "hue"
        assert [c["type"] for c in fake_client.ws_calls] == ["config_entries/get_single"]

    def test_get_without_direct_still_scans(self, runner, fake_client):
        fake_client.set_ws("config_entries/get", [{"entry_id": "e1", "domain": "hue"}])
        r = _invoke(runner, "config-entry", "get", "e1")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["type"] == "config_entries/get"

    def test_remove_device_prompts_without_yes(self, runner, fake_client):
        r = _invoke(
            runner, "config-entry", "remove-device", "e1", "d1", json_out=False, input_text="n\n"
        )
        assert r.exit_code == 0
        assert "aborted" in r.output
        assert fake_client.ws_calls == []

    def test_remove_device_with_yes(self, runner, fake_client):
        fake_client.set_ws("config/device_registry/remove_config_entry", {"id": "d1"})
        r = _invoke(runner, "config-entry", "remove-device", "e1", "d1", "--yes")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"] == {
            "config_entry_id": "e1",
            "device_id": "d1",
        }


class TestConfigFlowWiring:
    def test_progress_groups_by_what_it_means(self, runner, fake_client):
        fake_client.set_ws(
            "config_entries/flow/progress",
            [{"flow_id": "f", "handler": "hue", "context": {"source": "reauth"}}],
        )
        r = _invoke(runner, "config-flow", "progress")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["broken"] == 1

    def test_progress_raw_is_has_own_list(self, runner, fake_client):
        fake_client.set_ws(
            "config_entries/flow/progress",
            [{"flow_id": "f", "handler": "hue", "context": {"source": "reauth"}}],
        )
        r = _invoke(runner, "config-flow", "progress", "--raw")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)[0]["flow_id"] == "f"

    def test_ignore_needs_a_title(self, runner, fake_client):
        r = _invoke(runner, "config-flow", "ignore", "f1", "--yes")
        assert r.exit_code != 0
        assert "--title" in r.output

    def test_ignore_prompts_without_yes(self, runner, fake_client):
        r = _invoke(
            runner, "config-flow", "ignore", "f1", "--title", "Old thing",
            json_out=False, input_text="n\n",
        )
        assert r.exit_code == 0
        assert "aborted" in r.output
        assert fake_client.ws_calls == []

    def test_ignore_with_yes(self, runner, fake_client):
        r = _invoke(runner, "config-flow", "ignore", "f1", "--title", "Old thing", "--yes")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1] == {
            "type": "config_entries/ignore_flow",
            "payload": {"flow_id": "f1", "title": "Old thing"},
        }

    def test_handlers(self, runner, fake_client):
        fake_client.set("GET", "config/config_entries/flow_handlers", ["hue", "mqtt"])
        r = _invoke(runner, "config-flow", "handlers")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output) == ["hue", "mqtt"]

    def test_handlers_type_filter_is_constrained_to_has_values(self, runner, fake_client):
        r = _invoke(runner, "config-flow", "handlers", "--type", "nonsense")
        assert r.exit_code != 0
        assert "nonsense" in r.output

    def test_handlers_helper_filter(self, runner, fake_client):
        fake_client.set("GET", "config/config_entries/flow_handlers", ["input_boolean"])
        r = _invoke(runner, "config-flow", "handlers", "--type", "helper")
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["params"] == {"type": "helper"}


# ────────────────────────────────────────────────────────── lovelace config delete


class TestLovelaceConfigDeleteWiring:
    def test_it_prompts_without_yes(self, runner, fake_client):
        r = _invoke(runner, "lovelace", "config", "delete", "dash", json_out=False, input_text="n\n")
        assert r.exit_code != 0
        assert fake_client.ws_calls == []

    def test_with_yes_it_deletes_and_reports_the_snapshot(self, runner, fake_client, tmp_path):
        fake_client.set_ws("lovelace/config", {"views": []})
        r = _invoke(
            runner, "lovelace", "config", "delete", "dash", "--yes",
            "--snapshot-dir", str(tmp_path),
        )
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["deleted"] is True
        assert str(tmp_path) in data["snapshot"]
        assert fake_client.ws_calls[-1]["type"] == "lovelace/config/delete"
