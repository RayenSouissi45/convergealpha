"""Live estimate of every paper strategy during US trading hours (paper money only).

The sealed trade ledger is written only after the close. During the day this estimates what each
strategy is worth right now, the same way the engine will value it tonight:

- orders waiting for today's open are filled at today's official opening price, sells first, then
  the buys share the cash equally, with half the spread and the fee (the engine's rules);
- every holding is marked at its latest price (Yahoo, about 15 minutes delayed), in euros at the
  same EUR/USD rate the last official update used.

Nothing here is recorded anywhere: strategies_live.json is replaced by the official numbers after
the close, and the page says it is an estimate.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from convergealpha.decide import costs as C
from convergealpha.util.calendar import is_trading_day
from convergealpha.util.io import write_json
from convergealpha.util.log import get

log = get(__name__)

NEW_YORK = ZoneInfo("America/New_York")
OPEN, CLOSE = time(9, 30), time(16, 0)
DEFAULT_SPREAD = 0.002  # when an order or holding carries no spread (files from before Oct 14)


@dataclass(frozen=True)
class Quote:
    open: float | None  # today's official opening price (None before the open)
    last: float  # latest price
    at: str  # when the latest price was taken, ISO time


def market_state(now: datetime) -> str:
    """pre-open | open | closed (after the close, a weekend or a holiday)."""
    ny = now.astimezone(NEW_YORK)
    if not is_trading_day(ny.date()):
        return "closed"
    if ny.time() < OPEN:
        return "pre-open"
    if ny.time() < CLOSE:
        return "open"
    return "closed"


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def _spread(item: Mapping[str, Any]) -> float:
    s = _f(item.get("spread"))
    return s if s is not None and s >= 0 else DEFAULT_SPREAD


def estimate(card: Mapping[str, Any], quotes: Mapping[str, Quote], fx: float, today: date, capital: float = 200.0) -> dict[str, Any]:  # fmt: skip
    """One strategy's value right now, from its last official card and today's prices."""
    fees = C.Fees(fractional=bool(card.get("benchmark")))
    cash = float(card.get("cash") or 0.0)
    held: dict[str, dict[str, Any]] = {
        h["ticker"]: {
            "ticker": h["ticker"],
            "shares": float(h["shares"]),
            "entry_usd": _f(h.get("entry_usd")),
            "prev_usd": _f(h.get("close_usd")),
            "cost_eur": _f(h.get("cost_eur")),
            "bought_today": False,
        }
        for h in card.get("holdings") or []
    }
    filled: list[dict[str, Any]] = []
    waiting: list[dict[str, Any]] = []
    due = [o for o in card.get("pending") or [] if str(o.get("fill_on", "")) <= today.isoformat()]
    later = [o for o in card.get("pending") or [] if o not in due]

    def opened(tk: str) -> float | None:
        q = quotes.get(tk)
        return q.open if q is not None and q.open is not None and q.open > 0 else None

    for o in [o for o in due if o["side"] == "sell"]:
        h = held.get(o["ticker"])
        op = opened(o["ticker"])
        if h is None or op is None:
            waiting.append(o)
            continue
        got = C.sell_value(h["shares"], op, fx, _spread(o), fees.sell)
        cash += got
        filled.append({"side": "sell", "ticker": o["ticker"], "shares": h["shares"], "open_usd": op, "amount_eur": got})  # fmt: skip
        del held[o["ticker"]]
    buys = [o for o in due if o["side"] == "buy"]
    for i, o in enumerate(buys):
        op = opened(o["ticker"])
        if op is None:
            waiting += buys[i:]
            break
        b = C.buy(cash / (len(buys) - i), op, fx, _spread(o), fees)
        if b.shares <= 0:
            filled.append({"side": "buy", "ticker": o["ticker"], "shares": 0.0, "open_usd": op, "amount_eur": 0.0, "note": "one share cost more than the money available"})  # fmt: skip
            continue
        cash -= b.spent
        held[o["ticker"]] = {"ticker": o["ticker"], "shares": b.shares, "entry_usd": op, "prev_usd": op, "cost_eur": b.spent, "bought_today": True}  # fmt: skip
        filled.append({"side": "buy", "ticker": o["ticker"], "shares": b.shares, "open_usd": op, "amount_eur": b.spent})  # fmt: skip

    value = cash
    holdings = []
    priced = True
    for h in held.values():
        q = quotes.get(h["ticker"])
        px = q.last if q is not None and q.last > 0 else h["prev_usd"]
        if q is None:
            priced = False
        if px is None:
            continue
        v = h["shares"] * px / fx
        value += v
        holdings.append({
            "ticker": h["ticker"], "shares": h["shares"], "price_usd": px, "value_eur": v,
            "entry_usd": h["entry_usd"], "cost_eur": h["cost_eur"],
            "move": px / h["entry_usd"] - 1 if h["entry_usd"] else None,
            "day_move": px / h["prev_usd"] - 1 if h["prev_usd"] else None,
            "gain_eur": v - h["cost_eur"] if h["cost_eur"] is not None else None,
            "bought_today": h["bought_today"], "live": q is not None,
        })  # fmt: skip
    official = _f(card.get("value"))
    return {
        "key": card["key"],
        "value": value,
        "pct": value / capital - 1,
        "day_change_eur": value - official if official is not None else None,
        "cash": cash,
        "holdings": holdings,
        "filled_today": filled,
        "waiting": [{"side": o["side"], "ticker": o["ticker"]} for o in [*waiting, *later]],
        "all_priced": priced,
    }


def yahoo_quotes(tickers: list[str], today: date) -> dict[str, Quote]:
    """Today's open and latest price from Yahoo's daily bar (about 15 minutes delayed)."""
    from datetime import timedelta

    from convergealpha.sources.prices import download

    out: dict[str, Quote] = {}
    if not tickers:
        return out
    bars = download(tickers, today - timedelta(days=5), batch_size=150, pause=0.5)
    if bars.empty:
        return out
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    for tk, g in bars.sort_values("date").groupby("ticker"):
        r = g.iloc[-1]
        if pd.Timestamp(r["date"]).date() != today:
            continue
        last = _f(r["close"])
        if last is None or last <= 0:
            continue
        out[str(tk)] = Quote(open=_f(r["open"]), last=last, at=stamp)
    return out


def finnhub_quotes(api_key: str) -> Callable[[list[str], date], dict[str, Quote]]:
    """Finnhub's free quote (real time for US stocks), polite to its 60 calls a minute."""

    def get(tickers: list[str], today: date) -> dict[str, Quote]:
        import time as _time

        from convergealpha.sources import finnhub as FH

        s = FH.session(api_key)
        out: dict[str, Quote] = {}
        for tk in tickers[:50]:
            q = FH.quote(s, tk)
            _time.sleep(1.1)
            if not q or not q.get("c"):
                continue
            t = q.get("t")
            when = datetime.fromtimestamp(t, UTC) if t else datetime.now(UTC)
            if when.astimezone(NEW_YORK).date() != today:
                continue
            out[tk] = Quote(
                open=q.get("o") or None, last=q["c"], at=when.isoformat(timespec="seconds")
            )
        return out

    return get


