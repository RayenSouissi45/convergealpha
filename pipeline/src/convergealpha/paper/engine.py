"""Paper-trading engine: one append-only, hash-chained trade ledger (ledger/trades.jsonl in the
private data repo) and the daily step that extends it.

Each run replays the ledger into every strategy's book (cash, holdings, pending orders), then
processes each trading day after the last one recorded, in order:

1. corporate actions at that day's open (splits change the share count; dividends paid to cash
   after 15% US withholding tax),
2. fills of the previous decision's orders at that day's official open (sells first, then buys
   sharing the cash equally), in euros with half the spread and the fee,
3. marking every holding at that day's close,
4. decisions after the close: exits, switches, buys; each with a plain-English reason. Orders
   wait for the next trading day's open.

Only the day being decided uses that day's full data (scores, forecasts, badges). A day the daily
build missed is caught up from prices alone: fills, stops and limits, no new buys. A same-day
re-run finds the day already recorded and adds nothing. Past entries are never edited.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from convergealpha.decide import costs as C
from convergealpha.ledger import ledger as LG
from convergealpha.paper import strategies as S
from convergealpha.sources.prices import Panel
from convergealpha.util.calendar import trading_days_between
from convergealpha.util.log import get

log = get(__name__)

LEDGER = Path("ledger") / "trades.jsonl"
SPY = "SPY"


# --------------------------------------------------------------------------- state


@dataclass
class Position:
    ticker: str
    shares: float
    entry_usd: float  # the opening price paid (before the spread), in today's share units
    entry_date: str
    cost_eur: float  # everything paid: shares x price with spread + buy fee
    peak_usd: float
    days_held: int  # closes seen since the fill, the fill day included
    spread: float


@dataclass
class Pending:
    order_id: str
    side: str
    ticker: str
    date: str  # decision date; fills at the next trading day's open
    reason: str
    spread: float


@dataclass
class Book:
    spec: S.Spec
    started: bool = False
    digest: str | None = None
    cash: float = 0.0
    positions: dict[str, Position] = field(default_factory=dict)
    pending: list[Pending] = field(default_factory=list)
    last_day: str | None = None
    fees: float = 0.0
    fills: list[dict[str, Any]] = field(default_factory=list)
    values: list[tuple[str, float]] = field(default_factory=list)
    last_notes: list[str] = field(default_factory=list)
    reasons: dict[str, str] = field(default_factory=dict)  # order id -> reason
    dividends: float = 0.0
    locked: str | None = None
    bought_once: bool = False
    last_positions: list[dict[str, Any]] = field(default_factory=list)
    log: list[dict[str, Any]] = field(default_factory=list)  # fills, cancels, dividends, splits
    last_sold: dict[str, str] = field(default_factory=dict)  # ticker -> date of the last sale


def replay(entries: Iterable[dict[str, Any]], specs: Sequence[S.Spec]) -> dict[str, Book]:
    books = {s.key: Book(s) for s in specs}
    for e in entries:
        b = books.get(e.get("strategy", ""))
        if b is None:
            continue  # an older version or a strategy not run any more: history stays as it is
        k = e["kind"]
        if k == "start":
            b.started, b.digest, b.cash = True, e["params_digest"], float(e["capital"])
        elif k == "order":
            b.pending.append(Pending(e["order_id"], e["side"], e["ticker"], e["date"], e["reason"], float(e["spread"])))  # fmt: skip
            b.reasons[e["order_id"]] = e["reason"]
        elif k == "cancel":
            b.pending = [p for p in b.pending if p.order_id != e["order_id"]]
            b.log.append(e)
        elif k == "fill":
            b.pending = [p for p in b.pending if p.order_id != e["order_id"]]
            b.fees += float(e["fee"])
            b.fills.append(e)
            b.log.append(e)
            if e["side"] == "buy":
                b.cash -= float(e["amount_eur"])
                b.bought_once = True
                b.positions[e["ticker"]] = Position(
                    e["ticker"], float(e["shares"]), float(e["open_usd"]), e["date"],
                    float(e["amount_eur"]), float(e["open_usd"]), 0, float(e["spread"]),
                )  # fmt: skip
            else:
                b.cash += float(e["amount_eur"])
                b.positions.pop(e["ticker"], None)
                b.last_sold[e["ticker"]] = e["date"]
        elif k == "split":
            b.log.append(e)
            p = b.positions.get(e["ticker"])
            if p:
                r = float(e["ratio"])
                p.shares, p.entry_usd, p.peak_usd = p.shares * r, p.entry_usd / r, p.peak_usd / r
        elif k == "dividend":
            b.cash += float(e["net_eur"])
            b.dividends += float(e["net_eur"])
            b.log.append(e)
        elif k == "day":
            b.last_day = e["date"]
            b.values.append((e["date"], float(e["value_eur"])))
            b.last_notes = list(e.get("notes") or [])
            b.last_positions = list(e.get("positions") or [])
            for rec in e.get("positions") or []:
                p = b.positions.get(rec["ticker"])
                if p:
                    p.peak_usd, p.days_held = float(rec["peak_usd"]), int(rec["days_held"])
    return books


# --------------------------------------------------------------------------- prices


class Prices:
    """Real prices on a given day. The panel is split-adjusted to today; splits after `d` are
    undone so a past day's open or close is what a buyer really saw then."""

    def __init__(self, panel: Panel) -> None:
        self.p = panel
        self.splits: dict[str, list[tuple[pd.Timestamp, float]]] = {}
        ev = panel.split_events
        if ev is not None and not ev.empty:
            for r in ev.itertuples():
                self.splits.setdefault(str(r.ticker), []).append((pd.Timestamp(r.date), float(r.ratio)))  # fmt: skip

    def factor_after(self, tk: str, d: pd.Timestamp) -> float:
        return float(np.prod([r for sd, r in self.splits.get(tk, []) if sd > d] or [1.0]))

    def _at(self, frame: pd.DataFrame, tk: str, d: pd.Timestamp) -> float:
        if tk not in frame.columns or d not in frame.index:
            return math.nan
        v = frame.at[d, tk]
        return float(v) * self.factor_after(tk, d) if pd.notna(v) else math.nan

    def open(self, tk: str, d: pd.Timestamp) -> float:
        return self._at(self.p.open, tk, d)

    def close(self, tk: str, d: pd.Timestamp) -> float:
        return self._at(self.p.close, tk, d)

    def last_close(self, tk: str, d: pd.Timestamp) -> tuple[float, pd.Timestamp] | None:
        if tk not in self.p.close.columns:
            return None
        s = self.p.close[tk].loc[:d].dropna()
        if s.empty:
            return None
        when = s.index[-1]
        return float(s.iloc[-1]) * self.factor_after(tk, when), when

    def split_on(self, tk: str, d: pd.Timestamp) -> float | None:
        r = [x for sd, x in self.splits.get(tk, []) if sd == d]
        return r[0] if r else None

    def dividend_on(self, tk: str, d: pd.Timestamp) -> float:
        v = self._at(self.p.dividend, tk, d)
        return v if math.isfinite(v) and v > 0 else 0.0


