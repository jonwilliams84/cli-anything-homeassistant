"""Unit tests for the DISCOVERY half of config entries + `lovelace config delete`.

The existing `config-entry` / `config-flow` coverage is all operator-initiated:
you name a handler and walk the form. HA also starts flows on its own — a hub
found by mDNS, an integration whose credentials expired — and those are what
these functions read and dismiss.

FakeClient only. Shapes from `components/config/config_entries.py`,
`components/config/device_registry.py` and `components/lovelace/websocket.py`.

Covered:
  config_entries/flow/progress                  — flows_in_progress / flows_needing_attention
  config_entries/ignore_flow                    — ignore_flow
  config_entries/get_single                      — get_entry_single
  GET config/config_entries/flow_handlers        — flow_handlers
  config/device_registry/remove_config_entry     — remove_device
  lovelace/config/delete                         — lovelace.delete_dashboard_config
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli_anything.homeassistant.core import config_entries as ce
from cli_anything.homeassistant.core import lovelace as lovelace_core


PROGRESS = [
    {
        "flow_id": "f_reauth",
        "handler": "hue",
        "step_id": "reauth_confirm",
        "context": {"source": "reauth", "unique_id": "hue-1", "title_placeholders": {"name": "Hue"}},
    },
    {
        "flow_id": "f_disc",
        "handler": "shelly",
        "step_id": "confirm",
        "context": {"source": "zeroconf", "unique_id": "AABBCC"},
    },
    {
        "flow_id": "f_recfg",
        "handler": "mqtt",
        "step_id": "reconfigure",
        "context": {"source": "reconfigure", "unique_id": "mqtt-1"},
    },
    {
        "flow_id": "f_nokey",
        "handler": "dhcp_thing",
        "step_id": "user",
        "context": {"source": "dhcp"},
    },
]


class TestFlowsInProgress:
    def test_the_list_is_passed_through(self, fake_client):
        fake_client.set_ws("config_entries/flow/progress", PROGRESS)
        assert len(ce.flows_in_progress(fake_client)) == 4

    def test_a_non_list_response_is_an_empty_list(self, fake_client):
        fake_client.set_ws("config_entries/flow/progress", {"unexpected": True})
        assert ce.flows_in_progress(fake_client) == []


class TestFlowsNeedingAttention:
    def test_reauth_is_counted_as_broken_not_as_an_offer(self, fake_client):
        fake_client.set_ws("config_entries/flow/progress", PROGRESS)
        got = ce.flows_needing_attention(fake_client)
        assert got["broken"] == 1
        assert got["reauth"][0]["handler"] == "hue"

    def test_the_three_kinds_are_kept_apart(self, fake_client):
        fake_client.set_ws("config_entries/flow/progress", PROGRESS)
        got = ce.flows_needing_attention(fake_client)
        assert [f["flow_id"] for f in got["discovered"]] == ["f_disc", "f_nokey"]
        assert [f["flow_id"] for f in got["reconfigure"]] == ["f_recfg"]
        assert got["total"] == 4

    def test_a_flow_without_a_unique_id_is_marked_unignorable(self, fake_client):
        """`ignore` refuses it, and HA's reason (`no_unique_id`) says why."""
        fake_client.set_ws("config_entries/flow/progress", PROGRESS)
        got = ce.flows_needing_attention(fake_client)
        by_id = {f["flow_id"]: f for f in got["discovered"]}
        assert by_id["f_disc"]["ignorable"] is True
        assert by_id["f_nokey"]["ignorable"] is False

    def test_a_quiet_instance_is_all_zeroes(self, fake_client):
        fake_client.set_ws("config_entries/flow/progress", [])
        got = ce.flows_needing_attention(fake_client)
        assert got == {
            "total": 0,
            "broken": 0,
            "reauth": [],
            "reconfigure": [],
            "discovered": [],
            "note": got["note"],
        }


class TestIgnoreFlow:
    def test_the_payload_is_what_ha_asks_for(self, fake_client):
        ce.ignore_flow(fake_client, "f_disc", "Old Shelly in the shed")
        assert fake_client.ws_calls[-1] == {
            "type": "config_entries/ignore_flow",
            "payload": {"flow_id": "f_disc", "title": "Old Shelly in the shed"},
        }

    def test_the_result_explains_how_to_undo_it(self, fake_client):
        got = ce.ignore_flow(fake_client, "f", "t")
        assert got["ignored"] is True
        assert "un-ignore" in got["note"]

    def test_a_missing_title_is_refused_locally(self, fake_client):
        with pytest.raises(ValueError, match="title is required"):
            ce.ignore_flow(fake_client, "f", "")
        assert fake_client.ws_calls == []

    def test_a_missing_flow_id_points_at_the_command_that_lists_them(self, fake_client):
        with pytest.raises(ValueError, match="config-flow progress"):
            ce.ignore_flow(fake_client, "", "t")


