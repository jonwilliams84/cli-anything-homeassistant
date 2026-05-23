"""Entity-control shortcut wrappers.

Thin wrappers around `services/<domain>/<service>` calls for the everyday
entity-control domains (light, media_player, climate, cover, fan, vacuum,
humidifier, water_heater, valve, lawn_mower, siren, remote, number, select,
button, text, notify).

Each function:
  * validates the entity_id prefix (when an entity_id is required),
  * builds the service_data payload while omitting None-valued args,
  * POSTs to the matching HA service endpoint.

Returns the raw client response.
"""

from __future__ import annotations

from typing import Any, Iterable


# ──────────────────────────────────────────────────────────────────── helpers

def _require_prefix(entity_id: str, prefix: str) -> None:
    if not entity_id.startswith(prefix):
        raise ValueError(f"expected {prefix}* entity_id, got {entity_id!r}")


def _drop_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def _call(client, domain: str, service: str, payload: dict) -> Any:
    return client.post(f"services/{domain}/{service}", payload)


# ──────────────────────────────────────────────────────────────────── light

def light_turn_on(
    client,
    entity_id: str,
    *,
    brightness: int | None = None,
    brightness_pct: float | None = None,
    kelvin: int | None = None,
    color_temp_kelvin: int | None = None,
    rgb_color: list[int] | tuple[int, int, int] | None = None,
    rgbw_color: list[int] | None = None,
    rgbww_color: list[int] | None = None,
    xy_color: list[float] | None = None,
    hs_color: list[float] | None = None,
    color_name: str | None = None,
    effect: str | None = None,
    flash: str | None = None,
    transition: float | None = None,
    profile: str | None = None,
    white: int | bool | None = None,
) -> Any:
    _require_prefix(entity_id, "light.")
    if brightness is not None and not 0 <= brightness <= 255:
        raise ValueError(f"brightness must be 0..255, got {brightness}")
    if brightness_pct is not None and not 0 <= brightness_pct <= 100:
        raise ValueError(f"brightness_pct must be 0..100, got {brightness_pct}")
    payload = _drop_none({
        "entity_id": entity_id,
        "brightness": brightness,
        "brightness_pct": brightness_pct,
        "kelvin": kelvin,
        "color_temp_kelvin": color_temp_kelvin,
        "rgb_color": list(rgb_color) if rgb_color is not None else None,
        "rgbw_color": list(rgbw_color) if rgbw_color is not None else None,
        "rgbww_color": list(rgbww_color) if rgbww_color is not None else None,
        "xy_color": list(xy_color) if xy_color is not None else None,
        "hs_color": list(hs_color) if hs_color is not None else None,
        "color_name": color_name,
        "effect": effect,
        "flash": flash,
        "transition": transition,
        "profile": profile,
        "white": white,
    })
    return _call(client, "light", "turn_on", payload)


def light_turn_off(
    client,
    entity_id: str,
    *,
    transition: float | None = None,
    flash: str | None = None,
) -> Any:
    _require_prefix(entity_id, "light.")
    payload = _drop_none({
        "entity_id": entity_id,
        "transition": transition,
        "flash": flash,
    })
    return _call(client, "light", "turn_off", payload)


def light_toggle(
    client,
    entity_id: str,
    *,
    brightness: int | None = None,
    brightness_pct: float | None = None,
    kelvin: int | None = None,
    rgb_color: list[int] | None = None,
    transition: float | None = None,
) -> Any:
    _require_prefix(entity_id, "light.")
    payload = _drop_none({
        "entity_id": entity_id,
        "brightness": brightness,
        "brightness_pct": brightness_pct,
        "kelvin": kelvin,
        "rgb_color": list(rgb_color) if rgb_color is not None else None,
        "transition": transition,
    })
    return _call(client, "light", "toggle", payload)


# ──────────────────────────────────────────────────────────────────── media_player

def _mp_require(entity_id: str) -> None:
    _require_prefix(entity_id, "media_player.")


def media_player_play(client, entity_id: str) -> Any:
    _mp_require(entity_id)
    return _call(client, "media_player", "media_play", {"entity_id": entity_id})


def media_player_pause(client, entity_id: str) -> Any:
    _mp_require(entity_id)
    return _call(client, "media_player", "media_pause", {"entity_id": entity_id})


def media_player_stop(client, entity_id: str) -> Any:
    _mp_require(entity_id)
    return _call(client, "media_player", "media_stop", {"entity_id": entity_id})


