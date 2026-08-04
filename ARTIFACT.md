# Fix: `str:` prefix to force string values in `-D` / `--data`

## Problem

`service call mqtt publish -D 'payload={"contact":false,"battery":87}'` silently
sent `payload` as a **dict** to Home Assistant. `mqtt.publish` expects `payload`
to be a **string**. The call returned HTTP 200 and published something no
subscriber could parse — a silent failure with no error reported anywhere.

## Root Cause

`parse_kv_pairs` (cli_anything/homeassistant/homeassistant_cli.py, ~line 255)
did `json.loads(val)` on every `-D` value, falling back to the raw string only
on `JSONDecodeError`. A payload that IS valid JSON therefore always became a
dict. The same pattern existed in the WebSocket `--data` path (~line 2305).

## Fix

Added an explicit `str:` prefix convention. A value prefixed with `str:` is
kept as a literal string with the prefix stripped. A shared `_coerce_value()`
helper is used by both `parse_kv_pairs` (REST `service call` / `event fire`)
and the WebSocket `--data` path, so both code paths are fixed consistently.

### Usage

```bash
# Force payload to stay a string (the fix):
cli-anything-homeassistant service call mqtt publish \
  -D 'topic=z2m/Pantry Door' \
  -D 'payload=str:{"contact":false,"battery":87}'

# To send a value that literally starts with "str:", use str:str:
cli-anything-homeassistant service call mqtt publish \
  -D 'payload=str:str:hello'
```

### What changed

1. **cli_anything/homeassistant/homeassistant_cli.py**:
   - Added `_STR_PREFIX = "str:"` constant and `_coerce_value(val)` helper
   - `_coerce_value` checks for `str:` prefix first → returns remainder as string
   - Otherwise tries `json.loads()` → falls back to raw string on `JSONDecodeError`
   - `parse_kv_pairs` now calls `_coerce_value(val)` instead of inline `json.loads`
   - WebSocket `ws_cmd` `--data` path now calls `_coerce_value(raw)` instead of inline `json.loads`
   - `--data` help text for `service call` and `ws` updated to document `str:` convention

2. **tests/test_str_prefix.py** (222 lines, 22 tests):
   - `TestCoerceValue`: 10 unit tests for `_coerce_value` (JSON types, str: prefix, double-escape)
   - `TestParseKvPairs`: 7 tests for `parse_kv_pairs` (str: prefix + unchanged coercion)
   - `TestServiceCallStrPrefix`: 3 CLI tests via FakeClient (string payload, dict without prefix, mixed)
   - `TestWsStrPrefix`: 2 CLI tests for WebSocket --data path (str: prefix + unchanged coercion)

3. **tests/test_str_force_prefix.py** (151 lines, 14 tests):
   - `TestParseKvStrPrefix`: 9 unit tests for `parse_kv_pairs` with str: prefix
   - `TestServiceCallStrPrefix`: 3 CLI tests via FakeClient (string, dict, --dry-run)
   - `TestWsDataStrPrefix`: 2 CLI tests for WebSocket --data path

4. **CHANGELOG.md**: Added v1.47.1 entry documenting the fix.
5. **setup.py**: Bumped version from 1.47.0 → 1.47.1.

## Verification Results

### Full test suite
```
2770 passed, 57 skipped in 2.12s
```

### New tests only
```
36 passed in 0.17s
```

### Coverage
```
Required test coverage of 76% reached. Total coverage: 77.62%
```

### ruff format
```
108 files already formatted
```

### ruff lint
```
(no issues)
```

### --dry-run with str: prefix (payload is a STRING)
```json
{
  "domain": "mqtt",
  "dry_run": true,
  "return_response": false,
  "service": "publish",
  "service_data": {
    "payload": "{\"contact\":false,\"battery\":87}",
    "topic": "z2m/Pantry Door"
  },
  "target": null
}
```

### --dry-run WITHOUT str: prefix (payload is a dict — old behaviour unchanged)
```json
{
  "domain": "mqtt",
  "dry_run": true,
  "return_response": false,
  "service": "publish",
  "service_data": {
    "payload": {
      "battery": 87,
      "contact": false
    },
    "topic": "z2m/Pantry Door"
  },
  "target": null
}
```

## Rubric Checklist

- [x] mqtt.publish can send a JSON payload that arrives at HA as a STRING, not a dict
- [x] The mechanism to force a string value is explicit and discoverable at the call site (`str:` prefix, documented in `--help`)
- [x] Existing -D JSON coercion for numbers, booleans, lists and nested objects still works unchanged
- [x] A unit test using FakeClient asserts the exact service_data sent for both the string case and the coerced case
- [x] The same class of bug is addressed in the WebSocket --data path (~line 2305)
- [x] CHANGELOG.md entry added and setup.py version bumped
- [x] The full test suite passes (2770 passed, 57 skipped)
- [x] ruff format check passes
- [x] ruff lint check passes
- [x] Coverage ≥ 76% (77.62%)
