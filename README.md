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

External dep: a running Home Assistant. A long-lived access token if you have
one; if you don't, `auth login` will get you one — and if the instance is so
new it has no accounts yet, `onboarding provision` will create one (see below).

## First-time setup

```bash
cli-anything-homeassistant \
  --url http://homeassistant.local:8123 \
  --token "<long-lived-token>" \
  config save
```

### Brand-new Home Assistant, no account at all? (v1.53+)

`onboarding provision` creates the first account and hands back a working
token, in one call — the step before `auth login` is even possible:

```bash
cli-anything-homeassistant --url http://homeassistant.local:8123 \
  onboarding provision --name Agent --username agent --save
```

Onboarding steps are **one-shot and commit before they can fail**: Home
Assistant marks each done at the top of its handler, so a step that errors is
still finished and retrying it answers "already done". Every command here
reports `ok` and `committed` separately and nothing retries. `provision` runs
the fallible steps last, so a refused one never costs you the token.

Also: `onboarding status` (which steps are done — no token needed),
`onboarding installation-type` (readable *only* before the first step),
`onboarding create-user`, `onboarding finish-step`, `onboarding
finish-integration`.

### No token yet? (v1.52+)

`auth login` drives Home Assistant's IndieAuth flow — it needs no existing
credential, because getting one is the point:

```bash
# Username + password → access token, written straight into the profile.
cli-anything-homeassistant --url http://homeassistant.local:8123 \
  auth login --username agent --save          # prompts for the password, hidden

# That token expires in 30 minutes. Trade it for a durable one:
cli-anything-homeassistant auth tokens create my-agent
cli-anything-homeassistant config set --token "<the long-lived token>"
```

Useful companions: `auth providers` (what this instance accepts, no token
needed), `auth refresh --refresh-token …` (new access token; pass the SAME
`--client-id` `login` reported), `auth revoke --token … --verify`, and
`auth login-flow start/step/abort` when a provider asks for fields `login`
doesn't know about. `auth login --mfa-code` handles two-factor accounts.

> A wrong password counts toward Home Assistant's IP-ban tracker, so don't
> script a retry loop around `auth login`.

