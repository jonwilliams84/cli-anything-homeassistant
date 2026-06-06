# cli-anything-homeassistant

A `click`-based CLI + interactive REPL that exposes the full Home Assistant REST +
WebSocket API surface (states, services, registries, lovelace, automations, backups,
diagnostics, statistics, powercalc, 17 typed entity-control groups, …) for agents and
shell scripts. Stateless thin client — HA does all the work; this never runs automation
logic or renders templates locally. Every command supports `--json`.

## Layout
- `cli_anything/homeassistant/homeassistant_cli.py` — the Click CLI + REPL (~10k lines, single file; all commands wired here). Entry point: `main`.
- `cli_anything/homeassistant/core/` — ~100 modules, one HA API surface each (states, registry, lovelace*, automation, backup, statistics, powercalc*, …). Each is pure function-per-operation, callable from Python directly or via the Click wrapper.
- `cli_anything/homeassistant/utils/homeassistant_backend.py` — the wire client: `requests.Session` (REST) + websocket-client subscriber (WS). All core modules call through this.
- `cli_anything/homeassistant/skills/SKILL.md` — packaged self-contained skill manifest (full command docs); packaged via `package_data`.
- `tests/` — 55 files, 200+ unit tests. `tests/conftest.py` defines `FakeClient` (records every REST/WS call, returns prepared responses). E2e tests boot a real HA in a temp config dir.
- `HOMEASSISTANT.md` — SOP / agent operating guide. `CHANGELOG.md` — per-version detail.

## Commands
- Install (editable): `pip install -e .` → exposes `cli-anything-homeassistant`.
- Test: `pip install -e '.[test]'` (installs pytest + homeassistant for e2e), then `python3 -m pytest tests/ -v` (config in `pytest.ini`: importlib mode, `testpaths=tests`).
- Run needs a live HA: `--url`/`--token` flags or env `HASS_URL` / `HASS_TOKEN` / `HASS_VERIFY_SSL` / `HASS_TIMEOUT`; persisted profile at `~/.config/cli-anything-homeassistant.json` (mode 0600).

## Conventions
- Deps are minimal and deliberate: `click`, `prompt-toolkit`, `requests`, `websocket-client`, `numpy` (numpy only for `powercalc regress` linear regression — no scipy/sklearn). Python >= 3.10.
- New API surface = new module under `core/` (pure functions) + a Click wrapper in `homeassistant_cli.py` + a unit test using `FakeClient`. Keep `--json` output on every new command.
- Versioning: bump `version` in `setup.py`, add a `CHANGELOG.md` entry. Work happens on `feat/*` branches → PR → merge to `main` (see git history). Tags like `v1.42.0` per release.
- Powercalc commands are safety wrappers over HA footguns (REPLACE-on-write options flow, binary_sensor no-op); preserve the backup-first / dry-run-by-default / `--apply`-to-commit pattern when extending them (mirrored in `entity prune`).

## Gotchas
- `homeassistant_cli.py` is one huge file — grep for the command name; new commands go alongside existing siblings.
- Never commit a token: `.gitignore` excludes the connection-profile JSON.
- Sibling family: `cli-anything-zigbee2mqtt`, `cli-anything-espresense` share the profile/JSON/REPL pattern.