# --------------------------------------------------------------------------- the day step


@dataclass
class Today:
    """Inputs for deciding at the close of `as_of` (the build's table)."""

    table: pd.DataFrame
    validated: list[str]
    base_up_1m: float | None
    can_buy: bool = True
    why_not: str | None = None
    inputs: dict[str, Any] = field(default_factory=dict)


def _money(v: float) -> str:
    return f"€{v:,.2f}"


def _row(t: pd.DataFrame | None, tk: str) -> pd.Series | None:
    return t.loc[tk] if t is not None and tk in t.index else None


def _num(row: pd.Series | None, k: str) -> float:
    if row is None:
        return math.nan
    try:
        return float(row.get(k))
    except (TypeError, ValueError):
        return math.nan


def _levels(spec: S.Spec, p: Position) -> dict[str, Any]:
    return {
        "stop_usd": None if spec.stop is None else p.entry_usd * (1 - spec.stop),
        "take_profit_usd": (
            None if spec.take_profit is None else p.entry_usd * (1 + spec.take_profit)
        ),
        "trailing_usd": None if spec.trailing is None else p.peak_usd * (1 - spec.trailing),
        "max_hold_days": spec.max_hold,
        "days_left": None if spec.max_hold is None else max(0, spec.max_hold - p.days_held),
    }


