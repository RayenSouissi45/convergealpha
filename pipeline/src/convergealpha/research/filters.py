"""Quality filters on the model's top picks, tested once on 2016-2023 with a protocol fixed before
the run.

Question: among the stocks the model ranks highest, do simple company-quality filters (cash burn,
heavy debt, an expensive price for the sector, weak earnings quality) remove the losers, or do they
throw away winners the model already priced in?

Data: the walk-forward out-of-sample predictions of 2016-2023 (oos_devval.parquet) joined with the
point-in-time features of the same stock and month-end (dataset.parquet). The 2024-2026 holdout is
never read.

PROTOCOL (fixed before the first run; any change = a new protocol id):
- Picks: each month-end, the top 2% of eligible stocks by the model's ranking (L1), as in the sell
  rule research.
- Outcome: excess return over the S&P 500 in the next 63 trading days (the dataset's exc_3m).
- Filters, each tested alone against no filter:
  cash_burn   exclude a negative free-cash-flow yield;
  heavy_debt  exclude debt above 6x EBITDA (or debt with negative EBITDA);
  expensive   exclude the most expensive 20% of the sector by free-cash-flow yield that month
              (eligible stocks, sectors with 10+ stocks);
  accruals    exclude the 10% of stocks with the highest accruals that month (weak earnings quality).
- Score = mean excess - 0.5 x |average of the worst 5%|. A filter is adopted only if its score beats
  no filter in both halves (2016-2019 and 2020-2023) AND it keeps at least 70% of the picks.
- An adopted filter is shown as a warning next to a stock (never a hidden rule); it can only enter a
  strategy or a label as a new rules version. The run is logged in the experiment log either way.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np
import pandas as pd

PROTOCOL_ID = "filters-2016-2023-v1"
TOP_FRACTION = 0.02
TAIL = 0.05
TAIL_WEIGHT = 0.5
MIN_KEEP = 0.70
HALVES = ((2016, 2019), (2020, 2023))
EXPENSIVE = 0.20
ACCRUALS_TOP = 0.10
DEBT_MAX = 6.0
FILTERS = ("cash_burn", "heavy_debt", "expensive", "accruals")


def protocol_digest() -> str:
    spec = {
        "id": PROTOCOL_ID, "top": TOP_FRACTION, "tail": TAIL, "tail_weight": TAIL_WEIGHT,
        "min_keep": MIN_KEEP, "halves": HALVES, "expensive": EXPENSIVE, "accruals_top": ACCRUALS_TOP,
        "debt_max": DEBT_MAX, "filters": FILTERS, "outcome": "exc_3m",
    }  # fmt: skip
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]


def flags(ds: pd.DataFrame) -> pd.DataFrame:
    """Per (date, ticker): which filters would exclude the stock that month."""
    d = ds[["date", "ticker", "sector", "eligible", "fcf_yield", "debt_ebitda", "accruals"]].copy()
    d = d[d["eligible"].astype(bool)]
    d["cash_burn"] = d["fcf_yield"] < 0
    d["heavy_debt"] = d["debt_ebitda"] >= DEBT_MAX
    pct = d.groupby(["date", "sector"])["fcf_yield"].rank(pct=True)
    size = d.groupby(["date", "sector"])["fcf_yield"].transform("count")
    d["expensive"] = (pct <= EXPENSIVE) & (size >= 10)
    acc = d.groupby("date")["accruals"].rank(pct=True)
    d["accruals"] = acc > 1 - ACCRUALS_TOP
    return d[["date", "ticker", *FILTERS]]


def picks(oos: pd.DataFrame) -> pd.DataFrame:
    o = oos.copy()
    o["date"] = pd.to_datetime(o["date"])
    o = o[(o["date"].dt.year >= HALVES[0][0]) & (o["date"].dt.year <= HALVES[1][1])]
    o = o[o["exc_3m"].notna() & o["l1"].notna()]
    rank = o.groupby("date")["l1"].rank(ascending=False, pct=True)
    return o[rank <= TOP_FRACTION][["date", "ticker", "exc_3m"]]


def score(x: pd.Series) -> dict[str, Any]:
    if x.empty:
        return {"n": 0, "mean": None, "worst5": None, "score": None}
    k = max(1, int(np.ceil(len(x) * TAIL)))
    worst = float(np.sort(x.to_numpy())[:k].mean())
    mean = float(x.mean())
    return {"n": int(len(x)), "mean": mean, "worst5": worst, "hit": float((x > 0).mean()), "score": mean - TAIL_WEIGHT * abs(worst)}  # fmt: skip


def evaluate(oos: pd.DataFrame, ds: pd.DataFrame) -> dict[str, Any]:
    p = picks(oos)
    f = flags(ds.assign(date=pd.to_datetime(ds["date"])))
    p = p.merge(f, on=["date", "ticker"], how="left")
    for c in FILTERS:
        p[c] = p[c].astype("boolean").fillna(False).astype(bool)  # unknown data never excludes
    p["year"] = p["date"].dt.year
    out: dict[str, Any] = {"protocol": PROTOCOL_ID, "protocol_digest": protocol_digest(), "period": "2016-2023", "picks": int(len(p)), "filters": {}}  # fmt: skip
    base = {"all": score(p["exc_3m"])} | {f"{a}-{b}": score(p[p["year"].between(a, b)]["exc_3m"]) for a, b in HALVES}  # fmt: skip
    out["no_filter"] = base
    for c in FILTERS:
        kept = p[~p[c]]
        res = {"all": score(kept["exc_3m"])} | {f"{a}-{b}": score(kept[kept["year"].between(a, b)]["exc_3m"]) for a, b in HALVES}  # fmt: skip
        removed = score(p[p[c]]["exc_3m"])
        keep_share = len(kept) / len(p) if len(p) else 0.0
        better = all(
            res[h]["score"] is not None
            and base[h]["score"] is not None
            and res[h]["score"] > base[h]["score"]
            for h in (f"{a}-{b}" for a, b in HALVES)
        )
        out["filters"][c] = {**res, "removed": removed, "keep_share": keep_share, "adopted": bool(better and keep_share >= MIN_KEEP)}  # fmt: skip
    out["decision"] = {c: v["adopted"] for c, v in out["filters"].items()}
    return out


__all__ = ["FILTERS", "PROTOCOL_ID", "evaluate", "flags", "picks", "protocol_digest", "score"]
