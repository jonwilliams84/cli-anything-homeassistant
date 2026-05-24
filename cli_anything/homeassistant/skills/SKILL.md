---
name: cli-anything-homeassistant
description: >-
  Drive a running Home Assistant from the shell. A stateless CLI + REPL over
  HA's REST and WebSocket APIs. Read any entity, call any service, render Jinja
  templates, manage automations/scripts/scenes/blueprints/backups/dashboards,
  inspect registries (area/device/entity/floor/label/category/zone), audit
  diagnostics + statistics, manage powercalc, edit Lovelace surgically, watch
  live events, fire webhooks, snapshot image entities, and drive the profiler
  integration for live perf triage. 17 typed shortcut groups (light, media-player, climate,
  cover, fan, vacuum, …) so agents never hand-craft JSON for routine entity
  control. Every command has --json for machine output. Use this when an agent
  needs to do anything to a smart home without the browser UI.
---

# cli-anything-homeassistant — agent skill

**The CLI does not reimplement Home Assistant.** Every command resolves to one
or more API calls against a running HA server. If HA is offline, the CLI
returns a clear error. The CLI is stateless between invocations — only the
connection profile is persisted on disk.

## Cold-start checklist (always do this first)

When you join a session and don't know the install, run these in order:

```bash
# 1. Confirm you can reach HA and the token is valid.
cli-anything-homeassistant --json system info
# → {"message": "API running."} or an error.

# 2. Know who you are.
cli-anything-homeassistant --json whoami
# → {"id", "name", "is_admin", "is_owner"}

# 3. Inventory the install.
cli-anything-homeassistant --json state counts          # {domain: count}
cli-anything-homeassistant --json area list             # rooms + ids
cli-anything-homeassistant --json floor list            # storey topology
cli-anything-homeassistant --json system config | jq '{version, location_name, time_zone, unit_system}'

# 4. Know what services exist.
cli-anything-homeassistant --json service domains       # ["light","switch",...]
```

Pass `--json` whenever scripting. Output is a single JSON document; errors go
to stderr with non-zero exit. Skip `--json` for human-readable output.

## Installation

```bash
pip install cli-anything-homeassistant
```

External dependency: a running HA instance reachable via HTTP, and a
long-lived access token (HA UI → profile → Long-Lived Access Tokens).

```bash
cli-anything-homeassistant --url http://homeassistant.local:8123 \
    --token "<LLAT>" config save
cli-anything-homeassistant config test    # confirms reachability
```

Profile lives at `~/.config/cli-anything-homeassistant.json` (mode `0600`).
Environment overrides: `HASS_URL`, `HASS_TOKEN`, `HASS_VERIFY_SSL`,
`HASS_TIMEOUT`.

## Command-group index

