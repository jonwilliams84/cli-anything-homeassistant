# PDP — cli-anything-homeassistant v1.21.0 → v1.23.0

**Goal:** raise WS-command coverage from ~33% to ~70% across 3 sprints, dispatched
as 17 parallel sub-agents (each unit fully independent, new-files only).

## Universal constraints
- Each unit creates ONLY the two NEW files listed (one core module + one test
  file). Never edit `setup.py`, `SKILL.md`, `conftest.py`, or any existing
  `cli_anything/homeassistant/core/*.py` / `tests/test_*.py`.
- Match patterns in `helpers.py` and `automation.py`: module docstring, ValueError
  on bad input, function docstrings name the WS message type.
- Tests use the FakeClient fixture (auto-injected as `fake_client`).
- Pass criteria: `pytest tests/<your_test_file>.py -v` 100% green.
- Reference HA source at `/home/jonwi/.local/lib/python3.12/site-packages/homeassistant/`
  for exact WS message-type strings and payload schemas.

## Sprint 1 (v1.21.0) — 7 units

| ID | Unit | Model | New module |
|---|---|---|---|
| S1A | Statistics admin | Sonnet | `statistics_admin.py` |
| S1B | Trace list/get/contexts | Sonnet | `trace_debug.py` |
| S1C | Diagnostics + syslog | Sonnet | `diagnostics_dl.py`, `system_log.py` |
| S1D | Todo CRUD | Sonnet | `todos.py` |
| S1E | Live subscriptions | Sonnet | `state_stream.py` |
| S1F | Sections polish | Haiku | `lovelace_sections_ext.py` |
| S1G | Service shortcuts | Haiku | `service_shortcuts.py` |

## Sprint 2 (v1.22.0) — 6 units

| ID | Unit | Model | New module |
|---|---|---|---|
| S2A | Blueprints CRUD | Sonnet | `blueprints.py` |
| S2B | Category registry | Sonnet | `categories.py` |
| S2C | Frontend prefs + template preview | Sonnet | `frontend_prefs.py` |
| S2D | Hardware info + status subscribe | Sonnet | `hardware_info.py` |
| S2E | Conversation/Assist advanced | Sonnet | `conversation_advanced.py` |
| S2F | Energy advanced | Sonnet | `energy_advanced.py` |

## Sprint 3 (v1.23.0) — 4 units

| ID | Unit | Model | New module |
|---|---|---|---|
| S3A | Auth + token management | Sonnet | `auth_tokens.py` |
| S3B | Backup advanced | Sonnet | `backup_advanced.py` |
| S3C | Mobile app push | Haiku | `mobile_app.py` |
| S3D | Weather subscribe + convertibles | Haiku | `weather_advanced.py` |

## Orchestrator (me, after agents land)
1. Verify each agent's new test file passes.
2. Run full suite — no regressions.
3. Bump `setup.py` 1.20.0 → 1.23.0.
4. Update `SKILL.md` with new command groups.
5. Apply view-level fixes to live dashboard (11 subviews missing back_path, etc).
6. Report combined status.