def _level_text(spec: S.Spec, p: Position) -> str:
    lv = _levels(spec, p)
    bits = []
    if lv["stop_usd"] is not None:
        bits.append(f"stop ${lv['stop_usd']:,.2f}")
    if lv["trailing_usd"] is not None:
        bits.append(f"trailing stop ${lv['trailing_usd']:,.2f}")
    if lv["take_profit_usd"] is not None:
        bits.append(f"take-profit ${lv['take_profit_usd']:,.2f}")
    if lv["days_left"] is not None:
        bits.append(f"{lv['days_left']} trading days left")
    return ", ".join(bits)


def process_day(
    book: Book,
    d: pd.Timestamp,
    px: Prices,
    fx: tuple[float, str],
    today: Today | None,
    recorded_at: str,
) -> list[dict[str, Any]]:
    """All ledger entries for one strategy and one trading day (fills, marks, decisions)."""
    spec = book.spec
    ds = d.strftime("%Y-%m-%d")
    rate, rate_date = fx
    base = {"strategy": spec.key, "date": ds, "recorded_at": recorded_at}
    out: list[dict[str, Any]] = []
    notes: list[str] = []
    fees = spec.fees()

    # 1. corporate actions (before the open)
    for tk, p in book.positions.items():
        r = px.split_on(tk, d)
        if r:
            before = p.shares
            p.shares, p.entry_usd, p.peak_usd = p.shares * r, p.entry_usd / r, p.peak_usd / r
            out.append({**base, "kind": "split", "ticker": tk, "ratio": r, "shares_before": before, "shares_after": p.shares})  # fmt: skip
            notes.append(f"{tk} split {r:g} for 1: {before:g} shares became {p.shares:g}.")
        div = px.dividend_on(tk, d)
        if div > 0:
            net = p.shares * div * (1 - C.DIVIDEND_WITHHOLDING) / rate
            book.cash += net
            book.dividends += net
            out.append({**base, "kind": "dividend", "ticker": tk, "per_share_usd": div, "shares": p.shares, "withholding": C.DIVIDEND_WITHHOLDING, "fx": rate, "fx_date": rate_date, "net_eur": net})  # fmt: skip
            notes.append(f"Dividend from {tk}: {_money(net)} after 15% US withholding tax.")

    # 2. fills at the open: sells first, then buys share the cash equally
    due = [o for o in book.pending if o.date < ds]
    for o in [o for o in due if o.side == "sell"]:
        held = book.positions.get(o.ticker)
        if held is None:
            book.pending.remove(o)
            out.append({**base, "kind": "cancel", "order_id": o.order_id, "ticker": o.ticker, "reason": "not held any more"})  # fmt: skip
            continue
        op = px.open(o.ticker, d)
        if not (math.isfinite(op) and op > 0):
            notes.append(
                f"No opening price for {o.ticker} today: it will be sold at the next open."
            )
            continue
        p = held
        proceeds = C.sell_value_fees(p.shares, op, rate, o.spread, fees)
        fee = C.fee_for(fees.sell, p.shares * op * (1 - o.spread / 2) / rate, fees)
        pnl = proceeds - p.cost_eur
        book.cash += proceeds
        book.pending.remove(o)
        del book.positions[o.ticker]
        book.last_sold[o.ticker] = ds
        out.append({
            **base, "kind": "fill", "order_id": o.order_id, "side": "sell", "ticker": o.ticker,
            "shares": p.shares, "open_usd": op, "spread": o.spread, "price_usd": op * (1 - o.spread / 2),
            "fx": rate, "fx_date": rate_date, "price_eur": op * (1 - o.spread / 2) / rate, "fee": fee,
            "amount_eur": proceeds, "pnl_eur": pnl, "pnl_pct": pnl / p.cost_eur if p.cost_eur else None,
            "stock_move": op / p.entry_usd - 1, "entry_date": p.entry_date, "days_held": p.days_held,
            "cash_after": book.cash,
        })  # fmt: skip
    buys = [o for o in due if o.side == "buy"]
    for i, o in enumerate(buys):
        op = px.open(o.ticker, d)
        book.pending.remove(o)
        if not (math.isfinite(op) and op > 0):
            out.append({**base, "kind": "cancel", "order_id": o.order_id, "ticker": o.ticker, "reason": "no opening price that day"})  # fmt: skip
            continue
        alloc = book.cash / (len(buys) - i)
        b = C.buy(alloc, op, rate, o.spread, fees)
        if b.shares <= 0:
            out.append({**base, "kind": "cancel", "order_id": o.order_id, "ticker": o.ticker,
                        "reason": f"at the open one share cost {_money(b.pay_eur + fees.buy)} with the fee, more than the {_money(alloc)} available"})  # fmt: skip
            notes.append(
                f"Did not buy {o.ticker}: too expensive at the open for the money available."
            )
            continue
        book.cash -= b.spent
        book.bought_once = True
        book.positions[o.ticker] = Position(o.ticker, b.shares, op, ds, b.spent, op, 0, o.spread)
        out.append({
            **base, "kind": "fill", "order_id": o.order_id, "side": "buy", "ticker": o.ticker,
            "shares": b.shares, "open_usd": op, "spread": o.spread, "price_usd": op * (1 + o.spread / 2),
            "fx": rate, "fx_date": rate_date, "price_eur": b.pay_eur, "fee": b.fee, "amount_eur": b.spent,
            "leftover_eur": b.leftover, "cash_after": book.cash,
        })  # fmt: skip

    # 3. mark at the close
    value = book.cash
    closes: dict[str, float] = {}
    for tk, p in book.positions.items():
        lc = px.last_close(tk, d)
        c = lc[0] if lc else p.entry_usd
        if lc and lc[1] < d:
            notes.append(
                f"No close for {tk} today: valued at its last close ({lc[1]:%b} {lc[1].day})."
            )
        closes[tk] = c
        p.days_held += 1
        p.peak_usd = max(p.peak_usd, c)
        value += p.shares * c / rate

    # 4. decisions after the close
    orders, dnotes = decide(book, d, closes, rate, today)
    out += [{**base, **o} for o in orders]
    notes += dnotes
    out.append({
        **base, "kind": "day", "value_eur": value, "cash_eur": book.cash, "fx": rate, "fx_date": rate_date,
        "data": "full" if today is not None else "prices only",
        "positions": [
            {"ticker": tk, "shares": p.shares, "entry_usd": p.entry_usd, "close_usd": closes[tk],
             "value_eur": p.shares * closes[tk] / rate, "stock_move": closes[tk] / p.entry_usd - 1,
             "peak_usd": p.peak_usd, "days_held": p.days_held, "cost_eur": p.cost_eur}
            for tk, p in book.positions.items()
        ],
        "notes": notes,
        **({"inputs": today.inputs} if today is not None and today.inputs else {}),
    })  # fmt: skip
    book.last_day = ds
    book.values.append((ds, value))
    book.last_notes = notes
    book.last_positions = out[-1]["positions"]
    book.log += [e for e in out if e["kind"] in ("fill", "cancel", "dividend", "split")]
    book.fills += [e for e in out if e["kind"] == "fill"]
    book.fees += sum(float(e["fee"]) for e in out if e["kind"] == "fill")
    return out


