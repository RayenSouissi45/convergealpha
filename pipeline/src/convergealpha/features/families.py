"""The six alpha evidence families (F1-F6), their agreement (D) and independence (N_eff).

Every raw signal is normalized across the universe (winsorize 1/99%, robust z inside the sector,
clip +-3, score = 100*Phi(z)). A family score is the average of its signal scores, normalized
again the same way. F7 (context) never votes; it only blocks or shrinks trades (decide/rules.py).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from convergealpha.config import GSPC, SPY
from convergealpha.core import stats
from convergealpha.sources.prices import Panel

FAMILIES = ("f1", "f2", "f3", "f4", "f5", "f6")
FAMILY_NAMES = {
    "f1": "Opinion",
    "f2": "Revisions",
    "f3": "Earnings events",
    "f4": "Insiders & ownership",
    "f5": "Price & trend",
    "f6": "Quality & value",
}


def norm(values: pd.Series, sectors: pd.Series) -> pd.Series:
    """0-100 score of one raw signal (NaN stays NaN)."""
    sec = sectors.fillna("Unknown").astype(str)
    return pd.Series(
        stats.robust_sector_scores(values.astype("float64").to_numpy(), sec.to_numpy()),
        index=values.index,
    )


def zsc(values: pd.Series, sectors: pd.Series) -> pd.Series:
    """Robust z (clipped) of one raw signal, for weighted combinations inside a family."""
    s = norm(values, sectors) / 100.0
    s = s.clip(1e-6, 1 - 1e-6)
    from scipy.stats import norm as _n

    return pd.Series(_n.ppf(s), index=values.index).where(values.notna())


def combine(parts: list[tuple[pd.Series, float]]) -> pd.Series:
    """Weighted mean of available parts (weights renormalized over what each stock has)."""
    num = pd.Series(0.0, index=parts[0][0].index)
    den = pd.Series(0.0, index=parts[0][0].index)
    for s, w in parts:
        ok = s.notna()
        num = num + s.fillna(0.0) * w
        den = den + ok.astype(float) * w
    return (num / den).where(den > 0)


# --------------------------------------------------------------------------- F5 inputs from prices


def residual_momentum(
    panel: Panel, sectors: pd.Series, as_of: pd.Timestamp | None = None, months: int = 36
) -> pd.Series:
    """Regress each stock's last 36 monthly returns on the market and its sector's return;
    residual momentum = sum of residuals over months t-12..t-2 / stdev(residuals)."""
    tr = panel.tr if as_of is None else panel.tr.loc[:as_of]
    monthly = tr.resample("ME").last().pct_change(fill_method=None).iloc[-(months + 1) :]
    monthly = monthly.iloc[1:] if len(monthly) > months else monthly
    if SPY not in monthly:
        return pd.Series(np.nan, index=sectors.index)
    mkt = monthly[SPY]
    stocks = [t for t in sectors.index if t in monthly.columns]
    sec = sectors.reindex(stocks).fillna("Unknown")
    sector_ret = {s: monthly[list(g.index)].mean(axis=1) for s, g in sec.groupby(sec)}
    out = {}
    for t in stocks:
        y = monthly[t]
        x = pd.concat([mkt, sector_ret[sec[t]]], axis=1)
        ok = y.notna() & x.notna().all(axis=1)
        if ok.sum() < 24:
            continue
        X = np.column_stack([np.ones(int(ok.sum())), x[ok].to_numpy()])
        coef, *_ = np.linalg.lstsq(X, y[ok].to_numpy(), rcond=None)
        resid = pd.Series(y[ok].to_numpy() - X @ coef, index=y[ok].index)
        sd = resid.std()
        window = resid.iloc[-12:-1]  # months t-12 .. t-2 (skip the most recent month)
        if sd > 0 and len(window) >= 9:
            out[t] = float(window.sum() / sd)
    return pd.Series(out).reindex(sectors.index)


def industry_momentum(ret_6m: pd.Series, groups: pd.Series, min_members: int = 5) -> pd.Series:
    """Average 6-month return of the stock's industry group (3-digit SIC; sector if too small)."""
    g = groups.fillna("none")
    counts = g.map(g.value_counts())
    avg = ret_6m.groupby(g).transform("mean")
    return avg.where(counts >= min_members)