| Group              | Purpose (one line)                                                                             |
|--------------------|------------------------------------------------------------------------------------------------|
| `config`           | Connection profile: `show`, `set`, `save`, `test`.                                              |
| `system`           | Server introspection (REST): info, config, core-state, error-log, components, manifest/analytics/issue/usb-scan/zha-permit-join/hardware-info/log. |
| `state`            | Entity state read/write: `list`, `get`, `set`, `delete`, `domains`, `counts`.                  |
| `service`          | Service registry + calls: `list`, `domains`, `describe`, `call -D key=value -T entity_id=…`.    |
| `event`            | Event bus: `list`, `fire`, `subscribe --limit N`.                                              |
| `template`         | Render Jinja against live state; `-V key=value` to inject vars.                                |
| `area`/`floor`/`label`/`category` | Full CRUD on each registry (WebSocket).                                          |
| `device`           | Device registry + updates (name/area/labels/disable).                                          |
| `entity`           | Entity registry + bulk-update (rename/move-area/label/disable) + `inspect`; `entity expose` for cloud assistants. |
| `entity-references`| Find every automation/script/scene/dashboard that names a given entity.                        |
| `helpers`          | input_select / input_boolean / input_button / input_number / input_text / input_datetime / counter / timer / schedule. |
| `template-helper`  | Create/update template-derived sensors/binary_sensors/etc.                                     |
| `automation`       | `list`, `trigger`, `toggle`, `turn-on`/`turn-off`, `reload`, traces (`traces`, `trace-get`).   |
| `script`           | `list`, `run`, `reload`, traces.                                                               |
| `scene`            | `list`, `activate`, `apply` (ad-hoc), `create` (snapshot), `reload`.                            |
| `blueprint`        | `list`, `import`, `save`, `delete`, `substitute` (dry-run render).                              |
| `config-entry`     | List/get/reload/delete/update + options flows (`options-init`/`options-configure`/`options-set`). |
| `config-flow`      | Create new integrations: `init`, `configure`, `create`, `get`, `abort`, `walk` (multi-step driver). |
| `subentry`         | Manage config-entry subentries.                                                                |
| `mqtt`             | `publish`, `subscribe` (diagnostics).                                                          |
| `mqtt-discovery`   | List/show/republish discovery topics.                                                          |
| `history`/`logbook`| Time-series + human-readable change logs (use `--hours`, `--start`, `-e entity_id`).            |
| `recorder`         | Recorder introspection — entity history depth checks.                                          |
| `statistics`       | Long-term stats: `list`, `metadata`, `series`, `update-metadata`, `clear`.                     |
| `backup`           | `list`, `create`, `show`, `delete`, `restore` (HA 2024.6+).                                     |
| `repairs`          | `list`, `show`, `ignore`, `fix` on HA's repairs feed.                                          |
| `diagnostics`      | Per-integration + per-device diagnostic JSON downloads.                                        |
| `lovelace`         | Dashboards: `dashboards`, `config`, `view`, `section`, `resources`, `card`, `badge` — surgical edits. |
| `lovelace-tools`   | Backup/diff utilities for dashboards.                                                          |
| `notifications`    | Persistent notification create/list/dismiss.                                                   |
| `tag`              | NFC tags + HA tag IDs.                                                                         |
| `tts`              | Text-to-speech: engines, speak, clear-cache.                                                   |
| `assist`           | Conversation pipeline: send text, list agents/sentences/languages, debug sentence matching.    |
| `assist-satellite` | `assist_satellite.*` — current config, set wake words, test connection.                        |
| `mobile-app`       | Companion app push delivery receipts.                                                          |
| `media`            | `media_source` browse / resolve / remove.                                                      |
| `camera`           | `camera.*` capabilities / HLS stream URL / prefs / WebRTC config.                              |
| `device-automation`| List a device's available triggers/conditions/actions.                                         |
| `auth`             | `me`, `sign-path`, `tokens` (refresh-token CRUD), `user` (full user admin).                    |
| `logger`           | Runtime log-level control (REST + WS-per-component).                                           |
| `search`           | `search/related` — every automation/scene/script/dashboard tied to an item.                    |
| `group`            | List members of a group entity.                                                                |
| `person`           | Person registry + their device_trackers.                                                       |
| `hacs`             | HACS repository management.                                                                    |
| `theme`            | Frontend themes — list/set/reload.                                                             |
| `weather`          | `weather.*` — list, convertible units, `forecast`, `forecast-subscribe`.                       |
| `shopping-list`    | Default HA shopping list — list/add/update/remove/clear/reorder.                               |
| `todo`             | `todo.*` integrations — list/add/update/complete/remove/move/clear.                            |
| `lock`/`alarm`     | Shortcut groups: lock/unlock/open; arm-away/arm-home/arm-night/arm-vacation/disarm.            |
| `updates`          | `update.*` entities: list, install, install-all, skip, clear-skipped.                          |
| `zone`             | Zone registry (storage zones via `config/zone/*` WS): list/state-list/find/create/update/delete; `entities` lists person/device_tracker entities currently inside. |
| `webhook`          | Webhook discovery + triggering: `list` (registered + automations + mobile_app), `trigger` (POST/PUT/GET/HEAD with guard), `generate-id`, `cloudhooks`, `cloudhook-create`/`-delete`. |
| `image`            | `image.*` entities: `list`, `show`, `snapshot <eid> <path>` (signed or direct), `proxy-url` (signed URL minted via `auth/sign_path`), `subscribe` for update events. |
| `profiler`         | `profiler.*` services: `start` (cProfile), `memory` (memray), `dump-log-objects`, `log-thread-frames`/`log-current-tasks`/`log-event-loop-scheduled`, `lru-stats`, `set-asyncio-debug`, `status` (loaded? services exposed?). |
| `whoami`           | Current user (id, name, admin/owner flags).                                                    |
| **Entity-control shortcut groups** (typed, ergonomic — prefer these over raw `service call`) | |
| `light`            | `on` (brightness/kelvin/rgb/effect/transition/profile/white), `off`, `toggle`.                  |
| `media-player`     | `play`/`pause`/`stop`/`play-pause`/`next`/`previous`, `volume-set`/`volume-up`/`volume-down`/`mute`, `select-source`/`select-sound-mode`, `play-media`, `shuffle`, `repeat`, `clear-playlist`, `turn-on`/`turn-off`, `join`/`unjoin`. |
| `climate`          | `set-temperature` (`-t`/`--high`/`--low`/`--hvac-mode`), `set-hvac-mode`, `set-fan-mode`, `set-preset`, `set-humidity`, `set-swing`, `turn-on`/`turn-off`. |
| `cover`            | `open`/`close`/`stop`/`toggle`, `set-position`, `set-tilt`, `open-tilt`/`close-tilt`/`stop-tilt`. |
| `fan`              | `turn-on`/`turn-off`/`toggle`, `set-percentage`, `set-preset`, `set-direction` (forward/reverse), `oscillate`, `increase`/`decrease`. |
| `vacuum`           | `start`/`stop`/`pause`, `return-to-base`, `locate`, `clean-spot`, `set-fan-speed`, `send-command`. |
| `humidifier`       | `turn-on`/`turn-off`/`toggle`, `set-humidity`, `set-mode`.                                      |
| `water-heater`     | `turn-on`/`turn-off`, `set-temperature`, `set-operation-mode`, `set-away-mode`.                 |
| `valve`            | `open`/`close`/`stop`/`toggle`, `set-position`.                                                |
| `lawn-mower`       | `start`, `pause`, `dock`.                                                                      |
| `siren`            | `on` (`--duration`/`--tone`/`--volume`), `off`, `toggle`.                                       |
| `remote`           | `turn-on` (`--activity`), `turn-off`, `toggle`, `send-command`, `learn-command`, `delete-command`. |
| `number`           | `set <entity_id> <value>`.                                                                     |
| `select`           | `set <entity_id> <option>`, `next`, `previous`, `first`, `last`.                                |
| `button`           | `press <entity_id>`.                                                                           |
| `text`             | `set <entity_id> <value>`.                                                                     |
| `notify`           | `send <message> [--title …] [--service notify|mobile_app_…] [--target …]+ [--data <json>]`.     |
| `domain`           | Last-resort generic per-domain `turn-on`/`turn-off`/`toggle`/`list` for any controllable domain. Use a typed shortcut group above if one exists. |