def media_player_play_pause(client, entity_id: str) -> Any:
    _mp_require(entity_id)
    return _call(client, "media_player", "media_play_pause",
                 {"entity_id": entity_id})


def media_player_next(client, entity_id: str) -> Any:
    _mp_require(entity_id)
    return _call(client, "media_player", "media_next_track",
                 {"entity_id": entity_id})


def media_player_previous(client, entity_id: str) -> Any:
    _mp_require(entity_id)
    return _call(client, "media_player", "media_previous_track",
                 {"entity_id": entity_id})


def media_player_volume_set(client, entity_id: str, *, volume: float) -> Any:
    _mp_require(entity_id)
    if not 0.0 <= volume <= 1.0:
        raise ValueError(f"volume must be 0.0..1.0, got {volume}")
    return _call(client, "media_player", "volume_set",
                 {"entity_id": entity_id, "volume_level": volume})


def media_player_volume_up(client, entity_id: str) -> Any:
    _mp_require(entity_id)
    return _call(client, "media_player", "volume_up", {"entity_id": entity_id})


def media_player_volume_down(client, entity_id: str) -> Any:
    _mp_require(entity_id)
    return _call(client, "media_player", "volume_down", {"entity_id": entity_id})


def media_player_mute(client, entity_id: str, *, mute: bool) -> Any:
    _mp_require(entity_id)
    return _call(client, "media_player", "volume_mute",
                 {"entity_id": entity_id, "is_volume_muted": bool(mute)})


def media_player_select_source(client, entity_id: str, *, source: str) -> Any:
    _mp_require(entity_id)
    if not source:
        raise ValueError("source is required")
    return _call(client, "media_player", "select_source",
                 {"entity_id": entity_id, "source": source})


def media_player_select_sound_mode(client, entity_id: str, *,
                                   sound_mode: str) -> Any:
    _mp_require(entity_id)
    if not sound_mode:
        raise ValueError("sound_mode is required")
    return _call(client, "media_player", "select_sound_mode",
                 {"entity_id": entity_id, "sound_mode": sound_mode})


def media_player_play_media(
    client,
    entity_id: str,
    *,
    media_content_id: str,
    media_content_type: str,
    enqueue: str | bool | None = None,
    announce: bool | None = None,
    extra: dict | None = None,
) -> Any:
    _mp_require(entity_id)
    if not media_content_id:
        raise ValueError("media_content_id is required")
    if not media_content_type:
        raise ValueError("media_content_type is required")
    payload = _drop_none({
        "entity_id": entity_id,
        "media_content_id": media_content_id,
        "media_content_type": media_content_type,
        "enqueue": enqueue,
        "announce": announce,
        "extra": extra,
    })
    return _call(client, "media_player", "play_media", payload)


def media_player_shuffle(client, entity_id: str, *, shuffle: bool) -> Any:
    _mp_require(entity_id)
    return _call(client, "media_player", "shuffle_set",
                 {"entity_id": entity_id, "shuffle": bool(shuffle)})


def media_player_repeat(client, entity_id: str, *, repeat: str) -> Any:
    _mp_require(entity_id)
    if repeat not in ("off", "all", "one"):
        raise ValueError(f"repeat must be off|all|one, got {repeat!r}")
    return _call(client, "media_player", "repeat_set",
                 {"entity_id": entity_id, "repeat": repeat})


def media_player_clear_playlist(client, entity_id: str) -> Any:
    _mp_require(entity_id)
    return _call(client, "media_player", "clear_playlist",
                 {"entity_id": entity_id})


def media_player_turn_on(client, entity_id: str) -> Any:
    _mp_require(entity_id)
    return _call(client, "media_player", "turn_on", {"entity_id": entity_id})


def media_player_turn_off(client, entity_id: str) -> Any:
    _mp_require(entity_id)
    return _call(client, "media_player", "turn_off", {"entity_id": entity_id})


def media_player_join(client, entity_id: str, *,
                      group_members: Iterable[str]) -> Any:
    _mp_require(entity_id)
    members = list(group_members)
    if not members:
        raise ValueError("group_members must be non-empty")
    return _call(client, "media_player", "join",
                 {"entity_id": entity_id, "group_members": members})


def media_player_unjoin(client, entity_id: str) -> Any:
    _mp_require(entity_id)
    return _call(client, "media_player", "unjoin", {"entity_id": entity_id})


