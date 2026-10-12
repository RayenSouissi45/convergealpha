"""Phase 3+ decision layer, called by build.py: families -> ranks -> forecasts -> labels -> plan.

Before the models of phase 4 exist (or when their files are missing) the transparent fallback
forecast is used and labels are marked provisional. Everything carries the RESEARCH MODE flag
until the validation lab passes.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from convergealpha.config import HORIZON_NAMES, HORIZONS, SPY
from convergealpha.core import stats
from convergealpha.decide import rules as R
from convergealpha.features import families as FA
from convergealpha.features.evidence import Sources
from convergealpha.sources import macro as M
from convergealpha.util.log import get

if TYPE_CHECKING:
    from convergealpha.run import RunContext

log = get(__name__)


def betas(panel: Any, tickers: list[str], window: int = 252) -> pd.Series:
    """1-year daily beta to SPY (total return)."""
    tr = panel.tr.iloc[-(window + 1) :]
    rets = tr.pct_change(fill_method=None).iloc[1:]
    if SPY not in rets:
        return pd.Series(1.0, index=tickers)
    m = rets[SPY]
    cols = [t for t in tickers if t in rets.columns]
    r = rets[cols]
    ok = r.notna() & m.notna().to_numpy()[:, None]
    mc = m.to_numpy()[:, None] - np.nanmean(m.to_numpy())
    rc = r - r.mean()
    cov = (rc * mc).where(ok).sum() / ok.sum()
    var = float(np.nanvar(m.to_numpy()))
    b = (cov / var).where(ok.sum() >= 120)
    return b.reindex(tickers).clip(-1, 4)


def correlation_clusters(
    panel: Any, tickers: list[str], days: int = 126, rho: float = 0.7
) -> pd.Series:
    """Groups of stocks whose daily returns are highly correlated (pairs with rho > 0.7 end up
    together: average linkage on 1 - rho, cut at 0.3). Singletons get no cluster id."""
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform

    cols = [t for t in tickers if t in panel.tr.columns]
    rets = panel.tr[cols].iloc[-(days + 1) :].pct_change(fill_method=None).iloc[1:]
    rets = rets.loc[:, rets.notna().sum() >= int(days * 0.8)]
    if rets.shape[1] < 2:
        return pd.Series(np.nan, index=tickers)
    corr = np.nan_to_num(rets.corr().to_numpy(), nan=0.0)
    dist = np.clip(1.0 - corr, 0.0, 2.0)
    np.fill_diagonal(dist, 0.0)
    labels = fcluster(
        linkage(squareform(dist, checks=False), method="average"), t=1.0 - rho, criterion="distance"
    )
    lab = pd.Series(labels, index=rets.columns)
    sizes = lab.map(lab.value_counts())
    return lab.where(sizes >= 2).reindex(tickers)


def risk_free(data_dir: Any) -> float:
    fred = M.load_fred(data_dir)
    if "DFF" in fred and fred["DFF"].notna().any():
        return float(fred["DFF"].dropna().iloc[-1]) / 100.0
    return 0.04


def model_forecasts(
    ctx: RunContext, t: pd.DataFrame, src: Sources
) -> tuple[pd.DataFrame | None, dict[str, Any]]:
    """Phase 4 hook: calibrated model forecasts if trained models are available."""
    import importlib

    try:
        serve = importlib.import_module("convergealpha.models.serve")
        result: tuple[pd.DataFrame | None, dict[str, Any]] = serve.predict(ctx, t, src)
        return result
    except Exception as e:  # missing models or a failure: fall back, and say so
        log.info("model forecasts unavailable (%s); using the fallback estimate", type(e).__name__)
        return None, {}


def decide(
    ctx: RunContext, t: pd.DataFrame, src: Sources, regime: dict[str, Any] | None
) -> tuple[pd.DataFrame, dict[str, Any]]:
    as_of = src.as_of
    t = FA.compute(t, src.panel, as_of)
    family_corr = t.attrs.pop(
        "family_corr", None
    )  # attrs would otherwise leak into Parquet metadata
    t.attrs = {}
    elig = t["eligible"].astype(bool)
    t["f2_pct"] = t["f2"].rank(pct=True)
    state = regime["state"] if regime else None

    model, model_meta = model_forecasts(ctx, t, src)
    # L1 score: model when available, else the equal-weight family average (a baseline, honest).
    if model is not None and "l1" in model:
        t["l1"] = model["l1"].reindex(t.index)
    else:
        t["l1"] = t["composite"]
    t["l1_rank_pct"] = t["l1"].where(elig).rank(pct=True)

    rf = risk_free(ctx.paths.data)
    beta = betas(src.panel, t.index.tolist())
    blocks = R.blocking_events(t)

    stock_sections: dict[str, dict[str, Any]] = {}
    out_cols: dict[str, dict[str, Any]] = {}
    for tk, r in t.iterrows():
        tk = str(tk)
        b = float(beta.get(tk, 1.0)) if pd.notna(beta.get(tk, np.nan)) else 1.0
        fc: dict[str, dict[str, float]] | None = None
        method = R.ForecastInputs(0, 0, 0, 0).method
        mrow = model.loc[tk] if model is not None and tk in model.index else None
        if mrow is not None and pd.notna(mrow.get("p_up_6m")):
            fc = {
                HORIZON_NAMES[h]: {
                    k: float(mrow.get(f"{k}_{HORIZON_NAMES[h]}", np.nan))
                    for k in ("p_up", "p_beat", "median", "p10", "p90", "p25")
                }
                | {"days": h}
                for h in HORIZONS
            }
            method = "model (walk-forward, calibrated)"
        else:
            fi = R.fallback_inputs(r, rf, b)
            if fi is not None:
                fc = R.forecast(fi)
        cost = R.round_trip_cost(r)
        pf: dict[str, Any] = {"provisional": mrow is None}
        if fc:
            p_hat = (
                float(mrow["p_hat"])
                if mrow is not None and pd.notna(mrow.get("p_hat"))
                else fc["3m"]["p_beat"]
            )
            pf["p_hat"] = p_hat
            if mrow is not None:
                pf["p_lower"] = None if pd.isna(mrow.get("p_lower")) else float(mrow["p_lower"])
                pf["meta"] = None if pd.isna(mrow.get("meta")) else float(mrow["meta"])
                w_bar = float(mrow.get("avg_win", np.nan))
                l_bar = float(mrow.get("avg_loss", np.nan))
                pf["analog_pass"] = (
                    None if pd.isna(mrow.get("analog_pass", np.nan)) else bool(mrow["analog_pass"])
                )
                pf["analog_text"] = mrow.get("analog_text") or "analog check not available"
            else:
                # Fallback: average win/loss of the 63-day excess return implied by the same
                # normal model as p_hat, so p*W - (1-p)*L equals the expected excess return.
                fi_ = R.fallback_inputs(r, rf, b)
                w_bar, l_bar = (
                    R.conditional_win_loss(fi_, 63) if fi_ is not None else (np.nan, np.nan)
                )
            if math.isfinite(w_bar) and math.isfinite(l_bar):
                pf["ev"] = stats.expected_value(p_hat, w_bar, l_bar, cost)
                pf["b"] = w_bar / l_bar if l_bar > 0 else None
        label, results, extra = R.evaluate(r, state, list(blocks.get(tk, [])), pf)
        if not bool(r.get("eligible")) and label in (R.LABEL_BUY, R.LABEL_TOP, R.LABEL_WATCH):
            label = R.LABEL_NONE
        six = fc["6m"] if fc else None
        vol_m = float(r.get("vol_63") or np.nan) / math.sqrt(12)
        gain_m = six["median"] / 6 if six else np.nan
        out_cols[tk] = {
            "label": label,
            "tier": extra.get("tier"),
            "ev": pf.get("ev"),
            "p_hat": pf.get("p_hat"),
            "gain_per_month": gain_m,
            "speed": gain_m / vol_m if six and vol_m > 0 else np.nan,
            **({f"p_up_{k}": v["p_up"] for k, v in fc.items()} if fc else {}),
            **({f"p_beat_{k}": v["p_beat"] for k, v in fc.items()} if fc else {}),
            "med_6m": six["median"] if six else np.nan,
            "p90_6m": six["p90"] if six else np.nan,
            "p10_6m": six["p10"] if six else np.nan,
            "p25_1m": fc["1m"]["p25"] if fc else np.nan,
            "blocked": bool(blocks.get(tk)),
            "block_reason": (blocks.get(tk) or [None])[0],
            "cost": cost,
            "beta": b,
            "forecast_method": method,
        }
        p_lower = pf.get("p_lower")
        stock_sections[tk] = {
            "decision": {
                "label": label,
                "why": R.why(label, r, results, extra),
                "tier": extra.get("tier"),
                "provisional": extra.get("provisional"),
                "research_mode": True,
                "rules": [
                    {"id": x.id, "text": x.text, "passed": x.passed, "value": x.value}
                    for x in results
                ],
                "blocking": list(blocks.get(tk, [])),
                "risk_reasons": extra.get("risk_reasons", []),
                "ev": pf.get("ev"),
                "p_hat": pf.get("p_hat"),
                "p_lower": p_lower,
                "meta": pf.get("meta"),
                "cost": cost,
            },
            "forecast": {
                "method": method,
                "validated": False,
                "horizons": fc,
                "inputs": None
                if mrow is not None or not fc
                else {
                    "beta": b,
                    "risk_free": rf,
                    "composite": None if pd.isna(r.get("composite")) else float(r["composite"]),
                },
                "options_move": {
                    "1w": _f(r.get("implied_move_1w")),
                    "1m": _f(r.get("implied_move_1m")),
                },
                "analog": model_meta.get("analogs", {}).get(tk),
                "sample_size": model_meta.get("sample_sizes", {}).get(tk),
            },
            "families": {**FA.explain(r), "inputs": _family_inputs(r)},
            "plan": R.plan(
                r,
                p_lower if p_lower is not None else pf.get("p_hat"),
                pf.get("b"),
                extra.get("tier"),
            ),
            "patterns": model_meta.get("patterns", {}).get(tk),
        }
    cols = pd.DataFrame.from_dict(out_cols, orient="index")
    for c in cols.columns:
        t[c] = cols[c].reindex(t.index)
    t["cluster"] = correlation_clusters(src.panel, t.index[elig].tolist()).reindex(t.index)
    # Insider buys filed in the last 7 days (Today page list).
    t["insider_buy_7d"] = _insider_7d(src, t, as_of)
    counts = Counter(t.loc[elig, "label"])
    log.info("labels: %s", dict(counts))

    cand = t[elig].sort_values("l1", ascending=False).index[:400].tolist()
    cand += t.index[t["label"].isin([R.LABEL_BUY, R.LABEL_TOP, R.LABEL_WATCH])].tolist()
    cand += t.index[elig & t["days_to_earnings"].between(-3, 7)].tolist()
    snapshot_cols = (
        [
            "f1",
            "f2",
            "f3",
            "f4",
            "f5",
            "f6",
            "f1_raw",
            "composite",
            "l1",
            "n_eff",
            "disagreement",
            "families_fresh",
            "ev",
            "p_hat",
            "gain_per_month",
            "speed",
            "med_6m",
            "p90_6m",
            "p10_6m",
            "price",
            "tier",
        ]
        + [f"p_up_{k}" for k in HORIZON_NAMES.values()]
        + [f"p_beat_{k}" for k in HORIZON_NAMES.values()]
    )
    snap = t[[c for c in snapshot_cols if c in t]].copy()
    snap["label"] = t["label"].astype(str)
    snap["blocked"] = t["blocked"].astype(bool)
    snap = snap.reset_index().rename(columns={"index": "ticker"})
    extra_out = {
        "stock_sections": stock_sections,
        "candidates": list(dict.fromkeys(cand)),
        "market": {
            "labels": dict(counts),
            "forecast_method": "model"
            if model is not None
            else "fallback estimate — not calibrated",
            "family_corr": family_corr.round(3).to_dict() if family_corr is not None else None,
        },
        "snapshots": {"scores": snap},
        "health": {
            "labels": dict(counts),
            "forecast_method": "model" if model is not None else "fallback",
            **model_meta.get("health", {}),
        },
        "files": model_meta.get("files", {}),
    }
    return t, extra_out


def _f(v: Any) -> float | None:
    try:
        x = float(v)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


def _family_inputs(r: pd.Series) -> dict[str, Any]:
    keys = [
        "consensus",
        "target_upside",
        "net_upgrades_90d",
        "finnhub_trend_score",
        "rev60",
        "rev_breadth",
        "sue",
        "days_since_report",
        "insider_buy_usd",
        "insider_buyers",
        "inst_top_change",
        "resid_mom",
        "industry_mom",
        "trend_up",
        "roic",
        "gp_assets",
        "accruals",
        "fcf_yield",
        "debt_ebitda",
    ]
    return {
        k: (
            _f(r.get(k))
            if k != "trend_up"
            else (None if r.get(k) is None or pd.isna(r.get(k)) else bool(r.get(k)))
        )
        for k in keys
    }


def _insider_7d(src: Sources, t: pd.DataFrame, as_of: pd.Timestamp) -> pd.Series:
    tr = src.trades
    if tr.empty:
        return pd.Series(np.nan, index=t.index)
    w = tr[
        (tr["filing_date"] > as_of - pd.Timedelta(days=7))
        & (tr["filing_date"] <= as_of)
        & tr["opportunistic"]
        & (tr["code"] == "P")
    ]
    by = w.groupby("issuer_cik")["value"].sum()
    return t["cik"].map(by).fillna(0.0).where(t["cik"].notna())
