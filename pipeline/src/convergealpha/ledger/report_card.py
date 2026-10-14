"""The live report card: every forecast the app published, checked against what really happened.

Every daily build stores the chance of rising it gave each stock for 1 week, 1 month, 3 months and
6 months (snapshots/YYYY/YYYYMMDD/scores.parquet, its SHA-256 in the ledgers). Once a horizon has
passed, this compares those chances with the real total return: how often the stocks it gave
60% or more really rose ("we said 60%, 58% rose"), the Brier score against simply using the usual
up rate of 2016-2023, and a table by chance bucket with 95% ranges. Losers are counted like
winners: every eligible stock of every day is in it.

Forecasts made on consecutive days overlap in time, so the ranges are narrower than they should be;
the number of forecast days is shown next to every number for that reason.

forecast archive: forecasts/YYYY-MM.json on the site holds every forecast of that month (eligible
stocks, chance of rising for each horizon, the label) so anyone can check them later.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from convergealpha.config import HORIZON_NAMES
from convergealpha.core.stats import wilson_interval

EDGES = (0.0, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 1.0001)
CONFIDENT = 0.60  # "confident up" = a chance of 60% or more; "confident down" = 40% or less
MIN_N = 30  # fewer outcomes than this: shown as "too few to judge"


def snapshot_days(data_dir: Path) -> list[tuple[str, Path]]:
    """(YYYY-MM-DD, the day's first scores file): the forecasts as first published that day."""
    out = []
    for f in sorted((data_dir / "snapshots").glob("*/*/scores.parquet")):
        d = f.parent.name
        out.append((f"{d[:4]}-{d[4:6]}-{d[6:]}", f))
    return out


def outcomes(data_dir: Path, tr: pd.DataFrame, as_of: pd.Timestamp, raw: bool = False) -> pd.DataFrame:  # fmt: skip
    """One row per (forecast day, stock, horizon) whose horizon has passed by `as_of`. With
    `raw`, the chances before the live correction (p_up_raw_*, where stored)."""
    idx = pd.DatetimeIndex(tr.index)
    parts = []
    for day, f in snapshot_days(data_dir):
        d = pd.Timestamp(day)
        if d not in idx:
            continue
        i = idx.get_loc(d)
        snap = pd.read_parquet(f)
        if "eligible" in snap:
            snap = snap[snap["eligible"].astype(bool)]
        snap = snap.set_index("ticker")
        for days, name in HORIZON_NAMES.items():
            col = f"p_up_raw_{name}" if raw and f"p_up_raw_{name}" in snap else f"p_up_{name}"
            j = i + days
            if col not in snap or j >= len(idx) or idx[j] > as_of:
                continue
            p = snap[col].astype(float).dropna()
            tks = [t for t in p.index if t in tr.columns]
            start, end = tr.loc[idx[i], tks], tr.loc[idx[j], tks]
            ret = (end / start - 1).astype(float)
            ret = ret[ret.notna() & np.isfinite(ret)]
            parts.append(pd.DataFrame({"day": day, "ticker": ret.index.astype(str), "horizon": name, "p_up": p.reindex(ret.index).to_numpy(), "ret": ret.to_numpy()}))  # fmt: skip
    cols = ["day", "ticker", "horizon", "p_up", "ret"]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=cols)


def _rate(hits: int, n: int) -> dict[str, Any]:
    lo, hi = wilson_interval(hits, n) if n else (None, None)
    return {"n": n, "rate": hits / n if n else None, "lo": lo, "hi": hi}


