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
