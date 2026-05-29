"""v6 refine — regression tests for the safety + bug-fix pass.

Covers:
  * whoami fix (now calls auth_tokens.current_user, not auth.current_user)
  * WS subscription sends unsubscribe_events on exit
  * entity prune --protect-user-disabled honoured even with --entity-id
  * mqtt subscribe doesn't buffer when streaming to --out
  * project.py token write uses O_CREAT mode 0600 from the start
  * automation/script save: --dry-run prints diff; --yes bypasses prompt
  * lovelace card insert/delete have --dry-run
  * lovelace card insert/replace/section set/view set/add auto-validate;
    --no-validate bypasses
  * lovelace config save requires --yes for scripted use
  * shopping-list/todo remove + clear-completed prompt without --yes
  * system reload-core-config / reload-all prompt without --yes
  * state delete is wired
  * domain helpers now accept valve/lock/lawn_mower/alarm_control_panel/group
  * tag create / tag delete
  * services.call_service uses params= not hand-built query
  * history: --no-attributes / --significant-changes-only flags
  * event subscribe --filter filters client-side
"""

from __future__ import annotations

import os
import stat
import threading
from unittest import mock
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli_anything.homeassistant import homeassistant_cli as cli_mod
from cli_anything.homeassistant.core import (
    domain as domain_core,
    history as history_core,
    project,
    services as services_core,
    states as states_core,
    tags as tags_core,
)


# ─── helpers ──────────────────────────────────────────────────────────────

def _invoke(runner, *args, json_out=True, fake_client=None):
    full = (["--json"] if json_out else []) + list(args)
    obj = {
        "url": "http://x", "token": "t", "verify_ssl": False,
        "timeout": 5, "as_json": json_out, "config_path": None,
    }
    if fake_client is not None:
        with mock.patch.object(cli_mod, "make_client",
                                  return_value=fake_client):
            return runner.invoke(cli_mod.cli, full, obj=obj)
    return runner.invoke(cli_mod.cli, full, obj=obj)


@pytest.fixture
def runner():
    return CliRunner()


# ─── 1. whoami fix ────────────────────────────────────────────────────────

class TestWhoamiFix:
    def test_whoami_calls_auth_tokens_current_user(self, runner, fake_client):
        fake_client.set_ws("auth/current_user", {
            "id": "abc", "name": "agent", "is_admin": True,
        })
        r = _invoke(runner, "whoami", fake_client=fake_client)
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["type"] == "auth/current_user"

    def test_auth_module_does_not_have_current_user(self):
        from cli_anything.homeassistant.core import auth as auth_core
        assert not hasattr(auth_core, "current_user"), (
            "auth.current_user should not exist; whoami uses auth_tokens.current_user"
        )

    def test_auth_tokens_module_has_current_user(self):
        from cli_anything.homeassistant.core import auth_tokens as auth_tokens_core
        assert hasattr(auth_tokens_core, "current_user")


# ─── 2. WS unsubscribe on exit ────────────────────────────────────────────

class TestWsUnsubscribeOnExit:
    def test_ws_subscribe_sends_unsubscribe_before_close(self):
        """ws_subscribe should send {'type': 'unsubscribe_events', ...}
        before closing the socket so the HA server isn't left tracking
        a dangling subscription."""
        from cli_anything.homeassistant.utils import homeassistant_backend as backend
        sent: list[dict] = []
        recv_queue = [
            '{"type": "auth_required"}',
            '{"type": "auth_ok"}',
        ]

        class FakeWS:
            def __init__(self):
                self._closed = False
            def recv(self):
                if recv_queue:
                    return recv_queue.pop(0)
                raise backend.websocket.WebSocketTimeoutException()  # type: ignore[attr-defined]
            def send(self, msg):
                import json as _json
                sent.append(_json.loads(msg))
            def settimeout(self, _): pass
            def close(self): self._closed = True

        stop = threading.Event()
        stop.set()  # immediate stop
        client = backend.HomeAssistantClient(url="http://x", token="tok")
        with mock.patch.object(backend.websocket, "create_connection",
                                  return_value=FakeWS()):
            client.ws_subscribe("subscribe_events", None,
                                  lambda evt: None, stop)
        # The last sent message must be an unsubscribe_events with the
        # subscription id of the original subscribe.
        unsub = [m for m in sent if m.get("type") == "unsubscribe_events"]
        assert len(unsub) == 1, f"expected 1 unsubscribe, got {sent!r}"
        # The subscription id matches the subscribe id.
        subs = [m for m in sent if m.get("type") == "subscribe_events"]
        assert len(subs) == 1
        assert unsub[0]["subscription"] == subs[0]["id"]