def card(df: pd.DataFrame, base_up: Mapping[str, float]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in HORIZON_NAMES.values():
        h = df[df["horizon"] == name] if not df.empty else df
        if h.empty:
            out[name] = {"n": 0, "days": 0}
            continue
        p = h["p_up"].to_numpy()
        y = (h["ret"].to_numpy() > 0).astype(float)
        base = float(base_up.get(name, np.mean(y)))
        brier = float(np.mean((p - y) ** 2))
        brier_base = float(np.mean((base - y) ** 2))
        up = h["p_up"] >= CONFIDENT
        down = h["p_up"] <= 1 - CONFIDENT
        buckets = []
        for lo, hi in zip(EDGES[:-1], EDGES[1:], strict=True):
            m = (h["p_up"] >= lo) & (h["p_up"] < hi)
            n = int(m.sum())
            if n:
                hits = int((h.loc[m, "ret"] > 0).sum())
                buckets.append({"lo": lo, "hi": min(hi, 1.0), "said": float(h.loc[m, "p_up"].mean()), **_rate(hits, n)})  # fmt: skip
        out[name] = {
            "n": len(h),
            "days": int(h["day"].nunique()),
            "first_day": str(h["day"].min()),
            "last_day": str(h["day"].max()),
            "said_avg": float(p.mean()),
            "rose": float(y.mean()),
            "base_up": base,
            "brier": brier,
            "brier_base": brier_base,
            "skill": 1 - brier / brier_base if brier_base > 0 else None,
            "confident_up": _rate(int((h.loc[up, "ret"] > 0).sum()), int(up.sum())),
            "confident_down": _rate(int((h.loc[down, "ret"] <= 0).sum()), int(down.sum())),
            "buckets": buckets,
            "enough": len(h) >= MIN_N,
        }
    return out


def next_results(data_dir: Path) -> dict[str, str | None]:
    """When each horizon gets its first live result (trading days after the first forecast)."""
    days = snapshot_days(data_dir)
    if not days:
        return {name: None for name in HORIZON_NAMES.values()}
    first = pd.Timestamp(days[0][0])
    from convergealpha.util.calendar import next_trading_day

    out: dict[str, str | None] = {}
    for n, name in HORIZON_NAMES.items():
        d = first.date()
        for _ in range(n):
            d = next_trading_day(d)
        out[name] = d.isoformat()
    return out


def export(data_dir: Path, tr: pd.DataFrame, as_of: pd.Timestamp, base_up: Mapping[str, float]) -> dict[str, Any]:  # fmt: skip
    days = snapshot_days(data_dir)
    df = outcomes(data_dir, tr, as_of)
    return {
        "as_of": as_of.strftime("%Y-%m-%d"),
        "since": days[0][0] if days else None,
        "forecast_days": len(days),
        "confident": CONFIDENT,
        "horizons": card(df, base_up),
        "first_result": next_results(data_dir),
        "note": "Every eligible stock of every day counts, losers too. Forecasts on consecutive days overlap in time, so the 95% ranges are too narrow; read them with the number of forecast days.",
    }


LABEL_CODES = {"NO TRADE": "", "WATCH": "W", "BUY": "B", "STRONG BUY — TOP CONVICTION": "S", "SELL / RISK WARNING": "X"}  # fmt: skip


def archive(data_dir: Path) -> dict[str, dict[str, Any]]:
    """forecasts/YYYY-MM.json: every published forecast of each month (eligible stocks).
    Chances are stored in thousandths (583 = 58.3%) to keep the files small."""
    months: dict[str, dict[str, Any]] = {}
    for day, f in snapshot_days(data_dir):
        snap = pd.read_parquet(f)
        if "eligible" in snap:
            snap = snap[snap["eligible"].astype(bool)]
        cols = [f"p_up_{n}" for n in HORIZON_NAMES.values() if f"p_up_{n}" in snap]
        if not cols:
            continue
        rows = []
        for r in snap.itertuples(index=False):
            vals = [getattr(r, c) for c in cols]
            rows.append([str(r.ticker), *[None if pd.isna(v) else round(float(v) * 1000) for v in vals], LABEL_CODES.get(str(getattr(r, "label", "") or ""), str(getattr(r, "label", "") or ""))])  # fmt: skip
        m = months.setdefault(day[:7], {"month": day[:7], "fields": ["ticker", *cols, "label"], "units": "chances in thousandths", "labels": {v: k for k, v in LABEL_CODES.items()}, "days": {}})  # fmt: skip
        m["days"][day] = rows
    return months


__all__ = ["archive", "card", "export", "outcomes", "snapshot_days"]
