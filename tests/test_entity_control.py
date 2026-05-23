"""Unit tests for cli_anything.homeassistant.core.entity_control.

Each shortcut function is exercised against a FakeClient. Tests assert:
  * the resolved service endpoint (services/<domain>/<service>),
  * the payload shape (entity_id + drop-None semantics),
  * that the prefix validation rejects mismatched entity_ids,
  * that range/value validation rejects out-of-bounds args.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import entity_control as ec


def _last(client) -> dict:
    return client.calls[-1]


# ──────────────────────────────────────────────────────────────────── light

class TestLight:
    def test_turn_on_minimal(self, fake_client):
        ec.light_turn_on(fake_client, "light.kitchen")
        c = _last(fake_client)
        assert c["path"] == "services/light/turn_on"
        assert c["payload"] == {"entity_id": "light.kitchen"}

    def test_turn_on_with_brightness(self, fake_client):
        ec.light_turn_on(fake_client, "light.kitchen", brightness=128)
        assert _last(fake_client)["payload"] == {
            "entity_id": "light.kitchen", "brightness": 128,
        }

    def test_turn_on_brightness_out_of_range(self, fake_client):
        with pytest.raises(ValueError, match="brightness"):
            ec.light_turn_on(fake_client, "light.k", brightness=300)

    def test_turn_on_brightness_pct(self, fake_client):
        ec.light_turn_on(fake_client, "light.k", brightness_pct=42.5)
        assert _last(fake_client)["payload"] == {
            "entity_id": "light.k", "brightness_pct": 42.5,
        }

    def test_turn_on_brightness_pct_out_of_range(self, fake_client):
        with pytest.raises(ValueError, match="brightness_pct"):
            ec.light_turn_on(fake_client, "light.k", brightness_pct=101)

    def test_turn_on_kelvin_and_effect(self, fake_client):
        ec.light_turn_on(fake_client, "light.k", kelvin=2700, effect="pulse",
                         transition=2.5)
        assert _last(fake_client)["payload"] == {
            "entity_id": "light.k",
            "kelvin": 2700, "effect": "pulse", "transition": 2.5,
        }

    def test_turn_on_rgb_color_normalized_to_list(self, fake_client):
        ec.light_turn_on(fake_client, "light.k", rgb_color=(255, 128, 0))
        assert _last(fake_client)["payload"]["rgb_color"] == [255, 128, 0]

    def test_turn_on_full_kitchen_sink(self, fake_client):
        ec.light_turn_on(
            fake_client, "light.k",
            brightness=200, color_temp_kelvin=3000,
            rgbw_color=[1, 2, 3, 4], rgbww_color=[1, 2, 3, 4, 5],
            xy_color=[0.3, 0.4], hs_color=[180.0, 50.0],
            color_name="warm_white", flash="short",
            profile="relax", white=128,
        )
        p = _last(fake_client)["payload"]
        assert p["color_temp_kelvin"] == 3000
        assert p["rgbw_color"] == [1, 2, 3, 4]
        assert p["rgbww_color"] == [1, 2, 3, 4, 5]
        assert p["xy_color"] == [0.3, 0.4]
        assert p["hs_color"] == [180.0, 50.0]
        assert p["color_name"] == "warm_white"
        assert p["flash"] == "short"
        assert p["profile"] == "relax"
        assert p["white"] == 128

    def test_turn_off(self, fake_client):
        ec.light_turn_off(fake_client, "light.k")
        c = _last(fake_client)
        assert c["path"] == "services/light/turn_off"
        assert c["payload"] == {"entity_id": "light.k"}

    def test_turn_off_with_transition_and_flash(self, fake_client):
        ec.light_turn_off(fake_client, "light.k", transition=1, flash="long")
        assert _last(fake_client)["payload"] == {
            "entity_id": "light.k", "transition": 1, "flash": "long",
        }

    def test_toggle(self, fake_client):
        ec.light_toggle(fake_client, "light.k", brightness=50, transition=2)
        c = _last(fake_client)
        assert c["path"] == "services/light/toggle"
        assert c["payload"] == {
            "entity_id": "light.k", "brightness": 50, "transition": 2,
        }

    def test_wrong_prefix_rejected(self, fake_client):
        with pytest.raises(ValueError, match="light"):
            ec.light_turn_on(fake_client, "switch.k")


# ──────────────────────────────────────────────────────────────────── media_player

class TestMediaPlayer:
    def test_play(self, fake_client):
        ec.media_player_play(fake_client, "media_player.sonos")
        c = _last(fake_client)
        assert c["path"] == "services/media_player/media_play"
        assert c["payload"] == {"entity_id": "media_player.sonos"}

    def test_pause(self, fake_client):
        ec.media_player_pause(fake_client, "media_player.sonos")
        assert _last(fake_client)["path"] == "services/media_player/media_pause"

    def test_stop(self, fake_client):
        ec.media_player_stop(fake_client, "media_player.sonos")
        assert _last(fake_client)["path"] == "services/media_player/media_stop"

    def test_play_pause(self, fake_client):
        ec.media_player_play_pause(fake_client, "media_player.sonos")
        assert _last(fake_client)["path"] == (
            "services/media_player/media_play_pause"
        )

    def test_next(self, fake_client):
        ec.media_player_next(fake_client, "media_player.sonos")
        assert _last(fake_client)["path"] == (
            "services/media_player/media_next_track"
        )

    def test_previous(self, fake_client):
        ec.media_player_previous(fake_client, "media_player.sonos")
        assert _last(fake_client)["path"] == (
            "services/media_player/media_previous_track"
        )

    def test_volume_set(self, fake_client):
        ec.media_player_volume_set(fake_client, "media_player.sonos", volume=0.4)
        c = _last(fake_client)
        assert c["path"] == "services/media_player/volume_set"
        assert c["payload"] == {
            "entity_id": "media_player.sonos", "volume_level": 0.4,
        }

    def test_volume_out_of_range(self, fake_client):
        with pytest.raises(ValueError, match="volume"):
            ec.media_player_volume_set(fake_client, "media_player.s",
                                       volume=1.5)

    def test_volume_up(self, fake_client):
        ec.media_player_volume_up(fake_client, "media_player.s")
        assert _last(fake_client)["path"] == "services/media_player/volume_up"

    def test_volume_down(self, fake_client):
        ec.media_player_volume_down(fake_client, "media_player.s")
        assert _last(fake_client)["path"] == "services/media_player/volume_down"

    def test_mute_true(self, fake_client):
        ec.media_player_mute(fake_client, "media_player.s", mute=True)
        assert _last(fake_client)["payload"]["is_volume_muted"] is True

    def test_mute_false(self, fake_client):
        ec.media_player_mute(fake_client, "media_player.s", mute=False)
        assert _last(fake_client)["payload"]["is_volume_muted"] is False

    def test_select_source(self, fake_client):
        ec.media_player_select_source(fake_client, "media_player.s",
                                      source="Spotify")
        assert _last(fake_client)["payload"] == {
            "entity_id": "media_player.s", "source": "Spotify",
        }

    def test_select_source_empty(self, fake_client):
        with pytest.raises(ValueError, match="source"):
            ec.media_player_select_source(fake_client, "media_player.s",
                                          source="")

    def test_select_sound_mode(self, fake_client):
        ec.media_player_select_sound_mode(fake_client, "media_player.s",
                                          sound_mode="Movie")
        assert _last(fake_client)["payload"] == {
            "entity_id": "media_player.s", "sound_mode": "Movie",
        }

    def test_play_media_minimal(self, fake_client):
        ec.media_player_play_media(
            fake_client, "media_player.s",
            media_content_id="spotify:track:xyz",
            media_content_type="music",
        )
        assert _last(fake_client)["payload"] == {
            "entity_id": "media_player.s",
            "media_content_id": "spotify:track:xyz",
            "media_content_type": "music",
        }

    def test_play_media_with_enqueue_and_extra(self, fake_client):
        ec.media_player_play_media(
            fake_client, "media_player.s",
            media_content_id="http://foo/bar.mp3",
            media_content_type="music",
            enqueue="add", announce=True,
            extra={"thumb": "http://foo/bar.jpg"},
        )
        p = _last(fake_client)["payload"]
        assert p["enqueue"] == "add"
        assert p["announce"] is True
        assert p["extra"] == {"thumb": "http://foo/bar.jpg"}

    def test_play_media_requires_id(self, fake_client):
        with pytest.raises(ValueError, match="media_content_id"):
            ec.media_player_play_media(
                fake_client, "media_player.s",
                media_content_id="", media_content_type="music",
            )

    def test_play_media_requires_type(self, fake_client):
        with pytest.raises(ValueError, match="media_content_type"):
            ec.media_player_play_media(
                fake_client, "media_player.s",
                media_content_id="x", media_content_type="",
            )

    def test_shuffle(self, fake_client):
        ec.media_player_shuffle(fake_client, "media_player.s", shuffle=True)
        assert _last(fake_client)["payload"]["shuffle"] is True

    def test_repeat(self, fake_client):
        ec.media_player_repeat(fake_client, "media_player.s", repeat="one")
        assert _last(fake_client)["payload"]["repeat"] == "one"

    def test_repeat_invalid(self, fake_client):
        with pytest.raises(ValueError, match="repeat"):
            ec.media_player_repeat(fake_client, "media_player.s",
                                   repeat="forever")

    def test_clear_playlist(self, fake_client):
        ec.media_player_clear_playlist(fake_client, "media_player.s")
        assert _last(fake_client)["path"] == (
            "services/media_player/clear_playlist"
        )

    def test_turn_on(self, fake_client):
        ec.media_player_turn_on(fake_client, "media_player.s")
        assert _last(fake_client)["path"] == "services/media_player/turn_on"

    def test_turn_off(self, fake_client):
        ec.media_player_turn_off(fake_client, "media_player.s")
        assert _last(fake_client)["path"] == "services/media_player/turn_off"

    def test_join(self, fake_client):
        ec.media_player_join(
            fake_client, "media_player.s",
            group_members=["media_player.a", "media_player.b"],
        )
        assert _last(fake_client)["payload"]["group_members"] == [
            "media_player.a", "media_player.b",
        ]

    def test_join_empty_rejected(self, fake_client):
        with pytest.raises(ValueError, match="group_members"):
            ec.media_player_join(fake_client, "media_player.s",
                                 group_members=[])

    def test_unjoin(self, fake_client):
        ec.media_player_unjoin(fake_client, "media_player.s")
        assert _last(fake_client)["path"] == "services/media_player/unjoin"

    def test_wrong_prefix(self, fake_client):
        with pytest.raises(ValueError, match="media_player"):
            ec.media_player_play(fake_client, "light.k")


# ──────────────────────────────────────────────────────────────────── climate

class TestClimate:
    def test_set_temperature_simple(self, fake_client):
        ec.climate_set_temperature(fake_client, "climate.living",
                                   temperature=21.5)
        c = _last(fake_client)
        assert c["path"] == "services/climate/set_temperature"
        assert c["payload"] == {"entity_id": "climate.living",
                                "temperature": 21.5}

    def test_set_temperature_range(self, fake_client):
        ec.climate_set_temperature(
            fake_client, "climate.living",
            target_temp_high=23, target_temp_low=19, hvac_mode="heat_cool",
        )
        assert _last(fake_client)["payload"] == {
            "entity_id": "climate.living",
            "target_temp_high": 23, "target_temp_low": 19,
            "hvac_mode": "heat_cool",
        }

    def test_set_temperature_requires_a_value(self, fake_client):
        with pytest.raises(ValueError, match="temperature"):
            ec.climate_set_temperature(fake_client, "climate.x")

    def test_set_hvac_mode(self, fake_client):
        ec.climate_set_hvac_mode(fake_client, "climate.living",
                                 hvac_mode="cool")
        assert _last(fake_client)["payload"]["hvac_mode"] == "cool"

    def test_set_fan_mode(self, fake_client):
        ec.climate_set_fan_mode(fake_client, "climate.x", fan_mode="auto")
        assert _last(fake_client)["payload"]["fan_mode"] == "auto"

    def test_set_preset(self, fake_client):
        ec.climate_set_preset_mode(fake_client, "climate.x",
                                   preset_mode="eco")
        assert _last(fake_client)["payload"]["preset_mode"] == "eco"

    def test_set_humidity(self, fake_client):
        ec.climate_set_humidity(fake_client, "climate.x", humidity=45)
        assert _last(fake_client)["payload"]["humidity"] == 45

    def test_humidity_out_of_range(self, fake_client):
        with pytest.raises(ValueError, match="humidity"):
            ec.climate_set_humidity(fake_client, "climate.x", humidity=150)

    def test_set_swing(self, fake_client):
        ec.climate_set_swing_mode(fake_client, "climate.x", swing_mode="off")
        assert _last(fake_client)["payload"]["swing_mode"] == "off"

    def test_turn_on(self, fake_client):
        ec.climate_turn_on(fake_client, "climate.x")
        assert _last(fake_client)["path"] == "services/climate/turn_on"

    def test_turn_off(self, fake_client):
        ec.climate_turn_off(fake_client, "climate.x")
        assert _last(fake_client)["path"] == "services/climate/turn_off"

    def test_wrong_prefix(self, fake_client):
        with pytest.raises(ValueError, match="climate"):
            ec.climate_set_hvac_mode(fake_client, "x.y", hvac_mode="cool")


# ──────────────────────────────────────────────────────────────────── cover

class TestCover:
    def test_open(self, fake_client):
        ec.cover_open(fake_client, "cover.garage")
        assert _last(fake_client)["path"] == "services/cover/open_cover"

    def test_close(self, fake_client):
        ec.cover_close(fake_client, "cover.garage")
        assert _last(fake_client)["path"] == "services/cover/close_cover"

    def test_stop(self, fake_client):
        ec.cover_stop(fake_client, "cover.garage")
        assert _last(fake_client)["path"] == "services/cover/stop_cover"

    def test_toggle(self, fake_client):
        ec.cover_toggle(fake_client, "cover.garage")
        assert _last(fake_client)["path"] == "services/cover/toggle"

    def test_set_position(self, fake_client):
        ec.cover_set_position(fake_client, "cover.garage", position=50)
        assert _last(fake_client)["payload"] == {
            "entity_id": "cover.garage", "position": 50,
        }

    def test_position_range(self, fake_client):
        with pytest.raises(ValueError, match="position"):
            ec.cover_set_position(fake_client, "cover.x", position=-1)

    def test_set_tilt(self, fake_client):
        ec.cover_set_tilt(fake_client, "cover.x", tilt_position=25)
        assert _last(fake_client)["payload"]["tilt_position"] == 25

    def test_tilt_range(self, fake_client):
        with pytest.raises(ValueError, match="tilt_position"):
            ec.cover_set_tilt(fake_client, "cover.x", tilt_position=200)

    def test_tilt_open_close_stop(self, fake_client):
        ec.cover_open_tilt(fake_client, "cover.x")
        ec.cover_close_tilt(fake_client, "cover.x")
        ec.cover_stop_tilt(fake_client, "cover.x")
        paths = [c["path"] for c in fake_client.calls[-3:]]
        assert paths == [
            "services/cover/open_cover_tilt",
            "services/cover/close_cover_tilt",
            "services/cover/stop_cover_tilt",
        ]

    def test_wrong_prefix(self, fake_client):
        with pytest.raises(ValueError, match="cover"):
            ec.cover_open(fake_client, "light.x")


# ──────────────────────────────────────────────────────────────────── fan

class TestFan:
    def test_turn_on_minimal(self, fake_client):
        ec.fan_turn_on(fake_client, "fan.bedroom")
        assert _last(fake_client)["payload"] == {"entity_id": "fan.bedroom"}

    def test_turn_on_with_percentage(self, fake_client):
        ec.fan_turn_on(fake_client, "fan.x", percentage=75)
        assert _last(fake_client)["payload"] == {
            "entity_id": "fan.x", "percentage": 75,
        }

    def test_turn_on_percentage_out_of_range(self, fake_client):
        with pytest.raises(ValueError, match="percentage"):
            ec.fan_turn_on(fake_client, "fan.x", percentage=200)

    def test_turn_on_with_preset(self, fake_client):
        ec.fan_turn_on(fake_client, "fan.x", preset_mode="auto")
        assert _last(fake_client)["payload"]["preset_mode"] == "auto"

    def test_turn_off(self, fake_client):
        ec.fan_turn_off(fake_client, "fan.x")
        assert _last(fake_client)["path"] == "services/fan/turn_off"

    def test_toggle(self, fake_client):
        ec.fan_toggle(fake_client, "fan.x")
        assert _last(fake_client)["path"] == "services/fan/toggle"

    def test_set_percentage(self, fake_client):
        ec.fan_set_percentage(fake_client, "fan.x", percentage=50)
        assert _last(fake_client)["payload"]["percentage"] == 50

    def test_set_preset(self, fake_client):
        ec.fan_set_preset(fake_client, "fan.x", preset_mode="boost")
        assert _last(fake_client)["payload"]["preset_mode"] == "boost"

    def test_set_direction_forward(self, fake_client):
        ec.fan_set_direction(fake_client, "fan.x", direction="forward")
        assert _last(fake_client)["payload"]["direction"] == "forward"

    def test_set_direction_invalid(self, fake_client):
        with pytest.raises(ValueError, match="direction"):
            ec.fan_set_direction(fake_client, "fan.x", direction="sideways")

    def test_oscillate(self, fake_client):
        ec.fan_oscillate(fake_client, "fan.x", oscillating=True)
        assert _last(fake_client)["payload"]["oscillating"] is True

    def test_increase_step(self, fake_client):
        ec.fan_increase(fake_client, "fan.x", percentage_step=10)
        assert _last(fake_client)["payload"]["percentage_step"] == 10

    def test_decrease_no_step(self, fake_client):
        ec.fan_decrease(fake_client, "fan.x")
        assert _last(fake_client)["payload"] == {"entity_id": "fan.x"}


# ──────────────────────────────────────────────────────────────────── vacuum

class TestVacuum:
    def test_start_stop_pause(self, fake_client):
        ec.vacuum_start(fake_client, "vacuum.roomba")
        ec.vacuum_stop(fake_client, "vacuum.roomba")
        ec.vacuum_pause(fake_client, "vacuum.roomba")
        paths = [c["path"] for c in fake_client.calls[-3:]]
        assert paths == [
            "services/vacuum/start", "services/vacuum/stop",
            "services/vacuum/pause",
        ]

    def test_return_to_base(self, fake_client):
        ec.vacuum_return_to_base(fake_client, "vacuum.roomba")
        assert _last(fake_client)["path"] == "services/vacuum/return_to_base"

    def test_locate(self, fake_client):
        ec.vacuum_locate(fake_client, "vacuum.x")
        assert _last(fake_client)["path"] == "services/vacuum/locate"

    def test_clean_spot(self, fake_client):
        ec.vacuum_clean_spot(fake_client, "vacuum.x")
        assert _last(fake_client)["path"] == "services/vacuum/clean_spot"

    def test_set_fan_speed(self, fake_client):
        ec.vacuum_set_fan_speed(fake_client, "vacuum.x", fan_speed="high")
        assert _last(fake_client)["payload"]["fan_speed"] == "high"

    def test_send_command(self, fake_client):
        ec.vacuum_send_command(fake_client, "vacuum.x",
                               command="ping", params={"foo": "bar"})
        assert _last(fake_client)["payload"] == {
            "entity_id": "vacuum.x", "command": "ping",
            "params": {"foo": "bar"},
        }

    def test_send_command_empty(self, fake_client):
        with pytest.raises(ValueError, match="command"):
            ec.vacuum_send_command(fake_client, "vacuum.x", command="")


# ──────────────────────────────────────────────────────────────────── humidifier

class TestHumidifier:
    def test_on_off_toggle(self, fake_client):
        ec.humidifier_turn_on(fake_client, "humidifier.x")
        ec.humidifier_turn_off(fake_client, "humidifier.x")
        ec.humidifier_toggle(fake_client, "humidifier.x")
        paths = [c["path"] for c in fake_client.calls[-3:]]
        assert paths == [
            "services/humidifier/turn_on",
            "services/humidifier/turn_off",
            "services/humidifier/toggle",
        ]

    def test_set_humidity(self, fake_client):
        ec.humidifier_set_humidity(fake_client, "humidifier.x", humidity=55)
        assert _last(fake_client)["payload"]["humidity"] == 55

    def test_set_mode(self, fake_client):
        ec.humidifier_set_mode(fake_client, "humidifier.x", mode="auto")
        assert _last(fake_client)["payload"]["mode"] == "auto"

    def test_humidity_out_of_range(self, fake_client):
        with pytest.raises(ValueError, match="humidity"):
            ec.humidifier_set_humidity(fake_client, "humidifier.x",
                                       humidity=101)


# ──────────────────────────────────────────────────────────────────── water_heater

class TestWaterHeater:
    def test_on_off(self, fake_client):
        ec.water_heater_turn_on(fake_client, "water_heater.x")
        ec.water_heater_turn_off(fake_client, "water_heater.x")
        paths = [c["path"] for c in fake_client.calls[-2:]]
        assert paths == [
            "services/water_heater/turn_on",
            "services/water_heater/turn_off",
        ]

    def test_set_temperature(self, fake_client):
        ec.water_heater_set_temperature(fake_client, "water_heater.x",
                                        temperature=60)
        assert _last(fake_client)["payload"]["temperature"] == 60

    def test_set_operation_mode(self, fake_client):
        ec.water_heater_set_operation_mode(fake_client, "water_heater.x",
                                           operation_mode="electric")
        assert _last(fake_client)["payload"]["operation_mode"] == "electric"

    def test_set_away_mode(self, fake_client):
        ec.water_heater_set_away_mode(fake_client, "water_heater.x",
                                      away_mode=True)
        assert _last(fake_client)["payload"]["away_mode"] is True


# ──────────────────────────────────────────────────────────────────── valve

class TestValve:
    def test_open_close_stop_toggle(self, fake_client):
        ec.valve_open(fake_client, "valve.x")
        ec.valve_close(fake_client, "valve.x")
        ec.valve_stop(fake_client, "valve.x")
        ec.valve_toggle(fake_client, "valve.x")
        paths = [c["path"] for c in fake_client.calls[-4:]]
        assert paths == [
            "services/valve/open_valve",
            "services/valve/close_valve",
            "services/valve/stop_valve",
            "services/valve/toggle",
        ]

    def test_set_position(self, fake_client):
        ec.valve_set_position(fake_client, "valve.x", position=75)
        assert _last(fake_client)["payload"]["position"] == 75


# ──────────────────────────────────────────────────────────────────── lawn_mower

class TestLawnMower:
    def test_all(self, fake_client):
        ec.lawn_mower_start(fake_client, "lawn_mower.x")
        ec.lawn_mower_pause(fake_client, "lawn_mower.x")
        ec.lawn_mower_dock(fake_client, "lawn_mower.x")
        paths = [c["path"] for c in fake_client.calls[-3:]]
        assert paths == [
            "services/lawn_mower/start_mowing",
            "services/lawn_mower/pause",
            "services/lawn_mower/dock",
        ]


# ──────────────────────────────────────────────────────────────────── siren

class TestSiren:
    def test_on_minimal(self, fake_client):
        ec.siren_turn_on(fake_client, "siren.x")
        assert _last(fake_client)["payload"] == {"entity_id": "siren.x"}

    def test_on_full(self, fake_client):
        ec.siren_turn_on(fake_client, "siren.x", duration=5,
                         tone="alarm", volume_level=0.8)
        assert _last(fake_client)["payload"] == {
            "entity_id": "siren.x",
            "duration": 5, "tone": "alarm", "volume_level": 0.8,
        }

    def test_volume_out_of_range(self, fake_client):
        with pytest.raises(ValueError, match="volume_level"):
            ec.siren_turn_on(fake_client, "siren.x", volume_level=2)

    def test_off_toggle(self, fake_client):
        ec.siren_turn_off(fake_client, "siren.x")
        ec.siren_toggle(fake_client, "siren.x")
        paths = [c["path"] for c in fake_client.calls[-2:]]
        assert paths == ["services/siren/turn_off", "services/siren/toggle"]


# ──────────────────────────────────────────────────────────────────── remote

class TestRemote:
    def test_turn_on_with_activity(self, fake_client):
        ec.remote_turn_on(fake_client, "remote.harmony", activity="TV")
        assert _last(fake_client)["payload"] == {
            "entity_id": "remote.harmony", "activity": "TV",
        }

    def test_turn_off_toggle(self, fake_client):
        ec.remote_turn_off(fake_client, "remote.x")
        ec.remote_toggle(fake_client, "remote.x")
        paths = [c["path"] for c in fake_client.calls[-2:]]
        assert paths == [
            "services/remote/turn_off", "services/remote/toggle",
        ]

    def test_send_command_simple(self, fake_client):
        ec.remote_send_command(fake_client, "remote.x", command="VolumeUp",
                               device="receiver")
        assert _last(fake_client)["payload"] == {
            "entity_id": "remote.x", "command": "VolumeUp",
            "device": "receiver",
        }

    def test_send_command_list(self, fake_client):
        ec.remote_send_command(
            fake_client, "remote.x",
            command=["VolumeUp", "VolumeUp"], num_repeats=2, delay_secs=0.5,
            hold_secs=0.1,
        )
        p = _last(fake_client)["payload"]
        assert p["command"] == ["VolumeUp", "VolumeUp"]
        assert p["num_repeats"] == 2
        assert p["delay_secs"] == 0.5
        assert p["hold_secs"] == 0.1

    def test_send_command_empty(self, fake_client):
        with pytest.raises(ValueError, match="command"):
            ec.remote_send_command(fake_client, "remote.x", command="")

    def test_learn_command(self, fake_client):
        ec.remote_learn_command(
            fake_client, "remote.x",
            command="Foo", device="tv", command_type="ir",
            alternative=True, timeout=10,
        )
        p = _last(fake_client)["payload"]
        assert p["command"] == "Foo"
        assert p["command_type"] == "ir"
        assert p["alternative"] is True

    def test_delete_command(self, fake_client):
        ec.remote_delete_command(fake_client, "remote.x", command="Foo")
        assert _last(fake_client)["payload"]["command"] == "Foo"


# ──────────────────────────────────────────────────────────────────── number

class TestNumber:
    def test_set_value(self, fake_client):
        ec.number_set_value(fake_client, "number.x", value=12.5)
        c = _last(fake_client)
        assert c["path"] == "services/number/set_value"
        assert c["payload"] == {"entity_id": "number.x", "value": 12.5}

    def test_wrong_prefix(self, fake_client):
        with pytest.raises(ValueError, match="number"):
            ec.number_set_value(fake_client, "input_number.x", value=1)


# ──────────────────────────────────────────────────────────────────── select

class TestSelect:
    def test_select_option(self, fake_client):
        ec.select_select_option(fake_client, "select.x", option="Auto")
        c = _last(fake_client)
        assert c["path"] == "services/select/select_option"
        assert c["payload"] == {"entity_id": "select.x", "option": "Auto"}

    def test_option_required(self, fake_client):
        with pytest.raises(ValueError, match="option"):
            ec.select_select_option(fake_client, "select.x", option="")

    def test_next_previous(self, fake_client):
        ec.select_next(fake_client, "select.x", cycle=True)
        ec.select_previous(fake_client, "select.x")
        last_two = fake_client.calls[-2:]
        assert last_two[0]["path"] == "services/select/select_next"
        assert last_two[0]["payload"] == {"entity_id": "select.x",
                                          "cycle": True}
        assert last_two[1]["path"] == "services/select/select_previous"
        assert last_two[1]["payload"] == {"entity_id": "select.x"}

    def test_first_last(self, fake_client):
        ec.select_first(fake_client, "select.x")
        ec.select_last(fake_client, "select.x")
        paths = [c["path"] for c in fake_client.calls[-2:]]
        assert paths == [
            "services/select/select_first", "services/select/select_last",
        ]


# ──────────────────────────────────────────────────────────────────── button

class TestButton:
    def test_press(self, fake_client):
        ec.button_press(fake_client, "button.doorbell")
        c = _last(fake_client)
        assert c["path"] == "services/button/press"
        assert c["payload"] == {"entity_id": "button.doorbell"}

    def test_wrong_prefix(self, fake_client):
        with pytest.raises(ValueError, match="button"):
            ec.button_press(fake_client, "input_button.x")


# ──────────────────────────────────────────────────────────────────── text

class TestText:
    def test_set_value(self, fake_client):
        ec.text_set_value(fake_client, "text.x", value="hello")
        c = _last(fake_client)
        assert c["path"] == "services/text/set_value"
        assert c["payload"] == {"entity_id": "text.x", "value": "hello"}

    def test_empty_string_ok(self, fake_client):
        ec.text_set_value(fake_client, "text.x", value="")
        assert _last(fake_client)["payload"]["value"] == ""


# ──────────────────────────────────────────────────────────────────── notify

class TestNotifySend:
    def test_minimal(self, fake_client):
        ec.notify_send(fake_client, message="hi")
        c = _last(fake_client)
        assert c["path"] == "services/notify/notify"
        assert c["payload"] == {"message": "hi"}

    def test_custom_service(self, fake_client):
        ec.notify_send(fake_client, message="hi", service="telegram")
        assert _last(fake_client)["path"] == "services/notify/telegram"

    def test_all_fields(self, fake_client):
        ec.notify_send(
            fake_client, message="hi", title="t",
            target=["a", "b"], data={"channel": "c"}, service="email",
        )
        assert _last(fake_client)["payload"] == {
            "message": "hi", "title": "t",
            "target": ["a", "b"], "data": {"channel": "c"},
        }

    def test_empty_message(self, fake_client):
        with pytest.raises(ValueError, match="message"):
            ec.notify_send(fake_client, message="")

    def test_empty_service(self, fake_client):
        with pytest.raises(ValueError, match="service"):
            ec.notify_send(fake_client, message="hi", service="")
