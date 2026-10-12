"""Assemble every source into one evidence row per stock, as of the decision date.

Only information public by the decision time is used: SEC data by filing date, short interest by
FINRA publication date, analyst data by snapshot time, insider trades by filing date.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from convergealpha.sources import fundamentals as F
from convergealpha.sources import insiders as I
from convergealpha.sources.prices import Panel
from convergealpha.util.calendar import trading_days_between

ITEM_8K = {
    "1.01": "Material agreement", "1.02": "Agreement terminated", "1.03": "Bankruptcy or receivership",
    "2.01": "Acquisition or disposal completed", "2.02": "Results of operations", "2.03": "New financial obligation",
    "2.04": "Obligation accelerated", "2.05": "Exit or restructuring costs", "2.06": "Impairment",
    "3.01": "Delisting notice", "3.02": "Unregistered sale of equity", "3.03": "Change to shareholder rights",
    "4.01": "Auditor change", "4.02": "Prior financials no longer reliable (restatement)",
    "5.01": "Change in control", "5.02": "Director or officer change", "5.03": "Charter or bylaw amendment",
    "5.07": "Shareholder vote", "7.01": "Regulation FD disclosure", "8.01": "Other events", "9.01": "Financial exhibits",
}  # fmt: skip

OFFERING_FORMS = ("424B1", "424B4", "424B5", "424B7", "S-1", "S-1/A", "F-1")
MERGER_FORMS = ("DEFM14A", "PREM14A", "SC 14D9", "SC TO-T", "425", "DEFM14C", "PREM14C")
LATE_FORMS = ("NT 10-K", "NT 10-Q", "NT 20-F")


def rec_label(mean: float) -> str | None:
    if not math.isfinite(mean):
        return None
    if mean <= 1.5:
        return "Strong buy"
    if mean <= 2.5:
        return "Buy"
    if mean <= 3.5:
        return "Hold"
    if mean <= 4.5:
        return "Sell"
    return "Strong sell"


def _f(v: Any) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else math.nan
    except (TypeError, ValueError):
        return math.nan


@dataclass
class Sources:
    """Everything loaded for one build."""

    panel: Panel
    snap: pd.DataFrame  # price features per ticker
    stocks: pd.DataFrame  # universe rows (index ticker)
    companies: pd.DataFrame  # SEC company records (cik, sector, ...)
    yahoo: pd.DataFrame  # latest summary per ticker
    options: pd.DataFrame  # latest options per ticker
    upgrades: pd.DataFrame
    earnings_dates: pd.DataFrame
    trades: pd.DataFrame  # classified insider trades
    ttm: pd.DataFrame
    instants: pd.DataFrame
    short: pd.DataFrame  # latest short interest per ticker
    finnhub_rec: pd.DataFrame
    calendar: pd.DataFrame  # finnhub earnings calendar
    news: pd.DataFrame  # scored news
    filings: pd.DataFrame
    as_of: pd.Timestamp
    extras: dict[str, Any] = field(default_factory=dict)


def sue_table(earnings_dates: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Standardized unexpected earnings at the last report public by `as_of`:
    (actual - consensus) / stdev of the previous 8 surprises (in $ per share)."""
    if earnings_dates.empty:
        return pd.DataFrame(
            columns=[
                "sue",
                "last_report",
                "last_surprise_pct",
                "last_eps_actual",
                "last_eps_estimate",
            ]
        )
    e = earnings_dates.dropna(subset=["eps_actual", "eps_estimate"])
    e = e[e["datetime"] <= as_of].sort_values(["ticker", "datetime"])
    e = e.assign(surprise=e["eps_actual"] - e["eps_estimate"])
    out = {}
    for t, g in e.groupby("ticker"):
        if g.empty:
            continue
        last = g.iloc[-1]
        prior = g["surprise"].iloc[-9:-1]
        sd = prior.std() if len(prior) >= 4 else np.nan
        floor = max(abs(float(last["eps_estimate"])) * 0.02, 0.01)
        sue = float(last["surprise"]) / max(sd, floor) if pd.notna(sd) else np.nan
        out[t] = {
            "sue": float(np.clip(sue, -10, 10)) if pd.notna(sue) else np.nan,
            "last_report": last["datetime"],
            "last_surprise_pct": float(last["surprise_pct"])
            if pd.notna(last["surprise_pct"])
            else np.nan,
            "last_eps_actual": float(last["eps_actual"]),
            "last_eps_estimate": float(last["eps_estimate"]),
            "last_after_close": bool(last.get("after_close", False)),
        }
    return pd.DataFrame.from_dict(out, orient="index")


