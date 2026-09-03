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
    payload = _drop_none(
        {
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
        }
    )
    return _call(client, "light", "turn_on", payload)


def light_turn_off(
    client,
    entity_id: str,
    *,
    transition: float | None = None,
    flash: str | None = None,
) -> Any:
    _require_prefix(entity_id, "light.")
    payload = _drop_none(
        {
            "entity_id": entity_id,
            "transition": transition,
            "flash": flash,
        }
    )
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
    payload = _drop_none(
        {
            "entity_id": entity_id,
            "brightness": brightness,
            "brightness_pct": brightness_pct,
            "kelvin": kelvin,
            "rgb_color": list(rgb_color) if rgb_color is not None else None,
            "transition": transition,
        }
    )
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
    return _call(client, "media_player", "media_play_pause", {"entity_id": entity_id})


def media_player_next(client, entity_id: str) -> Any:
    _mp_require(entity_id)
    return _call(client, "media_player", "media_next_track", {"entity_id": entity_id})


def media_player_previous(client, entity_id: str) -> Any:
    _mp_require(entity_id)
    return _call(client, "media_player", "media_previous_track", {"entity_id": entity_id})


def media_player_volume_set(client, entity_id: str, *, volume: float) -> Any:
    _mp_require(entity_id)
    if not 0.0 <= volume <= 1.0:
        raise ValueError(f"volume must be 0.0..1.0, got {volume}")
    return _call(
        client, "media_player", "volume_set", {"entity_id": entity_id, "volume_level": volume}
    )


def media_player_volume_up(client, entity_id: str) -> Any:
    _mp_require(entity_id)
    return _call(client, "media_player", "volume_up", {"entity_id": entity_id})


def media_player_volume_down(client, entity_id: str) -> Any:
    _mp_require(entity_id)
    return _call(client, "media_player", "volume_down", {"entity_id": entity_id})


def media_player_mute(client, entity_id: str, *, mute: bool) -> Any:
    _mp_require(entity_id)
    return _call(
        client,
        "media_player",
        "volume_mute",
        {"entity_id": entity_id, "is_volume_muted": bool(mute)},
    )


def media_player_select_source(client, entity_id: str, *, source: str) -> Any:
    _mp_require(entity_id)
    if not source:
        raise ValueError("source is required")
    return _call(
        client, "media_player", "select_source", {"entity_id": entity_id, "source": source}
    )


def media_player_select_sound_mode(client, entity_id: str, *, sound_mode: str) -> Any:
    _mp_require(entity_id)
    if not sound_mode:
        raise ValueError("sound_mode is required")
    return _call(
        client,
        "media_player",
        "select_sound_mode",
        {"entity_id": entity_id, "sound_mode": sound_mode},
    )


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
    payload = _drop_none(
        {
            "entity_id": entity_id,
            "media_content_id": media_content_id,
            "media_content_type": media_content_type,
            "enqueue": enqueue,
            "announce": announce,
            "extra": extra,
        }
    )
    return _call(client, "media_player", "play_media", payload)


def media_player_shuffle(client, entity_id: str, *, shuffle: bool) -> Any:
    _mp_require(entity_id)
    return _call(
        client, "media_player", "shuffle_set", {"entity_id": entity_id, "shuffle": bool(shuffle)}
    )


def media_player_repeat(client, entity_id: str, *, repeat: str) -> Any:
    _mp_require(entity_id)
    if repeat not in ("off", "all", "one"):
        raise ValueError(f"repeat must be off|all|one, got {repeat!r}")
    return _call(client, "media_player", "repeat_set", {"entity_id": entity_id, "repeat": repeat})


def media_player_clear_playlist(client, entity_id: str) -> Any:
    _mp_require(entity_id)
    return _call(client, "media_player", "clear_playlist", {"entity_id": entity_id})


def media_player_turn_on(client, entity_id: str) -> Any:
    _mp_require(entity_id)
    return _call(client, "media_player", "turn_on", {"entity_id": entity_id})