# ──────────────────────────────────────────────────────────────────── climate

def climate_set_temperature(
    client,
    entity_id: str,
    *,
    temperature: float | None = None,
    target_temp_high: float | None = None,
    target_temp_low: float | None = None,
    hvac_mode: str | None = None,
) -> Any:
    _require_prefix(entity_id, "climate.")
    if temperature is None and target_temp_high is None and target_temp_low is None:
        raise ValueError(
            "must provide temperature or target_temp_high/target_temp_low"
        )
    payload = _drop_none({
        "entity_id": entity_id,
        "temperature": temperature,
        "target_temp_high": target_temp_high,
        "target_temp_low": target_temp_low,
        "hvac_mode": hvac_mode,
    })
    return _call(client, "climate", "set_temperature", payload)


def climate_set_hvac_mode(client, entity_id: str, *, hvac_mode: str) -> Any:
    _require_prefix(entity_id, "climate.")
    if not hvac_mode:
        raise ValueError("hvac_mode is required")
    return _call(client, "climate", "set_hvac_mode",
                 {"entity_id": entity_id, "hvac_mode": hvac_mode})


def climate_set_fan_mode(client, entity_id: str, *, fan_mode: str) -> Any:
    _require_prefix(entity_id, "climate.")
    if not fan_mode:
        raise ValueError("fan_mode is required")
    return _call(client, "climate", "set_fan_mode",
                 {"entity_id": entity_id, "fan_mode": fan_mode})


def climate_set_preset_mode(client, entity_id: str, *,
                            preset_mode: str) -> Any:
    _require_prefix(entity_id, "climate.")
    if not preset_mode:
        raise ValueError("preset_mode is required")
    return _call(client, "climate", "set_preset_mode",
                 {"entity_id": entity_id, "preset_mode": preset_mode})


def climate_set_humidity(client, entity_id: str, *, humidity: int) -> Any:
    _require_prefix(entity_id, "climate.")
    if not 0 <= humidity <= 100:
        raise ValueError(f"humidity must be 0..100, got {humidity}")
    return _call(client, "climate", "set_humidity",
                 {"entity_id": entity_id, "humidity": humidity})


def climate_set_swing_mode(client, entity_id: str, *, swing_mode: str) -> Any:
    _require_prefix(entity_id, "climate.")
    if not swing_mode:
        raise ValueError("swing_mode is required")
    return _call(client, "climate", "set_swing_mode",
                 {"entity_id": entity_id, "swing_mode": swing_mode})


def climate_turn_on(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "climate.")
    return _call(client, "climate", "turn_on", {"entity_id": entity_id})


def climate_turn_off(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "climate.")
    return _call(client, "climate", "turn_off", {"entity_id": entity_id})


# ──────────────────────────────────────────────────────────────────── cover

def cover_open(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "cover.")
    return _call(client, "cover", "open_cover", {"entity_id": entity_id})


def cover_close(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "cover.")
    return _call(client, "cover", "close_cover", {"entity_id": entity_id})


def cover_stop(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "cover.")
    return _call(client, "cover", "stop_cover", {"entity_id": entity_id})


def cover_toggle(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "cover.")
    return _call(client, "cover", "toggle", {"entity_id": entity_id})


def cover_set_position(client, entity_id: str, *, position: int) -> Any:
    _require_prefix(entity_id, "cover.")
    if not 0 <= position <= 100:
        raise ValueError(f"position must be 0..100, got {position}")
    return _call(client, "cover", "set_cover_position",
                 {"entity_id": entity_id, "position": position})


def cover_set_tilt(client, entity_id: str, *, tilt_position: int) -> Any:
    _require_prefix(entity_id, "cover.")
    if not 0 <= tilt_position <= 100:
        raise ValueError(f"tilt_position must be 0..100, got {tilt_position}")
    return _call(client, "cover", "set_cover_tilt_position",
                 {"entity_id": entity_id, "tilt_position": tilt_position})


def cover_open_tilt(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "cover.")
    return _call(client, "cover", "open_cover_tilt", {"entity_id": entity_id})


def cover_close_tilt(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "cover.")
    return _call(client, "cover", "close_cover_tilt", {"entity_id": entity_id})


def cover_stop_tilt(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "cover.")
    return _call(client, "cover", "stop_cover_tilt", {"entity_id": entity_id})


# ──────────────────────────────────────────────────────────────────── fan

