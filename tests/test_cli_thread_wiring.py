"""CLI wiring for the `thread` group (+ `thread otbr`) and the argv hoister.

Two things are asserted here:

  * every option reaches the core function — a flag that parses and is then
    dropped is the failure these catch;
  * `main()`'s global-flag hoisting no longer steals an option the SUBCOMMAND
    declares. `thread routers --timeout 2.5` used to die with "'2.5' is not a
    valid integer" because the root's int `--timeout` grabbed it.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from cli_anything.homeassistant import homeassistant_cli as cli_mod
from tests.test_thread_network import ENTRY, OTHER, TLV


@pytest.fixture
def runner(monkeypatch, fake_client):
    monkeypatch.setattr(cli_mod, "make_client", lambda ctx: fake_client)
    return CliRunner()


@pytest.fixture
def stocked(fake_client):
    fake_client.set_ws("thread/list_datasets", {"datasets": [ENTRY, OTHER]})
    fake_client.set_ws("thread/get_dataset_tlv", {"tlv": TLV})
    return fake_client


def _invoke(runner, *args, json_out=True, **kwargs):
    full = ["--json"] + list(args) if json_out else list(args)
    return runner.invoke(
        cli_mod.cli,
        full,
        obj={
            "url": "http://x", "token": "t", "verify_ssl": False,
            "timeout": 5, "as_json": json_out, "config_path": None,
        },
        **kwargs,
    )


class TestDatasets:
    def test_datasets_lists_and_marks_the_preferred(self, runner, stocked):
        r = _invoke(runner, "thread", "datasets")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["preferred"] == ENTRY["dataset_id"]

    def test_a_missing_integration_is_exit_zero(self, runner, fake_client):
        fake_client.set_ws_error("thread/list_datasets", "unknown_command", "")
        r = _invoke(runner, "thread", "datasets")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["available"] is False


class TestDataset:
    def test_the_credentials_are_redacted_by_default(self, runner, stocked):
        r = _invoke(runner, "thread", "dataset", ENTRY["dataset_id"])
        assert r.exit_code == 0, r.output
        assert "00112233445566778899aabbccddeeff" not in r.output
        assert json.loads(r.output)["tlv"] is None

    def test_reveal_prints_the_key(self, runner, stocked):
        r = _invoke(runner, "thread", "dataset", ENTRY["dataset_id"], "--reveal")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["tlv"] == TLV

    def test_an_unknown_id_is_a_clean_error_not_a_traceback(self, runner, fake_client):
        fake_client.set_ws_error("thread/get_dataset_tlv", "not_found", "unknown dataset")
        r = _invoke(runner, "thread", "dataset", "nope")
        assert r.exit_code != 0
        assert "No Thread dataset with id" in r.output
        assert "Traceback" not in r.output


class TestDecode:
    def test_decode_talks_to_nothing(self, runner, fake_client):
        r = _invoke(runner, "thread", "decode", TLV)
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["network_name"] == "HarnessNet"
        assert fake_client.ws_calls == []

    def test_decode_reveal(self, runner, fake_client):
        r = _invoke(runner, "thread", "decode", TLV, "--reveal")
        assert json.loads(r.output)["tlv"] == TLV


class TestAddDataset:
    def test_exactly_one_source_of_the_tlv_is_required(self, runner, stocked, tmp_path):
        r = _invoke(runner, "thread", "add-dataset")
        assert r.exit_code != 0
        assert "exactly one" in r.output

    def test_both_at_once_is_refused(self, runner, stocked, tmp_path):
        path = tmp_path / "ds.txt"
        path.write_text(TLV)
        r = _invoke(runner, "thread", "add-dataset", "--tlv", TLV, "--tlv-file", str(path))
        assert r.exit_code != 0
        assert "exactly one" in r.output

    def test_a_tlv_file_keeps_the_credential_out_of_argv(self, runner, stocked, tmp_path):
        path = tmp_path / "ds.txt"
        path.write_text(f"{TLV}\n")
        r = _invoke(runner, "thread", "add-dataset", "--tlv-file", str(path))
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["predicted"] == "unchanged"

    def test_dry_run_is_the_default(self, runner, stocked):
        r = _invoke(runner, "thread", "add-dataset", "--tlv", TLV)
        assert json.loads(r.output)["applied"] is False
        assert "thread/add_dataset_tlv" not in [c["type"] for c in stocked.ws_calls]

    def test_apply_and_source_are_forwarded(self, runner, stocked):
        r = _invoke(
            runner, "thread", "add-dataset", "--tlv", TLV, "--source", "mine", "--apply"
        )
        assert r.exit_code == 0, r.output
        sent = next(c for c in stocked.ws_calls if c["type"] == "thread/add_dataset_tlv")
        assert sent["payload"]["source"] == "mine"


class TestMutations:
    def test_delete_is_dry_run_by_default(self, runner, stocked):
        r = _invoke(runner, "thread", "delete-dataset", OTHER["dataset_id"])
        assert json.loads(r.output)["applied"] is False

    def test_delete_apply_calls_ha(self, runner, stocked):
        _invoke(runner, "thread", "delete-dataset", OTHER["dataset_id"], "--apply")
        assert "thread/delete_dataset" in [c["type"] for c in stocked.ws_calls]

    def test_deleting_the_preferred_dataset_is_a_named_refusal(self, runner, stocked):
        r = _invoke(runner, "thread", "delete-dataset", ENTRY["dataset_id"], "--apply")
        assert r.exit_code != 0
        assert "PREFERRED" in r.output

    def test_set_preferred_apply_forwards_the_id(self, runner, stocked):
        _invoke(runner, "thread", "set-preferred", OTHER["dataset_id"], "--apply")
        sent = next(c for c in stocked.ws_calls if c["type"] == "thread/set_preferred_dataset")
        assert sent["payload"] == {"dataset_id": OTHER["dataset_id"]}

    def test_set_border_agent_requires_the_extended_address(self, runner, stocked):
        r = _invoke(runner, "thread", "set-border-agent", ENTRY["dataset_id"])
        assert r.exit_code != 0
        assert "--extended-address" in r.output

    def test_set_border_agent_forwards_all_three(self, runner, stocked):
        _invoke(
            runner,
            "thread",
            "set-border-agent",
            ENTRY["dataset_id"],
            "--extended-address",
            "1122334455667788",
            "--border-agent-id",
            "aabb",
            "--apply",
        )
        sent = next(
            c for c in stocked.ws_calls if c["type"] == "thread/set_preferred_border_agent"
        )
        assert sent["payload"] == {
            "dataset_id": ENTRY["dataset_id"],
            "border_agent_id": "aabb",
            "extended_address": "1122334455667788",
        }


class TestRoutersAndAudit:
    def test_routers_forwards_the_window(self, monkeypatch, runner, fake_client):
        seen = {}

        def fake_discover(client, *, timeout, max_routers, **kwargs):
            seen.update(timeout=timeout, max_routers=max_routers)
            return {"available": True, "routers": [], "count": 0}

        monkeypatch.setattr(cli_mod.thread_network_core, "discover_routers", fake_discover)
        r = _invoke(runner, "thread", "routers", "--timeout", "2.5", "--max-routers", "3")
        assert r.exit_code == 0, r.output
        assert seen == {"timeout": 2.5, "max_routers": 3}

    def test_audit_is_read_only(self, runner, stocked):
        stocked.set_ws_error("otbr/info", "not_loaded", "")
        r = _invoke(runner, "thread", "audit")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["available"] is True
        assert all(c["type"].endswith(("list_datasets", "info")) for c in stocked.ws_calls)

    def test_audit_forwards_the_discovery_window(self, monkeypatch, runner, fake_client):
        seen = {}

        def fake_audit(client, *, discover_timeout):
            seen["discover_timeout"] = discover_timeout
            return {"available": True}

        monkeypatch.setattr(cli_mod.thread_network_core, "audit", fake_audit)
        _invoke(runner, "thread", "audit", "--discover-timeout", "4")
        assert seen == {"discover_timeout": 4.0}


class TestOtbrGroup:
    def test_info_hides_the_dataset_tlv(self, runner, fake_client):
        fake_client.set_ws(
            "otbr/info",
            {"1122334455667788": {"active_dataset_tlvs": "0e08", "channel": 15}},
        )
        r = _invoke(runner, "thread", "otbr", "info")
        assert r.exit_code == 0, r.output
        assert "0e08" not in r.output
        assert json.loads(r.output)["routers"][0]["has_active_dataset"] is True

    def test_set_channel_is_dry_run_by_default(self, runner, fake_client):
        fake_client.set_ws("otbr/info", {"aa11": {"channel": 15, "extended_address": "aa11"}})
        r = _invoke(runner, "thread", "otbr", "set-channel", "aa11", "20")
        assert json.loads(r.output)["applied"] is False
        assert "otbr/set_channel" not in [c["type"] for c in fake_client.ws_calls]

    def test_set_channel_apply(self, runner, fake_client):
        fake_client.set_ws("otbr/info", {"aa11": {"channel": 15, "extended_address": "aa11"}})
        fake_client.set_ws("otbr/set_channel", {"delay": 300.0})
        r = _invoke(runner, "thread", "otbr", "set-channel", "aa11", "20", "--apply")
        assert json.loads(r.output)["delay"] == 300.0

    def test_an_out_of_band_channel_is_a_clean_error(self, runner, fake_client):
        fake_client.set_ws("otbr/info", {"aa11": {"channel": 15, "extended_address": "aa11"}})
        r = _invoke(runner, "thread", "otbr", "set-channel", "aa11", "30")
        assert r.exit_code != 0
        assert "between 11 and 26" in r.output
        assert "Traceback" not in r.output

    def test_set_network_forwards_both_arguments(self, runner, fake_client):
        fake_client.set_ws(
            "otbr/info", {"aa11": {"channel": 15, "extended_address": "aa11"}}
        )
        fake_client.set_ws("thread/list_datasets", {"datasets": [ENTRY]})
        _invoke(
            runner, "thread", "otbr", "set-network", "aa11", ENTRY["dataset_id"], "--apply"
        )
        sent = next(c for c in fake_client.ws_calls if c["type"] == "otbr/set_network")
        assert sent["payload"] == {
            "extended_address": "aa11",
            "dataset_id": ENTRY["dataset_id"],
        }

    def test_create_network_dry_run_does_not_prompt(self, runner, fake_client):
        """The confirmation is on the apply — a dry run must stay non-interactive."""
        fake_client.set_ws("otbr/info", {"aa11": {"channel": 15, "extended_address": "aa11"}})
        r = _invoke(runner, "thread", "otbr", "create-network", "aa11", input="")
        assert r.exit_code == 0, r.output
        assert json.loads(r.output)["applied"] is False

    def test_create_network_apply_prompts_and_a_no_aborts(self, runner, fake_client):
        fake_client.set_ws("otbr/info", {"aa11": {"channel": 15, "extended_address": "aa11"}})
        r = _invoke(runner, "thread", "otbr", "create-network", "aa11", "--apply", input="n\n")
        assert r.exit_code != 0
        assert "otbr/create_network" not in [c["type"] for c in fake_client.ws_calls]

    def test_create_network_apply_with_yes_skips_the_prompt(self, runner, fake_client):
        fake_client.set_ws("otbr/info", {"aa11": {"channel": 15, "extended_address": "aa11"}})
        r = _invoke(runner, "thread", "otbr", "create-network", "aa11", "--apply", "--yes")
        assert r.exit_code == 0, r.output
        assert "otbr/create_network" in [c["type"] for c in fake_client.ws_calls]


class TestGlobalFlagHoisting:
    """`main()` rewrites argv; it must not steal an option the subcommand owns."""

    def test_a_subcommand_timeout_is_left_where_the_user_put_it(self):
        argv = ["ha", "--url", "http://x", "thread", "routers", "--timeout", "2.5"]
        assert cli_mod.hoist_global_flags(argv) == [
            "ha", "--url", "http://x", "thread", "routers", "--timeout", "2.5"
        ]

    def test_the_root_timeout_is_still_hoisted_for_a_command_without_one(self):
        argv = ["ha", "system", "info", "--timeout", "5"]
        assert cli_mod.hoist_global_flags(argv) == ["ha", "--timeout", "5", "system", "info"]

    def test_a_trailing_json_is_still_hoisted(self):
        assert cli_mod.hoist_global_flags(["ha", "system", "info", "--json"]) == [
            "ha", "--json", "system", "info"
        ]

    def test_the_equals_form_is_hoisted_too(self):
        assert cli_mod.hoist_global_flags(["ha", "system", "info", "--url=http://x"]) == [
            "ha", "--url=http://x", "system", "info"
        ]

    def test_verify_ssl_is_hoisted(self):
        assert cli_mod.hoist_global_flags(["ha", "system", "info", "--no-verify-ssl"]) == [
            "ha", "--no-verify-ssl", "system", "info"
        ]

    def test_an_option_value_is_not_mistaken_for_a_subcommand(self):
        """`--token thread` must not resolve `thread` as the command."""
        assert "--timeout" not in cli_mod._subcommand_option_names(
            ["ha", "--token", "thread", "system", "info"]
        )

    def test_arguments_after_the_command_do_not_derail_resolution(self):
        owned = cli_mod._subcommand_option_names(["ha", "thread", "dataset", "01ABC", "--reveal"])
        assert "--reveal" in owned

    def test_a_nested_group_resolves_to_the_leaf_command(self):
        owned = cli_mod._subcommand_option_names(["ha", "thread", "otbr", "set-channel", "aa", "20"])
        assert "--apply" in owned

    def test_an_unknown_command_owns_nothing(self):
        assert cli_mod._subcommand_option_names(["ha", "not-a-command", "--timeout", "2"]) == set()

    def test_a_bare_invocation_is_returned_unchanged(self):
        assert cli_mod.hoist_global_flags(["ha"]) == ["ha"]

    def test_main_applies_the_rewrite(self, monkeypatch):
        recorded = {}

        def fake_cli(**kwargs):
            import sys

            recorded["argv"] = list(sys.argv)

        monkeypatch.setattr("sys.argv", ["ha", "system", "info", "--json"])
        monkeypatch.setattr(cli_mod, "cli", fake_cli)
        cli_mod.main()
        assert recorded["argv"] == ["ha", "--json", "system", "info"]
