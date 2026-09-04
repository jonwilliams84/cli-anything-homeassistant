"""v1.52.0 — every service an entity can be told to run.

The gap this closes was found by diffing THIS instance's service registry
(`GET /api/services` on a live 2025.1.4 with the `demo` integration loaded)
against every `services/<domain>/<service>` string the harness sends. What
came back was not an exotic corner: `switch`, `date`, `time`, `datetime`,
`device_tracker` and `image_processing` had no command at all, and the
`camera` group could describe a camera in detail without being able to tell
it to do anything.

The registry — not `services.yaml` — is the authority. `vacuum/services.yaml`
on the same version documents `turn_on`, `turn_off`, `toggle` and
`start_pause`; the registry has none of them, and calling one is a bare 400.
That is why nothing here wraps them.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import (
    control as control_core,
    entity_control as entity_control_core,
    groups as groups_core,
)


def _svc(client):
    return client.service_calls


# ─────────────────────────────────────────────────────────────────── switch


class TestSwitch:
    def test_turn_on(self, fake_client):
        entity_control_core.switch_turn_on(fake_client, "switch.ac")
        assert _svc(fake_client)[-1] == {
            "domain": "switch",
            "service": "turn_on",
            "service_data": {"entity_id": "switch.ac"},
        }

    def test_turn_off(self, fake_client):
        entity_control_core.switch_turn_off(fake_client, "switch.ac")
        assert _svc(fake_client)[-1]["service"] == "turn_off"

    def test_toggle(self, fake_client):
        entity_control_core.switch_toggle(fake_client, "switch.ac")
        assert _svc(fake_client)[-1]["service"] == "toggle"

    def test_wrong_domain_refused(self, fake_client):
        with pytest.raises(ValueError, match="expected switch"):
            entity_control_core.switch_turn_on(fake_client, "light.bed_light")


# ────────────────────────────────────────────────────── date / time / datetime


class TestDateSetValue:
    def test_iso_accepted(self, fake_client):
        entity_control_core.date_set_value(fake_client, "date.date", date="2026-01-02")
        assert _svc(fake_client)[-1]["service_data"] == {
            "entity_id": "date.date",
            "date": "2026-01-02",
        }

    def test_has_services_yaml_example_is_refused(self, fake_client):
        """HA documents `2022/11/01` and its own parser rejects it.

        `dt_util.parse_date` is `strptime(dt_str, "%Y-%m-%d")`, so the example
        in `date/services.yaml` is a 400 with an empty body. Verified against
        the live instance before this validator was written.
        """
        with pytest.raises(ValueError, match="services.yaml example"):
            entity_control_core.date_set_value(fake_client, "date.date", date="2022/11/01")
        assert _svc(fake_client) == [], "must not reach the wire"

    def test_garbage_refused(self, fake_client):
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            entity_control_core.date_set_value(fake_client, "date.date", date="nope")

    def test_impossible_date_refused(self, fake_client):
        with pytest.raises(ValueError):
            entity_control_core.date_set_value(fake_client, "date.date", date="2026-02-31")

    def test_wrong_domain(self, fake_client):
        with pytest.raises(ValueError, match="expected date"):
            entity_control_core.date_set_value(
                fake_client, "input_datetime.x", date="2026-01-02"
            )


class TestTimeSetValue:
    def test_hh_mm(self, fake_client):
        entity_control_core.time_set_value(fake_client, "time.time", time="22:15")
        assert _svc(fake_client)[-1]["service_data"]["time"] == "22:15"

    def test_hh_mm_ss(self, fake_client):
        entity_control_core.time_set_value(fake_client, "time.time", time="22:15:30")
        assert _svc(fake_client)[-1]["service_data"]["time"] == "22:15:30"

    def test_bare_hour_refused(self, fake_client):
        """`parse_time` splits on ':' and needs two parts; "22" is a 400."""
        with pytest.raises(ValueError, match="HH:MM"):
            entity_control_core.time_set_value(fake_client, "time.time", time="22")

    def test_out_of_range_refused(self, fake_client):
        with pytest.raises(ValueError, match="HH:MM"):
            entity_control_core.time_set_value(fake_client, "time.time", time="25:00")


class TestDateTimeSetValue:
    def test_naive(self, fake_client):
        entity_control_core.datetime_set_value(
            fake_client, "datetime.x", datetime="2023-10-07T21:35:22"
        )
        assert _svc(fake_client)[-1]["service_data"]["datetime"] == "2023-10-07T21:35:22"

    def test_offset(self, fake_client):
        entity_control_core.datetime_set_value(
            fake_client, "datetime.x", datetime="2023-10-07T21:35:22+02:00"
        )
        assert _svc(fake_client)[-1]["service"] == "set_value"

    def test_trailing_z_accepted(self, fake_client):
        """`Z` is valid ISO-8601 to HA (ciso8601) but not to older fromisoformat."""
        entity_control_core.datetime_set_value(
            fake_client, "datetime.x", datetime="2023-10-07T21:35:22Z"
        )
        assert _svc(fake_client)[-1]["service_data"]["datetime"].endswith("Z")

    def test_date_only_is_allowed(self, fake_client):
        """HA accepts it and stores midnight — so this is not an error here."""
        entity_control_core.datetime_set_value(
            fake_client, "datetime.x", datetime="2023-10-07"
        )
        assert _svc(fake_client)[-1]["service_data"]["datetime"] == "2023-10-07"

    def test_garbage_refused(self, fake_client):
        with pytest.raises(ValueError, match="ISO-8601"):
            entity_control_core.datetime_set_value(
                fake_client, "datetime.x", datetime="last tuesday"
            )


# ─────────────────────────────────────────────────────────────────── camera


class TestCameraControl:
    def test_turn_on_off(self, fake_client):
        entity_control_core.camera_turn_on(fake_client, "camera.front")
        entity_control_core.camera_turn_off(fake_client, "camera.front")
        assert [c["service"] for c in _svc(fake_client)] == ["turn_on", "turn_off"]

    def test_motion_detection(self, fake_client):
        entity_control_core.camera_enable_motion_detection(fake_client, "camera.front")
        entity_control_core.camera_disable_motion_detection(fake_client, "camera.front")
        assert [c["service"] for c in _svc(fake_client)] == [
            "enable_motion_detection",
            "disable_motion_detection",
        ]

    def test_host_snapshot(self, fake_client):
        entity_control_core.camera_host_snapshot(
            fake_client, "camera.front", filename="/media/front.jpg"
        )
        assert _svc(fake_client)[-1]["service_data"] == {
            "entity_id": "camera.front",
            "filename": "/media/front.jpg",
        }

    def test_relative_host_path_refused(self, fake_client):
        """The file is written by HA, so a path relative to the CALLER's cwd
        is meaningless — and HA answers with a bare 500."""
        with pytest.raises(ValueError, match="ABSOLUTE path on the Home Assistant"):
            entity_control_core.camera_host_snapshot(
                fake_client, "camera.front", filename="front.jpg"
            )
        assert _svc(fake_client) == []

    def test_template_filename_allowed(self, fake_client):
        """The field is `cv.template`, so braces are legitimate."""
        entity_control_core.camera_host_snapshot(
            fake_client, "camera.front", filename="/media/{{ entity_id.name }}.jpg"
        )
        assert "{{" in _svc(fake_client)[-1]["service_data"]["filename"]

    def test_record_defaults_omitted(self, fake_client):
        entity_control_core.camera_record(
            fake_client, "camera.front", filename="/media/f.mp4"
        )
        data = _svc(fake_client)[-1]["service_data"]
        assert "duration" not in data and "lookback" not in data

    def test_record_with_bounds(self, fake_client):
        entity_control_core.camera_record(
            fake_client, "camera.front", filename="/media/f.mp4", duration=10, lookback=5
        )
        assert _svc(fake_client)[-1]["service_data"]["duration"] == 10

    @pytest.mark.parametrize("duration", [0, 3601])
    def test_record_duration_bounds(self, fake_client, duration):
        with pytest.raises(ValueError, match="1-3600"):
            entity_control_core.camera_record(
                fake_client, "camera.front", filename="/media/f.mp4", duration=duration
            )

    @pytest.mark.parametrize("lookback", [-1, 301])
    def test_record_lookback_bounds(self, fake_client, lookback):
        with pytest.raises(ValueError, match="0-300"):
            entity_control_core.camera_record(
                fake_client, "camera.front", filename="/media/f.mp4", lookback=lookback
            )

    def test_play_stream(self, fake_client):
        entity_control_core.camera_play_stream(
            fake_client, "camera.front", media_player="media_player.tv"
        )
        assert _svc(fake_client)[-1]["service_data"] == {
            "entity_id": "camera.front",
            "media_player": "media_player.tv",
            "format": "hls",
        }

    def test_play_stream_target_must_be_a_media_player(self, fake_client):
        with pytest.raises(ValueError, match="media_player"):
            entity_control_core.camera_play_stream(
                fake_client, "camera.front", media_player="light.tv"
            )

    def test_play_stream_format(self, fake_client):
        with pytest.raises(ValueError, match="hls"):
            entity_control_core.camera_play_stream(
                fake_client,
                "camera.front",
                media_player="media_player.tv",
                stream_format="dash",
            )


# ──────────────────────────────────────────────── fill-ins on existing domains


class TestDomainFillIns:
    def test_climate_toggle(self, fake_client):
        entity_control_core.climate_toggle(fake_client, "climate.hvac")
        assert _svc(fake_client)[-1] == {
            "domain": "climate",
            "service": "toggle",
            "service_data": {"entity_id": "climate.hvac"},
        }

    def test_climate_swing_horizontal(self, fake_client):
        entity_control_core.climate_set_swing_horizontal_mode(
            fake_client, "climate.hvac", swing_horizontal_mode="auto"
        )
        call = _svc(fake_client)[-1]
        assert call["service"] == "set_swing_horizontal_mode"
        assert call["service_data"]["swing_horizontal_mode"] == "auto"

    def test_climate_swing_horizontal_requires_mode(self, fake_client):
        with pytest.raises(ValueError, match="swing_horizontal_mode"):
            entity_control_core.climate_set_swing_horizontal_mode(
                fake_client, "climate.hvac", swing_horizontal_mode=""
            )

    def test_no_aux_heat_wrapper(self):
        """`climate.set_aux_heat` is deprecated and unsupported from 2025.4.

        Deliberately absent — asserted so a future "completeness" pass does
        not add it back without reading why.
        """
        assert not hasattr(entity_control_core, "climate_set_aux_heat")

    def test_no_vacuum_legacy_wrappers(self):
        """`vacuum.turn_on/turn_off/toggle/start_pause` are in services.yaml
        and NOT in the registry on 2025.1.4 — calling one is a bare 400."""
        for name in (
            "vacuum_turn_on",
            "vacuum_turn_off",
            "vacuum_toggle",
            "vacuum_start_pause",
        ):
            assert not hasattr(entity_control_core, name), name

    def test_cover_toggle_tilt(self, fake_client):
        entity_control_core.cover_toggle_tilt(fake_client, "cover.window")
        assert _svc(fake_client)[-1]["service"] == "toggle_cover_tilt"

    def test_media_player_toggle(self, fake_client):
        entity_control_core.media_player_toggle(fake_client, "media_player.tv")
        assert _svc(fake_client)[-1]["service"] == "toggle"

    def test_media_player_seek(self, fake_client):
        entity_control_core.media_player_seek(fake_client, "media_player.tv", position=30)
        assert _svc(fake_client)[-1]["service_data"]["seek_position"] == 30.0

    def test_media_player_seek_negative_refused(self, fake_client):
        with pytest.raises(ValueError, match=">= 0"):
            entity_control_core.media_player_seek(
                fake_client, "media_player.tv", position=-1
            )

    def test_alarm_arm_custom_bypass(self, fake_client):
        entity_control_core.alarm_arm_custom_bypass(
            fake_client, "alarm_control_panel.security", code="1234"
        )
        call = _svc(fake_client)[-1]
        assert call["service"] == "alarm_arm_custom_bypass"
        assert call["service_data"]["code"] == "1234"

    def test_alarm_arm_custom_bypass_without_code(self, fake_client):
        entity_control_core.alarm_arm_custom_bypass(
            fake_client, "alarm_control_panel.security"
        )
        assert "code" not in _svc(fake_client)[-1]["service_data"]

    def test_alarm_trigger(self, fake_client):
        entity_control_core.alarm_trigger(fake_client, "alarm_control_panel.security")
        assert _svc(fake_client)[-1]["service"] == "alarm_trigger"

    def test_alarm_wrong_domain(self, fake_client):
        with pytest.raises(ValueError, match="alarm_control_panel"):
            entity_control_core.alarm_trigger(fake_client, "switch.siren")


# ──────────────────────────────────────────────────────────── device_tracker


class TestDeviceTrackerSee:
    def test_dev_id_and_location(self, fake_client):
        entity_control_core.device_tracker_see(
            fake_client, dev_id="phonedave", location_name="home"
        )
        assert _svc(fake_client)[-1]["service_data"] == {
            "dev_id": "phonedave",
            "location_name": "home",
        }

    def test_gps(self, fake_client):
        entity_control_core.device_tracker_see(
            fake_client, dev_id="phonedave", gps=[52.1, 4.2], gps_accuracy=10, battery=80
        )
        data = _svc(fake_client)[-1]["service_data"]
        assert data["gps"] == [52.1, 4.2]
        assert data["battery"] == 80

    def test_mac_alone_is_enough(self, fake_client):
        entity_control_core.device_tracker_see(fake_client, mac="FF:FF:FF:FF:FF:FF")
        assert _svc(fake_client)[-1]["service_data"] == {"mac": "FF:FF:FF:FF:FF:FF"}

    def test_needs_a_key(self, fake_client):
        with pytest.raises(ValueError, match="dev_id or mac"):
            entity_control_core.device_tracker_see(fake_client, location_name="home")

    def test_gps_must_be_a_pair(self, fake_client):
        with pytest.raises(ValueError, match="latitude, longitude"):
            entity_control_core.device_tracker_see(
                fake_client, dev_id="x", gps=[52.1, 4.2, 0.0]
            )

    def test_gps_range(self, fake_client):
        with pytest.raises(ValueError, match="latitude"):
            entity_control_core.device_tracker_see(fake_client, dev_id="x", gps=[91.0, 0.0])
        with pytest.raises(ValueError, match="longitude"):
            entity_control_core.device_tracker_see(fake_client, dev_id="x", gps=[0.0, 181.0])

    def test_battery_range(self, fake_client):
        with pytest.raises(ValueError, match="battery"):
            entity_control_core.device_tracker_see(fake_client, dev_id="x", battery=101)


class TestImageProcessing:
    def test_scan(self, fake_client):
        entity_control_core.image_processing_scan(fake_client, "image_processing.face")
        assert _svc(fake_client)[-1] == {
            "domain": "image_processing",
            "service": "scan",
            "service_data": {"entity_id": "image_processing.face"},
        }

    def test_wrong_domain(self, fake_client):
        with pytest.raises(ValueError, match="expected image_processing"):
            entity_control_core.image_processing_scan(fake_client, "camera.front")


# ────────────────────────────────────────────────── homeassistant.* services


class TestUpdateEntity:
    def _seed(self, fake_client, entity_id, stamp):
        fake_client.set("GET", f"states/{entity_id}", {
            "entity_id": entity_id, "state": "1", "last_updated": stamp,
        })

    def test_refreshed_when_timestamp_moves(self, fake_client):
        stamps = iter(["2026-01-01T00:00:00Z", "2026-01-01T00:00:05Z"])
        real_get = fake_client.get

        def get(path, params=None):
            if path == "states/sensor.a":
                return {"entity_id": "sensor.a", "last_updated": next(stamps)}
            return real_get(path, params)

        fake_client.get = get
        out = control_core.update_entity(fake_client, ["sensor.a"])
        assert out["entities"][0]["status"] == "refreshed"
        assert out["refreshed"] == 1

    def test_unchanged_is_reported_honestly(self, fake_client):
        self._seed(fake_client, "sensor.a", "2026-01-01T00:00:00Z")
        out = control_core.update_entity(fake_client, ["sensor.a"])
        assert out["entities"][0]["status"] == "unchanged"
        assert out["unchanged"] == 1

    def test_missing_entity_is_caught(self, fake_client):
        """The service swallows a typo: HTTP 200, `[]`, no complaint.

        Reproduced against the live instance — `update_entity` for
        `sensor.does_not_exist` is indistinguishable from a real refresh on
        the wire. The before/after read is the only thing that catches it.
        """
        fake_client.set_rest_error("GET", "states/sensor.nope", 404, "")
        out = control_core.update_entity(fake_client, ["sensor.nope"])
        assert out["missing"] == ["sensor.nope"]
        assert out["entities"][0]["status"] == "missing"

    def test_service_payload(self, fake_client):
        self._seed(fake_client, "sensor.a", "t")
        control_core.update_entity(fake_client, ["sensor.a"])
        call = [c for c in _svc(fake_client) if c["service"] == "update_entity"][-1]
        assert call["service_data"] == {"entity_id": ["sensor.a"]}

    def test_all_is_refused(self, fake_client):
        """`cv.entity_ids` rejects `all`; HA's answer is a bare 400."""
        with pytest.raises(ValueError, match="does not accept 'all'"):
            control_core.update_entity(fake_client, ["all"])
        assert _svc(fake_client) == []

    def test_bare_object_id_refused(self, fake_client):
        with pytest.raises(ValueError, match="domain.object"):
            control_core.update_entity(fake_client, ["sensor"])

    def test_empty_refused(self, fake_client):
        with pytest.raises(ValueError, match="at least one"):
            control_core.update_entity(fake_client, [])

    def test_no_verify_skips_the_reads(self, fake_client):
        control_core.update_entity(fake_client, ["sensor.a"], verify=False)
        assert not [c for c in fake_client.calls if c["verb"] == "GET"]