Always start with `--help` if you're unsure:
`cli-anything-homeassistant <group> [<subcommand>] --help`.

## Golden-path recipes

### Find entities by attribute

```bash
# All lights in a given area (entity-registry view, not state)
cli-anything-homeassistant --json area list \
  | jq '.[] | select(.name=="Kitchen") | .area_id'        # → "kitchen"
cli-anything-homeassistant --json entity list --domain light \
  | jq '.[] | select(.area_id=="kitchen") | .entity_id'

# Every entity referencing "kitchen" anywhere (id or friendly_name)
cli-anything-homeassistant --json state list \
  | jq '[.[] | select((.entity_id + " " + (.attributes.friendly_name//"")) | test("kitchen"; "i"))]'
```

### Turn things on/off — prefer typed shortcuts

```bash
# DON'T (verbose, no validation):
cli-anything-homeassistant service call light turn_on \
    -T entity_id=light.kitchen -D brightness=200 -D kelvin=2700

# DO (typed, validated):
cli-anything-homeassistant light on light.kitchen --brightness 200 --kelvin 2700

cli-anything-homeassistant light off light.kitchen --transition 1.5
cli-anything-homeassistant climate set-temperature climate.living -t 21.5
cli-anything-homeassistant cover set-position cover.kitchen_blind 50
cli-anything-homeassistant media-player play-media media_player.sonos spotify:track:xyz music --enqueue add
cli-anything-homeassistant select set select.washer_program quick_30
cli-anything-homeassistant button press button.doorbell_chime
cli-anything-homeassistant notify send "Door left open" --service mobile_app_jon --title "Heads up"
```

### Activate a scene / apply ad-hoc states

```bash
cli-anything-homeassistant scene activate scene.movie_night --transition 2
cli-anything-homeassistant scene apply \
  --entity light.kitchen=on \
  --entity 'light.island={"brightness": 200, "color_temp_kelvin": 2700}'
cli-anything-homeassistant scene create movie_now \
  --snapshot light.kitchen --snapshot light.island
```

### Live triage