def tradable_reaction(
    panel: Panel, ticker: str, when: pd.Timestamp, after_close: bool
) -> tuple[float, float, pd.Timestamp | None]:
    """Return from the first tradable price after the news (next open) to 1 and 5 sessions later."""
    if ticker not in panel.close.columns:
        return math.nan, math.nan, None
    idx = panel.close.index
    local = (
        when.tz_localize("UTC").tz_convert("America/New_York")
        if when.tzinfo is None
        else when.tz_convert("America/New_York")
    )
    day = pd.Timestamp(local.date())
    # Before 9:30 -> that day's open; during or after the session -> next session's open.
    pos = idx.searchsorted(day)
    if pos < len(idx) and idx[pos] == day and (local.hour, local.minute) >= (9, 30):
        pos += 1
    if after_close and pos < len(idx) and idx[pos] == day:
        pos += 1
    if pos >= len(idx):
        return math.nan, math.nan, None
    o = float(panel.open[ticker].iloc[pos])
    c1 = float(panel.close[ticker].iloc[pos])
    c5 = (
        float(panel.close[ticker].iloc[min(pos + 4, len(idx) - 1)])
        if pos + 4 < len(idx)
        else math.nan
    )
    if not (o > 0):
        return math.nan, math.nan, idx[pos]
    return c1 / o - 1.0, (c5 / o - 1.0) if math.isfinite(c5) else math.nan, idx[pos]


