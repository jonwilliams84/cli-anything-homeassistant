"""Unit tests for `core/otbr.py` — the border-router radio.

`otbr/info`'s shape (a dict keyed by extended address, each value carrying
`active_dataset_tlvs`, `border_agent_id`, `channel`, `extended_pan_id`, `url`)
is read off HA's `components/otbr/websocket_api.py`. The absence path
(`unknown_command` on an instance with no OTBR integration) was measured on a
live 2025.1.4.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import otbr
from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantError

ROUTER = {
    "active_dataset_tlvs": "0e080000000000010000000300000f",
    "border_agent_id": "aabbccddeeff00112233445566778899",
    "channel": 15,
    "extended_address": "1122334455667788",
    "extended_pan_id": "1111111122222222",
    "url": "http://core-openthread-border-router:8081",
}
DATASET = {
    "channel": 15,
    "dataset_id": "01M0XSQAB1NV7B2KX4063XF7D3",
    "extended_pan_id": "1111111122222222",
    "network_name": "HarnessNet",
    "preferred": True,
}


@pytest.fixture
def with_router(fake_client):
    fake_client.set_ws("otbr/info", {ROUTER["extended_address"]: ROUTER})
    fake_client.set_ws("thread/list_datasets", {"datasets": [DATASET]})
    return fake_client


class TestInfo:
    def test_the_keyed_dict_is_flattened_to_a_list(self, with_router):
        got = otbr.info(with_router)
        assert got["available"] is True
        assert got["count"] == 1
        assert got["routers"][0]["extended_address"] == ROUTER["extended_address"]

    def test_the_active_dataset_tlv_is_dropped_because_it_is_the_network_key(self, with_router):
        got = otbr.info(with_router)
        assert "active_dataset_tlvs" not in got["routers"][0]
        assert got["routers"][0]["has_active_dataset"] is True

    def test_a_router_with_no_dataset_says_so(self, fake_client):
        fake_client.set_ws("otbr/info", {"aa": {**ROUTER, "active_dataset_tlvs": None}})
        assert otbr.info(fake_client)["routers"][0]["has_active_dataset"] is False

    @pytest.mark.parametrize("code", ["unknown_command", "not_loaded"])
    def test_no_border_router_is_an_answer_not_an_error(self, fake_client, code):
        fake_client.set_ws_error("otbr/info", code, "No OTBR API loaded")
        got = otbr.info(fake_client)
        assert got == {"available": False, "routers": [], "count": 0, "note": got["note"]}

    def test_any_other_error_still_raises(self, fake_client):
        fake_client.set_ws_error("otbr/info", "otbr_info_failed", "boom")
        with pytest.raises(HomeAssistantError):
            otbr.info(fake_client)


class TestRouterResolution:
    def test_an_unknown_address_is_refused_locally_listing_the_real_ones(self, with_router):
        """HA's own answer is the code `unknown_router` with an EMPTY message."""
        with pytest.raises(ValueError, match="1122334455667788"):
            otbr.set_channel(with_router, "ffffffffffffffff", 20, apply=True)
        assert "otbr/set_channel" not in [c["type"] for c in with_router.ws_calls]

    def test_the_match_is_case_insensitive(self, with_router):
        got = otbr.set_channel(with_router, "1122334455667788".upper(), 20)
        assert got["extended_address"] == ROUTER["extended_address"]

    def test_an_empty_address_names_the_command_that_lists_them(self, with_router):
        with pytest.raises(ValueError, match="otbr info"):
            otbr.set_channel(with_router, "", 20)

    def test_no_otbr_at_all_refuses_a_write_loudly(self, fake_client):
        fake_client.set_ws_error("otbr/info", "not_loaded", "")
        with pytest.raises(ValueError, match="No OpenThread Border Router"):
            otbr.set_channel(fake_client, "1122334455667788", 20, apply=True)