```bash
cli-anything-homeassistant system error-log --since 1h --errors-only --top 10 --by component
cli-anything-homeassistant repairs list --json
cli-anything-homeassistant --json state list \
  | jq '[.[] | select(.state=="unavailable") | .entity_id]'
```

### Wait until something happens

```bash
# Block until a person arrives home (max 30 min), then act
cli-anything-homeassistant state watch person.jon --until-state home --duration 1800 \
  && cli-anything-homeassistant notify send "Welcome" --service mobile_app_jon

# Stream the next 20 state-changed events for one entity
cli-anything-homeassistant --json event subscribe state_changed --limit 20 \
  --filter 'data.entity_id=sensor.outdoor_temperature'
```

### Safe bulk renames / re-area

```bash
# Dry-run any bulk-update first
cli-anything-homeassistant entity bulk-update \
  --pattern '_sophie_bedroom' --set-area sophie_bedroom --dry-run
# Then drop --dry-run
```

### Backup before any risky edit

```bash
cli-anything-homeassistant backup create --name "pre-rotation snapshot"
cli-anything-homeassistant backup list --json
```

### Render templates without poking automations

```bash
cli-anything-homeassistant template '{{ states("sensor.outdoor_temperature") | float }}'
cli-anything-homeassistant template '{{ now().isoformat() }}'
cli-anything-homeassistant template -V room=kitchen \
  '{{ states("sensor." + room + "_temperature") }}'
```

### Long-term stats (cheap chart data)

```bash
cli-anything-homeassistant --json statistics series \
  sensor.smart_meter_electricity_import_today \
  --period hour --type change \
  | jq '[.[] | .change] | add'
```

### Lovelace surgical edit (one view, no full re-push)

```bash
cli-anything-homeassistant lovelace view get jon-mobile scratch -o view.json
# edit view.json…
cli-anything-homeassistant lovelace view set jon-mobile scratch view.json
```

### Find dead references after a rename

```bash
cli-anything-homeassistant entity-references sensor.old_name
```

### Service introspection (when a typed shortcut doesn't exist)

```bash
cli-anything-homeassistant --json service describe vacuum send_command \
  | jq '.fields'
# Inspect the schema before guessing arg shapes.
```

### Zone CRUD + presence introspection

```bash
# Create a zone for the office
cli-anything-homeassistant zone create Office --lat 51.502 --lon -0.105 \
  --radius 250 --icon mdi:office-building

# Who is at home right now?
cli-anything-homeassistant --json zone entities zone.home \
  | jq '.[] | .entity_id'
```

### Webhook list + fire-by-id

```bash
# Inventory every webhook id this HA honours
cli-anything-homeassistant --json webhook list \
  | jq '{registered: .registered|length, automations: .automations|length}'

# Fire a known webhook with JSON body
cli-anything-homeassistant webhook trigger abc123 --data '{"door":"open"}'

# Mint a fresh id for a new automation
cli-anything-homeassistant --json webhook generate-id | jq -r .webhook_id
```

### Image entity snapshot

```bash
# Save the current frame of an image entity to disk
cli-anything-homeassistant image snapshot image.front_door /tmp/door.png --overwrite

# Get a signed URL valid for 5 minutes (no Auth header needed)
cli-anything-homeassistant image proxy-url image.front_door --expires 300 --json
```

### Profiler — live perf triage

```bash
# Is the profiler integration even loaded?
cli-anything-homeassistant --json profiler status

# 60s cProfile dump → .storage
cli-anything-homeassistant profiler start --seconds 60

# Dump every live State object to the log
cli-anything-homeassistant profiler dump-log-objects --type State

# Snapshot every running asyncio task
cli-anything-homeassistant profiler log-current-tasks
```

## Output shapes (so agents can write jq without guessing)

### `state get <entity_id>`

```json
{
  "entity_id": "sensor.outdoor_temperature",
  "state": "14.2",
  "attributes": {
    "unit_of_measurement": "°C",
    "device_class": "temperature",
    "friendly_name": "Outdoor temperature"
  },
  "last_changed": "2026-05-23T10:15:32.123456+00:00",
  "last_updated": "2026-05-23T10:15:32.123456+00:00",
  "context": {"id": "01H...","parent_id": null, "user_id": null}
}
```

### `state list` — array of the above.

### `service domains` — array of strings:

```json
["light","switch","fan","cover","media_player","climate","scene","automation","script", …]
```

### `area list`

```json
[
  {"area_id":"kitchen","name":"Kitchen","floor_id":"ground","icon":"mdi:silverware-fork-knife","labels":["wet"]},
  …
]
```