def media_player_turn_off(client, entity_id: str) -> Any:
    _mp_require(entity_id)
    return _call(client, "media_player", "turn_off", {"entity_id": entity_id})


def media_player_join(client, entity_id: str, *, group_members: Iterable[str]) -> Any:
    _mp_require(entity_id)
    members = list(group_members)
    if not members:
        raise ValueError("group_members must be non-empty")
    return _call(client, "media_player", "join", {"entity_id": entity_id, "group_members": members})


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
        raise ValueError("must provide temperature or target_temp_high/target_temp_low")
    payload = _drop_none(
        {
            "entity_id": entity_id,
            "temperature": temperature,
            "target_temp_high": target_temp_high,
            "target_temp_low": target_temp_low,
            "hvac_mode": hvac_mode,
        }
    )
    return _call(client, "climate", "set_temperature", payload)


def climate_set_hvac_mode(client, entity_id: str, *, hvac_mode: str) -> Any:
    _require_prefix(entity_id, "climate.")
    if not hvac_mode:
        raise ValueError("hvac_mode is required")
    return _call(
        client, "climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": hvac_mode}
    )


def climate_set_fan_mode(client, entity_id: str, *, fan_mode: str) -> Any:
    _require_prefix(entity_id, "climate.")
    if not fan_mode:
        raise ValueError("fan_mode is required")
    return _call(client, "climate", "set_fan_mode", {"entity_id": entity_id, "fan_mode": fan_mode})


def climate_set_preset_mode(client, entity_id: str, *, preset_mode: str) -> Any:
    _require_prefix(entity_id, "climate.")
    if not preset_mode:
        raise ValueError("preset_mode is required")
    return _call(
        client, "climate", "set_preset_mode", {"entity_id": entity_id, "preset_mode": preset_mode}
    )


def climate_set_humidity(client, entity_id: str, *, humidity: int) -> Any:
    _require_prefix(entity_id, "climate.")
    if not 0 <= humidity <= 100:
        raise ValueError(f"humidity must be 0..100, got {humidity}")
    return _call(client, "climate", "set_humidity", {"entity_id": entity_id, "humidity": humidity})


def climate_set_swing_mode(client, entity_id: str, *, swing_mode: str) -> Any:
    _require_prefix(entity_id, "climate.")
    if not swing_mode:
        raise ValueError("swing_mode is required")
    return _call(
        client, "climate", "set_swing_mode", {"entity_id": entity_id, "swing_mode": swing_mode}
    )


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
    return _call(
        client, "cover", "set_cover_position", {"entity_id": entity_id, "position": position}
    )


def cover_set_tilt(client, entity_id: str, *, tilt_position: int) -> Any:
    _require_prefix(entity_id, "cover.")
    if not 0 <= tilt_position <= 100:
        raise ValueError(f"tilt_position must be 0..100, got {tilt_position}")
    return _call(
        client,
        "cover",
        "set_cover_tilt_position",
        {"entity_id": entity_id, "tilt_position": tilt_position},
    )


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
    payload = _drop_none(
        {
            "entity_id": entity_id,
            "percentage": percentage,
            "preset_mode": preset_mode,
        }
    )
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
    return _call(
        client, "fan", "set_percentage", {"entity_id": entity_id, "percentage": percentage}
    )


def fan_set_preset(client, entity_id: str, *, preset_mode: str) -> Any:
    _require_prefix(entity_id, "fan.")
    if not preset_mode:
        raise ValueError("preset_mode is required")
    return _call(
        client, "fan", "set_preset_mode", {"entity_id": entity_id, "preset_mode": preset_mode}
    )


def fan_set_direction(client, entity_id: str, *, direction: str) -> Any:
    _require_prefix(entity_id, "fan.")
    if direction not in ("forward", "reverse"):
        raise ValueError(f"direction must be forward|reverse, got {direction!r}")
    return _call(client, "fan", "set_direction", {"entity_id": entity_id, "direction": direction})


