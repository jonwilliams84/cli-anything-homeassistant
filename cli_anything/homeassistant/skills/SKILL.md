---
name: cli-anything-homeassistant
description: >-
  Control a running Home Assistant instance from the command line. Wraps the
  full HA REST API and the WebSocket registry endpoints (areas, devices,
  entities, system_health) behind a stateful CLI + REPL with --json output for
  agents. Use this when an AI agent needs to read entity states, call services,
  render Jinja templates, fire events, or inspect a smart home without the
  browser UI.
---

# cli-anything-homeassistant

CLI harness for [Home Assistant](https://www.home-assistant.io/). It is a
**thin client** over Home Assistant's REST API (`/api/...`) and WebSocket API
(`/api/websocket`). The CLI never reimplements Home Assistant logic — every
command resolves to one or more API calls handled by the running HA server.

## Installation

```bash
pip install cli-anything-homeassistant
```

### Prerequisites

- Python 3.10+
- A running Home Assistant instance (the CLI is useless without it)
- A long-lived access token

Install Home Assistant via pip or Docker:

```bash
# Pip (in a virtualenv)
pip install homeassistant
hass --config /path/to/config

# Docker
docker run -d --name hass -p 8123:8123 \
  -v /PATH_TO_YOUR_CONFIG:/config \
  ghcr.io/home-assistant/home-assistant:stable
```

Open `http://localhost:8123`, complete onboarding, then create a Long-Lived
Access Token (user profile → Long-Lived Access Tokens).

### Configure

```bash
cli-anything-homeassistant config set \
  --url http://localhost:8123 \
  --token <token>
cli-anything-homeassistant config test
```

The profile is saved to `~/.config/cli-anything-homeassistant.json` (mode
`0600`). Environment overrides: `HASS_URL`, `HASS_TOKEN`, `HASS_VERIFY_SSL`,
`HASS_TIMEOUT`.

## Agent Quick Start

Always pass `--json` when scripting; output is single-document JSON.

```bash
# Auth check
cli-anything-homeassistant --json system info

# Inventory the install
cli-anything-homeassistant --json state counts
cli-anything-homeassistant --json system components
cli-anything-homeassistant --json area list
cli-anything-homeassistant --json entity list --domain sensor

# Read an entity
cli-anything-homeassistant --json state get sensor.outdoor_temperature

# Drive a device
cli-anything-homeassistant service call light turn_on \
    --target entity_id=light.kitchen --data brightness=200

# Render a template
cli-anything-homeassistant template '{{ states("sensor.outdoor_temperature") | float }}'

# Preview a service call without invoking it
cli-anything-homeassistant --json service call light turn_on \
    --target entity_id=light.foo --dry-run
```

## Command Groups

### `config` — Connection profile

| Command           | Description                                            |
|-------------------|--------------------------------------------------------|
| `config show`     | Show the active profile (token redacted)               |
| `config set`      | Set URL/token/verify-ssl/timeout and persist           |
| `config save`     | Save the current in-memory profile to disk             |
| `config test`     | Verify the profile reaches HA                          |

### `system` — Server introspection

| Command             | REST endpoint        | Description                          |
|---------------------|----------------------|--------------------------------------|
| `system info`       | `/api/`              | Auth check + status banner           |
| `system config`     | `/api/config`        | Server config (version, location)    |
| `system core-state` | `/api/core/state`    | Core state (RUNNING/STARTING/...)    |
| `system error-log`  | `/api/error_log`     | Error log (`-n` to tail)             |
| `system components` | `/api/components`    | Loaded components                    |
| `system health`     | `system_health/info` | System-health info (WebSocket)       |

### `state` — Entity states

| Command                      | Description                                    |
|------------------------------|------------------------------------------------|
| `state list [--domain X]`    | All states or just the chosen domain           |
| `state list --ids-only`      | Only entity IDs                                |
| `state get <entity_id>`      | Single entity state                            |
| `state set <id> <state>`     | Create/update state, with `-a key=value`        |
| `state domains`              | Unique domains across loaded entities          |
| `state counts`               | `{domain: count}` map                          |

### `service` — Services

| Command                                  | Description                          |
|------------------------------------------|--------------------------------------|
| `service list [--domain X]`              | Service registry                     |
| `service domains`                        | Unique service domains               |
| `service call <domain> <service>`        | Call a service                       |
| ` ↳ -D key=value`                        | Service data (JSON values supported) |
| ` ↳ -T key=value`                        | Target (entity_id/area_id/device_id) |
| ` ↳ --return-response`                   | Use HA 2024.8+ return-response mode  |
| ` ↳ --dry-run`                           | Print the payload without sending    |

### `event` — Event bus

| Command                              | Description                              |
|--------------------------------------|------------------------------------------|
| `event list`                         | Listener counts                          |
| `event fire <type> [-D ...]`         | Fire an event, optional `--dry-run`      |
| `event subscribe [<type>] --limit N` | Stream events via WS until N received    |

### `template` — Jinja2 rendering

```
cli-anything-homeassistant template '<jinja>' [-V key=value ...]
cli-anything-homeassistant template --file path/to/tpl.j2
echo '{{ now() }}' | cli-anything-homeassistant template
```

For multi-line / Jinja-heavy templates, prefer `--file` or stdin (avoids shell
quoting issues that mangle braces and pipes).

### `area` / `device` / `entity` — Registries (WebSocket)

| Command                          | Description                                |
|----------------------------------|--------------------------------------------|
| `area list`                      | Areas                                      |
| `device list [--area <id>]`      | Devices, optional area filter              |
| `entity list [--domain <name>]`  | Entity registry (different from `state`)   |

### `automation`

| Command                                    | Description                |
|--------------------------------------------|----------------------------|
| `automation list`                          | All automation entities    |
| `automation trigger <id> [--skip-condition]` | Force a manual trigger     |
| `automation toggle <id>`                   | Toggle on/off              |
| `automation turn-on <id>` / `turn-off <id>`| Explicit enable / disable  |
| `automation reload`                        | Reload automations         |

### `script`

| Command                          | Description                          |
|----------------------------------|--------------------------------------|
| `script list`                    | All script entities                  |
| `script run <id> [-V key=value]` | Run a script with optional variables |
| `script reload`                  | Reload scripts                       |

### `domain` — Per-domain shortcuts

For controllable domains: `light`, `switch`, `fan`, `cover`, `media_player`,
`input_boolean`, `scene`, `climate`, `vacuum`, `humidifier`, `siren`,
`remote`, `water_heater`, `automation`, `script`.

| Command                                      | Description           |
|----------------------------------------------|-----------------------|
| `domain list <domain>`                       | Entities for a domain |
| `domain turn-on <domain> [<entity_id>]`      | turn_on (`--dry-run`) |
| `domain turn-off <domain> [<entity_id>]`     | turn_off              |
| `domain toggle <domain> [<entity_id>]`       | toggle                |

### `history` / `logbook`

```
cli-anything-homeassistant history --hours 24 -e sensor.x -e sensor.y
cli-anything-homeassistant logbook --hours 1
```

### `config-entry` — Integration instances

| Command                                         | Description                              |
|-------------------------------------------------|------------------------------------------|
| `config-entry list [--domain X]`                | List all entries / filter by integration |
| `config-entry get <entry_id>`                   | Single entry by ID                       |
| `config-entry reload <entry_id>`                | Reload without restarting HA (REST)      |
| `config-entry delete <entry_id> [--yes]`        | Remove an integration instance           |
| `config-entry options-init <entry_id>`          | Start an options flow → returns flow_id  |
| `config-entry options-configure <flow_id>`      | Submit user_input for an active flow     |
| `config-entry options-set <entry_id>`           | Init + configure in one call (preferred) |
| `config-entry update <entry_id> [--title …]`    | Patch entry.title or entry.data directly |

**`options-set` is how to edit UI-created template helpers without restarting
HA.** Editing `.storage/core.config_entries` directly does NOT take effect at
runtime — HA caches options in memory. Always go through the options flow.

```bash
# Update a template helper's `state:` template via options flow
cat > /tmp/opts.json <<'JSON'
{"state": "{{ states('sensor.foo') | float }}", "state_class": "measurement"}
JSON
cli-anything-homeassistant config-entry options-set 01HXY... --data-file /tmp/opts.json
```

### `helpers` — input_select / input_number etc.

| Command                                                              | Description                          |
|---------------------------------------------------------------------|--------------------------------------|
| `helpers input-select set-options <eid> <opt> <opt> …`              | Replace the options list             |
| `helpers input-select set-options <eid> --from-file opts.json`      | Read JSON list from file             |
| `helpers input-select sync <src_eid> <dst_eid> [--fallback Auto]`   | Copy options src → dst (state stays) |

`set-options` calls the runtime service. To make the change survive a HA
restart you may also need to edit `.storage/input_select` on the host —
HA's input_select integration doesn't always flush set_options to disk
(sigh). The `sync` subcommand is idempotent and safe to call from
automations / mirror jobs.

### `lovelace-tools` — Backup & diff

| Command                                                  | Description                          |
|----------------------------------------------------------|--------------------------------------|
| `lovelace-tools backup --out-dir <dir>`                  | Snapshot every dashboard as JSON     |
| `lovelace-tools backup -d <dir> -u jon-mobile -u …`      | Just specific url_paths              |
| `lovelace-tools diff <a.json> <b.json>`                  | Summary diff (views added/removed/changed) |
| `lovelace-tools diff <a.json> <b.json> --full`           | Unified text diff of canonicalised JSON   |

Useful before any large dashboard rewrite — `backup --out-dir` first, then
`diff` after you save to verify what actually changed.

## Output for Agents

- Pass `--json`. Output is a single JSON document.
- Errors print to stderr and exit non-zero.
- All mutating commands accept `--dry-run` (where it makes sense) — the dry
  run never contacts the HA server.

### Example: read a sensor and act on it

```bash
TEMP=$(cli-anything-homeassistant --json state get sensor.outdoor_temperature \
        | jq -r '.state | tonumber')
if (( $(echo "$TEMP < 5" | bc -l) )); then
    cli-anything-homeassistant service call light turn_on \
        --target entity_id=light.outdoor --data brightness=255
fi
```

### Example: discover the install

```bash
cli-anything-homeassistant --json system config | jq '.version,.location_name'
cli-anything-homeassistant --json state counts        # entity counts by domain
cli-anything-homeassistant --json area list           # all rooms
cli-anything-homeassistant --json entity list --domain light
cli-anything-homeassistant --json service domains     # available services
```

## Cards Reference

Card builders live in `cli_anything.homeassistant.core.lovelace_card_builders`. Each builder validates its arguments and returns a card dict ready to drop into a Lovelace view. Common pitfalls (which fields are enums, where `card_mod` is valid, what HACS plugin a card needs) are encoded in the builders and surfaced below.

```python
from cli_anything.homeassistant.core import lovelace_card_builders as cb
from cli_anything.homeassistant.core import lovelace as ll
from cli_anything.homeassistant.core import project as proj
from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantClient

client = HomeAssistantClient(**proj.load_config())
dash = ll.get_dashboard_config(client, 'jon-mobile')
view = dash['views'][0]
view['cards'].append(cb.tile('light.kitchen', name='Kitchen'))
ll.save_dashboard_config(client, 'jon-mobile', dash)
```

### Native cards (no HACS plugin required)

**`button`** → `button`  
Tap-action button. Prefer `tile` for entity control.  
Signature: `button(entity: 'str', *, name: 'str | None' = None, icon: 'str | None' = None, show_state: 'bool | None' = None, tap_action: 'dict | None' = None, hold_action: 'dict | None' = None, theme: 'str | None' = None) -> 'dict'`

```yaml
type: button
entity: light.kitchen
name: Kitchen
show_state: true
```

**`conditional`** → `conditional`  
Show the inner `card` only when conditions match.  
Signature: `conditional(card: 'dict', conditions: 'list[dict]') -> 'dict'`

```yaml
type: conditional
conditions:
  - entity: binary_sensor.guest_mode
    state: on
card:
  type: tile
  entity: light.guest_room
```

**`entities`** → `entities`  
Classic list of entity rows with toggles/state.  
Signature: `entities(entities: 'list[str | dict]', *, title: 'str | None' = None, show_header_toggle: 'bool | None' = None, state_color: 'bool | None' = None, theme: 'str | None' = None) -> 'dict'`

```yaml
type: entities
title: Lights
entities:
  - light.kitchen
  - light.hall
```

**`gauge`** → `gauge`  
Numeric gauge with severity thresholds.  
Signature: `gauge(entity: 'str', *, name: 'str | None' = None, min: 'float | None' = None, max: 'float | None' = None, unit: 'str | None' = None, severity: 'dict | None' = None, needle: 'bool' = False) -> 'dict'`

```yaml
type: gauge
entity: sensor.cpu_temp
min: 0
max: 100
severity:
  green: 0
  yellow: 60
  red: 80
```

**`glance`** → `glance`  
Compact horizontal row of entities with state.  
Signature: `glance(entities: 'list[str | dict]', *, title: 'str | None' = None, columns: 'int | None' = None, show_state: 'bool | None' = None, show_icon: 'bool | None' = None, show_name: 'bool | None' = None) -> 'dict'`

```yaml
type: glance
title: Status
entities:
  - sensor.outdoor_temp
  - sensor.indoor_temp
```

**`grid`** → `grid`  
Grid of cards with `columns` and optional `square`.  
Signature: `grid(cards: 'list[dict]', *, columns: 'int' = 2, square: 'bool' = False, title: 'str | None' = None) -> 'dict'`

```yaml
type: grid
columns: 2
square: false
cards:
  - type: tile
    entity: light.kitchen
  - type: tile
    entity: light.hall
```

**`history-graph`** → `history-graph`  
Line graph of recent state history.  
Signature: `history-graph(entities: 'list[str | dict]', *, hours_to_show: 'int' = 24, title: 'str | None' = None, refresh_interval: 'int | None' = None) -> 'dict'`

```yaml
type: history-graph
hours_to_show: 24
entities:
  - sensor.outdoor_temp
```

**`horizontal-stack`** → `horizontal-stack`  
Stack child cards horizontally.  
Signature: `horizontal-stack(cards: 'list[dict]', *, title: 'str | None' = None) -> 'dict'`

```yaml
type: horizontal-stack
cards:
  - type: tile
    entity: light.kitchen
  - type: tile
    entity: light.hall
```

**`iframe`** → `iframe`  
Embed external URL. WARNING: most sites block iframing.  
Signature: `iframe(url: 'str', *, title: 'str | None' = None, aspect_ratio: 'str | None' = None) -> 'dict'`

```yaml
type: iframe
url: "https://embed.windy.com/embed.html?..."
aspect_ratio: "16:9"
```

**`markdown`** → `markdown`  
Render markdown + Jinja templates.  
Signature: `markdown(content: 'str', *, title: 'str | None' = None, theme: 'str | None' = None) -> 'dict'`

```yaml
type: markdown
title: Hello
content: "## Welcome, {{ user }}"
```

**`picture-elements`** → `picture-elements`  
Background image with absolutely-positioned elements.  
Signature: `picture-elements(image: 'str', elements: 'list[dict]', *, title: 'str | None' = None, state_filter: 'dict | None' = None) -> 'dict'`

```yaml
type: picture-elements
image: /local/floorplan.png
elements:
  - type: state-icon
    entity: light.kitchen
    style:
      top: "30%"
      left: "40%"
```

**`statistics-graph`** → `statistics-graph`  
Graph of long-term-statistics (LTS) values.  
Signature: `statistics-graph(entities: 'list[str | dict]', *, days_to_show: 'int' = 30, stat_types: 'list[str] | None' = None, title: 'str | None' = None, chart_type: 'str | None' = None) -> 'dict'`

```yaml
type: statistics-graph
days_to_show: 30
entities:
  - sensor.energy
stat_types:
  - mean
  - max
```

**`tile`** → `tile`  
Modern HA tile — primary entity surface (recommended over button).  
Signature: `tile(entity: 'str', *, name: 'str | None' = None, color: 'str | None' = None, icon: 'str | None' = None, vertical: 'bool' = False, show_entity_picture: 'bool | None' = None, tap_action: 'dict | None' = None) -> 'dict'`

```yaml
type: tile
entity: light.kitchen
name: Kitchen
icon: "mdi:silverware"
```

**`vertical-stack`** → `vertical-stack`  
Stack child cards vertically.  
Signature: `vertical-stack(cards: 'list[dict]', *, title: 'str | None' = None) -> 'dict'`

```yaml
type: vertical-stack
cards:
  - type: tile
    entity: light.kitchen
  - type: tile
    entity: light.hall
```

**`weather-forecast`** → `weather-forecast`  
Native weather forecast (daily/hourly).  
Signature: `weather-forecast(entity: 'str', *, name: 'str | None' = None, show_forecast: 'bool' = True, forecast_type: 'str' = 'daily', theme: 'str | None' = None) -> 'dict'`

```yaml
type: weather-forecast
entity: weather.home
forecast_type: daily
show_forecast: true
```

### HACS custom cards (install via HACS Frontend first)

**`apexcharts`** → `custom:apexcharts-card` — [apexcharts-card](https://github.com/RomRider/apexcharts-card)  
Time-series charts via ApexCharts.js. Powerful but strict schema — series entries take ONLY series fields (no card_mod inside).  
Signature: `apexcharts(series: 'list[dict]', *, header: 'dict | None' = None, graph_span: 'str | None' = None, chart_type: 'str | None' = None, stacked: 'bool | None' = None, apex_config: 'dict | None' = None, yaxis: 'list[dict] | None' = None, all_yaxis: 'dict | None' = None) -> 'dict'`

```yaml
type: "custom:apexcharts-card"
graph_span: 24h
header:
  show: true
  title: Grid · 24h
series:
  - entity: sensor.smart_meter_power
    name: Grid
    type: area
```

**`atomic-calendar`** → `custom:atomic-calendar-revive` — [atomic-calendar-revive](https://github.com/totaldebug/atomic-calendar-revive)  
Multi-calendar agenda. `entities` are dicts (not bare strings); use `defaultMode` not `mode`.  
Signature: `atomic-calendar(entities: 'list[str | dict]', *, name: 'str | None' = None, default_mode: 'str' = 'Event', max_days_to_show: 'int' = 7, show_location: 'bool | None' = None, show_no_event_days: 'bool | None' = None) -> 'dict'`

```yaml
type: "custom:atomic-calendar-revive"
entities:
  - entity: calendar.personal
    name: Personal
    color: "#FF7A00"
defaultMode: Event
maxDaysToShow: 14
```

**`auto-entities`** → `custom:auto-entities` — [lovelace-auto-entities](https://github.com/thomasloven/lovelace-auto-entities)  
Dynamically-populated wrapper card. `filter` selects entities (include patterns are dicts, not bare strings).  
Signature: `auto-entities(*, filter: 'dict', card: 'dict | None' = None, sort: 'dict | None' = None, show_empty: 'bool' = True, unique: 'bool' = False) -> 'dict'`

```yaml
type: "custom:auto-entities"
filter:
  include:
    - domain: light
card:
  type: entities
  title: All lights
```

**`bubble`** → `custom:bubble-card` — [Bubble-Card](https://github.com/Clooos/Bubble-Card)  
Bubble UI cards (popup, button, separator, slider, etc).  
Signature: `bubble(*, card_type: 'str' = 'button', entity: 'str | None' = None, name: 'str | None' = None, icon: 'str | None' = None, sub_button: 'list[dict] | None' = None, styles: 'str | None' = None, tap_action: 'dict | None' = None, button_type: 'str' = 'switch') -> 'dict'`

```yaml
type: "custom:bubble-card"
card_type: button
button_type: switch
entity: light.kitchen
name: Kitchen
```

**`button-card`** → `custom:button-card` — [button-card](https://github.com/custom-cards/button-card)  
Highly-customisable button with templates and state-driven styling.  
Signature: `button-card(*, entity: 'str | None' = None, template: 'str | list[str] | None' = None, name: 'str | None' = None, label: 'str | None' = None, icon: 'str | None' = None, color: 'str | None' = None, color_type: 'str | None' = None, show_state: 'bool | None' = None, state: 'list[dict] | None' = None, styles: 'dict | None' = None, tap_action: 'dict | None' = None, hold_action: 'dict | None' = None, variables: 'dict | None' = None) -> 'dict'`

```yaml
type: "custom:button-card"
entity: light.kitchen
name: Kitchen
show_state: true
color_type: card
```

**`calendar-card-pro`** → `custom:calendar-card-pro` — [calendar-card-pro](https://github.com/alexpfau/calendar-card-pro)  
Calendar agenda view (compact, multi-day, color-coded).  
Signature: `calendar-card-pro(entities: 'list[str | dict]', *, days_to_show: 'int' = 3, show_location: 'bool | None' = None, title: 'str | None' = None, max_events: 'int | None' = None, compact_mode: 'bool | None' = None, time_format: 'str | None' = None) -> 'dict'`

```yaml
type: "custom:calendar-card-pro"
entities:
  - entity: calendar.personal
    color: "#FF7A00"
days_to_show: 7
```

**`decluttering`** → `custom:decluttering-card` — [decluttering-card](https://github.com/custom-cards/decluttering-card)  
Reusable card template (DRY common card configs).  
Signature: `decluttering(template: 'str', *, variables: 'list[dict] | None' = None) -> 'dict'`

```yaml
type: "custom:decluttering-card"
template: room_tile
variables:
  - entity: light.kitchen
```

**`digital-clock`** → `custom:digital-clock` — [lovelace-digital-clock](https://github.com/wassy92x/lovelace-digital-clock)  
Digital clock card. No `border` field.  
Signature: `digital-clock(*, time_format: 'dict | None' = None, date_format: 'dict | None' = None, locale: 'str | None' = None, time_zone: 'str | None' = None) -> 'dict'`

```yaml
type: "custom:digital-clock"
time_format:
  hour: 2-digit
  minute: 2-digit
date_format:
  weekday: long
  day: numeric
  month: long
```

**`expander`** → `custom:expander-card` — [lovelace-expander-card](https://github.com/Alia5/lovelace-expander-card)  
Collapsible card wrapper.  
Signature: `expander(cards: 'list[dict]', *, title: 'str | None' = None, icon: 'str' = 'mdi:chevron-down', expanded: 'bool' = False, animation: 'bool' = True, haptic: 'str' = 'light', clear: 'bool' = False, clear_children: 'bool' = False, gap: 'str | None' = None, padding: 'str | None' = None, title_card: 'dict | None' = None, title_card_clickable: 'bool' = False, storage_id: 'str | None' = None, expander_card_id: 'str | None' = None) -> 'dict'`

```yaml
type: "custom:expander-card"
title: Details
expanded: false
cards:
  - type: tile
    entity: light.kitchen
```

**`flex-table`** → `custom:flex-table-card` — [flex-table-card](https://github.com/custom-cards/flex-table-card)  
Tabular view. `entities.include` are regex STRINGS (not auto-entities-style dicts).  
Signature: `flex-table(*, entities, columns: 'list[dict]', sort_by: 'str | None' = None, strict: 'bool | None' = None) -> 'dict'`

```yaml
type: "custom:flex-table-card"
entities:
  include: "sensor.*temp"
columns:
  - name: Entity
    data: entity_id
  - name: State
    data: state
```

**`horizon`** → `custom:horizon-card` — [lovelace-horizon-card](https://github.com/rejuvenate/lovelace-horizon-card)  
Sun arc + dawn/dusk panel.  
Signature: `horizon(*, title: 'str | None' = None, moon: 'bool' = True, refresh_period: 'int | None' = None, southern_flip: 'bool' = False, fields: 'dict[str, bool] | None' = None, language: 'str | None' = None, time_format: 'str | None' = None, no_card: 'bool' = False) -> 'dict'`

```yaml
type: "custom:horizon-card"
title: Sun
fields:
  sunrise: true
  sunset: true
  dawn: true
  dusk: true
```

**`layout-card`** → `custom:layout-card` — [lovelace-layout-card](https://github.com/thomasloven/lovelace-layout-card)  
Custom layouts (grid/horizontal/vertical/masonry) with per-card sizing.  
Signature: `layout-card(cards: 'list[dict]', *, layout_type: 'str' = 'grid', layout: 'dict | None' = None) -> 'dict'`

```yaml
type: "custom:layout-card"
layout_type: grid
cards:
  - type: tile
    entity: light.kitchen
```

**`mini-graph`** → `custom:mini-graph-card` — [mini-graph-card](https://github.com/kalkih/mini-graph-card)  
Compact sparkline graph for one or more sensors.  
Signature: `mini-graph(entities: 'list[str | dict]', *, hours_to_show: 'int' = 24, points_per_hour: 'float | None' = None, line_width: 'int | None' = None, line_color: 'str | None' = None, name: 'str | None' = None, show: 'dict | None' = None, color_thresholds: 'list[dict] | None' = None, smoothing: 'bool | None' = None) -> 'dict'`

```yaml
type: "custom:mini-graph-card"
entities:
  - entity: sensor.outdoor_temp
    name: Outdoor
hours_to_show: 24
line_width: 3
show:
  name: true
  state: true
  legend: false
```

**`mini-media-player`** → `custom:mini-media-player` — [mini-media-player](https://github.com/kalkih/mini-media-player)  
Compact media player with artwork, controls, shortcuts.  
Signature: `mini-media-player(entity: 'str', *, name: 'str | None' = None, artwork: 'str | None' = None, background: 'str | None' = None, icon: 'str | None' = None, hide: 'dict | None' = None, shortcuts: 'dict | None' = None, info: 'str | None' = None, group: 'bool' = False) -> 'dict'`

```yaml
type: "custom:mini-media-player"
entity: media_player.spotify
artwork: cover
hide:
  power: false
```

**`modern-circular-gauge`** → `custom:modern-circular-gauge` — [modern-circular-gauge](https://github.com/selvalt7/modern-circular-gauge)  
Modern circular gauge (replaces deprecated round gauges).  
Signature: `modern-circular-gauge(entity: 'str', *, min: 'float | str' = 0, max: 'float | str' = 100, gauge_type: 'str' = 'standard', attribute: 'str | None' = None, unit: 'str | None' = None, decimals: 'int | None' = None, name: 'str | None' = None, icon: 'str | None' = None, label: 'str | None' = None, needle: 'bool | None' = None, show_graph: 'bool | None' = None, adaptive_icon_color: 'bool | None' = None, secondary: 'dict | None' = None, tertiary: 'dict | None' = None, segments: 'list[dict] | None' = None) -> 'dict'`

```yaml
type: "custom:modern-circular-gauge"
entity: sensor.cpu_temp
min: 0
max: 100
segments:
  - from: 0
    color: "#43A047"
  - from: 60
    color: "#FFB300"
  - from: 80
    color: "#E53935"
```

**`mushroom-chips`** → `custom:mushroom-chips-card` — [lovelace-mushroom](https://github.com/piitaya/lovelace-mushroom)  
Horizontal row of small chips (status indicators).  
Signature: `mushroom-chips(chips: 'list[dict]') -> 'dict'`

```yaml
type: "custom:mushroom-chips-card"
chips:
  - type: weather
    entity: weather.home
  - type: entity
    entity: sensor.outdoor_temp
```

**`mushroom-climate`** → `custom:mushroom-climate-card` — [lovelace-mushroom](https://github.com/piitaya/lovelace-mushroom)  
Climate entity tile with HVAC mode buttons.  
Signature: `mushroom-climate(entity: 'str', *, name: 'str | None' = None, icon: 'str | None' = None, show_temperature_control: 'bool' = False, hvac_modes: 'list[str] | None' = None, collapsible_controls: 'bool' = False) -> 'dict'`

```yaml
type: "custom:mushroom-climate-card"
entity: climate.living_room
hvac_modes:
  - off
  - heat
  - cool
show_temperature_control: true
```

**`mushroom-light`** → `custom:mushroom-light-card` — [lovelace-mushroom](https://github.com/piitaya/lovelace-mushroom)  
Light entity with mushroom styling + brightness/color controls.  
Signature: `mushroom-light(entity: 'str', *, name: 'str | None' = None, icon: 'str | None' = None, show_brightness_control: 'bool' = False, show_color_control: 'bool' = False, show_color_temp_control: 'bool' = False, use_light_color: 'bool' = True, collapsible_controls: 'bool' = False, layout: 'str | None' = None) -> 'dict'`

```yaml
type: "custom:mushroom-light-card"
entity: light.kitchen
name: Kitchen
show_brightness_control: true
use_light_color: true
fill_container: true
```

**`mushroom-person`** → `custom:mushroom-person-card` — [lovelace-mushroom](https://github.com/piitaya/lovelace-mushroom)  
Person tracker with location and presence icon.  
Signature: `mushroom-person(entity: 'str', *, name: 'str | None' = None, icon: 'str | None' = None, layout: 'str | None' = None, hide_name: 'bool' = False, hide_state: 'bool' = False) -> 'dict'`

```yaml
type: "custom:mushroom-person-card"
entity: person.jon
name: Jon
icon_type: entity-picture
layout: horizontal
```

**`mushroom-template`** → `custom:mushroom-template-card` — [lovelace-mushroom](https://github.com/piitaya/lovelace-mushroom)  
Generic mushroom card driven by Jinja templates.  
Signature: `mushroom-template(primary: 'str', *, secondary: 'str | None' = None, icon: 'str | None' = None, icon_color: 'str | None' = None, badge_icon: 'str | None' = None, badge_color: 'str | None' = None, entity: 'str | None' = None, tap_action: 'dict | None' = None, hold_action: 'dict | None' = None, double_tap_action: 'dict | None' = None, fill_container: 'bool' = False, multiline_secondary: 'bool' = False) -> 'dict'`

```yaml
type: "custom:mushroom-template-card"
primary: "Hello {{ states('sensor.x') }}"
secondary: subtitle
icon: "mdi:home"
fill_container: true
multiline_secondary: true
```

**`mushroom-title`** → `custom:mushroom-title-card` — [lovelace-mushroom](https://github.com/piitaya/lovelace-mushroom)  
Heading text with optional subtitle.  
Signature: `mushroom-title(title: 'str | None' = None, subtitle: 'str | None' = None, alignment: 'str | None' = None) -> 'dict'`

```yaml
type: "custom:mushroom-title-card"
title: Living Room
subtitle: Always cosy
```

**`room-summary`** → `custom:room-summary-card` — [room-summary-card](https://github.com/homeassistant-extras/room-summary-card)  
Room-overview tile with area + auto-discovered entities.  
Signature: `room-summary(area: 'str', *, entity: 'str | None' = None, entities: 'list[str | dict] | None' = None, features: 'dict | None' = None, background: 'dict | None' = None, occupancy: 'dict | None' = None, thresholds: 'dict | None' = None) -> 'dict'`

```yaml
type: "custom:room-summary-card"
area: kitchen
```

**`simple-swipe`** → `custom:simple-swipe-card` — [simple-swipe-card](https://github.com/nutteloost/simple-swipe-card)  
Swipeable carousel of cards (paged or free).  
Signature: `simple-swipe(cards: 'list[dict]', *, view_mode: 'str' = 'single', show_pagination: 'bool | None' = None, card_spacing: 'int | None' = None, swipe_direction: 'str' = 'horizontal', swipe_behavior: 'str' = 'single', loop_mode: 'str' = 'none', enable_auto_swipe: 'bool' = False, auto_swipe_interval: 'int | None' = None, state_entity: 'str | None' = None) -> 'dict'`

```yaml
type: "custom:simple-swipe-card"
cards:
  - type: tile
    entity: light.kitchen
  - type: tile
    entity: light.hall
swipe_direction: horizontal
```

**`simple-weather`** → `custom:simple-weather-card` — [simple-weather-card](https://github.com/kalkih/simple-weather-card)  
Minimal weather chip. `primary_info`/`secondary_info` are enums.  
Signature: `simple-weather(entity: 'str', *, name: 'str | None' = None, primary_info: 'str | list[str] | None' = None, secondary_info: 'str | list[str] | None' = None, backdrop: 'dict | bool | None' = None) -> 'dict'`

```yaml
type: "custom:simple-weather-card"
entity: weather.home
primary_info: temperature
secondary_info: humidity
```

**`stack-in-card`** → `custom:stack-in-card` — [stack-in-card](https://github.com/custom-cards/stack-in-card)  
Vertical/horizontal stack with shared card chrome.  
Signature: `stack-in-card(cards: 'list[dict]', *, mode: 'str' = 'vertical', title: 'str | None' = None, keep: 'dict | None' = None) -> 'dict'`

```yaml
type: "custom:stack-in-card"
mode: vertical
cards:
  - type: tile
    entity: light.kitchen
```

**`swiss-army-knife`** → `custom:swiss-army-knife-card` — [swiss-army-knife-card](https://github.com/AmoebeLabs/swiss-army-knife-card)  
Programmable SVG card. REQUIRES yaml-mode dashboard for sak_sys_templates — not usable on storage-mode dashboards.  
Signature: `swiss-army-knife(*, entities: 'list[str | dict]', toolsets: 'list[dict]', aspectratio: 'str' = '1/1', layout_extra: 'dict | None' = None) -> 'dict'`

```yaml
type: "custom:swiss-army-knife-card"
entities:
  - entity: sensor.cpu_temp
layout:
  toolsets:
    - toolset: main
      position:
        cx: 50
        cy: 50
      tools:
        - type: circle
          position:
            cx: 50
            cy: 50
            radius: 45
        - type: state
          position:
            cx: 50
            cy: 50
            entity_index: 0
```

**`weather-chart`** → `custom:weather-chart-card` — [weather-chart-card](https://github.com/mlamberts78/weather-chart-card)  
Weather card with forecast chart + current conditions.  
Signature: `weather-chart(entity: 'str', *, title: 'str | None' = None, show_main: 'bool | None' = None, show_attributes: 'bool | None' = None, show_time: 'bool | None' = None, show_date: 'bool | None' = None, animated_icons: 'bool | None' = None, forecast: 'dict | None' = None, units: 'dict | None' = None, locale: 'str | None' = None, temp: 'str | None' = None, press: 'str | None' = None, humid: 'str | None' = None, uv: 'str | None' = None, winddir: 'str | None' = None, windspeed: 'str | None' = None) -> 'dict'`

```yaml
type: "custom:weather-chart-card"
entity: weather.home
show_main: true
show_temperature: true
forecast:
  type: daily
  chart_height: 180
```

### Swiss Army Knife tools

These are not standalone cards — they are tools you nest inside a `swiss-army-knife` card's `tools` list. Builder helpers (e.g. `cb.sak_circle(cx=50, cy=50, radius=45)`) live in the same module.

- **`sak_area`** — Area chart filled below sparkline.
  `{'type': 'area', 'position': {'cx': 50, 'cy': 50, 'width': 80, 'height': 30, 'entity_index': 0}, 'hours': 24}`
- **`sak_circle`** — SVG circle.
  `{'type': 'circle', 'position': {'cx': 50, 'cy': 50, 'radius': 45}}`
- **`sak_circslider`** — Circular slider.
  `{'type': 'circslider', 'position': {'cx': 50, 'cy': 50, 'radius': 40}}`
- **`sak_ellipse`** — SVG ellipse.
  `{'type': 'ellipse', 'position': {'cx': 50, 'cy': 50, 'rx': 40, 'ry': 25}}`
- **`sak_horseshoe`** — Horseshoe gauge.
  `{'type': 'horseshoe', 'position': {'cx': 50, 'cy': 50, 'radius': 45}}`
- **`sak_icon`** — Icon for one of the card's entities.
  `{'type': 'icon', 'position': {'cx': 50, 'cy': 30, 'entity_index': 0}}`
- **`sak_line`** — SVG straight line.
  `{'type': 'line', 'position': {'x1': 0, 'y1': 50, 'x2': 100, 'y2': 50}}`
- **`sak_name`** — Friendly name text for an entity.
  `{'type': 'name', 'position': {'cx': 50, 'cy': 80, 'entity_index': 0}}`
- **`sak_progpath`** — Progress-along-path tool.
  `{'type': 'progpath', 'position': {'cx': 50, 'cy': 50, 'width': 80, 'height': 30}, 'path': 'M0,0 L100,100'}`
- **`sak_rectangle`** — SVG rectangle.
  `{'type': 'rectangle', 'position': {'cx': 50, 'cy': 50, 'width': 80, 'height': 30}}`
- **`sak_rectex`** — Extended rectangle with rounded corners.
  `{'type': 'rectex', 'position': {'cx': 50, 'cy': 50, 'width': 80, 'height': 30, 'rx': 5, 'ry': 5}}`
- **`sak_regpoly`** — Regular polygon (hex, octagon, etc.).
  `{'type': 'regpoly', 'position': {'cx': 50, 'cy': 50, 'radius': 40, 'sides': 6}}`
- **`sak_segarc`** — Segmented arc gauge.
  `{'type': 'segarc', 'position': {'cx': 50, 'cy': 50, 'radius': 45, 'start_angle': 130, 'end_angle': 410}}`
- **`sak_slider`** — Interactive slider.
  `{'type': 'slider', 'position': {'cx': 50, 'cy': 50, 'length': 80}}`
- **`sak_sparkline`** — Mini sparkline graph.
  `{'type': 'sparkline', 'position': {'cx': 50, 'cy': 50, 'width': 80, 'height': 30}, 'hours': 24}`
- **`sak_state`** — Live state text for an entity.
  `{'type': 'state', 'position': {'cx': 50, 'cy': 60, 'entity_index': 0}}`
- **`sak_switch`** — Toggle switch shape.
  `{'type': 'switch', 'position': {'cx': 50, 'cy': 50}}`
- **`sak_text`** — SVG text label.
  `{'type': 'text', 'text': 'ON', 'position': {'cx': 50, 'cy': 50}}`
- **`sak_toolset`** — Toolset container — groups tools at a position.
  `{'toolset': 'main', 'position': {'cx': 50, 'cy': 50}, 'tools': []}`
- **`sak_usersvg`** — Inline user-supplied SVG.
  `{'type': 'usersvg', 'position': {'cx': 50, 'cy': 50, 'width': 50, 'height': 50}, 'svg': '<svg>...</svg>'}`

## v1.21–1.23 — Extended WS coverage

Modules added in the v1.21 → v1.23 sprint (import as
`from cli_anything.homeassistant.core import <module>`):

| Module | WS / REST coverage |
|---|---|
| `statistics_admin` | `recorder/adjust_sum_statistics`, `change_statistics_unit`, `validate_statistics`, `update_statistics_issues`, `update_statistics_metadata`, `import_statistics` |
| `trace_debug` | `trace/list`, `trace/get`, `trace/contexts` |
| `diagnostics_dl` | REST `/api/diagnostics/config_entry/{domain}/{entry_id}[/device/{device_id}]` + `save_diagnostics_to_file()` helper |
| `system_log` | WS `system_log/list`, service `system_log/clear`, `system_log/write` |
| `todos` | WS `todo/item/list`, `todo/item/move`, service `todo/add_item`, `update_item`, `remove_item`, `remove_completed_items` |
| `state_stream` | `subscribe_events`, `subscribe_state_changed`, `subscribe_trigger`, `collect_events` (synchronous wait-for-N-events) |
| `lovelace_sections_ext` | `with_section_options()`, `hero_section()`, `spacer_section()`, `divider_section()` |
| `service_shortcuts` | `notify`, `mqtt_publish`, `lock_lock/unlock/open`, `alarm_arm_away/home/night/disarm`, `persistent_notification_create/dismiss` |
| `blueprints` | `blueprint/list`, `import`, `save`, `delete`, `substitute` (+ `show()` convenience) |
| `categories` | `config/category_registry/list/create/update/delete` + `categories_by_name()` |
| `frontend_prefs` | WS `frontend/get_user_data`, `set_user_data`, REST `template`, WS `template/start_preview` |
| `hardware_info` | WS `hardware/info`, `hardware/subscribe_system_status` + `board_info()`, `cpu_info()` convenience |
| `conversation_advanced` | WS `conversation/process`, `agent/list`, `sentences/list`, `agent/homeassistant/debug`, `assist_pipeline/pipeline_debug/list/get`, `language/list`, `device/list`, `device/capture` |
| `energy_advanced` | WS `energy/validate`, `solar_forecast`, `fossil_energy_consumption`, `save_prefs` (kwargs form) |
| `auth_tokens` | WS `auth/current_user`, `refresh_tokens`, `long_lived_access_token`, `delete_refresh_token`, `delete_all_refresh_tokens`, `refresh_token_set_expiry`, `sign_path` |
| `backup_advanced` | WS `backup/details`, `delete`, `restore`, `generate_with_automatic_settings`, `agents/info`, `config/info`, `config/update`, `can_decrypt_on_download` |
| `mobile_app` | WS `mobile_app/push_notification_channel`, `push_notification_confirm` |
| `weather_advanced` | WS `weather/convertible_units`, `weather/subscribe_forecast`, service `weather/get_forecasts` |

Coverage jumped from ~33% to ~70% of HA's user-facing WS surface. Test count: 985 unit tests.

## v1.24 — Sprint 4 gap-closure (+39 WS commands)

| Module | WS commands |
|---|---|
| `camera_ws` | `camera/capabilities`, `stream`, `get_prefs`, `update_prefs`, `webrtc/get_client_config`, `webrtc/offer`, `webrtc/candidate` |
| `shopping_list` | `shopping_list/items`, `items/add`, `items/update`, `items/remove`, `items/clear`, `items/reorder` |
| `media_source` | `media_source/browse_media`, `resolve_media`, `local_source/remove` |
| `device_automation` | `device_automation/{trigger,condition,action}/{list,capabilities}` + `summarise_device()` aggregator |
| `expose_entity` | `homeassistant/expose_entity/list`, `expose_entity`, `expose_new_entities/get`, `expose_new_entities/set` |
| `network` | `network`, `network/configure`, `network/url` |
| `assist_satellite` | `assist_satellite/get_configuration`, `set_wake_words`, `test_connection`, `intercept_wake_word` |
| `logger_ws` | `logger/log_info`, `log_level`, `integration_log_level` (runtime log levels) |
| `calendar_ws` | `calendar/event/create`, `event/update`, `event/delete` (WS variants — REST still in `calendars.py`) |

WS coverage: **66.2% → 82.7%** of HA's WS surface. Test count: **1158**.

## Notes & Caveats

- The CLI is **stateless across invocations** — only the connection profile
  is persisted. There is no `project save`/`session save` step. (HARNESS.md's
  "auto-save + --dry-run" rule applies only to harnesses with mutable
  client-side state; this one has none. `--dry-run` is still supported on
  mutating commands so agents can preview a request before sending it.)
- WebSocket subscriptions (`event subscribe`) keep an open connection; in
  scripts, set `--limit` and/or `--timeout` so the call returns.
- `state set` is a **manual override** — it tells HA "this entity now has
  state X". For most workflows you probably want `service call <domain>.<svc>`
  instead, which goes through HA's normal entity logic.
- Long-lived access tokens grant full admin access. Treat the profile file
  (`~/.config/cli-anything-homeassistant.json`) as a secret — it is created
  with `0600` permissions.
