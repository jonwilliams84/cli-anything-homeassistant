"""CLI wiring tests for the fourth refine pass.

Covers the three clusters added against a live 2026.8.1 instance:

  A  author-time   `target extract|services|triggers|conditions|slugify`
                   (`validate*` and `entity source` landed on main separately
                   as the `action` group — not duplicated here)
  B  bytes in/out  `backup download|upload`, `file upload`, `media upload|
                   search`, `image upload`, `tts get-url`, `intent handle`
  D  preferences   `labs list|show|set`, `prefs ai-task|http|entity-naming|
                   auto-entity-id|recorded`, `units device-classes|convertible`,
                   `device-links splits|split-for|linked`
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
    full = ["--json", *args] if json_out else list(args)
    return runner.invoke(
        cli_mod.cli,
        full,
        obj={
            "url": "http://x", "token": "t", "verify_ssl": False,
            "timeout": 5, "as_json": json_out, "config_path": None,
        },
        input=input_text,
    )


# ─────────────────────────────────────────────────────────── A: author-time


class TestTargetGroup:
    def test_extract_builds_the_target_from_repeatable_options(self, runner, fake_client):
        fake_client.set_ws("extract_from_target", {"referenced_entities": ["light.a"]})
        r = _invoke(runner, "target", "extract", "--area-id", "kitchen", "--area-id", "hall")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"]["target"] == {
            "area_id": ["kitchen", "hall"]
        }

    def test_an_empty_target_is_refused_with_every_option_named(self, runner, fake_client):
        r = _invoke(runner, "target", "extract")
        assert r.exit_code != 0
        assert "--label-id" in r.output

    @pytest.mark.parametrize(
        ("sub", "command"),
        [
            ("services", "get_services_for_target"),
            ("triggers", "get_triggers_for_target"),
            ("conditions", "get_conditions_for_target"),
        ],
    )
    def test_each_subcommand_reaches_its_own_ws_command(self, runner, fake_client, sub, command):
        fake_client.set_ws(command, [])
        r = _invoke(runner, "target", sub, "--entity-id", "sun.sun")
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["type"] == command

    def test_target_has_no_source_subcommand(self):
        """`entity source` landed on main while this was being written.

        Two commands for one websocket call is worse than either, so `target
        source` was dropped rather than shipped alongside it. This asserts the
        drop stuck — a re-added duplicate is easy to reintroduce by reflex.
        """
        assert "source" not in cli_mod.cli.commands["target"].commands
        assert "source" in cli_mod.cli.commands["entity"].commands

    def test_slugify(self, runner, fake_client):
        fake_client.set_ws("slugify", {"slug": "a_b"})
        r = _invoke(runner, "target", "slugify", "A B")
        assert json.loads(r.output)["slug"] == "a_b"


# ──────────────────────────────────────────────────────── B: bytes in / out


class _TransferClient:
    """FakeClient does not implement download/upload; this records them."""

    def __init__(self):
        self.downloads = []
        self.uploads = []

    def download(self, path, dest, params=None, chunk_size=None):
        self.downloads.append({"path": path, "dest": str(dest), "params": params})
        return {"path": str(dest), "bytes": 10, "size_matches": True}

    def upload(self, path, file_path, field="file", params=None, extra_fields=None,
               content_type=None):
        self.uploads.append({"path": path, "field": field, "params": params,
                             "extra_fields": extra_fields})
        return {"file_id": "abc", "id": "abc"}

    def ws_call(self, msg_type, payload=None):
        return {}


@pytest.fixture
def transfer_runner(monkeypatch):
    client = _TransferClient()
    monkeypatch.setattr(cli_mod, "make_client", lambda ctx: client)
    return CliRunner(), client


def _t_invoke(runner, *args):
    return runner.invoke(
        cli_mod.cli,
        ["--json", *args],
        obj={"url": "http://x", "token": "t", "verify_ssl": False,
             "timeout": 5, "as_json": True, "config_path": None},
    )


class TestTransferWiring:
    def test_backup_download_requires_an_agent_id(self, transfer_runner, tmp_path):
        runner, client = transfer_runner
        r = _t_invoke(runner, "backup", "download", "abc", str(tmp_path / "o.tar"))
        assert r.exit_code != 0
        assert "--agent-id" in r.output
        assert client.downloads == []

    def test_backup_download_reaches_the_right_url(self, transfer_runner, tmp_path):
        runner, client = transfer_runner
        r = _t_invoke(runner, "backup", "download", "abc", str(tmp_path / "o.tar"),
                      "--agent-id", "backup.local")
        assert r.exit_code == 0, r.output
        assert client.downloads[0]["path"] == "backup/download/abc"

    def test_backup_upload_repeats_agent_id(self, transfer_runner, tmp_path):
        runner, client = transfer_runner
        f = tmp_path / "b.tar"
        f.write_bytes(b"x")
        r = _t_invoke(runner, "backup", "upload", str(f),
                      "--agent-id", "a", "--agent-id", "b")
        assert r.exit_code == 0, r.output
        assert client.uploads[0]["params"] == [("agent_id", "a"), ("agent_id", "b")]

    def test_file_upload_uses_the_field_name_ha_demands(self, transfer_runner, tmp_path):
        runner, client = transfer_runner
        f = tmp_path / "cert.pem"
        f.write_text("x")
        r = _t_invoke(runner, "file", "upload", str(f))
        assert r.exit_code == 0, r.output
        assert client.uploads[0]["field"] == "file"
        assert client.uploads[0]["path"] == "file_upload"

    def test_media_upload_refuses_a_non_media_file_before_the_bare_400(
        self, transfer_runner, tmp_path
    ):
        runner, client = transfer_runner
        f = tmp_path / "notes.txt"
        f.write_text("x")
        r = _t_invoke(runner, "media", "upload", str(f), "--target", "media-source://x")
        assert r.exit_code != 0
        assert "image/*" in r.output
        assert client.uploads == []

    def test_image_upload(self, transfer_runner, tmp_path):
        runner, client = transfer_runner
        f = tmp_path / "a.png"
        f.write_bytes(b"\x89PNG")
        r = _t_invoke(runner, "image", "upload", str(f))
        assert r.exit_code == 0, r.output
        assert client.uploads[0]["path"] == "image/upload"


class TestTtsAndIntentWiring:
    def test_tts_get_url(self, runner, fake_client):
        fake_client.set("POST", "tts_get_url", {"url": "http://x/a.mp3", "path": "/a.mp3"})
        r = _invoke(runner, "tts", "get-url", "hello", "--engine-id", "tts.piper")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["url"] == "http://x/a.mp3"

    def test_tts_get_url_refuses_an_unsupported_language(self, runner, fake_client):
        fake_client.set_ws(
            "tts/engine/list",
            {"providers": [{"engine_id": "tts.piper", "supported_languages": ["en_GB"]}]},
        )
        r = _invoke(runner, "tts", "get-url", "hi", "--engine-id", "tts.piper",
                    "--language", "en-GB")
        assert r.exit_code != 0
        assert "en_GB" in r.output

    def test_intent_handle_parses_repeatable_slots(self, runner, fake_client):
        fake_client.set("POST", "intent/handle", {"response_type": "action_done"})
        r = _invoke(runner, "intent", "handle", "HassTurnOn",
                    "--slot", "name=kitchen", "--slot", "domain=light")
        assert r.exit_code == 0, r.output
        assert fake_client.calls[-1]["payload"]["data"] == {
            "name": "kitchen", "domain": "light"
        }

    def test_a_malformed_slot_is_refused(self, runner, fake_client):
        r = _invoke(runner, "intent", "handle", "HassTurnOn", "--slot", "nope")
        assert r.exit_code != 0
        assert "key=value" in r.output


# ─────────────────────────────────────────────────────────── D: preferences


class TestPreferenceWiring:
    def test_labs_list(self, runner, fake_client):
        fake_client.set_ws("labs/list", {"features": [
            {"domain": "frontend", "preview_feature": "winter_mode", "enabled": True}
        ]})
        r = _invoke(runner, "labs", "list")
        assert json.loads(r.output)[0]["preview_feature"] == "winter_mode"

    def test_labs_set_is_confirmation_gated(self, runner, fake_client):
        fake_client.set_ws("labs/list", {"features": [
            {"domain": "frontend", "preview_feature": "winter_mode", "enabled": False}
        ]})
        fake_client.set_ws("labs/update", {})
        declined = _invoke(runner, "labs", "set", "frontend", "winter_mode", "true",
                           input_text="n\n")
        assert declined.exit_code != 0
        assert not [c for c in fake_client.ws_calls if c["type"] == "labs/update"]

    def test_prefs_ai_task_reads_with_no_options(self, runner, fake_client):
        fake_client.set_ws("ai_task/preferences/get", {"gen_data_entity_id": "ai_task.x"})
        r = _invoke(runner, "prefs", "ai-task")
        assert json.loads(r.output)["gen_data_entity_id"] == "ai_task.x"
        assert not [c for c in fake_client.ws_calls if c["type"].endswith("/set")]

    def test_prefs_entity_naming_reads_without_prompting(self, runner, fake_client):
        """A read-only invocation must not prompt — that is how a gate gets a
        reputation for being in the way."""
        fake_client.set_ws("config/entity_registry/settings/get", {"entity_id_parts": None})
        r = _invoke(runner, "prefs", "entity-naming")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["is_default"] is True

    def test_prefs_entity_naming_prompts_before_writing(self, runner, fake_client):
        fake_client.set_ws("config/entity_registry/settings/get", {"entity_id_parts": None})
        fake_client.set_ws("config/entity_registry/settings/update", {"entity_id_parts": []})
        r = _invoke(runner, "prefs", "entity-naming", "--set-parts",
                    '["device","entity"]', json_out=False)
        assert r.exit_code != 0  # aborted: no input supplied to the prompt
        assert not [
            c for c in fake_client.ws_calls if c["type"].endswith("settings/update")
        ]

    def test_prefs_recorded(self, runner, fake_client):
        fake_client.set_ws("recorder/entity_options/get", {"recording_disabled_by": "user"})
        r = _invoke(runner, "prefs", "recorded", "sun.sun")
        assert json.loads(r.output)["explains_empty_history"] is True

    def test_device_links_split_for(self, runner, fake_client):
        fake_client.set_ws("config/device_registry/list_composite_splits", {
            "c1": {"primary_id": "d1", "split_ids": ["d1", "d2"]}
        })
        r = _invoke(runner, "device-links", "split-for", "d2")
        data = json.loads(r.output)
        assert data["is_split"] is True
        assert data["siblings"] == ["d1"]


class TestEveryNewGroupIsReachable:
    """A group that exists in the module and is not on `cli` is invisible.

    Cheap, and it is the failure a big single-file CLI actually has — a group
    defined but never attached looks fine in the source and does not exist.
    """

    @pytest.mark.parametrize(
        "group",
        ["target", "labs", "prefs", "device-links", "intent", "file"],
    )
    def test_group_is_registered(self, group):
        assert group in cli_mod.cli.commands, f"{group} is not wired onto `cli`"

    @pytest.mark.parametrize(
        ("group", "sub"),
        [
            ("backup", "download"), ("backup", "upload"),
            ("media", "upload"), ("media", "search"),
            ("image", "upload"), ("tts", "get-url"),
            ("media-player", "search"),
        ],
    )
    def test_subcommand_added_to_an_existing_group(self, group, sub):
        assert sub in cli_mod.cli.commands[group].commands