def fan_oscillate(client, entity_id: str, *, oscillating: bool) -> Any:
    _require_prefix(entity_id, "fan.")
    return _call(
        client, "fan", "oscillate", {"entity_id": entity_id, "oscillating": bool(oscillating)}
    )


def fan_increase(client, entity_id: str, *, percentage_step: int | None = None) -> Any:
    _require_prefix(entity_id, "fan.")
    payload = _drop_none(
        {
            "entity_id": entity_id,
            "percentage_step": percentage_step,
        }
    )
    return _call(client, "fan", "increase_speed", payload)


def fan_decrease(client, entity_id: str, *, percentage_step: int | None = None) -> Any:
    _require_prefix(entity_id, "fan.")
    payload = _drop_none(
        {
            "entity_id": entity_id,
            "percentage_step": percentage_step,
        }
    )
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
    return _call(
        client, "vacuum", "set_fan_speed", {"entity_id": entity_id, "fan_speed": fan_speed}
    )


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
    payload = _drop_none(
        {
            "entity_id": entity_id,
            "command": command,
            "params": params,
        }
    )
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
    return _call(
        client, "humidifier", "set_humidity", {"entity_id": entity_id, "humidity": humidity}
    )


def humidifier_set_mode(client, entity_id: str, *, mode: str) -> Any:
    _require_prefix(entity_id, "humidifier.")
    if not mode:
        raise ValueError("mode is required")
    return _call(client, "humidifier", "set_mode", {"entity_id": entity_id, "mode": mode})


# ──────────────────────────────────────────────────────────────────── water_heater


def water_heater_turn_on(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "water_heater.")
    return _call(client, "water_heater", "turn_on", {"entity_id": entity_id})


def water_heater_turn_off(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "water_heater.")
    return _call(client, "water_heater", "turn_off", {"entity_id": entity_id})


def water_heater_set_temperature(client, entity_id: str, *, temperature: float) -> Any:
    _require_prefix(entity_id, "water_heater.")
    return _call(
        client,
        "water_heater",
        "set_temperature",
        {"entity_id": entity_id, "temperature": temperature},
    )


def water_heater_set_operation_mode(client, entity_id: str, *, operation_mode: str) -> Any:
    _require_prefix(entity_id, "water_heater.")
    if not operation_mode:
        raise ValueError("operation_mode is required")
    return _call(
        client,
        "water_heater",
        "set_operation_mode",
        {"entity_id": entity_id, "operation_mode": operation_mode},
    )


def water_heater_set_away_mode(client, entity_id: str, *, away_mode: bool) -> Any:
    _require_prefix(entity_id, "water_heater.")
    return _call(
        client,
        "water_heater",
        "set_away_mode",
        {"entity_id": entity_id, "away_mode": bool(away_mode)},
    )


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
    return _call(
        client, "valve", "set_valve_position", {"entity_id": entity_id, "position": position}
    )


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
        raise ValueError(f"volume_level must be 0.0..1.0, got {volume_level}")
    payload = _drop_none(
        {
            "entity_id": entity_id,
            "duration": duration,
            "tone": tone,
            "volume_level": volume_level,
        }
    )
    return _call(client, "siren", "turn_on", payload)


def siren_turn_off(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "siren.")
    return _call(client, "siren", "turn_off", {"entity_id": entity_id})


def siren_toggle(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "siren.")
    return _call(client, "siren", "toggle", {"entity_id": entity_id})


# ──────────────────────────────────────────────────────────────────── remote


