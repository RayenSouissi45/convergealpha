"""How often was the app right? Reliability tables per horizon, built by the weekly job.

For each horizon (1w, 1m, 3m, 6m) and each promise ("up": the price is higher; "beat": the
stock does better than the S&P 500), the walk-forward out-of-sample predictions of the
development and validation years (2016-2023, never the holdout) are grouped into buckets of the
calibrated probability. The buckets use the same fixed edges as the p̂ buckets, extended at both
ends because horizon probabilities spread wider, and a bucket with fewer than `min_cases` cases
is merged with its neighbour. Each bucket keeps its number of cases, the actual hit rate and the
95% Wilson interval of that rate.

Calibration is cross-fitted by year: a case from year Y gets the probability of a calibration
fitted on the other years only, so a bucket's hit rate is never measured on the outcomes that
shaped its own calibration.

Caveat shown on the site: cases overlap in time (monthly rows, multi-month horizons) and stocks
move together, so the true uncertainty is wider than the Wilson range.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from convergealpha.config import HORIZON_NAMES
from convergealpha.core import stats

# The p̂ bucket edges (models/train.py: buckets) plus 0.20-0.30 and 0.70-0.80.
EDGES: tuple[float, ...] = (
    0.0, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.48, 0.50, 0.52, 0.55, 0.58, 0.62, 0.66,
    0.70, 0.75, 0.80, 1.01,
)  # fmt: skip
MIN_CASES = 200
KINDS = ("up", "beat")


def table(
    p: np.ndarray, y: np.ndarray, edges: tuple[float, ...] = EDGES, min_cases: int = MIN_CASES
) -> list[dict[str, float]]:
    """Fixed-edge buckets of `p`, merged left to right until each holds `min_cases` cases."""
    p, y = np.asarray(p, dtype=float), np.asarray(y, dtype=float)
    ok = np.isfinite(p) & np.isfinite(y)
    p, y = p[ok], y[ok]
    groups: list[list[float]] = []  # [lo, hi, n, hits, sum_p]
    cur: list[float] | None = None
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (p >= lo) & (p < hi)
        n = int(m.sum())
        if cur is None:
            cur = [lo, hi, 0, 0, 0.0]
        cur[1] = hi
        cur[2] += n
        cur[3] += float(y[m].sum())
        cur[4] += float(p[m].sum())
        if cur[2] >= min_cases:
            groups.append(cur)
            cur = None
    if cur is not None and cur[2] > 0:
        if groups:  # too few cases left at the top: join the last full bucket
            last = groups[-1]
            groups[-1] = [last[0], cur[1], last[2] + cur[2], last[3] + cur[3], last[4] + cur[4]]
        else:
            groups.append(cur)
    out = []
    for g_lo, g_hi, g_n, hits, sp in groups:
        if g_n == 0:
            continue
        wl, wh = stats.wilson_interval(int(hits), int(g_n))
        out.append(
            {
                "lo": round(g_lo, 4),
                "hi": round(g_hi, 4),
                "n": int(g_n),
                "hits": int(hits),
                "rate": hits / g_n,
                "wilson_lo": wl,
                "wilson_hi": wh,
                "mean_p": sp / g_n,
            }
        )
    # Buckets with no cases at the ends would leave gaps: stretch the outer edges to 0 and 1.01.
    if out:
        out[0]["lo"] = 0.0
        out[-1]["hi"] = 1.01
    return out


def crossfit(raw: np.ndarray, y: np.ndarray, years: np.ndarray, min_bin: int) -> np.ndarray:
    """Calibrated probability of each case from a calibration fitted on the other years."""
    from convergealpha.models.train import BinnedIsotonic

    raw, y = np.asarray(raw, dtype=float), np.asarray(y, dtype=float)
    out = np.full(len(raw), np.nan)
    for yr in np.unique(years):
        test = years == yr
        train = ~test & np.isfinite(raw) & np.isfinite(y)
        if train.sum() < 5 * min_bin:
            continue
        out[test] = BinnedIsotonic(raw[train], y[train], min_bin).predict(raw[test])
    return out


def build(oos: pd.DataFrame, min_bin: int = MIN_CASES) -> dict[str, Any]:
    """Reliability tables from walk-forward predictions (development + validation years only)."""
    years = sorted(int(y) for y in oos["date"].dt.year.unique()) if len(oos) else []
    out: dict[str, Any] = {
        "method": "walk-forward out-of-sample predictions, calibration cross-fitted by year",
        "years": years,
        "min_cases": min_bin,
        "horizons": {},
    }
    for name in HORIZON_NAMES.values():
        hz: dict[str, Any] = {}
        for kind in KINDS:
            raw_col, y_col = f"raw_{kind}_{name}", f"{kind}_{name}"
            if raw_col not in oos or y_col not in oos:
                continue
            g = oos[oos[y_col].notna() & oos[raw_col].notna()]
            if len(g) < 5 * min_bin:
                continue
            p = crossfit(
                g[raw_col].to_numpy(), g[y_col].to_numpy(), g["date"].dt.year.to_numpy(), min_bin
            )
            hz[kind] = table(p, g[y_col].to_numpy(), min_cases=min_bin)
        if hz:
            out["horizons"][name] = hz
    return out


def lookup(buckets: list[dict[str, float]] | None, p: float | None) -> dict[str, float] | None:
    """The bucket a probability falls into: hit rate, its Wilson range and n."""
    if not buckets or p is None or not np.isfinite(p):
        return None
    for b in buckets:
        if b["lo"] <= p < b["hi"]:
            return {
                "rate": float(b["rate"]),
                "lo": float(b["wilson_lo"]),
                "hi": float(b["wilson_hi"]),
                "n": int(b["n"]),
                "p_lo": float(b["lo"]),
                "p_hi": float(min(b["hi"], 1.0)),
            }
    return None
