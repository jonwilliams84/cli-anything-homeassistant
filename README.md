# cli-anything-homeassistant

A command-line + Python harness for [Home Assistant](https://www.home-assistant.io)
that exposes the full WebSocket + REST API surface — states, services, registries,
lovelace dashboards, automations, scripts, backups, diagnostics, statistics,
config flows, blueprints, and more — through a single agent-friendly CLI with
JSON output on every command.

Built to be the third-party automation layer on top of HA: read live state,
mutate registries, surgically edit dashboards, debug traces, push backups
before risky operations, and stream live events — all without touching the
HA UI.

## Install

```bash
git clone https://github.com/jonwilliams84/cli-anything-homeassistant.git
cd cli-anything-homeassistant
pip install -e .
cli-anything-homeassistant --help
```

External dep: a running Home Assistant with a long-lived access token.

## First-time setup

```bash
cli-anything-homeassistant \
  --url http://homeassistant.local:8123 \
  --token "<long-lived-token>" \
  config save
```

Profile is stored at `~/.config/cli-anything-homeassistant.json`. Per-key env
overrides also work: `CLI_HA_URL`, `CLI_HA_TOKEN`, etc.

## What it covers

| Group | Coverage |
|---|---|
| `state` / `service` / `event` | Live state machine, service calls, event bus fire |
| `template` | Render Jinja against live state (`--file` for multi-line) |
| `history` / `logbook` | Time-series and human-readable change logs |
| `system` | API status, config, core-state, components, **error-log triage** (`--since` / `--top --by` / `--watch`), health |
| `lovelace` | Dashboard inventory + **surgical view/section/card edits**, search, paths, lint, prune, mirror |
| `automation` / `script` | List, trigger, run, reload, **traces** + `get_trace` for both |
| `area` / `floor` / `label` | **Full CRUD** on every registry |
| `entity` | List + **bulk-update** (rename / move-area / label / disable) + `inspect` (one-shot combined view) |
| `device` | List + update (name / area / labels / disable) |
| `person` / `tag` | CRUD |
| `helpers` / `template-helper` | Create / update / show input_*/template helpers |
| `config-entry` / `config-flow` | List / reload / options-flow + **create new integrations** via single-shot or multi-step flow |
| `mqtt` / `mqtt-discovery` | Publish, subscribe, MQTT-discovery list/show/republish |
| `repairs` | What HA thinks is wrong; list / show / ignore / fix |
| `notifications` | Persistent notifications create / list / dismiss |
| `backup` | Snapshot list / create / show / delete / restore (HA 2024.6+) |
| `statistics` | Long-term recorder stats: list / metadata / **series** (chart data) / update-metadata / clear |
| `diagnostics` | Per-integration + per-device JSON downloads (same as UI's "Download diagnostics") |
| `blueprint` | List / import / save / delete / substitute (dry-run render) |
| `assist` | Send text to HA's conversation pipeline; list Assist pipelines |
| `updates` | List, install, skip, clear-skipped on `update.*` entities |
| `logger` | Runtime log-level control without restart |
| `group` | List members of light/switch/sensor groups |
| `auth` | Users, long-lived tokens, whoami |
| `event subscribe` / `state watch` | Live tails — agent-friendly until-state-X loops |
| `entity-references` | Find every UI-managed automation/template/lovelace that mentions an entity_id |
| `scene` | List, activate (with `--transition`), apply ad-hoc states, snapshot to a new scene, reload |
| `weather` | List `weather.*` entities, convertible units, one-shot `forecast`, WS `forecast-subscribe` |
| `shopping-list` | Default HA shopping list — list / add / update / remove / clear-completed / reorder |
| `todo` | Any `todo.*` integration — list / add / update / complete / remove / move / clear-completed |
| `lock` | `lock.*` shortcuts: `lock` / `unlock` / `open` (garage-door style) |
| `alarm` | `alarm_control_panel.*` — `arm-away` / `arm-home` / `arm-night` / `arm-vacation` / `disarm` |
| `search` | `search/related` — every automation/scene/script/dashboard tied to an entity, device, area, … |
| `entity expose` | Per-assistant expose flags + new-entity defaults (cloud.alexa / cloud.google_assistant) |
| `camera` | `camera.*` capabilities, HLS stream URL, prefs, WebRTC client config |
| `device-automation` | List a device's available triggers, conditions, actions — what the HA UI's automation editor shows |
| `assist agents` / `sentences` / `debug` / `satellites` / `languages` | Conversation pipeline introspection + sentence-matching debugger |
| `assist-satellite` | `assist_satellite.*` — current config, set wake words, test connection |
| `mobile-app` | Companion app push delivery receipts |
| `media` | media_source browse / resolve to URL / local file remove |
| `light` | `light.*` — `on` (brightness/kelvin/rgb/effect/transition) / `off` / `toggle` |
| `media-player` | `media_player.*` — play/pause/stop/next/prev, volume/mute, source, play-media, shuffle, repeat, join/unjoin |
| `climate` | `climate.*` — set-temperature, set-hvac-mode, set-fan-mode, set-preset, set-humidity, set-swing |
| `cover` | `cover.*` — open/close/stop/toggle, set-position, set-tilt + tilt open/close/stop |
| `fan` | `fan.*` — turn-on (percentage/preset), set-percentage, set-preset, set-direction, oscillate, increase/decrease |
| `vacuum` | `vacuum.*` — start/stop/pause, return-to-base, locate, clean-spot, set-fan-speed, send-command |
| `humidifier` | `humidifier.*` — on/off/toggle, set-humidity, set-mode |
| `water-heater` | `water_heater.*` — on/off, set-temperature, set-operation-mode, set-away-mode |
| `valve` | `valve.*` — open/close/stop/toggle, set-position |
| `lawn-mower` | `lawn_mower.*` — start, pause, dock |
| `siren` | `siren.*` — on (duration/tone/volume), off, toggle |
| `remote` | `remote.*` — turn-on (activity), send-command, learn-command, delete-command |
| `number` / `select` / `button` / `text` | One-shot input setters: `number set`, `select set`/`next`/`previous`, `button press`, `text set` |
| `notify` | `notify.<service>` send with title/target/data |
| `powercalc` | `list` / `create` / `set-template` / `set-power` / `reload` + `group {members,add-members,remove-members,set-members}` — safety wrappers over the REPLACE-on-write and binary_sensor-no-op footguns |
| `entity restored` / `entity orphans` / `entity prune` | Find and bulk-delete orphan registry entries; backup-first + dry-run by default + per-entity error tolerance |
| `recorder top` | Rank entities by state-change count over a window — first question when investigating recorder DB bloat |

## Quick examples

```bash
# Live triage: what's broken in the last hour?
cli-anything-homeassistant system error-log --since 1h --errors-only \
  --top 10 --by component

# Snapshot before a risky bulk edit
cli-anything-homeassistant backup create --name "pre-rotation snapshot"

# Bulk-rename / re-area entities by pattern
cli-anything-homeassistant entity bulk-update \
  --pattern '_sophie_bedroom' --set-area sophie_bedroom --dry-run

# Wait until someone comes home, then do something
cli-anything-homeassistant state watch person.jon \
  --until-state home --duration 1800
&& cli-anything-homeassistant service call notify.mobile_app_jon \
   --data 'title=Welcome' --data 'message=Coffee on?'

# Find dead entity references after renaming a sensor
cli-anything-homeassistant entity-references sensor.old_name

# Surgical edit a single view in a dashboard without a full re-push
cli-anything-homeassistant lovelace view get jon-mobile scratch -o view.json
# edit view.json...
cli-anything-homeassistant lovelace view set jon-mobile scratch view.json

# Entity-control shortcuts (typed args beat raw `service call`)
cli-anything-homeassistant light on light.kitchen --brightness 200 --kelvin 2700
cli-anything-homeassistant climate set-temperature climate.living -t 21.5 --hvac-mode heat
cli-anything-homeassistant media-player play-media media_player.sonos \
  spotify:track:xyz music --enqueue add
cli-anything-homeassistant cover set-position cover.blinds 50
cli-anything-homeassistant select set select.washer_program quick_30
cli-anything-homeassistant notify send "Door left open" \
  --service mobile_app_jon --title "Heads up"

# Powercalc edits without the manual options-flow dance
cli-anything-homeassistant powercalc list --title-contains "Dining"
cli-anything-homeassistant powercalc set-template <ENTRY_ID> \
  "{{ 30 * ((state_attr('fan.dining','percentage')|float(0))/100)**3 \
       if is_state('fan.dining','on') else 0 }}"
cli-anything-homeassistant powercalc group add-members \
  --entry-id <GROUP_ID> --sensor sensor.power_dining \
  --member sensor.dining_room_fan_power

# Find orphaned / restored registry entries and prune safely
cli-anything-homeassistant entity restored --platform cloud
cli-anything-homeassistant entity prune --platform unifi \
  --disabled-by integration               # dry-run by default
cli-anything-homeassistant entity prune --platform unifi \
  --disabled-by integration --apply       # actually delete

# What's hammering the recorder right now?
cli-anything-homeassistant recorder top --hours 24 --domain sensor --limit 20

# Powercalc calibration (v1.37+) — figure out where the model is wrong
cli-anything-homeassistant --json powercalc audit --hours 24             # passive coverage report
cli-anything-homeassistant --json powercalc auto-calibrate --hours 168   # passive median-of-transitions from history
cli-anything-homeassistant powercalc calibrate <entry_id> \
    --service-on switch.turn_on --target switch.tower_fan \
    --service-off switch.turn_off --apply                                # active single-shot fixed-power
cli-anything-homeassistant powercalc calibrate-template <entry_id> \
    --source fan.x --attribute percentage \
    --service-set fan.set_percentage --state-arg percentage \
    --service-off fan.turn_off --states 0,25,50,75,100 --apply           # active variable-power

# Tier 2 (v1.38+): linear regression of smart-meter vs per-device on/off
# state — recovers per-device average load even for devices with no clean
# OFF→ON transitions. numpy-only; needs ~7 days of history.
cli-anything-homeassistant --json powercalc regress --hours 168                # dry-run
cli-anything-homeassistant powercalc regress --title-contains Lamp --apply     # commit
```

## Agent / `--json` mode

Every command supports `--json` for machine-readable output. Pair with `jq`
for shell pipelines or pipe straight into a Python script via `subprocess`.

```bash
cli-anything-homeassistant --json device list | \
  jq '.[] | select(.manufacturer=="Aqara") | {id,name:.name_by_user}'

cli-anything-homeassistant --json statistics series \
  sensor.smart_meter_electricity_import_today --period hour --type change | \
  jq '.[] | map(.change) | add'
```

The packaged `cli_anything/homeassistant/skills/SKILL.md` is a self-contained
skill manifest agents can load for full command documentation.

## Architecture

```
cli_anything/homeassistant/
├── homeassistant_cli.py     # Click CLI + REPL
├── core/                    # One module per HA API surface
│   ├── states.py, services.py, events.py, history.py, logbook.py
│   ├── automation.py, script.py
│   ├── areas.py, floors.py, labels.py, persons.py, tags.py
│   ├── registry.py (entity + device write), template_helpers.py
│   ├── lovelace.py, lovelace_paths.py, lovelace_cards.py, lovelace_mirror.py
│   ├── config_entries.py, blueprints.py
│   ├── backup.py, control.py, repairs.py, notifications.py
│   ├── diagnostics.py, statistics.py, assist.py, updates.py, inspect.py
│   ├── logger.py, groups.py, mqtt.py, mqtt_discovery.py, watch.py
│   └── system.py, references.py, recorder.py, template.py
└── utils/
    ├── homeassistant_backend.py   # requests Session + WS client
    └── repl_skin.py
```

The wire client is a thin `requests.Session` + a websocket subscriber. Every
core module is a pure function-per-operation, callable directly from Python
or via the Click wrappers.

## Tests

```bash
pip install -e '.[test]'  # if you want pytest
python3 -m pytest tests/ -v
```

Tests use a FakeClient that records every call — over 200 unit tests cover
every core module against synthetic payloads. End-to-end tests boot a real
Home Assistant in a temp config dir (requires `pip install homeassistant`).

## Sibling projects

This is part of a small `cli-anything-*` family of harnesses for connected
devices/services I run at home:

- [`cli-anything-zigbee2mqtt`](#) — full bridge + device control over MQTT
- [`cli-anything-espresense`](#) — BLE presence rooms + node config

All three share the same connection-profile pattern, JSON output, and REPL.

## License

MIT — see [LICENSE](./LICENSE).