def remote_turn_on(client, entity_id: str, *, activity: str | None = None) -> Any:
    _require_prefix(entity_id, "remote.")
    payload = _drop_none(
        {
            "entity_id": entity_id,
            "activity": activity,
        }
    )
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
    payload = _drop_none(
        {
            "entity_id": entity_id,
            "command": command,
            "device": device,
            "num_repeats": num_repeats,
            "delay_secs": delay_secs,
            "hold_secs": hold_secs,
        }
    )
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
    payload = _drop_none(
        {
            "entity_id": entity_id,
            "command": command,
            "device": device,
            "command_type": command_type,
            "alternative": alternative,
            "timeout": timeout,
        }
    )
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
    payload = _drop_none(
        {
            "entity_id": entity_id,
            "command": command,
            "device": device,
        }
    )
    return _call(client, "remote", "delete_command", payload)


# ──────────────────────────────────────────────────────────────────── number


def number_set_value(client, entity_id: str, *, value: float) -> Any:
    _require_prefix(entity_id, "number.")
    return _call(client, "number", "set_value", {"entity_id": entity_id, "value": value})


# ──────────────────────────────────────────────────────────────────── select


def select_select_option(client, entity_id: str, *, option: str) -> Any:
    _require_prefix(entity_id, "select.")
    if not option:
        raise ValueError("option is required")
    return _call(client, "select", "select_option", {"entity_id": entity_id, "option": option})


def select_next(client, entity_id: str, *, cycle: bool | None = None) -> Any:
    _require_prefix(entity_id, "select.")
    payload = _drop_none({"entity_id": entity_id, "cycle": cycle})
    return _call(client, "select", "select_next", payload)


def select_previous(client, entity_id: str, *, cycle: bool | None = None) -> Any:
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
    return _call(client, "text", "set_value", {"entity_id": entity_id, "value": value})


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
    payload = _drop_none(
        {
            "message": message,
            "title": title,
            "target": target,
            "data": data,
        }
    )
    return _call(client, "notify", service, payload)


# ──────────────────────────────────────────────────────────────────── switch


def switch_turn_on(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "switch.")
    return _call(client, "switch", "turn_on", {"entity_id": entity_id})


def switch_turn_off(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "switch.")
    return _call(client, "switch", "turn_off", {"entity_id": entity_id})


def switch_toggle(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "switch.")
    return _call(client, "switch", "toggle", {"entity_id": entity_id})


# ─────────────────────────────────────────────────── date / time / datetime
#
# The three `set_value` services each parse their argument with a DIFFERENT
# and mostly undocumented parser, and reject a bad one with a bare HTTP 400.
# The validators below are the client-side copies of HA 2025.1.4's own, so the
# refusal names the format instead of being a status code.


def _validate_date(value: str) -> str:
    """Accept exactly what `dt_util.parse_date` accepts: `YYYY-MM-DD`.

    HA's own `date/services.yaml` gives `"2022/11/01"` as the example for this
    field. That example is REJECTED: `parse_date` is
    `datetime.strptime(dt_str, "%Y-%m-%d")`, so slashes are a 400 with no body.
    """
    import datetime as _dt
    import re as _re

    if not value:
        raise ValueError("date is required")
    # `date.fromisoformat` also accepts the basic form ("20221101"), which HA's
    # `%Y-%m-%d` parser does not — so pin the shape first, then let the stdlib
    # reject impossible dates. A date carries no timezone, so this stays clear
    # of the naive-datetime rule the strptime form tripped (DTZ007).
    if not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(
            f"date must be ISO `YYYY-MM-DD`, got {value!r} — note that HA's own "
            f"services.yaml example ('2022/11/01') is not accepted by the parser"
        )
    try:
        _dt.date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"date must be a real calendar date, got {value!r}") from None
    return value


def _validate_time(value: str) -> str:
    """Accept what `dt_util.parse_time` accepts: `HH:MM` or `HH:MM:SS`.

    HA splits on `:` and int()s the parts, so it needs at least two of them;
    a bare `"22"` is a 400. The stored state is always normalised to
    `HH:MM:SS`.
    """
    import datetime as _dt

    if not value:
        raise ValueError("time is required")
    parts = str(value).split(":")
    if len(parts) < 2:
        raise ValueError(f"time must be `HH:MM` or `HH:MM:SS`, got {value!r}")
    try:
        _dt.time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
    except ValueError:
        raise ValueError(f"time must be `HH:MM` or `HH:MM:SS`, got {value!r}") from None
    return value