class TestSetChannel:
    @pytest.mark.parametrize("channel", [10, 27, 0, -1])
    def test_channels_outside_the_thread_band_are_refused(self, with_router, channel):
        with pytest.raises(ValueError, match="between 11 and 26"):
            otbr.set_channel(with_router, ROUTER["extended_address"], channel)

    def test_a_non_numeric_channel_is_refused(self, with_router):
        with pytest.raises(ValueError, match="must be an integer"):
            otbr.set_channel(with_router, ROUTER["extended_address"], "twenty")

    def test_a_dry_run_sends_nothing_and_names_the_pending_delay(self, with_router):
        got = otbr.set_channel(with_router, ROUTER["extended_address"], 20)
        assert got["applied"] is False
        assert got["current_channel"] == 15
        assert "PENDING dataset" in got["note"]
        assert "otbr/set_channel" not in [c["type"] for c in with_router.ws_calls]

    def test_asking_for_the_current_channel_is_marked_a_no_op(self, with_router):
        assert otbr.set_channel(with_router, ROUTER["extended_address"], 15)["no_op"] is True

    def test_apply_sends_the_pair_and_returns_has_delay(self, with_router):
        with_router.set_ws("otbr/set_channel", {"delay": 300.0})
        got = otbr.set_channel(with_router, ROUTER["extended_address"], 20, apply=True)
        sent = next(c for c in with_router.ws_calls if c["type"] == "otbr/set_channel")
        assert sent["payload"] == {"extended_address": ROUTER["extended_address"], "channel": 20}
        assert got["delay"] == 300.0
        assert got["previous_channel"] == 15

    def test_multiprotocol_refusal_is_translated(self, with_router):
        with_router.set_ws_error("otbr/set_channel", "multiprotocol_enabled", "")
        with pytest.raises(ValueError, match="multiprotocol add-on"):
            otbr.set_channel(with_router, ROUTER["extended_address"], 20, apply=True)

    def test_an_unnamed_failure_still_names_the_code_and_where_to_look(self, with_router):
        with_router.set_ws_error("otbr/set_channel", "set_channel_failed", "radio busy")
        with pytest.raises(ValueError, match="set_channel_failed"):
            otbr.set_channel(with_router, ROUTER["extended_address"], 20, apply=True)


class TestSetNetwork:
    def test_an_unknown_dataset_is_refused_before_the_call(self, with_router):
        with pytest.raises(ValueError, match="unknown_dataset"):
            otbr.set_network(with_router, ROUTER["extended_address"], "nope", apply=True)
        assert "otbr/set_network" not in [c["type"] for c in with_router.ws_calls]

    def test_an_empty_dataset_id_is_refused(self, with_router):
        with pytest.raises(ValueError, match="dataset_id cannot be empty"):
            otbr.set_network(with_router, ROUTER["extended_address"], "")

    def test_a_dry_run_compares_the_two_networks(self, with_router):
        got = otbr.set_network(with_router, ROUTER["extended_address"], DATASET["dataset_id"])
        assert got["applied"] is False
        assert got["already_on_network"] is True
        assert got["network_name"] == "HarnessNet"

    def test_apply_sends_both_keys(self, with_router):
        got = otbr.set_network(
            with_router, ROUTER["extended_address"], DATASET["dataset_id"], apply=True
        )
        sent = next(c for c in with_router.ws_calls if c["type"] == "otbr/set_network")
        assert sent["payload"] == {
            "extended_address": ROUTER["extended_address"],
            "dataset_id": DATASET["dataset_id"],
        }
        assert got["took"] is True

    def test_a_channel_conflict_names_zha(self, with_router):
        with_router.set_ws_error(
            "otbr/set_network", "channel_conflict", "ZHA is using channel 20"
        )
        with pytest.raises(ValueError, match="ZHA"):
            otbr.set_network(
                with_router, ROUTER["extended_address"], DATASET["dataset_id"], apply=True
            )


class TestCreateNetwork:
    def test_a_dry_run_spells_out_what_is_lost(self, with_router):
        got = otbr.create_network(with_router, ROUTER["extended_address"])
        assert got["applied"] is False
        assert "FACTORY-RESET" in got["note"]
        assert "--reveal" in got["note"]
        assert "otbr/create_network" not in [c["type"] for c in with_router.ws_calls]

    def test_apply_sends_the_address_only(self, with_router):
        otbr.create_network(with_router, ROUTER["extended_address"], apply=True)
        sent = next(c for c in with_router.ws_calls if c["type"] == "otbr/create_network")
        assert sent["payload"] == {"extended_address": ROUTER["extended_address"]}

    def test_apply_reports_whether_the_network_actually_changed(self, with_router):
        got = otbr.create_network(with_router, ROUTER["extended_address"], apply=True)
        # The fake keeps answering with the same extended PAN ID, so the
        # verification must say "nothing changed" rather than assume success.
        assert got["changed"] is False
        assert got["previous_extended_pan_id"] == ROUTER["extended_pan_id"]

    def test_a_failure_is_translated_with_the_code(self, with_router):
        with_router.set_ws_error("otbr/create_network", "factory_reset_failed", "no radio")
        with pytest.raises(ValueError, match="factory_reset_failed"):
            otbr.create_network(with_router, ROUTER["extended_address"], apply=True)
