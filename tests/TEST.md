# cli-anything-homeassistant — Test Plan

## Test Inventory

| File              | Purpose                                                   | Planned tests |
|-------------------|-----------------------------------------------------------|---------------|
| `test_core.py`    | Unit tests with a mocked HTTP/WebSocket backend           | ~30           |
| `test_full_e2e.py`| E2E tests against a real Home Assistant instance + CLI    | ~12           |

Total target: **~42** tests.

## Unit Test Plan (`test_core.py`)

All unit tests use a synthetic `FakeClient` that records calls and returns
prepared responses. No real Home Assistant required.

### `core/project.py`
- Defaults applied when no config file exists.
- File values overridden by env vars (`HASS_URL`, `HASS_TOKEN`,
  `HASS_VERIFY_SSL`, `HASS_TIMEOUT`).
- Save round-trip: write → load → values match.
- `redact()` masks the token.
- File permissions set to 0600 after save.

### `core/system.py`
- `status()`, `config()`, `core_state()` return the expected payload.
- `error_log()` honors the `lines` tail argument.
- `components()` returns a list even when the API returns nothing.
- `system_health()` calls the right WS message type.

### `core/states.py`
- `list_states()` returns all; with `domain` filters correctly.
- `get_state()` rejects empty entity_id.
- `set_state()` builds payload with optional attributes.
- `list_domains()` and `count_by_domain()` aggregate by entity_id prefix.

### `core/services.py`
- `list_services()` honors `domain`.
- `call_service()` folds `target` and `service_data` into the body.
- `return_response=True` appends the query parameter.

### `core/events.py`
- `list_listeners()` returns list.
- `fire_event()` sends payload to the right path.

### `core/template.py`
- `render()` returns the rendered text.
- Empty template raises ValueError.

### `core/registry.py`
- `list_areas()`/`list_devices()`/`list_entities()` invoke the right WS types.
- Entity domain filter and area filter helpers work.

### `core/automation.py`
- `trigger()` rejects non-`automation.*` IDs.
- `trigger(skip_condition=True)` includes the flag.
- `toggle/turn_on/turn_off/reload` call the right service.

### `core/script.py`
- `run()` rejects non-`script.*` IDs.
- `run(variables={...})` includes them.

### `core/domain.py`
- `turn_on`/`turn_off`/`toggle` reject unknown domains.
- Pass through to the right service call when valid.

### `core/history.py`
- `history()` builds path with start time.
- `logbook()` translates `hours` → start.

### `utils/homeassistant_backend.py`
- URL normalization (`localhost:8123` → `http://localhost:8123`).
- ws URL conversion (`http://` → `ws://`, `https://` → `wss://`).
- Bearer header attached to the requests session when token is set.
- `HomeAssistantError` raised on connection refused.
- `HomeAssistantError` raised on 401 with helpful message.

### CLI helpers
- `parse_kv_pairs()` JSON-decodes values when possible, falls back to strings.
- `parse_kv_pairs()` rejects malformed input.

## E2E Test Plan (`test_full_e2e.py`)

E2E tests boot a **real Home Assistant** instance using the installed
`homeassistant` Python package, in a temporary config directory. The fixture:

1. Creates a tmp config with `default_config:`.
2. Boots `python -m homeassistant --config <tmp>` in a subprocess.
3. Waits for `/api/` to become reachable.
4. Programmatically creates a long-lived access token by hitting the auth
   endpoints.
5. Runs CLI commands and verifies live behaviour.
6. On teardown, terminates the HA process.

### Workflow scenarios

1. **Connection workflow** — `config set` saves token; `config test`
   confirms the round trip; profile file has 0600 permissions.
2. **System introspection** — `system info` returns version; `system config`
   returns `latitude`/`longitude`/etc.; `system core-state` reports
   `running`; `system components` includes `default_config`.
3. **State read/write** — `state set sensor.test_temp 21.5
   --attr unit_of_measurement="°C"` then `state get sensor.test_temp`
   round-trips state and attribute.
4. **Service registry** — `service list` non-empty; `service domains`
   contains expected core domains (`homeassistant`, `persistent_notification`).
5. **Service call** — call `persistent_notification.create` with a unique
   message; verify a `persistent_notification.*` entity exists with the
   right attributes.
6. **Event fire** — fire a custom event and verify the bus accepted it
   (returned message includes the event type).
7. **Template render** — render `{{ now() }}` and verify the result is a
   non-empty ISO-ish string; render `{{ states("sensor.test_temp") }}`
   and verify it matches the value set earlier.
8. **Registry queries (WS)** — `area list`, `device list`, `entity list`
   each return JSON arrays and at least the entity registry has entries
   we created via `state set`.
9. **Domain helpers** — create `input_boolean.test_flag` via service call
   to `input_boolean.toggle` (exercising the dry-run path first).
10. **History/logbook** — `logbook --hours 24` returns a list (may be
    empty on a fresh instance).
11. **Subprocess CLI smoke** — `cli-anything-homeassistant --help`,
    `--json system info`, `--json state list --domain sensor` via the
    installed entry point using `_resolve_cli()`.
