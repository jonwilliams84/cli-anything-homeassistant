"""CLI wiring tests for the `action` group and `entity source`.

Covers the script-engine refine pass: `action run` (sequence / shorthand /
dry-run), `action validate`, `action validate-automation`,
`action validate-script`, `action test-condition` and `entity source`.
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


def _invoke(runner, *args, json_out=True):
    full = ["--json"] + list(args) if json_out else list(args)
    return runner.invoke(
        cli_mod.cli,
        full,
        obj={
            "url": "http://x", "token": "t", "verify_ssl": False,
            "timeout": 5, "as_json": json_out, "config_path": None,
        },
    )


def _write(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload))
    return str(path)


# ─────────────────────────────────────────────────────────────────── action run

class TestActionRun:
    def test_sequence_inline(self, runner, fake_client):
        fake_client.set_ws("execute_script", {"context": {"id": "c1"}, "response": None})
        r = _invoke(
            runner, "action", "run",
            "--sequence", '[{"action": "light.turn_on"}]',
        )
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["context"]["id"] == "c1"
        assert fake_client.ws_calls[-1] == {
            "type": "execute_script",
            "payload": {"sequence": [{"action": "light.turn_on"}]},
        }

    def test_sequence_from_file(self, runner, fake_client, tmp_path):
        fake_client.set_ws("execute_script", {"context": {}, "response": None})
        path = _write(tmp_path, "seq.json", [{"delay": {"seconds": 1}}])
        r = _invoke(runner, "action", "run", "--sequence-file", path)
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"]["sequence"] == [{"delay": {"seconds": 1}}]

    def test_service_shorthand_with_data_and_target(self, runner, fake_client):
        fake_client.set_ws("execute_script", {"context": {}, "response": None})
        r = _invoke(
            runner, "action", "run",
            "--service", "light.turn_on",
            "-t", "entity_id=light.kitchen",
            "-d", "brightness=200",
        )
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"]["sequence"] == [
            {
                "action": "light.turn_on",
                "target": {"entity_id": "light.kitchen"},
                "data": {"brightness": 200},
            }
        ]

    def test_response_variable_and_variables(self, runner, fake_client):
        fake_client.set_ws("execute_script", {"response": {"agenda": {}}})
        r = _invoke(
            runner, "action", "run",
            "--service", "calendar.get_events",
            "-t", "entity_id=calendar.home",
            "--response-variable", "agenda",
            "--var", "room=hall",
        )
        assert r.exit_code == 0, r.output
        payload = fake_client.ws_calls[-1]["payload"]
        assert payload["sequence"][0]["response_variable"] == "agenda"
        assert payload["variables"] == {"room": "hall"}

    def test_dry_run_does_not_call_ws(self, runner, fake_client):
        r = _invoke(
            runner, "action", "run",
            "--service", "light.turn_off",
            "-t", "entity_id=light.x",
            "--dry-run",
        )
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["dry_run"] is True
        assert data["ws"] == "execute_script"
        assert data["payload"]["sequence"][0]["action"] == "light.turn_off"
        assert fake_client.ws_calls == []

    def test_service_and_sequence_conflict(self, runner):
        r = _invoke(
            runner, "action", "run",
            "--service", "a.b", "--sequence", "[]",
        )
        assert r.exit_code != 0
        assert "either --service" in r.output

    def test_data_without_service_rejected(self, runner):
        r = _invoke(
            runner, "action", "run",
            "--sequence", '[{"action": "a.b"}]', "-d", "x=1",
        )
        assert r.exit_code != 0
        assert "require --service" in r.output

    def test_missing_input_rejected(self, runner):
        r = _invoke(runner, "action", "run")
        assert r.exit_code != 0
        assert "--sequence" in r.output

    def test_invalid_json_rejected(self, runner):
        r = _invoke(runner, "action", "run", "--sequence", "{not json}")
        assert r.exit_code != 0
        assert "not valid JSON" in r.output

    def test_inline_and_file_conflict(self, runner, tmp_path):
        path = _write(tmp_path, "seq.json", [{"action": "a.b"}])
        r = _invoke(
            runner, "action", "run",
            "--sequence", "[]", "--sequence-file", path,
        )
        assert r.exit_code != 0
        assert "only one of" in r.output

    def test_bad_service_name_surfaces_error(self, runner):
        r = _invoke(runner, "action", "run", "--service", "lightturnon")
        assert r.exit_code != 0


# ────────────────────────────────────────────────────────────── action validate

class TestActionValidate:
    def test_actions_only(self, runner, fake_client):
        fake_client.set_ws("validate_config", {"actions": {"valid": True, "error": None}})
        r = _invoke(
            runner, "action", "validate",
            "--actions", '[{"action": "light.turn_on"}]',
        )
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["actions"]["valid"] is True
        assert set(fake_client.ws_calls[-1]["payload"]) == {"actions"}

    def test_all_blocks_from_files(self, runner, fake_client, tmp_path):
        fake_client.set_ws("validate_config", {})
        t = _write(tmp_path, "t.json", [{"trigger": "state"}])
        c = _write(tmp_path, "c.json", [{"condition": "sun"}])
        a = _write(tmp_path, "a.json", [{"action": "light.turn_on"}])
        r = _invoke(
            runner, "action", "validate",
            "--triggers-file", t, "--conditions-file", c, "--actions-file", a,
        )
        assert r.exit_code == 0, r.output
        assert set(fake_client.ws_calls[-1]["payload"]) == {
            "triggers", "conditions", "actions",
        }

    def test_no_blocks_rejected(self, runner):
        r = _invoke(runner, "action", "validate")
        assert r.exit_code != 0
        assert "at least one" in r.output


class TestActionValidateAutomation:
    def test_valid_exits_zero(self, runner, fake_client, tmp_path):
        fake_client.set_ws(
            "validate_config",
            {
                "triggers": {"valid": True, "error": None},
                "actions": {"valid": True, "error": None},
            },
        )
        path = _write(
            tmp_path, "auto.json",
            {
                "alias": "Test",
                "trigger": [{"trigger": "state", "entity_id": "sun.sun"}],
                "action": [{"action": "light.turn_on"}],
            },
        )
        r = _invoke(runner, "action", "validate-automation", path)
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["valid"] is True
        # legacy singular keys were upgraded before the WS call
        assert set(fake_client.ws_calls[-1]["payload"]) == {"triggers", "actions"}

    def test_invalid_exits_nonzero_with_reason(self, runner, fake_client, tmp_path):
        fake_client.set_ws(
            "validate_config",
            {"triggers": {"valid": False, "error": "Invalid trigger 'stat'"}},
        )
        path = _write(tmp_path, "auto.json", {"triggers": [{"trigger": "stat"}]})
        r = _invoke(runner, "action", "validate-automation", path)
        assert r.exit_code != 0
        assert "Invalid trigger 'stat'" in r.output

    def test_config_without_blocks_errors(self, runner, fake_client, tmp_path):
        path = _write(tmp_path, "auto.json", {"alias": "nothing"})
        r = _invoke(runner, "action", "validate-automation", path)
        assert r.exit_code != 0


class TestActionValidateScript:
    def test_valid(self, runner, fake_client, tmp_path):
        fake_client.set_ws("validate_config", {"actions": {"valid": True, "error": None}})
        path = _write(
            tmp_path, "s.json",
            {"alias": "Bedtime", "sequence": [{"action": "light.turn_off"}]},
        )
        r = _invoke(runner, "action", "validate-script", path)
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["valid"] is True

    def test_invalid_exits_nonzero(self, runner, fake_client, tmp_path):
        fake_client.set_ws(
            "validate_config", {"actions": {"valid": False, "error": "boom"}}
        )
        path = _write(tmp_path, "s.json", {"sequence": [{"action": "nope"}]})
        r = _invoke(runner, "action", "validate-script", path)
        assert r.exit_code != 0
        assert "boom" in r.output


# ─────────────────────────────────────────────────────── action test-condition

class TestActionTestCondition:
    def test_true_condition(self, runner, fake_client):
        fake_client.set_ws("test_condition", {"result": True})
        r = _invoke(
            runner, "action", "test-condition",
            "--condition", '{"condition": "state", "entity_id": "sun.sun"}',
        )
        assert r.exit_code == 0, r.output
        assert json.loads(r.output) == {"result": True}

    def test_false_condition_without_exit_code_flag(self, runner, fake_client):
        fake_client.set_ws("test_condition", {"result": False})
        r = _invoke(runner, "action", "test-condition", "--condition", '{"condition": "sun"}')
        assert r.exit_code == 0, r.output
        assert json.loads(r.output) == {"result": False}

    def test_false_condition_with_exit_code_flag(self, runner, fake_client):
        fake_client.set_ws("test_condition", {"result": False})
        r = _invoke(
            runner, "action", "test-condition",
            "--condition", '{"condition": "sun"}', "--exit-code",
        )
        assert r.exit_code == 1

    def test_true_condition_with_exit_code_flag(self, runner, fake_client):
        fake_client.set_ws("test_condition", {"result": True})
        r = _invoke(
            runner, "action", "test-condition",
            "--condition", '{"condition": "sun"}', "--exit-code",
        )
        assert r.exit_code == 0, r.output

    def test_list_of_conditions_reports_each(self, runner, fake_client):
        fake_client.set_ws("test_condition", {"result": True})
        r = _invoke(
            runner, "action", "test-condition",
            "--condition", '[{"condition": "sun"}, {"condition": "state"}]',
        )
        assert r.exit_code == 0, r.output
        rows = json.loads(r.output)
        assert [row["index"] for row in rows] == [0, 1]

    def test_variables_forwarded(self, runner, fake_client):
        fake_client.set_ws("test_condition", {"result": True})
        r = _invoke(
            runner, "action", "test-condition",
            "--condition", '{"condition": "template"}', "--var", "x=1",
        )
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"]["variables"] == {"x": 1}

    def test_condition_from_file(self, runner, fake_client, tmp_path):
        fake_client.set_ws("test_condition", {"result": True})
        path = _write(tmp_path, "cond.json", {"condition": "sun", "after": "sunset"})
        r = _invoke(runner, "action", "test-condition", "--condition-file", path)
        assert r.exit_code == 0, r.output
        assert fake_client.ws_calls[-1]["payload"]["condition"]["after"] == "sunset"

    def test_missing_condition_rejected(self, runner):
        r = _invoke(runner, "action", "test-condition")
        assert r.exit_code != 0


# ────────────────────────────────────────────────────────────────  entity source

SOURCES = {
    "light.kitchen": {"domain": "hue"},
    "light.hall": {"domain": "hue"},
    "sun.sun": {"domain": "sun"},
}


class TestEntitySourceCommand:
    def test_full_map(self, runner, fake_client):
        fake_client.set_ws("entity/source", SOURCES)
        r = _invoke(runner, "entity", "source")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output) == SOURCES

    def test_single_entity(self, runner, fake_client):
        fake_client.set_ws("entity/source", SOURCES)
        r = _invoke(runner, "entity", "source", "sun.sun")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output) == {
            "entity_id": "sun.sun", "loaded": True, "domain": "sun",
        }

    def test_unknown_entity_marked_not_loaded(self, runner, fake_client):
        fake_client.set_ws("entity/source", SOURCES)
        r = _invoke(runner, "entity", "source", "light.ghost")
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert data["loaded"] is False and data["source"] is None

    def test_by_integration(self, runner, fake_client):
        fake_client.set_ws("entity/source", SOURCES)
        r = _invoke(runner, "entity", "source", "--by-integration")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output) == {
            "hue": ["light.hall", "light.kitchen"], "sun": ["sun.sun"],
        }

    def test_integration_filter(self, runner, fake_client):
        fake_client.set_ws("entity/source", SOURCES)
        r = _invoke(runner, "entity", "source", "-i", "sun")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output) == {"sun": ["sun.sun"]}

    def test_bad_entity_id_errors(self, runner, fake_client):
        fake_client.set_ws("entity/source", SOURCES)
        r = _invoke(runner, "entity", "source", "kitchen")
        assert r.exit_code != 0


# ────────────────────────────────────────────────────────────── plain (non-json)

class TestPlainOutput:
    def test_action_run_plain(self, runner, fake_client):
        fake_client.set_ws("execute_script", {"context": {"id": "c1"}, "response": None})
        r = _invoke(
            runner, "action", "run", "--service", "light.toggle",
            "-t", "entity_id=light.x", json_out=False,
        )
        assert r.exit_code == 0, r.output
        assert "context" in r.output

    def test_entity_source_plain(self, runner, fake_client):
        fake_client.set_ws("entity/source", SOURCES)
        r = _invoke(runner, "entity", "source", "sun.sun", json_out=False)
        assert r.exit_code == 0, r.output
        assert "domain: sun" in r.output


class TestHelpSurface:
    def test_action_group_listed_in_root_help(self):
        r = CliRunner().invoke(cli_mod.cli, ["--help"])
        assert r.exit_code == 0
        assert "action" in r.output

    @pytest.mark.parametrize(
        "cmd",
        ["run", "validate", "validate-automation", "validate-script", "test-condition"],
    )
    def test_subcommands_listed(self, cmd):
        r = CliRunner().invoke(cli_mod.cli, ["action", "--help"])
        assert r.exit_code == 0
        assert cmd in r.output

    def test_entity_source_listed(self):
        r = CliRunner().invoke(cli_mod.cli, ["entity", "--help"])
        assert r.exit_code == 0
        assert "source" in r.output