def fan_turn_on(
    client,
    entity_id: str,
    *,
    percentage: int | None = None,
    preset_mode: str | None = None,
) -> Any:
    _require_prefix(entity_id, "fan.")
    if percentage is not None and not 0 <= percentage <= 100:
        raise ValueError(f"percentage must be 0..100, got {percentage}")
    payload = _drop_none({
        "entity_id": entity_id,
        "percentage": percentage,
        "preset_mode": preset_mode,
    })
    return _call(client, "fan", "turn_on", payload)


def fan_turn_off(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "fan.")
    return _call(client, "fan", "turn_off", {"entity_id": entity_id})


def fan_toggle(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "fan.")
    return _call(client, "fan", "toggle", {"entity_id": entity_id})


def fan_set_percentage(client, entity_id: str, *, percentage: int) -> Any:
    _require_prefix(entity_id, "fan.")
    if not 0 <= percentage <= 100:
        raise ValueError(f"percentage must be 0..100, got {percentage}")
    return _call(client, "fan", "set_percentage",
                 {"entity_id": entity_id, "percentage": percentage})


def fan_set_preset(client, entity_id: str, *, preset_mode: str) -> Any:
    _require_prefix(entity_id, "fan.")
    if not preset_mode:
        raise ValueError("preset_mode is required")
    return _call(client, "fan", "set_preset_mode",
                 {"entity_id": entity_id, "preset_mode": preset_mode})


def fan_set_direction(client, entity_id: str, *, direction: str) -> Any:
    _require_prefix(entity_id, "fan.")
    if direction not in ("forward", "reverse"):
        raise ValueError(f"direction must be forward|reverse, got {direction!r}")
    return _call(client, "fan", "set_direction",
                 {"entity_id": entity_id, "direction": direction})


def fan_oscillate(client, entity_id: str, *, oscillating: bool) -> Any:
    _require_prefix(entity_id, "fan.")
    return _call(client, "fan", "oscillate",
                 {"entity_id": entity_id, "oscillating": bool(oscillating)})


def fan_increase(client, entity_id: str, *,
                 percentage_step: int | None = None) -> Any:
    _require_prefix(entity_id, "fan.")
    payload = _drop_none({
        "entity_id": entity_id,
        "percentage_step": percentage_step,
    })
    return _call(client, "fan", "increase_speed", payload)


def fan_decrease(client, entity_id: str, *,
                 percentage_step: int | None = None) -> Any:
    _require_prefix(entity_id, "fan.")
    payload = _drop_none({
        "entity_id": entity_id,
        "percentage_step": percentage_step,
    })
    return _call(client, "fan", "decrease_speed", payload)


# ──────────────────────────────────────────────────────────────────── vacuum

def vacuum_start(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "vacuum.")
    return _call(client, "vacuum", "start", {"entity_id": entity_id})


def vacuum_stop(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "vacuum.")
    return _call(client, "vacuum", "stop", {"entity_id": entity_id})


def vacuum_pause(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "vacuum.")
    return _call(client, "vacuum", "pause", {"entity_id": entity_id})


def vacuum_return_to_base(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "vacuum.")
    return _call(client, "vacuum", "return_to_base", {"entity_id": entity_id})


def vacuum_locate(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "vacuum.")
    return _call(client, "vacuum", "locate", {"entity_id": entity_id})


def vacuum_clean_spot(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "vacuum.")
    return _call(client, "vacuum", "clean_spot", {"entity_id": entity_id})


def vacuum_set_fan_speed(client, entity_id: str, *, fan_speed: str) -> Any:
    _require_prefix(entity_id, "vacuum.")
    if not fan_speed:
        raise ValueError("fan_speed is required")
    return _call(client, "vacuum", "set_fan_speed",
                 {"entity_id": entity_id, "fan_speed": fan_speed})


def vacuum_send_command(
    client,
    entity_id: str,
    *,
    command: str,
    params: dict | list | None = None,
) -> Any:
    _require_prefix(entity_id, "vacuum.")
    if not command:
        raise ValueError("command is required")
    payload = _drop_none({
        "entity_id": entity_id,
        "command": command,
        "params": params,
    })
    return _call(client, "vacuum", "send_command", payload)


# ──────────────────────────────────────────────────────────────────── humidifier

def humidifier_turn_on(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "humidifier.")
    return _call(client, "humidifier", "turn_on", {"entity_id": entity_id})