def _validate_datetime(value: str) -> str:
    """Accept an ISO-8601 datetime; report what HA will do with a loose one.

    Two behaviours worth knowing, both measured against 2025.1.4:

    * A DATE-ONLY string is accepted and silently becomes midnight —
      `"2023-10-07"` stores `2023-10-07T00:00:00`. It is not an error, so
      it is not refused here either.
    * A NAIVE datetime is interpreted in **Home Assistant's** timezone, not
      the caller's: `datetime/__init__.py` does
      `value.replace(tzinfo=dt_util.get_default_time_zone())`. Pass an
      explicit offset (or a trailing `Z`) when that matters.
    """
    import datetime as _dt

    if not value:
        raise ValueError("datetime is required")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        _dt.datetime.fromisoformat(candidate)
    except ValueError:
        raise ValueError(
            f"datetime must be ISO-8601 (e.g. `2023-10-07T21:35:22` or "
            f"`2023-10-07T21:35:22+02:00`), got {value!r}"
        ) from None
    return value


def date_set_value(client, entity_id: str, *, date: str) -> Any:
    _require_prefix(entity_id, "date.")
    return _call(
        client, "date", "set_value", {"entity_id": entity_id, "date": _validate_date(date)}
    )


def time_set_value(client, entity_id: str, *, time: str) -> Any:
    _require_prefix(entity_id, "time.")
    return _call(
        client, "time", "set_value", {"entity_id": entity_id, "time": _validate_time(time)}
    )


def datetime_set_value(client, entity_id: str, *, datetime: str) -> Any:
    _require_prefix(entity_id, "datetime.")
    return _call(
        client,
        "datetime",
        "set_value",
        {"entity_id": entity_id, "datetime": _validate_datetime(datetime)},
    )


# ──────────────────────────────────────────────────────────────────── camera
#
# These are the camera services that make the camera DO something, as opposed
# to the proxy endpoints (`camera snapshot` / `capture`, v1.51.0) that stream
# bytes back to this machine. `host_snapshot` and `record` write their output
# on the HOME ASSISTANT HOST, not here — see the docstrings.


def camera_turn_on(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "camera.")
    return _call(client, "camera", "turn_on", {"entity_id": entity_id})


def camera_turn_off(client, entity_id: str) -> Any:
    """Turn a camera off.

    A camera that is off answers `/api/camera_proxy/<entity_id>` with **503**:
    `CameraView.get` checks `camera.is_on` before dispatching. That is the
    same 503 `camera snapshot` reports.
    """
    _require_prefix(entity_id, "camera.")
    return _call(client, "camera", "turn_off", {"entity_id": entity_id})


def camera_enable_motion_detection(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "camera.")
    return _call(client, "camera", "enable_motion_detection", {"entity_id": entity_id})


def camera_disable_motion_detection(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "camera.")
    return _call(client, "camera", "disable_motion_detection", {"entity_id": entity_id})


def _validate_host_path(filename: str, *, what: str) -> str:
    """Refuse a path HA is certain to reject, and say where the file lands.

    `camera.snapshot` and `camera.record` write on the Home Assistant host and
    both run the destination through `hass.config.is_allowed_path()`. A path
    outside `allowlist_external_dirs` raises `HomeAssistantError` inside the
    handler, which over REST is a **500 with an empty body** — so the one
    check that can be made locally is worth making.

    The field is a TEMPLATE (`cv.template`), so `{{ entity_id.name }}` is
    rendered by HA; that is why a `{`/`}` is not treated as suspicious here.
    """
    if not filename:
        raise ValueError(f"{what} filename is required")
    if not filename.startswith("/"):
        raise ValueError(
            f"{what} filename must be an ABSOLUTE path on the Home Assistant "
            f"host (not on this machine), got {filename!r}"
        )
    return filename


