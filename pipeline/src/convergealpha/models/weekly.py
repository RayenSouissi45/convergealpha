"""Weekly model job: rebuild the point-in-time dataset, walk-forward, calibrate, fit final models,
build the analog index and event patterns, and save everything as one model bundle."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from convergealpha.config import BENCHMARKS
from convergealpha.models import dataset as D
from convergealpha.models import train as T
from convergealpha.util.io import write_json
from convergealpha.util.log import get

if TYPE_CHECKING:
    from convergealpha.run import RunContext

log = get(__name__)

ANALOG_FEATURES = [
    "f3h",
    "f4h",
    "f5h",
    "f6h",
    "mom_6m",
    "mom_12_2",
    "vol_63",
    "dist_52w",
    "log_mcap",
    "regime_code",
    "beta",
]


def load_history_from_data(ctx: RunContext) -> tuple[D.History, pd.DataFrame]:
    from convergealpha.features.evidence import build_table  # noqa: F401 - keeps import graph simple
    from convergealpha.run import universe_tickers
    from convergealpha.sources import fundamentals as F
    from convergealpha.sources import insiders as I
    from convergealpha.sources import macro as M
    from convergealpha.sources import prices as P
    from convergealpha.sources import sec_meta as S

    stocks, tickers = universe_tickers(ctx)
    comp = S.load_companies(ctx.paths.data).set_index("cik")
    stocks = stocks.copy()
    stocks["sector"] = stocks["cik"].map(comp["sector"]) if "sector" in comp else np.nan
    stocks["industry_group"] = (
        stocks["cik"].map(comp["industry_group"]) if "industry_group" in comp else np.nan
    )
    panel = P.build_panel(
        P.load_rows(ctx.paths.data, [*tickers, *BENCHMARKS] if ctx.tickers_override else None)
    )
    facts = F.load_facts(ctx.paths.data)
    trades = I.classify(I.load(ctx.paths.data))
    short = M.load_short_interest(ctx.paths.data)
    if not short.empty:
        short = short[short["ticker"].isin(set(tickers))]
    fred = M.load_fred(ctx.paths.data)
    h = D.load_history(
        panel, stocks[["sector", "industry_group", "cik"]], facts, trades, short, fred
    )
    return h, stocks


def analog_index(df: pd.DataFrame) -> dict[str, Any]:
    ref = df[df["up_6m"].notna()].dropna(subset=["f5h"])
    X = ref[ANALOG_FEATURES].astype("float64")
    mu = X.mean()
    sd = X.std().replace(0, 1)
    Z = ((X - mu) / sd).fillna(0.0).to_numpy(dtype="float32")
    return {
        "Z": Z,
        "up": ref["up_6m"].to_numpy(dtype="float32"),
        "ret": ref["ret_6m"].to_numpy(dtype="float32"),
        "ticker": ref["ticker"].to_numpy(),
        "date": ref["date"].to_numpy(dtype="datetime64[D]"),
        "mu": mu.to_dict(),
        "sd": sd.to_dict(),
        "features": ANALOG_FEATURES,
    }


def run(ctx: RunContext, out_dir: Path) -> dict[str, Any]:
    t0 = time.time()
    cfg = T.TrainConfig()
    h, stocks = load_history_from_data(ctx)
    df = D.build(h)
    trading = pd.DatetimeIndex(h.panel.close.index)
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_dir / "dataset.parquet", index=False)
    summary = D.summary(df)
    log.info("dataset: %s", summary)

    years = [y for y in [*T.DEV_YEARS, *T.VAL_YEARS] if (df["date"].dt.year == y).any()]
    oos = T.walk_forward(df[df["date"] < T.HOLDOUT[0]], years, cfg, trading)
    oos.to_parquet(out_dir / "oos_devval.parquet", index=False)
    cal = T.calibrate(oos, cfg)
    T.fit_meta(oos, cal)
    # "How often was it right?" tables (dev + validation years only; not part of the config).
    from convergealpha.models import reliability as RL

    write_json(RL.build(oos, cfg.calibration_min_bin), out_dir / "reliability.json")
    final = T.fit_models(df, cfg, trading)
    analogs = analog_index(df)
    recent = df[df["date"] >= df["date"].max() - pd.Timedelta(days=730)]
    recent[[c for c in cfg.features if c in recent]].to_parquet(
        out_dir / "reference.parquet", index=False
    )
    T.save(out_dir / "fitted.pkl", final)
    T.save(out_dir / "calibration.pkl", cal)
    T.save(out_dir / "analogs.pkl", analogs)

    from convergealpha.models import patterns as PT

    pats = PT.run(h, stocks)
    write_json(pats, out_dir / "patterns.json")

    metrics = quick_metrics(oos, cal)
    version = f"m-{datetime.now(UTC):%Y%m%d}-{cfg.digest()}"
    meta = {
        "version": version,
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "config": cfg.digest(),
        "features": cfg.features,
        "dataset": summary,
        "oos_years": years,
        "metrics": metrics,
        "patterns_tested": pats.get("tested", 0),
        "seconds": round(time.time() - t0),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    log.info("weekly models %s done in %.0fs: %s", version, time.time() - t0, metrics)
    return meta


def quick_metrics(oos: pd.DataFrame, cal: T.Calibration) -> dict[str, Any]:
    from sklearn.metrics import brier_score_loss, roc_auc_score

    d = oos[oos["tb_correct"].notna()]
    p = T.apply_correct(cal, d["raw_correct"].to_numpy(), d["regime"].astype(str).to_numpy())
    y = d["tb_correct"].to_numpy()
    base = np.full_like(p, y.mean())
    out: dict[str, Any] = {
        "rows": len(d),
        "auc_correct": float(roc_auc_score(y, d["raw_correct"])) if len(np.unique(y)) > 1 else None,
        "brier_correct": float(brier_score_loss(y, p)),
        "brier_base": float(brier_score_loss(y, base)),
        "base_rate": float(y.mean()),
    }
    for name in cal.conformal:
        g = oos[oos[f"ret_{name}"].notna()]
        lo = g[f"q10_{name}"] - cal.conformal[name]
        hi = g[f"q90_{name}"] + cal.conformal[name]
        out[f"coverage80_{name}"] = float(
            ((g[f"ret_{name}"] >= lo) & (g[f"ret_{name}"] <= hi)).mean()
        )
    return out