def build_table(src: Sources) -> pd.DataFrame:
    """One row per stock with every evidence input used by families, labels and the screener."""
    as_of = src.as_of
    t = src.stocks.join(src.snap, how="left")
    comp = (
        src.companies.set_index("cik")
        if not src.companies.empty and "cik" in src.companies
        else pd.DataFrame()
    )
    cik = t["cik"]
    for col, name in (
        ("sector", "sector"),
        ("sic_description", "industry"),
        ("industry_group", "industry_group"),
        ("sic", "sic"),
    ):
        t[name] = cik.map(comp[col]) if col in comp else np.nan
    # Yahoo sector as a fallback for companies without an SEC SIC code (some foreign filers).
    y = src.yahoo
    if not y.empty:
        yahoo_sector = {
            "Technology": "Information Technology",
            "Financial Services": "Financials",
            "Healthcare": "Health Care",
            "Consumer Cyclical": "Consumer Discretionary",
            "Consumer Defensive": "Consumer Staples",
            "Basic Materials": "Materials",
            "Communication Services": "Communication Services",
            "Energy": "Energy",
            "Industrials": "Industrials",
            "Real Estate": "Real Estate",
            "Utilities": "Utilities",
        }
        fallback = y["sector_y"].map(yahoo_sector) if "sector_y" in y else pd.Series(dtype=object)
        t["sector"] = t["sector"].where(t["sector"].notna(), fallback.reindex(t.index))
        t["industry"] = t["industry"].where(
            t["industry"].notna(), y.get("industry_y", pd.Series(dtype=object)).reindex(t.index)
        )

    # ---- size: SEC shares outstanding (point-in-time) -> market cap
    shares = (
        F.as_of(src.instants[src.instants["item"] == "shares_out"], as_of)
        if not src.instants.empty
        else pd.DataFrame()
    )
    sec_shares = (
        cik.map(shares["shares_out"])
        if "shares_out" in shares
        else pd.Series(np.nan, index=t.index)
    )
    y_shares = (
        y["shares_out_y"].reindex(t.index)
        if "shares_out_y" in y
        else pd.Series(np.nan, index=t.index)
    )
    t["shares_out"] = sec_shares.where(sec_shares.notna(), y_shares)
    t["market_cap"] = t["shares_out"] * t["price"]

    # ---- analysts (Yahoo)
    def ycol(c: str) -> pd.Series:
        return (
            y[c].reindex(t.index) if (not y.empty and c in y) else pd.Series(np.nan, index=t.index)
        )

    t["analyst_fetched_at"] = ycol("fetched_at")
    t["consensus"] = ycol("rec_mean")
    t["n_analysts"] = ycol("n_analysts")
    t["target_mean"] = ycol("target_mean")
    t["target_upside"] = t["target_mean"] / t["price"] - 1.0
    t["yahoo_rec_score"] = (5.0 - t["consensus"]) / 4.0 * 100.0
    cur, ago = ycol("eps_0y_cur"), ycol("eps_0y_60d")
    t["rev60"] = ((cur - ago) / ago.abs()).where(ago.abs() > 1e-6)
    n0 = ycol("eps_0y_n").where(lambda s: s > 0)
    t["rev_breadth"] = (ycol("eps_0y_up30") - ycol("eps_0y_down30")) / n0
    rcur, rago = ycol("eps_1y_cur"), ycol("eps_1y_60d")
    t["rev60_next_year"] = ((rcur - rago) / rago.abs()).where(rago.abs() > 1e-6)
    sb, b, h, s_, ss = (
        ycol(f"rt_0m_{k}") for k in ("strongBuy", "buy", "hold", "sell", "strongSell")
    )
    total = sb + b + h + s_ + ss
    t["yahoo_trend_score"] = ((2 * sb + b - s_ - 2 * ss) / total).where(total > 0)
    t["top_rated_sources"] = 0
    t["short_pct_float_y"] = ycol("short_pct_float")
    t["inst_pct"] = ycol("inst_pct")
    t["insider_pct"] = ycol("insider_pct")
    t["inst_top_change"] = ycol("inst_top_change")
    t["inst_net_buying_pct"] = ycol("inst_net_buying_pct")
    t["float_shares"] = ycol("float_shares")

    # ---- Finnhub recommendation trend (second opinion source)
    fr = src.finnhub_rec
    if not fr.empty:
        latest = fr.sort_values("period").drop_duplicates("ticker", keep="last").set_index("ticker")
        tot = latest[["strong_buy", "buy", "hold", "sell", "strong_sell"]].sum(axis=1)
        score = (
            2 * latest["strong_buy"] + latest["buy"] - latest["sell"] - 2 * latest["strong_sell"]
        ) / tot
        t["finnhub_trend_score"] = score.where(tot > 0).reindex(t.index)
        t["finnhub_n"] = tot.reindex(t.index)
    else:
        t["finnhub_trend_score"] = np.nan
        t["finnhub_n"] = np.nan
    # Sources at their top rating (C4): consensus <= 1.5, Finnhub trend >= 1.2 (mostly strong buys).
    t["top_rated_sources"] = (t["consensus"] <= 1.5).astype(int) + (
        t["finnhub_trend_score"] >= 1.2
    ).astype(int)

    # ---- rating changes over 90 days (point-in-time history exists, so this is backtestable)
    up = src.upgrades
    if not up.empty:
        w = up[(up["date"] <= as_of) & (up["date"] > as_of - pd.Timedelta(days=90))]
        act = w["action"].str.lower()
        net = (act == "up").astype(int) - (act == "down").astype(int)
        t["net_upgrades_90d"] = net.groupby(w["ticker"]).sum().reindex(t.index).fillna(0)
        pt = w[(w["pt_current"] > 0) & (w["pt_prior"] > 0)]
        t["pt_change_90d"] = (
            (pt["pt_current"] / pt["pt_prior"] - 1).groupby(pt["ticker"]).mean().reindex(t.index)
        )
    else:
        t["net_upgrades_90d"] = np.nan
        t["pt_change_90d"] = np.nan

    # ---- earnings: SUE at the last report, next report date
    sue = sue_table(src.earnings_dates, as_of)
    for c in ("sue", "last_report", "last_surprise_pct"):
        t[c] = sue[c].reindex(t.index) if c in sue else np.nan
    nxt = pd.Series(pd.NaT, index=t.index, dtype="datetime64[ns]")
    if not src.earnings_dates.empty:
        fut = (
            src.earnings_dates[src.earnings_dates["datetime"] > as_of]
            .sort_values("datetime")
            .drop_duplicates("ticker")
        )
        nxt = fut.set_index("ticker")["datetime"].reindex(t.index)
    if not src.calendar.empty:
        cal = (
            src.calendar[src.calendar["date"] >= as_of.normalize()]
            .sort_values("date")
            .drop_duplicates("ticker")
            .set_index("ticker")["date"]
        )
        nxt = nxt.where(nxt.notna(), cal.reindex(t.index))
    yn = ycol("next_earnings")
    nxt = nxt.where(nxt.notna(), yn.where(yn > as_of))
    t["next_earnings"] = pd.to_datetime(nxt)
    d0 = as_of.date()
    t["days_to_earnings"] = [
        trading_days_between(d0, x.date()) if pd.notna(x) else np.nan for x in t["next_earnings"]
    ]
    t["days_since_report"] = [
        trading_days_between(x.date(), d0) if pd.notna(x) else np.nan
        for x in pd.to_datetime(t["last_report"])
    ]

    # ---- insiders (F4 input) by issuer CIK
    if not src.trades.empty:
        f4 = I.f4_raw(src.trades, as_of)
        for c in ("insider_value", "insider_buy_usd", "insider_sell_usd", "insider_buyers"):
            t[c] = cik.map(f4[c]) if c in f4 else np.nan
        t[["insider_value", "insider_buy_usd", "insider_sell_usd", "insider_buyers"]] = t[
            ["insider_value", "insider_buy_usd", "insider_sell_usd", "insider_buyers"]
        ].fillna(0)
        t.loc[
            cik.isna(), ["insider_value", "insider_buy_usd", "insider_sell_usd", "insider_buyers"]
        ] = np.nan
    else:
        for c in ("insider_value", "insider_buy_usd", "insider_sell_usd", "insider_buyers"):
            t[c] = np.nan
    t["insider_net_90d"] = t["insider_buy_usd"]

    # ---- fundamentals (F6 inputs), point-in-time
    if not src.ttm.empty:
        mc_by_cik = pd.Series(t["market_cap"].to_numpy(), index=cik.to_numpy()).dropna()
        mc_by_cik = mc_by_cik[~mc_by_cik.index.duplicated()]
        f6 = F.f6_inputs(src.ttm, src.instants, as_of, mc_by_cik)
        for c in f6.columns:
            t[c] = cik.map(f6[c])
        known = F.known_dates(src.ttm, as_of)
        t["fundamentals_as_of"] = cik.map(known)
    # ---- short interest (FINRA; Yahoo as fallback)
    si = src.short
    if not si.empty:
        t["short_shares"] = si["short_shares"].reindex(t.index)
        t["days_to_cover"] = si["days_to_cover"].reindex(t.index)
        t["short_settlement"] = si["settlement"].reindex(t.index)
        base = t["float_shares"].where(t["float_shares"] > 0, t["shares_out"])
        t["short_pct_float"] = (t["short_shares"] / base).where(base > 0)
    else:
        t["short_pct_float"] = np.nan
        t["days_to_cover"] = np.nan
    t["short_pct_float"] = t["short_pct_float"].where(
        t["short_pct_float"].notna(), t["short_pct_float_y"]
    )

    # ---- options
    o = src.options
    for c in (
        "iv_1w",
        "iv_1m",
        "implied_move_1w",
        "implied_move_1m",
        "put_call_volume",
        "call_volume_oi",
    ):
        t[c] = o[c].reindex(t.index) if (not o.empty and c in o) else np.nan
    t["iv_30d"] = t["iv_1m"]

    # ---- news (10 days)
    if not src.news.empty:
        from convergealpha.features.news import per_ticker

        pn = per_ticker(src.news, as_of + pd.Timedelta(hours=23))
        for c in ("news_sentiment", "news_count", "news_negative_tags"):
            t[c] = pn[c].reindex(t.index) if c in pn else np.nan
    else:
        t["news_sentiment"] = np.nan
        t["news_count"] = np.nan
        t["news_negative_tags"] = None

    # ---- filings flags (SEC)
    fl = src.filings
    for c in ("offering_recent", "merger_pending", "auditor_change", "restatement", "late_filing"):
        t[c] = False
    if not fl.empty:
        fl = fl[fl["filing_date"] <= as_of]
        recent10 = fl[fl["filing_date"] > as_of - pd.Timedelta(days=14)]
        recent90 = fl[fl["filing_date"] > as_of - pd.Timedelta(days=90)]
        by = {
            "offering_recent": set(recent10.loc[recent10["form"].isin(OFFERING_FORMS), "cik"]),
            "merger_pending": set(recent90.loc[recent90["form"].isin(MERGER_FORMS), "cik"]),
            "auditor_change": set(
                recent90.loc[recent90["items"].fillna("").str.contains("4.01"), "cik"]
            ),
            "restatement": set(
                recent90.loc[recent90["items"].fillna("").str.contains("4.02"), "cik"]
            ),
            "late_filing": set(recent90.loc[recent90["form"].isin(LATE_FORMS), "cik"]),
        }
        for c, ciks in by.items():
            t[c] = cik.isin(ciks)
    # Lock-up: IPOs (first price within the last ~200 days) have a ~180-day lock-up.
    first = src.panel.close.apply(lambda s: s.first_valid_index())
    first_dates = first.reindex(t.index)
    t["listing_date"] = first_dates
    lock = pd.to_datetime(first_dates) + pd.Timedelta(days=180)
    days_to_lock = (lock - as_of).dt.days
    young = pd.to_datetime(first_dates) > pd.Timestamp("2010-02-01")
    t["lockup_soon"] = young & days_to_lock.between(-1, 14)
    return t


def evidence_freshness(t: pd.DataFrame, as_of: pd.Timestamp) -> pd.Series:
    """Days since the analyst snapshot was taken."""
    f = pd.to_datetime(t.get("analyst_fetched_at"))
    return (as_of - f).dt.days
