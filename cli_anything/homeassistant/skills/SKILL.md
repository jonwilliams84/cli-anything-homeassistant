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
  control. RESOLVE A TARGET to the entities a service call would really hit,
  including the areas and labels HA cannot resolve and would silently ignore.
  GET A BACKUP OFF THE BOX and push one back, upload files/media/images, search
  the media sources, and mint a TTS URL without playing it. READ THE
  PREFERENCES THAT SHAPE EVERYTHING ELSE: which AI Task model a job reaches,
  whether an HTTP change is live or merely pending, which HA Labs preview
  features are on, and whether an entity is recorded at all — the reason a
  history is empty rather than quiet. Every command has --json for machine
  output. Use this when an agent needs to do anything to a smart home without
  the browser UI.
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
| `automation`       | `list`, `trigger`, `toggle`, `turn-on`/`turn-off`, `reload`, `get`/`save`/`delete` (UI-managed config), traces (`traces`; `trace <entity> [run_id] [--vars]` — run_id positional or `--run-id`; `--vars` flattens to per-step changed vars + service calls). |
| `script`           | `list`, `run`, `reload`, `get`/`save`/`delete` (UI-managed config), `traces`, `trace <entity> [run_id] [--vars]`. |
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
| `assist`           | Conversation pipeline: send text, list agents/sentences/languages, debug sentence matching. `assist run` executes a pipeline END TO END (STT -> agent -> TTS); `--audio cmd.wav` transcribes a 16-bit mono WAV, `--save-tts` keeps the spoken reply. |
| `assist-satellite` | `assist_satellite.*` — current config, set wake words, test connection.                        |
| `mobile-app`       | Companion app push delivery receipts.                                                          |
| `media`            | `media_source` browse / resolve / remove.                                                      |
| `camera`           | `camera.*` capabilities / HLS URL / prefs / WebRTC + `snapshot`, `capture`, `proxy-url`.       |
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
| `alarmo`           | [Alarmo](https://github.com/nielsfaber/alarmo) HACS alarm integration: `arm`/`disarm` (services, `--mode`/`--code`/`--skip-delay`/`--force`), `enable-user`/`disable-user`, `config`/`config-set`, `areas`/`area-create`/`area-delete`, `sensors`/`sensor-show`/`sensor-remove`/`sensor-update`, `users`/`automations`/`sensor-groups`/`entities`. Sensor/config/area writes hit `/api/alarmo/*`; reads over WS. Destructive verbs (`sensor-remove`, `sensor-update`, `area-delete`, `config-set`) carry `--dry-run`/`--yes`. |
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
| `domain`           | Last-resort generic per-domain `turn-on`/`turn-off`/`toggle`/`list` for any controllable domain (now also accepts `valve`/`lock`/`lawn_mower`/`alarm_control_panel`/`group` — v1.39+). |
| **New in v1.39 — wired core modules** | |
| `backup advanced`  | Restore + decryption + agent config (`details`, `delete`, `restore`, `auto-generate`, `list-agents`, `get-config`, `update-config`, `can-decrypt`). |
| `calendar-ws`      | Calendar event CRUD via WebSocket (different shape from REST `calendar` group). |
| `network`          | Network adapters, internal/external/cloud URL config. |
| `frontend`         | Per-user frontend data + template preview. |
| `state-stream`     | Live WS event firehose (`events`, `state-changed`, `trigger`, `collect`). |
| `history-ext`      | Long-history fallback path — recorder states → long-term stats; `with-stats-fallback`, `retention-estimate`, `stats-to-samples`. |
| `history-logbook`  | WS `history/history_during_period` — bypasses the 24h-only REST gotcha that bites multi-day walks. |
| `helper-preview`   | UI preview-flow dispatch for template/threshold/derivative helpers. |
| `diagnostics download` | Unified diagnostics download (integration or device via `--device-id`). |
| `trace-debug`      | Trace introspection (`list`, `get`, `contexts`). |
| `trace-debugger`   | Live breakpoint debugger for running automations/scripts. |
| `lovelace layout-lint` | Read-only layout audit (sections fit, columns add up, etc). |
| `lovelace section <hero/spacer/divider/with-options>` | Pre-baked section builders. |
| `lovelace view <build-sections/build-masonry/build-panel/build-sidebar/…>` | View-shape builders + `summaries`, `set-max-columns`, `set-visibility`. |
| `energy <validate/solar-forecast/fossil-consumption/save-prefs-structured>` | Long-term energy admin. |
| `statistics <adjust-sum/change-unit/validate/import/update-issue/update-stored-metadata>` | Statistics admin CRUD. |
| `entity <get-many/list-for-display/remove/subscribe-config-entries/integration-setup-info/statistic-during-period>` | Registry extras. |
| `state delete <entity_id>` | Tear out a state-machine entry (registry untouched). |
| `tag create/delete` | Full tag CRUD (was list/find/update only). |
| **New in v1.48 — script-engine primitives** | |
| `action`           | `run` (WS `execute_script` — ad-hoc action sequence through HA's script engine: traced, gets a context, can return a `response_variable`, creates no `script.*` entity; `--sequence`/`--sequence-file` or `--service light.turn_on -t entity_id=… -d k=v` shorthand; `--var k=v`; `--dry-run` prints the WS payload), `validate` (WS `validate_config` — `--triggers`/`--conditions`/`--actions` (+ `-file` variants), each answered `{valid, error}`), `validate-automation <file>` / `validate-script <file>` (whole config; legacy singular `trigger:`/`condition:`/`action:` keys auto-upgraded; **exits non-zero when invalid** so it chains with `&&`), `test-condition` (WS `test_condition` against live state; JSON list evaluates per-item error-tolerantly; `--exit-code` makes false → exit 1). |
| `entity source`    | WS `entity/source` — which integration actually supplies an entity. `entity source` (full map), `entity source <entity_id>` (`{loaded, domain}`), `--by-integration` / `-i <domain>` to group/filter. Registry entry with no source = strong orphan signal. |

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

### Get the pixels: camera stills, stream frames, cover art (v1.51+)

```bash
# One still from a camera
cli-anything-homeassistant camera snapshot camera.front_door /tmp/front.jpg --overwrite

# Rescale: --width and --height MUST be given together. HA only rescales when
# both are present AND the camera returns JPEG; `resized` reports whether it
# actually happened, so never assume it did.
cli-anything-homeassistant --json camera snapshot camera.front_door /tmp/s.jpg \
    --width 640 --height 480 | jq .resized

# N distinct frames off the MJPEG stream. The stream never ends, so ALWAYS
# bound it: --frames is the budget and --timeout is the deadline. --interval
# makes HA compose the stream from stills (>= 0.5s) instead of using the
# camera's native MJPEG, which not every platform has (a 502 says so).
cli-anything-homeassistant --json camera capture camera.front_door /tmp/frames \
    --frames 5 --interval 1.0 --timeout 30 | jq '{frames, duplicates_skipped, complete}'

# Image entities stream too, but with no interval — HA pushes on change. A
# static entity gives ONE frame and reports complete:false at the deadline.
cli-anything-homeassistant --json image capture image.doorbell /tmp/frames --frames 3

# A URL something without an Auth header can fetch (browser, curl, notification)
cli-anything-homeassistant --json camera proxy-url camera.front_door --expires 300 | jq -r .url

# Cover art for what's playing; or a thumbnail from the browse tree, which is
# the only way to get those bytes (--content-type and --content-id together).
cli-anything-homeassistant media-player artwork media_player.lounge /tmp/art.jpg
cli-anything-homeassistant media-player artwork media_player.lounge /tmp/t.jpg \
    --content-type album --content-id 'library/albums/17'
```

Failure modes worth knowing, because HA answers all of them with an empty body:
`503` = **the camera is off** (`camera turn-on <id>`), `502` = the platform has
no MJPEG stream (use `--interval`), `500` = no image/artwork available, `403` =
no credentials reached HA (a bad `--signed` URL), `404` = no such entity. The
CLI translates each of these into a sentence naming the remedy.

### Author an automation without shipping a broken one

```bash
# 1. Validate the config file first — non-zero exit + which block failed
cli-anything-homeassistant action validate-automation morning.json

# 2. Do its conditions hold right now?
cli-anything-homeassistant action test-condition \
  --condition '{"condition":"state","entity_id":"sun.sun","state":"below_horizon"}' \
  --exit-code

# 3. Dry-run just the action block (traced by HA, no entity created)
cli-anything-homeassistant --json action run --sequence-file morning-actions.json

# 4. Chain validate → save so a bad config can never land
cli-anything-homeassistant action validate-automation morning.json \
  && cli-anything-homeassistant automation save automation.morning morning.json --yes
```

### Run one action with a response (what `service call` can't do)

```bash
cli-anything-homeassistant --json action run \
  --service calendar.get_events -t entity_id=calendar.home \
  -d 'duration={"hours":24}' --response-variable agenda | jq '.response'
```

### Entity provenance / orphan hunting

```bash
# Which integration provides it?
cli-anything-homeassistant --json entity source light.kitchen
# {"entity_id": "light.kitchen", "loaded": true, "domain": "hue"}

# Entity count per integration (biggest offenders first)
cli-anything-homeassistant --json entity source --by-integration \
  | jq 'map_values(length) | to_entries | sort_by(-.value) | .[:10]'

# Registry says it exists but nothing supplies it → orphan
cli-anything-homeassistant --json entity source sensor.suspect | jq '.loaded'
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


## What a target actually hits (v1.49.0+)

```bash
# What would this target really reach — and what resolves to nothing?
cli-anything-homeassistant --json target extract --area-id kitchen \\
  | jq '{entity_count, missing_areas, missing_labels}'
cli-anything-homeassistant target services --entity-id media_player.lounge
cli-anything-homeassistant target slugify 'Living Room — Lamp #2'
```

`target extract` defaults `--no-expand-group`; the three `*_for_target`
commands default to `--expand-group`. That asymmetry is HA's own.

For "is this config valid" and "which integration supplies this entity", use
the `action` group and `entity source` — same authoring loop, already there.

## Bytes in and out (v1.49.0+)

```bash
cli-anything-homeassistant backup agents                     # which agent holds it
cli-anything-homeassistant --timeout 600 backup download <id> ./ --agent-id backup.local
cli-anything-homeassistant --timeout 600 backup upload ./backup.tar --agent-id backup.local

cli-anything-homeassistant file upload ./client.pem          # -> file_id for a config flow
cli-anything-homeassistant media upload ./clip.mp4 --target 'media-source://media_source/.'
cli-anything-homeassistant image upload ./avatar.png
cli-anything-homeassistant tts get-url "the back door is open" --engine-id tts.piper
cli-anything-homeassistant intent handle HassTurnOn --slot name=desk --slot domain=light
```

- `--agent-id` is REQUIRED on both backup commands and repeatable on upload.
  HA answers a missing one with a **bare 400 and no body**.
- A big transfer needs a bigger `--timeout`; otherwise the failure looks like a
  connection problem.
- `media upload` only accepts **image/ video/ audio/**. HA answers a bare 400
  for anything else and logs the reason server-side only, so the CLI refuses
  locally and names the cause.
- `media search` on the ROOT is an error (`search_not_supported`), not an empty
  result. Scope it: `--scope media-source://media_source`.

## Preferences that explain odd behaviour (v1.49.0+)

```bash
cli-anything-homeassistant labs list --enabled-only   # a preview feature changes behaviour
cli-anything-homeassistant prefs ai-task              # which model an ai_task job reaches
cli-anything-homeassistant prefs http                 # stable vs PENDING (unpromoted) config
cli-anything-homeassistant prefs recorded sensor.x    # is there any history to look for?
cli-anything-homeassistant prefs auto-entity-id light.a   # what HA WOULD call it
cli-anything-homeassistant entity convertible-units --device-class temperature
cli-anything-homeassistant device-links split-for <device_id>
```

**`prefs recorded` first when a history looks empty.** `recording_disabled_by`
non-null means there is no history and no long-term statistics — which every
history command here reports as an empty result indistinguishable from a quiet
entity.

**`device-links split-for` before a device-scoped call.** A device-scoped
target applies to ONE registry entry; where HA has split a device, the
`siblings` field lists the ones your call would miss.

## Pitfalls

These are paid in lost time. Read them before mutating anything.

- **A 500 from `tts get-url` means the ENGINE DOES NOT SUPPORT THAT LANGUAGE**,
  and HA's body says nothing at all. Measured across four engines: omitting
  `--language` works on every one, while the engines disagree on the string —
  `tts.piper` declares `en_GB`, the Wyoming engines declare `en-GB`, and
  `tts.google_ai_tts` declares neither. `tts get-url` checks the engine's own
  list first; `tts list` shows it (it comes from `tts/engine/list`, NOT the
  entity attributes, which report an empty list).
- **`media search` on the ROOT is an error** (`search_not_supported`), not an
  empty result. Scope it: `--scope media-source://media_source`.
- **`camera snapshot --width` alone does NOTHING and HA will not say so.**
  Rescaling happens only when width AND height are both present and the
  camera returns JPEG; otherwise the size argument is passed to the platform,
  ignored, and you get a full-size image with a 200. The CLI refuses one
  without the other, and `resized` in the JSON is the honest answer.
- **Never point `camera capture` / `image capture` at an unbounded run.**
  Both MJPEG views stream forever by design — `--frames` and `--timeout` are
  not optional tuning, they are the only things that end the request. Check
  `complete` in the output: `false` means the deadline hit first, which for a
  static entity is the normal answer, not a fault.
- **A camera that is switched off answers 503**, not 404 and not a blank
  image. If a snapshot "fails on the server", check `camera turn-on` first.
- **`media upload` only accepts image/ video/ audio/.** HA answers a bare 400
  for anything else and logs the reason server-side only.
- **Token = full admin.** Treat `~/.config/cli-anything-homeassistant.json`
  as a secret.
- **`state set` is a manual override**, not a service call. It writes a state
  directly into HA's state machine without going through the entity's normal
  logic. For controlling devices, always use `service call <domain>.<svc>` or
  a typed shortcut group.
- **`state delete`** (v1.39.0+) tears an entity out of the state machine but
  leaves the registry entry intact. Use `entity delete` for the registry
  side; use `state delete` for stale REST/template-only entities only.
- **WebSocket `subscribe` commands keep an open connection** — in scripts,
  always pass `--limit` and/or `--timeout` so the call returns. WS
  subscriptions now send `unsubscribe_events` on exit (v1.39.0+) so
  Ctrl-C'd long-runners don't leave the server tracking stale ids.
- **Mutating commands accept `--dry-run`** (where it makes sense). The dry
  run never touches HA. Use it for any "I'm going to bulk-rename N entities"
  command. Newly added in v1.39: `automation save`, `script save`,
  `lovelace card insert/delete` all carry `--dry-run` (diff against live).
- **Destructive verbs require `--yes` when scripted.** Affects (v1.39+):
  `automation save`, `script save`, `lovelace config save`, `shopping-list
  remove`/`clear-completed`, `todo remove`/`clear-completed`, `system
  reload-core-config`/`reload-all`, `state delete`, `tag delete`,
  `alarmo sensor-remove`/`sensor-update`/`area-delete`/`config-set`. Without
  `--yes` and without a TTY, the command aborts rather than blocking.
- **`automation delete <entity_id>` / `script delete <entity_id>`** (v1.46.3+)
  hit HA's UI-managed-config DELETE endpoints directly (`DELETE
  config/automation/config/{id}` / `DELETE config/script/config/{object_id}`)
  — the correct way to remove an automation/script, as opposed to the
  generic `entity remove` (which only tears the registry entry out, not the
  underlying automation/script config). Both are confirmation-gated like the
  other destructive verbs above; pass `--yes` when scripted.
- **`action run` is not `service call`.** `action run` goes through HA's
  *script engine* (WS `execute_script`, admin-only): the run is traced, gets a
  script context, honours full script syntax (`choose`/`repeat`/`delay`/
  `wait_template`/`stop`) and can collect a `response_variable`. `service call`
  is a single REST POST. Use `action run` when you need sequencing, variables
  or a response; use `service call` for one flat call. Both mutate for real —
  `action run --dry-run` prints the WS payload without executing.
- **Validate before you save.** `automation save` / `script save` will happily
  write a config HA then refuses to load (it only shows up later in the error
  log). `action validate-automation <file>` / `action validate-script <file>`
  run HA's own validator and **exit non-zero** on failure, so always chain:
  `action validate-automation a.json && automation save automation.x a.json --yes`.
  Note HA validates *shape and referenced trigger/condition/action platforms* —
  a service that doesn't exist yet still passes.
- **`entity source` only lists entities whose integration is loaded.** That's
  the point: a registry entry (`entity list`) with no `entity source` record is
  a strong orphan signal, and complements `entity orphans` / `entity restored`
  before an `entity prune`. Don't read a missing source as "entity deleted".
- **`alarmo` mutates a home alarm — treat with care.** `sensor-remove` and
  `sensor-update --no-trigger-unavailable` *weaken* the alarm (the sensor no
  longer triggers or blocks arming). Both support `--dry-run` (prints the exact
  REST body, sends nothing) and print the sensor's current config before a TTY
  confirm, so the change is diffable/reversible. REST writes go to
  `/api/alarmo/*`; a common failure is arming being blocked by a stale/ghost
  sensor left `unavailable` — remove it with `alarmo sensor-remove` rather than
  force-bypassing blindly.
- **Lovelace dashboards** — prefer `lovelace view get` / `view set` /
  `section ...` over re-pushing the full config. The full-config write is
  destructive and easy to corrupt. **Card writes auto-validate**
  (v1.39.0+) via `lovelace_card_validate`; broken-config errors abort the
  write. Pass `--no-validate` to override (e.g. when the HACS plugin will
  be installed later).
- **Active calibration is noise-gated (v1.40+), not noise-proof.**
  `powercalc calibrate` / `calibrate-template` reject a measurement window if
  the whole-home meter's spread exceeds `--max-variance-w` (default 50 W) OR
  another tracked device toggles during it, retrying `--max-retries` times
  then excluding it. A noisy run won't auto-apply; check `noisy` /
  `excluded_steps` in the output. Still, calibrating a **small load against a
  busy whole-home meter is marginal** — a ~15 W LED strip lives below the
  noise floor of a 1 kW+ house. For small loads, point `--smart-meter` at a
  per-circuit CT clamp / smart plug instead. Set `--max-variance-w 0` to
  disable the gate.
- **Powercalc on-state vs off-state power are two different commands.**
  `powercalc set-power <entry> <W>` sets the ON-state fixed power (the `fixed`
  step). The OFF-state standby is a separate field on the `basic_options`
  step — use `powercalc set-standby <entry> <W>` (v1.41+). So "1 W off / 7.4 W
  on" is `set-power 7.4` + `set-standby 1.0`, not a template. `set-standby`
  re-sends the source `entity_id` so it can't blank the entry. Read current
  config (mode, source, configured power/standby) with `powercalc show
  <entry>` — the config-entry list doesn't expose powercalc options. Both
  `set-power` and `set-template` auto-reload the entry so the change lands.
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
