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

All requests require a **Long-Lived Access Token** (Bearer):

1. Start Home Assistant.
2. Sign in to the UI, open your profile (bottom-left avatar).
3. Scroll to the bottom and create a Long-Lived Access Token.
4. Save it to the harness with `cli-anything-homeassistant config set --token <token>`
   or expose it via the `HASS_TOKEN` environment variable.

### Reference Endpoints

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

WebSocket message types used by the harness:

- `auth` (`access_token`)
- `config/area_registry/list`
- `config/device_registry/list`
- `config/entity_registry/list`
- `config_entries/get`
- `system_health/info`
- `subscribe_events`

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
| `entity`     | Entity registry (WS) (`list`)                                       |
| `automation` | Automations (`list`/`trigger`/`toggle`/`reload`)                    |
| `script`     | Scripts (`list`/`run`)                                              |
| `domain`     | Helpers per domain (`list`/`turn-on`/`turn-off`/`toggle`)           |
| `history`    | Historical state changes                                            |
| `logbook`    | Logbook entries                                                     |

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
| Toggle a light in the dashboard       | `service call light.toggle --target entity_id=light.kitchen`     |
| Read a sensor value                   | `state get sensor.outdoor_temperature`                           |
| Trigger an automation manually        | `automation trigger automation.morning_routine`                  |
| Run a script                          | `script run script.bedtime`                                      |
| Render a template                     | `template render '{{ states("sensor.foo") }}'`                   |
| Look at server health                 | `system info` / `system core-state`                              |
| List what's loaded                    | `system components`                                              |
| Inspect device/area/entity registry   | `area list` / `device list` / `entity list`                      |
| See recent logbook                    | `logbook --hours 1`                                              |

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

The tests must NOT skip when `homeassistant` is not installed — Home
Assistant is a hard dependency.

## Dependencies

Python:
- `click`, `prompt_toolkit`, `requests`, `websocket-client`, `pyyaml`

System (the real software):
- `homeassistant` Python package (installed standalone or via Docker).
  Install: `pip install homeassistant` or
  `docker run -d --name hass -p 8123:8123 ghcr.io/home-assistant/home-assistant:stable`
