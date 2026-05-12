"""Type-aware card builders.

Each builder returns a card dict with sensible defaults for the given type.
Designed to be terse on the CLI side — `lovelace card create mushroom-light
-e light.kitchen` should produce a working card.

Includes built-in HA card types AND popular HACS custom cards for
minimalist / futuristic / material design dashboards.

References:
- HA docs: https://www.home-assistant.io/dashboards/cards/
- Mushroom: https://github.com/piitaya/lovelace-mushroom
- ApexCharts: https://github.com/RomRider/apexcharts-card
- Mini Graph: https://github.com/kalkih/mini-graph-card
- Button Card: https://github.com/custom-cards/button-card
- Bubble Card: https://github.com/Clooos/Bubble-Card
- Auto-Entities: https://github.com/thomasloven/lovelace-auto-entities
- Layout Card: https://github.com/thomasloven/lovelace-layout-card
- Decluttering: https://github.com/custom-cards/decluttering-card
- Stack-In-Card: https://github.com/custom-cards/stack-in-card
- Bar Card: https://github.com/custom-cards/bar-card
"""

from __future__ import annotations

from typing import Any, Optional


# ─────────────────────────────────────────────────── built-in HA card types

def entities(entities: list[str | dict], *, title: str | None = None,
              show_header_toggle: bool | None = None,
              state_color: bool | None = None,
              theme: str | None = None) -> dict:
    """Build an `entities` card.

    Each entry in `entities` is an entity_id string OR a dict like
    `{entity: light.x, name: "Kitchen", icon: "mdi:lightbulb"}`.
    """
    if not entities:
        raise ValueError("at least one entity required")
    card: dict[str, Any] = {"type": "entities", "entities": list(entities)}
    if title is not None: card["title"] = title
    if show_header_toggle is not None: card["show_header_toggle"] = show_header_toggle
    if state_color is not None: card["state_color"] = state_color
    if theme is not None: card["theme"] = theme
    return card


def vertical_stack(cards: list[dict], *, title: str | None = None) -> dict:
    if not cards:
        raise ValueError("at least one card required")
    out = {"type": "vertical-stack", "cards": list(cards)}
    if title: out["title"] = title
    return out


def horizontal_stack(cards: list[dict], *, title: str | None = None) -> dict:
    if not cards:
        raise ValueError("at least one card required")
    out = {"type": "horizontal-stack", "cards": list(cards)}
    if title: out["title"] = title
    return out


def grid(cards: list[dict], *, columns: int = 2,
          square: bool = False, title: str | None = None) -> dict:
    if not cards:
        raise ValueError("at least one card required")
    if columns <= 0:
        raise ValueError("columns must be positive")
    out: dict[str, Any] = {
        "type": "grid", "cards": list(cards),
        "columns": columns, "square": square,
    }
    if title: out["title"] = title
    return out


def glance(entities: list[str | dict], *, title: str | None = None,
            columns: int | None = None,
            show_state: bool | None = None,
            show_icon: bool | None = None,
            show_name: bool | None = None) -> dict:
    if not entities:
        raise ValueError("at least one entity required")
    card: dict[str, Any] = {"type": "glance", "entities": list(entities)}
    if title is not None: card["title"] = title
    if columns is not None: card["columns"] = columns
    if show_state is not None: card["show_state"] = show_state
    if show_icon is not None: card["show_icon"] = show_icon
    if show_name is not None: card["show_name"] = show_name
    return card


def gauge(entity: str, *, name: str | None = None,
           min: float | None = None, max: float | None = None,
           unit: str | None = None,
           severity: dict | None = None,
           needle: bool = False) -> dict:
    if not entity:
        raise ValueError("entity required")
    card: dict[str, Any] = {"type": "gauge", "entity": entity}
    if name is not None: card["name"] = name
    if min is not None: card["min"] = min
    if max is not None: card["max"] = max
    if unit is not None: card["unit"] = unit
    if severity is not None: card["severity"] = severity
    if needle: card["needle"] = True
    return card


def tile(entity: str, *, name: str | None = None,
          color: str | None = None,
          icon: str | None = None,
          vertical: bool = False,
          show_entity_picture: bool | None = None,
          tap_action: dict | None = None) -> dict:
    if not entity:
        raise ValueError("entity required")
    card: dict[str, Any] = {"type": "tile", "entity": entity}
    if name is not None: card["name"] = name
    if color is not None: card["color"] = color
    if icon is not None: card["icon"] = icon
    if vertical: card["vertical"] = True
    if show_entity_picture is not None:
        card["show_entity_picture"] = show_entity_picture
    if tap_action is not None: card["tap_action"] = tap_action
    return card


def button(entity: str, *, name: str | None = None,
            icon: str | None = None,
            show_state: bool | None = None,
            tap_action: dict | None = None,
            hold_action: dict | None = None,
            theme: str | None = None) -> dict:
    if not entity:
        raise ValueError("entity required")
    card: dict[str, Any] = {"type": "button", "entity": entity}
    if name is not None: card["name"] = name
    if icon is not None: card["icon"] = icon
    if show_state is not None: card["show_state"] = show_state
    if tap_action is not None: card["tap_action"] = tap_action
    if hold_action is not None: card["hold_action"] = hold_action
    if theme is not None: card["theme"] = theme
    return card


def markdown(content: str, *, title: str | None = None,
              theme: str | None = None) -> dict:
    if not content:
        raise ValueError("content required")
    card: dict[str, Any] = {"type": "markdown", "content": content}
    if title is not None: card["title"] = title
    if theme is not None: card["theme"] = theme
    return card


def history_graph(entities: list[str | dict], *, hours_to_show: int = 24,
                    title: str | None = None,
                    refresh_interval: int | None = None) -> dict:
    if not entities:
        raise ValueError("at least one entity required")
    card: dict[str, Any] = {
        "type": "history-graph", "entities": list(entities),
        "hours_to_show": hours_to_show,
    }
    if title is not None: card["title"] = title
    if refresh_interval is not None: card["refresh_interval"] = refresh_interval
    return card


def statistics_graph(entities: list[str | dict], *, days_to_show: int = 30,
                      stat_types: list[str] | None = None,
                      title: str | None = None,
                      chart_type: str | None = None) -> dict:
    if not entities:
        raise ValueError("at least one entity required")
    card: dict[str, Any] = {
        "type": "statistics-graph", "entities": list(entities),
        "days_to_show": days_to_show,
    }
    if stat_types is not None: card["stat_types"] = stat_types
    if title is not None: card["title"] = title
    if chart_type is not None: card["chart_type"] = chart_type
    return card


def conditional(card: dict, conditions: list[dict]) -> dict:
    """Wrap a card in a conditional with the given condition list."""
    if not card or not conditions:
        raise ValueError("card and conditions required")
    return {"type": "conditional", "conditions": conditions, "card": card}


def picture_elements(image: str, elements: list[dict], *,
                       title: str | None = None,
                       state_filter: dict | None = None) -> dict:
    if not image:
        raise ValueError("image required")
    card: dict[str, Any] = {
        "type": "picture-elements",
        "image": image,
        "elements": elements or [],
    }
    if title is not None: card["title"] = title
    if state_filter is not None: card["state_filter"] = state_filter
    return card


def iframe(url: str, *, title: str | None = None,
            aspect_ratio: str | None = None) -> dict:
    """Built-in HA `iframe` card.

    ⚠️  Many sites refuse to be embedded by setting an `X-Frame-Options:
        DENY/SAMEORIGIN` header or a CSP `frame-ancestors` directive
        (e.g. bbc.co.uk, google.com). Such URLs will fail to load with
        `net::ERR_BLOCKED_BY_RESPONSE` in the browser. Known-embeddable
        targets include: Grafana panels, Windy embeds, your own
        /local/* assets, in-network admin UIs you control, and most
        radar/weather widget providers (e.g. embed.windy.com,
        rainviewer.com).
    """
    if not url:
        raise ValueError("url required")
    card: dict[str, Any] = {"type": "iframe", "url": url}
    if title is not None: card["title"] = title
    if aspect_ratio is not None: card["aspect_ratio"] = aspect_ratio
    return card


def weather_forecast(entity: str, *, name: str | None = None,
                       show_forecast: bool = True,
                       forecast_type: str = "daily",
                       theme: str | None = None) -> dict:
    if not entity.startswith("weather."):
        raise ValueError("entity must be a weather.* entity")
    card: dict[str, Any] = {"type": "weather-forecast", "entity": entity}
    if name is not None: card["name"] = name
    if not show_forecast: card["show_forecast"] = False
    if forecast_type != "daily": card["forecast_type"] = forecast_type
    if theme is not None: card["theme"] = theme
    return card


# ─────────────────────────────────────────────────── Mushroom suite

def mushroom_template(primary: str, *, secondary: str | None = None,
                        icon: str | None = None,
                        icon_color: str | None = None,
                        badge_icon: str | None = None,
                        badge_color: str | None = None,
                        entity: str | None = None,
                        tap_action: dict | None = None,
                        hold_action: dict | None = None,
                        double_tap_action: dict | None = None,
                        fill_container: bool = False,
                        multiline_secondary: bool = False) -> dict:
    """`custom:mushroom-template-card` — fully template-driven tile."""
    card: dict[str, Any] = {
        "type": "custom:mushroom-template-card",
        "primary": primary,
    }
    if secondary is not None: card["secondary"] = secondary
    if icon is not None: card["icon"] = icon
    if icon_color is not None: card["icon_color"] = icon_color
    if badge_icon is not None: card["badge_icon"] = badge_icon
    if badge_color is not None: card["badge_color"] = badge_color
    if entity is not None: card["entity"] = entity
    if tap_action is not None: card["tap_action"] = tap_action
    if hold_action is not None: card["hold_action"] = hold_action
    if double_tap_action is not None: card["double_tap_action"] = double_tap_action
    if fill_container: card["fill_container"] = True
    if multiline_secondary: card["multiline_secondary"] = True
    return card


