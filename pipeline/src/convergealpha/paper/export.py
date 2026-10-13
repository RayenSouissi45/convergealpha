"""strategies.json: the Strategies page (leaderboard, chart, one card per strategy, and what each
strategy would buy today for your own amount)."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from convergealpha.decide import costs as C
from convergealpha.paper import engine as E
from convergealpha.paper import strategies as S
from convergealpha.util.calendar import next_trading_day

SUGGESTIONS = 40  # candidates per strategy for "Give me a strategy" (the page keeps those that fit your amount)
PROVEN_DAYS = (
    126  # trading days (6 months) a strategy must beat the S&P 500 live to drop RESEARCH MODE
)


def _f(v: Any, digits: int = 4) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else round(x, digits)


def _name(t: pd.DataFrame | None, tk: str) -> str | None:
    if t is None or tk not in t.index or "name" not in t:
        return None
    v = t.at[tk, "name"]
    return str(v) if isinstance(v, str) and v else None


def strategy_card(b: E.Book, t: pd.DataFrame | None, bench_pct: float | None) -> dict[str, Any]:
    spec = b.spec
    values = [v for _, v in b.values]
    value = values[-1] if values else S.CAPITAL
    pct = value / S.CAPITAL - 1
    sells = [f for f in b.fills if f["side"] == "sell"]
    wins = sum(1 for f in sells if float(f.get("pnl_eur") or 0) > 0)
    holdings = []
    for rec in b.last_positions:
        tk = rec["ticker"]
        p = b.positions.get(tk)
        if p is None:
            continue
        holdings.append(
            {
                "ticker": tk,
                "name": _name(t, tk),
                "shares": _f(p.shares, 6),
                "entry_date": p.entry_date,
                "entry_usd": _f(p.entry_usd, 4),
                "cost_eur": _f(p.cost_eur, 2),
                "close_usd": _f(rec.get("close_usd"), 4),
                "value_eur": _f(rec.get("value_eur"), 2),
                "stock_move": _f(rec.get("stock_move")),
                "gain_eur": _f(float(rec.get("value_eur") or 0) - p.cost_eur, 2),
                "days_held": p.days_held,
                "levels": {k: _f(v) for k, v in E._levels(spec, p).items()},
            }
        )
    pending = [
        {
            "side": o.side,
            "ticker": o.ticker,
            "name": _name(t, o.ticker),
            "reason": o.reason,
            "date": o.date,
            "fill_on": next_trading_day(date.fromisoformat(o.date)).isoformat(),
        }
        for o in b.pending
    ]
    history = []
    for e in reversed(b.log):
        k = e["kind"]
        h: dict[str, Any] = {"date": e["date"], "kind": k, "ticker": e.get("ticker")}
        if k == "fill":
            h |= {
                "side": e["side"],
                "shares": _f(e["shares"], 6),
                "open_usd": _f(e["open_usd"]),
                "price_usd": _f(e["price_usd"]),
                "price_eur": _f(e["price_eur"]),
                "fx": _f(e["fx"]),
                "fx_date": e.get("fx_date"),
                "fee": _f(e["fee"], 2),
                "amount_eur": _f(e["amount_eur"], 2),
                "pnl_eur": _f(e.get("pnl_eur"), 2),
                "pnl_pct": _f(e.get("pnl_pct")),
                "stock_move": _f(e.get("stock_move")),
                "reason": b.reasons.get(e["order_id"]),
            }
        elif k == "cancel":
            h |= {"reason": f"Order cancelled: {e['reason']}.", "order_reason": b.reasons.get(e["order_id"])}  # fmt: skip
        elif k == "dividend":
            h |= {"amount_eur": _f(e["net_eur"], 2), "reason": f"Dividend: ${float(e['per_share_usd']):.4f} a share, after 15% US withholding tax."}  # fmt: skip
        elif k == "split":
            h |= {"reason": f"Split {float(e['ratio']):g} for 1: {float(e['shares_before']):g} → {float(e['shares_after']):g} shares."}  # fmt: skip
        history.append(h)
    return {
        "key": spec.key,
        "id": spec.id,
        "version": spec.version,
        "name": spec.name,
        "mindset": spec.mindset,
        "rules": list(spec.rules),
        "max_positions": spec.max_positions,
        "params": spec.params(),
        "benchmark": spec.benchmark,
        "locked": b.locked,
        "last_day": b.last_day,
        "value": _f(value, 2),
        "pct": _f(pct),
        "vs_benchmark": None if bench_pct is None or spec.benchmark else _f(pct - bench_pct),
        "fees": _f(b.fees, 2),
        "dividends": _f(b.dividends, 2),
        "trades": len(b.fills),
        "closed": len(sells),
        "wins": wins,
        "win_rate": _f(wins / len(sells)) if sells else None,
        "max_drawdown": _f(E.max_drawdown([S.CAPITAL, *values])),
        "cash": _f(b.cash, 2),
        "holdings": holdings,
        "pending": pending,
        "history": history,
        "notes": b.last_notes,
        "series": [[d, _f(v, 2)] for d, v in b.values],
    }


def suggestions(
    t: pd.DataFrame, validated: list[str], base_up_1m: float | None
) -> dict[str, list[dict[str, Any]]]:
    """What each strategy would buy today, starting fresh (best first)."""
    out: dict[str, list[dict[str, Any]]] = {}
    for spec in S.SPECS:
        r = S.ranked(spec, t, validated, base_up_1m).head(SUGGESTIONS)
        rows = []
        for i, tk in enumerate(r.index, start=1):
            row = t.loc[tk]
            rows.append(
                {
                    "rank": i,
                    "ticker": str(tk),
                    "name": _name(t, str(tk)),
                    "sector": row.get("sector") if isinstance(row.get("sector"), str) else None,
                    "price": _f(row.get("price")),
                    "spread": _f(C.spread(_f(row.get("adv_dollar"))), 5),
                    "score": _f(r.at[tk, "score"], 2),
                    "score_text": S.score_text(spec, row, float(r.at[tk, "score"])),
                    "p_up_1m": _f(row.get("p_up_1m")),
                    "med_1m": _f(row.get("med_1m")),
                    "p10_1m": _f(row.get("p10_1m")),
                    "p90_1m": _f(row.get("p90_1m")),
                    "opp": row.get("opp") if isinstance(row.get("opp"), str) else None,
                    "opp_event": row.get("opp_event")
                    if isinstance(row.get("opp_event"), str)
                    else None,
                }
            )
        out[spec.id] = rows
    return out


def export(
    books: Mapping[str, E.Book],
    t: pd.DataFrame | None,
    as_of: str,
    now: datetime,
    fx: tuple[float, str] | None,
    ledger: tuple[bool, str, int],
    validated: Sequence[str],
    base_up_1m: float | None,
    status: str | None = None,
    reliability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bench = books.get(S.BENCHMARK.key)
    bench_pct = (bench.values[-1][1] / S.CAPITAL - 1) if bench and bench.values else None
    cards = [strategy_card(books[s.key], t, bench_pct) for s in S.SPECS if s.key in books]
    proven = [
        c["name"]
        for c in cards
        if len(c["series"]) >= PROVEN_DAYS and (c["vs_benchmark"] or 0) > 0 and not c["locked"]
    ]
    started = any(b.values for b in books.values())
    return {
        "schema_version": 1,
        "generated_at": now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "as_of": as_of,
        "start": S.START.isoformat(),
        "capital": S.CAPITAL,
        "currency": "EUR",
        "paper_money_only": True,
        "status": status or ("live" if started else "waiting"),
        "research_mode": not proven,
        "proven": proven,
        "proven_days": PROVEN_DAYS,
        "fx": {"rate": fx[0], "date": fx[1], "series": C.FX_SERIES, "source": "FRED"}
        if fx
        else None,
        "costs": {
            "fee_buy": C.FEE_BUY_EUR,
            "fee_sell": C.FEE_SELL_EUR,
            "dividend_withholding": C.DIVIDEND_WITHHOLDING,
            "min_hold": S.MIN_HOLD,
            "rebuy_cooldown": S.REBUY_COOLDOWN,
        },
        "shared_rules": list(S.SHARED_RULES),
        "ledger": {"verified": ledger[0], "detail": ledger[1], "entries": ledger[2]},
        "validated": list(validated),
        "base_up_1m": _f(base_up_1m),
        # "How often right" buckets for the 1-month chance up ("Give me a strategy").
        "reliability_1m": [
            {k: b[k] for k in ("lo", "hi", "n", "rate", "wilson_lo", "wilson_hi")}
            for b in (((reliability or {}).get("horizons") or {}).get("1m") or {}).get("up", [])
        ],
        "benchmark": strategy_card(bench, t, None) if bench else None,
        "strategies": cards,
        "suggestions": suggestions(t, list(validated), base_up_1m) if t is not None else {},
    }