def camera_host_snapshot(client, entity_id: str, *, filename: str) -> Any:
    """`camera.snapshot` — write a still ON THE HOME ASSISTANT HOST.

    Not to be confused with `camera snapshot`, the CLI command that downloads
    a frame to THIS machine over `/api/camera_proxy`. This one hands the path
    to HA and HA writes it, so the directory must be inside
    `allowlist_external_dirs` in HA's `configuration.yaml`.

    Returns nothing useful: the REST service endpoint returns the list of
    states this call changed, and taking a snapshot changes none.
    """
    _require_prefix(entity_id, "camera.")
    return _call(
        client,
        "camera",
        "snapshot",
        {
            "entity_id": entity_id,
            "filename": _validate_host_path(filename, what="snapshot"),
        },
    )


def camera_record(
    client,
    entity_id: str,
    *,
    filename: str,
    duration: int | None = None,
    lookback: int | None = None,
) -> Any:
    """`camera.record` — record to a file ON THE HOME ASSISTANT HOST.

    Needs the `stream` integration AND a camera that provides a stream source;
    a camera without one raises `<entity_id> does not support record service`,
    which arrives over REST as a bare 500.

    `lookback` replays from the stream's already-buffered past, so it only
    yields anything when `preload_stream` is on for that camera
    (`camera prefs-set --preload-stream`).

    The selector bounds `duration` to 1-3600 and `lookback` to 0-300 in the
    UI; the voluptuous schema behind it is only `vol.Coerce(int)`, so those
    are enforced here rather than by HA.
    """
    _require_prefix(entity_id, "camera.")
    payload: dict[str, Any] = {
        "entity_id": entity_id,
        "filename": _validate_host_path(filename, what="record"),
    }
    if duration is not None:
        if not 1 <= int(duration) <= 3600:
            raise ValueError(f"duration must be 1-3600 seconds, got {duration}")
        payload["duration"] = int(duration)
    if lookback is not None:
        if not 0 <= int(lookback) <= 300:
            raise ValueError(f"lookback must be 0-300 seconds, got {lookback}")
        payload["lookback"] = int(lookback)
    return _call(client, "camera", "record", payload)


def camera_play_stream(
    client,
    entity_id: str,
    *,
    media_player: str,
    stream_format: str = "hls",
) -> Any:
    """`camera.play_stream` — cast a camera's live stream to a media player."""
    _require_prefix(entity_id, "camera.")
    if not media_player:
        raise ValueError("media_player is required")
    if not media_player.startswith("media_player."):
        raise ValueError(f"expected media_player.* entity_id for the target, got {media_player!r}")
    if stream_format not in ("hls",):
        raise ValueError(f"format must be 'hls', got {stream_format!r}")
    return _call(
        client,
        "camera",
        "play_stream",
        {
            "entity_id": entity_id,
            "media_player": media_player,
            "format": stream_format,
        },
    )


# ────────────────────────────────────────────── fill-ins on existing domains


def climate_toggle(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "climate.")
    return _call(client, "climate", "toggle", {"entity_id": entity_id})


def climate_set_swing_horizontal_mode(client, entity_id: str, *, swing_horizontal_mode: str) -> Any:
    """Set the HORIZONTAL swing mode — a separate service from `set_swing_mode`.

    (`climate.set_aux_heat` is deliberately not wrapped: it is deprecated and
    documented as unsupported from Home Assistant 2025.4.)
    """
    _require_prefix(entity_id, "climate.")
    if not swing_horizontal_mode:
        raise ValueError("swing_horizontal_mode is required")
    return _call(
        client,
        "climate",
        "set_swing_horizontal_mode",
        {"entity_id": entity_id, "swing_horizontal_mode": swing_horizontal_mode},
    )


def cover_toggle_tilt(client, entity_id: str) -> Any:
    _require_prefix(entity_id, "cover.")
    return _call(client, "cover", "toggle_cover_tilt", {"entity_id": entity_id})


