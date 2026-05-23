"""CLI wiring tests for the entity-control refine pass.

Exercises every shortcut group/command registered in homeassistant_cli.py
through Click's CliRunner and asserts that the resulting HA service call
matches what the core function would have emitted.
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
    return runner.invoke(cli_mod.cli, full,
                         obj={
                             "url": "http://x", "token": "t",
                             "verify_ssl": False, "timeout": 5,
                             "as_json": json_out, "config_path": None,
                         })


def _last_service(fake_client) -> dict:
    return fake_client.service_calls[-1]


# ──────────────────────────────────────────────────────────────── light

class TestLightWiring:
    def test_on_minimal(self, runner, fake_client):
        r = _invoke(runner, "light", "on", "light.kitchen")
        assert r.exit_code == 0, r.output
        s = _last_service(fake_client)
        assert (s["domain"], s["service"]) == ("light", "turn_on")
        assert s["service_data"] == {"entity_id": "light.kitchen"}

    def test_on_all_args(self, runner, fake_client):
        r = _invoke(runner, "light", "on", "light.kitchen",
                    "--brightness", "200",
                    "--kelvin", "2700",
                    "--rgb", "255,128,0",
                    "--transition", "1.5",
                    "--effect", "pulse",
                    "--flash", "short")
        assert r.exit_code == 0, r.output
        d = _last_service(fake_client)["service_data"]
        assert d["brightness"] == 200
        assert d["kelvin"] == 2700
        assert d["rgb_color"] == [255, 128, 0]
        assert d["transition"] == 1.5
        assert d["effect"] == "pulse"
        assert d["flash"] == "short"

    def test_off(self, runner, fake_client):
        r = _invoke(runner, "light", "off", "light.k", "--transition", "0.5")
        assert r.exit_code == 0, r.output
        s = _last_service(fake_client)
        assert (s["domain"], s["service"]) == ("light", "turn_off")
        assert s["service_data"]["transition"] == 0.5

    def test_toggle(self, runner, fake_client):
        r = _invoke(runner, "light", "toggle", "light.k", "--brightness-pct", "50")
        assert r.exit_code == 0, r.output
        s = _last_service(fake_client)
        assert s["service"] == "toggle"
        assert s["service_data"]["brightness_pct"] == 50.0


# ──────────────────────────────────────────────────────────── media-player

class TestMediaPlayerWiring:
    def test_play(self, runner, fake_client):
        r = _invoke(runner, "media-player", "play", "media_player.sonos")
        assert r.exit_code == 0, r.output
        s = _last_service(fake_client)
        assert (s["domain"], s["service"]) == ("media_player", "media_play")

    def test_pause_stop_next_prev(self, runner, fake_client):
        for cmd, expected in [
            ("pause", "media_pause"),
            ("stop", "media_stop"),
            ("next", "media_next_track"),
            ("previous", "media_previous_track"),
            ("play-pause", "media_play_pause"),
        ]:
            r = _invoke(runner, "media-player", cmd, "media_player.s")
            assert r.exit_code == 0, r.output
            assert _last_service(fake_client)["service"] == expected

    def test_volume_set(self, runner, fake_client):
        r = _invoke(runner, "media-player", "volume-set",
                    "media_player.s", "0.35")
        assert r.exit_code == 0, r.output
        d = _last_service(fake_client)["service_data"]
        assert d["volume_level"] == 0.35

    def test_volume_up_down(self, runner, fake_client):
        _invoke(runner, "media-player", "volume-up", "media_player.s")
        _invoke(runner, "media-player", "volume-down", "media_player.s")
        last_two = fake_client.service_calls[-2:]
        assert [c["service"] for c in last_two] == ["volume_up", "volume_down"]

    def test_mute_default_and_off(self, runner, fake_client):
        _invoke(runner, "media-player", "mute", "media_player.s")
        assert _last_service(fake_client)["service_data"][
            "is_volume_muted"] is True
        _invoke(runner, "media-player", "mute", "media_player.s", "--off")
        assert _last_service(fake_client)["service_data"][
            "is_volume_muted"] is False

    def test_select_source(self, runner, fake_client):
        r = _invoke(runner, "media-player", "select-source",
                    "media_player.s", "Spotify")
        assert r.exit_code == 0, r.output
        assert _last_service(fake_client)["service_data"]["source"] == "Spotify"

    def test_select_sound_mode(self, runner, fake_client):
        r = _invoke(runner, "media-player", "select-sound-mode",
                    "media_player.s", "Movie")
        assert r.exit_code == 0, r.output
        assert _last_service(fake_client)["service_data"][
            "sound_mode"] == "Movie"

    def test_play_media(self, runner, fake_client):
        r = _invoke(runner, "media-player", "play-media",
                    "media_player.s",
                    "spotify:track:xyz", "music",
                    "--enqueue", "add",
                    "--extra", '{"thumb":"http://x.jpg"}')
        assert r.exit_code == 0, r.output
        d = _last_service(fake_client)["service_data"]
        assert d["media_content_id"] == "spotify:track:xyz"
        assert d["media_content_type"] == "music"
        assert d["enqueue"] == "add"
        assert d["extra"] == {"thumb": "http://x.jpg"}

    def test_shuffle(self, runner, fake_client):
        _invoke(runner, "media-player", "shuffle", "media_player.s")
        assert _last_service(fake_client)["service_data"]["shuffle"] is True
        _invoke(runner, "media-player", "shuffle", "media_player.s", "--off")
        assert _last_service(fake_client)["service_data"]["shuffle"] is False

    def test_repeat(self, runner, fake_client):
        r = _invoke(runner, "media-player", "repeat",
                    "media_player.s", "one")
        assert r.exit_code == 0, r.output
        assert _last_service(fake_client)["service_data"]["repeat"] == "one"

    def test_clear_playlist_turn_on_off(self, runner, fake_client):
        _invoke(runner, "media-player", "clear-playlist", "media_player.s")
        _invoke(runner, "media-player", "turn-on", "media_player.s")
        _invoke(runner, "media-player", "turn-off", "media_player.s")
        last_three = fake_client.service_calls[-3:]
        assert [c["service"] for c in last_three] == [
            "clear_playlist", "turn_on", "turn_off",
        ]

    def test_join_unjoin(self, runner, fake_client):
        r = _invoke(runner, "media-player", "join", "media_player.s",
                    "--member", "media_player.a",
                    "--member", "media_player.b")
        assert r.exit_code == 0, r.output
        assert _last_service(fake_client)["service_data"]["group_members"] == [
            "media_player.a", "media_player.b",
        ]
        _invoke(runner, "media-player", "unjoin", "media_player.s")
        assert _last_service(fake_client)["service"] == "unjoin"


# ──────────────────────────────────────────────────────────── climate

class TestClimateWiring:
    def test_set_temperature(self, runner, fake_client):
        r = _invoke(runner, "climate", "set-temperature", "climate.living",
                    "-t", "21.5")
        assert r.exit_code == 0, r.output
        d = _last_service(fake_client)["service_data"]
        assert d == {"entity_id": "climate.living", "temperature": 21.5}

    def test_set_temperature_range_and_mode(self, runner, fake_client):
        r = _invoke(runner, "climate", "set-temperature", "climate.living",
                    "--high", "23", "--low", "19",
                    "--hvac-mode", "heat_cool")
        assert r.exit_code == 0, r.output
        d = _last_service(fake_client)["service_data"]
        assert d["target_temp_high"] == 23
        assert d["target_temp_low"] == 19
        assert d["hvac_mode"] == "heat_cool"

    def test_set_hvac_mode(self, runner, fake_client):
        r = _invoke(runner, "climate", "set-hvac-mode", "climate.x", "cool")
        assert r.exit_code == 0, r.output
        assert _last_service(fake_client)["service_data"]["hvac_mode"] == "cool"

    def test_set_fan_preset_humidity_swing(self, runner, fake_client):
        for cmd, val, key in [
            ("set-fan-mode", "auto", "fan_mode"),
            ("set-preset", "eco", "preset_mode"),
            ("set-humidity", "45", "humidity"),
            ("set-swing", "vertical", "swing_mode"),
        ]:
            r = _invoke(runner, "climate", cmd, "climate.x", val)
            assert r.exit_code == 0, r.output
            d = _last_service(fake_client)["service_data"]
            assert d[key] == (int(val) if key == "humidity" else val)

    def test_turn_on_off(self, runner, fake_client):
        _invoke(runner, "climate", "turn-on", "climate.x")
        _invoke(runner, "climate", "turn-off", "climate.x")
        last_two = fake_client.service_calls[-2:]
        assert [c["service"] for c in last_two] == ["turn_on", "turn_off"]


# ──────────────────────────────────────────────────────────── cover

class TestCoverWiring:
    def test_open_close_stop_toggle(self, runner, fake_client):
        mapping = {
            "open": "open_cover", "close": "close_cover",
            "stop": "stop_cover", "toggle": "toggle",
        }
        for cli_cmd, svc in mapping.items():
            r = _invoke(runner, "cover", cli_cmd, "cover.x")
            assert r.exit_code == 0, r.output
            assert _last_service(fake_client)["service"] == svc

    def test_set_position(self, runner, fake_client):
        r = _invoke(runner, "cover", "set-position", "cover.x", "75")
        assert r.exit_code == 0, r.output
        assert _last_service(fake_client)["service_data"]["position"] == 75

    def test_tilt_ops(self, runner, fake_client):
        r = _invoke(runner, "cover", "set-tilt", "cover.x", "30")
        assert r.exit_code == 0, r.output
        assert _last_service(fake_client)["service_data"][
            "tilt_position"] == 30

        _invoke(runner, "cover", "open-tilt", "cover.x")
        _invoke(runner, "cover", "close-tilt", "cover.x")
        _invoke(runner, "cover", "stop-tilt", "cover.x")
        last_three = fake_client.service_calls[-3:]
        assert [c["service"] for c in last_three] == [
            "open_cover_tilt", "close_cover_tilt", "stop_cover_tilt",
        ]


# ──────────────────────────────────────────────────────────── fan

class TestFanWiring:
    def test_on_off_toggle(self, runner, fake_client):
        _invoke(runner, "fan", "turn-on", "fan.x")
        _invoke(runner, "fan", "turn-off", "fan.x")
        _invoke(runner, "fan", "toggle", "fan.x")
        last_three = fake_client.service_calls[-3:]
        assert [c["service"] for c in last_three] == [
            "turn_on", "turn_off", "toggle",
        ]

    def test_set_percentage(self, runner, fake_client):
        r = _invoke(runner, "fan", "set-percentage", "fan.x", "60")
        assert r.exit_code == 0, r.output
        assert _last_service(fake_client)["service_data"]["percentage"] == 60

    def test_set_preset(self, runner, fake_client):
        r = _invoke(runner, "fan", "set-preset", "fan.x", "boost")
        assert r.exit_code == 0, r.output
        assert _last_service(fake_client)["service_data"][
            "preset_mode"] == "boost"

    def test_set_direction(self, runner, fake_client):
        r = _invoke(runner, "fan", "set-direction", "fan.x", "reverse")
        assert r.exit_code == 0, r.output
        assert _last_service(fake_client)["service_data"][
            "direction"] == "reverse"

    def test_oscillate(self, runner, fake_client):
        _invoke(runner, "fan", "oscillate", "fan.x")
        assert _last_service(fake_client)["service_data"][
            "oscillating"] is True

    def test_increase_decrease(self, runner, fake_client):
        _invoke(runner, "fan", "increase", "fan.x", "--step", "10")
        assert _last_service(fake_client)["service"] == "increase_speed"
        assert _last_service(fake_client)["service_data"][
            "percentage_step"] == 10
        _invoke(runner, "fan", "decrease", "fan.x")
        assert _last_service(fake_client)["service"] == "decrease_speed"


# ──────────────────────────────────────────────────────────── vacuum

class TestVacuumWiring:
    def test_lifecycle(self, runner, fake_client):
        for cmd, svc in [
            ("start", "start"), ("stop", "stop"), ("pause", "pause"),
            ("return-to-base", "return_to_base"), ("locate", "locate"),
            ("clean-spot", "clean_spot"),
        ]:
            r = _invoke(runner, "vacuum", cmd, "vacuum.x")
            assert r.exit_code == 0, r.output
            assert _last_service(fake_client)["service"] == svc

    def test_set_fan_speed(self, runner, fake_client):
        r = _invoke(runner, "vacuum", "set-fan-speed", "vacuum.x", "high")
        assert r.exit_code == 0, r.output
        assert _last_service(fake_client)["service_data"]["fan_speed"] == "high"

    def test_send_command(self, runner, fake_client):
        r = _invoke(runner, "vacuum", "send-command", "vacuum.x", "ping",
                    "--params", '{"x":1}')
        assert r.exit_code == 0, r.output
        d = _last_service(fake_client)["service_data"]
        assert d["command"] == "ping"
        assert d["params"] == {"x": 1}


# ──────────────────────────────────────────────────────────── humidifier

class TestHumidifierWiring:
    def test_all(self, runner, fake_client):
        _invoke(runner, "humidifier", "turn-on", "humidifier.x")
        _invoke(runner, "humidifier", "turn-off", "humidifier.x")
        _invoke(runner, "humidifier", "toggle", "humidifier.x")
        last_three = fake_client.service_calls[-3:]
        assert [c["service"] for c in last_three] == [
            "turn_on", "turn_off", "toggle",
        ]

        r = _invoke(runner, "humidifier", "set-humidity", "humidifier.x", "55")
        assert r.exit_code == 0, r.output
        assert _last_service(fake_client)["service_data"]["humidity"] == 55

        r = _invoke(runner, "humidifier", "set-mode", "humidifier.x", "auto")
        assert r.exit_code == 0, r.output
        assert _last_service(fake_client)["service_data"]["mode"] == "auto"


# ──────────────────────────────────────────────────────────── water-heater

class TestWaterHeaterWiring:
    def test_all(self, runner, fake_client):
        _invoke(runner, "water-heater", "turn-on", "water_heater.x")
        _invoke(runner, "water-heater", "turn-off", "water_heater.x")
        last_two = fake_client.service_calls[-2:]
        assert [c["service"] for c in last_two] == ["turn_on", "turn_off"]

        r = _invoke(runner, "water-heater", "set-temperature",
                    "water_heater.x", "60")
        assert r.exit_code == 0, r.output
        assert _last_service(fake_client)["service_data"]["temperature"] == 60

        r = _invoke(runner, "water-heater", "set-operation-mode",
                    "water_heater.x", "heat_pump")
        assert r.exit_code == 0, r.output
        assert _last_service(fake_client)["service_data"][
            "operation_mode"] == "heat_pump"

        _invoke(runner, "water-heater", "set-away-mode", "water_heater.x")
        assert _last_service(fake_client)["service_data"][
            "away_mode"] is True
        _invoke(runner, "water-heater", "set-away-mode", "water_heater.x",
                "--off")
        assert _last_service(fake_client)["service_data"][
            "away_mode"] is False


# ──────────────────────────────────────────────────────────── valve

class TestValveWiring:
    def test_all(self, runner, fake_client):
        mapping = {
            "open": "open_valve", "close": "close_valve",
            "stop": "stop_valve", "toggle": "toggle",
        }
        for cli_cmd, svc in mapping.items():
            r = _invoke(runner, "valve", cli_cmd, "valve.x")
            assert r.exit_code == 0, r.output
            assert _last_service(fake_client)["service"] == svc

        r = _invoke(runner, "valve", "set-position", "valve.x", "40")
        assert r.exit_code == 0, r.output
        assert _last_service(fake_client)["service_data"]["position"] == 40


# ──────────────────────────────────────────────────────────── lawn-mower

class TestLawnMowerWiring:
    def test_all(self, runner, fake_client):
        for cmd, svc in [
            ("start", "start_mowing"), ("pause", "pause"), ("dock", "dock"),
        ]:
            r = _invoke(runner, "lawn-mower", cmd, "lawn_mower.x")
            assert r.exit_code == 0, r.output
            assert _last_service(fake_client)["service"] == svc


# ──────────────────────────────────────────────────────────── siren

class TestSirenWiring:
    def test_on_minimal(self, runner, fake_client):
        r = _invoke(runner, "siren", "on", "siren.x")
        assert r.exit_code == 0, r.output
        d = _last_service(fake_client)["service_data"]
        assert d == {"entity_id": "siren.x"}

    def test_on_with_opts(self, runner, fake_client):
        r = _invoke(runner, "siren", "on", "siren.x",
                    "--duration", "5",
                    "--tone", "alarm",
                    "--volume", "0.7")
        assert r.exit_code == 0, r.output
        d = _last_service(fake_client)["service_data"]
        assert d["duration"] == 5
        assert d["tone"] == "alarm"
        assert d["volume_level"] == 0.7

    def test_off_toggle(self, runner, fake_client):
        _invoke(runner, "siren", "off", "siren.x")
        _invoke(runner, "siren", "toggle", "siren.x")
        last_two = fake_client.service_calls[-2:]
        assert [c["service"] for c in last_two] == ["turn_off", "toggle"]


# ──────────────────────────────────────────────────────────── remote

class TestRemoteWiring:
    def test_turn_on_off_toggle(self, runner, fake_client):
        _invoke(runner, "remote", "turn-on", "remote.x",
                "--activity", "Movie")
        assert _last_service(fake_client)["service_data"][
            "activity"] == "Movie"
        _invoke(runner, "remote", "turn-off", "remote.x")
        _invoke(runner, "remote", "toggle", "remote.x")
        last_two = fake_client.service_calls[-2:]
        assert [c["service"] for c in last_two] == ["turn_off", "toggle"]

    def test_send_command_single(self, runner, fake_client):
        r = _invoke(runner, "remote", "send-command", "remote.x",
                    "-c", "VolumeUp", "--device", "tv",
                    "--num-repeats", "2")
        assert r.exit_code == 0, r.output
        d = _last_service(fake_client)["service_data"]
        assert d["command"] == "VolumeUp"
        assert d["device"] == "tv"
        assert d["num_repeats"] == 2

    def test_send_command_multi(self, runner, fake_client):
        r = _invoke(runner, "remote", "send-command", "remote.x",
                    "-c", "Up", "-c", "Down")
        assert r.exit_code == 0, r.output
        assert _last_service(fake_client)["service_data"]["command"] == [
            "Up", "Down",
        ]

    def test_learn_command(self, runner, fake_client):
        r = _invoke(runner, "remote", "learn-command", "remote.x",
                    "-c", "Foo", "--device", "tv",
                    "--command-type", "ir", "--timeout", "10")
        assert r.exit_code == 0, r.output
        d = _last_service(fake_client)["service_data"]
        assert d["command"] == "Foo"
        assert d["command_type"] == "ir"
        assert d["timeout"] == 10

    def test_delete_command(self, runner, fake_client):
        r = _invoke(runner, "remote", "delete-command", "remote.x",
                    "-c", "Foo")
        assert r.exit_code == 0, r.output
        assert _last_service(fake_client)["service_data"]["command"] == "Foo"


# ──────────────────────────────────────────────────────────── number

class TestNumberWiring:
    def test_set(self, runner, fake_client):
        r = _invoke(runner, "number", "set", "number.x", "12.5")
        assert r.exit_code == 0, r.output
        s = _last_service(fake_client)
        assert s["service"] == "set_value"
        assert s["service_data"]["value"] == 12.5


# ──────────────────────────────────────────────────────────── select

class TestSelectWiring:
    def test_set_next_prev_first_last(self, runner, fake_client):
        r = _invoke(runner, "select", "set", "select.x", "Auto")
        assert r.exit_code == 0, r.output
        assert _last_service(fake_client)["service_data"]["option"] == "Auto"

        _invoke(runner, "select", "next", "select.x", "--cycle")
        assert _last_service(fake_client)["service_data"]["cycle"] is True

        _invoke(runner, "select", "previous", "select.x")
        assert _last_service(fake_client)["service"] == "select_previous"

        _invoke(runner, "select", "first", "select.x")
        _invoke(runner, "select", "last", "select.x")
        last_two = fake_client.service_calls[-2:]
        assert [c["service"] for c in last_two] == [
            "select_first", "select_last",
        ]


# ──────────────────────────────────────────────────────────── button

class TestButtonWiring:
    def test_press(self, runner, fake_client):
        r = _invoke(runner, "button", "press", "button.doorbell")
        assert r.exit_code == 0, r.output
        s = _last_service(fake_client)
        assert (s["domain"], s["service"]) == ("button", "press")
        assert s["service_data"] == {"entity_id": "button.doorbell"}


# ──────────────────────────────────────────────────────────── text

class TestTextWiring:
    def test_set(self, runner, fake_client):
        r = _invoke(runner, "text", "set", "text.label", "hello world")
        assert r.exit_code == 0, r.output
        d = _last_service(fake_client)["service_data"]
        assert d == {"entity_id": "text.label", "value": "hello world"}


# ──────────────────────────────────────────────────────────── notify

class TestNotifyWiring:
    def test_send_minimal(self, runner, fake_client):
        r = _invoke(runner, "notify", "send", "hi")
        assert r.exit_code == 0, r.output
        s = _last_service(fake_client)
        assert (s["domain"], s["service"]) == ("notify", "notify")
        assert s["service_data"] == {"message": "hi"}

    def test_send_full(self, runner, fake_client):
        r = _invoke(runner, "notify", "send", "Alert",
                    "--title", "Heads up",
                    "--service", "mobile_app_jon",
                    "--target", "device1",
                    "--target", "device2",
                    "--data", '{"channel":"alarm"}')
        assert r.exit_code == 0, r.output
        s = _last_service(fake_client)
        assert s["service"] == "mobile_app_jon"
        assert s["service_data"] == {
            "message": "Alert", "title": "Heads up",
            "target": ["device1", "device2"],
            "data": {"channel": "alarm"},
        }


# ──────────────────────────────────────────────────────────── --help smoke

def test_all_new_groups_in_root_help(runner):
    r = runner.invoke(cli_mod.cli, ["--help"])
    assert r.exit_code == 0
    for grp in [
        "light", "media-player", "climate", "cover", "fan", "vacuum",
        "humidifier", "water-heater", "valve", "lawn-mower", "siren",
        "remote", "number", "select", "button", "text", "notify",
    ]:
        assert grp in r.output, f"group {grp!r} missing from root --help"
