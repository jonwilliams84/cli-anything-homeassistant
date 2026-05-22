# cli-anything-homeassistant

A CLI harness for [Home Assistant](https://www.home-assistant.io/). Lets AI
agents and shells read entity states, call services, render templates,
inspect registries, and stream events from a running Home Assistant instance
without the browser UI.

## How it Works

`cli-anything-homeassistant` is a thin client over the **real** Home Assistant
REST API (`/api/...`) and WebSocket API (`/api/websocket`). The CLI does not
reimplement Home Assistant — it must be running and reachable.

## Install Home Assistant

The CLI is useless without a running Home Assistant. Install it via one of:

```bash
# Pip (in a virtualenv)
pip install homeassistant
hass --config /path/to/config

# Docker (recommended for production-style usage)
docker run -d --name hass -p 8123:8123 \
  -v /PATH_TO_YOUR_CONFIG:/config \
  ghcr.io/home-assistant/home-assistant:stable
```

Then open `http://localhost:8123`, complete onboarding, and from your user
profile (bottom-left avatar → Long-Lived Access Tokens) create a token.

## Install the CLI

```bash
cd CLI-Anything/homeassistant/agent-harness
pip install -e .
```

After install, the `cli-anything-homeassistant` command is available on PATH.

## Configure

```bash
cli-anything-homeassistant config set \
  --url http://localhost:8123 \
  --token <your-long-lived-access-token>

cli-anything-homeassistant config test
```

The profile is saved to `~/.config/cli-anything-homeassistant.json` with
`0600` permissions.

You can also use environment variables: `HASS_URL`, `HASS_TOKEN`,
`HASS_VERIFY_SSL=0`, `HASS_TIMEOUT=30`.

## Usage

Stateless one-shot commands:

```bash
cli-anything-homeassistant system info
cli-anything-homeassistant state list --domain light
cli-anything-homeassistant state get sensor.outdoor_temperature
cli-anything-homeassistant service call light turn_on \
    --target entity_id=light.kitchen --data brightness=200
cli-anything-homeassistant template render '{{ states("sensor.outdoor_temperature") }}'
cli-anything-homeassistant area list --json
cli-anything-homeassistant logbook --hours 1
```

Run the REPL (default when invoked with no args):

```bash
cli-anything-homeassistant
```

JSON output for agents:

```bash
cli-anything-homeassistant --json state list --domain light
```

`--dry-run` is supported on every mutating command (`service call`,
`event fire`, `domain turn-on/off/toggle`):

```bash
cli-anything-homeassistant service call light turn_on \
  --target entity_id=light.foo --dry-run --json
```

## Command Surface

| Group        | Notable commands                                           |
|--------------|------------------------------------------------------------|
| `config`     | `show`, `set`, `save`, `test`                              |
| `system`     | `info`, `config`, `core-state`, `error-log`, `components`, `health` |
| `state`      | `list`, `get`, `set`, `domains`, `counts`                  |
| `service`    | `list`, `domains`, `call`                                  |
| `event`      | `list`, `fire`, `subscribe`                                |
| `template`   | `template <jinja>`                                         |
| `area`       | `list`                                                     |
| `device`     | `list`                                                     |
| `entity`     | `list`                                                     |
| `automation` | `list`, `trigger`, `toggle`, `turn-on`, `turn-off`, `reload` |
| `script`     | `list`, `run`, `reload`                                    |
| `domain`     | `list`, `turn-on`, `turn-off`, `toggle`                    |
| `history`    | `history --hours N`                                        |
| `logbook`    | `logbook --hours N`                                        |
| `scene`      | `list`, `activate`, `apply`, `create`, `reload`            |
| `weather`    | `list`, `units`, `forecast`, `forecast-subscribe`          |
| `shopping-list` | `list`, `add`, `update`, `remove`, `clear-completed`, `reorder` |
| `todo`       | `list`, `add`, `update`, `complete`, `remove`, `move`, `clear-completed` |
| `lock`       | `lock`, `unlock`, `open`                                   |
| `alarm`      | `arm-away`, `arm-home`, `arm-night`, `arm-vacation`, `disarm` |
| `search`     | `search <type> <id>` — find related entities/devices/areas |
| `entity expose` | `list`, `set`, `new-default-get`, `new-default-set`     |
| `camera`     | `capabilities`, `stream` (HLS URL), `prefs-get`, `prefs-set`, `webrtc-config` |
| `device-automation` | `triggers`, `conditions`, `actions`, `summary` — for building automations programmatically |
| `assist` (extensions) | `agents`, `sentences`, `debug`, `satellites`, `languages` |
| `assist-satellite` | `config`, `wake-words-set`, `test-connection`        |
| `mobile-app` | `confirm-push` — acknowledge a Companion-app push notification |
| `media`      | `browse`, `resolve`, `remove` — media_source tree + URL resolution |
| `auth` (extensions) | `me`, `sign-path`, `tokens list/delete/delete-all/set-expiry`, `user create/update/credential-create/credential-delete/change-password` |
| `category`   | `list`, `create`, `update`, `delete`, `by-name` — registry CRUD for scope-bound categories |
| `logger` (extensions) | `info-ws`, `level-get`, `level-set` (WS-side per-component log control) |
| `system` (extensions) | `manifest list/get`, `analytics get/set`, `app-credentials config/entry`, `issue get-data/ignore`, `usb-scan`, `zha-permit-join`, `hardware-info`, `board-info`, `cpu-info`, `log errors/clear/write` |

Examples from the refine pass:

```bash
# Activate a scene with a 2s transition
cli-anything-homeassistant scene activate scene.movie_night --transition 2

# Snapshot the kitchen lights into a new scene
cli-anything-homeassistant scene create kitchen_now \
  --snapshot light.kitchen --snapshot light.island

# Get a 24h forecast as JSON for an automation
cli-anything-homeassistant --json weather forecast weather.home --type hourly

# Add an item to the household shopping list
cli-anything-homeassistant shopping-list add "Sourdough"

# Mark a Google Tasks item complete
cli-anything-homeassistant todo complete todo.errands "Pick up dry cleaning"

# Lock the front door (with a code)
cli-anything-homeassistant lock lock lock.front_door --code 1234

# Arm the alarm in vacation mode
cli-anything-homeassistant alarm arm-vacation alarm_control_panel.home

# Find every automation, scene, and dashboard that references a light
cli-anything-homeassistant --json search entity light.kitchen

# Hide an entity from Alexa
cli-anything-homeassistant entity expose set \
  --assistant cloud.alexa --entity light.bedroom --hide

# Get an HLS stream URL for a camera (for embedding / viewing)
cli-anything-homeassistant --json camera stream camera.front_door

# Discover what triggers / conditions / actions a device exposes
cli-anything-homeassistant --json device-automation summary <device_id>

# Debug how the default Assist agent would parse a sentence
cli-anything-homeassistant assist debug "turn off the kitchen lights"

# Set the wake word(s) on a voice satellite
cli-anything-homeassistant assist-satellite wake-words-set \
  assist_satellite.kitchen okay_nabu

# Browse the media library tree
cli-anything-homeassistant --json media browse

# Resolve a media-source URI to a playable URL
cli-anything-homeassistant --json media resolve "media-source://tts/cloud?message=hi"

# Who am I (the user the active token belongs to)?
cli-anything-homeassistant auth me --json

# Sign a download URL for offline use
cli-anything-homeassistant auth sign-path /api/camera_proxy/camera.front --expires 300

# Audit refresh tokens, then revoke a specific one
cli-anything-homeassistant --json auth tokens list
cli-anything-homeassistant auth tokens delete <token-id> --yes

# Create a new HA user in the admin group
cli-anything-homeassistant auth user create "House Guest" \
  --group system-users --local-only

# Tag automations by purpose
cli-anything-homeassistant category create automation Alerts --icon mdi:alert
cli-anything-homeassistant --json category by-name automation

# Crank one integration to DEBUG without restarting HA
cli-anything-homeassistant logger level-set mqtt debug --persistence once

# Inspect integration manifests, OAuth setup, repairs issues
cli-anything-homeassistant --json system manifest get mqtt
cli-anything-homeassistant --json system app-credentials config
cli-anything-homeassistant system issue ignore homeassistant <issue_id>

# Trigger a USB rescan or open Zigbee for join
cli-anything-homeassistant system usb-scan
cli-anything-homeassistant system zha-permit-join --duration 120
```

## Tests

The test suite expects a real Home Assistant install:

```bash
pip install homeassistant home-assistant-frontend
cd CLI-Anything/homeassistant/agent-harness
CLI_ANYTHING_FORCE_INSTALLED=1 pytest tests/ -v -s
```

See `tests/TEST.md` for the test plan and results.

> **Note on test layout:** the harness convention puts tests under
> `cli_anything/<software>/tests/`. For Home Assistant we deliberately ship
> them under `agent-harness/tests/` instead, because the inner package name
> `homeassistant` collides with the real `homeassistant` Python package.
> Pytest's default import mode would put `cli_anything/` on `sys.path` and
> shadow the real Home Assistant package during fixture setup. Keeping the
> tests at the harness root sidesteps that collision; `pytest.ini` pins
> `--import-mode=importlib` for the same reason.
