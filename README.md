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
