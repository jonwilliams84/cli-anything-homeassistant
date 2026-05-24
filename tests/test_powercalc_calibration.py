"""v1.37.0 — powercalc calibration & audit tests.

Stubs HA's REST + powercalc helpers; verifies:
  * `_measure` averaging + sample timing (no real sleep)
  * `_time_weighted_mean` math
  * `audit` end-to-end: smart-meter vs home-total + group ranking
  * `calibrate` baseline → service → load → delta → optional apply
  * `calibrate_template` walks states, builds piecewise template
  * `auto_calibrate` filters clean transitions + medians + apply
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from click.testing import CliRunner

from cli_anything.homeassistant.core import (
    powercalc_calibration as cal,
)
from cli_anything.homeassistant import homeassistant_cli as cli_mod


# ─────────────────────────────────────────── helper test client

class _Client:
    """Records HTTP-shape calls; returns canned responses by (verb, path)."""

    def __init__(self):
        self.calls: list[dict] = []
        self.responses: dict[tuple, object] = {}
        # Convenience: service-call recorder.
        self.service_calls: list[dict] = []

    def set(self, verb, path, response):
        self.responses[(verb.upper(), path.lstrip("/"))] = response

    def get(self, path, params=None):
        match = path.lstrip("/").split("?", 1)[0]
        self.calls.append({"verb": "GET", "path": path, "params": params})
        return self.responses.get(("GET", match),
                                  self.responses.get(("GET", path), []))

    def post(self, path, payload=None):
        self.calls.append({"verb": "POST", "path": path, "payload": payload})
        match = path.lstrip("/").split("?", 1)[0]
        if match.startswith("services/"):
            parts = match.split("/")
            if len(parts) >= 3:
                self.service_calls.append({
                    "domain": parts[1], "service": parts[2],
                    "service_data": payload,
                })
        return self.responses.get(("POST", match), {})

    def ws_call(self, msg_type, payload=None):
        # Some powercalc helpers query config_entries via WS. Not used by
        # the calibration module directly except through pc.list_entries
        # for the audit/auto-calibrate group/entry walks — we override
        # those paths in the tests that need them.
        return self.responses.get(("WS", msg_type), [])


def _hist_point(ts: datetime, state) -> dict:
    return {
        "last_changed": ts.isoformat(),
        "state": str(state),
    }


# ─────────────────────────────────────────── _measure / _time_weighted_mean

class TestMeasure:
    def test_averages_readings(self):
        client = _Client()
        client.set("GET", "states/sensor.x",
                    {"entity_id": "sensor.x", "state": "100"})
        out = cal._measure(client, "sensor.x", duration_seconds=0,
                            samples=3, sleep=lambda _: None)
        assert out["n"] == 3
        assert out["mean"] == 100.0

    def test_skips_non_numeric_readings(self):
        client = _Client()
        # Toggle between numeric and "unavailable"
        seq = iter([{"entity_id": "x", "state": "100"},
                    {"entity_id": "x", "state": "unavailable"},
                    {"entity_id": "x", "state": "200"}])

        def fake_get(path, params=None):
            return next(seq)
        client.get = fake_get
        out = cal._measure(client, "sensor.x", duration_seconds=0,
                            samples=3, sleep=lambda _: None)
        assert out["n"] == 2
        assert out["mean"] == 150.0


class TestTimeWeightedMean:
    def test_basic(self):
        t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        points = [
            _hist_point(t0, 100),
            _hist_point(t0 + timedelta(seconds=10), 200),
            _hist_point(t0 + timedelta(seconds=20), 300),
        ]
        out = cal._time_weighted_mean(points)
        # 100W for 10s + 200W for 10s = 1500/20 = 75? no:
        # Held 100W from t0 to t+10 (10s), 200W from t+10 to t+20 (10s).
        # Total span = 20s; weighted = (100*10 + 200*10)/20 = 150.
        assert out["mean"] == 150.0
        assert out["n"] == 3
        assert out["min"] == 100
        assert out["max"] == 300

    def test_empty(self):
        out = cal._time_weighted_mean([])
        assert out["mean"] is None
        assert out["n"] == 0

    def test_single_point(self):
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        out = cal._time_weighted_mean([_hist_point(t0, 42)])
        # span is 0; returns latest value
        assert out["mean"] == 42


# ─────────────────────────────────────────── audit

class TestAudit:
    def _wire(self, client, *, sm_mean=1000, ht_mean=700,
              group_means=None):
        # 2-point history → time-weighted mean = first value
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        t1 = t0 + timedelta(hours=1)

        # Smart meter history
        client.set("GET", "history/period/" + t0.isoformat(),
                    [[_hist_point(t0, sm_mean),
                       _hist_point(t1, sm_mean)]])

        # We need to intercept history calls by entity_id — easiest is
        # a stub get() that filters on params.
        groups = group_means or {}
        all_series = {
            "sensor.smart_meter_electricity_power": sm_mean,
            "sensor.power_home_total_power": ht_mean,
        }
        for eid, mean in groups.items():
            all_series[eid] = mean
        # Patch get to route by params.filter_entity_id
        orig_get = client.get

        def routed_get(path, params=None):
            client.calls.append({"verb": "GET", "path": path,
                                  "params": params})
            if path.startswith("history/period/"):
                eid = (params or {}).get("filter_entity_id")
                v = all_series.get(eid)
                if v is None:
                    return [[]]
                return [[_hist_point(t0, v),
                          _hist_point(t1, v)]]
            return orig_get(path, params)
        client.get = routed_get

        # Stub powercalc.list_entries via the ws_call hook used by
        # config_entries.list_entries
        client.responses[("WS", "config_entries/get")] = [
            {"entry_id": f"g_{name}",
             "title": f"Power · {name}",
             "domain": "powercalc",
             "state": "loaded"}
            for name in groups.keys() if False  # placeholder
        ]
        # Build entries list matching group title → entity_id mapping
        entries = []
        for eid, _ in groups.items():
            # eid like sensor.power_lounge_power → title "Power · Lounge"
            base = eid.removeprefix("sensor.power_").removesuffix("_power")
            title = "Power · " + base.replace("_", " ").title()
            entries.append({
                "entry_id": f"g_{base}",
                "title": title,
                "domain": "powercalc",
                "state": "loaded",
            })
        client.responses[("WS", "config_entries/get")] = entries

    def test_full_audit(self):
        client = _Client()
        self._wire(client, sm_mean=10000, ht_mean=8500, group_means={
            "sensor.power_outside_power": 7000,
            "sensor.power_climate_power": 1200,
            "sensor.power_lighting_power": 300,
        })
        out = cal.audit(client, hours=1, top_n=5)
        assert out["smart_meter"]["mean"] == 10000
        assert out["home_total"]["mean"] == 8500
        assert out["delta_mean"] == 1500.0
        assert out["coverage_ratio"] == 0.85
        titles = [g["title"] for g in out["groups"]]
        assert titles == ["Power · Outside", "Power · Climate",
                          "Power · Lighting"]
        assert out["groups"][0]["mean"] == 7000.0
        # Contribution pct = 7000 / (7000+1200+300) = 82.4%
        assert out["groups"][0]["contribution_pct"] == 82.4


# ─────────────────────────────────────────── calibrate (active)

class TestCalibrate:
    def test_basic_delta(self):
        client = _Client()
        # First call (baseline): 200W. After service call: 2000W.
        readings = iter([{"state": "200"}] * 6 + [{"state": "2000"}] * 6)

        def fake_get(path, params=None):
            client.calls.append({"verb": "GET", "path": path})
            if path.startswith("states/"):
                return next(readings)
            return {}
        client.get = fake_get
        # list_entries returns the entry with a known previous power
        client.responses[("WS", "config_entries/get")] = [
            {"entry_id": "E1", "domain": "powercalc", "title": "Tower Fan",
             "options": {"power": 80, "entity_id": "switch.tower_fan"}},
        ]
        out = cal.calibrate(
            client, "E1",
            service_on="switch.turn_on", target="switch.tower_fan",
            baseline_seconds=0, load_seconds=0,
            stabilisation_seconds=0, samples=6,
            apply_=False, sleep=lambda _: None,
        )
        assert out["baseline"]["mean"] == 200
        assert out["load"]["mean"] == 2000
        assert out["delta_w"] == 1800.0
        assert out["previous_fixed_power"] == 80
        assert out["applied"] is False
        # Service call recorded
        assert any(c["service"] == "turn_on" and c["domain"] == "switch"
                   for c in client.service_calls)

    def test_apply_writes_fixed_power(self):
        client = _Client()
        readings = iter([{"state": "100"}] * 6 + [{"state": "500"}] * 6)

        def fake_get(path, params=None):
            if path.startswith("states/"):
                return next(readings)
            return {}
        client.get = fake_get
        client.responses[("WS", "config_entries/get")] = []

        # Capture set_fixed_power calls
        calls = []
        from cli_anything.homeassistant.core import powercalc as pc
        orig = pc.set_fixed_power
        pc.set_fixed_power = lambda c, eid, *, power: calls.append(
            (eid, power)
        ) or {"ok": True}
        try:
            out = cal.calibrate(
                client, "E2",
                service_on="light.turn_on", target="light.x",
                baseline_seconds=0, load_seconds=0,
                stabilisation_seconds=0, samples=6,
                apply_=True, sleep=lambda _: None,
            )
        finally:
            pc.set_fixed_power = orig
        assert out["applied"] is True
        assert calls == [("E2", 400.0)]


# ─────────────────────────────────────────── calibrate_template

class TestCalibrateTemplate:
    def test_walks_states_and_builds_template(self):
        client = _Client()
        # Baseline 100W, then load varies per state: 200/400/700/1100/1700
        sequence = (
            [{"state": "100"}] * 5           # baseline (after off)
            + [{"state": "200"}] * 5          # at 0%
            + [{"state": "400"}] * 5          # at 25%
            + [{"state": "700"}] * 5          # at 50%
            + [{"state": "1100"}] * 5         # at 75%
            + [{"state": "1700"}] * 5         # at 100%
        )
        it = iter(sequence)

        def fake_get(path, params=None):
            if path.startswith("states/"):
                return next(it)
            return {}
        client.get = fake_get

        out = cal.calibrate_template(
            client, "E3",
            source_entity="fan.test", attribute="percentage",
            service_set="fan.set_percentage", state_arg="percentage",
            service_off="fan.turn_off",
            states=[0, 25, 50, 75, 100],
            baseline_seconds=0, load_seconds=0,
            stabilisation_seconds=0, samples=5,
            apply_=False, sleep=lambda _: None,
        )
        assert out["baseline_mean_w"] == 100
        # Deltas: 100/300/600/1000/1600
        deltas = [s["delta_w"] for s in out["steps"]]
        assert deltas == [100.0, 300.0, 600.0, 1000.0, 1600.0]
        # Template should reference the source entity and attribute
        assert "state_attr('fan.test', 'percentage')" in out["template"]
        # Cuts at midpoints (12.5, 37.5, 62.5, 87.5)
        assert "12.5" in out["template"]
        assert "87.5" in out["template"]
        # service-set called 5 times with the right values
        set_calls = [c for c in client.service_calls
                     if c["service"] == "set_percentage"]
        assert len(set_calls) == 5
        assert [c["service_data"]["percentage"] for c in set_calls] == \
               [0, 25, 50, 75, 100]


# ─────────────────────────────────────────── auto_calibrate (passive)

class TestAutoCalibrate:
    def test_finds_clean_transitions(self):
        client = _Client()
        t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Two devices: tower_fan (target) and unrelated_light (potential noise).
        # tower_fan transitions OFF→ON at t=100s, t=300s, t=500s.
        # unrelated_light transitions at t=305s (within ±10s of one of them —
        # should disqualify the t=300s sample).
        # Smart meter: 200W baseline, jumps to 1700W during fan-on periods.
        def at(secs, state):
            return _hist_point(t0 + timedelta(seconds=secs), state)

        fan_hist = [
            at(50,  "off"),
            at(100, "on"),
            at(200, "off"),
            at(300, "on"),
            at(400, "off"),
            at(500, "on"),
            at(600, "off"),
        ]
        light_hist = [
            at(0,   "off"),
            at(305, "on"),  # noise too close to fan's t=300 transition
            at(350, "off"),
        ]
        # Smart meter: piecewise. Pre each on (≤t-1s): 200W. Post (t+10..40s): 1700W.
        sm_points = []
        for t_offset in range(0, 700, 5):
            tt = t0 + timedelta(seconds=t_offset)
            # Compute expected aggregate at time tt:
            # The fan adds 1500W when on; we model it explicitly.
            fan_on = False
            for h in fan_hist:
                ts = datetime.fromisoformat(h["last_changed"])
                if ts > tt:
                    break
                fan_on = (h["state"] == "on")
            sm_points.append(_hist_point(tt, 200 + (1500 if fan_on else 0)))

        # Route get()
        def routed_get(path, params=None):
            client.calls.append({"verb": "GET", "path": path,
                                  "params": params})
            if path.startswith("history/period/"):
                eid = (params or {}).get("filter_entity_id")
                if eid == cal.DEFAULT_SMART_METER:
                    return [[*sm_points]]
                if eid == "switch.tower_fan":
                    return [[*fan_hist]]
                if eid == "light.unrelated":
                    return [[*light_hist]]
            return {}
        client.get = routed_get

        # Two powercalc entries (the fan + the light)
        client.responses[("WS", "config_entries/get")] = [
            {"entry_id": "E_FAN", "domain": "powercalc",
             "title": "Tower Fan",
             "options": {"entity_id": "switch.tower_fan", "power": 80}},
            {"entry_id": "E_LIGHT", "domain": "powercalc",
             "title": "Light",
             "options": {"entity_id": "light.unrelated", "power": 50}},
        ]

        out = cal.auto_calibrate(
            client, hours=1,
            pre_window_seconds=30, post_window_seconds=20,
            quiet_seconds=10, min_samples=2, apply_=False,
        )
        cand_by_id = {c["entry_id"]: c for c in out["candidates"]}
        fan = cand_by_id["E_FAN"]
        # t=100 and t=500 transitions are clean; t=300 is rejected.
        # So fan should have 2 samples → meets min_samples=2.
        assert fan["samples"] == 2
        # Median delta ~ 1500W (200 → 1700)
        assert 1400 <= (fan["median_delta_w"] or 0) <= 1600
        assert fan["previous_power_w"] == 80
        assert fan["applied"] is False

    def test_apply_writes(self):
        client = _Client()
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

        def at(secs, state):
            return _hist_point(t0 + timedelta(seconds=secs), state)
        fan_hist = []
        sm_points = []
        # 6 clean ON transitions, each adding +1000W for 40s
        for i in range(6):
            base_t = 100 + i * 200
            fan_hist.extend([at(base_t, "on"), at(base_t + 60, "off")])
            for off in range(-30, 0, 5):
                sm_points.append(_hist_point(
                    t0 + timedelta(seconds=base_t + off), 200))
            for off in range(10, 51, 5):
                sm_points.append(_hist_point(
                    t0 + timedelta(seconds=base_t + off), 1200))

        def routed_get(path, params=None):
            if path.startswith("history/period/"):
                eid = (params or {}).get("filter_entity_id")
                if eid == cal.DEFAULT_SMART_METER:
                    return [[*sm_points]]
                if eid == "switch.tower_fan":
                    return [[*fan_hist]]
            return {}
        client.get = routed_get
        client.responses[("WS", "config_entries/get")] = [
            {"entry_id": "E_FAN", "domain": "powercalc",
             "title": "Tower Fan",
             "options": {"entity_id": "switch.tower_fan", "power": 80}},
        ]
        # Capture set_fixed_power
        from cli_anything.homeassistant.core import powercalc as pc
        orig = pc.set_fixed_power
        seen = []
        pc.set_fixed_power = lambda c, eid, *, power: seen.append(
            (eid, power)) or {"ok": True}
        try:
            out = cal.auto_calibrate(
                client, hours=1, min_samples=4, apply_=True,
            )
        finally:
            pc.set_fixed_power = orig
        c = next(c for c in out["candidates"] if c["entry_id"] == "E_FAN")
        assert c["samples"] >= 4
        assert c["applied"] is True
        assert seen and seen[0][0] == "E_FAN"
        assert 900 <= seen[0][1] <= 1100   # delta ~ 1000W

    def test_low_sample_count_skipped(self):
        client = _Client()
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        # Smart-meter has data but switch.x has no transitions
        sm = [_hist_point(t0 + timedelta(seconds=i * 10), 200)
              for i in range(5)]

        def routed_get(path, params=None):
            if path.startswith("history/period/"):
                eid = (params or {}).get("filter_entity_id")
                if eid == cal.DEFAULT_SMART_METER:
                    return [list(sm)]
                if eid == "switch.x":
                    return [[]]
            return {}
        client.get = routed_get
        client.responses[("WS", "config_entries/get")] = [
            {"entry_id": "E_X", "domain": "powercalc",
             "title": "X", "options": {"entity_id": "switch.x", "power": 50}},
        ]
        out = cal.auto_calibrate(client, hours=1, min_samples=5,
                                  apply_=False)
        c = out["candidates"][0]
        assert c["median_delta_w"] is None
        assert c["samples"] == 0
        assert c["applied"] is False
        assert "clean samples" in c["skip_reason"]


# ─────────────────────────────────────────── CLI wiring

@pytest.fixture
def runner(monkeypatch):
    client = _Client()
    monkeypatch.setattr(cli_mod, "make_client", lambda ctx: client)
    return CliRunner(), client


def _invoke(runner, *args):
    return runner.invoke(
        cli_mod.cli, ["--json"] + list(args),
        obj={"url": "http://x", "token": "t", "verify_ssl": False,
             "timeout": 5, "as_json": True, "config_path": None},
    )


class TestCli:
    def test_audit_passes_hours_through(self, runner, monkeypatch):
        runn, client = runner
        captured = {}

        def fake_audit(c, **kw):
            captured.update(kw)
            return {"window_hours": kw["hours"], "smart_meter": {"mean": None},
                    "home_total": {"mean": None}, "delta_mean": None,
                    "coverage_ratio": None, "groups": []}
        monkeypatch.setattr(
            "cli_anything.homeassistant.core.powercalc_calibration.audit",
            fake_audit,
        )
        r = _invoke(runn, "powercalc", "audit", "--hours", "12", "--top", "3")
        assert r.exit_code == 0, r.output
        assert captured["hours"] == 12.0
        assert captured["top_n"] == 3

    def test_calibrate_dry_run(self, runner, monkeypatch):
        runn, client = runner
        captured = {}

        def fake_calibrate(c, entry_id, **kw):
            captured["entry_id"] = entry_id
            captured.update(kw)
            return {"entry_id": entry_id, "delta_w": 1234, "applied": False,
                    "baseline": {"mean": 0}, "load": {"mean": 1234},
                    "previous_fixed_power": None,
                    "service_on": kw["service_on"], "service_off": None,
                    "smart_meter": "x"}
        monkeypatch.setattr(
            "cli_anything.homeassistant.core.powercalc_calibration.calibrate",
            fake_calibrate,
        )
        r = _invoke(runn, "powercalc", "calibrate", "E1",
                    "--service-on", "switch.turn_on",
                    "--target", "switch.tower_fan",
                    "--baseline-seconds", "1",
                    "--load-seconds", "1",
                    "--stabilisation-seconds", "0",
                    "--samples", "2")
        assert r.exit_code == 0, r.output
        assert captured["entry_id"] == "E1"
        assert captured["service_on"] == "switch.turn_on"
        assert captured["target"] == "switch.tower_fan"
        assert captured["apply_"] is False

    def test_calibrate_target_json(self, runner, monkeypatch):
        runn, client = runner
        captured = {}
        monkeypatch.setattr(
            "cli_anything.homeassistant.core.powercalc_calibration.calibrate",
            lambda c, entry_id, **kw: captured.update(
                {"entry_id": entry_id, **kw}) or {
                "entry_id": entry_id, "delta_w": 0, "applied": False,
                "baseline": {"mean": 0}, "load": {"mean": 0},
                "previous_fixed_power": None,
                "service_on": kw["service_on"], "service_off": None,
                "smart_meter": "x"},
        )
        r = _invoke(runn, "powercalc", "calibrate", "E1",
                    "--service-on", "light.turn_on",
                    "--target", '{"area_id":"kitchen"}',
                    "--baseline-seconds", "0",
                    "--load-seconds", "0",
                    "--stabilisation-seconds", "0",
                    "--samples", "1")
        assert r.exit_code == 0, r.output
        assert captured["target"] == {"area_id": "kitchen"}

    def test_calibrate_template_parses_states(self, runner, monkeypatch):
        runn, client = runner
        captured = {}
        monkeypatch.setattr(
            "cli_anything.homeassistant.core.powercalc_calibration.calibrate_template",
            lambda c, entry_id, **kw: captured.update(
                {"entry_id": entry_id, **kw}) or {
                "entry_id": entry_id, "source_entity": kw["source_entity"],
                "attribute": kw["attribute"], "baseline_mean_w": 0,
                "steps": [], "template": "", "applied": False},
        )
        r = _invoke(runn, "powercalc", "calibrate-template", "E1",
                    "--source", "fan.x", "--attribute", "percentage",
                    "--service-set", "fan.set_percentage",
                    "--state-arg", "percentage",
                    "--service-off", "fan.turn_off",
                    "--states", "0,25,50,75,100",
                    "--baseline-seconds", "0",
                    "--load-seconds", "0",
                    "--stabilisation-seconds", "0",
                    "--samples", "2")
        assert r.exit_code == 0, r.output
        assert captured["states"] == [0, 25, 50, 75, 100]
        assert captured["service_set"] == "fan.set_percentage"

    def test_auto_calibrate_dry_run_by_default(self, runner, monkeypatch):
        runn, client = runner
        captured = {}
        monkeypatch.setattr(
            "cli_anything.homeassistant.core.powercalc_calibration.auto_calibrate",
            lambda c, **kw: captured.update(kw) or {
                "window_hours": kw["hours"], "smart_meter": "x",
                "candidates": [], "applied": 0, "skipped": 0},
        )
        r = _invoke(runn, "powercalc", "auto-calibrate",
                    "--hours", "168",
                    "--quiet-seconds", "15",
                    "--min-samples", "10")
        assert r.exit_code == 0, r.output
        assert captured["hours"] == 168.0
        assert captured["quiet_seconds"] == 15.0
        assert captured["min_samples"] == 10
        assert captured["apply_"] is False
