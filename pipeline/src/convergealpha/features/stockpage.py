"""Per-stock page sections (stocks/<TICKER>.json) built from the evidence row and raw events."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from convergealpha.features.evidence import ITEM_8K, Sources, rec_label, tradable_reaction
from convergealpha.sources import insiders as I


def _v(x: Any) -> Any:
    if x is None:
        return None
    if isinstance(x, (float, np.floating)):
        return None if not math.isfinite(float(x)) else float(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, pd.Timestamp):
        return None if pd.isna(x) else x.isoformat()
    if x is pd.NaT:
        return None
    try:
        if pd.isna(x):
            return None
    except (TypeError, ValueError):
        pass
    return x


def _date(x: Any) -> str | None:
    try:
        ts = pd.Timestamp(x)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(ts) else ts.strftime("%Y-%m-%d")


def analysts(row: pd.Series, src: Sources, ticker: str) -> dict[str, Any] | None:
    y = src.yahoo.loc[ticker] if ticker in src.yahoo.index else None
    if y is None:
        return None
    months = []
    for p, label in (
        ("0m", "This month"),
        ("m1m", "1 month ago"),
        ("m2m", "2 months ago"),
        ("m3m", "3 months ago"),
    ):
        counts = {
            k: _v(y.get(f"rt_{p}_{k}")) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")
        }
        if any(v is not None for v in counts.values()):
            months.append({"period": label, **counts})
    changes = []
    if not src.upgrades.empty:
        u = (
            src.upgrades[(src.upgrades["ticker"] == ticker) & (src.upgrades["date"] <= src.as_of)]
            .sort_values("date", ascending=False)
            .head(15)
        )
        for r in u.itertuples():
            changes.append(
                {
                    "date": _date(r.date),
                    "firm": r.firm,
                    "from": r.from_grade or None,
                    "to": r.to_grade or None,
                    "action": r.action,
                    "target": _v(r.pt_current) if (r.pt_current or 0) > 0 else None,
                    "prior_target": _v(r.pt_prior) if (r.pt_prior or 0) > 0 else None,
                }
            )
    return {
        "consensus": _v(row.get("consensus")),
        "consensus_label": rec_label(
            float(row.get("consensus") if row.get("consensus") is not None else float("nan"))
        ),
        "n_analysts": _v(row.get("n_analysts")),
        "target_mean": _v(y.get("target_mean")),
        "target_median": _v(y.get("target_median")),
        "target_high": _v(y.get("target_high")),
        "target_low": _v(y.get("target_low")),
        "target_upside": _v(row.get("target_upside")),
        "net_upgrades_90d": _v(row.get("net_upgrades_90d")),
        "finnhub_trend_score": _v(row.get("finnhub_trend_score")),
        "trend": months,
        "changes": changes,
        "as_of": _v(y.get("fetched_at")),
        "source": "Yahoo Finance (yfinance); Finnhub recommendation trends",
    }


def estimates(src: Sources, ticker: str) -> dict[str, Any] | None:
    if ticker not in src.yahoo.index:
        return None
    y = src.yahoo.loc[ticker]
    rows = []
    for p, label in (
        ("0q", "This quarter"),
        ("1q", "Next quarter"),
        ("0y", "This year"),
        ("1y", "Next year"),
    ):
        cur = y.get(f"eps_{p}_cur")
        if cur is None or (isinstance(cur, float) and math.isnan(cur)):
            continue
        rows.append(
            {
                "period": label,
                "end": y.get(f"eps_{p}_end"),
                "eps": {k: _v(y.get(f"eps_{p}_{k}")) for k in ("cur", "7d", "30d", "60d", "90d")},
                "revisions": {
                    k: _v(y.get(f"eps_{p}_{k}")) for k in ("up7", "up30", "down30", "down7")
                },
                "analysts": _v(y.get(f"eps_{p}_n")),
                "revenue": _v(y.get(f"rev_{p}_avg")),
            }
        )
    return (
        {
            "periods": rows,
            "as_of": _v(y.get("fetched_at")),
            "source": "Yahoo Finance (yfinance) estimate trends",
        }
        if rows
        else None
    )


def earnings(row: pd.Series, src: Sources, ticker: str) -> dict[str, Any] | None:
    e = src.earnings_dates
    if e.empty:
        return None
    g = e[e["ticker"] == ticker].sort_values("datetime", ascending=False)
    if g.empty:
        return None
    hist = []
    for r in g[g["datetime"] <= src.as_of].head(12).itertuples():
        r1, r5, first = tradable_reaction(
            src.panel, ticker, pd.Timestamp(r.datetime), bool(r.after_close)
        )
        hist.append(
            {
                "date": _date(r.datetime),
                "timing": "after close"
                if r.after_close
                else ("before open" if r.before_open else "during session"),
                "eps_estimate": _v(r.eps_estimate),
                "eps_actual": _v(r.eps_actual),
                "surprise_pct": _v(r.surprise_pct),
                "reaction_1d": _v(r1),
                "reaction_5d": _v(r5),
                "first_tradable": _date(first) if first is not None else None,
            }
        )
    nxt = row.get("next_earnings")
    return {
        "next": _date(nxt),
        "days_to_next": _v(row.get("days_to_earnings")),
        "sue": _v(row.get("sue")),
        "history": hist,
        "note": "Reactions are measured from the first tradable price after the report (the next open), never from before it.",
        "source": "Yahoo Finance earnings calendar; Finnhub earnings calendar",
    }


def insiders(row: pd.Series, src: Sources, ticker: str) -> dict[str, Any] | None:
    cik = row.get("cik")
    if cik is None or pd.isna(cik) or src.trades.empty:
        return None
    trades = I.recent_trades(src.trades, int(cik), src.as_of)
    return {
        "buy_usd_90d": _v(row.get("insider_buy_usd")),
        "sell_usd_90d": _v(row.get("insider_sell_usd")),
        "buyers_30d": _v(row.get("insider_buyers")),
        "trades": trades,
        "note": "Only open-market trades. Routine traders (same month in each of the 3 prior years) and 10b5-1 plan trades are not opportunistic and do not count as signals.",
        "source": "SEC EDGAR Form 4 (data sets + daily filings)",
    }


def ownership(row: pd.Series) -> dict[str, Any]:
    return {
        "inst_pct": _v(row.get("inst_pct")),
        "insider_pct": _v(row.get("insider_pct")),
        "inst_top_change": _v(row.get("inst_top_change")),
        "inst_net_buying_pct": _v(row.get("inst_net_buying_pct")),
        "short_shares": _v(row.get("short_shares")),
        "short_pct_float": _v(row.get("short_pct_float")),
        "days_to_cover": _v(row.get("days_to_cover")),
        "short_settlement": _date(row.get("short_settlement")),
        "source": "FINRA short interest (twice monthly); Yahoo Finance holders",
    }


def options(row: pd.Series) -> dict[str, Any] | None:
    if row.get("iv_1m") is None or pd.isna(row.get("iv_1m")):
        return None
    px = row.get("price")
    out: dict[str, Any] = {
        "source": "Yahoo Finance option chains (at-the-money implied volatility)"
    }
    for k in ("1w", "1m"):
        move = row.get(f"implied_move_{k}")
        out[f"iv_{k}"] = _v(row.get(f"iv_{k}"))
        out[f"move_{k}"] = _v(move)
        if move is not None and pd.notna(move) and px:
            out[f"range_{k}"] = [_v(px * (1 - move)), _v(px * (1 + move))]
    out["put_call_volume"] = _v(row.get("put_call_volume"))
    out["call_volume_oi"] = _v(row.get("call_volume_oi"))
    return out


def fundamentals(row: pd.Series) -> dict[str, Any] | None:
    keys = (
        "revenue_ttm",
        "net_income_ttm",
        "fcf_ttm",
        "roic",
        "gp_assets",
        "accruals",
        "fcf_yield",
        "debt_ebitda",
        "assets",
        "equity",
        "debt",
    )
    vals = {k: _v(row.get(k)) for k in keys}
    if all(v is None for v in vals.values()):
        return None
    vals["as_of"] = _date(row.get("fundamentals_as_of"))
    vals["source"] = "SEC XBRL company facts, as first reported (no restated values)"
    return vals


def news(src: Sources, ticker: str, limit: int = 12) -> dict[str, Any] | None:
    n = src.news
    if n.empty:
        return None
    g = n[n["ticker"] == ticker].sort_values("datetime", ascending=False).head(limit)
    if g.empty:
        return None
    return {
        "items": [
            {
                "datetime": r.datetime.isoformat(),
                "headline": r.headline,
                "source": r.source,
                "url": r.url,
                "sentiment": _v(r.sentiment),
                "tags": [x for x in str(r.tags or "").split(",") if x],
            }
            for r in g.itertuples()
        ],
        "method": src.extras.get("lexicon", "Loughran-McDonald"),
        "ai": "not connected (needs ANTHROPIC_API_KEY)",
        "source": "Finnhub company news",
    }


def filings(src: Sources, cik: Any, limit: int = 12) -> list[dict[str, Any]]:
    if src.filings.empty or cik is None or pd.isna(cik):
        return []
    f = src.filings[(src.filings["cik"] == int(cik)) & (src.filings["filing_date"] <= src.as_of)]
    f = f[
        f["form"].isin(
            [
                "8-K",
                "8-K/A",
                "10-K",
                "10-Q",
                "20-F",
                "6-K",
                "424B4",
                "424B5",
                "S-1",
                "S-3",
                "SC TO-T",
                "SC 14D9",
                "DEFM14A",
                "PREM14A",
                "NT 10-K",
                "NT 10-Q",
                "425",
            ]
        )
    ]
    out = []
    for r in f.sort_values("filing_date", ascending=False).head(limit).itertuples():
        items = [x.strip() for x in str(r.items or "").split(",") if x.strip()]
        out.append(
            {
                "date": _date(r.filing_date),
                "form": r.form,
                "items": [f"{i} {ITEM_8K.get(i, '')}".strip() for i in items],
                "accession": r.accession,
            }
        )
    return out


def blocking_inputs(row: pd.Series) -> dict[str, Any]:
    return {
        "days_to_earnings": _v(row.get("days_to_earnings")),
        "days_since_report": _v(row.get("days_since_report")),
        "offering_recent": bool(row.get("offering_recent", False)),
        "merger_pending": bool(row.get("merger_pending", False)),
        "auditor_change": bool(row.get("auditor_change", False)),
        "restatement": bool(row.get("restatement", False)),
        "late_filing": bool(row.get("late_filing", False)),
        "lockup_soon": bool(row.get("lockup_soon", False)),
        "news_negative_tags": row.get("news_negative_tags")
        if isinstance(row.get("news_negative_tags"), str)
        else None,
    }
