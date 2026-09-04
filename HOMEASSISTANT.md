# Home Assistant Agent Harness — SOP

## Overview

`cli-anything-homeassistant` is a CLI harness for [Home Assistant](https://www.home-assistant.io/),
the open-source home automation platform. It exposes Home Assistant's REST and
WebSocket APIs through a stateless `click`-based CLI plus an interactive REPL,
so AI agents and shell scripts can read and control a running Home Assistant
instance without a browser.

## Backend Engine

Home Assistant runs as a long-lived Python service (typically on port `8123`)
that exposes:

- A **REST API** at `/api/...` used for states, services, events, templates,
  config, components, and the error log.
- A **WebSocket API** at `/api/websocket` used for the registry endpoints
  (areas, devices, entities, config entries, system health) and for live
  state-change subscriptions.

The harness is a **thin client over those APIs**. Home Assistant itself is a
hard dependency: the CLI does not run automation logic locally, render
templates locally, or fake registry data. Every command resolves to one or
more API calls against a running HA instance.

### Authentication

Almost every request carries a **Long-Lived Access Token** (Bearer):

1. Start Home Assistant.
2. Sign in to the UI, open your profile (bottom-left avatar).
3. Scroll to the bottom and create a Long-Lived Access Token.
4. Save it to the harness with `cli-anything-homeassistant config set --token <token>`
   or expose it via the `HASS_TOKEN` environment variable.

**Or get one without the UI (v1.52.0+).** The `auth login` / `providers` /
`login-flow` / `refresh` / `revoke` / `oauth-metadata` commands need no
existing token — they wrap the views Home Assistant mounts at the server root,
outside `/api/`:

```bash
HASS_URL=http://ha.local:8123 cli-anything-homeassistant \
  auth login --username agent --save     # password prompted, hidden
cli-anything-homeassistant auth tokens create my-agent   # make it durable
```

The access token from `auth login` lasts `expires_in` seconds (1800 by
default); `auth tokens create` converts it into a long-lived one. See
`core/auth_login.py` for the encoding and status-code traps — the two halves of
the flow disagree about body encoding, and a wrong password is an HTTP 200.

### Reference Endpoints

Root-mounted (NOT under `/api/`, so `client.get()`/`post()` cannot reach them —
they go through `client.root_request()`):

| Endpoint                                       | Purpose                                  |
|------------------------------------------------|------------------------------------------|
| `GET /.well-known/oauth-authorization-server`   | RFC 8414 metadata (no auth)              |
| `GET /auth/providers`                           | Configured auth providers (no auth)      |
| `POST /auth/login_flow`                         | Open a login flow — **JSON body**        |
| `POST|DELETE /auth/login_flow/{flow_id}`        | Advance / abort a flow — **JSON body**   |
| `POST /auth/token`                              | Code or refresh grant — **FORM body**    |
| `POST /auth/revoke`                             | Revoke a refresh token — **FORM body**   |
| `POST /auth/link_user`                          | Link a credential — JSON, **needs auth** |


| Endpoint                              | Purpose                                  |
|---------------------------------------|------------------------------------------|
| `GET /api/`                           | Root status (auth check)                 |
| `GET /api/config`                     | Server config (location, version, etc.)  |
| `GET /api/core/state`                 | Core state (running/stopped/etc.)        |
| `GET /api/states`                     | All entity states                        |
| `GET /api/states/<entity_id>`         | Single entity state                      |
| `POST /api/states/<entity_id>`        | Set state (manual override)              |
| `GET /api/services`                   | All services grouped by domain           |
| `POST /api/services/<domain>/<svc>`   | Call a service                           |
| `GET /api/events`                     | Event listener counts                    |
| `POST /api/events/<event>`            | Fire an event                            |
| `POST /api/template`                  | Render a Jinja template                  |
| `GET /api/components`                 | Loaded components                        |
| `GET /api/error_log`                  | Plain-text error log                     |
| `GET /api/history/period[/<ts>]`      | Historical state changes                 |
| `GET /api/logbook[/<ts>]`             | Logbook entries                          |
| `WS /api/websocket`                   | All registry/system_health/subscriptions |
| `GET /api/backup/download/<id>`       | Backup tarball (needs `?agent_id=`)      |
| `POST /api/backup/upload`             | Push a backup back (`?agent_id=`, repeatable) |
| `POST /api/file_upload`               | Stage a file, returns `file_id`          |
| `POST /api/media_source/local_source/upload` | Into the media library (image/video/audio ONLY) |
| `GET /api/camera_proxy/<entity_id>`   | Camera still (`?width=&height=`, JPEG-only rescale) |
| `GET /api/camera_proxy_stream/<entity_id>` | Camera MJPEG stream (`?interval=`, NEVER ends) |
| `GET /api/image_proxy/<entity_id>`    | Image entity still                       |
| `GET /api/image_proxy_stream/<entity_id>` | Image entity still-stream (NEVER ends) |
| `GET /api/media_player_proxy/<entity_id>` | Cover art; `/browse_media/<type>/<id>` for a thumb |
| `POST /api/image/upload`              | image_upload integration                 |
| `POST /api/tts_get_url`               | Synthesise and return a playable URL     |
| `POST /api/intent/handle`             | Fire an intent by name, no sentence parsing |

WebSocket message types used by the harness:

- `auth` (`access_token`)
- `config/area_registry/list`
- `config/device_registry/list`
- `config/entity_registry/list`
- `config_entries/get`
- `system_health/info`
- `subscribe_events`
- `extract_from_target` / `get_{services,triggers,conditions}_for_target` / `slugify`
- `labs/list` / `labs/update`
- `ai_task/preferences/{get,set}` / `http/config`
- `config/entity_registry/settings/{get,update}` / `.../get_automatic_entity_ids`
- `recorder/entity_options/get`
- `config/device_registry/{list_composite_splits,list_linked_devices}`
- `tts/engine/list` / `media_source/search_media` / `media_player/search_media`

**Enumerating the real surface.** HA's source ships inside the container at
`/usr/src/homeassistant`. Diffing what it registers against what this harness
sends is how a refine pass is scoped — see CLAUDE.md for the method and the
false-positive trap in it.
- `execute_script` / `validate_config` / `test_condition` / `entity/source`
  (the script-engine primitives behind the `action` group and `entity source`)

## Data Model

Home Assistant has no project file in the GUI sense — its persistent state is
the running server. The harness keeps a small **connection profile** in
`~/.config/cli-anything-homeassistant.json`:

```json
{
  "url": "http://localhost:8123",
  "token": "<long-lived-token>",
  "verify_ssl": true,
  "timeout": 30
}
```

Environment variables (override file):

- `HASS_URL` (e.g. `http://localhost:8123`)
- `HASS_TOKEN`
- `HASS_VERIFY_SSL` (`0`/`1`)

This makes every CLI invocation idempotent: state lives in HA, not in the
client.

## CLI Architecture

Two interaction modes, sharing the same Click command tree:

- **One-shot** — `cli-anything-homeassistant <group> <cmd> [opts]`
- **Interactive** — `cli-anything-homeassistant` (no args) drops into a REPL
  styled by the shared `ReplSkin`.

Every command supports `--json` for machine-readable output. Errors print to
stderr and return a non-zero exit code.

### Command Groups

| Group        | Purpose                                                             |
|--------------|---------------------------------------------------------------------|
| `config`     | Connection profile (`show`/`set`/`save`/`test`)                     |
| `system`     | Server info (`info`/`config`/`core-state`/`error-log`/`components`) |
| `state`      | Entity states (`list`/`get`/`set`/`delete`)                         |
| `service`    | Services (`list`/`call`)                                            |
| `event`      | Events (`list`/`fire`)                                              |
| `template`   | Render Jinja2 templates (`render`)                                  |
| `area`       | Area registry (WS) (`list`)                                         |
| `device`     | Device registry (WS) (`list`)                                       |
| `entity`     | Entity registry (WS) (`list` + `expose` subgroup)                   |
| `automation` | Automations (`list`/`trigger`/`toggle`/`reload`)                    |
| `script`     | Scripts (`list`/`run`)                                              |
| `domain`     | Helpers per domain (`list`/`turn-on`/`turn-off`/`toggle`)           |
| `history`    | Historical state changes                                            |
| `logbook`    | Logbook entries                                                     |
| `scene`      | `list`/`activate`/`apply`/`create`/`reload` for `scene.*` entities  |
| `weather`    | `list`/`units`/`forecast`/`forecast-subscribe` for `weather.*`      |
| `shopping-list` | Default HA shopping list CRUD (WS-backed)                        |
| `todo`       | `todo.*` lists — CRUD + move + complete shortcut                    |
| `lock`       | `lock.*` shortcuts (`lock`/`unlock`/`open`)                         |
| `alarm`      | `alarm_control_panel.*` arm/disarm shortcuts                        |
| `search`     | `search/related` — find entities/devices/areas tied to an item      |
| `camera`     | `camera.*` — capabilities / stream URL / prefs / WebRTC + `snapshot` / `capture` / `proxy-url` |
| `device-automation` | List a device's available triggers/conditions/actions        |
| `assist-satellite` | `assist_satellite.*` — wake-word config + test-connection     |
| `assist run`  | Run a pipeline END TO END (`assist_pipeline/run`) — its own STT, agent and TTS, not just the conversation agent. `--audio` streams a 16-bit mono WAV as binary frames |
| `mobile-app` | Companion app push delivery receipts                                |
| `media`      | `media_source` browse / resolve / remove                            |
| `category`   | Category registry CRUD (scope-bound tags for automations/scripts/…) |
| `auth` (extensions) | `me`, `sign-path`, refresh token CRUD, full user admin       |
| `auth` (pre-auth)   | `login` (username+password → token, NO existing token needed), `providers`, `refresh`, `revoke`, `exchange-code`, `link-user`, `login-flow start/step/abort`, `oauth-metadata` |
| `logger` (extensions) | WS-side per-component log levels (`info-ws`/`level-get`/`level-set`) |
| `system` (extensions) | manifest / analytics / app-credentials / issue / usb-scan / zha-permit-join / hardware-info / log |
| `light`        | `light.*` ergonomic shortcuts (brightness/kelvin/rgb/effect/transition) |
| `media-player` | `media_player.*` playback + volume + source + play-media + group join/unjoin |
| `climate`      | `climate.*` set-temperature / set-hvac-mode / set-fan-mode / set-preset / set-humidity / set-swing / on / off |
| `cover`        | `cover.*` open/close/stop/toggle + set-position + tilt ops |
| `fan`          | `fan.*` percentage/preset/direction/oscillate + increase/decrease |
| `vacuum`       | `vacuum.*` start/stop/pause/return-to-base/locate/clean-spot/set-fan-speed/send-command |
| `humidifier`   | `humidifier.*` on/off/toggle + set-humidity/set-mode |
| `water-heater` | `water_heater.*` on/off + set-temperature/operation-mode/away-mode |
| `valve`        | `valve.*` open/close/stop/toggle + set-position |
| `lawn-mower`   | `lawn_mower.*` start/pause/dock |
| `siren`        | `siren.*` on (duration/tone/volume) / off / toggle |
| `remote`       | `remote.*` turn-on (activity) + send-command / learn-command / delete-command |
| `number`       | `number.* set` |
| `select`       | `select.* set` / next / previous / first / last |
| `button`       | `button.* press` |
| `text`         | `text.* set` |
| `notify`       | `notify.<service> send` with `--title` / `--target` / `--data` / `--service` |
| `powercalc`    | `list` / `create` / `set-template` / `set-power` / `reload` + nested `group {members,add-members,remove-members,set-members}` — safety wrappers over powercalc's REPLACE-on-write group API and the binary_sensor fixed-mode no-op |
| `entity restored` / `entity orphans` | List entities flagged `restored=true` or referencing missing config entries — strong orphan signal |
| `entity prune` | Bulk-delete registry entries matching `--platform` / `--restored` / `--orphan` / `--disabled-by` / `--entity-id`; dry-run by default, protects user-disabled entries, per-entity error tolerance (proven against the 96.7k-entry UniFi cleanup) |
| `recorder top` | Rank entities by state-change count over `--hours N`; `--domain` to scope on large installs |
| `backup list/show` | Now correctly surface `size_mb` / `agents` / `protected` (previously stuck at null because the fields live per-agent in HA's payload) |
| `powercalc audit` | Passive: smart-meter vs Home Total over a window + ranked sub-group contributions |
| `powercalc calibrate` | Active single-shot for fixed-power devices: baseline → service-on → load → delta, optional `--apply` |
| `powercalc calibrate-template` | Active multi-step for variable devices: walks states, builds piecewise `power_template` |
| `powercalc auto-calibrate` | Passive median-of-transitions from recorder history — fits fixed-power models from real data with no switch-flipping |
| `powercalc regress` | Tier-2 ML: linear regression of smart-meter vs per-device on/off state. Recovers per-device load even when transitions are noisy / absent. Reports R² + per-coef 95% CI. numpy-only |
| `zone`         | Storage zone registry (`config/zone/*` WS): list/state-list/find/create/update/delete + `entities` (who's inside right now). YAML zones are read-only and surface via `state-list`. |
| `webhook`      | `webhook/list` WS + automation/mobile-app scan; `trigger <id>` (POST/PUT/GET/HEAD) with a registered-id guard; `generate-id`; cloudhook CRUD via `cloud/cloudhook/*` |
| `image`        | `image.*` entity domain: `list` / `show` / `snapshot <eid> <path>` (signed or direct), `proxy-url` (signed via `auth/sign_path`), `subscribe` to state-change events |
| `profiler`     | Wraps the `profiler` integration's services (cProfile/memray/lru_stats/dump_log_objects/log_thread_frames/log_event_loop_scheduled/log_current_tasks/set_asyncio_debug/log_events) plus a `status` probe |
| `action`       | Script-engine primitives — the pre-flight for `automation save` / `script save`. `run` (WS `execute_script`: ad-hoc sequence through HA's script engine — traced, gets a context, can return a `response_variable`, creates no entity; `--service` shorthand + `--dry-run`), `validate` (WS `validate_config` on triggers/conditions/actions), `validate-automation` / `validate-script` (whole config file, legacy singular keys upgraded, **exits non-zero when invalid** so it chains with `&&`), `test-condition` (WS `test_condition` against live state; a JSON list is evaluated per-item, error-tolerant; `--exit-code` for shell chaining) |
| `entity source`| WS `entity/source` — which integration currently supplies an entity. Provenance, not registry: only entities whose integration is loaded appear, so a registry entry with no source is a strong orphan signal (pairs with `entity orphans` / `entity prune`). `--by-integration` groups, `-i <domain>` filters. |

### State Model

The CLI is **stateless between invocations**. The only persisted state is the
connection profile (URL + token). All other state lives on the HA server and
is fetched on demand. This means:

- No session save/load step is required for one-shot mutations.
- The auto-save / `--dry-run` pattern from the harness guide does not apply
  (no client-side mutable session). However the CLI still supports a
  `--dry-run` flag on mutating service calls so agents can preview the
  request body without invoking the service.

## Output Formats

- Default: human-readable, key/value or table output with the unified skin.
- `--json`: emit a single JSON document for machine consumption (always a
  single value: object, array, or scalar).
- Error path: print error message to stderr, exit non-zero.

## How GUI Actions Map to CLI

| GUI action                            | CLI invocation                                                   |
|---------------------------------------|------------------------------------------------------------------|
| Toggle a light in the dashboard       | `service call light.toggle --target entity_id=light.kitchen` (or `light toggle light.kitchen`) |
| Set a light to warm dim               | `light on light.kitchen --brightness 80 --kelvin 2700`           |
| Set living-room thermostat            | `climate set-temperature climate.living -t 21.5`                 |
| Cast a track to Sonos                 | `media-player play-media media_player.sonos spotify:track:xyz music` |
| Drop a blind to 30 %                  | `cover set-position cover.kitchen_blind 30`                      |
| Pick a washing program                | `select set select.washer_program quick_30`                      |
| Fire a one-off notification           | `notify send "Garage left open" --service mobile_app_jon`        |
| Read a sensor value                   | `state get sensor.outdoor_temperature`                           |
| Trigger an automation manually        | `automation trigger automation.morning_routine`                  |
| Run a script                          | `script run script.bedtime`                                      |
| Render a template                     | `template render '{{ states("sensor.foo") }}'`                   |
| Look at server health                 | `system info` / `system core-state`                              |
| List what's loaded                    | `system components`                                              |
| Inspect device/area/entity registry   | `area list` / `device list` / `entity list`                      |
| See recent logbook                    | `logbook --hours 1`                                              |
| Activate a scene                      | `scene activate scene.movie_night --transition 2`                |
| Snapshot the current state into a scene | `scene create movie_now --snapshot light.kitchen --snapshot light.island` |
| Get the upcoming forecast             | `weather forecast weather.home --type daily`                     |
| Add a household shopping item         | `shopping-list add "Sourdough"`                                  |
| Mark a Google Tasks item done         | `todo complete todo.errands "Pick up dry cleaning"`              |
| Lock the front door                   | `lock lock lock.front_door --code 1234`                          |
| Arm the alarm                         | `alarm arm-vacation alarm_control_panel.home`                    |
| Find everything tied to a light       | `search entity light.kitchen --json`                             |
| Hide an entity from Alexa             | `entity expose set --assistant cloud.alexa --entity light.bedroom --hide` |
| Grab an HLS URL for a camera          | `camera stream camera.front_door --json`                         |
| See what the camera sees right now    | `camera snapshot camera.front_door front.jpg`                    |
| Record a few frames off the stream    | `camera capture camera.front_door ./frames --frames 5 --interval 1.0` |
| Embed a camera still with no auth header | `camera proxy-url camera.front_door --expires 300 --json`     |
| Save the album art that's on screen   | `media-player artwork media_player.lounge art.jpg`               |
| What triggers/conditions/actions does a device expose? | `device-automation summary <device_id> --json` |
| How would Assist parse a sentence?    | `assist debug "turn off the lights"`                             |
| Does the voice pipeline actually work? | `assist run "turn on the kitchen light" --json`                 |
| Transcribe a WAV and act on it        | `assist run --start-stage stt --audio cmd.wav --save-tts reply.mp3` |
| Switch a satellite's wake word        | `assist-satellite wake-words-set assist_satellite.kitchen okay_nabu` |
| Browse the media library              | `media browse --json`                                            |
| Get a token with no token             | `auth login --username agent --save --json`                      |
| What logins does this instance accept | `auth providers --json`                                          |
| Renew a short-lived access token      | `auth refresh --refresh-token <rt> --client-id <cid> --save`     |
| Revoke a refresh token, and prove it  | `auth revoke --token <rt> --verify --yes`                        |
| Log in to a 2FA account               | `auth login --username u --password p --mfa-code 123456`         |
| Who am I right now                    | `auth me --json`                                                 |
| Audit & revoke refresh tokens         | `auth tokens list --json` / `auth tokens delete <id> --yes`      |
| Sign a one-shot URL for download      | `auth sign-path /api/camera_proxy/camera.front --expires 300`    |
| Crank an integration to DEBUG live    | `logger level-set mqtt debug --persistence once`                 |
| Pull integration manifests / analytics | `system manifest list --json` / `system analytics get --json`   |
| Ignore a repairs issue                | `system issue ignore homeassistant <issue_id>`                   |
| Rescan USB / open Zigbee join         | `system usb-scan` / `system zha-permit-join --duration 120`      |
| Tag automations by purpose            | `category create automation Alerts --icon mdi:alert`             |
| Hit "Run actions" in the script editor | `action run --sequence-file seq.json` (or `--service light.turn_on -t entity_id=…`) |
| The editor's red "invalid config" box | `action validate-automation morning.json`                        |
| Hit "Test" next to a condition        | `action test-condition --condition '{"condition":"sun","after":"sunset"}'` |
| "Provided by <integration>" in the entity dialog | `entity source light.kitchen --json`                  |

## Testing

> Tests live in `agent-harness/tests/`, not `cli_anything/homeassistant/tests/`.
> The inner package directory `homeassistant` collides with the real Home
> Assistant Python package; pytest's default prepend import mode would put
> `cli_anything/` on `sys.path` and shadow the real package during fixture
> setup. Hosting the tests at the harness root plus `--import-mode=importlib`
> in `pytest.ini` avoids the collision.

- **Unit tests** (`test_core.py`) — mock the backend HTTP/WebSocket layer with
  `requests-mock` and a fake WebSocket fixture. Verify URL construction, payload
  shapes, header injection, and error handling.
- **E2E tests** (`test_full_e2e.py`) — boot a **real** Home Assistant
  instance with `python -m homeassistant --config <tmp>` (installed from
  `requirements_test_all.txt`), wait for the API to come up, create a
  long-lived token via the CLI helpers, and exercise the full command
  surface against the live server. Tests then verify state via the same API.
- **CLI subprocess tests** (`TestCLISubprocess`) — invoke
  `cli-anything-homeassistant` via the installed entry point with
  `_resolve_cli("cli-anything-homeassistant")`.
- **Real-counterparty tests** — where the harness implements a WIRE FORMAT
  rather than a JSON call, a `FakeClient` is not evidence: a fixture written
  from the same reading of the protocol as the client agrees with the client
  whether or not either is right. Two suites therefore run against a genuine
  second implementation: `test_ws_run_events.py` (an aiohttp server speaking
  HA's websocket framing) and `test_media_proxy_stream.py` (multipart frames
  produced by Home Assistant's OWN `async_get_still_stream`, read over a real
  socket). The latter caught two client bugs on first run.

The tests must NOT skip when `homeassistant` is not installed — Home
Assistant is a hard dependency.

## Dependencies

Python:
- `click`, `prompt_toolkit`, `requests`, `websocket-client`

System (the real software):
- `homeassistant` Python package (installed standalone or via Docker).
  Install: `pip install homeassistant` or
  `docker run -d --name hass -p 8123:8123 ghcr.io/home-assistant/home-assistant:stable`
