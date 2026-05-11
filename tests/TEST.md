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

