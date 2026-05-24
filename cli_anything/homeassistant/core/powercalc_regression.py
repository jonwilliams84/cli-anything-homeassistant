"""Tier-2 regression-based powercalc calibration.

Where :mod:`powercalc_calibration` finds clean ON/OFF transitions and
takes the median delta, this module fits a linear regression of the
smart-meter signal against the binary state of every tracked device
simultaneously. Two cases this catches that the median-of-transitions
approach misses:

* devices that are almost always on/off in concert with another device
  (the transition filter rejects too many samples)
* devices with no clean OFF→ON transitions in the window (e.g. fridges
  that cycle continuously)

The regression coefficient for device *i* is the expected smart-meter
delta when device *i* is on, holding every other tracked device fixed.
That's what powercalc's fixed-power should be set to.

Uses numpy only (lstsq). No scipy / sklearn dependency.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from cli_anything.homeassistant.core import powercalc as _pc


DEFAULT_SMART_METER = "sensor.smart_meter_electricity_power"


# ── history collection ─────────────────────────────────────────────────────

def _history(client, entity_id: str, *, hours: float) -> list[dict]:
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(hours=hours)
    raw = client.get(
        f"history/period/{start.isoformat()}",
        params={
            "filter_entity_id": entity_id,
            "end_time": end.isoformat(),
            "minimal_response": "true",
        },
    )
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return raw[0]
    return []


def _parse_points(points: list[dict]) -> list[tuple[float, str]]:
    """Return [(epoch_ts, state_str), ...] sorted by ts."""
    out: list[tuple[float, str]] = []
    for p in points:
        try:
            ts = datetime.fromisoformat(
                p["last_changed"].replace("Z", "+00:00")
            ).timestamp()
            out.append((ts, str(p.get("state", ""))))
        except (KeyError, ValueError, TypeError):
            continue
    out.sort()
    return out


def _is_on(state: str) -> int:
    """Binary 'is the device drawing power right now?' from state string."""
    s = state.lower().strip()
    if s in ("off", "0", "0.0", "", "unavailable", "unknown", "none"):
        return 0
    return 1


def _resample(
    series: list[tuple[float, str]],
    *,
    start: float,
    end: float,
    interval: float,
    encoder=_is_on,
):
    """Forward-fill a sparse series onto a fixed time grid.

    Returns a list of (timestamp, encoded_value) at each grid point. The
    value at time t is the encoded form of the most recent state on or
    before t; gaps before the first state are treated as 0.
    """
    out: list[tuple[float, float]] = []
    i = 0
    n = len(series)
    last_val = 0
    t = start
    while t <= end:
        # Advance i while series[i].ts <= t
        while i < n and series[i][0] <= t:
            last_val = encoder(series[i][1])
            i += 1
        out.append((t, float(last_val)))
        t += interval
    return out


def _smart_meter_numeric(state: str) -> float | None:
    try:
        return float(state)
    except (ValueError, TypeError):
        return None


def _resample_numeric(
    series: list[tuple[float, str]],
    *,
    start: float,
    end: float,
    interval: float,
) -> list[tuple[float, float]]:
    """Same as _resample but encodes the state as a numeric value (smart meter)."""
    out: list[tuple[float, float]] = []
    i = 0
    n = len(series)
    last_val: float | None = None
    t = start
    while t <= end:
        while i < n and series[i][0] <= t:
            v = _smart_meter_numeric(series[i][1])
            if v is not None:
                last_val = v
            i += 1
        if last_val is not None:
            out.append((t, last_val))
        t += interval
    return out


# ── linear regression (numpy-only OLS) ─────────────────────────────────────

def _fit_ols(X, y):
    """Ordinary-least-squares fit.

    Returns ``{coef: [...], intercept: float, r_squared: float,
    std_err: [...], n: int, p: int}``.

    X is a 2D matrix of shape (n_samples, n_features) — without an
    intercept column; we add it. y is a 1D vector of length n_samples.
    """
    import numpy as np  # local import keeps top-level import lean
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    n, p = X.shape
    # Add intercept column
    A = np.hstack([X, np.ones((n, 1))])
    coef_full, residuals, rank, _sv = np.linalg.lstsq(A, y, rcond=None)
    coef = coef_full[:-1].tolist()
    intercept = float(coef_full[-1])
    # R²
    y_hat = A @ coef_full
    ss_res = float(((y - y_hat) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    # std-err for coefficients (only when over-determined)
    std_err = [None] * len(coef)
    if n > p + 1 and rank == p + 1:
        sigma2 = ss_res / (n - p - 1)
        try:
            cov = sigma2 * np.linalg.inv(A.T @ A)
            std_err = [float(np.sqrt(max(cov[i, i], 0))) for i in range(p)]
        except np.linalg.LinAlgError:
            pass
    return {
        "coef": coef,
        "intercept": intercept,
        "r_squared": float(r_squared),
        "std_err": std_err,
        "n": n,
        "p": p,
    }


# ── top-level orchestration ────────────────────────────────────────────────

def regress(
    client,
    *,
    smart_meter: str = DEFAULT_SMART_METER,
    hours: float = 24 * 7,
    interval_seconds: float = 60,
    title_contains: str | None = None,
    min_on_fraction: float = 0.005,
    min_off_fraction: float = 0.005,
    apply_: bool = False,
) -> dict:
    """Fit a linear regression of smart_meter against binary on/off for
    every powercalc virtual_power entry's source entity.

    Args:
      smart_meter:        ground-truth sensor.
      hours:              history window (default 168h = 7 days).
      interval_seconds:   grid spacing (default 60s = 1 min).
      title_contains:     case-insensitive substring filter on entry title.
      min_on_fraction:    drop devices that are on for less than this
                          fraction of samples (otherwise the coefficient
                          is meaningless). Default 0.5 %.
      min_off_fraction:   drop devices that are on for MORE than (1 −
                          this) of samples (e.g. always-on devices add
                          no variance). Default 0.5 %.
      apply_:             with True, write each fitted coefficient back
                          into the matching entry's fixed_power.

    Returns ``{n_samples, n_features, r_squared, intercept, candidates:
    [...], applied, dropped}``.
    """
    entries = _pc.list_entries(client, title_contains=title_contains)
    raw_candidates: list[dict] = []
    for e in entries:
        opts = e.get("options") or {}
        data = e.get("data") or {}
        source = opts.get("entity_id") or data.get("entity_id")
        if not source:
            continue
        if (e.get("title") or "").startswith("Power · "):
            continue
        raw_candidates.append({
            "entry_id": e["entry_id"],
            "title": e.get("title") or "",
            "source_entity": source,
            "previous_power_w": opts.get("power") or data.get("power"),
        })

    if not raw_candidates:
        return {"n_samples": 0, "n_features": 0, "r_squared": None,
                "intercept": None, "candidates": [], "applied": 0,
                "dropped": []}

    # Time bounds for the grid
    end = datetime.now(tz=timezone.utc).timestamp()
    start = end - hours * 3600

    # Smart meter (target)
    sm_series = _parse_points(_history(client, smart_meter, hours=hours))
    if not sm_series:
        return {"n_samples": 0, "n_features": 0, "r_squared": None,
                "intercept": None, "candidates": [], "applied": 0,
                "dropped": [], "warning": f"no history for {smart_meter}"}
    sm_grid = _resample_numeric(
        sm_series, start=start, end=end, interval=interval_seconds,
    )
    if not sm_grid:
        return {"n_samples": 0, "n_features": 0, "r_squared": None,
                "intercept": None, "candidates": [], "applied": 0,
                "dropped": []}

    sm_ts = [t for t, _ in sm_grid]
    y = [v for _, v in sm_grid]
    n = len(y)

    # Per-device feature column
    dropped: list[dict] = []
    keep: list[dict] = []
    columns: list[list[float]] = []
    for c in raw_candidates:
        series = _parse_points(_history(client, c["source_entity"],
                                          hours=hours))
        grid = _resample(series, start=sm_ts[0], end=sm_ts[-1],
                          interval=interval_seconds)
        col = [v for _, v in grid][: n]
        if len(col) < n:
            col = col + [0.0] * (n - len(col))
        on_frac = sum(col) / n if n else 0
        if on_frac < min_on_fraction:
            dropped.append({**c, "drop_reason": f"on for {on_frac:.2%} of samples "
                                                  f"(< {min_on_fraction:.2%})"})
            continue
        if on_frac > 1 - min_off_fraction:
            dropped.append({**c, "drop_reason": f"on for {on_frac:.2%} of samples "
                                                  f"(no variance)"})
            continue
        keep.append({**c, "on_fraction": round(on_frac, 4)})
        columns.append(col)

    if not keep:
        return {"n_samples": n, "n_features": 0, "r_squared": None,
                "intercept": None, "candidates": [], "applied": 0,
                "dropped": dropped, "warning": "every candidate dropped"}

    # Transpose columns into (n, p) matrix
    X = [[columns[j][i] for j in range(len(columns))] for i in range(n)]
    fit = _fit_ols(X, y)

    out_candidates: list[dict] = []
    applied_count = 0
    for i, c in enumerate(keep):
        coef = fit["coef"][i]
        se = fit["std_err"][i]
        ci95 = (1.96 * se) if se is not None else None
        row = {
            **c,
            "fitted_power_w": round(coef, 1),
            "std_err_w": round(se, 1) if se is not None else None,
            "ci95_w": round(ci95, 1) if ci95 is not None else None,
            "applied": False,
        }
        if apply_ and coef > 0:
            try:
                _pc.set_fixed_power(client, c["entry_id"],
                                    power=round(coef, 1))
                row["applied"] = True
                applied_count += 1
            except Exception as exc:
                row["apply_error"] = str(exc)[:200]
        out_candidates.append(row)

    out_candidates.sort(key=lambda r: -(r.get("fitted_power_w") or 0))
    return {
        "n_samples": n,
        "n_features": len(keep),
        "r_squared": round(fit["r_squared"], 4),
        "intercept": round(fit["intercept"], 1),
        "candidates": out_candidates,
        "applied": applied_count,
        "dropped": dropped,
    }