def decide(
    book: Book, d: pd.Timestamp, closes: dict[str, float], rate: float, today: Today | None
) -> tuple[list[dict[str, Any]], list[str]]:
    spec = book.spec
    ds = d.strftime("%Y-%m-%d")
    t = today.table if today is not None else None
    base_up = today.base_up_1m if today is not None else None
    orders: list[dict[str, Any]] = []
    notes: list[str] = []
    fees = spec.fees()

    def order(side: str, tk: str, reason: str, spread: float, **extra: Any) -> None:
        oid = f"{spec.key}:{ds}:{side}:{tk}"
        orders.append({"kind": "order", "order_id": oid, "side": side, "ticker": tk, "reason": reason, "spread": spread, **extra})  # fmt: skip
        book.pending.append(Pending(oid, side, tk, ds, reason, spread))
        book.reasons[oid] = reason

    # The benchmark buys once and holds.
    if spec.benchmark:
        if not book.bought_once and not book.pending:
            row = _row(t, SPY)
            s = C.spread(_num(row, "adv_dollar")) if row is not None else 0.0003
            fee_txt = (
                "one buy fee" if spec.fee_rule == "flat" else "no fee (orders from 500 € are free)"
            )
            order("buy", SPY, f"Bought the S&P 500 (SPY) once with all {spec.capital:,.0f} € as the yardstick; a fraction of a share, {fee_txt}, then held.", s)  # fmt: skip
        elif book.positions:
            notes.append("Held SPY (the S&P 500 yardstick never trades again).")
        return orders, notes

    sold: dict[str, float] = {}  # ticker -> estimated euros back
    kept: list[str] = []
    waiting = {o.ticker for o in book.pending if o.side == "sell"}
    for tk, p in book.positions.items():
        if tk in waiting:
            sold[tk] = C.sell_value_fees(p.shares, closes[tk], rate, p.spread, fees)
            notes.append(f"{tk}: the sell order is still waiting for an opening price.")
            continue
        row = _row(t, tk)
        c = closes[tk]
        gain = c / p.entry_usd - 1
        why, _stop, wait = S.exit_check(spec, gain, c, p.peak_usd, p.days_held, row, base_up)
        if why:
            order("sell", tk, f"Sold {tk}: {why}.", p.spread, close_usd=c, stock_move=gain)
            sold[tk] = C.sell_value_fees(p.shares, c, rate, p.spread, fees)
        else:
            kept.append(tk)
            if wait:
                notes.append(f"Kept {tk}: {wait}.")

    if t is None:
        for tk in kept:
            p = book.positions[tk]
            notes.append(f"Kept {tk}: {closes[tk] / p.entry_usd - 1:+.1%} since buying; {_level_text(spec, p)}.")  # fmt: skip
        notes.append("The daily build did not run for this day: only stops and limits were checked from prices; no new buys.")  # fmt: skip
        return orders, notes

    validated = today.validated if today is not None else []
    allsc = S.scores(spec, t, validated, base_up)
    cand = S.ranked(spec, t, validated, base_up)
    # Sold recently: not bought again for a while (no buying straight back what was just sold).
    cooling = {
        tk for tk, sd in book.last_sold.items()
        if trading_days_between(date.fromisoformat(sd), d.date()) < S.REBUY_COOLDOWN
    }  # fmt: skip
    taken = set(book.positions) | cooling
    est_cash = book.cash + sum(sold.values())
    switch_out: dict[str, str] = {}
    switch_in: list[tuple[str, str, float]] = []

    def affordable(tk: str, alloc: float) -> tuple[bool, float, str]:
        row = t.loc[tk]
        s = C.spread(_num(row, "adv_dollar"))
        b = C.buy(alloc, float(row["price"]), rate, s, fees)
        if b.shares <= 0:
            return False, s, f"one share costs about {_money(b.pay_eur + fees.buy)} with the fee, more than the {_money(alloc)} available"  # fmt: skip
        if spec.id == "balanced":
            rt = C.round_trip_cost(b.invested, s, fees)
            g = _num(row, "med_1m")
            if not (g > rt):
                return False, s, f"its expected 1-month gain {g:+.1%} does not cover the {rt:.1%} round-trip cost"  # fmt: skip
        return True, s, ""

    for tk in kept:
        p = book.positions[tk]
        row = _row(t, tk)
        cur = float(allsc["score"].get(tk, math.nan)) if tk in allsc.index else math.nan
        gain = closes[tk] / p.entry_usd - 1
        status = f"{gain:+.1%} since buying, {p.days_held} trading day{'s' if p.days_held != 1 else ''}; {S.score_text(spec, row, cur)}; {_level_text(spec, p)}"  # fmt: skip
        if p.days_held < S.MIN_HOLD:
            notes.append(f"Kept {tk}: {status}. (Minimum hold: {S.MIN_HOLD} trading days.)")
            continue
        if not math.isfinite(cur):
            notes.append(f"Kept {tk}: {status}. It has no score today, so no switch is compared.")
            continue
        value = p.shares * closes[tk] / rate
        done = False
        for c in cand.itertuples():
            if c.ticker in taken or c.ticker in {x for x, _, _ in switch_in}:
                continue
            if c.score < cur + spec.switch_margin:
                break
            # Buys at the next open share the cash: this one, earlier switches and empty slots.
            n_buys = 1 + len(switch_in) + max(0, spec.max_positions - len(kept))
            ok, s_new, _why = affordable(c.ticker, (est_cash + value) / n_buys)
            if not ok:
                continue
            g_new, g_cur = _num(t.loc[c.ticker], "med_1m"), _num(row, "med_1m")
            cost = C.switch_cost(value, p.spread, s_new, fees)
            if math.isfinite(g_new) and math.isfinite(g_cur) and g_new - g_cur > cost:
                why = (
                    f"{S.score_text(spec, t.loc[c.ticker], float(c.score))} vs {cur:.1f} (needs +{spec.switch_margin:g}), "
                    f"expected 1-month gain {g_new:+.1%} vs {g_cur:+.1%}: more than the {cost:.1%} cost of switching"
                )
                switch_out[tk] = c.ticker
                switch_in.append((c.ticker, why, s_new))
                order("sell", tk, f"Sold {tk} to switch into {c.ticker}: {why}.", p.spread, close_usd=closes[tk], stock_move=gain)  # fmt: skip
                est_cash += C.sell_value_fees(p.shares, closes[tk], rate, p.spread, fees)
                done = True
                break
        if not done:
            notes.append(
                f"Kept {tk}: {status}. No candidate is ahead by {spec.switch_margin:g} points with enough extra expected gain to pay for switching."
            )
    for tk_new, why, s_new in switch_in:
        order(
            "buy", tk_new, f"Bought {tk_new}: switched in; {why}.", s_new, **_inputs(t.loc[tk_new])
        )
        taken.add(tk_new)

    free = spec.max_positions - (len(kept) - len(switch_out)) - len(switch_in)
    if free <= 0:
        return orders, notes
    if today is not None and not today.can_buy:
        notes.append(f"No new buy today: {today.why_not}.")
        return orders, notes
    if cand.empty:
        notes.append(f"No buy: {S.why_no_candidates(spec, validated)}. The money stays in cash.")
        return orders, notes
    n_total = free + len(switch_in)
    alloc = est_cash / n_total if n_total else est_cash
    rank = 0
    skipped: list[str] = []
    n_skipped = 0
    bought = 0
    for c in cand.itertuples():
        rank += 1
        if c.ticker in taken or c.ticker in sold or c.ticker in switch_out:
            continue
        ok, s, why_not = affordable(c.ticker, alloc)
        if not ok:
            n_skipped += 1
            if len(skipped) < 2:
                skipped.append(f"{c.ticker} ({why_not})")
            continue
        row = t.loc[c.ticker]
        opp = row.get("opp")
        opp_txt = (
            f"; {opp} opportunity: {row.get('opp_event')}" if isinstance(opp, str) and opp else ""
        )
        why_rank = (
            f"; {n_skipped} higher-ranked stock{'s' if n_skipped > 1 else ''} did not fit about {_money(alloc)} (one share too expensive, or an expected gain below the costs)"
            if n_skipped
            else ""
        )
        reason = (
            f"Bought {c.ticker}: #{rank} for this strategy ({S.score_text(spec, row, float(c.score))}){why_rank}; "
            f"chance up 1M {_num(row, 'p_up_1m'):.0%}, expected 1-month change {_num(row, 'med_1m'):+.1%}{opp_txt}."
        )
        order("buy", c.ticker, reason, s, **_inputs(row))
        taken.add(c.ticker)
        bought += 1
        if bought >= free:
            break
    if skipped:
        notes.append("Skipped: " + "; ".join(skipped) + ".")
    if bought < free:
        notes.append(
            f"{'No buy' if bought == 0 else 'One slot stays empty'}: nothing else it may buy fits today. The money stays in cash."
        )
    return orders, notes