# ─── 3. entity prune --protect-user-disabled honoured with --entity-id ────

class TestEntityPruneProtect:
    def test_user_disabled_entity_skipped_even_with_explicit_entity_id(self, runner):
        from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantClient
        client = mock.MagicMock(spec=HomeAssistantClient)
        # Registry contains one user-disabled entry
        with mock.patch("cli_anything.homeassistant.core.registry.list_entities",
                          return_value=[
                              {"entity_id": "light.user_off", "disabled_by": "user"},
                              {"entity_id": "light.normal", "disabled_by": None},
                          ]), \
              mock.patch("cli_anything.homeassistant.core.registry.bulk_remove_entities",
                          return_value={"total": 1, "removed": ["light.normal"],
                                         "failed": [], "dry_run": True}) as bulk:
            with mock.patch.object(cli_mod, "make_client", return_value=client):
                r = runner.invoke(cli_mod.cli, [
                    "--json", "entity", "prune",
                    "--entity-id", "light.user_off",
                    "--entity-id", "light.normal",
                ], obj={"url": "x", "token": "t", "verify_ssl": False,
                         "timeout": 5, "as_json": True, "config_path": None})
        assert r.exit_code == 0, r.output
        # bulk_remove_entities should have been called with ONLY light.normal —
        # user_off was filtered by --protect-user-disabled (default on).
        assert bulk.call_args.kwargs["entity_ids"] == ["light.normal"]


# ─── 4. mqtt subscribe streaming-only ─────────────────────────────────────

class TestMqttSubscribeBuffering:
    def test_streaming_to_file_does_not_buffer(self, runner, tmp_path,
                                                  subscribing_client):
        out_path = tmp_path / "msgs.jsonl"
        # Pre-queue 5 fake messages
        for i in range(5):
            subscribing_client.queue_events({"topic": "t", "payload": f"m{i}"})
        # JSON mode + --out → buffer_messages must be False
        r = _invoke(runner, "mqtt", "subscribe", "test/topic",
                     "--out", str(out_path), "--limit", "5",
                     fake_client=subscribing_client)
        assert r.exit_code == 0, r.output
        # File got all messages
        assert out_path.exists()
        lines = out_path.read_text().strip().splitlines()
        assert len(lines) == 5
        # Stdout JSON document indicates streamed-only (no buffered list)
        import json
        out = json.loads(r.output)
        assert out.get("streamed_only") is True
        assert out.get("received") == 5


# ─── 5. project.py token write race ───────────────────────────────────────

class TestProjectFilePerms:
    def test_save_config_creates_file_with_mode_0600(self, tmp_path):
        path = tmp_path / "cfg.json"
        # Permissive umask to prove O_CREAT mode 0600 takes effect
        old = os.umask(0o000)
        try:
            project.save_config(url="http://x", token="t", config_path=path)
        finally:
            os.umask(old)
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600, oct(mode)


# ─── 6. automation/script save: --dry-run + --yes ────────────────────────

class TestAutomationSaveSafety:
    def test_dry_run_emits_diff_and_does_not_save(self, runner, fake_client,
                                                      tmp_path):
        body = tmp_path / "new.json"
        body.write_text('{"trigger": [], "action": []}')
        fake_client.set_ws("config/automation/config/foo", {"trigger": [{"x": 1}]})
        # Mock the underlying get_config + save_config so we can assert
        with mock.patch("cli_anything.homeassistant.core.automation.get_config",
                          return_value={"trigger": [{"x": 1}], "action": []}), \
              mock.patch("cli_anything.homeassistant.core.automation.save_config") as save:
            r = _invoke(runner, "automation", "save", "automation.foo",
                         str(body), "--dry-run", fake_client=fake_client)
        assert r.exit_code == 0, r.output
        assert save.call_count == 0
        import json
        out = json.loads(r.output)
        assert out["dry_run"] is True
        assert "diff" in out

    def test_yes_bypasses_prompt(self, runner, fake_client, tmp_path):
        body = tmp_path / "new.json"
        body.write_text('{"trigger": [], "action": []}')
        with mock.patch("cli_anything.homeassistant.core.automation.save_config",
                          return_value={"ok": True}) as save:
            r = _invoke(runner, "automation", "save", "automation.foo",
                         str(body), "--yes", fake_client=fake_client)
        assert r.exit_code == 0, r.output
        assert save.call_count == 1

    def test_without_yes_or_dry_run_aborts_on_closed_stdin(self, runner,
                                                              fake_client,
                                                              tmp_path):
        body = tmp_path / "new.json"
        body.write_text('{"trigger": [], "action": []}')
        # Closed stdin → click.confirm raises Abort → ClickException
        with mock.patch("cli_anything.homeassistant.core.automation.save_config") as save:
            r = _invoke(runner, "automation", "save", "automation.foo",
                         str(body), fake_client=fake_client)
        assert r.exit_code != 0
        assert save.call_count == 0