def run(
    site_dir: Path,
    now: datetime,
    quote_source: Callable[[list[str], date], dict[str, Quote]] = yahoo_quotes,
    fallback: Callable[[list[str], date], dict[str, Quote]] | None = None,
) -> dict[str, Any] | None:
    """Write strategies_live.json next to strategies.json. Returns what was written (None if the
    strategies are not live yet)."""
    path = site_dir / "strategies.json"
    if not path.is_file():
        return None
    f = json.loads(path.read_text(encoding="utf-8"))
    fx = _f((f.get("fx") or {}).get("rate"))
    if f.get("status") != "live" or not fx:
        return None
    cards = [*(f.get("strategies") or []), *(f.get("strategies_all") or [])]
    bench = f.get("benchmark")
    state = market_state(now)
    today = now.astimezone(NEW_YORK).date()
    out: dict[str, Any] = {
        "generated_at": now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "official_as_of": f.get("as_of"),
        "market": state,
        "fx": fx,
        "source": "Yahoo daily bar, about 15 minutes delayed",
        "strategies": {},
        "benchmark": None,
    }
    if (
        state == "pre-open"
        or not is_trading_day(today)
        or (f.get("as_of") or "") >= today.isoformat()
    ):
        # Nothing has traded since the official numbers: the page shows those.
        out["note"] = (
            "waiting for the open"
            if state == "pre-open"
            else "no trading since the official numbers"
        )
        write_json(out, site_dir / "strategies_live.json")
        return out
    tickers = sorted({
        t for c in [*cards, *([bench] if bench else [])]
        for t in [*(h["ticker"] for h in c.get("holdings") or []), *(o["ticker"] for o in c.get("pending") or [])]
    })  # fmt: skip
    quotes = quote_source(tickers, today)
    missing = [t for t in tickers if t not in quotes]
    if missing and fallback is not None:
        quotes = {**fallback(missing, today), **quotes}
        out["source"] += "; Finnhub for the rest"
    times = sorted(q.at for q in quotes.values())
    out["prices_at"] = times[-1] if times else None
    out["priced"] = f"{len(quotes)} of {len(tickers)} stocks"
    capital = _f(f.get("capital")) or 200.0
    bench_est = estimate(bench, quotes, fx, today, capital) if bench else None
    bench_pct = bench_est["pct"] if bench_est else None
    for c in cards:
        e = estimate(c, quotes, fx, today, capital)
        e["vs_benchmark"] = e["pct"] - bench_pct if bench_pct is not None else None
        out["strategies"][c["key"]] = e
    out["benchmark"] = bench_est
    write_json(out, site_dir / "strategies_live.json")
    log.info("live strategies: %s, %s priced", state, out["priced"])
    return out


__all__ = ["Quote", "estimate", "finnhub_quotes", "market_state", "run", "yahoo_quotes"]