### `entity list --domain light`

```json
[
  {"entity_id":"light.kitchen","platform":"hue","area_id":"kitchen",
   "device_id":"...","disabled_by":null,"hidden_by":null,"labels":[],
   "name":null,"original_name":"Kitchen","unique_id":"..."},
  …
]
```

## Pitfalls

These are paid in lost time. Read them before mutating anything.

- **Token = full admin.** Treat `~/.config/cli-anything-homeassistant.json`
  as a secret.
- **`state set` is a manual override**, not a service call. It writes a state
  directly into HA's state machine without going through the entity's normal
  logic. For controlling devices, always use `service call <domain>.<svc>` or
  a typed shortcut group.
- **WebSocket `subscribe` commands keep an open connection** — in scripts,
  always pass `--limit` and/or `--timeout` so the call returns.
- **Mutating commands accept `--dry-run`** (where it makes sense). The dry
  run never touches HA. Use it for any "I'm going to bulk-rename N entities"
  command.
- **Lovelace dashboards** — prefer `lovelace view get` / `view set` /
  `section ...` over re-pushing the full config. The full-config write is
  destructive and easy to corrupt.
- **Powercalc group membership is REPLACE-on-write** at the API level.
  Use the wrapper `core/powercalc.py::add_group_members` /
  `remove_group_members` (or the dedicated CLI surface when wired) rather
  than hand-rolling the options flow — a typo wipes the whole group.
- **Powercalc fixed-mode on a `binary_sensor` source silently no-ops**
  (the resulting power sensor stays at 0 W). Use `power_template` with
  `is_state(...)` instead. `create_virtual_power` in this harness refuses
  the bad combination.
- **Group rollups don't auto-refresh upstream caches** when you add a new
  leaf entry. After creating a virtual_power entry that joins a sub-group
  (e.g. `Power · Dining Room`), reload the parent group entries (e.g.
  `Power · Ground Floor`, `Power · Home Total`) with
  `cli-anything-homeassistant config-entry reload <entry_id>` so the
  flat `entities` attribute regenerates.
- **`--json` is a one-shot document**, not NDJSON. For `event subscribe`
  with `--limit 1`, expect a JSON array of length 1, not a single object.
- **Two integrations can mirror the same physical device** (e.g. a TV via
  Google Cast + Bravia). Powercalc on each = double-counted load. Pick one
  source-of-truth media_player and powercalc only that.

## Discovery cookbook for unknown installs

When you arrive at an install you don't know:

```bash
# 1. Connectivity + auth
cli-anything-homeassistant --json system info
cli-anything-homeassistant --json whoami

# 2. The map
cli-anything-homeassistant --json area list
cli-anything-homeassistant --json floor list                       # if any
cli-anything-homeassistant --json device list                      # devices
cli-anything-homeassistant --json entity list --domain light       # narrow

# 3. The clock + units
cli-anything-homeassistant --json system config \
  | jq '{version, time_zone, unit_system, country, latitude, longitude}'

# 4. The integrations
cli-anything-homeassistant --json system components | head -20
cli-anything-homeassistant --json config-entry list \
  | jq 'group_by(.domain) | map({domain: .[0].domain, count: length}) | sort_by(-.count)'

# 5. The automations + scripts
cli-anything-homeassistant --json automation list | jq '.[].entity_id'
cli-anything-homeassistant --json script list | jq '.[].entity_id'

# 6. What's broken right now
cli-anything-homeassistant --json repairs list
cli-anything-homeassistant system error-log --since 1h --errors-only --top 5 --by component

# 7. Health
cli-anything-homeassistant --json system health
```

## REPL mode

Running `cli-anything-homeassistant` with no arguments drops into an
interactive REPL with the same command tree, history, and tab completion.
Inside the REPL, omit the program name: just `state get sensor.outdoor_temperature`,
`light on light.kitchen --brightness 200`, etc. `exit` or Ctrl-D quits.

## Why this exists

Home Assistant has no first-class CLI of its own (only `hass --check-config`
type commands). Every operation a human does in the UI maps to one or more
REST / WebSocket calls. This harness wraps those calls so an agent — even a
small local model — can drive HA without screen-scraping the dashboard or
inventing its own HTTP client. The 17 entity-control shortcut groups exist
specifically so that small models don't have to think about service-data
JSON shapes for the everyday cases (turn on a light, set a thermostat,
queue a track, drop a blind).
