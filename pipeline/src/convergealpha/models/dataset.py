"""Point-in-time training panel: features at each month-end and the outcomes that followed.

Features use only data public by the decision date (prices up to that close, SEC fundamentals by
filing date, insider trades by filing date, FINRA short interest by publication date). Analyst
families (F1, F2) have no history before live snapshots began, so they are not model inputs yet;
they are displayed as information (spec: new sources start at zero weight).

Labels: triple barrier (entry next open, upper E + 3 ATR, lower E - 2 ATR, 60 trading days;
"correct" = exit return - S&P 500 return - costs > 0) and forward returns at 5/21/63/126 days.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from convergealpha.config import GSPC, HORIZON_NAMES, HORIZONS, MIN_ADV_DOLLARS, MIN_PRICE, SPY
from convergealpha.features import families as FA
from convergealpha.features.price_features import wilder_atr
from convergealpha.features.regime import regime_series
from convergealpha.sources import fundamentals as F
from convergealpha.sources import insiders as I
from convergealpha.sources.prices import Panel
from convergealpha.util.log import get

log = get(__name__)

START = pd.Timestamp("2012-12-31")
BARRIER_UP, BARRIER_DN, BARRIER_DAYS = 3.0, 2.0, 60
DEFAULT_COST = 0.002  # round trip for eligible (liquid) stocks; the live model uses per-stock costs

FEATURES = [
    "mom_1m", "mom_3m", "mom_6m", "mom_12_2", "resid_mom", "industry_mom", "trend", "vol_63",
    "atr_pct", "dist_52w", "beta", "log_mcap", "log_adv", "insider_value", "roic", "gp_assets",
    "accruals", "fcf_yield", "debt_ebitda", "sue_srw", "days_since_report", "short_pct",
    "f3h", "f4h", "f5h", "f6h", "disagreement_h", "n_fam", "regime_code",
]  # fmt: skip
FAMILY_FEATURES = ["f3h", "f4h", "f5h", "f6h"]
# Outcome columns (forward-looking). No feature may ever share a name with these.
LABEL_PREFIXES = ("ret_", "up_", "beat_", "exc_", "tb_")


@dataclass
class History:
    panel: Panel
    stocks: pd.DataFrame  # index ticker: sector, industry_group, cik
    ttm: pd.DataFrame
    inst: pd.DataFrame
    trades: pd.DataFrame
    short: pd.DataFrame
    eps_sue: pd.DataFrame  # cik, end, known, sue
    regime: pd.DataFrame
    atr: pd.DataFrame
    resid: pd.DataFrame  # month-end x ticker residual momentum


def eps_surprise_series(facts: pd.DataFrame) -> pd.DataFrame:
    """Seasonal-random-walk SUE from first-reported quarterly diluted EPS:
    (EPS_q - EPS_{q-4}) / stdev of the previous 8 such changes. Known from the filing date.
    (Vectorized: as-of merge to the same quarter a year earlier, rolling stdev per company.)"""
    e = facts[(facts["item"] == "eps_diluted") & facts["start"].notna()]
    e = e[((e["end"] - e["start"]).dt.days.between(80, 100))]
    e = e.sort_values("filed").drop_duplicates(["cik", "end"], keep="first")
    if e.empty:
        return pd.DataFrame(columns=["cik", "end", "known", "sue"])
    cur = (
        e[["cik", "end", "val", "filed"]]
        .assign(target=e["end"] - pd.Timedelta(days=365))
        .sort_values("target")
    )
    prev = (
        e[["cik", "end", "val"]]
        .rename(columns={"end": "prev_end", "val": "prev_val"})
        .sort_values("prev_end")
    )
    m = pd.merge_asof(
        cur,
        prev,
        left_on="target",
        right_on="prev_end",
        by="cik",
        tolerance=pd.Timedelta(days=15),
        direction="nearest",
    )
    m = m.dropna(subset=["prev_val"]).sort_values(["cik", "end"]).reset_index(drop=True)
    m["d"] = m["val"] - m["prev_val"]
    sd = m.groupby("cik")["d"].transform(lambda x: x.shift(1).rolling(8, min_periods=4).std())
    sue = (m["d"] / sd).where(sd > 0).clip(-10, 10)
    out = pd.DataFrame({"cik": m["cik"], "end": m["end"], "known": m["filed"], "sue": sue})
    return out.dropna(subset=["sue"]).reset_index(drop=True)


def residual_momentum_panel(panel: Panel, sectors: pd.Series, months: int = 36) -> pd.DataFrame:
    """Residual momentum at every month-end, batched per sector (stocks with a full window)."""
    monthly = panel.tr.resample("ME").last().pct_change(fill_method=None)
    mkt = monthly[SPY]
    tickers = [t for t in sectors.index if t in monthly.columns]
    sec = sectors.reindex(tickers).fillna("Unknown")
    out = pd.DataFrame(np.nan, index=monthly.index, columns=tickers)
    sector_ret = {s: monthly[list(g.index)].mean(axis=1) for s, g in sec.groupby(sec)}
    for m in range(months, len(monthly)):
        win = monthly.iloc[m - months + 1 : m + 1]
        mk = mkt.iloc[m - months + 1 : m + 1].to_numpy()
        for s, g in sec.groupby(sec):
            cols = list(g.index)
            Y = win[cols]
            full = Y.notna().all().to_numpy()
            if full.sum() < 1 or np.isnan(mk).any():
                continue
            sr = sector_ret[s].iloc[m - months + 1 : m + 1].to_numpy()
            if np.isnan(sr).any():
                continue
            X = np.column_stack([np.ones(months), mk, sr])
            Yf = Y.to_numpy()[:, full]
            B, *_ = np.linalg.lstsq(X, Yf, rcond=None)
            R = Yf - X @ B
            sd = R.std(axis=0, ddof=1)
            val = R[-12:-1].sum(axis=0) / np.where(sd > 0, sd, np.nan)
            out.iloc[m, [out.columns.get_loc(c) for c in np.array(cols)[full]]] = val
    return out


def load_history(
    panel: Panel,
    stocks: pd.DataFrame,
    facts: pd.DataFrame,
    trades: pd.DataFrame,
    short: pd.DataFrame,
    fred: pd.DataFrame,
) -> History:
    t0 = time.time()
    q = F.quarterly_flows(facts) if not facts.empty else pd.DataFrame()
    ttm = F.ttm(q) if not q.empty else pd.DataFrame()
    inst = F.instants(facts) if not facts.empty else pd.DataFrame()
    sue = (
        eps_surprise_series(facts)
        if not facts.empty
        else pd.DataFrame(columns=["cik", "end", "known", "sue"])
    )
    spx = (
        panel.close[GSPC].astype("float64").dropna()
        if GSPC in panel.close
        else pd.Series(dtype=float)
    )
    vix = (
        fred["VIXCLS"]
        if "VIXCLS" in fred
        else panel.close.get("^VIX", pd.Series(dtype=float)).astype("float64")
    )
    hy = fred.get("BAMLH0A0HYM2")
    reg = regime_series(spx, vix, hy) if len(spx) else pd.DataFrame()
    atr = wilder_atr(
        panel.high.astype("float64"), panel.low.astype("float64"), panel.close.astype("float64")
    )
    sectors = stocks["sector"].fillna("Unknown")
    resid = residual_momentum_panel(panel, sectors)
    log.info(
        "history inputs ready in %.0fs (%d SUE points, %d TTM values)",
        time.time() - t0,
        len(sue),
        len(ttm),
    )
    return History(panel, stocks, ttm, inst, trades, short, sue, reg, atr, resid)


def _ret(tr: pd.DataFrame, i: int, n: int) -> pd.Series:
    if i - n < 0:
        return pd.Series(np.nan, index=tr.columns)
    return tr.iloc[i] / tr.iloc[i - n] - 1.0


def features_at(h: History, d: pd.Timestamp) -> pd.DataFrame:
    """Model features for every stock at the close of `d` (point-in-time)."""
    p = h.panel
    idx = p.close.index
    i = int(idx.searchsorted(d, side="right")) - 1
    d = idx[i]
    tickers = [t for t in h.stocks.index if t in p.close.columns]
    tr = p.tr[tickers]
    close = p.close[tickers].astype("float64")
    px = close.iloc[i]
    f = pd.DataFrame(index=pd.Index(tickers, name="ticker"))
    f["price"] = px
    f["mom_1m"] = _ret(tr, i, 21)
    f["mom_3m"] = _ret(tr, i, 63)
    f["mom_6m"] = _ret(tr, i, 126)
    f["mom_12_2"] = (tr.iloc[i - 21] / tr.iloc[i - 252] - 1.0) if i >= 252 else np.nan
    daily = np.log(tr.iloc[max(0, i - 63) : i + 1] / tr.iloc[max(0, i - 63) : i + 1].shift(1))
    f["vol_63"] = daily.std() * math.sqrt(252)
    f["atr_pct"] = h.atr[tickers].iloc[i] / px
    hi = p.high[tickers].iloc[max(0, i - 251) : i + 1].astype("float64").max()
    f["dist_52w"] = px / hi - 1.0
    s50 = close.iloc[max(0, i - 49) : i + 1].mean()
    s200 = close.iloc[max(0, i - 199) : i + 1].mean()
    f["trend"] = (
        ((px > s50) & (s50 > s200))
        .astype(float)
        .where(close.iloc[max(0, i - 199) : i + 1].count() >= 180)
    )
    vol = p.volume[tickers].iloc[max(0, i - 20) : i + 1]
    adv = (close.iloc[max(0, i - 20) : i + 1] * vol).mean()
    f["adv"] = adv
    f["log_adv"] = np.log(adv.where(adv > 0))
    rets = tr.iloc[max(0, i - 252) : i + 1].pct_change(fill_method=None).iloc[1:]
    if SPY in p.tr:
        m = p.tr[SPY].iloc[max(0, i - 252) : i + 1].pct_change(fill_method=None).iloc[1:]
        mc = m - m.mean()
        cov = (rets - rets.mean()).mul(mc, axis=0).mean()
        f["beta"] = (cov / mc.var(ddof=0)).where(rets.count() >= 120).clip(-1, 4)
    else:
        f["beta"] = np.nan
    # Residual and industry momentum (as of the last completed month-end <= d).
    me = h.resid.index[h.resid.index <= d]
    f["resid_mom"] = h.resid.loc[me[-1]].reindex(tickers) if len(me) else np.nan
    grp = (
        h.stocks["industry_group"]
        .reindex(tickers)
        .where(
            h.stocks["industry_group"].reindex(tickers).notna(), h.stocks["sector"].reindex(tickers)
        )
    )
    f["industry_mom"] = FA.industry_momentum(f["mom_6m"], grp)

    cik = h.stocks["cik"].reindex(tickers)
    # Size: SEC shares outstanding as of d.
    if not h.inst.empty:
        sh = F.as_of(h.inst[h.inst["item"] == "shares_out"], d)
        shares = (
            cik.map(sh["shares_out"]) if "shares_out" in sh else pd.Series(np.nan, index=tickers)
        )
    else:
        shares = pd.Series(np.nan, index=tickers)
    mcap = shares * px
    f["log_mcap"] = np.log(mcap.where(mcap > 0))
    # Fundamentals (F6 inputs).
    if not h.ttm.empty:
        mc_by_cik = pd.Series(mcap.to_numpy(), index=cik.to_numpy()).dropna()
        mc_by_cik = mc_by_cik[~mc_by_cik.index.duplicated()]
        f6 = F.f6_inputs(h.ttm, h.inst, d, mc_by_cik)
        for c in ("roic", "gp_assets", "accruals", "fcf_yield", "debt_ebitda"):
            f[c] = cik.map(f6[c]) if c in f6 else np.nan
        known = F.known_dates(h.ttm, d)
        f["f6_age"] = (d - cik.map(known)).dt.days
    else:
        for c in ("roic", "gp_assets", "accruals", "fcf_yield", "debt_ebitda", "f6_age"):
            f[c] = np.nan
    # Insiders (F4).
    if not h.trades.empty:
        f4 = I.f4_raw(h.trades, d)
        f["insider_value"] = (
            cik.map(f4["insider_value"]).fillna(0.0).where(cik.notna())
            if "insider_value" in f4
            else 0.0
        )
    else:
        f["insider_value"] = np.nan
    # Earnings surprise (seasonal random walk, from 10-Q/10-K EPS) and days since that filing.
    if not h.eps_sue.empty:
        s = (
            h.eps_sue[h.eps_sue["known"] <= d]
            .sort_values("known")
            .drop_duplicates("cik", keep="last")
            .set_index("cik")
        )
        f["sue_srw"] = cik.map(s["sue"])
        f["days_since_report"] = (d - cik.map(s["known"])).dt.days * 5 / 7
    else:
        f["sue_srw"] = np.nan
        f["days_since_report"] = np.nan
    # Short interest (FINRA, published by d).
    if not h.short.empty:
        si = (
            h.short[h.short["published"] <= d]
            .sort_values("settlement")
            .drop_duplicates("ticker", keep="last")
            .set_index("ticker")
        )
        f["short_pct"] = (si["short_shares"].reindex(tickers) / shares).where(shares > 0)
    else:
        f["short_pct"] = np.nan
    # Regime.
    code = {"Normal": 0.0, "Caution": 1.0, "Stress": 2.0}
    if not h.regime.empty:
        r = h.regime.loc[:d, "state"].dropna()
        f["regime_code"] = code.get(r.iloc[-1], np.nan) if len(r) else np.nan
        f["regime"] = r.iloc[-1] if len(r) else None
    else:
        f["regime_code"] = np.nan
        f["regime"] = None
    f["sector"] = h.stocks["sector"].reindex(tickers)
    f["eligible"] = (px >= MIN_PRICE) & (adv >= MIN_ADV_DOLLARS) & close.iloc[i].notna()
    return add_families(f)


def add_families(f: pd.DataFrame) -> pd.DataFrame:
    """Historical family scores (same normalization as the live families), on the eligible set."""
    sec = f["sector"].fillna("Unknown")
    z = FA.zsc
    f3 = FA.norm(z(f["sue_srw"], sec).where(f["days_since_report"].between(1, 70)), sec)
    f4 = FA.norm(f["insider_value"], sec)
    f5_raw = FA.combine(
        [
            (z(f["resid_mom"], sec), 0.5),
            (z(f["industry_mom"], sec), 0.25),
            (z(f["trend"], sec), 0.25),
        ]
    )
    f5 = FA.norm(f5_raw, sec)
    hot = f["mom_1m"] >= f["mom_1m"].quantile(0.95)
    f5 = f5.where(~hot, f5.clip(upper=60))
    f6_raw = FA.combine(
        [
            (z(f["roic"], sec), 1.0),
            (z(f["gp_assets"], sec), 1.0),
            (-z(f["accruals"], sec), 1.0),
            (z(f["fcf_yield"], sec), 1.0),
            (-z(f["debt_ebitda"], sec), 1.0),
        ]
    )
    f6 = FA.norm(f6_raw, sec).where(f.get("f6_age", pd.Series(0, index=f.index)) <= 200)
    f["f3h"], f["f4h"], f["f5h"], f["f6h"] = f3, f4, f5, f6
    fam = f[FAMILY_FEATURES]
    f["n_fam"] = fam.notna().sum(axis=1)
    f["disagreement_h"] = fam.std(axis=1, ddof=0).where(f["n_fam"] >= 2)
    f["composite_h"] = fam.mean(axis=1).where(f["n_fam"] >= 2)
    return f


def labels_at(h: History, d: pd.Timestamp, tickers: list[str]) -> pd.DataFrame:
    """Triple-barrier outcome and horizon returns for a decision at the close of `d`."""
    p = h.panel
    idx = p.close.index
    i = int(idx.searchsorted(d, side="right")) - 1
    n = len(idx)
    out = pd.DataFrame(index=pd.Index(tickers, name="ticker"))
    tr = p.tr[tickers]
    spy = p.tr[SPY] if SPY in p.tr else None
    for hz in HORIZONS:
        name = HORIZON_NAMES[hz]
        if i + hz < n:
            r = tr.iloc[i + hz] / tr.iloc[i] - 1.0
            out[f"ret_{name}"] = r
            out[f"up_{name}"] = (r > 0).astype(float).where(r.notna())
            if spy is not None:
                sr = float(spy.iloc[i + hz] / spy.iloc[i] - 1.0)
                out[f"exc_{name}"] = r - sr
                out[f"beat_{name}"] = (r - sr > 0).astype(float).where(r.notna())
    # Triple barrier.
    if i + 1 + BARRIER_DAYS <= n - 1:
        sl = slice(i + 1, i + 1 + BARRIER_DAYS)
        O = p.open[tickers].iloc[sl].to_numpy(dtype="float64")
        H = p.high[tickers].iloc[sl].to_numpy(dtype="float64")
        L = p.low[tickers].iloc[sl].to_numpy(dtype="float64")
        C = p.close[tickers].iloc[sl].to_numpy(dtype="float64")
        entry = O[0]
        atr = h.atr[tickers].iloc[i].to_numpy(dtype="float64")
        up = entry + BARRIER_UP * atr
        dn = entry - BARRIER_DN * atr
        lo_hit = np.nan_to_num(L, nan=np.inf) <= dn
        hi_hit = np.nan_to_num(H, nan=-np.inf) >= up
        k = BARRIER_DAYS
        first_lo = np.where(lo_hit.any(axis=0), lo_hit.argmax(axis=0), k)
        first_hi = np.where(hi_hit.any(axis=0), hi_hit.argmax(axis=0), k)
        exit_day = np.minimum(first_lo, first_hi)
        loss = (first_lo <= first_hi) & (first_lo < k)  # same day: assume the loss came first
        win = (first_hi < first_lo) & (first_hi < k)
        cols = np.arange(len(tickers))
        o_exit = O[np.minimum(exit_day, k - 1), cols]
        gap_ok = exit_day > 0
        px_loss = np.where(gap_ok, np.fmin(dn, o_exit), dn)
        px_win = np.where(gap_ok, np.fmax(up, o_exit), up)
        last_close = pd.DataFrame(C).ffill().to_numpy()[-1]
        px_exit = np.where(loss, px_loss, np.where(win, px_win, last_close))
        day = np.where(loss | win, exit_day, k - 1)
        ret = px_exit / entry - 1.0
        if spy is not None:
            s_open = p.open[SPY].iloc[sl].to_numpy(dtype="float64")
            s_close = p.close[SPY].iloc[sl].to_numpy(dtype="float64")
            spy_ret = s_close[day] / s_open[0] - 1.0
        else:
            spy_ret = np.zeros(len(tickers))
        excess = ret - spy_ret - DEFAULT_COST
        valid = np.isfinite(entry) & np.isfinite(atr) & (atr > 0) & np.isfinite(ret)
        out["tb_ret"] = np.where(valid, ret, np.nan)
        out["tb_excess"] = np.where(valid, excess, np.nan)
        out["tb_correct"] = np.where(valid, (excess > 0).astype(float), np.nan)
        out["tb_outcome"] = np.where(valid, np.where(win, 1, np.where(loss, -1, 0)), np.nan)
        out["tb_days"] = np.where(valid, day + 1, np.nan)
    return out


def month_ends(index: pd.DatetimeIndex, start: pd.Timestamp = START) -> list[pd.Timestamp]:
    s = pd.Series(index, index=index)
    me = s.groupby([index.year, index.month]).max()
    return [d for d in me if d >= start]


def build(
    h: History, dates: list[pd.Timestamp] | None = None, with_labels: bool = True
) -> pd.DataFrame:
    dates = dates or month_ends(h.panel.close.index)
    frames = []
    t0 = time.time()
    for k, d in enumerate(dates):
        f = features_at(h, d)
        f = f[f["eligible"]]
        if with_labels:
            f = f.join(labels_at(h, d, f.index.tolist()))
        f.insert(0, "date", d)
        frames.append(f.reset_index())
        if k % 24 == 0:
            log.info(
                "dataset: %s (%d/%d) %d rows, %.0fs",
                d.date(),
                k + 1,
                len(dates),
                len(f),
                time.time() - t0,
            )
    return pd.concat(frames, ignore_index=True)


def summary(df: pd.DataFrame) -> dict[str, Any]:
    return {
        "rows": len(df),
        "dates": int(df["date"].nunique()),
        "first": str(df["date"].min().date()),
        "last": str(df["date"].max().date()),
        "labelled_tb": int(df["tb_correct"].notna().sum()) if "tb_correct" in df else 0,
        "base_rate_tb": float(df["tb_correct"].mean()) if "tb_correct" in df else None,
    }
