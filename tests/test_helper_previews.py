"""Unit tests for cli_anything.homeassistant.core.helper_previews.

All tests run against FakeClient (auto-injected via the ``fake_client``
fixture in conftest.py) — no live Home Assistant required.

WS subscription commands covered:
  group/start_preview            — start_group_preview
  generic_camera/start_preview   — start_generic_camera_preview
  mold_indicator/start_preview   — start_mold_indicator_preview
  statistics/start_preview       — start_statistics_preview
  threshold/start_preview        — start_threshold_preview
  time_date/start_preview        — start_time_date_preview
  switch_as_x/start_preview      — start_switch_as_x_preview
  <domain>/start_preview         — start_helper_preview (dispatcher)
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import helper_previews


# Shared fixtures used across all tests.
_FLOW_ID = "abc-123"
_FLOW_TYPE = "config_flow"
_USER_INPUT = {"entity_id": "sensor.temp", "threshold": 20.0}
_USER_INPUT_CAM = {"still_image_url": "http://cam.local/still"}
_USER_INPUT_SIMPLE = {"display_option": "time"}


class TestHelperPreviews:
    # ────────────────────────── start_group_preview ──────────────────────────

    def test_group_preview_happy_path_payload(self, fake_client):
        """start_group_preview sends ``group/start_preview`` with the full payload."""
        fake_client.set_ws("group/start_preview", {})
        helper_previews.start_group_preview(
            fake_client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT,
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "group/start_preview"
        assert call["payload"]["flow_id"] == _FLOW_ID
        assert call["payload"]["flow_type"] == _FLOW_TYPE
        assert call["payload"]["user_input"] == _USER_INPUT

    def test_group_preview_return_shape(self, fake_client):
        """start_group_preview returns the WS response dict."""
        expected = {"id": 1, "type": "result", "success": True}
        fake_client.set_ws("group/start_preview", expected)
        result = helper_previews.start_group_preview(
            fake_client,
            flow_id=_FLOW_ID,
            flow_type="options_flow",
            user_input=_USER_INPUT,
        )
        assert result == expected

    def test_group_preview_options_flow_accepted(self, fake_client):
        """start_group_preview accepts ``options_flow`` as flow_type."""
        fake_client.set_ws("group/start_preview", {})
        helper_previews.start_group_preview(
            fake_client,
            flow_id=_FLOW_ID,
            flow_type="options_flow",
            user_input=_USER_INPUT,
        )
        call = fake_client.ws_calls[-1]
        assert call["payload"]["flow_type"] == "options_flow"

    # ───────────────────── start_generic_camera_preview ──────────────────────

    def test_generic_camera_preview_happy_path_payload(self, fake_client):
        """start_generic_camera_preview sends ``generic_camera/start_preview``."""
        fake_client.set_ws("generic_camera/start_preview", {})
        helper_previews.start_generic_camera_preview(
            fake_client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT_CAM,
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "generic_camera/start_preview"
        assert call["payload"]["flow_id"] == _FLOW_ID
        assert call["payload"]["flow_type"] == _FLOW_TYPE
        assert call["payload"]["user_input"] == _USER_INPUT_CAM

    def test_generic_camera_preview_return_shape(self, fake_client):
        """start_generic_camera_preview returns the WS response dict."""
        expected = {"success": True, "camera": "preview"}
        fake_client.set_ws("generic_camera/start_preview", expected)
        result = helper_previews.start_generic_camera_preview(
            fake_client,
            flow_id="flow-cam-1",
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT_CAM,
        )
        assert result == expected

    # ───────────────────── start_mold_indicator_preview ──────────────────────

    def test_mold_indicator_preview_happy_path_payload(self, fake_client):
        """start_mold_indicator_preview sends ``mold_indicator/start_preview``."""
        fake_client.set_ws("mold_indicator/start_preview", {})
        ui = {"indoor_temp_sensor": "sensor.in_temp",
              "indoor_humidity_sensor": "sensor.in_hum",
              "outdoor_temp_sensor": "sensor.out_temp"}
        helper_previews.start_mold_indicator_preview(
            fake_client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=ui,
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "mold_indicator/start_preview"
        assert call["payload"]["user_input"] == ui

    # ───────────────────── start_statistics_preview ──────────────────────────

    def test_statistics_preview_happy_path_payload(self, fake_client):
        """start_statistics_preview sends ``statistics/start_preview``."""
        fake_client.set_ws("statistics/start_preview", {})
        ui = {"entity_id": "sensor.power", "state_characteristic": "mean"}
        helper_previews.start_statistics_preview(
            fake_client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=ui,
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "statistics/start_preview"
        assert call["payload"]["flow_id"] == _FLOW_ID
        assert call["payload"]["user_input"] == ui

    # ───────────────────── start_threshold_preview ───────────────────────────

    def test_threshold_preview_happy_path_payload(self, fake_client):
        """start_threshold_preview sends ``threshold/start_preview``."""
        fake_client.set_ws("threshold/start_preview", {})
        helper_previews.start_threshold_preview(
            fake_client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT,
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "threshold/start_preview"
        assert call["payload"]["flow_id"] == _FLOW_ID
        assert call["payload"]["flow_type"] == _FLOW_TYPE

    # ───────────────────── start_time_date_preview ───────────────────────────

    def test_time_date_preview_happy_path_payload(self, fake_client):
        """start_time_date_preview sends ``time_date/start_preview``."""
        fake_client.set_ws("time_date/start_preview", {})
        helper_previews.start_time_date_preview(
            fake_client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT_SIMPLE,
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "time_date/start_preview"
        assert call["payload"]["flow_id"] == _FLOW_ID
        assert call["payload"]["user_input"] == _USER_INPUT_SIMPLE

    # ───────────────────── start_switch_as_x_preview ─────────────────────────

    def test_switch_as_x_preview_happy_path_payload(self, fake_client):
        """start_switch_as_x_preview sends ``switch_as_x/start_preview``."""
        fake_client.set_ws("switch_as_x/start_preview", {})
        ui = {"entity_id": "switch.bedroom_light", "target_domain": "light"}
        helper_previews.start_switch_as_x_preview(
            fake_client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=ui,
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "switch_as_x/start_preview"
        assert call["payload"]["flow_id"] == _FLOW_ID
        assert call["payload"]["user_input"] == ui

    # ───────────────────── start_helper_preview (dispatcher) ─────────────────

    def test_dispatcher_group_happy_path(self, fake_client):
        """start_helper_preview with domain='group' sends ``group/start_preview``."""
        fake_client.set_ws("group/start_preview", {})
        helper_previews.start_helper_preview(
            fake_client,
            domain="group",
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT,
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "group/start_preview"
        assert call["payload"]["flow_id"] == _FLOW_ID

    def test_dispatcher_statistics_happy_path(self, fake_client):
        """start_helper_preview with domain='statistics' sends correct type."""
        fake_client.set_ws("statistics/start_preview", {})
        ui = {"entity_id": "sensor.power", "state_characteristic": "mean"}
        helper_previews.start_helper_preview(
            fake_client,
            domain="statistics",
            flow_id="flow-stats-1",
            flow_type=_FLOW_TYPE,
            user_input=ui,
        )
        call = fake_client.ws_calls[-1]
        assert call["type"] == "statistics/start_preview"

    def test_dispatcher_all_domains_route_correctly(self, fake_client):
        """start_helper_preview routes every supported domain to the right WS type."""
        domains = [
            "group", "generic_camera", "mold_indicator",
            "statistics", "threshold", "time_date", "switch_as_x",
        ]
        for domain in domains:
            msg_type = f"{domain}/start_preview"
            fake_client.set_ws(msg_type, {})
            helper_previews.start_helper_preview(
                fake_client,
                domain=domain,
                flow_id=f"flow-{domain}",
                flow_type=_FLOW_TYPE,
                user_input={"key": "value"},
            )
            call = fake_client.ws_calls[-1]
            assert call["type"] == msg_type, (
                f"expected {msg_type!r} but got {call['type']!r} for domain={domain!r}"
            )

    # ════════════════════════════════════════════════════════════════════════
    # Validation error tests — ValueError branches
    # ════════════════════════════════════════════════════════════════════════

    def test_invalid_flow_type_raises(self, fake_client):
        """All preview functions raise ValueError for an unrecognised flow_type."""
        with pytest.raises(ValueError, match="flow_type must be"):
            helper_previews.start_group_preview(
                fake_client,
                flow_id=_FLOW_ID,
                flow_type="bad_flow_type",
                user_input=_USER_INPUT,
            )

    def test_empty_flow_id_raises(self, fake_client):
        """All preview functions raise ValueError for an empty flow_id."""
        with pytest.raises(ValueError, match="flow_id must be a non-empty string"):
            helper_previews.start_threshold_preview(
                fake_client,
                flow_id="",
                flow_type=_FLOW_TYPE,
                user_input=_USER_INPUT,
            )

    def test_empty_user_input_raises(self, fake_client):
        """All preview functions raise ValueError for an empty user_input dict."""
        with pytest.raises(ValueError, match="user_input must be a non-empty dict"):
            helper_previews.start_statistics_preview(
                fake_client,
                flow_id=_FLOW_ID,
                flow_type=_FLOW_TYPE,
                user_input={},
            )

    def test_non_dict_user_input_raises(self, fake_client):
        """All preview functions raise ValueError when user_input is not a dict."""
        with pytest.raises(ValueError, match="user_input must be a non-empty dict"):
            helper_previews.start_mold_indicator_preview(
                fake_client,
                flow_id=_FLOW_ID,
                flow_type=_FLOW_TYPE,
                user_input=["entity_id", "sensor.temp"],  # type: ignore[arg-type]
            )

    def test_dispatcher_unknown_domain_raises(self, fake_client):
        """start_helper_preview raises ValueError for an unsupported domain."""
        with pytest.raises(ValueError, match="not a supported preview domain"):
            helper_previews.start_helper_preview(
                fake_client,
                domain="unknown_domain",
                flow_id=_FLOW_ID,
                flow_type=_FLOW_TYPE,
                user_input=_USER_INPUT,
            )

    def test_dispatcher_template_domain_raises(self, fake_client):
        """start_helper_preview raises ValueError for 'template' (not in the 7)."""
        with pytest.raises(ValueError, match="not a supported preview domain"):
            helper_previews.start_helper_preview(
                fake_client,
                domain="template",
                flow_id=_FLOW_ID,
                flow_type=_FLOW_TYPE,
                user_input=_USER_INPUT,
            )

    def test_dispatcher_empty_flow_id_raises(self, fake_client):
        """start_helper_preview validates flow_id before dispatching."""
        with pytest.raises(ValueError, match="flow_id must be a non-empty string"):
            helper_previews.start_helper_preview(
                fake_client,
                domain="group",
                flow_id="",
                flow_type=_FLOW_TYPE,
                user_input=_USER_INPUT,
            )

    def test_dispatcher_bad_flow_type_raises(self, fake_client):
        """start_helper_preview validates flow_type before dispatching."""
        with pytest.raises(ValueError, match="flow_type must be"):
            helper_previews.start_helper_preview(
                fake_client,
                domain="threshold",
                flow_id=_FLOW_ID,
                flow_type="wrong",
                user_input=_USER_INPUT,
            )

    # ════════════════════════════════════════════════════════════════════════
    # WS call recording — ws_calls contains the sent messages
    # ════════════════════════════════════════════════════════════════════════

    def test_ws_calls_recorded_after_group_preview(self, fake_client):
        """start_group_preview is recorded in ws_calls."""
        fake_client.set_ws("group/start_preview", {})
        helper_previews.start_group_preview(
            fake_client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT,
        )
        types = [c["type"] for c in fake_client.ws_calls]
        assert "group/start_preview" in types

    def test_ws_calls_recorded_after_camera_preview(self, fake_client):
        """start_generic_camera_preview is recorded in ws_calls."""
        fake_client.set_ws("generic_camera/start_preview", {})
        helper_previews.start_generic_camera_preview(
            fake_client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT_CAM,
        )
        types = [c["type"] for c in fake_client.ws_calls]
        assert "generic_camera/start_preview" in types

    def test_multiple_previews_all_recorded(self, fake_client):
        """Multiple preview calls are all recorded in ws_calls in order."""
        fake_client.set_ws("threshold/start_preview", {})
        fake_client.set_ws("statistics/start_preview", {})
        helper_previews.start_threshold_preview(
            fake_client,
            flow_id="flow-1",
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT,
        )
        helper_previews.start_statistics_preview(
            fake_client,
            flow_id="flow-2",
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT,
        )
        types = [c["type"] for c in fake_client.ws_calls]
        assert types[-2] == "threshold/start_preview"
        assert types[-1] == "statistics/start_preview"