def humidifier_turn_off(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "humidifier.")
    return _call(client, "humidifier", "turn_off", {"entity_id": entity_id})


def humidifier_toggle(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "humidifier.")
    return _call(client, "humidifier", "toggle", {"entity_id": entity_id})


def humidifier_set_humidity(client, entity_id: str, *, humidity: int) -> Any:
    _require_prefix(entity_id, "humidifier.")
    if not 0 <= humidity <= 100:
        raise ValueError(f"humidity must be 0..100, got {humidity}")
    return _call(client, "humidifier", "set_humidity",
                 {"entity_id": entity_id, "humidity": humidity})


def humidifier_set_mode(client, entity_id: str, *, mode: str) -> Any:
    _require_prefix(entity_id, "humidifier.")
    if not mode:
        raise ValueError("mode is required")
    return _call(client, "humidifier", "set_mode",
                 {"entity_id": entity_id, "mode": mode})


# ──────────────────────────────────────────────────────────────────── water_heater

def water_heater_turn_on(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "water_heater.")
    return _call(client, "water_heater", "turn_on", {"entity_id": entity_id})


def water_heater_turn_off(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "water_heater.")
    return _call(client, "water_heater", "turn_off", {"entity_id": entity_id})


def water_heater_set_temperature(client, entity_id: str, *,
                                 temperature: float) -> Any:
    _require_prefix(entity_id, "water_heater.")
    return _call(client, "water_heater", "set_temperature",
                 {"entity_id": entity_id, "temperature": temperature})


def water_heater_set_operation_mode(client, entity_id: str, *,
                                    operation_mode: str) -> Any:
    _require_prefix(entity_id, "water_heater.")
    if not operation_mode:
        raise ValueError("operation_mode is required")
    return _call(client, "water_heater", "set_operation_mode",
                 {"entity_id": entity_id, "operation_mode": operation_mode})


def water_heater_set_away_mode(client, entity_id: str, *,
                               away_mode: bool) -> Any:
    _require_prefix(entity_id, "water_heater.")
    return _call(client, "water_heater", "set_away_mode",
                 {"entity_id": entity_id, "away_mode": bool(away_mode)})


# ──────────────────────────────────────────────────────────────────── valve

def valve_open(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "valve.")
    return _call(client, "valve", "open_valve", {"entity_id": entity_id})


def valve_close(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "valve.")
    return _call(client, "valve", "close_valve", {"entity_id": entity_id})


def valve_stop(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "valve.")
    return _call(client, "valve", "stop_valve", {"entity_id": entity_id})


def valve_toggle(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "valve.")
    return _call(client, "valve", "toggle", {"entity_id": entity_id})


def valve_set_position(client, entity_id: str, *, position: int) -> Any:
    _require_prefix(entity_id, "valve.")
    if not 0 <= position <= 100:
        raise ValueError(f"position must be 0..100, got {position}")
    return _call(client, "valve", "set_valve_position",
                 {"entity_id": entity_id, "position": position})


# ──────────────────────────────────────────────────────────────────── lawn_mower

def lawn_mower_start(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "lawn_mower.")
    return _call(client, "lawn_mower", "start_mowing", {"entity_id": entity_id})


def lawn_mower_pause(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "lawn_mower.")
    return _call(client, "lawn_mower", "pause", {"entity_id": entity_id})


def lawn_mower_dock(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "lawn_mower.")
    return _call(client, "lawn_mower", "dock", {"entity_id": entity_id})


# ──────────────────────────────────────────────────────────────────── siren

def siren_turn_on(
    client,
    entity_id: str,
    *,
    duration: int | None = None,
    tone: str | int | None = None,
    volume_level: float | None = None,
) -> Any:
    _require_prefix(entity_id, "siren.")
    if volume_level is not None and not 0.0 <= volume_level <= 1.0:
        raise ValueError(
            f"volume_level must be 0.0..1.0, got {volume_level}"
        )
    payload = _drop_none({
        "entity_id": entity_id,
        "duration": duration,
        "tone": tone,
        "volume_level": volume_level,
    })
    return _call(client, "siren", "turn_on", payload)


def siren_turn_off(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "siren.")
    return _call(client, "siren", "turn_off", {"entity_id": entity_id})


def siren_toggle(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "siren.")
    return _call(client, "siren", "toggle", {"entity_id": entity_id})


# ──────────────────────────────────────────────────────────────────── remote