def mushroom_light(entity: str, *, name: str | None = None,
                     icon: str | None = None,
                     show_brightness_control: bool = False,
                     show_color_control: bool = False,
                     show_color_temp_control: bool = False,
                     use_light_color: bool = True,
                     collapsible_controls: bool = False,
                     layout: str | None = None) -> dict:
    if not entity.startswith("light."):
        raise ValueError("entity must be a light.*")
    card: dict[str, Any] = {"type": "custom:mushroom-light-card", "entity": entity}
    if name is not None: card["name"] = name
    if icon is not None: card["icon"] = icon
    if show_brightness_control: card["show_brightness_control"] = True
    if show_color_control: card["show_color_control"] = True
    if show_color_temp_control: card["show_color_temp_control"] = True
    if not use_light_color: card["use_light_color"] = False
    if collapsible_controls: card["collapsible_controls"] = True
    if layout is not None: card["layout"] = layout
    return card


def mushroom_person(entity: str, *, name: str | None = None,
                      icon: str | None = None,
                      layout: str | None = None,
                      hide_name: bool = False,
                      hide_state: bool = False) -> dict:
    if not entity.startswith("person."):
        raise ValueError("entity must be a person.*")
    card: dict[str, Any] = {"type": "custom:mushroom-person-card", "entity": entity}
    if name is not None: card["name"] = name
    if icon is not None: card["icon"] = icon
    if layout is not None: card["layout"] = layout
    if hide_name: card["hide_name"] = True
    if hide_state: card["hide_state"] = True
    return card


def mushroom_climate(entity: str, *, name: str | None = None,
                       icon: str | None = None,
                       show_temperature_control: bool = False,
                       hvac_modes: list[str] | None = None,
                       collapsible_controls: bool = False) -> dict:
    if not entity.startswith("climate."):
        raise ValueError("entity must be a climate.*")
    card: dict[str, Any] = {"type": "custom:mushroom-climate-card", "entity": entity}
    if name is not None: card["name"] = name
    if icon is not None: card["icon"] = icon
    if show_temperature_control: card["show_temperature_control"] = True
    if hvac_modes is not None: card["hvac_modes"] = hvac_modes
    if collapsible_controls: card["collapsible_controls"] = True
    return card


def mushroom_chips(chips: list[dict]) -> dict:
    """`custom:mushroom-chips-card` — row of small status chips."""
    if not chips:
        raise ValueError("at least one chip required")
    return {"type": "custom:mushroom-chips-card", "chips": list(chips)}


def mushroom_title(title: str | None = None,
                     subtitle: str | None = None,
                     alignment: str | None = None) -> dict:
    """`custom:mushroom-title-card` — large section heading."""
    card: dict[str, Any] = {"type": "custom:mushroom-title-card"}
    if title is not None: card["title"] = title
    if subtitle is not None: card["subtitle"] = subtitle
    if alignment is not None: card["alignment"] = alignment
    return card


# ─────────────────────────────────────────────────── ApexCharts

def apexcharts(series: list[dict], *, header: dict | None = None,
                graph_span: str | None = None,
                chart_type: str | None = None,
                stacked: bool | None = None,
                apex_config: dict | None = None,
                yaxis: list[dict] | None = None,
                all_yaxis: dict | None = None) -> dict:
    """`custom:apexcharts-card`. `series` is a list of `{entity, name, type, ...}` dicts."""
    if not series:
        raise ValueError("at least one series required")
    card: dict[str, Any] = {"type": "custom:apexcharts-card", "series": list(series)}
    if header is not None: card["header"] = header
    if graph_span is not None: card["graph_span"] = graph_span
    if chart_type is not None: card["chart_type"] = chart_type
    if stacked is not None: card["stacked"] = stacked
    if apex_config is not None: card["apex_config"] = apex_config
    if yaxis is not None: card["yaxis"] = yaxis
    if all_yaxis is not None: card["all_yaxis"] = all_yaxis
    return card


# ─────────────────────────────────────────────────── Mini Graph Card

def mini_graph(entities: list[str | dict], *, hours_to_show: int = 24,
                points_per_hour: float | None = None,
                line_width: int | None = None,
                line_color: str | None = None,
                name: str | None = None,
                show: dict | None = None,
                color_thresholds: list[dict] | None = None,
                smoothing: bool | None = None) -> dict:
    if not entities:
        raise ValueError("at least one entity required")
    card: dict[str, Any] = {
        "type": "custom:mini-graph-card",
        "entities": list(entities),
        "hours_to_show": hours_to_show,
    }
    if points_per_hour is not None: card["points_per_hour"] = points_per_hour
    if line_width is not None: card["line_width"] = line_width
    if line_color is not None: card["line_color"] = line_color
    if name is not None: card["name"] = name
    if show is not None: card["show"] = show
    if color_thresholds is not None: card["color_thresholds"] = color_thresholds
    if smoothing is not None: card["smoothing"] = smoothing
    return card


# ─────────────────────────────────────────────────── Button Card

def button_card(*, entity: str | None = None,
                  template: str | list[str] | None = None,
                  name: str | None = None,
                  label: str | None = None,
                  icon: str | None = None,
                  color: str | None = None,
                  color_type: str | None = None,
                  show_state: bool | None = None,
                  state: list[dict] | None = None,
                  styles: dict | None = None,
                  tap_action: dict | None = None,
                  hold_action: dict | None = None,
                  variables: dict | None = None) -> dict:
    """`custom:button-card`. Either `entity` or `template` (or both) required."""
    if not entity and not template:
        raise ValueError("entity or template required")
    card: dict[str, Any] = {"type": "custom:button-card"}
    if entity is not None: card["entity"] = entity
    if template is not None: card["template"] = template
    if name is not None: card["name"] = name
    if label is not None: card["label"] = label
    if icon is not None: card["icon"] = icon
    if color is not None: card["color"] = color
    if color_type is not None: card["color_type"] = color_type
    if show_state is not None: card["show_state"] = show_state
    if state is not None: card["state"] = state
    if styles is not None: card["styles"] = styles
    if tap_action is not None: card["tap_action"] = tap_action
    if hold_action is not None: card["hold_action"] = hold_action
    if variables is not None: card["variables"] = variables
    return card


# ─────────────────────────────────────────────────── Bubble Card

def bubble(*, card_type: str = "button", entity: str | None = None,
             name: str | None = None,
             icon: str | None = None,
             sub_button: list[dict] | None = None,
             styles: str | None = None,
             tap_action: dict | None = None,
             button_type: str = "switch") -> dict:
    """`custom:bubble-card` — the unified Clooos bubble UI card.

    For `card_type=button`, `entity` is required and `button_type` (one of
    switch / slider / state / name) defaults to 'switch'.
    """
    if card_type == "button" and not entity:
        raise ValueError("bubble button card requires entity")
    card: dict[str, Any] = {"type": "custom:bubble-card", "card_type": card_type}
    if card_type == "button":
        card["button_type"] = button_type
    if entity is not None: card["entity"] = entity
    if name is not None: card["name"] = name
    if icon is not None: card["icon"] = icon
    if sub_button is not None: card["sub_button"] = sub_button
    if styles is not None: card["styles"] = styles
    if tap_action is not None: card["tap_action"] = tap_action
    return card


# ─────────────────────────────────────────────────── Mini Media Player

def mini_media_player(entity: str, *, name: str | None = None,
                        artwork: str | None = None,
                        background: str | None = None,
                        icon: str | None = None,
                        hide: dict | None = None,
                        shortcuts: dict | None = None,
                        info: str | None = None,
                        group: bool = False) -> dict:
    if not entity.startswith("media_player."):
        raise ValueError("entity must be a media_player.*")
    card: dict[str, Any] = {"type": "custom:mini-media-player", "entity": entity}
    if name is not None: card["name"] = name
    if artwork is not None: card["artwork"] = artwork
    if background is not None: card["background"] = background
    if icon is not None: card["icon"] = icon
    if hide is not None: card["hide"] = hide
    if shortcuts is not None: card["shortcuts"] = shortcuts
    if info is not None: card["info"] = info
    if group: card["group"] = True
    return card


# ─────────────────────────────────────────────────── Auto-Entities

def auto_entities(*, filter: dict, card: dict | None = None,
                    sort: dict | None = None,
                    show_empty: bool = True,
                    unique: bool = False) -> dict:
    """`custom:auto-entities` — filter+populate wrapper.

    `filter` must contain `include` and optionally `exclude`. `card` is
    the template card to wrap each entity in (defaults to `entities`).
    """
    if not filter or not isinstance(filter, dict):
        raise ValueError("filter dict required")
    card_template = card or {"type": "entities", "entities": []}
    out: dict[str, Any] = {
        "type": "custom:auto-entities",
        "card": card_template,
        "filter": filter,
    }
    if sort is not None: out["sort"] = sort
    if not show_empty: out["show_empty"] = False
    if unique: out["unique"] = True
    return out


# ─────────────────────────────────────────────────── Layout Card

def layout_card(cards: list[dict], *, layout_type: str = "grid",
                  layout: dict | None = None) -> dict:
    """`custom:layout-card` — flexible CSS-grid layout for child cards."""
    if not cards:
        raise ValueError("at least one card required")
    out: dict[str, Any] = {
        "type": "custom:layout-card",
        "layout_type": layout_type,
        "cards": list(cards),
    }
    if layout is not None: out["layout"] = layout
    return out


# ─────────────────────────────────────────────────── Decluttering Card

def decluttering(template: str, *, variables: list[dict] | None = None) -> dict:
    """`custom:decluttering-card` — invoke a decluttering template."""
    if not template:
        raise ValueError("template name required")
    card: dict[str, Any] = {"type": "custom:decluttering-card", "template": template}
    if variables is not None: card["variables"] = variables
    return card


# ─────────────────────────────────────────────────── Stack-In-Card

