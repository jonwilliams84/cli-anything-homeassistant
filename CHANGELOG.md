# Changelog

All notable changes to `cli-anything-homeassistant` are documented here.

The project versions follow semver (MAJOR.MINOR.PATCH).

## [1.41.0] — 2026-06-02

Powercalc editing gaps exposed while setting a lamp's standby power. The only
way to set off-state power on an existing entry was hand-driving the options
flow; there was no way to read an entry's configured options back; and
`set-power` could be silently shadowed by a stale template.

### Added
- **`powercalc set-standby <entry> <watts>`** — set the OFF-state
  `standby_power` on an existing virtual_power entry. It lives on the
  `basic_options` step (not `fixed`), so `set-power`/`set-template` never
  reached it. The source `entity_id` is auto-resolved and re-sent so the
  submit can't blank the entry's source (`--source` to override). Pairs with
  `set-power`: on-state W vs off-state W.
- **`powercalc show <entry>`** — read an entry's live + configured state
  (`calculation_mode`, `source_entity`, current W, and best-effort
  `power`/`power_template`/`standby_power`). The config-entry list doesn't
  expose powercalc options; previously you had to infer them from the sensor.

### Changed / fixed
- **`set-power` now clears any stale `power_template`** before writing the
  constant — powercalc gives a template precedence over the fixed value, so a
  leftover template silently shadowed the new number.
- **`set-power` / `set-template` now auto-reload the entry** after writing
  (`reload=False` to skip) so the change lands on the sensor immediately — an
  options-flow `create_entry` didn't always reload on its own, the usual
  reason a freshly-written value "didn't take".

## [1.40.0] — 2026-06-02

Noise rejection for the **active** powercalc calibrators (`calibrate`,
`calibrate-template`). Previously they computed `delta = load − baseline`
against the whole-home smart meter and blindly trusted the device under test
was the only thing moving — so a kettle/microwave/another light switching
mid-window silently poisoned the result. Now each measurement window is
gated two ways and re-measured (then excluded) if either trips:

### Added
- **Variance gate** — rejects a window whose spread (max − min) exceeds
  `--max-variance-w` (default 50 W). Catches large spikes from **untracked**
  loads (no powercalc profile, no native sensor) — they show up as a blown
  spread on the whole-home meter.
- **Confounder watch** — before/after each window we snapshot OTHER tracked
  devices and reject the window if any moved:
  - source entities of other **powercalc** profiles (discrete on/off/bright
    state change), and
  - **natively-metered** entities (`device_class: power`, non-powercalc) whose
    value moves beyond a 5 W epsilon.
  Catches a neighbour toggling even when its draw is too small to trip the
  variance gate.
- `--max-variance-w` / `--max-retries` flags on both commands (set
  `--max-variance-w 0` to disable the gate — legacy behaviour).
- New result fields: `calibrate` → `noisy`; `calibrate-template` →
  `baseline_noisy`, `excluded_steps`, and per-step `spread`/`attempts`/
  `excluded`/`confounder`. Each measurement carries `spread`/`stdev`/
  `attempts`/`accepted`/`confounder`.

### Changed
- A noisy run **never auto-applies**: `calibrate` skips the write when
  `noisy`; `calibrate-template` fits the template only from clean steps and
  refuses to apply on a poisoned baseline.

## [1.39.0] — 2026-05-29

Safety + correctness refine. The headline change: most v6-listed agent
footguns are now closed. `whoami` no longer crashes, WS subscriptions don't
leak server-side state on exit, lovelace card writes auto-validate before
posting, and every destructive verb now accepts `--yes` for non-interactive
use. Plus 17 previously library-only modules got CLI surfaces.

### Fixed — bugs that would burn an agent

- **`whoami` was broken at runtime.** It called `auth_core.current_user`
  which doesn't exist; the real implementation is in
  `auth_tokens_core.current_user`. Every cold-start agent that followed
  SKILL.md hit `AttributeError`. Now wired correctly + smoke-tested.
- **WS subscriptions leaked server-side ids on exit.** `ws_subscribe()`
  closed the socket without sending `unsubscribe_events`, so Ctrl-C'd
  `event subscribe` / `state watch` / `mqtt subscribe` left the HA
  server tracking dangling subscriptions until the next restart. Now
  unsubscribes before close. Backend: `utils/homeassistant_backend.py`.
- **`entity prune --protect-user-disabled` was bypassed by `--entity-id`.**
  The early-return branch for explicit entity lists skipped the safety
  filter loop, so a typo deleted a user-disabled entry despite the flag.
  Now honored in both branches. CLI: `entity_prune` at homeassistant_cli.py.
- **`mqtt subscribe --limit 0 --out FILE` grew memory unboundedly.** The
  in-memory `seen[]` buffer was populated even when messages streamed to
  a file. Now skips the buffer in streaming-only mode; the final JSON
  emit reports `{"streamed_only": true, "received": N}` instead of the
  message array.
- **`project.save_config()` had a token-write race.** It wrote the JSON
  then `chmod 0o600`'d it — a permissive umask left the token briefly
  world-readable. Now uses `os.open(O_CREAT, mode=0o600)` so the file is
  never less than 0600.