# --------------------------------------------------------------------------- families


def compute(t: pd.DataFrame, panel: Panel, as_of: pd.Timestamp) -> pd.DataFrame:
    """Add f1..f6, their raw inputs, freshness flags, D and N_eff to the evidence table."""
    t = t.copy()
    sec = t["sector"].fillna("Unknown")
    fresh_analyst = (as_of - pd.to_datetime(t["analyst_fetched_at"])).dt.days <= 8

    # F2 revisions: 0.6 z(Rev60) + 0.4 z(Breadth) (+ next year's EPS revision when available).
    f2_raw = combine(
        [
            (zsc(t["rev60"], sec), 0.6),
            (zsc(t["rev_breadth"], sec), 0.4),
            (zsc(t["rev60_next_year"], sec), 0.2),
        ]
    )
    t["f2"] = norm(f2_raw, sec).where(fresh_analyst)

    # F3 earnings events: 0.5 z(SUE) + 0.3 z(revenue surprise: not available free) + 0.2 z(guidance/tone).
    tone = t["news_sentiment"] if "news_sentiment" in t else pd.Series(np.nan, index=t.index)
    in_window = t["days_since_report"].between(1, 70)
    f3_raw = combine([(zsc(t["sue"], sec), 0.5), (zsc(tone, sec), 0.2)])
    t["f3"] = norm(f3_raw.where(in_window), sec)

    # F5 price & trend.
    t["resid_mom"] = residual_momentum(panel, sec, as_of)
    t["industry_mom"] = industry_momentum(
        t["ret_6m"], t["industry_group"].where(t["industry_group"].notna(), sec)
    )
    trend = t["trend_up"].map({True: 1.0, False: 0.0}).astype("float64")
    f5_raw = combine(
        [
            (zsc(t["resid_mom"], sec), 0.5),
            (zsc(t["industry_mom"], sec), 0.25),
            (zsc(trend, sec), 0.25),
        ]
    )
    f5 = norm(f5_raw, sec)
    hot = t["ret_1m"] >= t["ret_1m"].quantile(0.95)  # reversal guard
    t["f5"] = f5.where(~hot, f5.clip(upper=60.0)).where(t["history_days"] >= 252)

    # F6 quality & value (SEC XBRL, point-in-time).
    if "gp_assets" in t:
        parts = [
            (zsc(t["roic"], sec), 1.0),
            (zsc(t["gp_assets"], sec), 1.0),
            (-zsc(t["accruals"], sec), 1.0),
            (zsc(t["fcf_yield"], sec), 1.0),
            (-zsc(t["debt_ebitda"], sec), 1.0),
        ]
        known = pd.to_datetime(t.get("fundamentals_as_of"))
        t["f6"] = norm(combine(parts), sec).where((as_of - known).dt.days <= 200)
    else:
        t["f6"] = np.nan

    # F4 insiders & ownership: opportunistic insider value + institutional accumulation.
    inst = combine(
        [(zsc(t["inst_top_change"], sec), 0.5), (zsc(t["inst_net_buying_pct"], sec), 0.5)]
    )
    f4_raw = combine([(zsc(t["insider_value"], sec), 0.7), (inst, 0.3)])
    t["f4"] = norm(f4_raw, sec).where(t["cik"].notna())

    # F1 opinion: credibility-weighted mean of the opinion sources, then residualized on F2 and F5
    # so platforms only count for what they know beyond revisions and momentum.
    sources = credibility_sources(t, sec)
    weights = source_weights()
    f1_raw = combine([(sources[k], weights.get(k, 0.03)) for k in sources])
    t["f1_raw"] = f1_raw.where(fresh_analyst)
    t["f1"] = norm(residualize(t["f1_raw"], t["f2"], t["f5"]), sec)

    fam = t[list(FAMILIES)]
    t["families_fresh"] = fam.notna().sum(axis=1)
    t["disagreement"] = fam.std(axis=1, ddof=0).where(t["families_fresh"] >= 3)
    corr = family_correlation(t)
    t["n_eff"] = [_n_eff_row(r, corr) for r in fam.to_numpy()]
    t["composite"] = fam.mean(axis=1).where(t["families_fresh"] >= 3)
    t.attrs["family_corr"] = corr
    return t