class TestCoreServices:
    def test_set_location(self, fake_client):
        control_core.set_location(fake_client, latitude=52.0, longitude=4.0)
        call = _svc(fake_client)[-1]
        assert call["service"] == "set_location"
        assert call["service_data"] == {"latitude": 52.0, "longitude": 4.0}

    def test_set_location_elevation_is_optional_not_reset(self, fake_client):
        control_core.set_location(fake_client, latitude=52.0, longitude=4.0)
        assert "elevation" not in _svc(fake_client)[-1]["service_data"]
        control_core.set_location(
            fake_client, latitude=52.0, longitude=4.0, elevation=12.0
        )
        assert _svc(fake_client)[-1]["service_data"]["elevation"] == 12.0

    @pytest.mark.parametrize("lat", [-91.0, 91.0])
    def test_latitude_range(self, fake_client, lat):
        with pytest.raises(ValueError, match="latitude"):
            control_core.set_location(fake_client, latitude=lat, longitude=0.0)

    @pytest.mark.parametrize("lon", [-181.0, 181.0])
    def test_longitude_range(self, fake_client, lon):
        with pytest.raises(ValueError, match="longitude"):
            control_core.set_location(fake_client, latitude=0.0, longitude=lon)

    def test_reload_custom_templates(self, fake_client):
        control_core.reload_custom_templates(fake_client)
        assert _svc(fake_client)[-1]["service"] == "reload_custom_templates"

    def test_save_persistent_states(self, fake_client):
        control_core.save_persistent_states(fake_client)
        assert _svc(fake_client)[-1]["service"] == "save_persistent_states"


