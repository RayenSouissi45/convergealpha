"""Sector and stock corrections of the chances of rising, tested once on 2016-2023 with a protocol
fixed before the run.

Question: does a small learned correction per sector (and per stock, kept close to its sector)
make the chances of rising more accurate than the app's one calibration for all stocks?

Data: the walk-forward out-of-sample predictions of 2016-2023 (oos_devval.parquet from the weekly
model job: one row per stock and month-end). The 2024-2026 holdout is never read.

PROTOCOL (fixed before the first run; any change = a new protocol id):
- Fit period 2016-2020, test period 2021-2023 (the app's own development / validation split).
- For each horizon (1 week, 1 month, 3 months, 6 months): calibrate the raw score on the fit
  period exactly as the app does (binned isotonic, bins of at least 500 outcomes) -> p.
- Sector correction: gap_s = logit(share that rose in sector s) - logit(mean p in s), on the fit
  period; weight w_s = m_s / (m_s + 24), m_s = months in which the sector had at least 5 stocks.
- Stock correction, on top of the sector one: gap_i = logit((rose_i + 1) / (n_i + 2)) -
  logit(mean p' of stock i) with p' the sector-corrected chance; weight w_i = n_i / (n_i + 36).
- Each correction is w x gap in log-odds; the total shift is capped at +/-0.3.
- Score: Brier score on the test period. A correction is adopted for a horizon only if it lowers
  the test Brier by at least 0.2% (relative) AND lowers it in at least 2 of the 3 test years. The
  stock correction is judged on top of the adopted sector correction (if the sector one is not
  adopted, the stock correction is not tried).
- Adopted corrections are refitted by the weekly job on all of 2016-2023 and applied to the daily
  chances; the others are never used. The run and its result go to the experiment log.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np
import pandas as pd

from convergealpha.config import HORIZON_NAMES

PROTOCOL_ID = "corrections-2016-2023-v1"
FIT_YEARS = (2016, 2020)
TEST_YEARS = (2021, 2023)
MIN_BIN = 500
SECTOR_K = 24.0
STOCK_K = 36.0
SECTOR_MIN_STOCKS = 5
CAP = 0.3
MIN_GAIN = 0.002
MIN_YEARS = 2
EPS = 0.01


def protocol_digest() -> str:
    spec = {
        "id": PROTOCOL_ID, "fit": FIT_YEARS, "test": TEST_YEARS, "min_bin": MIN_BIN,
        "sector_k": SECTOR_K, "stock_k": STOCK_K, "sector_min_stocks": SECTOR_MIN_STOCKS,
        "cap": CAP, "min_gain": MIN_GAIN, "min_years": MIN_YEARS,
    }  # fmt: skip
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]


def _logit(p: Any) -> Any:
    q = np.clip(p, EPS, 1 - EPS)
    return np.log(q / (1 - q))


def _sigmoid(x: Any) -> Any:
    return 1 / (1 + np.exp(-x))


def sector_shifts(d: pd.DataFrame) -> dict[str, float]:
    """d: rows with sector, month, p, y. Returns sector -> shift in log-odds (weighted, capped)."""
    out: dict[str, float] = {}
    for s, g in d.dropna(subset=["sector"]).groupby("sector"):
        months = int((g.groupby("month")["ticker"].nunique() >= SECTOR_MIN_STOCKS).sum())
        if months == 0:
            continue
        gap = float(_logit(g["y"].mean()) - _logit(g["p"].mean()))
        w = months / (months + SECTOR_K)
        out[str(s)] = float(np.clip(w * gap, -CAP, CAP))
    return out


def stock_shifts(d: pd.DataFrame, p_col: str = "p") -> dict[str, float]:
    out: dict[str, float] = {}
    for tk, g in d.groupby("ticker"):
        n = len(g)
        rate = (g["y"].sum() + 1) / (n + 2)
        gap = float(_logit(rate) - _logit(g[p_col].mean()))
        out[str(tk)] = float(np.clip(n / (n + STOCK_K) * gap, -CAP, CAP))
    return out


def apply(p: np.ndarray, sectors: pd.Series, tickers: pd.Series, by_sector: dict[str, float], by_stock: dict[str, float] | None = None) -> np.ndarray:  # fmt: skip
    shift = sectors.map(by_sector).fillna(0.0).to_numpy(dtype=float)
    if by_stock is not None:
        shift = shift + tickers.map(by_stock).fillna(0.0).to_numpy(dtype=float)
    shift = np.clip(shift, -CAP, CAP)
    return np.asarray(_sigmoid(_logit(np.asarray(p, dtype=float)) + shift))


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def evaluate(oos: pd.DataFrame) -> dict[str, Any]:
    from convergealpha.models import train as T

    oos = oos.copy()
    oos["year"] = pd.to_datetime(oos["date"]).dt.year
    oos["month"] = pd.to_datetime(oos["date"]).dt.to_period("M").astype(str)
    oos = oos[(oos["year"] >= FIT_YEARS[0]) & (oos["year"] <= TEST_YEARS[1])]
    res: dict[str, Any] = {"protocol": PROTOCOL_ID, "protocol_digest": protocol_digest(), "period": f"fit {FIT_YEARS[0]}-{FIT_YEARS[1]}, test {TEST_YEARS[0]}-{TEST_YEARS[1]}", "horizons": {}}  # fmt: skip
    for name in HORIZON_NAMES.values():
        raw, up = f"raw_up_{name}", f"up_{name}"
        if raw not in oos or up not in oos:
            continue
        d = oos[oos[raw].notna() & oos[up].notna()][["ticker", "sector", "year", "month", raw, up]]
        fit = d[d["year"] <= FIT_YEARS[1]].copy()
        test = d[d["year"] >= TEST_YEARS[0]].copy()
        cal = T._iso(fit[raw].to_numpy(), fit[up].to_numpy(), MIN_BIN)
        for f in (fit, test):
            f["p"] = cal.predict(f[raw].to_numpy())
            f["y"] = f[up].astype(float)
        sec = sector_shifts(fit)
        fit["p_sec"] = apply(fit["p"].to_numpy(), fit["sector"], fit["ticker"], sec)
        stk = stock_shifts(fit, "p_sec")
        test["p_sec"] = apply(test["p"].to_numpy(), test["sector"], test["ticker"], sec)
        test["p_stk"] = apply(test["p"].to_numpy(), test["sector"], test["ticker"], sec, stk)
        y = test["y"].to_numpy()
        base, b_sec, b_stk = (_brier(test[c].to_numpy(), y) for c in ("p", "p_sec", "p_stk"))
        years = {}
        for yr, g in test.groupby("year"):
            yy = g["y"].to_numpy()
            years[int(yr)] = {c: _brier(g[c].to_numpy(), yy) for c in ("p", "p_sec", "p_stk")}
        sec_ok = base > 0 and (base - b_sec) / base >= MIN_GAIN and sum(v["p_sec"] < v["p"] for v in years.values()) >= MIN_YEARS  # fmt: skip
        stk_ok = sec_ok and b_sec > 0 and (b_sec - b_stk) / b_sec >= MIN_GAIN and sum(v["p_stk"] < v["p_sec"] for v in years.values()) >= MIN_YEARS  # fmt: skip
        res["horizons"][name] = {
            "fit_rows": len(fit), "test_rows": len(test),
            "brier": base, "brier_sector": b_sec, "brier_sector_stock": b_stk,
            "gain_sector": (base - b_sec) / base if base else None,
            "gain_stock": (b_sec - b_stk) / b_sec if b_sec else None,
            "years": years,
            "sectors": dict(sorted(sec.items(), key=lambda kv: -abs(kv[1]))),
            "adopt_sector": bool(sec_ok), "adopt_stock": bool(stk_ok),
        }  # fmt: skip
    res["decision"] = {h: {"sector": v["adopt_sector"], "stock": v["adopt_stock"]} for h, v in res["horizons"].items()}  # fmt: skip
    return res


def refit(oos: pd.DataFrame, cal_up: dict[str, Any], decision: dict[str, dict[str, bool]]) -> dict[str, Any]:  # fmt: skip
    """The weekly job: refit the adopted corrections on all of 2016-2023 with the app's own
    calibration. Returns {horizon: {"sector": {...}, "stock": {...}}} (only what was adopted)."""
    oos = oos.copy()
    oos["month"] = pd.to_datetime(oos["date"]).dt.to_period("M").astype(str)
    out: dict[str, Any] = {}
    for name, dec in decision.items():
        if not dec.get("sector") or name not in cal_up:
            continue
        raw, up = f"raw_up_{name}", f"up_{name}"
        d = oos[oos[raw].notna() & oos[up].notna()][["ticker", "sector", "month", raw, up]].copy()
        d["p"] = cal_up[name].predict(d[raw].to_numpy())
        d["y"] = d[up].astype(float)
        sec = sector_shifts(d)
        entry: dict[str, Any] = {"sector": sec}
        if dec.get("stock"):
            d["p_sec"] = apply(d["p"].to_numpy(), d["sector"], d["ticker"], sec)
            entry["stock"] = stock_shifts(d, "p_sec")
        out[name] = entry
    return out


__all__ = ["PROTOCOL_ID", "apply", "evaluate", "protocol_digest", "refit", "sector_shifts", "stock_shifts"]  # fmt: skip