# ─── 7. lovelace card insert/delete have --dry-run ────────────────────────

class TestLovelaceCardSafety:
    def test_card_insert_has_dry_run_in_help(self, runner):
        r = runner.invoke(cli_mod.cli, ["lovelace", "card", "insert", "--help"])
        assert r.exit_code == 0
        assert "--dry-run" in r.output
        assert "--no-validate" in r.output

    def test_card_delete_has_dry_run_in_help(self, runner):
        r = runner.invoke(cli_mod.cli, ["lovelace", "card", "delete", "--help"])
        assert r.exit_code == 0
        assert "--dry-run" in r.output


# ─── 8. lovelace_card_validate is wired ──────────────────────────────────

class TestLovelaceValidationWired:
    def test_validate_helper_blocks_on_errors(self):
        """_validate_card_or_abort raises ClickException on error-level issues."""
        import click as _click
        bad_card = {"type": "custom:does-not-exist-anywhere"}
        # Force the validator to claim the resource is NOT installed
        with mock.patch(
            "cli_anything.homeassistant.core.lovelace_card_validate.installed_card_types",
            return_value=set(),
        ):
            with pytest.raises(_click.ClickException, match="lovelace validation failed"):
                cli_mod._validate_card_or_abort(
                    bad_card, client=mock.MagicMock(), skip=False,
                )

    def test_validate_helper_skipped_when_flag_set(self):
        bad_card = {"type": "custom:does-not-exist-anywhere"}
        # skip=True → no validation, returns None
        cli_mod._validate_card_or_abort(bad_card, client=mock.MagicMock(), skip=True)


# ─── 9. lovelace config save requires --yes ──────────────────────────────

class TestLovelaceConfigSaveSafety:
    def test_help_mentions_yes(self, runner):
        r = runner.invoke(cli_mod.cli, ["lovelace", "config", "save", "--help"])
        assert r.exit_code == 0
        assert "--yes" in r.output
        assert "--dry-run" in r.output


# ─── 10. shopping-list / todo confirmation prompts ───────────────────────

class TestShoppingListTodoConfirmation:
    def test_shopping_list_remove_prompts(self, runner, fake_client):
        # No --yes → confirmation_option aborts on closed stdin
        r = _invoke(runner, "shopping-list", "remove", "abc",
                     fake_client=fake_client)
        assert r.exit_code != 0

    def test_shopping_list_remove_with_yes_proceeds(self, runner, fake_client):
        fake_client.set_ws("shopping_list/items/remove", {"ok": True})
        r = _invoke(runner, "shopping-list", "remove", "abc", "--yes",
                     fake_client=fake_client)
        assert r.exit_code == 0, r.output

    def test_todo_remove_prompts(self, runner, fake_client):
        r = _invoke(runner, "todo", "remove", "todo.list", "Bread",
                     fake_client=fake_client)
        assert r.exit_code != 0

    def test_todo_clear_completed_prompts(self, runner, fake_client):
        r = _invoke(runner, "todo", "clear-completed", "todo.list",
                     fake_client=fake_client)
        assert r.exit_code != 0


# ─── 11. system reload confirmations ──────────────────────────────────────

class TestSystemReloadConfirmation:
    def test_reload_core_config_prompts(self, runner, fake_client):
        r = _invoke(runner, "system", "reload-core-config",
                     fake_client=fake_client)
        assert r.exit_code != 0

    def test_reload_all_prompts(self, runner, fake_client):
        r = _invoke(runner, "system", "reload-all",
                     fake_client=fake_client)
        assert r.exit_code != 0


# ─── 12. state delete ─────────────────────────────────────────────────────

class TestStateDelete:
    def test_state_delete_core(self, fake_client):
        states_core.delete_state(fake_client, "sensor.foo")
        last = fake_client.calls[-1]
        assert last["verb"] == "DELETE"
        assert last["path"] == "states/sensor.foo"

    def test_state_delete_empty_id_raises(self, fake_client):
        with pytest.raises(ValueError):
            states_core.delete_state(fake_client, "")

    def test_state_delete_cli_with_yes(self, runner, fake_client):
        r = _invoke(runner, "state", "delete", "sensor.foo", "--yes",
                     fake_client=fake_client)
        assert r.exit_code == 0, r.output

    def test_state_delete_cli_without_yes_prompts(self, runner, fake_client):
        r = _invoke(runner, "state", "delete", "sensor.foo",
                     fake_client=fake_client)
        assert r.exit_code != 0


