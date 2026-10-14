"""Plain answers for a stock page and your holdings: why did it move today, what is already in the
price, and how fragile the company looks. Display only: none of these feeds a label or a rule
until it passes a one-time test like every other signal.

- Why did it move: today's move split into the market (SPY), its sector beyond the market (the
  median move of the sector's eligible stocks minus SPY) and its own part (the rest), with the
  news headlines and SEC filings of that day. "No public reason found" when there is none in the
  sources the app reads.
- What is already in the price: free-cash-flow yield and earnings yield, each as a percentile
  within the sector (100 = the cheapest of its sector).
- Distress check (simple rules, not a probability): liabilities above 90% of assets or negative
  equity, cash for less than a year of cash burn, debt above 6x EBITDA (or debt with negative
  EBITDA), and filings or news of bankruptcy, a delisting notice, a going-concern doubt or a late
  report. 0 flags = low, 1-2 = elevated, 3+ or any bankruptcy / delisting / going concern = high.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from convergealpha.features.evidence import ITEM_8K

SPY = "SPY"
EXPLAIN_MOVE = 0.03  # moves of 3% or more get a short "why" in the screener and holdings


def _f(v: Any) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return math.nan
    return x


def _pct(x: float) -> str:
    """+1.2% / -0.4%, and never "-0.0%"."""
    return f"{0.0 if abs(x) < 0.0005 else x:+.1%}"


def _about(headline: str, ticker: str, name: Any) -> bool:
    """Finnhub attaches an article to every company it mentions: keep a headline only when the
    company is its subject (ticker or the first word of its name in the first six words)."""
    words = [w.strip(".,:;!?'\"()").lower() for w in str(headline).split()[:6]]
    first = (
        str(name).split()[0].strip(".,").lower() if isinstance(name, str) and name.strip() else None
    )
    return ticker.lower() in words or (first is not None and len(first) > 2 and first in words)


def why_move(t: pd.DataFrame, news: pd.DataFrame, filings: pd.DataFrame, as_of: pd.Timestamp, spy_move: float) -> dict[str, dict[str, Any]]:  # fmt: skip
    """Per ticker: the move split into market, sector and own part, and that day's news/filings."""
    move = pd.to_numeric(t.get("change_1d"), errors="coerce")
    elig = t["eligible"].astype(bool) if "eligible" in t else pd.Series(True, index=t.index)
    sector = t.get("sector", pd.Series(None, index=t.index))
    sec_med = move[elig].groupby(sector[elig]).median()
    day = as_of.normalize()
    news_today: dict[str, list[dict[str, Any]]] = {}
    if news is not None and not news.empty and "datetime" in news:
        n = news[pd.to_datetime(news["datetime"]).dt.normalize() == day]
        names = t["name"] if "name" in t else pd.Series(None, index=t.index, dtype=object)
        for r in n.sort_values("datetime", ascending=False).itertuples():
            if not _about(str(r.headline), str(r.ticker), names.get(str(r.ticker))):
                continue
            lst = news_today.setdefault(str(r.ticker), [])
            if len(lst) < 3:
                lst.append({"headline": r.headline, "source": getattr(r, "source", None), "url": getattr(r, "url", None)})  # fmt: skip
    filings_today: dict[int, list[dict[str, Any]]] = {}
    if filings is not None and not filings.empty:
        fl = filings[pd.to_datetime(filings["filing_date"]).dt.normalize() == day]
        for r in fl.itertuples():
            items = [x.strip() for x in str(r.items or "").split(",") if x.strip()]
            text = "; ".join(ITEM_8K.get(i, i) for i in items if i not in ("9.01",)) or str(r.form)
            filings_today.setdefault(int(r.cik), []).append({"form": str(r.form), "what": text})
    out: dict[str, dict[str, Any]] = {}
    cik = pd.to_numeric(t.get("cik"), errors="coerce") if "cik" in t else pd.Series(np.nan, index=t.index)  # fmt: skip
    for tk in t.index:
        r = _f(move.get(tk))
        if not math.isfinite(r):
            continue
        s = _f(sec_med.get(sector.get(tk))) if isinstance(sector.get(tk), str) else math.nan
        m = spy_move if math.isfinite(spy_move) else 0.0
        sec_part = (s - m) if math.isfinite(s) else 0.0
        own = r - m - sec_part
        c = cik.get(tk)
        fl = filings_today.get(int(c), []) if pd.notna(c) else []
        nw = news_today.get(str(tk), [])
        parts = f"market {_pct(m)}, sector {_pct(sec_part)}, its own part {_pct(own)}"
        if nw or fl:
            reason = "; ".join([*(f"filing: {f['what']}" for f in fl[:2]), *(f"news: {x['headline']}" for x in nw[:1])])  # fmt: skip
        else:
            reason = "no public reason found in the news and filings the app reads"
        out[str(tk)] = {
            "move": r, "market": m, "sector": sec_part, "own": own,
            "news": nw, "filings": fl,
            "text": f"{_pct(r)} today: {parts}. {reason[0].upper() + reason[1:]}.",
        }  # fmt: skip
    return out