def credibility_sources(t: pd.DataFrame, sec: pd.Series) -> dict[str, pd.Series]:
    """Each opinion platform as a 0-100 score (one family however many platforms)."""
    out = {
        "yahoo_consensus": norm(t["yahoo_rec_score"], sec),
        "yahoo_trend": norm(t["yahoo_trend_score"], sec),
        "finnhub_trend": norm(t["finnhub_trend_score"], sec),
        "target_upside": norm(t["target_upside"].clip(-0.9, 3.0), sec),
        "rating_changes": norm(t["net_upgrades_90d"] + 3 * t["pt_change_90d"].fillna(0), sec),
    }
    for name, scores in (t.attrs.get("manual_ratings") or {}).items():
        out[f"manual_{name}"] = norm(scores.reindex(t.index), sec)
    return out


def source_weights() -> dict[str, float]:
    """c = max(h - 0.47, 0.01) with h = (wins + 10)/(signals + 20).

    Credibility is measured by the app itself on one protocol; with no measured history every
    source starts at h = 0.5 -> c = 0.03 (equal weights). decide/credibility.py updates this.
    """
    import importlib

    try:
        weights: dict[str, float] = importlib.import_module(
            "convergealpha.models.credibility"
        ).measured_weights()
        return weights
    except Exception:
        return {}


def residualize(f1: pd.Series, f2: pd.Series, f5: pd.Series) -> pd.Series:
    """F1 = F1_raw - (a + b2 F2 + b5 F5), fitted across stocks that have all three."""
    df = pd.concat([f1, f2, f5], axis=1, keys=["y", "f2", "f5"])
    ok = df.notna().all(axis=1)
    if ok.sum() < 30:
        return f1
    X = np.column_stack([np.ones(int(ok.sum())), df.loc[ok, "f2"], df.loc[ok, "f5"]])
    coef, *_ = np.linalg.lstsq(X, df.loc[ok, "y"].to_numpy(), rcond=None)
    pred = coef[0] + coef[1] * df["f2"].fillna(50.0) + coef[2] * df["f5"].fillna(50.0)
    return f1 - pred


def family_correlation(t: pd.DataFrame) -> pd.DataFrame:
    """Correlation of family scores. The spec wants a trailing 3-year time-series correlation;
    until enough history of all six families exists, the cross-section of eligible stocks today
    is used (models/history.py replaces it with the backtest panel where available)."""
    fam = t.loc[t.get("eligible", True) == True, list(FAMILIES)]  # noqa: E712
    corr = fam.corr(min_periods=50)
    return corr.fillna(0.0).where(~np.eye(len(FAMILIES), dtype=bool), 1.0)


def _n_eff_row(row: np.ndarray, corr: pd.DataFrame) -> float:
    bullish = [i for i, v in enumerate(row) if not math.isnan(v) and v > 50.0]
    if not bullish:
        return 0.0
    rho = corr.to_numpy()[np.ix_(bullish, bullish)]
    try:
        return stats.n_eff(np.ones(len(bullish)), rho)
    except ValueError:
        return float(len(bullish))


def explain(row: pd.Series) -> dict[str, Any]:
    """Plain-language description of a stock's families for the stock page."""
    out = []
    for f in FAMILIES:
        v = row.get(f)
        out.append(
            {"id": f, "name": FAMILY_NAMES[f], "score": None if pd.isna(v) else round(float(v), 1)}
        )
    return {
        "families": out,
        "n_eff": _f(row.get("n_eff")),
        "disagreement": _f(row.get("disagreement")),
        "fresh": int(row.get("families_fresh", 0)),
    }


def _f(v: Any) -> float | None:
    try:
        x = float(v)
        return None if math.isnan(x) else round(x, 2)
    except (TypeError, ValueError):
        return None


def _unused() -> tuple[str, str]:
    return GSPC, SPY