def stack_in_card(cards: list[dict], *, mode: str = "vertical",
                    title: str | None = None,
                    keep: dict | None = None) -> dict:
    """`custom:stack-in-card` — visually unified stack with no borders."""
    if not cards:
        raise ValueError("at least one card required")
    out: dict[str, Any] = {
        "type": "custom:stack-in-card",
        "mode": mode,
        "cards": list(cards),
    }
    if title is not None: out["title"] = title
    if keep is not None: out["keep"] = keep
    return out


# `bar-card` (custom-cards/bar-card) was archived by its author in 2023
# and is not in the HACS default repo list. We deliberately do NOT ship a
# builder for it; for similar bar-style visualisations use the built-in
# `gauge` (with severity) or `tile` (with linear-colored states), or a
# `custom:mushroom-template-card` with a styled progress bar.


# ─────────────────────────────────────────────────── Simple Weather Card

_SIMPLE_WEATHER_INFO_VALUES = {
    "extrema", "precipitation", "precipitation_probability",
    "humidity", "wind_speed", "wind_bearing", "pressure",
}


def simple_weather(entity: str, *, name: str | None = None,
                     primary_info: str | list[str] | None = None,
                     secondary_info: str | list[str] | None = None,
                     backdrop: dict | bool | None = None) -> dict:
    """`custom:simple-weather-card` (kalkih). `primary_info` and
    `secondary_info` accept a single string or a list of:
    extrema / precipitation / precipitation_probability /
    humidity / wind_speed / wind_bearing / pressure.
    """
    if not entity.startswith("weather."):
        raise ValueError("entity must be weather.*")
    def _check(field_name, v):
        if v is None: return
        vals = [v] if isinstance(v, str) else list(v)
        bad = [x for x in vals if x not in _SIMPLE_WEATHER_INFO_VALUES]
        if bad:
            raise ValueError(
                f"{field_name} must be one of "
                f"{sorted(_SIMPLE_WEATHER_INFO_VALUES)}, got bad values {bad}"
            )
    _check("primary_info", primary_info)
    _check("secondary_info", secondary_info)
    card: dict[str, Any] = {"type": "custom:simple-weather-card", "entity": entity}
    if name is not None: card["name"] = name
    if primary_info is not None: card["primary_info"] = primary_info
    if secondary_info is not None: card["secondary_info"] = secondary_info
    if backdrop is not None: card["backdrop"] = backdrop
    return card


# ─────────────────────────────────────────────────── Atomic Calendar Revive

def atomic_calendar(entities: list[str | dict], *, name: str | None = None,
                      default_mode: str = "Event",
                      max_days_to_show: int = 7,
                      show_location: bool | None = None,
                      show_no_event_days: bool | None = None) -> dict:
    """`custom:atomic-calendar-revive` (v10+).

    Entries may be bare entity_ids (auto-wrapped to ``{entity: ...}``) or
    full dicts with ``entity``, ``name``, ``color``. ``default_mode`` is
    ``Event`` (default), ``EventList``, or ``Calendar`` — set on the v10
    field ``defaultMode``.
    """
    if not entities:
        raise ValueError("at least one calendar entity required")
    if default_mode not in ("Event", "EventList", "Calendar"):
        raise ValueError(
            f"default_mode must be Event / EventList / Calendar, got {default_mode!r}"
        )
    norm: list[dict] = []
    for e in entities:
        if isinstance(e, str):
            norm.append({"entity": e})
        elif isinstance(e, dict):
            norm.append(e)
        else:
            raise ValueError(f"calendar entity must be str or dict, got {type(e).__name__}")
    card: dict[str, Any] = {
        "type": "custom:atomic-calendar-revive",
        "entities": norm,
        "defaultMode": default_mode,
        "maxDaysToShow": max_days_to_show,
    }
    if name is not None: card["name"] = name
    if show_location is not None: card["showLocation"] = show_location
    if show_no_event_days is not None: card["showNoEventDays"] = show_no_event_days
    return card


# ─────────────────────────────────────────────────── Digital Clock

def digital_clock(*, time_format: dict | None = None,
                    date_format: dict | None = None,
                    locale: str | None = None,
                    time_zone: str | None = None) -> dict:
    """`custom:digital-clock` (wassy92x).

    `time_format` / `date_format` are Luxon `toLocaleString` option objects
    (camelCase keys: `hour`, `minute`, `weekday`, `day`, `month`, `hour12`).
    """
    card: dict[str, Any] = {"type": "custom:digital-clock"}
    if time_format is not None: card["timeFormat"] = time_format
    if date_format is not None: card["dateFormat"] = date_format
    if locale is not None: card["locale"] = locale
    if time_zone is not None: card["timeZone"] = time_zone
    return card


# ─────────────────────────────────────────────────── Flex Table

def flex_table(*, entities, columns: list[dict],
                 sort_by: str | None = None,
                 strict: bool | None = None) -> dict:
    """`custom:flex-table-card`.

    `entities` accepts:
      - a list of entity_ids (bare strings)
      - a regex/wildcard pattern string (e.g. ``'sensor.*_energy'``)
      - a dict ``{include: <pattern_or_list>, exclude: <pattern_or_list>}``
        where patterns are STRINGS (not auto-entities-style filter dicts).
    """
    if not columns:
        raise ValueError("at least one column required")
    # Validate that filter patterns are strings (catch the common
    # mistake of passing auto-entities-style dict filters).
    if isinstance(entities, dict):
        for key in ("include", "exclude"):
            v = entities.get(key)
            if v is None:
                continue
            items = v if isinstance(v, list) else [v]
            for it in items:
                if not isinstance(it, str):
                    raise ValueError(
                        f"flex-table entities.{key} expects regex/wildcard "
                        f"STRINGS, got {type(it).__name__} {it!r}. "
                        f"(auto-entities-style filter dicts are NOT supported "
                        f"here — use a string pattern like 'light.*' instead.)"
                    )
    card: dict[str, Any] = {
        "type": "custom:flex-table-card",
        "entities": entities,
        "columns": columns,
    }
    if sort_by is not None: card["sort_by"] = sort_by
    if strict is not None: card["strict"] = strict
    return card


# ─────────────────────────────────────────────────── Swiss Army Knife
# AmoebeLabs/swiss-army-knife-card — fully YAML-driven SVG card builder.
# Card structure:
#   type:           custom:swiss-army-knife-card
#   aspectratio:    "W/H" — canvas aspect ratio (default 1/1)
#   entities:       [{entity, name?, attribute?, decimals?, unit?, ...}, …]
#   layout:
#     toolsets:     [{toolset: <name>, position: {cx, cy}, tools: […]}, …]
#
# Each tool has: type, position, entity_index? (0-based into `entities`),
# classes?, styles?, animations?, user_actions?.
#
# 17 tool types (per the official docs): circle, ellipse, line, rectangle,
# rectex (rectangle-ex), regpoly, text, circslider, horseshoe, progpath,
# segarc, slider, sparkline, switch, usersvg, icon (= entity-icon),
# state (= entity-state) — plus `name` and `area` are common in examples.

SAK_TOOL_TYPES = (
    # basic
    "circle", "ellipse", "line", "rectangle", "rectex", "regpoly", "text",
    # advanced
    "circslider", "horseshoe", "progpath", "segarc", "slider", "sparkline",
    "switch", "usersvg",
    # HA-entity
    "icon", "state", "name", "area",
)


def swiss_army_knife(
    *,
    entities: list[str | dict],
    toolsets: list[dict],
    aspectratio: str = "1/1",
    layout_extra: dict | None = None,
) -> dict:
    """`custom:swiss-army-knife-card` (AmoebeLabs).

    ⚠️  **NOT ready for storage-mode auto-setup.** SAK v2.5+ requires a
    full upstream HA-config tree (sak_templates/ with CSS definitions,
    colorstops, derived JS functions, layouts, material3 themes,
    statemaps, tools, toolsets — plus user-css-definitions). The
    upstream YAML uses ``!include_dir_merge_named`` and ``!include``
    directives which **only work in YAML-mode lovelace**.

    For storage-mode dashboards (the kind this harness reads/writes via
    the WebSocket API), every SAK card on the dashboard will fail with
    ``i.setConfig is not a function`` until the user manually copies the
    upstream `ha-config/lovelace/sak_templates/` directory into their
    HA config + reformats the YAML tree into JSON-compatible inline
    structures.

    Recommended path: use SAK on a YAML-mode dashboard (or skip it).
    The builder + tool helpers are kept here so authors who do invest
    in the upstream config can still compose SAK cards programmatically.

    Args (same as before):
        entities: list of entity_ids (auto-wrapped to ``{entity: ...}``)
            or dicts with ``entity``, ``name``, ``attribute``, etc.
        toolsets: list of toolset dicts with
            ``{toolset: <name>, position: {cx, cy}, tools: [...]}``.
        aspectratio: canvas aspect (e.g. "1/1", "2/1"). Default 1/1.
        layout_extra: extra keys merged into ``layout:`` (e.g. ``template:``).

    `entities` — list of entity_ids (auto-wrapped to ``{entity: ...}``) OR
                 dicts with ``entity``, ``name``, ``attribute``, etc.
    `toolsets` — list of toolset dicts. Each toolset has:
        ``{toolset: <name>, position: {cx, cy}, tools: [<tool>, ...]}``.
        Build tools with the ``sak_*`` helpers below.
    `aspectratio` — canvas aspect (e.g. "1/1", "2/1", "10/4"). Default 1/1.
    `layout_extra` — extra keys to merge under `layout:` (e.g. `template:`).
    """
    if not entities:
        raise ValueError("swiss-army-knife: at least one entity required")
    if not toolsets:
        raise ValueError("swiss-army-knife: at least one toolset required")
    # Normalize entities
    norm_entities: list[dict] = []
    for e in entities:
        if isinstance(e, str):
            norm_entities.append({"entity": e})
        elif isinstance(e, dict):
            norm_entities.append(e)
        else:
            raise ValueError(
                f"entities[*] must be str or dict, got {type(e).__name__}"
            )
    # Validate toolsets shape
    for i, ts in enumerate(toolsets):
        if not isinstance(ts, dict):
            raise ValueError(f"toolsets[{i}] must be a dict")
        if "tools" not in ts or not isinstance(ts["tools"], list):
            raise ValueError(f"toolsets[{i}] missing 'tools' list")
        # Each tool must have a valid type
        for j, t in enumerate(ts["tools"]):
            tt = t.get("type")
            if tt not in SAK_TOOL_TYPES:
                raise ValueError(
                    f"toolsets[{i}].tools[{j}] has unknown type "
                    f"{tt!r}; valid: {SAK_TOOL_TYPES}"
                )
    layout: dict[str, Any] = {"toolsets": toolsets}
    if layout_extra:
        layout = {**layout_extra, **layout}
    return {
        "type": "custom:swiss-army-knife-card",
        "aspectratio": aspectratio,
        "entities": norm_entities,
        "layout": layout,
    }