# ──────────────────────────────────────────────────────────── group set/remove


class TestGroupCrud:
    def test_set_replaces_membership(self, fake_client):
        out = groups_core.set_group(
            fake_client, "kitchen", name="Kitchen", entities=["light.a", "switch.b"]
        )
        assert out["entity_id"] == "group.kitchen"
        assert _svc(fake_client)[-1]["service_data"] == {
            "object_id": "kitchen",
            "name": "Kitchen",
            "entities": ["light.a", "switch.b"],
        }

    def test_entity_id_is_unwrapped(self, fake_client):
        """`group.set` takes an OBJECT id; a full entity id would silently
        create `group.group.kitchen`."""
        groups_core.set_group(fake_client, "group.kitchen", name="K")
        assert _svc(fake_client)[-1]["service_data"]["object_id"] == "kitchen"

    def test_other_domain_refused(self, fake_client):
        with pytest.raises(ValueError, match="bare id"):
            groups_core.set_group(fake_client, "light.kitchen", name="K")

    def test_add_and_remove(self, fake_client):
        groups_core.set_group(
            fake_client, "kitchen", add_entities=["light.c"], remove_entities=["light.a"]
        )
        data = _svc(fake_client)[-1]["service_data"]
        assert data["add_entities"] == ["light.c"]
        assert data["remove_entities"] == ["light.a"]

    def test_replace_and_edit_together_refused(self, fake_client):
        with pytest.raises(ValueError, match="not both"):
            groups_core.set_group(
                fake_client, "kitchen", entities=["light.a"], add_entities=["light.b"]
            )

    def test_empty_set_refused(self, fake_client):
        with pytest.raises(ValueError, match="nothing to set"):
            groups_core.set_group(fake_client, "kitchen")

    def test_all_flag(self, fake_client):
        groups_core.set_group(fake_client, "kitchen", all_must_be_on=True)
        assert _svc(fake_client)[-1]["service_data"]["all"] is True

    def test_entities_may_be_emptied(self, fake_client):
        """An empty list is a real instruction (drop every member) and must
        not be confused with "not given"."""
        groups_core.set_group(fake_client, "kitchen", entities=[])
        assert _svc(fake_client)[-1]["service_data"]["entities"] == []

    def test_remove(self, fake_client):
        out = groups_core.remove_group(fake_client, "group.kitchen")
        assert out == {
            "object_id": "kitchen",
            "entity_id": "group.kitchen",
            "removed": True,
        }
        assert _svc(fake_client)[-1]["service"] == "remove"

    def test_reload(self, fake_client):
        assert groups_core.reload_groups(fake_client) == {"reloaded": "group"}
        assert _svc(fake_client)[-1]["service"] == "reload"