# ─── 13. domain helpers accept new toggleable domains ─────────────────────

class TestToggleableDomains:
    @pytest.mark.parametrize("domain", [
        "valve", "lock", "lawn_mower", "alarm_control_panel", "group",
    ])
    def test_new_domain_in_whitelist(self, domain, fake_client):
        # No ValueError raised → domain is whitelisted
        domain_core.turn_on(fake_client, domain, entity_id=f"{domain}.x")
        domain_core.turn_off(fake_client, domain, entity_id=f"{domain}.x")
        domain_core.toggle(fake_client, domain, entity_id=f"{domain}.x")


# ─── 14. tag create / delete ──────────────────────────────────────────────

class TestTagCrud:
    def test_tag_create(self, fake_client):
        fake_client.set_ws("tag/create", {"id": "nfc-1"})
        tags_core.create(fake_client, "nfc-1", name="Front Door")
        last = fake_client.ws_calls[-1]
        assert last["type"] == "tag/create"
        assert last["payload"] == {"tag_id": "nfc-1", "name": "Front Door"}

    def test_tag_create_empty_id_raises(self, fake_client):
        with pytest.raises(ValueError):
            tags_core.create(fake_client, "")

    def test_tag_delete(self, fake_client):
        fake_client.set_ws("tag/delete", {"ok": True})
        tags_core.delete(fake_client, "nfc-1")
        last = fake_client.ws_calls[-1]
        assert last["type"] == "tag/delete"
        assert last["payload"] == {"tag_id": "nfc-1"}

    def test_tag_delete_empty_id_raises(self, fake_client):
        with pytest.raises(ValueError):
            tags_core.delete(fake_client, "")


# ─── 15. services.call_service uses params= ─────────────────────────────-

class TestServicesParams:
    def test_return_response_in_params_not_path(self, fake_client):
        services_core.call_service(
            fake_client, "calendar", "get_events", return_response=True,
        )
        last = fake_client.calls[-1]
        assert last["path"] == "services/calendar/get_events"
        assert last["params"] == {"return_response": "true"}

    def test_no_return_response_no_params(self, fake_client):
        services_core.call_service(fake_client, "light", "turn_on")
        last = fake_client.calls[-1]
        assert last["path"] == "services/light/turn_on"
        # When return_response=False, params should be None / not present
        assert last.get("params") is None


# ─── 16. history flags ────────────────────────────────────────────────────

class TestHistoryFlags:
    def test_no_attributes_in_params(self, fake_client):
        history_core.history(fake_client, no_attributes=True)
        last = fake_client.calls[-1]
        assert "no_attributes" in last["params"]

    def test_significant_changes_only_in_params(self, fake_client):
        history_core.history(fake_client, significant_changes_only=True)
        last = fake_client.calls[-1]
        assert "significant_changes_only" in last["params"]

    def test_default_behavior_unchanged(self, fake_client):
        history_core.history(fake_client)
        last = fake_client.calls[-1]
        # Defaults: minimal_response=True only.
        assert "minimal_response" in last["params"]
        assert "no_attributes" not in last["params"]
        assert "significant_changes_only" not in last["params"]


# ─── 17. event subscribe --filter client-side filtering ───────────────────

class TestEventSubscribeFilter:
    def test_filter_matches(self, runner, subscribing_client):
        subscribing_client.queue_events(
            {"data": {"entity_id": "sensor.outdoor_temperature", "value": 1}},
            {"data": {"entity_id": "sensor.indoor_temperature", "value": 2}},
            {"data": {"entity_id": "sensor.outdoor_temperature", "value": 3}},
        )
        r = _invoke(runner, "event", "subscribe", "state_changed",
                     "--limit", "10",
                     "--filter", "data.entity_id=sensor.outdoor_temperature",
                     fake_client=subscribing_client)
        assert r.exit_code == 0, r.output
        import json
        out = json.loads(r.output)
        # Only the two outdoor entries match
        assert len(out) == 2
        for ev in out:
            assert ev["data"]["entity_id"] == "sensor.outdoor_temperature"

    def test_filter_malformed_aborts(self, runner, subscribing_client):
        r = _invoke(runner, "event", "subscribe", "state_changed",
                     "--filter", "missing-equals",
                     fake_client=subscribing_client)
        assert r.exit_code != 0