def _inputs(row: pd.Series) -> dict[str, Any]:
    """The numbers behind a buy, kept with the order for the record."""
    keys = ("price", "p_up_1m", "med_1m", "p10_1m", "p90_1m", "hit_up_1m_lo", "pick_balanced", "pick_safety", "pick_upside", "pick_confidence", "f5", "opp")  # fmt: skip
    out: dict[str, Any] = {}
    for k in keys:
        v = row.get(k)
        if isinstance(v, str):
            out[k] = v
        elif v is not None and pd.notna(v):
            out[k] = float(v)
    return {"inputs": out}


# --------------------------------------------------------------------------- run


def trading_days(panel: Panel, start: date, end: pd.Timestamp) -> list[pd.Timestamp]:
    idx = pd.DatetimeIndex(panel.close.index)
    return [pd.Timestamp(x) for x in idx[(idx >= pd.Timestamp(start)) & (idx <= end)]]


def fx_for(fx: pd.Series | Mapping[str, pd.Series], spec: S.Spec) -> pd.Series:
    """The EUR/USD series a strategy's rules name (FRED for version 1, the ECB for version 2)."""
    if isinstance(fx, pd.Series):
        return fx
    return fx.get(spec.fx_source, pd.Series(dtype=float))


def run(
    data_dir: Path,
    panel: Panel,
    fx: pd.Series | Mapping[str, pd.Series],
    as_of: pd.Timestamp,
    today: Today | None,
    recorded_at: str,
    specs: Sequence[S.Spec] = S.ALL_SPECS,
    start: date | None = None,
) -> tuple[dict[str, Book], list[dict[str, Any]]]:
    """Extend the trade ledger up to `as_of`. Returns the books and the entries written.
    Each strategy starts on its own start date (`start` overrides it, for tests); a strategy
    whose start date is after `as_of` is not started yet."""
    path = data_dir / LEDGER
    entries = LG.read(path)
    books = replay(entries, specs)
    px = Prices(panel)
    new: list[dict[str, Any]] = []
    for spec in specs:
        begin = start if start is not None else spec.start
        if as_of < pd.Timestamp(begin):
            continue
        days = trading_days(panel, begin, as_of)
        series = fx_for(fx, spec)
        b = books[spec.key]
        if not b.started:
            new.append({
                "kind": "start", "strategy": spec.key, "date": begin.isoformat(), "recorded_at": recorded_at,
                "name": spec.name, "params": spec.params(), "params_digest": spec.digest(), "capital": spec.capital,
                "currency": "EUR", "fee_buy": C.FEE_BUY_EUR, "fee_sell": C.FEE_SELL_EUR,
                **({"fee_free_from": C.ZERO_FEE_FREE_FROM} if spec.fee_rule == "zero" else {}),
                "paper_money_only": True,
            })  # fmt: skip
            b.started, b.digest, b.cash = True, spec.digest(), spec.capital
        elif b.digest != spec.digest():
            b.locked = (
                "The rules in the code differ from the rules recorded when this version started; "
                "a rule change must be a new version. Nothing was traded."
            )
            log.error("strategy %s: %s", spec.key, b.locked)
            continue
        for d in days:
            ds = d.strftime("%Y-%m-%d")
            if b.last_day is not None and ds <= b.last_day:
                continue
            rate = C.fx_on(series, d)
            if rate is None:
                log.warning("no EUR/USD rate (%s) on or before %s: %s waits", spec.fx_source, ds, spec.key)  # fmt: skip
                break
            new += process_day(b, d, px, rate, today if d == as_of else None, recorded_at)
    if new:
        LG.append(path, new)
    return books, new


def verify(data_dir: Path) -> tuple[bool, str]:
    return LG.verify(data_dir / LEDGER)


def max_drawdown(values: Sequence[float]) -> float:
    peak, worst = -math.inf, 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            worst = min(worst, v / peak - 1)
    return worst


__all__ = ["LEDGER", "Book", "Prices", "Today", "date", "fx_for", "max_drawdown", "process_day", "replay", "run", "verify"]  # fmt: skip
