"""Unit tests for `core/thread_network.py` — dataset store, TLV decode, audit.

The wire shapes and error codes asserted here were MEASURED against a real
Home Assistant 2025.1.4 with the `thread` integration loaded (see
CHANGELOG v1.50.0), not read off the docs:

  * `thread/list_datasets` → {"datasets": [ ... ]}
  * `thread/get_dataset_tlv` → {"tlv": "<hex>"}
  * add/delete/set-preferred/set-border-agent all return `null`
  * unknown id → `not_found`, except `set_preferred_border_agent`, which
    reaches an uncaught KeyError and answers `unknown_error`
  * deleting the preferred dataset → `not_allowed`
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import thread_network as tn
from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError


# A complete operational dataset, built with python_otbr_api's own encoder and
# accepted by a live HA. Network name "HarnessNet", channel 15, PAN id 1234,
# extended PAN id 1111111122222222, active timestamp seconds=1.
TLV = (
    "0e080000000000010000000300000f35060004001fffe002081111111122222222"
    "0708fd33333333444444051000112233445566778899aabbccddeeff030a4861726e6573734e6574"
    "010212340410445f2b5ca6f2a93a55ce570a70efeecb0c0402a0f7f8"
)
# Same network, active timestamp seconds=2, network name "NewName".
TLV_NEWER = (
    "0e080000000000020000000300001035060004001fffe002081111111122222222"
    "0708fd33333333444444051000112233445566778899aabbccddeeff03074e65774e616d65"
    "010212340410445f2b5ca6f2a93a55ce570a70efeecb0c0402a0f7f8"
)

ENTRY = {
    "channel": 15,
    "created": "2026-08-26T01:07:32.321135+00:00",
    "dataset_id": "01M0XSQAB1NV7B2KX4063XF7D3",
    "extended_pan_id": "1111111122222222",
    "network_name": "HarnessNet",
    "pan_id": "1234",
    "preferred": True,
    "preferred_border_agent_id": None,
    "preferred_extended_address": None,
    "source": "otbr",
}
OTHER = {
    **ENTRY,
    "dataset_id": "01M0XSQABCGHK5SDYCNGK0G45E",
    "extended_pan_id": "3333333344444444",
    "network_name": "Second",
    "preferred": False,
}


@pytest.fixture
def stocked(fake_client):
    fake_client.set_ws("thread/list_datasets", {"datasets": [ENTRY, OTHER]})
    fake_client.set_ws("thread/get_dataset_tlv", {"tlv": TLV})
    return fake_client


class TestParseTlv:
    def test_a_dataset_decodes_to_its_items(self):
        items = tn.parse_tlv(TLV)
        by_name = {item["name"]: item for item in items}
        assert by_name["NETWORKNAME"]["value"] == "4861726e6573734e6574"
        assert by_name["CHANNEL"]["length"] == 3

    def test_whitespace_is_tolerated(self):
        assert tn.parse_tlv(f"  {TLV}\n") == tn.parse_tlv(TLV)

    def test_non_hex_is_a_value_error_naming_the_input(self):
        with pytest.raises(ValueError, match="not valid hex"):
            tn.parse_tlv("zzzz")

    def test_an_empty_tlv_is_refused_before_parsing(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            tn.parse_tlv("   ")

    def test_a_truncated_item_is_named_not_silently_dropped(self):
        # tag 3, declares 10 bytes, supplies 2.
        with pytest.raises(ValueError, match="truncated tlv"):
            tn.parse_tlv("030a1122")

    def test_a_lone_tag_byte_is_a_truncated_header(self):
        with pytest.raises(ValueError, match="truncated tlv header"):
            tn.parse_tlv("03")

    def test_a_duplicated_tag_is_rejected_the_way_has_parser_rejects_it(self):
        with pytest.raises(ValueError, match="duplicated tlv tag"):
            tn.parse_tlv("0102123401021234")

    def test_an_unknown_tag_is_passed_through_with_no_name(self):
        items = tn.parse_tlv("fa020102")
        assert items == [{"tag": 250, "name": None, "length": 2, "value": "0102"}]


class TestDescribeDataset:
    def test_the_named_fields_come_out_decoded(self):
        got = tn.describe_dataset(TLV)
        assert got["network_name"] == "HarnessNet"
        assert got["channel"] == 15
        assert got["pan_id"] == "1234"
        assert got["extended_pan_id"] == "1111111122222222"
        assert got["active_timestamp"] == {"seconds": 1, "ticks": 0, "authoritative": False}

    def test_the_credentials_are_redacted_by_default(self):
        got = tn.describe_dataset(TLV)
        secrets = [item for item in got["items"] if item["secret"]]
        assert {item["name"] for item in secrets} == {"NETWORKKEY", "PSKC"}
        assert all(item["value"] == tn.REDACTED for item in secrets)

    def test_the_raw_tlv_is_withheld_with_the_credentials(self):
        """The TLV *is* the credential — printing it would defeat the redaction."""
        assert tn.describe_dataset(TLV)["tlv"] is None

    def test_reveal_puts_the_key_and_the_tlv_back(self):
        got = tn.describe_dataset(TLV, reveal=True)
        key = next(item for item in got["items"] if item["name"] == "NETWORKKEY")
        assert key["value"] == "00112233445566778899aabbccddeeff"
        assert got["tlv"] == TLV
        assert got["revealed"] is True
        assert "network key" in got["note"]

    def test_the_thread_ui_default_key_is_flagged(self):
        """The same condition HA raises the `insecure_thread_network` repair for."""
        assert tn.describe_dataset(TLV)["insecure_default_network_key"] is True

    def test_another_key_is_not_flagged(self):
        swapped = TLV.replace("00112233445566778899aabbccddeeff", "0f1e2d3c4b5a69788796a5b4c3d2e1f0")
        assert tn.describe_dataset(swapped)["insecure_default_network_key"] is False

    def test_a_dataset_ha_would_refuse_is_marked_unstorable(self):
        """Missing EXTPANID/ACTIVETIMESTAMP is the bare 'Invalid dataset' error."""
        got = tn.describe_dataset("030a4861726e6573734e6574")
        assert got["storable"] is False
        assert got["missing_required"] == ["EXTPANID", "ACTIVETIMESTAMP"]


class TestListDatasets:
    def test_the_preferred_dataset_is_named(self, stocked):
        got = tn.list_datasets(stocked)
        assert got["available"] is True
        assert got["preferred"] == ENTRY["dataset_id"]
        assert got["count"] == 2
        assert got["networks"] == 2

    def test_no_tlv_is_ever_fetched_for_a_list(self, stocked):
        tn.list_datasets(stocked)
        assert [call["type"] for call in stocked.ws_calls] == ["thread/list_datasets"]

    def test_a_missing_thread_integration_is_an_answer_not_an_error(self, fake_client):
        fake_client.set_ws_error("thread/list_datasets", "unknown_command", "Unknown command.")
        got = tn.list_datasets(fake_client)
        assert got == {
            "available": False,
            "datasets": [],
            "count": 0,
            "preferred": None,
            "networks": 0,
            "note": got["note"],
        }
        assert "not set up" in got["note"]

    def test_any_other_error_still_raises(self, fake_client):
        fake_client.set_ws_error("thread/list_datasets", "unauthorized", "")
        with pytest.raises(HomeAssistantError):
            tn.list_datasets(fake_client)


class TestDataset:
    def test_a_dataset_joins_its_store_entry_to_its_decoded_tlv(self, stocked):
        got = tn.dataset(stocked, ENTRY["dataset_id"])
        assert got["dataset_id"] == ENTRY["dataset_id"]
        assert got["source"] == "otbr"
        assert got["preferred"] is True
        assert got["network_name"] == "HarnessNet"

    def test_it_is_redacted_by_default(self, stocked):
        assert tn.dataset(stocked, ENTRY["dataset_id"])["tlv"] is None

    def test_reveal_is_the_documented_way_to_back_a_network_up(self, stocked):
        assert tn.dataset(stocked, ENTRY["dataset_id"], reveal=True)["tlv"] == TLV

    def test_an_empty_id_is_refused_before_any_call(self, stocked):
        with pytest.raises(ValueError, match="cannot be empty"):
            tn.dataset(stocked, "")
        assert stocked.ws_calls == []

    def test_not_found_becomes_a_sentence_about_ids(self, fake_client):
        fake_client.set_ws_error("thread/get_dataset_tlv", "not_found", "unknown dataset")
        with pytest.raises(ValueError, match="No Thread dataset with id"):
            tn.dataset(fake_client, "bogus")

    def test_a_missing_integration_is_an_error_for_a_specific_id(self, fake_client):
        fake_client.set_ws_error("thread/get_dataset_tlv", "unknown_command", "")
        with pytest.raises(ValueError, match="not set up"):
            tn.dataset(fake_client, "any")


class TestAddDataset:
    def test_a_new_network_is_predicted_as_a_create(self, fake_client):
        fake_client.set_ws("thread/list_datasets", {"datasets": [OTHER]})
        got = tn.add_dataset(fake_client, TLV)
        assert got["predicted"] == "create"
        assert got["applied"] is False
        assert [c["type"] for c in fake_client.ws_calls] == ["thread/list_datasets"]

    def test_a_dry_run_sends_nothing(self, stocked):
        tn.add_dataset(stocked, TLV)
        assert "thread/add_dataset_tlv" not in [c["type"] for c in stocked.ws_calls]

    def test_an_identical_tlv_is_predicted_as_unchanged(self, stocked):
        got = tn.add_dataset(stocked, TLV)
        assert got["predicted"] == "unchanged"
        assert got["matched_dataset_id"] == ENTRY["dataset_id"]

    def test_a_newer_timestamp_is_predicted_as_a_replace_in_place(self, stocked):
        got = tn.add_dataset(stocked, TLV_NEWER)
        assert got["predicted"] == "replace"
        assert "REPLACED IN PLACE" in got["detail"]

    def test_an_older_timestamp_is_predicted_as_the_silent_drop(self, fake_client):
        fake_client.set_ws("thread/list_datasets", {"datasets": [ENTRY]})
        fake_client.set_ws("thread/get_dataset_tlv", {"tlv": TLV_NEWER})
        got = tn.add_dataset(fake_client, TLV)
        assert got["predicted"] == "ignored_older"
        assert "DROP this one silently" in got["detail"]

    def test_the_insecure_default_key_is_reported_before_it_is_stored(self, stocked):
        assert tn.add_dataset(stocked, TLV)["insecure_default_network_key"] is True

    def test_a_dataset_ha_would_reject_is_refused_locally_by_name(self, stocked):
        with pytest.raises(ValueError, match="EXTPANID"):
            tn.add_dataset(stocked, "030a4861726e6573734e6574", apply=True)
        assert stocked.ws_calls == []

    def test_apply_sends_the_source_and_the_normalized_tlv(self, fake_client):
        fake_client.set_ws("thread/list_datasets", {"datasets": []})
        tn.add_dataset(fake_client, f"  {TLV}  ", source="mine", apply=True)
        sent = next(c for c in fake_client.ws_calls if c["type"] == "thread/add_dataset_tlv")
        assert sent["payload"] == {"source": "mine", "tlv": TLV}

    def test_apply_reports_created_when_a_new_id_appears(self, fake_client):
        class Growing:
            """list_datasets answers empty first, then with the new entry."""

            def __init__(self):
                self.ws_calls = []
                self.seen = 0

            def ws_call(self, msg_type, payload=None):
                self.ws_calls.append({"type": msg_type, "payload": payload})
                if msg_type == "thread/list_datasets":
                    self.seen += 1
                    return {"datasets": [] if self.seen == 1 else [ENTRY]}
                return None

        got = tn.add_dataset(Growing(), TLV, apply=True)
        assert got["outcome"] == "created"
        assert got["dataset_id"] == ENTRY["dataset_id"]

    def test_apply_reports_ignored_older_when_the_store_did_not_move(self, fake_client):
        fake_client.set_ws("thread/list_datasets", {"datasets": [ENTRY]})
        fake_client.set_ws("thread/get_dataset_tlv", {"tlv": TLV_NEWER})
        got = tn.add_dataset(fake_client, TLV, apply=True)
        assert got["applied"] is True
        assert got["outcome"] == "ignored_older"

    def test_an_empty_source_is_refused(self, stocked):
        with pytest.raises(ValueError, match="source cannot be empty"):
            tn.add_dataset(stocked, TLV, source="  ")

    def test_adding_without_the_thread_integration_refuses_loudly(self, fake_client):
        fake_client.set_ws_error("thread/list_datasets", "unknown_command", "")
        with pytest.raises(ValueError, match="not set up"):
            tn.add_dataset(fake_client, TLV)


class TestDeleteDataset:
    def test_the_preferred_dataset_is_refused_with_the_remedy(self, stocked):
        with pytest.raises(ValueError, match="set-preferred"):
            tn.delete_dataset(stocked, ENTRY["dataset_id"], apply=True)
        assert "thread/delete_dataset" not in [c["type"] for c in stocked.ws_calls]

    def test_an_unknown_id_is_refused_before_the_call(self, stocked):
        with pytest.raises(ValueError, match="No Thread dataset with id"):
            tn.delete_dataset(stocked, "nope")

    def test_a_dry_run_names_what_would_go_and_sends_nothing(self, stocked):
        got = tn.delete_dataset(stocked, OTHER["dataset_id"])
        assert got["applied"] is False
        assert got["network_name"] == "Second"
        assert "--reveal" in got["note"]
        assert "thread/delete_dataset" not in [c["type"] for c in stocked.ws_calls]

    def test_apply_deletes_and_verifies_by_re_reading(self, stocked):
        got = tn.delete_dataset(stocked, OTHER["dataset_id"], apply=True)
        sent = next(c for c in stocked.ws_calls if c["type"] == "thread/delete_dataset")
        assert sent["payload"] == {"dataset_id": OTHER["dataset_id"]}
        # The FakeClient keeps answering with both rows, so the verification
        # must report that the row is still there rather than assume success.
        assert got["gone"] is False


class TestSetPreferred:
    def test_a_dry_run_reports_the_current_preference(self, stocked):
        got = tn.set_preferred(stocked, OTHER["dataset_id"])
        assert got["applied"] is False
        assert got["was_preferred"] == ENTRY["dataset_id"]
        assert got["already_preferred"] is False

    def test_apply_sends_the_id_and_reads_back(self, stocked):
        got = tn.set_preferred(stocked, ENTRY["dataset_id"], apply=True)
        sent = next(c for c in stocked.ws_calls if c["type"] == "thread/set_preferred_dataset")
        assert sent["payload"] == {"dataset_id": ENTRY["dataset_id"]}
        assert got["took"] is True

    def test_an_unknown_id_is_refused(self, stocked):
        with pytest.raises(ValueError, match="No Thread dataset"):
            tn.set_preferred(stocked, "nope")

    def test_no_thread_integration_refuses_loudly(self, fake_client):
        fake_client.set_ws_error("thread/list_datasets", "unknown_command", "")
        with pytest.raises(ValueError, match="not set up"):
            tn.set_preferred(fake_client, "any")


class TestSetBorderAgent:
    def test_an_unknown_id_is_refused_because_ha_answers_unknown_error(self, stocked):
        with pytest.raises(ValueError, match="unknown_error"):
            tn.set_border_agent(stocked, "nope", extended_address="1122334455667788")

    def test_the_extended_address_is_required_even_to_clear(self, stocked):
        with pytest.raises(ValueError, match="extended_address cannot be empty"):
            tn.set_border_agent(stocked, ENTRY["dataset_id"], extended_address="")

    def test_a_dry_run_shows_the_current_pinning(self, stocked):
        got = tn.set_border_agent(
            stocked, ENTRY["dataset_id"], extended_address="1122334455667788"
        )
        assert got["applied"] is False
        assert got["was_extended_address"] is None
        assert "thread/set_preferred_border_agent" not in [c["type"] for c in stocked.ws_calls]

    def test_apply_sends_all_three_keys_with_a_null_agent_id_when_clearing(self, stocked):
        tn.set_border_agent(
            stocked, ENTRY["dataset_id"], extended_address="1122334455667788", apply=True
        )
        sent = next(
            c for c in stocked.ws_calls if c["type"] == "thread/set_preferred_border_agent"
        )
        assert sent["payload"] == {
            "dataset_id": ENTRY["dataset_id"],
            "border_agent_id": None,
            "extended_address": "1122334455667788",
        }

    def test_apply_forwards_a_border_agent_id(self, stocked):
        tn.set_border_agent(
            stocked,
            ENTRY["dataset_id"],
            extended_address="1122334455667788",
            border_agent_id="aabbccddeeff0011",
            apply=True,
        )
        sent = next(
            c for c in stocked.ws_calls if c["type"] == "thread/set_preferred_border_agent"
        )
        assert sent["payload"]["border_agent_id"] == "aabbccddeeff0011"


class TestDiscoverRouters:
    def test_discovered_routers_are_collected(self, subscribing_client):
        subscribing_client.queue_events(
            {
                "type": "router_discovered",
                "key": "router-1",
                "data": {"extended_address": "aa", "network_name": "HarnessNet"},
            },
            {
                "type": "router_discovered",
                "key": "router-2",
                "data": {"extended_address": "bb", "network_name": "Second"},
            },
        )
        got = tn.discover_routers(subscribing_client, timeout=1.0)
        assert got["count"] == 2
        assert [r["extended_address"] for r in got["routers"]] == ["aa", "bb"]
        assert subscribing_client.subscribe_calls[0][0] == "thread/discover_routers"

    def test_a_removal_takes_the_router_back_out(self, subscribing_client):
        subscribing_client.queue_events(
            {"type": "router_discovered", "key": "k", "data": {"extended_address": "aa"}},
            {"type": "router_removed", "key": "k"},
        )
        got = tn.discover_routers(subscribing_client, timeout=1.0)
        assert got["routers"] == []
        assert got["removed"] == ["k"]

    def test_an_empty_window_is_an_answer_that_explains_mdns(self, subscribing_client):
        got = tn.discover_routers(subscribing_client, timeout=1.0)
        assert got["available"] is True
        assert got["count"] == 0
        assert "multicast" in got["note"]

    def test_on_router_is_called_per_discovery(self, subscribing_client):
        seen = []
        subscribing_client.queue_events(
            {"type": "router_discovered", "key": "k", "data": {"extended_address": "aa"}}
        )
        tn.discover_routers(subscribing_client, timeout=1.0, on_router=seen.append)
        assert [r["extended_address"] for r in seen] == ["aa"]

    def test_a_bad_timeout_is_refused(self, subscribing_client):
        with pytest.raises(ValueError, match="timeout must be > 0"):
            tn.discover_routers(subscribing_client, timeout=0)

    def test_a_bad_max_routers_is_refused(self, subscribing_client):
        with pytest.raises(ValueError, match="max_routers must be >= 1"):
            tn.discover_routers(subscribing_client, timeout=1.0, max_routers=0)

    def test_a_non_callable_handler_is_refused(self, subscribing_client):
        with pytest.raises(ValueError, match="must be callable"):
            tn.discover_routers(subscribing_client, timeout=1.0, on_router="nope")

    def test_a_missing_integration_is_an_answer_not_a_crash(self, subscribing_client):
        def boom(*args, **kwargs):
            raise HomeAssistantError("WS subscribe failed: unknown_command")

        subscribing_client.ws_subscribe = boom
        got = tn.discover_routers(subscribing_client, timeout=1.0)
        assert got["available"] is False
        assert got["routers"] == []
        # The window is echoed on both branches so the shape does not change.
        assert got["timeout"] == 1.0

    def test_another_subscription_failure_still_raises(self, subscribing_client):
        def boom(*args, **kwargs):
            raise HomeAssistantError("WS subscribe failed: unauthorized")

        subscribing_client.ws_subscribe = boom
        with pytest.raises(HomeAssistantError):
            tn.discover_routers(subscribing_client, timeout=1.0)


class TestAudit:
    def test_more_than_one_stored_network_is_reported_as_information(self, stocked):
        stocked.set_ws_error("otbr/info", "not_loaded", "No OTBR API loaded")
        got = tn.audit(stocked)
        codes = {f["code"] for f in got["findings"]}
        assert "multiple_networks" in codes
        assert got["healthy"] is True
        assert got["otbr_available"] is False

    def test_a_router_off_the_preferred_network_is_a_warning(self, stocked):
        stocked.set_ws(
            "otbr/info",
            {
                "1122334455667788": {
                    "extended_address": "1122334455667788",
                    "extended_pan_id": "3333333344444444",
                    "channel": 15,
                    "url": "http://core-openthread-border-router:8081",
                    "border_agent_id": "aabb",
                    "active_dataset_tlvs": "0e08",
                }
            },
        )
        got = tn.audit(stocked)
        finding = next(f for f in got["findings"] if f["code"] == "router_not_on_preferred_network")
        assert finding["severity"] == "warning"
        assert got["healthy"] is False
        assert got["border_routers"][0]["dataset_id"] == OTHER["dataset_id"]

    def test_a_router_on_an_unstored_network_is_a_warning(self, stocked):
        stocked.set_ws(
            "otbr/info",
            {
                "1122334455667788": {
                    "extended_address": "1122334455667788",
                    "extended_pan_id": "9999999999999999",
                    "channel": 15,
                }
            },
        )
        got = tn.audit(stocked)
        assert "router_network_not_stored" in {f["code"] for f in got["findings"]}
        assert got["border_routers"][0]["dataset_id"] is None

    def test_a_stored_network_nobody_runs_is_information(self, stocked):
        stocked.set_ws(
            "otbr/info",
            {
                "1122334455667788": {
                    "extended_address": "1122334455667788",
                    "extended_pan_id": "1111111122222222",
                    "channel": 15,
                }
            },
        )
        got = tn.audit(stocked)
        dangling = [f for f in got["findings"] if f["code"] == "dataset_without_router"]
        assert [f["dataset_id"] for f in dangling] == [OTHER["dataset_id"]]

    def test_no_preferred_dataset_is_a_warning(self, fake_client):
        fake_client.set_ws("thread/list_datasets", {"datasets": [{**ENTRY, "preferred": False}]})
        fake_client.set_ws_error("otbr/info", "unknown_command", "")
        got = tn.audit(fake_client)
        assert "no_preferred_dataset" in {f["code"] for f in got["findings"]}
        assert got["healthy"] is False

    def test_no_thread_integration_short_circuits(self, fake_client):
        fake_client.set_ws_error("thread/list_datasets", "unknown_command", "")
        got = tn.audit(fake_client)
        assert got == {
            "available": False,
            "datasets": [],
            "border_routers": [],
            "findings": [],
            "note": got["note"],
        }

    def test_discovery_is_skipped_unless_a_window_is_given(self, stocked):
        stocked.set_ws_error("otbr/info", "not_loaded", "")
        assert tn.audit(stocked)["discovered"] is None

    def test_an_otbr_that_never_advertises_is_reported(self, subscribing_client):
        subscribing_client.set_ws("thread/list_datasets", {"datasets": [ENTRY]})
        subscribing_client.set_ws(
            "otbr/info",
            {
                "1122334455667788": {
                    "extended_address": "1122334455667788",
                    "extended_pan_id": "1111111122222222",
                    "channel": 15,
                }
            },
        )
        got = tn.audit(subscribing_client, discover_timeout=1.0)
        assert "router_not_advertising" in {f["code"] for f in got["findings"]}
        assert got["discovered"]["count"] == 0