def ensure_sak_templates_on_dashboard(client, url_path: str | None,
                                          *, sys_templates: dict | None = None,
                                          user_templates: dict | None = None) -> bool:
    """Add `sak_sys_templates` + `sak_user_templates` to a dashboard root.

    SAK v2.5+ refuses to instantiate any tool if these keys are missing.
    Pass real templates if you have them; pass `None` to leave existing
    or set an empty dict.

    ⚠️  An EMPTY `sak_sys_templates: {}` is **not enough** for cards that
    use template references (`template:` inside a tool). SAK looks up
    subkeys like ``colorstops``, ``layouts``, ``tools``, ``toolsets``,
    ``derived``, ``statemaps`` and errors if a referenced one is missing.
    For tool-only cards that never reference a template, the empty form
    typically silences the global "system templates NOT defined" error.

    See :func:`fetch_sak_system_templates` to pull the upstream system
    templates from the AmoebeLabs repo as a starting point.

    Returns True if the dashboard was modified, False if both keys
    already existed and no overrides were passed.
    """
    from cli_anything.homeassistant.core import lovelace as ll
    cfg = ll.get_dashboard_config(client, url_path)
    changed = False
    if "sak_sys_templates" not in cfg:
        cfg["sak_sys_templates"] = sys_templates if sys_templates is not None else {}
        changed = True
    elif sys_templates is not None:
        cfg["sak_sys_templates"] = sys_templates
        changed = True
    if "sak_user_templates" not in cfg:
        cfg["sak_user_templates"] = user_templates if user_templates is not None else {}
        changed = True
    elif user_templates is not None:
        cfg["sak_user_templates"] = user_templates
        changed = True
    if changed:
        ll.save_dashboard_config(client, url_path, cfg)
    return changed


def fetch_sak_system_templates(*, branch: str = "master") -> dict:
    """Fetch the upstream SAK `sak_templates` directory from GitHub and
    flatten it into a dict suitable for the dashboard root.

    Returns a dict keyed by template name (e.g. ``colorstops``, ``layouts``,
    ``tools``, etc.) ready to merge into ``sak_sys_templates``. Walks each
    `templates/<NN-name>/` subdir, parses every `.yaml` file inside,
    merges them under the directory's short name (everything after the
    `NN-` prefix).

    Requires PyYAML to be importable. Network access required.
    """
    import urllib.request, json as _json
    try:
        import yaml  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "PyYAML required to load SAK templates "
            "(pip install pyyaml)"
        ) from e

    base = "https://api.github.com"
    repo = "AmoebeLabs/swiss-army-knife-card"
    root_path = f"ha-config/lovelace/sak_templates/templates"

    def _gh(path):
        url = f"{base}/repos/{repo}/contents/{path}?ref={branch}"
        with urllib.request.urlopen(url) as r:
            return _json.loads(r.read())

    out: dict[str, Any] = {}
    try:
        dirs = _gh(root_path)
    except Exception as e:
        raise RuntimeError(f"failed to list SAK templates: {e}") from e

    for entry in dirs:
        if entry.get("type") != "dir":
            continue
        name = entry["name"]  # e.g. "11-colorstops"
        short = name.split("-", 1)[1] if "-" in name else name
        merged: dict[str, Any] = {}
        for f in _gh(f"{root_path}/{name}"):
            if f.get("type") != "file" or not f["name"].endswith(".yaml"):
                continue
            with urllib.request.urlopen(f["download_url"]) as r:
                doc = yaml.safe_load(r.read()) or {}
            if isinstance(doc, dict):
                merged.update(doc)
        out[short] = merged
    return out


# Toolset helper — keeps the SAK config readable when authoring cards.
def sak_toolset(name: str, *, cx: float = 50, cy: float = 50,
                  tools: list[dict] | None = None) -> dict:
    return {
        "toolset": name,
        "position": {"cx": cx, "cy": cy},
        "tools": list(tools or []),
    }


# ─── Tool helpers ─────────────────────────────────────────────────────
# Each returns a tool dict with the right `type:`. Pass extra kwargs to
# override anything (styles, classes, animations, entity_index, etc.).

def _sak_tool(type_: str, **kw) -> dict:
    out: dict[str, Any] = {"type": type_}
    # `position`, `entity_index`, `styles`, `classes`, `animations`,
    # `user_actions`, `text`, `icon` etc. all pass through.
    for k, v in kw.items():
        if v is None:
            continue
        out[k] = v
    return out


def sak_circle(*, cx: float, cy: float, radius: float = 45,
                 entity_index: int | None = None,
                 styles: dict | None = None,
                 classes: dict | None = None,
                 animations: list | None = None) -> dict:
    return _sak_tool("circle",
                      position={"cx": cx, "cy": cy, "radius": radius},
                      entity_index=entity_index, styles=styles,
                      classes=classes, animations=animations)


def sak_ellipse(*, cx: float, cy: float, rx: float, ry: float,
                  styles: dict | None = None, **kw) -> dict:
    return _sak_tool("ellipse",
                      position={"cx": cx, "cy": cy, "rx": rx, "ry": ry},
                      styles=styles, **kw)