def media_player_toggle(client, entity_id: str) -> Any:
    _mp_require(entity_id)
    return _call(client, "media_player", "toggle", {"entity_id": entity_id})


def media_player_seek(client, entity_id: str, *, position: float) -> Any:
    """Seek to `position` SECONDS from the start of the current item.

    `seek_position` is `cv.positive_float`, so a negative value is refused by
    HA with a bare 400 — refused here instead.
    """
    _mp_require(entity_id)
    if position is None:
        raise ValueError("position is required")
    if float(position) < 0:
        raise ValueError(f"position must be >= 0 seconds, got {position}")
    return _call(
        client,
        "media_player",
        "media_seek",
        {"entity_id": entity_id, "seek_position": float(position)},
    )


def alarm_arm_custom_bypass(client, entity_id: str, *, code: str | None = None) -> Any:
    if not entity_id.startswith("alarm_control_panel."):
        raise ValueError(f"expected alarm_control_panel.* entity_id, got {entity_id!r}")
    payload = _drop_none({"entity_id": entity_id, "code": code})
    return _call(client, "alarm_control_panel", "alarm_arm_custom_bypass", payload)


def alarm_trigger(client, entity_id: str, *, code: str | None = None) -> Any:
    """Trigger the alarm — as if a sensor had fired. **This sounds the siren.**"""
    if not entity_id.startswith("alarm_control_panel."):
        raise ValueError(f"expected alarm_control_panel.* entity_id, got {entity_id!r}")
    payload = _drop_none({"entity_id": entity_id, "code": code})
    return _call(client, "alarm_control_panel", "alarm_trigger", payload)


# ───────────────────────────────────────────────────────────── device_tracker


def device_tracker_see(
    client,
    *,
    dev_id: str | None = None,
    mac: str | None = None,
    host_name: str | None = None,
    location_name: str | None = None,
    gps: tuple[float, float] | list[float] | None = None,
    gps_accuracy: int | None = None,
    battery: int | None = None,
) -> Any:
    """`device_tracker.see` — report a device's position to HA.

    This is the "manual tracker" entry point: it CREATES `device_tracker.<dev_id>`
    on first use and persists it in `known_devices.yaml`.

    At least one of `dev_id`/`mac` is required — with neither, HA has nothing
    to key the device on and answers a bare 400.

    `location_name` and `gps` are alternatives: `location_name` sets a zone by
    name (`home`, `not_home`, or a zone's friendly name) and `gps` sets
    coordinates that HA then resolves to a zone itself.
    """
    if not dev_id and not mac:
        raise ValueError("device_tracker.see needs at least one of dev_id or mac")
    if gps is not None:
        if len(list(gps)) != 2:
            raise ValueError("gps must be exactly [latitude, longitude]")
        lat, lon = (float(v) for v in gps)
        if not -90 <= lat <= 90:
            raise ValueError(f"latitude must be between -90 and 90, got {lat}")
        if not -180 <= lon <= 180:
            raise ValueError(f"longitude must be between -180 and 180, got {lon}")
        gps = [lat, lon]
    if battery is not None and not 0 <= int(battery) <= 100:
        raise ValueError(f"battery must be 0-100, got {battery}")
    payload = _drop_none(
        {
            "dev_id": dev_id,
            "mac": mac,
            "host_name": host_name,
            "location_name": location_name,
            "gps": gps,
            "gps_accuracy": gps_accuracy,
            "battery": battery,
        }
    )
    return _call(client, "device_tracker", "see", payload)


# ─────────────────────────────────────────────────────────── image_processing


def image_processing_scan(client, entity_id: str) -> Any:
    """`image_processing.scan` — force a scan now instead of waiting for the poll.

    The result is not returned: it lands on the `image_processing.*` entity's
    own state and attributes, so read it back with `state get` afterwards.
    """
    _require_prefix(entity_id, "image_processing.")
    return _call(client, "image_processing", "scan", {"entity_id": entity_id})
