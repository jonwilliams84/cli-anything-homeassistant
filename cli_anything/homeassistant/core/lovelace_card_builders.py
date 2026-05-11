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
                      mode: str = "Event",
                      max_days_to_show: int = 7,
                      show_location: bool | None = None,
                      show_no_event_days: bool | None = None) -> dict:
    """`custom:atomic-calendar-revive`. Entries may be bare entity_ids
    (auto-wrapped) or full dicts with `entity`, `name`, `color`."""
    if not entities:
        raise ValueError("at least one calendar entity required")
    # Atomic-calendar-revive expects [{"entity": ..., ...}] — normalize bare strings
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
        "mode": mode,
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

def flex_table(*, entities: dict, columns: list[dict],
                 sort_by: str | None = None,
                 strict: bool | None = None) -> dict:
    """`custom:flex-table-card`. `entities` is a filter spec like
    `{include: [...]}` or `{entities: [...]}`."""
    if not columns:
        raise ValueError("at least one column required")
    card: dict[str, Any] = {
        "type": "custom:flex-table-card",
        "entities": entities,
        "columns": columns,
    }
    if sort_by is not None: card["sort_by"] = sort_by
    if strict is not None: card["strict"] = strict
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
    "decluttering": decluttering,
    "stack-in-card": stack_in_card,
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