def remote_turn_on(client, entity_id: str, *,
                   activity: str | None = None) -> Any:
    _require_prefix(entity_id, "remote.")
    payload = _drop_none({
        "entity_id": entity_id,
        "activity": activity,
    })
    return _call(client, "remote", "turn_on", payload)


def remote_turn_off(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "remote.")
    return _call(client, "remote", "turn_off", {"entity_id": entity_id})


def remote_toggle(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "remote.")
    return _call(client, "remote", "toggle", {"entity_id": entity_id})


def remote_send_command(
    client,
    entity_id: str,
    *,
    command: str | list[str],
    device: str | None = None,
    num_repeats: int | None = None,
    delay_secs: float | None = None,
    hold_secs: float | None = None,
) -> Any:
    _require_prefix(entity_id, "remote.")
    if not command:
        raise ValueError("command is required")
    payload = _drop_none({
        "entity_id": entity_id,
        "command": command,
        "device": device,
        "num_repeats": num_repeats,
        "delay_secs": delay_secs,
        "hold_secs": hold_secs,
    })
    return _call(client, "remote", "send_command", payload)


def remote_learn_command(
    client,
    entity_id: str,
    *,
    command: str | list[str] | None = None,
    device: str | None = None,
    command_type: str | None = None,
    alternative: bool | None = None,
    timeout: float | None = None,
) -> Any:
    _require_prefix(entity_id, "remote.")
    payload = _drop_none({
        "entity_id": entity_id,
        "command": command,
        "device": device,
        "command_type": command_type,
        "alternative": alternative,
        "timeout": timeout,
    })
    return _call(client, "remote", "learn_command", payload)


def remote_delete_command(
    client,
    entity_id: str,
    *,
    command: str | list[str],
    device: str | None = None,
) -> Any:
    _require_prefix(entity_id, "remote.")
    if not command:
        raise ValueError("command is required")
    payload = _drop_none({
        "entity_id": entity_id,
        "command": command,
        "device": device,
    })
    return _call(client, "remote", "delete_command", payload)


# ──────────────────────────────────────────────────────────────────── number

def number_set_value(client, entity_id: str, *, value: float) -> Any:
    _require_prefix(entity_id, "number.")
    return _call(client, "number", "set_value",
                 {"entity_id": entity_id, "value": value})


# ──────────────────────────────────────────────────────────────────── select

def select_select_option(client, entity_id: str, *, option: str) -> Any:
    _require_prefix(entity_id, "select.")
    if not option:
        raise ValueError("option is required")
    return _call(client, "select", "select_option",
                 {"entity_id": entity_id, "option": option})


def select_next(client, entity_id: str, *, cycle: bool | None = None) -> Any:
    _require_prefix(entity_id, "select.")
    payload = _drop_none({"entity_id": entity_id, "cycle": cycle})
    return _call(client, "select", "select_next", payload)


def select_previous(client, entity_id: str, *,
                    cycle: bool | None = None) -> Any:
    _require_prefix(entity_id, "select.")
    payload = _drop_none({"entity_id": entity_id, "cycle": cycle})
    return _call(client, "select", "select_previous", payload)


def select_first(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "select.")
    return _call(client, "select", "select_first", {"entity_id": entity_id})


def select_last(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "select.")
    return _call(client, "select", "select_last", {"entity_id": entity_id})


# ──────────────────────────────────────────────────────────────────── button

def button_press(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "button.")
    return _call(client, "button", "press", {"entity_id": entity_id})


# ──────────────────────────────────────────────────────────────────── text

def text_set_value(client, entity_id: str, *, value: str) -> Any:
    _require_prefix(entity_id, "text.")
    if value is None:
        raise ValueError("value is required")
    return _call(client, "text", "set_value",
                 {"entity_id": entity_id, "value": value})


# ──────────────────────────────────────────────────────────────────── notify (extension)

def notify_send(
    client,
    *,
    message: str,
    title: str | None = None,
    target: str | list[str] | None = None,
    data: dict | None = None,
    service: str = "notify",
) -> Any:
    """Send a notify.* service call.

    Alias surface for the notify CLI group; the original `service_shortcuts.notify`
    function is preserved for backwards compatibility.
    """
    if not message:
        raise ValueError("message is required and must be non-empty")
    if not service:
        raise ValueError("service is required and must be non-empty")
    payload = _drop_none({
        "message": message,
        "title": title,
        "target": target,
        "data": data,
    })
    return _call(client, "notify", service, payload)
