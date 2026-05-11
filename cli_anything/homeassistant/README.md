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