Profile is stored at `~/.config/cli-anything-homeassistant.json` (mode 0600).
Per-key env overrides: `HASS_URL`, `HASS_TOKEN`, `HASS_VERIFY_SSL` (`0` to
disable), `HASS_TIMEOUT` (seconds).

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
| `backup` | Snapshot list / create / show / delete / restore (HA 2024.6+) + **`download` / `upload`** — the tarball off the box and back, which is the only half that matters for disaster recovery |
| `statistics` | Long-term recorder stats: list / metadata / **series** (chart data) / update-metadata / clear |
| `diagnostics` | Per-integration + per-device JSON downloads (same as UI's "Download diagnostics") |
| `blueprint` | List / import / save / delete / substitute (dry-run render) |
| `assist` | Send text to HA's conversation pipeline; list Assist pipelines; **run one end to end** (`assist run`) |
| `updates` | List, install, skip, clear-skipped on `update.*` entities |
| `logger` | Runtime log-level control without restart |
| `group` | List members of light/switch/sensor groups |
| `auth` | Users, long-lived tokens, whoami — plus **`login` (username + password → token, no existing token needed)**, `providers`, `refresh`, `revoke`, `exchange-code`, `link-user`, `login-flow start/step/abort`, `oauth-metadata` |
| `onboarding` | **Set up a brand-new instance**: `provision` (nothing → owner account → access token in one call), `status`, `installation-type`, `create-user`, `finish-step`, `finish-integration` |
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
| `camera` | `camera.*` capabilities, HLS stream URL, prefs, WebRTC client config, **stills and stream frames** (`snapshot` / `capture` / `proxy-url`) |
| `device-automation` | List a device's available triggers, conditions, actions — what the HA UI's automation editor shows |
| `assist agents` / `sentences` / `debug` / `satellites` / `languages` | Conversation pipeline introspection + sentence-matching debugger |
| `assist run` | **Run a pipeline end to end** (WS `assist_pipeline/run`) — the pipeline's own STT → agent → TTS, not just the conversation agent. `--start-stage stt --audio cmd.wav` transcribes a 16-bit mono WAV (streamed as binary frames) and acts on it; `--save-tts` writes the spoken reply to a file; `--stream` tails events live |
| `assist-satellite` | `assist_satellite.*` — current config, set wake words, test connection |
| `mobile-app` | Companion app push delivery receipts |
| `media` | media_source browse / resolve to URL / local file remove |
| `light` | `light.*` — `on` (brightness/kelvin/rgb/effect/transition) / `off` / `toggle` |
| `media-player` | `media_player.*` — play/pause/stop/next/prev, volume/mute, source, play-media, shuffle, repeat, join/unjoin, `artwork` (cover art / browse-media thumbnails) |
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
| `zone` | Storage zone registry CRUD (`config/zone/*` WS) — `list`/`state-list`/`find`/`create`/`update`/`delete` + `entities <zone>` (who is inside right now). YAML-declared zones are read-only and surface via `state-list`. |
| `webhook` | Webhook discovery (aggregates `webhook/list` WS, automation triggers, and mobile_app registrations) + `trigger <id>` (POST/PUT/GET/HEAD with registered-id guard) + `generate-id` + cloudhook CRUD via `cloud/cloudhook/*` |
| `image` | `image.*` entity domain — `list`/`show`/`snapshot <entity_id> <path>` (signed via `auth/sign_path` or direct auth) + `proxy-url` (signed URL minted on demand) + `subscribe` for update events |
| `action` | Script-engine primitives — `run` an ad-hoc action sequence (WS `execute_script`, no `script.*` entity needed), `validate` trigger/condition/action blocks, `validate-automation`/`validate-script` a whole config file (exit non-zero when invalid), `test-condition` against live state (`--exit-code` for shell chaining) |
| `entity source` | Which integration actually supplies an entity (WS `entity/source`) — provenance, `--by-integration` to group, and a strong orphan signal when a registry entry has no source |
| `target` | **What a target actually hits** — `extract` (the entities a service call would reach, plus the areas/labels HA cannot resolve and would silently ignore), `services`/`triggers`/`conditions` (what can be done with it), `slugify` |
| `labs` | HA 2026 preview features — `list` (`--enabled-only` is the one that explains odd behaviour), `show`, `set` with an explicit `--create-backup` because a preview feature can migrate storage |
| `prefs` | Instance preferences with outsized effects — `ai-task` (which model a job reaches), `http` (stable vs **pending** config; a change that "did not take" is usually unpromoted), `entity-naming` + `auto-entity-id` (what HA WOULD call an entity — run before renaming), `recorded` (`recording_disabled_by` — the reason a history is empty rather than quiet) |
| `device-links` | Composite splits and linked devices — topology the flat registry cannot show. A device-scoped target applies to ONE registry entry, so a split device is a silent partial hit |
| `intent` | Fire an intent by name, skipping the sentence parser — what separates a sentence-match failure from a handler failure |
| `file` | `upload` a file to HA's staging area and get the `file_id` a config flow wants |
| `supervisor` | **The other half of a Home Assistant OS / Supervised install** (v1.52+) — add-ons, host, OS, network. `available`/`status` (versions side by side, what is stale), `info`, `component`, `stats`, `resolution`, `logs`/`boots` (journals over the HTTP proxy), `watch` (progress events), `api` (any Supervisor endpoint) + `addon list/info/start/stop/restart/rebuild/update/options/logs`. Writes are dry-run until `--apply`; `addon options` merges and validates because the POST REPLACES the whole options object |
| `profiler` | Pass-through to the `profiler` integration's services: `start` (cProfile), `memory` (memray), `dump-log-objects --type Class`, `log-thread-frames`/`log-current-tasks`/`log-event-loop-scheduled`/`log-events`, `lru-stats`, `set-asyncio-debug`. `status` is a cheap "is the integration even loaded" probe. |
| `zwave` | **The `zwave_js` integration's own WebSocket API** (v1.54) — what the Z-Wave configuration panel drives. `available` (a read: 'not loaded' is an answer, not an error), `nodes`, `status`, per-node `node` / `node-metadata` / `node-alerts` / `capabilities` / `config` / `config-set` (int, `0x…` hex or JSON bitmask), `refresh` / `refresh-values` / `rebuild-routes` / `begin-rebuild-routes` / `stop-rebuild-routes` / `remove-failed` / `hard-reset`, driver `log-config` / `log-config-set`, telemetry `data-collection` / `data-collection-opt`, device-database `config-updates` / `config-updates-install`, `integration-settings`, and the domain's services: `ping`, `lock-usercode` / `lock-clear-usercode` / `lock-configuration`. Node-scoped commands accept an entity id and resolve the device via the registry; an instance with no Z-Wave controller gets every command's refusal as one sentence instead of `unknown_command` |

## Quick examples

```bash
# What would "turn off the kitchen" really hit — and what silently resolves to nothing?
cli-anything-homeassistant --json target extract --area-id kitchen \\
  | jq '{entity_count, missing_areas, missing_labels}'

# Get a backup OFF the box (the half `create` never did)
cli-anything-homeassistant backup agents            # which agent holds it
cli-anything-homeassistant --timeout 600 backup download <id> ./ --agent-id backup.local

# Why is this entity's history empty — quiet, or not recorded at all?
cli-anything-homeassistant prefs recorded sensor.something

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

# Does the voice pipeline I just wired up actually work, end to end?
cli-anything-homeassistant --json assist run "turn on the kitchen light" \
  | jq '{completed, speech, error}'

# Transcribe a recording and let the pipeline act on it, then keep the reply
cli-anything-homeassistant --json assist run \
  --start-stage stt --audio command.wav --save-tts reply.mp3 \
  | jq '{stt_text, speech, saved_tts}'

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

# Author an automation without writing a broken one (v1.48+)
# 1. validate the config file — exits non-zero (and says which block) if bad
cli-anything-homeassistant action validate-automation morning.json
# 2. check the conditions actually hold right now
cli-anything-homeassistant action test-condition \
    --condition '{"condition":"state","entity_id":"sun.sun","state":"below_horizon"}' \
    --exit-code
# 3. dry-run the action block through HA's script engine (traced, no entity created)
cli-anything-homeassistant --json action run --sequence-file morning-actions.json
# 4. only now write it
cli-anything-homeassistant action validate-automation morning.json \
  && cli-anything-homeassistant automation save automation.morning morning.json --yes

# One-off action with a response variable (things `service call` can't do:
# script context, tracing, response collection)
cli-anything-homeassistant --json action run \
    --service calendar.get_events -t entity_id=calendar.home \
    -d 'duration={"hours":24}' --response-variable agenda

# Who actually provides this entity? (and what's an orphan)
cli-anything-homeassistant --json entity source light.kitchen
cli-anything-homeassistant --json entity source --by-integration | jq 'map_values(length)'

# Get the BYTES an entity is showing, not a description of them (v1.51+)
# A still from a camera. --width and --height must be given TOGETHER: HA only
# rescales when both are present, and only for JPEG cameras (`resized` in the
# JSON says whether it actually happened).
cli-anything-homeassistant camera snapshot camera.front_door front.jpg
cli-anything-homeassistant --json camera snapshot camera.front_door small.jpg \
    --width 640 --height 480 | jq .resized

# Frames off the MJPEG stream. The stream NEVER ENDS, so a capture is bounded
# by both a frame budget and a deadline. --interval makes HA compose the
# stream from stills instead of using the camera's native MJPEG (which not
# every platform has). HA deliberately sends the first frame twice; duplicates
# are collapsed and counted.
cli-anything-homeassistant --json camera capture camera.front_door ./frames \
    --frames 5 --interval 1.0 --timeout 30 | jq '.frames, .duplicates_skipped'

# Frames from an image entity (no interval — HA pushes on change; a static
# entity yields one frame and reports complete:false at the timeout)
cli-anything-homeassistant --json image capture image.doorbell ./frames --frames 3

# A URL a browser or curl can fetch with no Authorization header
cli-anything-homeassistant --json camera proxy-url camera.front_door --expires 300 | jq -r .url

# Cover art for what's playing, or a thumbnail from the browse tree
cli-anything-homeassistant media-player artwork media_player.lounge art.jpg
cli-anything-homeassistant media-player artwork media_player.lounge thumb.jpg \
    --content-type album --content-id 'library/albums/17'

# The Supervisor: add-ons, host and OS (v1.52+)
# There is no Supervisor on a Core or Container install — `available` says so
# as an ANSWER (exit 0, `available: false`), so scripts branch on it instead of
# on the text of an error.
cli-anything-homeassistant --json supervisor available | jq .available

# Is anything out of date? Supervisor, Core, host and OS in one read; each part
# degrades on its own, so a Supervised box with no HA OS under it still answers.
cli-anything-homeassistant --json supervisor status | jq '.updates_available'

# Add-ons. `list` is what is INSTALLED (the store catalogue is /store/addons,
# via `supervisor api`). Options are withheld from `info` unless --reveal:
# that is where an add-on's database password lives.
cli-anything-homeassistant --json supervisor addon list --updates-only
cli-anything-homeassistant --json supervisor addon info core_ssh | jq .options_keys

# Every write is a dry run first. It reports the state the add-on is in NOW,
# including when the answer is "already stopped, this would do nothing".
cli-anything-homeassistant --json supervisor addon restart core_ssh
cli-anything-homeassistant --json supervisor addon restart core_ssh --apply

# `POST /addons/<slug>/options` REPLACES the options object: send one key and
# every other key silently reverts to its default. So the current options are
# read, the change is merged in, and Supervisor is asked whether the RESULT is
# legal (`/options/validate`, which writes nothing) before anything is sent.
cli-anything-homeassistant --json supervisor addon options core_ssh \
    --set 'packages=["git","curl"]' | jq '.keys_preserved, .valid'
cli-anything-homeassistant --json supervisor addon options core_ssh \
    --set 'packages=["git","curl"]' --apply

# Logs go over the HTTP proxy, not the websocket one — these endpoints answer
# plain text and the websocket path parses every body as JSON. --lines rides a
# `Range: entries=:-N:` header; there is no query parameter for it.
cli-anything-homeassistant supervisor logs core --lines 200 --text
cli-anything-homeassistant supervisor addon logs core_ssh --lines 50 --text
cli-anything-homeassistant --json supervisor boots        # then --boot -1

# Anything this group does not name. The path must be absolute and carry no
# query string: HA compares it against its own normalisation and refuses any
# difference with an EMPTY error message, so the check is done here first.
cli-anything-homeassistant --json supervisor api /store/addons
cli-anything-homeassistant --json supervisor api /core/update \
    --method post --timeout 600     # the default is TEN seconds
```

```bash
# The Z-Wave JS integration (v1.54+) — the API the Z-Wave panel itself drives
# First question: is there even a Z-Wave controller here? `available` is a
# READ — 'not loaded' is an answer (exit 0), so scripts branch on it.
cli-anything-homeassistant --json zwave available | jq .available

# Inventory: every node, with the node id pulled out of the device identifiers
cli-anything-homeassistant --json zwave nodes --pattern door

# A node's state, its alerts, and every config parameter with values.
# Node-scoped commands take a device id OR any entity id on that device.
cli-anything-homeassistant --json zwave node lock.front_door
cli-anything-homeassistant --json zwave node-alerts lock.front_door
cli-anything-homeassistant --json zwave config lock.front_door

# Write a config parameter: plain, 0x-hex or a JSON bitmask object
cli-anything-homeassistant zwave config-set lock.front_door 68 1
cli-anything-homeassistant zwave config-set dev1 112 0x2a --property-key 2
cli-anything-homeassistant zwave config-set dev1 9 '{"1": true, "4": true}'

# Maintenance: refresh a node, rebuild its routes, drop a failed node.
# The network-wide rebuild and the controller factory reset are separate,
# explicitly gated commands — hard-reset REMOVES every node from the network.
cli-anything-homeassistant zwave refresh lock.front_door
cli-anything-homeassistant zwave begin-rebuild-routes <ENTRY_ID>
cli-anything-homeassistant zwave hard-reset <ENTRY_ID>       # asks twice

# Locks: program / clear a user code slot, set the relock behaviour
cli-anything-homeassistant zwave lock-usercode lock.front 3 1234
cli-anything-homeassistant zwave lock-configuration lock.front \
    --operation-type timed --timeout 30

# Diagnose an unreachable device: is it the mesh or the lock?
cli-anything-homeassistant --json zwave ping sensor.front_door_battery
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
│   ├── system.py, references.py, recorder.py, template.py
│   ├── media_proxy.py   # binary GETs: camera/image stills + MJPEG, artwork
│   └── supervisor.py    # the Supervisor: add-ons, host, OS — via the
│                        # `supervisor/api` WS proxy, and `/api/hassio/…`
│                        # for the logs, which answer plain text
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

Two suites deliberately do NOT use a fake, because a fixture written by the
author of the parser encodes the same assumption twice and agrees with itself:
`tests/test_ws_run_events.py` runs the websocket client against a server that
implements HA's protocol from the other side, and
`tests/test_media_proxy_stream.py` parses multipart frames produced by Home
Assistant's *own* `async_get_still_stream` over a real socket.

The `supervisor` suite is the same idea from the other direction. The instance
the e2e tests boot is a **Core** install, so `supervisor/api` is genuinely
unregistered and `/api/hassio/…` is genuinely unrouted — the two refusals this
group has to turn into sentences are produced by a real Home Assistant rather
than by a fake told to produce them. The `Range: entries=:-N:` header that
carries `--lines` is asserted against a real HTTP server, because a header that
never left the process looks identical to one the server ignored.

## Sibling projects

This is part of a small `cli-anything-*` family of harnesses for connected
devices/services I run at home:

- [`cli-anything-zigbee2mqtt`](#) — full bridge + device control over MQTT
- [`cli-anything-espresense`](#) — BLE presence rooms + node config

All three share the same connection-profile pattern, JSON output, and REPL.

## License

MIT — see [LICENSE](./LICENSE).