class TestGetEntrySingle:
    def test_the_entry_is_unwrapped(self, fake_client):
        fake_client.set_ws(
            "config_entries/get_single",
            {"config_entry": {"entry_id": "abc", "domain": "hue", "title": "Hue"}},
        )
        got = ce.get_entry_single(fake_client, "abc")
        assert got["domain"] == "hue"
        assert fake_client.ws_calls[-1]["payload"] == {"entry_id": "abc"}

    def test_it_does_not_list_every_entry_the_way_the_scan_does(self, fake_client):
        fake_client.set_ws("config_entries/get_single", {"config_entry": {"entry_id": "abc"}})
        ce.get_entry_single(fake_client, "abc")
        assert [c["type"] for c in fake_client.ws_calls] == ["config_entries/get_single"]

    def test_a_missing_entry_is_an_error_here_where_the_scan_returns_none(self, fake_client):
        fake_client.set_ws("config_entries/get_single", {})
        with pytest.raises(ValueError, match="No config entry"):
            ce.get_entry_single(fake_client, "nope")

    def test_an_empty_entry_id_is_refused(self, fake_client):
        with pytest.raises(ValueError, match="entry_id is required"):
            ce.get_entry_single(fake_client, "")


class TestFlowHandlers:
    def test_the_catalogue_comes_back_as_a_list(self, fake_client):
        fake_client.set("GET", "config/config_entries/flow_handlers", ["hue", "mqtt", "shelly"])
        assert ce.flow_handlers(fake_client) == ["hue", "mqtt", "shelly"]

    def test_the_type_filter_is_has_own_query_param(self, fake_client):
        fake_client.set("GET", "config/config_entries/flow_handlers", ["input_boolean"])
        ce.flow_handlers(fake_client, "helper")
        assert fake_client.calls[-1]["params"] == {"type": "helper"}

    def test_no_filter_sends_no_params(self, fake_client):
        fake_client.set("GET", "config/config_entries/flow_handlers", [])
        ce.flow_handlers(fake_client)
        assert fake_client.calls[-1]["params"] is None

    def test_a_non_list_response_is_an_empty_list(self, fake_client):
        fake_client.set("GET", "config/config_entries/flow_handlers", {"nope": 1})
        assert ce.flow_handlers(fake_client) == []


class TestRemoveDevice:
    def test_the_payload_uses_config_entry_id_not_entry_id(self, fake_client):
        """The one place HA names this field differently — easy to get wrong."""
        fake_client.set_ws(
            "config/device_registry/remove_config_entry", {"id": "dev1", "name": "Bulb"}
        )
        ce.remove_device(fake_client, "entry1", "dev1")
        assert fake_client.ws_calls[-1] == {
            "type": "config/device_registry/remove_config_entry",
            "payload": {"config_entry_id": "entry1", "device_id": "dev1"},
        }

    def test_a_surviving_device_is_returned(self, fake_client):
        fake_client.set_ws(
            "config/device_registry/remove_config_entry", {"id": "dev1", "name": "Bulb"}
        )
        got = ce.remove_device(fake_client, "entry1", "dev1")
        assert got["device"]["name"] == "Bulb"
        assert "survives" in got["note"]

    def test_a_null_device_is_success_because_ha_allows_self_removal(self, fake_client):
        fake_client.set_ws("config/device_registry/remove_config_entry", None)
        got = ce.remove_device(fake_client, "entry1", "dev1")
        assert got["removed"] is True and got["device"] is None
        assert "not a failure" in got["note"]

    @pytest.mark.parametrize("entry,device", [("", "d"), ("e", "")])
    def test_both_ids_are_required(self, fake_client, entry, device):
        with pytest.raises(ValueError, match="is required"):
            ce.remove_device(fake_client, entry, device)
        assert fake_client.ws_calls == []


class TestLovelaceConfigDelete:
    def test_the_current_config_is_snapshotted_before_it_goes(self, fake_client, tmp_path):
        fake_client.set_ws("lovelace/config", {"views": [{"title": "Home"}]})
        got = lovelace_core.delete_dashboard_config(
            fake_client, "jon-mobile", snapshot_dir=str(tmp_path)
        )
        assert got["deleted"] is True
        written = list(Path(tmp_path).glob("jon-mobile-*.json"))
        assert len(written) == 1
        assert json.loads(written[0].read_text())["config"] == {"views": [{"title": "Home"}]}

    def test_the_delete_is_sent_with_the_url_path(self, fake_client, tmp_path):
        fake_client.set_ws("lovelace/config", {"views": []})
        lovelace_core.delete_dashboard_config(
            fake_client, "jon-mobile", snapshot_dir=str(tmp_path)
        )
        assert fake_client.ws_calls[-1] == {
            "type": "lovelace/config/delete",
            "payload": {"url_path": "jon-mobile"},
        }

    def test_the_main_dashboard_is_addressed_with_no_url_path(self, fake_client, tmp_path):
        fake_client.set_ws("lovelace/config", {"views": []})
        got = lovelace_core.delete_dashboard_config(fake_client, snapshot_dir=str(tmp_path))
        assert fake_client.ws_calls[-1]["payload"] == {}
        assert got["url_path"] == "lovelace"

    def test_an_unreadable_config_does_not_block_the_delete(self, fake_client, tmp_path):
        """Nothing stored is the normal state for a never-customised dashboard."""

        class NoConfig(type(fake_client)):
            def ws_call(self, msg_type, payload=None):
                if msg_type == "lovelace/config":
                    raise RuntimeError("Config not found")
                return super().ws_call(msg_type, payload)

        client = NoConfig()
        got = lovelace_core.delete_dashboard_config(client, "x", snapshot_dir=str(tmp_path))
        assert got["deleted"] is True
        assert "_error" in got["snapshot"]

    def test_the_result_says_how_to_get_the_dashboard_back(self, fake_client, tmp_path):
        fake_client.set_ws("lovelace/config", {"views": []})
        got = lovelace_core.delete_dashboard_config(fake_client, "x", snapshot_dir=str(tmp_path))
        assert "lovelace config save" in got["note"]