def _sector_pct(x: pd.Series, sector: pd.Series, elig: pd.Series) -> pd.Series:
    """Percentile within the sector among eligible stocks with a value (higher x = higher pct)."""
    out = pd.Series(np.nan, index=x.index)
    ok = x.notna() & elig
    for _, idx in x[ok].groupby(sector[ok]).groups.items():
        g = x.loc[idx]
        if len(g) >= 5:
            out.loc[idx] = g.rank(pct=True) * 100
    return out


def valuation(t: pd.DataFrame) -> pd.DataFrame:
    """fcf_yield and earnings yield as sector percentiles (100 = cheapest) and a short verdict."""
    elig = t["eligible"].astype(bool) if "eligible" in t else pd.Series(True, index=t.index)
    sector = t.get("sector", pd.Series(None, index=t.index))
    mc = pd.to_numeric(t.get("market_cap"), errors="coerce")
    ey = pd.to_numeric(t.get("net_income_ttm"), errors="coerce") / mc.where(mc > 0)
    fy = pd.to_numeric(t.get("fcf_yield"), errors="coerce")
    out = pd.DataFrame(index=t.index)
    out["earnings_yield"] = ey
    out["value_fcf_pct"] = _sector_pct(fy, sector, elig)
    out["value_earn_pct"] = _sector_pct(ey, sector, elig)
    out["value_pct"] = out[["value_fcf_pct", "value_earn_pct"]].mean(axis=1, skipna=True)
    pct = out["value_pct"]
    view = pd.Series(None, index=t.index, dtype=object)
    view[pct.notna()] = "about average for its sector"
    view[pct >= 67] = "cheap for its sector"
    view[pct <= 33] = "expensive for its sector"
    out["value_view"] = view
    return out


def distress(t: pd.DataFrame, filings: pd.DataFrame | None = None, as_of: pd.Timestamp | None = None) -> pd.DataFrame:  # fmt: skip
    assets = pd.to_numeric(t.get("assets"), errors="coerce")
    liab = pd.to_numeric(t.get("liabilities"), errors="coerce")
    equity = pd.to_numeric(t.get("equity"), errors="coerce")
    cash = pd.to_numeric(t.get("cash"), errors="coerce")
    fcf = pd.to_numeric(t.get("fcf_ttm"), errors="coerce")
    lev = pd.to_numeric(t.get("debt_ebitda"), errors="coerce")
    neg = t.get("news_negative_tags", pd.Series(None, index=t.index)).fillna("").astype(str)
    sector = t.get("sector", pd.Series(None, index=t.index))
    serious: dict[str, set[int]] = {"1.03": set(), "3.01": set()}
    if filings is not None and not filings.empty and as_of is not None:
        recent = filings[(filings["filing_date"] <= as_of) & (filings["filing_date"] > as_of - pd.Timedelta(days=90))]  # fmt: skip
        for item in serious:
            serious[item] = set(recent.loc[recent["items"].fillna("").str.contains(item, regex=False), "cik"])  # fmt: skip
    cik = pd.to_numeric(t.get("cik"), errors="coerce") if "cik" in t else pd.Series(np.nan, index=t.index)  # fmt: skip
    levels: list[str | None] = []
    reasons: list[str | None] = []
    for tk in t.index:
        why: list[str] = []
        hard = False
        a, li, e = _f(assets.get(tk)), _f(liab.get(tk)), _f(equity.get(tk))
        # Banks and insurers fund themselves with deposits and policies: high liabilities are normal.
        financial = sector.get(tk) == "Financials"
        if math.isfinite(e) and e < 0 and not financial:
            why.append("negative equity (debts larger than assets)")
        elif not financial and math.isfinite(a) and a > 0 and math.isfinite(li) and li / a > 0.9:
            why.append(f"liabilities are {li / a:.0%} of assets")
        f, c = _f(fcf.get(tk)), _f(cash.get(tk))
        if math.isfinite(f) and f < 0 and math.isfinite(c) and c < -f:
            why.append("cash covers less than a year of cash burn")
        lv = _f(lev.get(tk))
        if math.isfinite(lv) and lv >= 6:
            why.append("debt above 6x EBITDA" if lv < 20 else "debt with negative EBITDA")
        tags = set(neg.get(tk, "").split(",")) if neg.get(tk) else set()
        if "going_concern" in tags:
            why.append("going-concern doubt in the news")
            hard = True
        if bool(t.at[tk, "late_filing"]) if "late_filing" in t else False:
            why.append("late annual or quarterly report")
        ck = cik.get(tk)
        if pd.notna(ck) and int(ck) in serious["1.03"]:
            why.append("bankruptcy or receivership filed (8-K 1.03)")
            hard = True
        if pd.notna(ck) and int(ck) in serious["3.01"]:
            why.append("delisting notice (8-K 3.01)")
            hard = True
        known = math.isfinite(a) or math.isfinite(e) or math.isfinite(f)
        if hard or len(why) >= 3:
            levels.append("high")
        elif why:
            levels.append("elevated")
        else:
            levels.append("low" if known else None)
        reasons.append("; ".join(why) if why else None)
    return pd.DataFrame({"distress": levels, "distress_why": reasons}, index=t.index)


__all__ = ["EXPLAIN_MOVE", "distress", "valuation", "why_move"]