### Changed — safety / correctness

- **`automation save` / `script save` no longer silently overwrite.**
  Both gain `--dry-run` (prints a unified diff vs the live config) and
  `--yes` (skips the new interactive prompt). Without either, the command
  prompts; without a TTY, it aborts.
- **`lovelace card insert` and `card delete` gain `--dry-run`.** Matches
  `card replace` which already had it.
- **`lovelace config save` requires `--yes` when scripted.** Adds
  `--dry-run` (full unified diff vs live dashboard) and `--yes`
  (skips prompt). Wholesale dashboard overwrite is destructive — typos
  here wipe entire dashboards.
- **`lovelace_card_validate` is now wired** (was implemented + tested
  but never called). `lovelace card insert`, `card replace`,
  `section set`, `view set`, `view add` all run the validator first
  and refuse the write on `error`-severity issues. Pass `--no-validate`
  to bypass (e.g. when the HACS plugin will be installed later).
- **Four destructive verbs gain confirmation prompts** (Click
  `@confirmation_option`, accepts `--yes` to skip): `shopping-list
  remove`, `shopping-list clear-completed`, `todo remove`,
  `todo clear-completed`.
- **`system reload-core-config` and `system reload-all` gain
  confirmation prompts.** They're mutating; match the pre-existing
  `system restart` / `system stop` pattern.

### Added — surface

- **`state delete <entity_id>`** wires the long-documented but never-
  implemented `DELETE /api/states/<entity_id>` (HOMEASSISTANT.md and
  SKILL.md both promised it). Tears an entity out of the state machine
  without touching the registry. Confirmation-gated.
- **`tag create` and `tag delete`.** Tags went from list/find/update
  only to full CRUD (`tag/create` and `tag/delete` WS namespaces).
- **`event subscribe --filter 'key.path=value'`.** Repeatable client-
  side filter that runs after HA's server-side event_type filter.
  SKILL.md already documented it; now implemented.
- **`history` flags `--no-attributes` and `--significant-changes-only`.**
  HA's REST API supports both — exposes the size/speed knobs to agents
  hitting big installs.
- **`_TOGGLABLE_DOMAINS` covers 5 more domains**: `valve`,
  `lawn_mower`, `lock`, `alarm_control_panel`, `group`. Means the
  generic `domain turn-on valve.x` now works.
- **17 previously-unwired core modules now have CLI surfaces** (sprint
  artifacts that landed code without wiring): `backup_advanced`
  (subgroup), `calendar_ws`, `diagnostics_dl`, `entity_registry_extras`,
  `frontend_prefs`, `network`, `energy_advanced`, `statistics_admin`,
  `helper_previews`, `history_ext`, `history_logbook` (the
  `history_during_period` WS path that bypasses the REST "first 24h
  only" gotcha), `lovelace_layout_lint`, `lovelace_sections_ext`,
  `lovelace_views`, `state_stream`, `trace_debug`, `trace_debugger`.

### Changed — internals

- **`backend.HomeAssistantClient.post()` and `.delete()` now accept
  `params=`.** `core/services.py::call_service` switched from a hand-
  built `?return_response` suffix to `params={"return_response": "true"}`.
- **`backend.HomeAssistantClient.ws_subscribe()` sends
  `unsubscribe_events` on exit** (see Fixed above).

### Docs

- **README.md**: corrected env var names from `CLI_HA_URL`/`CLI_HA_TOKEN`
  (didn't exist) to the actual `HASS_URL`/`HASS_TOKEN`/`HASS_VERIFY_SSL`/
  `HASS_TIMEOUT`. Also flagged the 0600 profile mode.
- **HOMEASSISTANT.md**: dropped `pyyaml` from the dependencies list
  (not installed, not imported).
- **SKILL.md**: documented the new safety surface, the 17 newly-wired
  command groups, and the `--no-validate` escape hatch.

### Tests

- **`tests/test_v6_refine_fixes.py`** — 41 new regression tests covering
  every behaviour change above: whoami fix, WS unsubscribe, entity
  prune safety, mqtt buffer, project.py file perms, automation/script
  save `--dry-run`/`--yes`, lovelace card insert/delete `--dry-run`,
  lovelace validation wiring, lovelace config save `--yes` gate,
  shopping-list/todo confirmation, system reload confirmation,
  `state delete` wiring, new toggleable domains, `tag create`/`delete`,
  services params, history flags, `event subscribe --filter`.
- **`tests/test_v6_core_coverage.py`** — 26 new tests for previously-
  untested core modules: `groups`, `lovelace_mirror` (pure-Python
  paths), `mqtt_discovery`, `template_helpers` (validation paths),
  `watch`, `_ws_subscribe_utils`.
- **`tests/conftest.py::FakeClient`**: `post()` and `delete()` now
  accept `params=` to match the real backend signature change.
- Existing tests adjusted for the new confirmation prompts (added
  `--yes` where appropriate) and the new params-shape on services
  return_response.
- **2024 tests pass** (was 1957 before the refine, +67 v6 fixtures).
  4 skipped (real-HA fixtures), 0 failures.

## [1.38.0] — pre-refine

(See git log for prior changes.)