def sak_line(*, x1: float, y1: float, x2: float, y2: float,
               styles: dict | None = None, **kw) -> dict:
    return _sak_tool("line",
                      position={"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                      styles=styles, **kw)


def sak_rectangle(*, cx: float, cy: float, width: float, height: float,
                    rx: float | None = None,
                    styles: dict | None = None, **kw) -> dict:
    pos: dict[str, Any] = {"cx": cx, "cy": cy,
                            "width": width, "height": height}
    if rx is not None: pos["rx"] = rx
    return _sak_tool("rectangle", position=pos, styles=styles, **kw)


def sak_text(text: str, *, cx: float, cy: float,
               align: str | None = None,
               entity_index: int | None = None,
               styles: dict | None = None, **kw) -> dict:
    pos: dict[str, Any] = {"cx": cx, "cy": cy}
    if align is not None: pos["align"] = align
    return _sak_tool("text", text=text, position=pos,
                      entity_index=entity_index, styles=styles, **kw)


def sak_icon(*, cx: float, cy: float, entity_index: int = 0,
               icon_size: float = 25, align: str = "center",
               styles: dict | None = None, **kw) -> dict:
    return _sak_tool("icon",
                      position={"cx": cx, "cy": cy,
                                 "align": align, "icon_size": icon_size},
                      entity_index=entity_index, styles=styles, **kw)


def sak_state(*, cx: float, cy: float, entity_index: int = 0,
                styles: dict | None = None, **kw) -> dict:
    return _sak_tool("state",
                      position={"cx": cx, "cy": cy},
                      entity_index=entity_index, styles=styles, **kw)


def sak_name(*, cx: float, cy: float, entity_index: int = 0,
               styles: dict | None = None, **kw) -> dict:
    return _sak_tool("name",
                      position={"cx": cx, "cy": cy},
                      entity_index=entity_index, styles=styles, **kw)


def sak_segarc(*, cx: float, cy: float, radius: float,
                 start_angle: float = -200, end_angle: float = 20,
                 entity_index: int = 0,
                 segments: dict | None = None,
                 scale: dict | None = None,
                 styles: dict | None = None, **kw) -> dict:
    """Segmented arc (great for gauges)."""
    return _sak_tool("segarc",
                      position={"cx": cx, "cy": cy, "radius": radius,
                                 "start_angle": start_angle,
                                 "end_angle": end_angle},
                      entity_index=entity_index,
                      segments=segments, scale=scale,
                      styles=styles, **kw)


def sak_horseshoe(*, cx: float, cy: float, radius: float,
                    entity_index: int = 0,
                    styles: dict | None = None, **kw) -> dict:
    return _sak_tool("horseshoe",
                      position={"cx": cx, "cy": cy, "radius": radius},
                      entity_index=entity_index, styles=styles, **kw)


def sak_sparkline(*, cx: float, cy: float, width: float, height: float,
                    entity_index: int = 0,
                    hours: int = 24,
                    styles: dict | None = None, **kw) -> dict:
    return _sak_tool("sparkline",
                      position={"cx": cx, "cy": cy,
                                 "width": width, "height": height,
                                 "hours": hours},
                      entity_index=entity_index, styles=styles, **kw)


def sak_slider(*, cx: float, cy: float, length: float, orientation: str = "horizontal",
                 entity_index: int = 0, styles: dict | None = None, **kw) -> dict:
    return _sak_tool("slider",
                      position={"cx": cx, "cy": cy, "length": length,
                                 "orientation": orientation},
                      entity_index=entity_index, styles=styles, **kw)


def sak_switch(*, cx: float, cy: float, width: float = 30, height: float = 15,
                 entity_index: int = 0, styles: dict | None = None, **kw) -> dict:
    return _sak_tool("switch",
                      position={"cx": cx, "cy": cy,
                                 "width": width, "height": height},
                      entity_index=entity_index, styles=styles, **kw)


def sak_usersvg(*, cx: float, cy: float, width: float, height: float,
                  uri: str, styles: dict | None = None, **kw) -> dict:
    """User-supplied SVG embedded in the card."""
    return _sak_tool("usersvg",
                      position={"cx": cx, "cy": cy,
                                 "width": width, "height": height},
                      uri=uri, styles=styles, **kw)


def sak_circslider(*, cx: float, cy: float, radius: float,
                     entity_index: int = 0,
                     start_angle: float = 0, end_angle: float = 360,
                     styles: dict | None = None, **kw) -> dict:
    return _sak_tool("circslider",
                      position={"cx": cx, "cy": cy, "radius": radius,
                                 "start_angle": start_angle,
                                 "end_angle": end_angle},
                      entity_index=entity_index, styles=styles, **kw)


def sak_progpath(*, cx: float, cy: float, width: float, height: float,
                   entity_index: int = 0,
                   styles: dict | None = None, **kw) -> dict:
    return _sak_tool("progpath",
                      position={"cx": cx, "cy": cy,
                                 "width": width, "height": height},
                      entity_index=entity_index, styles=styles, **kw)


def sak_regpoly(*, cx: float, cy: float, radius: float, sides: int = 6,
                  styles: dict | None = None, **kw) -> dict:
    return _sak_tool("regpoly",
                      position={"cx": cx, "cy": cy, "radius": radius,
                                 "sides": sides},
                      styles=styles, **kw)


def sak_rectex(*, cx: float, cy: float, width: float, height: float,
                 styles: dict | None = None, **kw) -> dict:
    """RectEx — rectangle with per-corner radii / advanced shapes."""
    return _sak_tool("rectex",
                      position={"cx": cx, "cy": cy,
                                 "width": width, "height": height},
                      styles=styles, **kw)


def sak_area(*, cx: float, cy: float, entity_index: int = 0,
               styles: dict | None = None, **kw) -> dict:
    return _sak_tool("area",
                      position={"cx": cx, "cy": cy},
                      entity_index=entity_index, styles=styles, **kw)


# ─────────────────────────────────────────────────── Modern Circular Gauge

def modern_circular_gauge(entity: str, *,
                            min: float | str = 0,
                            max: float | str = 100,
                            gauge_type: str = "standard",
                            attribute: str | None = None,
                            unit: str | None = None,
                            decimals: int | None = None,
                            name: str | None = None,
                            icon: str | None = None,
                            label: str | None = None,
                            needle: bool | None = None,
                            show_graph: bool | None = None,
                            adaptive_icon_color: bool | None = None,
                            secondary: dict | None = None,
                            tertiary: dict | None = None,
                            segments: list[dict] | None = None) -> dict:
    """`custom:modern-circular-gauge` (selvalt7).

    `gauge_type` is one of: standard / half / full. `segments` lets you
    set colour bands like `[{from: 13, color: [11, 182, 239]}, ...]`.
    """
    if not entity:
        raise ValueError("entity required")
    if gauge_type not in ("standard", "half", "full"):
        raise ValueError(f"gauge_type must be standard/half/full, got {gauge_type!r}")
    card: dict[str, Any] = {
        "type": "custom:modern-circular-gauge",
        "entity": entity, "min": min, "max": max,
        "gauge_type": gauge_type,
    }
    if attribute is not None: card["attribute"] = attribute
    if unit is not None: card["unit"] = unit
    if decimals is not None: card["decimals"] = decimals
    if name is not None: card["name"] = name
    if icon is not None: card["icon"] = icon
    if label is not None: card["label"] = label
    if needle is not None: card["needle"] = needle
    if show_graph is not None: card["show_graph"] = show_graph
    if adaptive_icon_color is not None: card["adaptive_icon_color"] = adaptive_icon_color
    if secondary is not None: card["secondary"] = secondary
    if tertiary is not None: card["tertiary"] = tertiary
    if segments is not None: card["segments"] = segments
    return card


# ─────────────────────────────────────────────────── Horizon Card

def horizon_card(*, title: str | None = None,
                   moon: bool = True,
                   refresh_period: int | None = None,
                   southern_flip: bool = False,
                   fields: dict[str, bool] | None = None,
                   language: str | None = None,
                   time_format: str | None = None,
                   no_card: bool = False) -> dict:
    """`custom:horizon-card` (rejuvenate). Sun + moon visualization.

    `fields` is an optional dict of visibility toggles, e.g.
    ``{sunrise: true, sunset: true, dawn: true, noon: true, dusk: true,
       azimuth: false, elevation: false, moonrise: false, moonset: false,
       moon_phase: false}``. Pass into the `fields:` key of the card.
    """
    card: dict[str, Any] = {"type": "custom:horizon-card"}
    if title is not None: card["title"] = title
    if not moon: card["moon"] = False
    if refresh_period is not None: card["refresh_period"] = refresh_period
    if southern_flip: card["southern_flip"] = True
    if fields is not None: card["fields"] = fields
    if language is not None: card["language"] = language
    if time_format is not None: card["time_format"] = time_format
    if no_card: card["no_card"] = True
    return card


# ─────────────────────────────────────────────────── Calendar Card Pro

def calendar_card_pro(entities: list[str | dict], *,
                        days_to_show: int = 3,
                        show_location: bool | None = None,
                        title: str | None = None,
                        max_events: int | None = None,
                        compact_mode: bool | None = None,
                        time_format: str | None = None) -> dict:
    """`custom:calendar-card-pro` (alexpfau).

    Entity entries can be bare strings (auto-wrapped) or dicts with
    ``entity``, ``label``, ``color``, ``accent_color``, ``allowlist``,
    ``blocklist``.
    """
    if not entities:
        raise ValueError("at least one calendar entity required")
    norm: list = []
    for e in entities:
        if isinstance(e, str):
            norm.append(e)
        elif isinstance(e, dict):
            if not e.get("entity"):
                raise ValueError("entity dict must have an 'entity' key")
            norm.append(e)
        else:
            raise ValueError(
                f"calendar entity must be str or dict, got {type(e).__name__}"
            )
    card: dict[str, Any] = {
        "type": "custom:calendar-card-pro",
        "entities": norm,
        "days_to_show": days_to_show,
    }
    if show_location is not None: card["show_location"] = show_location
    if title is not None: card["title"] = title
    if max_events is not None: card["max_events"] = max_events
    if compact_mode is not None: card["compact_mode"] = compact_mode
    if time_format is not None: card["time_format"] = time_format
    return card


# ─────────────────────────────────────────────────── Weather Chart Card
# (mlamberts78/weather-chart-card — repo archived 2024 but still installable
# and widely used; not flagged as deprecated by HACS itself yet.)

def weather_chart_card(entity: str, *,
                          title: str | None = None,
                          show_main: bool | None = None,
                          show_attributes: bool | None = None,
                          show_time: bool | None = None,
                          show_date: bool | None = None,
                          animated_icons: bool | None = None,
                          forecast: dict | None = None,
                          units: dict | None = None,
                          locale: str | None = None,
                          # Custom-sensor overrides
                          temp: str | None = None,
                          press: str | None = None,
                          humid: str | None = None,
                          uv: str | None = None,
                          winddir: str | None = None,
                          windspeed: str | None = None) -> dict:
    """`custom:weather-chart-card` (mlamberts78). Forecast charts + tiles."""
    if not entity.startswith("weather."):
        raise ValueError("entity must be a weather.* entity")
    card: dict[str, Any] = {
        "type": "custom:weather-chart-card",
        "entity": entity,
    }
    for k, v in (("title", title), ("show_main", show_main),
                  ("show_attributes", show_attributes),
                  ("show_time", show_time), ("show_date", show_date),
                  ("animated_icons", animated_icons), ("forecast", forecast),
                  ("units", units), ("locale", locale),
                  ("temp", temp), ("press", press), ("humid", humid),
                  ("uv", uv), ("winddir", winddir), ("windspeed", windspeed)):
        if v is not None:
            card[k] = v
    return card


# ─────────────────────────────────────────────────── Room Summary Card

def room_summary_card(area: str, *,
                         entity: str | None = None,
                         entities: list[str | dict] | None = None,
                         features: dict | None = None,
                         background: dict | None = None,
                         occupancy: dict | None = None,
                         thresholds: dict | None = None) -> dict:
    """`custom:room-summary-card` (homeassistant-extras).

    `area` is the area_id (required). `entities` lets you override the
    auto-discovered entity list. `features`, `background`, `occupancy`,
    `thresholds` carry advanced presentation options.
    """
    if not area:
        raise ValueError("area required")
    card: dict[str, Any] = {
        "type": "custom:room-summary-card",
        "area": area,
    }
    if entity is not None: card["entity"] = entity
    if entities is not None: card["entities"] = entities
    if features is not None: card["features"] = features
    if background is not None: card["background"] = background
    if occupancy is not None: card["occupancy"] = occupancy
    if thresholds is not None: card["thresholds"] = thresholds
    return card


# ─────────────────────────────────────────────────── Expander Card

def expander_card(cards: list[dict], *,
                     title: str | None = None,
                     icon: str = "mdi:chevron-down",
                     expanded: bool = False,
                     animation: bool = True,
                     haptic: str = "light",
                     clear: bool = False,
                     clear_children: bool = False,
                     gap: str | None = None,
                     padding: str | None = None,
                     title_card: dict | None = None,
                     title_card_clickable: bool = False,
                     storage_id: str | None = None,
                     expander_card_id: str | None = None) -> dict:
    """`custom:expander-card` (MelleD). Collapsible group of child cards."""
    if not cards:
        raise ValueError("at least one child card required")
    if haptic not in ("light", "medium", "heavy", "success",
                       "warning", "failure", "selection", "none"):
        raise ValueError(f"invalid haptic: {haptic!r}")
    card: dict[str, Any] = {
        "type": "custom:expander-card",
        "icon": icon, "expanded": expanded,
        "animation": animation, "haptic": haptic,
        "cards": list(cards),
    }
    if title is not None: card["title"] = title
    if clear: card["clear"] = True
    if clear_children: card["clear-children"] = True
    if gap is not None: card["gap"] = gap
    if padding is not None: card["padding"] = padding
    if title_card is not None: card["title-card"] = title_card
    if title_card_clickable: card["title-card-clickable"] = True
    if storage_id is not None: card["storage-id"] = storage_id
    if expander_card_id is not None: card["expander-card-id"] = expander_card_id
    return card


# ─────────────────────────────────────────────────── Simple Swipe Card

def simple_swipe_card(cards: list[dict], *,
                        view_mode: str = "single",
                        show_pagination: bool | None = None,
                        card_spacing: int | None = None,
                        swipe_direction: str = "horizontal",
                        swipe_behavior: str = "single",
                        loop_mode: str = "none",
                        enable_auto_swipe: bool = False,
                        auto_swipe_interval: int | None = None,
                        state_entity: str | None = None) -> dict:
    """`custom:simple-swipe-card` (nutteloost). Swipe-through carousel."""
    if not cards:
        raise ValueError("at least one card required")
    if view_mode not in ("single", "carousel"):
        raise ValueError(f"view_mode must be single/carousel, got {view_mode!r}")
    if swipe_direction not in ("horizontal", "vertical"):
        raise ValueError(f"swipe_direction must be horizontal/vertical, got {swipe_direction!r}")
    if swipe_behavior not in ("single", "free"):
        raise ValueError(f"swipe_behavior must be single/free, got {swipe_behavior!r}")
    if loop_mode not in ("none", "loopback", "infinite"):
        raise ValueError(f"loop_mode must be none/loopback/infinite, got {loop_mode!r}")
    card: dict[str, Any] = {
        "type": "custom:simple-swipe-card",
        "cards": list(cards),
        "view_mode": view_mode,
        "swipe_direction": swipe_direction,
        "swipe_behavior": swipe_behavior,
        "loop_mode": loop_mode,
    }
    if show_pagination is not None: card["show_pagination"] = show_pagination
    if card_spacing is not None: card["card_spacing"] = card_spacing
    if enable_auto_swipe: card["enable_auto_swipe"] = True
    if auto_swipe_interval is not None: card["auto_swipe_interval"] = auto_swipe_interval
    if state_entity is not None: card["state_entity"] = state_entity
    return card


# ─────────────────────────────────────────────────── registry of builders

BUILDERS: dict[str, callable] = {
    # built-ins
    "entities": entities,
    "vertical-stack": vertical_stack,
    "horizontal-stack": horizontal_stack,
    "grid": grid,
    "glance": glance,
    "gauge": gauge,
    "tile": tile,
    "button": button,
    "markdown": markdown,
    "history-graph": history_graph,
    "statistics-graph": statistics_graph,
    "conditional": conditional,
    "picture-elements": picture_elements,
    "iframe": iframe,
    "weather-forecast": weather_forecast,
    # mushroom suite
    "mushroom-template": mushroom_template,
    "mushroom-light": mushroom_light,
    "mushroom-person": mushroom_person,
    "mushroom-climate": mushroom_climate,
    "mushroom-chips": mushroom_chips,
    "mushroom-title": mushroom_title,
    # other custom
    "apexcharts": apexcharts,
    "mini-graph": mini_graph,
    "button-card": button_card,
    "bubble": bubble,
    "mini-media-player": mini_media_player,
    "auto-entities": auto_entities,
    "layout-card": layout_card,
    "calendar-card-pro": calendar_card_pro,
    "decluttering": decluttering,
    "expander": expander_card,
    "horizon": horizon_card,
    "modern-circular-gauge": modern_circular_gauge,
    "room-summary": room_summary_card,
    "simple-swipe": simple_swipe_card,
    "stack-in-card": stack_in_card,
    "swiss-army-knife": swiss_army_knife,
    "weather-chart": weather_chart_card,
    "simple-weather": simple_weather,
    "atomic-calendar": atomic_calendar,
    "digital-clock": digital_clock,
    "flex-table": flex_table,
}


def list_builders() -> list[str]:
    return sorted(BUILDERS.keys())


def build(card_type: str, **kwargs) -> dict:
    """Generic dispatcher — `build("mushroom-light", entity="light.x", ...)`."""
    if card_type not in BUILDERS:
        raise ValueError(
            f"unknown card type {card_type!r}; known: {', '.join(list_builders())}"
        )
    return BUILDERS[card_type](**kwargs)


# ════════════════════════════════════════════════════════════════════════
# Builder metadata — example, resource dependency, summary
# ════════════════════════════════════════════════════════════════════════
# Each entry is keyed by the same name used in BUILDERS. The validator and
# SKILL.md generator both consume this. `card_type` is the literal `type:`
# value the card uses (e.g. "tile" or "custom:apexcharts-card"). `resource`
# is the canonical HACS repo URL (None for native HA cards). `example` is
# a complete, valid card dict that can be dropped straight into a view.

BUILDER_META: dict[str, dict] = {
    "entities": {
        "card_type": "entities",
        "resource": None,
        "summary": "Classic list of entity rows with toggles/state.",
        "example": {"type": "entities", "title": "Lights",
                      "entities": ["light.kitchen", "light.hall"]},
    },
    "vertical-stack": {
        "card_type": "vertical-stack",
        "resource": None,
        "summary": "Stack child cards vertically.",
        "example": {"type": "vertical-stack", "cards": [
            {"type": "tile", "entity": "light.kitchen"},
            {"type": "tile", "entity": "light.hall"},
        ]},
    },
    "horizontal-stack": {
        "card_type": "horizontal-stack",
        "resource": None,
        "summary": "Stack child cards horizontally.",
        "example": {"type": "horizontal-stack", "cards": [
            {"type": "tile", "entity": "light.kitchen"},
            {"type": "tile", "entity": "light.hall"},
        ]},
    },
    "grid": {
        "card_type": "grid",
        "resource": None,
        "summary": "Grid of cards with `columns` and optional `square`.",
        "example": {"type": "grid", "columns": 2, "square": False,
                      "cards": [
                          {"type": "tile", "entity": "light.kitchen"},
                          {"type": "tile", "entity": "light.hall"},
                      ]},
    },
    "glance": {
        "card_type": "glance",
        "resource": None,
        "summary": "Compact horizontal row of entities with state.",
        "example": {"type": "glance", "title": "Status",
                      "entities": ["sensor.outdoor_temp",
                                    "sensor.indoor_temp"]},
    },
    "gauge": {
        "card_type": "gauge",
        "resource": None,
        "summary": "Numeric gauge with severity thresholds.",
        "example": {"type": "gauge", "entity": "sensor.cpu_temp",
                      "min": 0, "max": 100,
                      "severity": {"green": 0, "yellow": 60, "red": 80}},
    },
    "tile": {
        "card_type": "tile",
        "resource": None,
        "summary": "Modern HA tile — primary entity surface (recommended over button).",
        "example": {"type": "tile", "entity": "light.kitchen",
                      "name": "Kitchen", "icon": "mdi:silverware"},
    },
    "button": {
        "card_type": "button",
        "resource": None,
        "summary": "Tap-action button. Prefer `tile` for entity control.",
        "example": {"type": "button", "entity": "light.kitchen",
                      "name": "Kitchen", "show_state": True},
    },
    "markdown": {
        "card_type": "markdown",
        "resource": None,
        "summary": "Render markdown + Jinja templates.",
        "example": {"type": "markdown", "title": "Hello",
                      "content": "## Welcome, {{ user }}"},
    },
    "history-graph": {
        "card_type": "history-graph",
        "resource": None,
        "summary": "Line graph of recent state history.",
        "example": {"type": "history-graph", "hours_to_show": 24,
                      "entities": ["sensor.outdoor_temp"]},
    },
    "statistics-graph": {
        "card_type": "statistics-graph",
        "resource": None,
        "summary": "Graph of long-term-statistics (LTS) values.",
        "example": {"type": "statistics-graph", "days_to_show": 30,
                      "entities": ["sensor.energy"],
                      "stat_types": ["mean", "max"]},
    },
    "conditional": {
        "card_type": "conditional",
        "resource": None,
        "summary": "Show the inner `card` only when conditions match.",
        "example": {"type": "conditional",
                      "conditions": [{"entity": "binary_sensor.guest_mode",
                                       "state": "on"}],
                      "card": {"type": "tile",
                                 "entity": "light.guest_room"}},
    },
    "picture-elements": {
        "card_type": "picture-elements",
        "resource": None,
        "summary": "Background image with absolutely-positioned elements.",
        "example": {"type": "picture-elements",
                      "image": "/local/floorplan.png",
                      "elements": [
                          {"type": "state-icon", "entity": "light.kitchen",
                            "style": {"top": "30%", "left": "40%"}},
                      ]},
    },
    "iframe": {
        "card_type": "iframe",
        "resource": None,
        "summary": "Embed external URL. WARNING: most sites block iframing.",
        "example": {"type": "iframe",
                      "url": "https://embed.windy.com/embed.html?...",
                      "aspect_ratio": "16:9"},
    },
    "weather-forecast": {
        "card_type": "weather-forecast",
        "resource": None,
        "summary": "Native weather forecast (daily/hourly).",
        "example": {"type": "weather-forecast", "entity": "weather.home",
                      "forecast_type": "daily", "show_forecast": True},
    },
    "mushroom-template": {
        "card_type": "custom:mushroom-template-card",
        "resource": "https://github.com/piitaya/lovelace-mushroom",
        "summary": "Generic mushroom card driven by Jinja templates.",
        "example": {"type": "custom:mushroom-template-card",
                      "primary": "Hello {{ states('sensor.x') }}",
                      "secondary": "subtitle",
                      "icon": "mdi:home",
                      "fill_container": True,
                      "multiline_secondary": True},
    },
    "mushroom-light": {
        "card_type": "custom:mushroom-light-card",
        "resource": "https://github.com/piitaya/lovelace-mushroom",
        "summary": "Light entity with mushroom styling + brightness/color controls.",
        "example": {"type": "custom:mushroom-light-card",
                      "entity": "light.kitchen", "name": "Kitchen",
                      "show_brightness_control": True,
                      "use_light_color": True,
                      "fill_container": True},
    },
    "mushroom-person": {
        "card_type": "custom:mushroom-person-card",
        "resource": "https://github.com/piitaya/lovelace-mushroom",
        "summary": "Person tracker with location and presence icon.",
        "example": {"type": "custom:mushroom-person-card",
                      "entity": "person.jon", "name": "Jon",
                      "icon_type": "entity-picture",
                      "layout": "horizontal"},
    },
    "mushroom-climate": {
        "card_type": "custom:mushroom-climate-card",
        "resource": "https://github.com/piitaya/lovelace-mushroom",
        "summary": "Climate entity tile with HVAC mode buttons.",
        "example": {"type": "custom:mushroom-climate-card",
                      "entity": "climate.living_room",
                      "hvac_modes": ["off", "heat", "cool"],
                      "show_temperature_control": True},
    },
    "mushroom-chips": {
        "card_type": "custom:mushroom-chips-card",
        "resource": "https://github.com/piitaya/lovelace-mushroom",
        "summary": "Horizontal row of small chips (status indicators).",
        "example": {"type": "custom:mushroom-chips-card",
                      "chips": [
                          {"type": "weather", "entity": "weather.home"},
                          {"type": "entity", "entity": "sensor.outdoor_temp"},
                      ]},
    },
    "mushroom-title": {
        "card_type": "custom:mushroom-title-card",
        "resource": "https://github.com/piitaya/lovelace-mushroom",
        "summary": "Heading text with optional subtitle.",
        "example": {"type": "custom:mushroom-title-card",
                      "title": "Living Room", "subtitle": "Always cosy"},
    },
    "apexcharts": {
        "card_type": "custom:apexcharts-card",
        "resource": "https://github.com/RomRider/apexcharts-card",
        "summary": "Time-series charts via ApexCharts.js. Powerful but strict schema — series entries take ONLY series fields (no card_mod inside).",
        "example": {"type": "custom:apexcharts-card",
                      "graph_span": "24h",
                      "header": {"show": True, "title": "Grid · 24h"},
                      "series": [
                          {"entity": "sensor.smart_meter_power",
                            "name": "Grid", "type": "area"},
                      ]},
    },
    "mini-graph": {
        "card_type": "custom:mini-graph-card",
        "resource": "https://github.com/kalkih/mini-graph-card",
        "summary": "Compact sparkline graph for one or more sensors.",
        "example": {"type": "custom:mini-graph-card",
                      "entities": [{"entity": "sensor.outdoor_temp",
                                     "name": "Outdoor"}],
                      "hours_to_show": 24,
                      "line_width": 3,
                      "show": {"name": True, "state": True, "legend": False}},
    },
    "button-card": {
        "card_type": "custom:button-card",
        "resource": "https://github.com/custom-cards/button-card",
        "summary": "Highly-customisable button with templates and state-driven styling.",
        "example": {"type": "custom:button-card",
                      "entity": "light.kitchen", "name": "Kitchen",
                      "show_state": True, "color_type": "card"},
    },
    "bubble": {
        "card_type": "custom:bubble-card",
        "resource": "https://github.com/Clooos/Bubble-Card",
        "summary": "Bubble UI cards (popup, button, separator, slider, etc).",
        "example": {"type": "custom:bubble-card",
                      "card_type": "button", "button_type": "switch",
                      "entity": "light.kitchen", "name": "Kitchen"},
    },
    "mini-media-player": {
        "card_type": "custom:mini-media-player",
        "resource": "https://github.com/kalkih/mini-media-player",
        "summary": "Compact media player with artwork, controls, shortcuts.",
        "example": {"type": "custom:mini-media-player",
                      "entity": "media_player.spotify",
                      "artwork": "cover", "hide": {"power": False}},
    },
    "auto-entities": {
        "card_type": "custom:auto-entities",
        "resource": "https://github.com/thomasloven/lovelace-auto-entities",
        "summary": "Dynamically-populated wrapper card. `filter` selects entities (include patterns are dicts, not bare strings).",
        "example": {"type": "custom:auto-entities",
                      "filter": {"include": [{"domain": "light"}]},
                      "card": {"type": "entities", "title": "All lights"}},
    },
    "layout-card": {
        "card_type": "custom:layout-card",
        "resource": "https://github.com/thomasloven/lovelace-layout-card",
        "summary": "Custom layouts (grid/horizontal/vertical/masonry) with per-card sizing.",
        "example": {"type": "custom:layout-card", "layout_type": "grid",
                      "cards": [{"type": "tile", "entity": "light.kitchen"}]},
    },
    "calendar-card-pro": {
        "card_type": "custom:calendar-card-pro",
        "resource": "https://github.com/alexpfau/calendar-card-pro",
        "summary": "Calendar agenda view (compact, multi-day, color-coded).",
        "example": {"type": "custom:calendar-card-pro",
                      "entities": [{"entity": "calendar.personal",
                                     "color": "#FF7A00"}],
                      "days_to_show": 7},
    },
    "decluttering": {
        "card_type": "custom:decluttering-card",
        "resource": "https://github.com/custom-cards/decluttering-card",
        "summary": "Reusable card template (DRY common card configs).",
        "example": {"type": "custom:decluttering-card",
                      "template": "room_tile",
                      "variables": [{"entity": "light.kitchen"}]},
    },
    "expander": {
        "card_type": "custom:expander-card",
        "resource": "https://github.com/Alia5/lovelace-expander-card",
        "summary": "Collapsible card wrapper.",
        "example": {"type": "custom:expander-card",
                      "title": "Details", "expanded": False,
                      "cards": [{"type": "tile", "entity": "light.kitchen"}]},
    },
    "horizon": {
        "card_type": "custom:horizon-card",
        "resource": "https://github.com/rejuvenate/lovelace-horizon-card",
        "summary": "Sun arc + dawn/dusk panel.",
        "example": {"type": "custom:horizon-card",
                      "title": "Sun",
                      "fields": {"sunrise": True, "sunset": True,
                                  "dawn": True, "dusk": True}},
    },
    "modern-circular-gauge": {
        "card_type": "custom:modern-circular-gauge",
        "resource": "https://github.com/selvalt7/modern-circular-gauge",
        "summary": "Modern circular gauge (replaces deprecated round gauges).",
        "example": {"type": "custom:modern-circular-gauge",
                      "entity": "sensor.cpu_temp",
                      "min": 0, "max": 100,
                      "segments": [{"from": 0, "color": "#43A047"},
                                    {"from": 60, "color": "#FFB300"},
                                    {"from": 80, "color": "#E53935"}]},
    },
    "room-summary": {
        "card_type": "custom:room-summary-card",
        "resource": "https://github.com/homeassistant-extras/room-summary-card",
        "summary": "Room-overview tile with area + auto-discovered entities.",
        "example": {"type": "custom:room-summary-card",
                      "area": "kitchen"},
    },
    "simple-swipe": {
        "card_type": "custom:simple-swipe-card",
        "resource": "https://github.com/nutteloost/simple-swipe-card",
        "summary": "Swipeable carousel of cards (paged or free).",
        "example": {"type": "custom:simple-swipe-card",
                      "cards": [{"type": "tile", "entity": "light.kitchen"},
                                  {"type": "tile", "entity": "light.hall"}],
                      "swipe_direction": "horizontal"},
    },
    "stack-in-card": {
        "card_type": "custom:stack-in-card",
        "resource": "https://github.com/custom-cards/stack-in-card",
        "summary": "Vertical/horizontal stack with shared card chrome.",
        "example": {"type": "custom:stack-in-card", "mode": "vertical",
                      "cards": [{"type": "tile", "entity": "light.kitchen"}]},
    },
    "swiss-army-knife": {
        "card_type": "custom:swiss-army-knife-card",
        "resource": "https://github.com/AmoebeLabs/swiss-army-knife-card",
        "summary": "Programmable SVG card. REQUIRES yaml-mode dashboard for sak_sys_templates — not usable on storage-mode dashboards.",
        "example": {"type": "custom:swiss-army-knife-card",
                      "entities": [{"entity": "sensor.cpu_temp"}],
                      "layout": {"toolsets": [
                          {"toolset": "main", "position": {"cx": 50, "cy": 50},
                            "tools": [
                                {"type": "circle", "position": {"cx": 50, "cy": 50, "radius": 45}},
                                {"type": "state", "position": {"cx": 50, "cy": 50, "entity_index": 0}},
                            ]},
                      ]}},
    },
    "weather-chart": {
        "card_type": "custom:weather-chart-card",
        "resource": "https://github.com/mlamberts78/weather-chart-card",
        "summary": "Weather card with forecast chart + current conditions.",
        "example": {"type": "custom:weather-chart-card",
                      "entity": "weather.home",
                      "show_main": True, "show_temperature": True,
                      "forecast": {"type": "daily", "chart_height": 180}},
    },
    "simple-weather": {
        "card_type": "custom:simple-weather-card",
        "resource": "https://github.com/kalkih/simple-weather-card",
        "summary": "Minimal weather chip. `primary_info`/`secondary_info` are enums.",
        "example": {"type": "custom:simple-weather-card",
                      "entity": "weather.home",
                      "primary_info": "temperature",
                      "secondary_info": "humidity"},
    },
    "atomic-calendar": {
        "card_type": "custom:atomic-calendar-revive",
        "resource": "https://github.com/totaldebug/atomic-calendar-revive",
        "summary": "Multi-calendar agenda. `entities` are dicts (not bare strings); use `defaultMode` not `mode`.",
        "example": {"type": "custom:atomic-calendar-revive",
                      "entities": [{"entity": "calendar.personal",
                                     "name": "Personal", "color": "#FF7A00"}],
                      "defaultMode": "Event",
                      "maxDaysToShow": 14},
    },
    "digital-clock": {
        "card_type": "custom:digital-clock",
        "resource": "https://github.com/wassy92x/lovelace-digital-clock",
        "summary": "Digital clock card. No `border` field.",
        "example": {"type": "custom:digital-clock",
                      "time_format": {"hour": "2-digit", "minute": "2-digit"},
                      "date_format": {"weekday": "long",
                                       "day": "numeric",
                                       "month": "long"}},
    },
    "flex-table": {
        "card_type": "custom:flex-table-card",
        "resource": "https://github.com/custom-cards/flex-table-card",
        "summary": "Tabular view. `entities.include` are regex STRINGS (not auto-entities-style dicts).",
        "example": {"type": "custom:flex-table-card",
                      "entities": {"include": "sensor.*temp"},
                      "columns": [
                          {"name": "Entity", "data": "entity_id"},
                          {"name": "State", "data": "state"},
                      ]},
    },
}


# SAK sub-tools are NOT standalone cards — they are tools inside a SAK card's
# `tools` list. Keep separate metadata so the SKILL generator can show them
# under a sub-section.
SAK_TOOL_META: dict[str, dict] = {
    "sak_circle":    {"summary": "SVG circle.",
                       "example": {"type": "circle", "position": {"cx": 50, "cy": 50, "radius": 45}}},
    "sak_ellipse":   {"summary": "SVG ellipse.",
                       "example": {"type": "ellipse", "position": {"cx": 50, "cy": 50, "rx": 40, "ry": 25}}},
    "sak_line":      {"summary": "SVG straight line.",
                       "example": {"type": "line", "position": {"x1": 0, "y1": 50, "x2": 100, "y2": 50}}},
    "sak_rectangle": {"summary": "SVG rectangle.",
                       "example": {"type": "rectangle", "position": {"cx": 50, "cy": 50, "width": 80, "height": 30}}},
    "sak_text":      {"summary": "SVG text label.",
                       "example": {"type": "text", "text": "ON", "position": {"cx": 50, "cy": 50}}},
    "sak_icon":      {"summary": "Icon for one of the card's entities.",
                       "example": {"type": "icon", "position": {"cx": 50, "cy": 30, "entity_index": 0}}},
    "sak_state":     {"summary": "Live state text for an entity.",
                       "example": {"type": "state", "position": {"cx": 50, "cy": 60, "entity_index": 0}}},
    "sak_name":      {"summary": "Friendly name text for an entity.",
                       "example": {"type": "name", "position": {"cx": 50, "cy": 80, "entity_index": 0}}},
    "sak_segarc":    {"summary": "Segmented arc gauge.",
                       "example": {"type": "segarc", "position": {"cx": 50, "cy": 50, "radius": 45, "start_angle": 130, "end_angle": 410}}},
    "sak_horseshoe": {"summary": "Horseshoe gauge.",
                       "example": {"type": "horseshoe", "position": {"cx": 50, "cy": 50, "radius": 45}}},
    "sak_sparkline": {"summary": "Mini sparkline graph.",
                       "example": {"type": "sparkline", "position": {"cx": 50, "cy": 50, "width": 80, "height": 30}, "hours": 24}},
    "sak_slider":    {"summary": "Interactive slider.",
                       "example": {"type": "slider", "position": {"cx": 50, "cy": 50, "length": 80}}},
    "sak_switch":    {"summary": "Toggle switch shape.",
                       "example": {"type": "switch", "position": {"cx": 50, "cy": 50}}},
    "sak_usersvg":   {"summary": "Inline user-supplied SVG.",
                       "example": {"type": "usersvg", "position": {"cx": 50, "cy": 50, "width": 50, "height": 50}, "svg": "<svg>...</svg>"}},
    "sak_circslider":{"summary": "Circular slider.",
                       "example": {"type": "circslider", "position": {"cx": 50, "cy": 50, "radius": 40}}},
    "sak_progpath":  {"summary": "Progress-along-path tool.",
                       "example": {"type": "progpath", "position": {"cx": 50, "cy": 50, "width": 80, "height": 30}, "path": "M0,0 L100,100"}},
    "sak_regpoly":   {"summary": "Regular polygon (hex, octagon, etc.).",
                       "example": {"type": "regpoly", "position": {"cx": 50, "cy": 50, "radius": 40, "sides": 6}}},
    "sak_rectex":    {"summary": "Extended rectangle with rounded corners.",
                       "example": {"type": "rectex", "position": {"cx": 50, "cy": 50, "width": 80, "height": 30, "rx": 5, "ry": 5}}},
    "sak_area":      {"summary": "Area chart filled below sparkline.",
                       "example": {"type": "area", "position": {"cx": 50, "cy": 50, "width": 80, "height": 30, "entity_index": 0}, "hours": 24}},
    "sak_toolset":   {"summary": "Toolset container — groups tools at a position.",
                       "example": {"toolset": "main", "position": {"cx": 50, "cy": 50}, "tools": []}},
}


def builder_info(name: str) -> dict:
    """Return metadata + example for a builder. Useful for agents that
    want to know the schema and a working example without parsing source.

    Returns ``{"name", "card_type", "resource", "summary", "example",
                "signature"}``.
    """
    if name not in BUILDERS:
        raise ValueError(f"unknown builder {name!r}; known: {', '.join(list_builders())}")
    meta = BUILDER_META.get(name, {})
    import inspect
    sig = inspect.signature(BUILDERS[name])
    return {
        "name": name,
        "card_type": meta.get("card_type"),
        "resource": meta.get("resource"),
        "summary": meta.get("summary", ""),
        "example": meta.get("example"),
        "signature": str(sig),
    }


def all_builder_info() -> list[dict]:
    """Return ``builder_info`` for every registered builder, in stable order."""
    return [builder_info(n) for n in list_builders()]


def _yaml_block(obj, indent: int = 0) -> str:
    """Tiny YAML emitter sufficient for compact card examples.
    Avoids the PyYAML dependency."""
    pad = "  " * indent
    if isinstance(obj, dict):
        out = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)) and v:
                out.append(f"{pad}{k}:")
                out.append(_yaml_block(v, indent + 1))
            else:
                out.append(f"{pad}{k}: {_yaml_scalar(v)}")
        return "\n".join(out)
    if isinstance(obj, list):
        out = []
        for item in obj:
            if isinstance(item, dict):
                first = True
                for k, v in item.items():
                    prefix = f"{pad}- " if first else f"{pad}  "
                    if isinstance(v, (dict, list)) and v:
                        out.append(f"{prefix}{k}:")
                        out.append(_yaml_block(v, indent + 2))
                    else:
                        out.append(f"{prefix}{k}: {_yaml_scalar(v)}")
                    first = False
            else:
                out.append(f"{pad}- {_yaml_scalar(item)}")
        return "\n".join(out)
    return f"{pad}{_yaml_scalar(obj)}"


