# Enhancement — active calibration should reject noisy windows

**Status:** ✅ implemented in v1.40.0 (2026-06-02)
**Area:** `cli_anything/homeassistant/core/powercalc_calibration.py`
**Affects:** `calibrate` (single-shot, fixed) and `calibrate_template` (multi-step, variable)

## Shipped

Both gates landed: a **variance gate** (window spread > `--max-variance-w`,
default 50 W, catches untracked spikes) and a **confounder watch** (rejects a
window if another powercalc-profiled source toggles or a natively-metered
`device_class: power` entity moves > 5 W). Windows retry `--max-retries`
times then are excluded; noisy runs never auto-apply. See CHANGELOG [1.40.0]
and `tests/test_powercalc_calibration.py::TestMeasureStable` /
`TestConfounderWatch`. The notes below are the original proposal, kept for
context.

---

## Problem

The **active** calibrators (`calibrate`, `calibrate_template`) do no noise rejection.
Each step is `delta = load_mean − baseline_mean` against the whole-home smart meter,
and the code blindly assumes the device under test is the *only* thing changing on
the circuit during the measurement window. It isn't.

Observed failure (real): calibrating a ~29 W office LED zone against a
~1.1 kW whole-home meter, a 1,400 W microwave switched on mid-walk. Every affected
step banked a poisoned delta (one zone read +854/+1405/+1385/+1383 W — pure
microwave). Nothing flagged it; the run completed "successfully" with garbage.

The **passive** `auto_calibrate` already has the right idea — `_has_other_change()`
rejects transitions where another powercalc source entity toggled within
`±quiet_seconds`. The active path has no equivalent.

## Proposal

Make each measurement window self-validating. Two complementary mechanisms:

### 1. Meter-variance gate (cheap, no extra API surface)
`_measure()` already collects `raw` samples. Add a coefficient-of-variation /
spread check: if the within-window spread exceeds a threshold (abs W or % of mean),
treat the window as contaminated. Re-take it up to `--max-retries` times; if it
still won't settle, mark that step `"noisy": true` and exclude it from the fit
rather than banking it.

- New args: `--max-variance-w` (default e.g. 50), `--max-retries` (default 2).
- `_measure` returns `stdev`/`spread` already-computable from `raw`.

### 2. Event-watch gate (precise, catches discrete loads)
During each baseline/load window, watch for confounders and discard the window if
one fires:
- **Simplest:** sample the smart meter itself; reject if it jumps > `--meter-jump-w`
  (e.g. 100 W) between consecutive reads within a window — the microwave trips this
  instantly.
- **Better:** open a WS `subscribe_events` on `state_changed` for the window and
  reject if any entity *other than the device under test* changes (optionally scoped
  to an `--ignore` list, or to powercalc source entities only, mirroring
  `_has_other_change`).

Reuse the existing WS subscriber in `utils/homeassistant_backend.py`. Mirror
`auto_calibrate`'s `quiet_seconds` semantics so the two paths feel consistent.

## Acceptance
- A confounding load (>`--meter-jump-w`) during a window causes that step to retry,
  then be excluded — never silently averaged in.
- Excluded steps surface in the result (`"noisy"`/`"excluded"` flags + reason).
- Existing happy-path tests unchanged; new tests drive a FakeClient that injects a
  mid-window spike and assert the step is retried/excluded.
- No change to the passive `auto_calibrate` behaviour.

## Notes
- Until this lands, the active path's only defence is operator discipline:
  quiet house + long `--baseline-seconds`/`--load-seconds` windows. Document that
  caveat in `SKILL.md` under the powercalc calibration recipes.
- Small loads (~10–30 W) against a whole-home meter remain marginal even with
  rejection — the real fix for those is a per-circuit CT clamp / smart plug passed
  as `--smart-meter`. Noise rejection makes the whole-home path *usable*, not ideal.
