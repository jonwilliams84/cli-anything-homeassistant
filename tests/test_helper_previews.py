"""Unit tests for cli_anything.homeassistant.core.helper_previews.

All subscribe functions now call ws_subscribe (not ws_call), so tests use
SubscribingFakeClient (from conftest.py) to record calls and deliver events.

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

import threading

import pytest

from tests.conftest import SubscribingFakeClient
from cli_anything.homeassistant.core import helper_previews


# Shared fixtures used across all tests.
_FLOW_ID = "abc-123"
_FLOW_TYPE = "config_flow"
_USER_INPUT = {"entity_id": "sensor.temp", "threshold": 20.0}
_USER_INPUT_CAM = {"still_image_url": "http://cam.local/still"}
_USER_INPUT_SIMPLE = {"display_option": "time"}


class TestHelperPreviews:
    # ────────────────────────── start_group_preview ──────────────────────────

    def test_group_preview_happy_path_payload(self):
        """start_group_preview calls ws_subscribe with ``group/start_preview``."""
        client = SubscribingFakeClient()
        ev = {"state": "on"}
        client.queue_events(ev)
        received = []
        helper_previews.start_group_preview(
            client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT,
            on_event=received.append,
            max_events=1,
        )
        assert len(client.subscribe_calls) == 1
        msg_type, payload = client.subscribe_calls[0]
        assert msg_type == "group/start_preview"
        assert payload["flow_id"] == _FLOW_ID
        assert payload["flow_type"] == _FLOW_TYPE
        assert payload["user_input"] == _USER_INPUT

    def test_group_preview_delivers_events(self):
        """start_group_preview forwards events to on_event."""
        client = SubscribingFakeClient()
        ev = {"state": "preview_ready"}
        client.queue_events(ev)
        received = []
        helper_previews.start_group_preview(
            client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT,
            on_event=received.append,
            max_events=1,
        )
        assert received == [ev]

    def test_group_preview_options_flow_accepted(self):
        """start_group_preview accepts ``options_flow`` as flow_type."""
        client = SubscribingFakeClient()
        stop = threading.Event()
        stop.set()
        helper_previews.start_group_preview(
            client,
            flow_id=_FLOW_ID,
            flow_type="options_flow",
            user_input=_USER_INPUT,
            on_event=lambda e: None,
            stop_event=stop,
        )
        _, payload = client.subscribe_calls[0]
        assert payload["flow_type"] == "options_flow"

    def test_group_preview_max_events_auto_stop(self):
        """start_group_preview stops after max_events."""
        client = SubscribingFakeClient()
        client.queue_events({"n": 1}, {"n": 2}, {"n": 3})
        received = []
        helper_previews.start_group_preview(
            client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT,
            on_event=received.append,
            max_events=2,
        )
        assert received == [{"n": 1}, {"n": 2}]

    # ───────────────────── start_generic_camera_preview ──────────────────────

    def test_generic_camera_preview_happy_path_payload(self):
        """start_generic_camera_preview calls ws_subscribe with correct type."""
        client = SubscribingFakeClient()
        stop = threading.Event()
        stop.set()
        helper_previews.start_generic_camera_preview(
            client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT_CAM,
            on_event=lambda e: None,
            stop_event=stop,
        )
        assert len(client.subscribe_calls) == 1
        msg_type, payload = client.subscribe_calls[0]
        assert msg_type == "generic_camera/start_preview"
        assert payload["flow_id"] == _FLOW_ID
        assert payload["flow_type"] == _FLOW_TYPE
        assert payload["user_input"] == _USER_INPUT_CAM

    def test_generic_camera_preview_delivers_events(self):
        """start_generic_camera_preview forwards events to on_event."""
        client = SubscribingFakeClient()
        ev = {"image": "data:image/jpeg;base64,..."}
        client.queue_events(ev)
        received = []
        helper_previews.start_generic_camera_preview(
            client,
            flow_id="flow-cam-1",
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT_CAM,
            on_event=received.append,
            max_events=1,
        )
        assert received == [ev]

    # ───────────────────── start_mold_indicator_preview ──────────────────────

    def test_mold_indicator_preview_happy_path_payload(self):
        """start_mold_indicator_preview calls ws_subscribe with correct type."""
        client = SubscribingFakeClient()
        stop = threading.Event()
        stop.set()
        ui = {"indoor_temp_sensor": "sensor.in_temp",
              "indoor_humidity_sensor": "sensor.in_hum",
              "outdoor_temp_sensor": "sensor.out_temp"}
        helper_previews.start_mold_indicator_preview(
            client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=ui,
            on_event=lambda e: None,
            stop_event=stop,
        )
        msg_type, payload = client.subscribe_calls[0]
        assert msg_type == "mold_indicator/start_preview"
        assert payload["user_input"] == ui

    def test_mold_indicator_preview_delivers_events(self):
        """start_mold_indicator_preview forwards events to on_event."""
        client = SubscribingFakeClient()
        ev = {"mold_risk": 0.12}
        client.queue_events(ev)
        received = []
        ui = {"indoor_temp_sensor": "sensor.in_temp",
              "indoor_humidity_sensor": "sensor.in_hum",
              "outdoor_temp_sensor": "sensor.out_temp"}
        helper_previews.start_mold_indicator_preview(
            client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=ui,
            on_event=received.append,
            max_events=1,
        )
        assert received == [ev]

    # ───────────────────── start_statistics_preview ──────────────────────────

    def test_statistics_preview_happy_path_payload(self):
        """start_statistics_preview calls ws_subscribe with correct type."""
        client = SubscribingFakeClient()
        stop = threading.Event()
        stop.set()
        ui = {"entity_id": "sensor.power", "state_characteristic": "mean"}
        helper_previews.start_statistics_preview(
            client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=ui,
            on_event=lambda e: None,
            stop_event=stop,
        )
        msg_type, payload = client.subscribe_calls[0]
        assert msg_type == "statistics/start_preview"
        assert payload["flow_id"] == _FLOW_ID
        assert payload["user_input"] == ui

    def test_statistics_preview_delivers_events(self):
        """start_statistics_preview forwards events to on_event."""
        client = SubscribingFakeClient()
        ev = {"state": "42.3"}
        client.queue_events(ev)
        received = []
        ui = {"entity_id": "sensor.power", "state_characteristic": "mean"}
        helper_previews.start_statistics_preview(
            client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=ui,
            on_event=received.append,
            max_events=1,
        )
        assert received == [ev]

    # ───────────────────── start_threshold_preview ───────────────────────────

    def test_threshold_preview_happy_path_payload(self):
        """start_threshold_preview calls ws_subscribe with correct type."""
        client = SubscribingFakeClient()
        stop = threading.Event()
        stop.set()
        helper_previews.start_threshold_preview(
            client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT,
            on_event=lambda e: None,
            stop_event=stop,
        )
        msg_type, payload = client.subscribe_calls[0]
        assert msg_type == "threshold/start_preview"
        assert payload["flow_id"] == _FLOW_ID
        assert payload["flow_type"] == _FLOW_TYPE

    def test_threshold_preview_delivers_events(self):
        """start_threshold_preview forwards events to on_event."""
        client = SubscribingFakeClient()
        ev = {"state": "on"}
        client.queue_events(ev)
        received = []
        helper_previews.start_threshold_preview(
            client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT,
            on_event=received.append,
            max_events=1,
        )
        assert received == [ev]

    # ───────────────────── start_time_date_preview ───────────────────────────

    def test_time_date_preview_happy_path_payload(self):
        """start_time_date_preview calls ws_subscribe with correct type."""
        client = SubscribingFakeClient()
        stop = threading.Event()
        stop.set()
        helper_previews.start_time_date_preview(
            client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT_SIMPLE,
            on_event=lambda e: None,
            stop_event=stop,
        )
        msg_type, payload = client.subscribe_calls[0]
        assert msg_type == "time_date/start_preview"
        assert payload["flow_id"] == _FLOW_ID
        assert payload["user_input"] == _USER_INPUT_SIMPLE

    def test_time_date_preview_delivers_events(self):
        """start_time_date_preview forwards events to on_event."""
        client = SubscribingFakeClient()
        ev = {"state": "12:34"}
        client.queue_events(ev)
        received = []
        helper_previews.start_time_date_preview(
            client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT_SIMPLE,
            on_event=received.append,
            max_events=1,
        )
        assert received == [ev]

    # ───────────────────── start_switch_as_x_preview ─────────────────────────

    def test_switch_as_x_preview_happy_path_payload(self):
        """start_switch_as_x_preview calls ws_subscribe with correct type."""
        client = SubscribingFakeClient()
        stop = threading.Event()
        stop.set()
        ui = {"entity_id": "switch.bedroom_light", "target_domain": "light"}
        helper_previews.start_switch_as_x_preview(
            client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=ui,
            on_event=lambda e: None,
            stop_event=stop,
        )
        msg_type, payload = client.subscribe_calls[0]
        assert msg_type == "switch_as_x/start_preview"
        assert payload["flow_id"] == _FLOW_ID
        assert payload["user_input"] == ui

    def test_switch_as_x_preview_delivers_events(self):
        """start_switch_as_x_preview forwards events to on_event."""
        client = SubscribingFakeClient()
        ev = {"state": "off"}
        client.queue_events(ev)
        received = []
        ui = {"entity_id": "switch.bedroom_light", "target_domain": "light"}
        helper_previews.start_switch_as_x_preview(
            client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=ui,
            on_event=received.append,
            max_events=1,
        )
        assert received == [ev]

    # ───────────────────── start_helper_preview (dispatcher) ─────────────────

    def test_dispatcher_group_happy_path(self):
        """start_helper_preview with domain='group' calls ws_subscribe with correct type."""
        client = SubscribingFakeClient()
        ev = {"state": "on"}
        client.queue_events(ev)
        received = []
        helper_previews.start_helper_preview(
            client,
            domain="group",
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT,
            on_event=received.append,
            max_events=1,
        )
        msg_type, payload = client.subscribe_calls[0]
        assert msg_type == "group/start_preview"
        assert payload["flow_id"] == _FLOW_ID
        assert received == [ev]

    def test_dispatcher_statistics_happy_path(self):
        """start_helper_preview with domain='statistics' routes to correct type."""
        client = SubscribingFakeClient()
        stop = threading.Event()
        stop.set()
        ui = {"entity_id": "sensor.power", "state_characteristic": "mean"}
        helper_previews.start_helper_preview(
            client,
            domain="statistics",
            flow_id="flow-stats-1",
            flow_type=_FLOW_TYPE,
            user_input=ui,
            on_event=lambda e: None,
            stop_event=stop,
        )
        msg_type, _ = client.subscribe_calls[0]
        assert msg_type == "statistics/start_preview"

    def test_dispatcher_all_domains_route_correctly(self):
        """start_helper_preview routes every supported domain to the right WS type."""
        domains = [
            "group", "generic_camera", "mold_indicator",
            "statistics", "threshold", "time_date", "switch_as_x",
        ]
        for domain in domains:
            client = SubscribingFakeClient()
            stop = threading.Event()
            stop.set()
            helper_previews.start_helper_preview(
                client,
                domain=domain,
                flow_id=f"flow-{domain}",
                flow_type=_FLOW_TYPE,
                user_input={"key": "value"},
                on_event=lambda e: None,
                stop_event=stop,
            )
            msg_type, _ = client.subscribe_calls[0]
            assert msg_type == f"{domain}/start_preview", (
                f"expected {domain}/start_preview but got {msg_type!r} for domain={domain!r}"
            )

    def test_dispatcher_delivers_events(self):
        """start_helper_preview forwards events to on_event via dispatcher."""
        client = SubscribingFakeClient()
        ev = {"state": "preview"}
        client.queue_events(ev)
        received = []
        helper_previews.start_helper_preview(
            client,
            domain="threshold",
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT,
            on_event=received.append,
            max_events=1,
        )
        assert received == [ev]

    # ════════════════════════════════════════════════════════════════════════
    # Validation error tests — ValueError branches
    # ════════════════════════════════════════════════════════════════════════

    def test_invalid_flow_type_raises(self):
        """All preview functions raise ValueError for an unrecognised flow_type."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="flow_type must be"):
            helper_previews.start_group_preview(
                client,
                flow_id=_FLOW_ID,
                flow_type="bad_flow_type",
                user_input=_USER_INPUT,
                on_event=lambda e: None,
                max_events=1,
            )

    def test_empty_flow_id_raises(self):
        """All preview functions raise ValueError for an empty flow_id."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="flow_id must be a non-empty string"):
            helper_previews.start_threshold_preview(
                client,
                flow_id="",
                flow_type=_FLOW_TYPE,
                user_input=_USER_INPUT,
                on_event=lambda e: None,
                max_events=1,
            )

    def test_empty_user_input_raises(self):
        """All preview functions raise ValueError for an empty user_input dict."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="user_input must be a non-empty dict"):
            helper_previews.start_statistics_preview(
                client,
                flow_id=_FLOW_ID,
                flow_type=_FLOW_TYPE,
                user_input={},
                on_event=lambda e: None,
                max_events=1,
            )

    def test_non_dict_user_input_raises(self):
        """All preview functions raise ValueError when user_input is not a dict."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="user_input must be a non-empty dict"):
            helper_previews.start_mold_indicator_preview(
                client,
                flow_id=_FLOW_ID,
                flow_type=_FLOW_TYPE,
                user_input=["entity_id", "sensor.temp"],  # type: ignore[arg-type]
                on_event=lambda e: None,
                max_events=1,
            )

    def test_non_callable_on_event_raises(self):
        """All preview functions raise ValueError when on_event is not callable."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="on_event must be callable"):
            helper_previews.start_group_preview(
                client,
                flow_id=_FLOW_ID,
                flow_type=_FLOW_TYPE,
                user_input=_USER_INPUT,
                on_event="not_callable",  # type: ignore[arg-type]
                max_events=1,
            )

    def test_raises_without_stop_or_max(self):
        """All preview functions raise ValueError when neither stop_event nor max_events."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="must supply stop_event or max_events"):
            helper_previews.start_group_preview(
                client,
                flow_id=_FLOW_ID,
                flow_type=_FLOW_TYPE,
                user_input=_USER_INPUT,
                on_event=lambda e: None,
            )

    def test_dispatcher_unknown_domain_raises(self):
        """start_helper_preview raises ValueError for an unsupported domain."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="not a supported preview domain"):
            helper_previews.start_helper_preview(
                client,
                domain="unknown_domain",
                flow_id=_FLOW_ID,
                flow_type=_FLOW_TYPE,
                user_input=_USER_INPUT,
                on_event=lambda e: None,
                max_events=1,
            )

    def test_dispatcher_template_domain_raises(self):
        """start_helper_preview raises ValueError for 'template' (not in the 7)."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="not a supported preview domain"):
            helper_previews.start_helper_preview(
                client,
                domain="template",
                flow_id=_FLOW_ID,
                flow_type=_FLOW_TYPE,
                user_input=_USER_INPUT,
                on_event=lambda e: None,
                max_events=1,
            )

    def test_dispatcher_empty_flow_id_raises(self):
        """start_helper_preview validates flow_id before dispatching."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="flow_id must be a non-empty string"):
            helper_previews.start_helper_preview(
                client,
                domain="group",
                flow_id="",
                flow_type=_FLOW_TYPE,
                user_input=_USER_INPUT,
                on_event=lambda e: None,
                max_events=1,
            )

    def test_dispatcher_bad_flow_type_raises(self):
        """start_helper_preview validates flow_type before dispatching."""
        client = SubscribingFakeClient()
        with pytest.raises(ValueError, match="flow_type must be"):
            helper_previews.start_helper_preview(
                client,
                domain="threshold",
                flow_id=_FLOW_ID,
                flow_type="wrong",
                user_input=_USER_INPUT,
                on_event=lambda e: None,
                max_events=1,
            )

    # ════════════════════════════════════════════════════════════════════════
    # subscribe_calls recorded — ws_subscribe records all calls
    # ════════════════════════════════════════════════════════════════════════

    def test_subscribe_calls_recorded_after_group_preview(self):
        """start_group_preview is recorded in subscribe_calls."""
        client = SubscribingFakeClient()
        stop = threading.Event()
        stop.set()
        helper_previews.start_group_preview(
            client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT,
            on_event=lambda e: None,
            stop_event=stop,
        )
        types = [sc[0] for sc in client.subscribe_calls]
        assert "group/start_preview" in types

    def test_subscribe_calls_recorded_after_camera_preview(self):
        """start_generic_camera_preview is recorded in subscribe_calls."""
        client = SubscribingFakeClient()
        stop = threading.Event()
        stop.set()
        helper_previews.start_generic_camera_preview(
            client,
            flow_id=_FLOW_ID,
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT_CAM,
            on_event=lambda e: None,
            stop_event=stop,
        )
        types = [sc[0] for sc in client.subscribe_calls]
        assert "generic_camera/start_preview" in types

    def test_multiple_previews_all_recorded(self):
        """Multiple preview calls are all recorded in subscribe_calls in order."""
        client = SubscribingFakeClient()
        stop = threading.Event()
        stop.set()
        helper_previews.start_threshold_preview(
            client,
            flow_id="flow-1",
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT,
            on_event=lambda e: None,
            stop_event=stop,
        )
        helper_previews.start_statistics_preview(
            client,
            flow_id="flow-2",
            flow_type=_FLOW_TYPE,
            user_input=_USER_INPUT,
            on_event=lambda e: None,
            stop_event=stop,
        )
        types = [sc[0] for sc in client.subscribe_calls]
        assert types[-2] == "threshold/start_preview"
        assert types[-1] == "statistics/start_preview"