def _yaml_scalar(v) -> str:
    if v is None: return "null"
    if v is True: return "true"
    if v is False: return "false"
    if isinstance(v, (int, float)): return str(v)
    s = str(v)
    if any(ch in s for ch in ":#[]{}|>*&!%@`,'\"") or s != s.strip():
        return '"' + s.replace('"', '\\"') + '"'
    return s


def generate_cards_reference() -> str:
    """Build the Markdown 'Cards Reference' section for SKILL.md.

    Groups builders into Native vs HACS, alphabetises within each group,
    and emits each builder as a heading + signature + summary + YAML example.
    """
    native = [n for n in list_builders()
                if BUILDER_META.get(n, {}).get("resource") is None]
    custom = [n for n in list_builders()
                if BUILDER_META.get(n, {}).get("resource") is not None]

    lines = ["## Cards Reference",
              "",
              "Card builders live in `cli_anything.homeassistant.core."
              "lovelace_card_builders`. Each builder validates its arguments "
              "and returns a card dict ready to drop into a Lovelace view. "
              "Common pitfalls (which fields are enums, where `card_mod` is "
              "valid, what HACS plugin a card needs) are encoded in the "
              "builders and surfaced below.",
              "",
              "```python",
              "from cli_anything.homeassistant.core import lovelace_card_builders as cb",
              "from cli_anything.homeassistant.core import lovelace as ll",
              "from cli_anything.homeassistant.core import project as proj",
              "from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantClient",
              "",
              "client = HomeAssistantClient(**proj.load_config())",
              "dash = ll.get_dashboard_config(client, 'jon-mobile')",
              "view = dash['views'][0]",
              "view['cards'].append(cb.tile('light.kitchen', name='Kitchen'))",
              "ll.save_dashboard_config(client, 'jon-mobile', dash)",
              "```",
              ""]

    def emit_section(title, names):
        lines.append(f"### {title}")
        lines.append("")
        for name in names:
            meta = BUILDER_META[name]
            info = builder_info(name)
            resource = meta.get("resource")
            res_md = f" — [{resource.split('/')[-1]}]({resource})" if resource else ""
            lines.append(f"**`{name}`** → `{meta['card_type']}`{res_md}  ")
            lines.append(f"{meta['summary']}  ")
            lines.append(f"Signature: `{name}{info['signature']}`")
            lines.append("")
            lines.append("```yaml")
            lines.append(_yaml_block(meta["example"]))
            lines.append("```")
            lines.append("")

    emit_section("Native cards (no HACS plugin required)", native)
    emit_section("HACS custom cards (install via HACS Frontend first)", custom)

    # SAK tools — listed separately because they're sub-tools of swiss-army-knife
    lines.append("### Swiss Army Knife tools")
    lines.append("")
    lines.append("These are not standalone cards — they are tools you nest "
                  "inside a `swiss-army-knife` card's `tools` list. Builder "
                  "helpers (e.g. `cb.sak_circle(cx=50, cy=50, radius=45)`) "
                  "live in the same module.")
    lines.append("")
    for tool_name in sorted(SAK_TOOL_META):
        meta = SAK_TOOL_META[tool_name]
        lines.append(f"- **`{tool_name}`** — {meta['summary']}")
        lines.append(f"  `{meta['example']}`")
    lines.append("")
    return "\n".join(lines)