12. **End-to-end JSON output** — every command run with `--json` produces
    valid JSON that `json.loads()` accepts.

### Verified properties

- HTTP responses match expected JSON schemas.
- WebSocket messages produce valid registry entries.
- The CLI never silently drops mutations (state set is observable on read).
- `--dry-run` never reaches the API (verified by checking state didn't change).
- `_resolve_cli()` finds the installed `cli-anything-homeassistant` and the
  `[_resolve_cli]` line shows up in `-s` test output.

## Realistic Workflow Scenarios

### Scenario A: "Smart-home agent inspection"

Simulates an agent that lands in a fresh HA install and wants to learn
what's there:

```
config set → config test → system info → system components →
state domains → state counts → entity list --domain sensor
```

Verified: every step succeeds with valid JSON and the agent can build a
mental model of the install with no GUI.

### Scenario B: "Set a sensor and read it back"

Simulates a script that publishes external data into HA and then queries
it:

```
state set sensor.outdoor_temperature 18.3 --attr unit_of_measurement="°C" \
  --attr friendly_name="Outdoor"
state get sensor.outdoor_temperature
template render '{{ states("sensor.outdoor_temperature") | float }}'
```

Verified: the value persisted, the attributes round-tripped, the template
engine sees the new state immediately.

### Scenario C: "Trigger a service"

Simulates an agent reacting to an event:

```
service call persistent_notification create \
  --data title="Agent" --data message="Hello from CLI" --data notification_id="cli_test"
state get persistent_notification.cli_test
```

Verified: the persistent notification entity exists with the agent's
message in `attributes.message`.

### Scenario D: "Dry-run safety"

Simulates an agent that wants to inspect a request before sending it:

```
service call light turn_on --target entity_id=light.does_not_exist --dry-run --json
```

Verified: the response includes `"dry_run": true` and the API was not
contacted (HA error log unchanged).

## Notes / Limitations

- Home Assistant requires Python 3.13+; if the test environment has an older
  Python, the E2E tests will skip with a clear message and the suite should
  flag this as a coverage gap.
- The first boot of HA installs default_config dependencies; the fixture
  pre-installs them via `requirements_test_all.txt` to avoid surprise
  network calls during the test run.

---

## Test Results

Run with:

```bash
pip install -e .
pip install pytest requests-mock
pip install homeassistant home-assistant-frontend
CLI_ANYTHING_FORCE_INSTALLED=1 pytest tests/ -v
```

### Summary

| Metric                | Value           |
|-----------------------|-----------------|
| Total tests           | **95**          |
| Passing               | **95** (100%)   |
| Failing               | 0               |
| Execution time        | ~5.5 seconds    |
| Python                | 3.12.3          |
| Home Assistant        | 2025.1.4        |

### Pytest output (`pytest -v --tb=no`)

```
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.3, pluggy-1.6.0
rootdir: /home/jonwi/CLI-Anything/homeassistant/agent-harness
configfile: pytest.ini
plugins: requests-mock-1.12.1

tests/test_core.py::TestProjectConfig::test_defaults_when_no_file PASSED
tests/test_core.py::TestProjectConfig::test_env_override PASSED
tests/test_core.py::TestProjectConfig::test_save_and_load_roundtrip PASSED
tests/test_core.py::TestProjectConfig::test_save_sets_0600 PASSED
tests/test_core.py::TestProjectConfig::test_redact PASSED
tests/test_core.py::TestSystem::test_status PASSED
tests/test_core.py::TestSystem::test_status_non_dict_wraps_message PASSED
tests/test_core.py::TestSystem::test_config_returns_dict PASSED
tests/test_core.py::TestSystem::test_core_state PASSED
tests/test_core.py::TestSystem::test_error_log_full PASSED
tests/test_core.py::TestSystem::test_error_log_tail PASSED
tests/test_core.py::TestSystem::test_components_list PASSED
tests/test_core.py::TestSystem::test_components_empty PASSED
tests/test_core.py::TestSystem::test_system_health_uses_ws PASSED
tests/test_core.py::TestStates::test_list_all PASSED
tests/test_core.py::TestStates::test_list_filter_domain PASSED
tests/test_core.py::TestStates::test_get_state_empty_id_raises PASSED
tests/test_core.py::TestStates::test_set_state_payload PASSED
tests/test_core.py::TestStates::test_set_state_no_attributes PASSED
tests/test_core.py::TestStates::test_list_domains PASSED
tests/test_core.py::TestStates::test_count_by_domain PASSED
tests/test_core.py::TestServices::test_list_all PASSED
tests/test_core.py::TestServices::test_list_filter_domain PASSED
tests/test_core.py::TestServices::test_list_domains PASSED
tests/test_core.py::TestServices::test_call_service_payload PASSED
tests/test_core.py::TestServices::test_call_service_return_response PASSED
tests/test_core.py::TestServices::test_call_service_validates PASSED
tests/test_core.py::TestEvents::test_list_listeners PASSED
tests/test_core.py::TestEvents::test_fire_event PASSED
tests/test_core.py::TestEvents::test_fire_event_validates PASSED
tests/test_core.py::TestTemplate::test_render PASSED
tests/test_core.py::TestTemplate::test_render_with_vars PASSED
tests/test_core.py::TestTemplate::test_render_validates PASSED
tests/test_core.py::TestRegistry::test_areas PASSED
tests/test_core.py::TestRegistry::test_devices PASSED
tests/test_core.py::TestRegistry::test_entities PASSED
tests/test_core.py::TestRegistry::test_filter_entities_by_domain PASSED
tests/test_core.py::TestRegistry::test_filter_devices_by_area PASSED
tests/test_core.py::TestAutomation::test_trigger_validates_id PASSED
tests/test_core.py::TestAutomation::test_trigger_skip_condition PASSED
tests/test_core.py::TestAutomation::test_toggle PASSED
tests/test_core.py::TestAutomation::test_reload PASSED
tests/test_core.py::TestScript::test_run_validates_id PASSED
tests/test_core.py::TestScript::test_run_with_vars PASSED
tests/test_core.py::TestDomainHelpers::test_turn_on_unknown_domain PASSED
tests/test_core.py::TestDomainHelpers::test_turn_on_light PASSED
tests/test_core.py::TestDomainHelpers::test_toggle_switch PASSED
tests/test_core.py::TestHistory::test_history_with_start PASSED
tests/test_core.py::TestHistory::test_logbook_with_hours PASSED
tests/test_core.py::TestBackend::test_normalize_base_no_scheme PASSED
tests/test_core.py::TestBackend::test_normalize_base_scheme PASSED
tests/test_core.py::TestBackend::test_normalize_base_invalid_raises PASSED
tests/test_core.py::TestBackend::test_ws_url_http PASSED
tests/test_core.py::TestBackend::test_ws_url_https PASSED
tests/test_core.py::TestBackend::test_bearer_header_set PASSED
tests/test_core.py::TestBackend::test_no_bearer_when_token_empty PASSED
tests/test_core.py::TestBackend::test_connection_refused_raises PASSED
tests/test_core.py::TestCLIHelpers::test_parse_kv_string PASSED
tests/test_core.py::TestCLIHelpers::test_parse_kv_int PASSED
tests/test_core.py::TestCLIHelpers::test_parse_kv_bool PASSED
tests/test_core.py::TestCLIHelpers::test_parse_kv_object PASSED
tests/test_core.py::TestCLIHelpers::test_parse_kv_invalid PASSED
tests/test_full_e2e.py::TestLiveSystem::test_status PASSED
tests/test_full_e2e.py::TestLiveSystem::test_config PASSED
tests/test_full_e2e.py::TestLiveSystem::test_core_state PASSED
tests/test_full_e2e.py::TestLiveSystem::test_components PASSED
tests/test_full_e2e.py::TestLiveSystem::test_error_log PASSED
tests/test_full_e2e.py::TestLiveStates::test_set_and_get PASSED
tests/test_full_e2e.py::TestLiveStates::test_list_with_domain PASSED
tests/test_full_e2e.py::TestLiveStates::test_count_by_domain PASSED
tests/test_full_e2e.py::TestLiveServices::test_list_includes_persistent_notification PASSED
tests/test_full_e2e.py::TestLiveServices::test_call_persistent_notification PASSED
tests/test_full_e2e.py::TestLiveServices::test_call_homeassistant_check_config PASSED
tests/test_full_e2e.py::TestLiveEvents::test_list_listeners PASSED
tests/test_full_e2e.py::TestLiveEvents::test_fire_event PASSED
tests/test_full_e2e.py::TestLiveTemplate::test_render_now PASSED
tests/test_full_e2e.py::TestLiveTemplate::test_render_state PASSED
tests/test_full_e2e.py::TestLiveRegistry::test_area_list PASSED
tests/test_full_e2e.py::TestLiveRegistry::test_device_list PASSED
tests/test_full_e2e.py::TestLiveRegistry::test_entity_list PASSED
tests/test_full_e2e.py::TestLiveAutomation::test_reload_succeeds PASSED
tests/test_full_e2e.py::TestLiveScript::test_reload_succeeds PASSED
tests/test_full_e2e.py::TestLiveLogbook::test_logbook_returns_list PASSED
tests/test_full_e2e.py::TestCLISubprocess::test_help_runs PASSED
tests/test_full_e2e.py::TestCLISubprocess::test_config_show_json PASSED
tests/test_full_e2e.py::TestCLISubprocess::test_config_test_json PASSED
tests/test_full_e2e.py::TestCLISubprocess::test_system_info_json PASSED
tests/test_full_e2e.py::TestCLISubprocess::test_system_config_json PASSED
tests/test_full_e2e.py::TestCLISubprocess::test_state_set_get_via_cli PASSED
tests/test_full_e2e.py::TestCLISubprocess::test_service_call_dry_run PASSED
tests/test_full_e2e.py::TestCLISubprocess::test_service_call_via_subprocess PASSED
tests/test_full_e2e.py::TestCLISubprocess::test_template_render_via_cli PASSED
tests/test_full_e2e.py::TestCLISubprocess::test_area_list_json_via_cli PASSED
tests/test_full_e2e.py::TestCLISubprocess::test_state_counts_via_cli PASSED
tests/test_full_e2e.py::TestCLISubprocess::test_state_list_ids_only PASSED

======================== 95 passed, 7 warnings in 5.51s ========================
```

### Coverage Notes

- **Core REST surface (`/api/`, `/api/config`, `/api/states`, `/api/services`,
  `/api/events`, `/api/template`, `/api/error_log`, `/api/components`,
  `/api/core/state`)** — fully covered by both unit and live E2E tests.
- **WebSocket registry surface (`config/area_registry/list`,
  `config/device_registry/list`, `config/entity_registry/list`,
  `system_health/info`)** — covered by unit tests + live E2E tests.
- **WebSocket subscriptions (`subscribe_events`)** — implementation is wired in
  the CLI (`event subscribe`) but full streaming verification requires a
  longer-running test; not in the automated suite.
- **Service domains tested live**: `homeassistant.check_config`,
  `persistent_notification.create`, `automation.reload`, `script.reload`.
- **Templating**: live render via the real Jinja engine.
- **Subprocess CLI**: 12 tests via `_resolve_cli("cli-anything-homeassistant")`
  with `CLI_ANYTHING_FORCE_INSTALLED=1` to guarantee the installed entry
  point is used.

### Known Limitations

- HA's `recovery_mode` requires the `home-assistant-frontend` package even
  though our test config doesn't enable `frontend`. This is documented in
  the README install notes.
- HA `2025.1.4` is the last release supporting Python 3.12; newer HA versions
  require Python 3.13+. The CLI itself supports Python 3.10+.

---

## Refine pass — daily-driver action shortcuts

This pass exposed orphan core modules that were already implemented but not
wired into the CLI, plus added a new `scenes` core module.

### New CLI groups wired

| Group              | Backing core module(s)                 | New tests added |
|--------------------|-----------------------------------------|-----------------|
| `scene`            | new `core/scenes.py`                    | unit + wiring + 2 live E2E |
| `weather`          | `core/weather_advanced.py`              | wiring + 1 live E2E |
| `shopping-list`    | `core/shopping_list.py`                 | wiring |
| `todo`             | `core/todos.py`                         | wiring |
| `lock`             | `core/service_shortcuts.py`             | wiring |
| `alarm`            | `core/service_shortcuts.py` (+`alarm_arm_vacation`) | unit + wiring |
| `search`           | `core/singletons.py::search_related`    | wiring + 1 live E2E |
| `entity expose`    | `core/expose_entity.py`                 | wiring + 1 live E2E |

### New / extended functions

- `core/scenes.py` (new): `list_scenes`, `activate`, `apply`, `create`,
  `reload`.
- `core/service_shortcuts.py`: added `alarm_arm_vacation`.

### Test results — refine pass

```
$ python3 -m pytest tests/ -q --tb=no --ignore=tests/test_full_e2e.py
1511 passed in 1.14s

$ python3 -m pytest tests/test_full_e2e.py -q --tb=no
39 passed in 7.45s
```

- **Before refine:** ~733 unit tests, 33 live E2E.
- **After refine:** 1,511 unit + 39 live E2E (added ~778 unit + 6 live tests).
- **Regressions:** 0.

The new tests live in:

- `tests/test_scenes.py` — unit tests for the new `core/scenes.py` module.
- `tests/test_cli_refine_wiring.py` — Click `CliRunner` wiring tests for all
  eight new groups; uses `make_client` monkey-patch to inject `FakeClient`.
- `tests/test_service_shortcuts.py` — three new tests for `alarm_arm_vacation`.
- `tests/test_full_e2e.py::TestCLISubprocess` — six new live tests:
  `test_scene_create_and_activate`, `test_scene_apply_adhoc`,
  `test_search_related_entity`, `test_entity_expose_list`,
  `test_weather_list_filters_to_domain`, `test_help_lists_new_groups`.

---

## Refine pass v2 — voice & multi-modal

This pass wired six more orphan modules into the CLI.

### New CLI groups wired

| Group              | Backing core module(s)                  | Tests added |
|--------------------|------------------------------------------|-------------|
| `camera`           | `core/camera_ws.py`                      | wiring (8)  |
| `device-automation`| `core/device_automation.py`              | wiring (4)  |
| `assist` (extensions: `agents`, `sentences`, `debug`, `satellites`, `languages`) | `core/conversation_advanced.py` | wiring (6) + 3 live (skip on older HA) |
| `assist-satellite` | `core/assist_satellite.py`               | wiring (4)  |
| `mobile-app`       | `core/mobile_app.py`                     | wiring (1)  |
| `media`            | `core/media_source.py`                   | wiring (5) + 1 live |

### Test config change

To exercise the new groups against a live HA boot, `tests/conftest.py` now
loads two more lightweight integrations into the test config:

- `conversation:` — required for the `assist` group's WS commands
- `media_source:` — required for `media browse`/`resolve`/`remove`

`assist_pipeline:` was NOT added (it pulls heavy STT/TTS dependencies).
The three live tests that need `assist_pipeline/*` WS commands or the
newer `conversation/agent/list` (introduced in HA versions after 2025.1.4)
skip cleanly via `_skip_if_unknown_command` rather than fail.

### Test results — refine pass v2

```
$ python3 -m pytest tests/ -q --ignore=tests/test_full_e2e.py
1539 passed in 1.19s

$ python3 -m pytest tests/test_full_e2e.py -q
41 passed, 3 skipped in 8.73s
```

- **Before pass v2:** 1,511 unit + 39 live E2E.
- **After pass v2:** 1,539 unit + 41 live E2E (+ 3 conditional skips).
- **Regressions:** 0.

The new tests live in:

- `tests/test_cli_refine_wiring_v2.py` — 28 CliRunner wiring tests covering
  camera, device-automation, assist extensions, assist-satellite, mobile-app,
  media.
- `tests/test_full_e2e.py::TestCLISubprocess` — 5 new live tests:
  `test_help_lists_v2_groups`, `test_media_browse_root_live`,
  `test_assist_languages_live`, `test_assist_satellites_live`,
  `test_assist_agents_live` (the last three skip on HA builds that don't
  ship the corresponding WS command).

---

## Refine pass v3 — sysadmin & auth

This pass wired the operations-and-auth orphans: per-integration WS log
control, refresh-token administration, full user CRUD with credentials,
category registry, integration manifests, analytics, OAuth application
credentials, repairs issue introspection, USB / Zigbee discovery, hardware
info, and the runtime error log.

### New CLI groups/subgroups wired

| Surface                       | Backing module        | Tests added |
|-------------------------------|-----------------------|-------------|
| `auth me`, `auth sign-path`   | `core/auth_tokens.py` | wiring (2) + 2 live |
| `auth tokens` extensions      | `core/auth_tokens.py` | wiring (6) + 1 live |
| `auth user` subgroup          | `core/user_admin.py`  | wiring (7) |
| `category`                    | `core/categories.py`  | wiring (6) + 1 live |
| `logger info-ws / level-get / level-set` | `core/logger_ws.py` | wiring (4) + 1 live |
| `system manifest`             | `core/system_ops.py`  | wiring (2) + 1 live |
| `system analytics`            | `core/system_ops.py`  | wiring (3) + 1 live |
| `system app-credentials`      | `core/system_ops.py`  | wiring (2) |
| `system issue`                | `core/system_ops.py`  | wiring (3) |
| `system usb-scan`, `zha-permit-join` | `core/singletons.py` | wiring (2) |
| `system hardware-info / board-info / cpu-info` | `core/hardware_info.py` | wiring (3) |
| `system log errors / clear / write` | `core/system_log.py` | wiring (4) + 1 live |

### Test results — refine pass v3

```
$ python3 -m pytest tests/ -q --ignore=tests/test_full_e2e.py
1583 passed in 1.25s

$ python3 -m pytest tests/test_full_e2e.py -q
50 passed, 3 skipped in 11.26s
```

- **Before pass v3:** 1,539 unit + 41 live E2E.
- **After pass v3:** 1,583 unit + 50 live E2E.
- **Regressions:** 0.

New tests in:

- `tests/test_cli_refine_wiring_v3.py` — 44 CliRunner wiring tests across
  auth core extensions, auth tokens, auth user, category, logger WS variants,
  system extensions, and the system_log subgroup.
- `tests/test_full_e2e.py::TestCLISubprocess` — 9 new live tests:
  `test_help_lists_v3_groups`, `test_auth_me_live`, `test_auth_sign_path_live`,
  `test_auth_tokens_list_live`, `test_logger_info_ws_live`,
  `test_system_manifest_list_live`, `test_system_log_errors_live`,
  `test_system_analytics_get_live`, `test_category_list_live`. Each `WS`-
  backed one skips cleanly via `_skip_if_unknown_command` on older HA builds.


## Refine pass v4 — entity-control shortcuts

Added ergonomic per-domain shortcut groups so agents don't have to hand-craft
`service call <domain> <svc> -d '<json>'` for everyday entity control. Each
group is a thin wrapper over `services/<domain>/<service>` with typed Click
options and prefix-validated entity_ids.

### New CLI groups wired

| Group          | Backing module        | Subcommands |
|----------------|-----------------------|-------------|
| `light`        | `core/entity_control.py` | `on`, `off`, `toggle` |
| `media-player` | `core/entity_control.py` | `play`, `pause`, `stop`, `play-pause`, `next`, `previous`, `volume-set`, `volume-up`, `volume-down`, `mute`, `select-source`, `select-sound-mode`, `play-media`, `shuffle`, `repeat`, `clear-playlist`, `turn-on`, `turn-off`, `join`, `unjoin` |
| `climate`      | `core/entity_control.py` | `set-temperature`, `set-hvac-mode`, `set-fan-mode`, `set-preset`, `set-humidity`, `set-swing`, `turn-on`, `turn-off` |
| `cover`        | `core/entity_control.py` | `open`, `close`, `stop`, `toggle`, `set-position`, `set-tilt`, `open-tilt`, `close-tilt`, `stop-tilt` |
| `fan`          | `core/entity_control.py` | `turn-on`, `turn-off`, `toggle`, `set-percentage`, `set-preset`, `set-direction`, `oscillate`, `increase`, `decrease` |
| `vacuum`       | `core/entity_control.py` | `start`, `stop`, `pause`, `return-to-base`, `locate`, `clean-spot`, `set-fan-speed`, `send-command` |
| `humidifier`   | `core/entity_control.py` | `turn-on`, `turn-off`, `toggle`, `set-humidity`, `set-mode` |
| `water-heater` | `core/entity_control.py` | `turn-on`, `turn-off`, `set-temperature`, `set-operation-mode`, `set-away-mode` |
| `valve`        | `core/entity_control.py` | `open`, `close`, `stop`, `toggle`, `set-position` |
| `lawn-mower`   | `core/entity_control.py` | `start`, `pause`, `dock` |
| `siren`        | `core/entity_control.py` | `on`, `off`, `toggle` |
| `remote`       | `core/entity_control.py` | `turn-on`, `turn-off`, `toggle`, `send-command`, `learn-command`, `delete-command` |
| `number`       | `core/entity_control.py` | `set` |
| `select`       | `core/entity_control.py` | `set`, `next`, `previous`, `first`, `last` |
| `button`       | `core/entity_control.py` | `press` |
| `text`         | `core/entity_control.py` | `set` |
| `notify`       | `core/entity_control.py` | `send` |

### Test results — refine pass v4

```
$ python3 -m pytest tests/ -q --ignore=tests/test_full_e2e.py
1755 passed in 1.53s
```

- **Before pass v4:** 1,583 unit tests.
- **After pass v4:** 1,755 unit tests (+172).
- **Regressions:** 0.

New tests in:

- `tests/test_entity_control.py` — 120 unit tests against the `entity_control`
  core module. Each function is exercised for happy path, prefix validation,
  drop-None semantics, and range/value validation where applicable.
- `tests/test_cli_entity_control_wiring.py` — 52 Click-runner wiring tests
  covering every new subcommand against the recorded `service_calls` log of
  the shared `FakeClient`.

## Refine pass v5 — powercalc CLI + entity prune + recorder top + backup size

This pass addressed gaps that surfaced during real-world sessions:

1. **No `powercalc` CLI group** — `core/powercalc.py` already had the safety
   wrappers, but every operation went through ad-hoc `python3 <<PY`. Wired a
   full Click surface: `list`, `create`, `set-template`, `set-power`,
   `reload`, plus nested `group` (members/add-members/remove-members/set-members).
2. **No entity-prune command** — the 96.7k UniFi cleanup was hand-rolled.
   Added `entity restored`, `entity orphans`, and `entity prune` (with
   `--platform`/`--restored`/`--orphan`/`--disabled-by`/`--entity-id`
   filters, default-dry-run, user-disabled protection, per-entity
   error tolerance via `bulk_remove_entities`).
3. **`backup list/show` always returned `size: null`** — HA stores `size`,
   `protected`, and `agent_ids` per agent. Added `_enrich()` in
   `core/backup.py` that promotes these to top-level fields, and updated
   the CLI list view to read them.
4. **No "what's eating the recorder" probe** — added `recorder top`
   (state-change count per entity over `--hours`, with `--domain` scope).

### New CLI groups / commands wired

| Surface                              | Backing module          |
|--------------------------------------|-------------------------|
| `powercalc list/create/set-template/set-power/reload` | `core/powercalc.py` |
| `powercalc group {members,add-members,remove-members,set-members}` | `core/powercalc.py` |
| `entity restored / orphans / prune`  | `core/registry.py` (new: `remove_entity`, `bulk_remove_entities`, `find_restored_entities`, `find_orphan_entities`) |
| `recorder top`                       | `core/recorder.py` (new: `top_entities`) |
| `backup list` (size promotion fix)   | `core/backup.py` (new: `_enrich`) |

### Test results — refine pass v5

```
$ python3 -m pytest tests/ -q --ignore=tests/test_full_e2e.py
1797 passed in 1.54s
```

- **Before pass v5:** 1,755 unit tests.
- **After pass v5:** 1,797 unit tests (+42).
- **Regressions:** 0.

New tests in:

- `tests/test_v5_refine_core.py` — 26 unit tests against the new core
  helpers (backup enrichment, powercalc list/reload/set-template/set-power
  flow incl. the fixed-step menu traversal, registry remove/bulk-remove
  with per-entity error tolerance + progress callback, find_restored and
  find_orphan classification, recorder.top_entities ordering/domain
  filter/limit/unknown-mode rejection).
- `tests/test_v5_refine_cli_wiring.py` — 16 CliRunner wiring tests
  covering every new CLI surface end-to-end against the recorded
  FakeClient `service_calls`/`ws_calls` log.

## Refine pass v6 — powercalc calibration & audit (v1.37.0)

Driven by the EV-charger fix session, which surfaced two things:
the powercalc Home Total was sitting at 20 % coverage of the smart
meter, and there was no way to know which sub-groups deserved attention
without eyeballing the energy dashboard. Built four new commands:

1. **`powercalc audit`** — passive coverage report. Reads `--hours` of
   history for the smart-meter and the Home Total powercalc rollup,
   computes time-weighted means, gap, and coverage ratio. Then ranks
   every `Power · …` sub-group by its mean contribution. Read-only.

2. **`powercalc calibrate <entry_id>`** — active single-shot. Takes a
   baseline measurement → calls `--service-on` against `--target` →
   waits for stabilisation → takes a load measurement → computes delta.
   Optional `--service-off` returns the device to baseline after. With
   `--apply`, writes the delta into the entry's fixed power via
   `powercalc set-power`.

3. **`powercalc calibrate-template <entry_id>`** — active multi-step
   for variable devices. Walks the device through each value in
   `--states`, measures delta per state, fits a piecewise Jinja
   template keyed on `--attribute`, and optionally writes via
   `powercalc set-template`.

4. **`powercalc auto-calibrate`** — *passive median-of-transitions*.
   Scans recorder history over `--hours`, finds clean ON→OFF / OFF→ON
   transitions for every powercalc virtual_power entry's source entity
   (rejecting any whose smart-meter delta is contaminated by other
   tracked devices changing within `±--quiet-seconds`), takes the
   median across N clean samples, and proposes a fixed_power update.
   Default dry-run; `--apply` commits.

The four together cover all three calibration shapes:
"actively flip a switch", "actively walk through states", and "passively
mine my history".

### Test results — v1.37.0

```
$ python3 -m pytest tests/ -q --ignore=tests/test_full_e2e.py
1814 passed in 1.55s
```

- **Before:** 1,797 unit tests.
- **After:** 1,814 (+17). 0 regressions.

New tests in `tests/test_powercalc_calibration.py`:

- `TestMeasure` (2) — averaging across multiple reads + skipping
  unavailable readings.
- `TestTimeWeightedMean` (3) — basic time-weighted math, empty input,
  single-point degenerate case.
- `TestAudit` (1) — full end-to-end: smart-meter mean, home-total
  mean, coverage ratio, group ranking by contribution.
- `TestCalibrate` (2) — baseline+load delta computation + service-call
  recording; `--apply` writes via `powercalc.set_fixed_power`.
- `TestCalibrateTemplate` (1) — walks five state values, builds
  template referencing the source entity, mid-point cuts as expected.
- `TestAutoCalibrate` (3) — finds clean transitions while rejecting
  noisy ones (other-device within ±quiet-seconds), `--apply` writes
  the median, low-sample-count is reported with a `skip_reason`.
- `TestCli` (5) — CLI wiring for all four commands.

### Live verification (against home.k8s.home)

```
$ cli-anything-homeassistant --json powercalc audit --hours 1 --top 5
window: 1.0h
smart_meter: mean=5634W min=798 max=10830
home_total:  mean=4017W min=914 max=10936
delta_mean: 1617W  coverage: 0.713
top 5 groups by contribution:
   40.1%  mean=2288W  Power · Outside
   20.2%  mean=1152W  Power · Ground Floor
   15.1%  mean= 860W  Power · Office
   10.2%  mean= 584W  Power · Appliances
    5.3%  mean= 302W  Power · Upstairs
```

The Outside group's 40 % share confirms the EV-charger fix from the
prior session is now the dominant contribution. Coverage is 71 % over
this window (was 20 % before the fix).

## Refine pass v7 — Tier-2 regression calibration (v1.38.0)

Where v1.37.0's `auto-calibrate` does median-of-clean-transitions, this
pass fits a linear regression of the smart-meter signal against the
binary on/off state of every tracked device simultaneously. Two cases
this catches that the median approach misses:

* Devices that always switch in concert with another device — the
  transition filter rejects too many candidates.
* Devices with no clean OFF→ON transitions (e.g. fridges that cycle
  continuously).

The per-device regression coefficient is the expected smart-meter
delta when that device is on, holding every other tracked device
fixed — which is what powercalc's fixed_power should be set to.
Output also reports R² (model quality) and per-coefficient 95 %
confidence interval.

### Implementation

* `core/powercalc_regression.py::regress(client, *, hours,
  interval_seconds, ...)` — pulls per-device + smart-meter history,
  resamples to a 1-min grid, drops always-on / always-off devices,
  fits OLS via `numpy.linalg.lstsq`, reports per-coefficient std-err
  + CI, and optionally writes via `powercalc.set_fixed_power`.

* `core/powercalc_regression.py::_fit_ols(X, y)` — pure-numpy OLS:
  adds the intercept column, computes residuals, R², and the
  variance-covariance matrix for per-coefficient standard errors.

* CLI: `powercalc regress [--hours 168] [--interval 60]
  [--title-contains <substr>] [--min-on 0.005] [--min-off 0.005]
  [--apply]`. Default dry-run.

New dependency: `numpy>=1.24` (already a transitive of Home Assistant
core, so no fresh install impact).

### Test results — v1.38.0

```
$ python3 -m pytest tests/ -q --ignore=tests/test_full_e2e.py
1826 passed in 1.57s
```

- **Before:** 1,814 unit tests.
- **After:** 1,826 (+12). 0 regressions.

New tests in `tests/test_powercalc_regression.py`:

- `TestEncoders` (2) — binary on/off classification of state strings.
- `TestResample` (2) — forward-fill onto a fixed grid; numeric encoder
  for the smart-meter target.
- `TestFitOls` (1) — recovers known coefficients from synthetic data
  to within ±2W and R² > 0.99.
- `TestRegress` (5) — end-to-end:
  - Two-device synthetic dataset (800W + 200W); regression recovers
    both to within ±5W including per-coef CI computation.
  - Always-on device is dropped with `drop_reason` (no variance).
  - `--apply` writes via `set_fixed_power`.
  - Empty-history input short-circuits with a warning.
  - Title-filter is forwarded to `powercalc.list_entries`.
- `TestCli` (2) — `powercalc regress --hours/--interval/--title-contains
  /--min-on/--min-off/--apply` flag wiring.

---

## v1.39.0 — refine pass: zone / webhook / image / profiler

Four new command groups + core modules, all wired into the CLI's main Click
tree and covered by isolated FakeClient unit tests.

### New core modules

* `core/zone.py` — storage zone CRUD via `config/zone/*` WS, plus
  `list_state_zones()` and `entities_in_zone()` helpers built off the
  state machine.
* `core/webhook.py` — webhook discovery (aggregates `webhook/list` WS,
  automation YAML triggers, and `mobile_app/list_for_user`) + `trigger`
  (POST/PUT/GET/HEAD on `/api/webhook/<id>`) + `generate_id` + cloudhook
  CRUD via `cloud/cloudhook/*`.
* `core/image.py` — `image.*` entity domain: listing with attribute
  scrubbing, `auth/sign_path`-minted proxy URLs, binary snapshot to disk
  (signed or direct), and `subscribe_updates` for state-changed events.
* `core/profiler.py` — thin service wrappers over every `profiler.*`
  service plus a `status` probe that reads `/api/components` and
  `/api/services` to confirm the integration is loaded.

### New CLI groups

| Group | Commands |
|-------|----------|
| `zone` | `list`, `state-list`, `find`, `create`, `update`, `delete`, `entities` |
| `webhook` | `list`, `trigger`, `generate-id`, `cloudhooks`, `cloudhook-create`, `cloudhook-delete` |
| `image` | `list`, `show`, `snapshot`, `proxy-url`, `subscribe` |
| `profiler` | `start`, `memory`, `dump-log-objects`, `log-thread-frames`, `log-event-loop-scheduled`, `log-current-tasks`, `lru-stats`, `set-asyncio-debug`, `log-events`, `status` |

### Test results — v1.39.0

```
$ python3 -m pytest tests/ -q --ignore=tests/test_full_e2e.py
1904 passed in 1.91s
```

- **Before:** 1,826 unit tests.
- **After:** 1,904 (+78). 0 regressions.

Breakdown of new tests:

- `tests/test_zone.py` (20) — `list/find/create/update/delete` happy paths
  + boundary cases (empty ident, missing coords, partial update payloads,
  passive flag) + `list_state_zones` filtering + `entities_in_zone`
  resolution by entity_id and by friendly_name.
- `tests/test_webhook.py` (21) — registered list, automation-trigger
  discovery (both `trigger` and `triggers` schema variants), aggregator
  totals, `trigger()` with POST happy path / unknown-id guard + bypass /
  bad-method / GET-via-session, `generate_id` uniqueness, cloudhooks dict
  flattening, cloudhook create/delete payload shape.
- `tests/test_image.py` (19) — listing with and without attributes,
  proxy-url signed and unsigned paths (verifies `auth/sign_path` call
  shape), `snapshot()` direct + signed (header-stripping check) +
  overwrite guard + missing-session error path, `subscribe_updates`
  entity-id filtering via `SubscribingFakeClient`.
- `tests/test_profiler.py` (18) — every `profiler.*` service has a
  payload-shape assertion, plus `seconds<=0` rejection on `start` /
  `memory`, plus a `status` test that reads from
  `/api/components` + `/api/services` and gracefully degrades when
  `client.get` raises.

All new code paths are exercised by FakeClient (no live HA required for
unit tests). E2E coverage against a real HA instance lands via the
existing `tests/test_full_e2e.py` harness when run with a populated
`homeassistant` install.
