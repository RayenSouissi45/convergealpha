"""Sell rules and entry timing, tested once on 2016-2023 with a protocol fixed before the run.

Question: which exit rule and which entry method give the best defensible trade-off between
losses, missed recoveries and costs, for the stocks the app would have bought?

Data: the walk-forward out-of-sample predictions of 2016-2023 (oos_devval.parquet from the weekly
model job; the 2024-2026 holdout is never touched) and the daily price panel. Each month-end
signal enters at the next session's open; a rule decides after each close and its sell fills at
the next open (so overnight gaps count, as in the app). Costs: half the estimated spread each way
plus 0.2% round trip, the dataset's cost.

PROTOCOL (fixed before the first run; any change = a new protocol id):
- Entry sets: "model" = the top 2% of each month by the model's ranking (L1, the BUY signal's
  core), and "control" = 30 random eligible stocks a month (seed 7): an exit rule must not depend
  on entry skill.
- Window: 63 trading days from the entry; money left after an exit earns nothing. A signal is
  used only if its window and the 21 days after it end by 31 Dec 2023, so no 2024 price (the
  holdout years) is ever read.
- Exit score = mean net return - 0.5 x |average of the worst 5% of returns|; computed on the model
  set. The winner must also be in the top 3 of each half (2016-2019 and 2020-2023); otherwise
  the simplest rule ("hold_63") is kept.
- Entry methods are compared on the model set by mean net 63-day result per signal (a missed
  fill counts as 0). An alternative replaces "next open" only if it beats it by 0.2 points or more
  in both halves.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from convergealpha.decide.rules import spread_estimate

PROTOCOL_ID = "rules-2016-2023-v1"
WINDOW = 63
ATR_DAYS = 14
TOP_FRACTION = 0.02
CONTROL_PER_MONTH = 30
SEED = 7
COST = 0.002
TAIL = 0.05
TAIL_WEIGHT = 0.5
ENTRY_MARGIN = 0.002
FIRST_YEAR, LAST_YEAR = 2016, 2023
LAST_PRICE_DAY = pd.Timestamp("2023-12-31")
HALVES = ((2016, 2019), (2020, 2023))


def protocol_digest() -> str:
    spec = {
        "id": PROTOCOL_ID,
        "window": WINDOW,
        "atr_days": ATR_DAYS,
        "top": TOP_FRACTION,
        "control": CONTROL_PER_MONTH,
        "seed": SEED,
        "cost": COST,
        "tail": TAIL,
        "tail_weight": TAIL_WEIGHT,
        "entry_margin": ENTRY_MARGIN,
        "years": [FIRST_YEAR, LAST_YEAR],
        "last_price_day": LAST_PRICE_DAY.strftime("%Y-%m-%d"),
        "exits": list(EXITS),
        "entries": list(ENTRIES),
    }
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- one trade path


@dataclass(frozen=True)
class PricePath:
    """Daily prices from the entry day (index 0 = the entry session) for up to WINDOW + 1 days."""

    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    atr: float  # ATR(14) at the signal, in dollars
    signal_close: float


@dataclass(frozen=True)
class Exit:
    ret: float  # gross return of the whole position, from the entry open (cash after the exit)
    days: int  # trading days held
    stopped: bool  # left because of a loss rule
    recovered: bool  # stopped, and the close 21 days later was back above the entry


def _hold(p: PricePath, decide: Callable[[int, float, float], tuple[str, float] | None]) -> Exit:
    """Walk the path: `decide(k, close, peak)` after each close returns ("all"|"third", fraction)
    or None. Sells fill at the next open. Returns the position's result."""
    e = p.open[0]
    left = 1.0
    proceeds = 0.0
    peak = p.close[0]
    stopped = False
    last = min(WINDOW, len(p.close) - 1)
    third_done = False
    for k in range(last):
        c = p.close[k]
        peak = max(peak, c)
        d = decide(k, c, peak)
        if d is None:
            continue
        kind, frac = d
        if kind == "third" and third_done:
            continue
        sell = left if kind == "all" else left * frac
        proceeds += sell * p.open[k + 1] / e
        left -= sell
        if kind == "third":
            third_done = True
        if kind == "all":
            stopped = d[1] < 0  # negative fraction marks a loss rule
            later = min(k + 1 + 21, len(p.close) - 1)
            return Exit(proceeds - 1.0, k + 1, stopped, stopped and p.close[later] > e)
    proceeds += left * p.open[min(last + 1, len(p.open) - 1)] / e if left > 0 else 0.0
    return Exit(proceeds - 1.0, last + 1, False, False)


def _stop_tp(stop: float | None, tp: float | None) -> Callable[[PricePath], Exit]:
    def run(p: PricePath) -> Exit:
        e = p.open[0]

        def decide(k: int, c: float, peak: float) -> tuple[str, float] | None:
            if stop is not None and c <= e * (1 - stop):
                return ("all", -1.0)
            if tp is not None and c >= e * (1 + tp):
                return ("all", 1.0)
            return None

        return _hold(p, decide)

    return run


def _time(days: int) -> Callable[[PricePath], Exit]:
    def run(p: PricePath) -> Exit:
        return _hold(p, lambda k, c, peak: ("all", 1.0) if k + 1 >= days else None)

    return run


def _trailing(pct: float) -> Callable[[PricePath], Exit]:
    def run(p: PricePath) -> Exit:
        return _hold(p, lambda k, c, peak: ("all", -1.0) if c <= peak * (1 - pct) else None)

    return run


def _atr_stop(p: PricePath) -> Exit:
    e = p.open[0]
    stop = max(e - 2 * p.atr, 0.92 * e)
    return _hold(p, lambda k, c, peak: ("all", -1.0) if c <= stop else None)


def _atr_plan(p: PricePath) -> Exit:
    """The app's position plan: exit 2 ATR below (at most 8%), break-even after +1.5 ATR, sell a
    third at +3 ATR and trail the rest 3 ATR below the highest close, 60 trading days."""
    e = p.open[0]
    a = p.atr
    state = {"stop": max(e - 2 * a, 0.92 * e), "trail": False}

    def decide(k: int, c: float, peak: float) -> tuple[str, float] | None:
        if c >= e + 1.5 * a:
            state["stop"] = max(state["stop"], e)
        if state["trail"]:
            state["stop"] = max(state["stop"], peak - 3 * a)
        if c <= state["stop"]:
            return ("all", -1.0 if c < e else 1.0)
        if c >= e + 3 * a and not state["trail"]:
            state["trail"] = True
            return ("third", 1 / 3)
        if k + 1 >= 60:
            return ("all", 1.0)
        return None

    return _hold(p, decide)


EXITS: dict[str, Callable[[PricePath], Exit]] = {
    "hold_63": _time(WINDOW),
    "time_21": _time(21),
    "fixed_6_tp_8": _stop_tp(0.06, 0.08),
    "fixed_5_tp_6": _stop_tp(0.05, 0.06),
    "fixed_8": _stop_tp(0.08, None),
    "atr_2": _atr_stop,
    "atr_plan": _atr_plan,
    "trail_10": _trailing(0.10),
}
EXIT_TEXT = {
    "hold_63": "No stop: sell after 63 trading days",
    "time_21": "Sell after 21 trading days",
    "fixed_6_tp_8": "Fixed stop −6%, take profit +8% (first Balanced strategy)",
    "fixed_5_tp_6": "Fixed stop −5%, take profit +6% (first Safest strategy)",
    "fixed_8": "Fixed stop −8%",
    "atr_2": "Stop 2 × the stock's normal daily swing below (at most −8%)",
    "atr_plan": "The app's position plan (swing-based stop, break-even, sell a third, trail)",
    "trail_10": "Trailing stop 10% below the highest close",
}


# --------------------------------------------------------------------------- entry methods


@dataclass(frozen=True)
class Fill:
    filled: float  # share of the money invested (0..1)
    ret63: float  # result of the money over 63 trading days from the signal (missed money = 0)


def _value_at(p: PricePath, start: int, price: float, end: int) -> float:
    return float(p.close[min(end, len(p.close) - 1)] / price - 1)


def entry_open(p: PricePath) -> Fill:
    return Fill(1.0, _value_at(p, 0, p.open[0], WINDOW - 1))


def entry_limit(p: PricePath) -> Fill:
    """Limit at most 1% above the signal close; skip if the open is 3%+ higher."""
    if p.open[0] > p.signal_close * 1.03:
        return Fill(0.0, 0.0)
    lim = p.signal_close * 1.01
    if p.low[0] > lim:
        return Fill(0.0, 0.0)
    px = min(p.open[0], lim)
    return Fill(1.0, _value_at(p, 0, px, WINDOW - 1))


def entry_staged(p: PricePath) -> Fill:
    """Half at the next open, half five sessions later (two orders: the cost counts twice)."""
    a = _value_at(p, 0, p.open[0], WINDOW - 1)
    k = min(5, len(p.open) - 1)
    b = _value_at(p, k, p.open[k], WINDOW - 1)
    return Fill(1.0, (a + b) / 2 - COST / 2)


def entry_pullback(p: PricePath) -> Fill:
    """Buy only if it dips 3% below the signal close within 10 sessions, else stay out."""
    lim = p.signal_close * 0.97
    for k in range(min(10, len(p.low))):
        if p.low[k] <= lim:
            return Fill(1.0, _value_at(p, k, min(p.open[k], lim), WINDOW - 1))
    return Fill(0.0, 0.0)


def entry_wait_1d(p: PricePath) -> Fill:
    k = min(1, len(p.open) - 1)
    return Fill(1.0, _value_at(p, k, p.open[k], WINDOW - 1))


ENTRIES: dict[str, Callable[[PricePath], Fill]] = {
    "next_open": entry_open,
    "limit_1pct_skip_gap_3pct": entry_limit,
    "two_parts_5_days": entry_staged,
    "wait_for_3pct_dip": entry_pullback,
    "wait_one_day": entry_wait_1d,
}
ENTRY_TEXT = {
    "next_open": "Buy at the next opening price",
    "limit_1pct_skip_gap_3pct": "Limit at most 1% above the signal; skip a 3%+ jump at the open",
    "two_parts_5_days": "Half at the next open, half 5 trading days later",
    "wait_for_3pct_dip": "Wait up to 10 days for a 3% dip, else stay out",
    "wait_one_day": "Wait one day, buy at the following open",
}


# --------------------------------------------------------------------------- signals and paths


def atr(
    panel_high: pd.DataFrame,
    panel_low: pd.DataFrame,
    panel_close: pd.DataFrame,
    days: int = ATR_DAYS,
) -> pd.DataFrame:
    prev = panel_close.shift(1)
    tr = np.maximum(
        panel_high - panel_low, np.maximum((panel_high - prev).abs(), (panel_low - prev).abs())
    )
    return tr.rolling(days, min_periods=days).mean()


def signals(oos: pd.DataFrame) -> pd.DataFrame:
    """Model set (top 2% by L1 each month) and control set (random), 2016-2023 only."""
    d = oos[(oos["date"].dt.year >= FIRST_YEAR) & (oos["date"].dt.year <= LAST_YEAR)].copy()
    r = d.groupby("date")["l1_ridge"].rank(pct=True)
    g = d.groupby("date")["l1_lgbm"].rank(pct=True)
    d["l1"] = (r + g) / 2
    d["l1_pct"] = d.groupby("date")["l1"].rank(pct=True)
    model = d[d["l1_pct"] > 1 - TOP_FRACTION].assign(set="model")  # exactly the top 2%
    rng = np.random.default_rng(SEED)
    picks = []
    for _, grp in d.groupby("date"):
        n = min(CONTROL_PER_MONTH, len(grp))
        picks.append(grp.iloc[rng.choice(len(grp), size=n, replace=False)])
    control = pd.concat(picks).assign(set="control")
    keep = ["date", "ticker", "regime", "log_adv", "set"]
    return pd.concat([model[keep], control[keep]], ignore_index=True)


def paths(
    sig: pd.DataFrame,
    open_: pd.DataFrame,
    high: pd.DataFrame,
    low: pd.DataFrame,
    close: pd.DataFrame,
) -> list[tuple[dict[str, Any], PricePath]]:
    a = atr(high, low, close)
    idx = close.index
    out = []
    for s in sig.itertuples(index=False):
        t = s.ticker
        if t not in close.columns:
            continue
        pos = idx.searchsorted(pd.Timestamp(s.date), side="right")  # the next session
        if pos >= len(idx) or pos == 0:
            continue
        end = pos + WINDOW + 21
        if end >= len(idx) or idx[end] > LAST_PRICE_DAY:
            continue  # its outcome would need prices from the holdout years
        sl = slice(pos, pos + WINDOW + 1 + 21)
        o, h, lo, c = (m[t].to_numpy()[sl] for m in (open_, high, low, close))
        if len(c) < WINDOW + 1 or np.isnan(o[0]) or np.isnan(c[: WINDOW + 1]).any():
            continue
        atr_s = float(a[t].iloc[pos - 1]) if not math.isnan(a[t].iloc[pos - 1]) else float("nan")
        sc = float(close[t].iloc[pos - 1])
        if not (o[0] > 0 and sc > 0) or math.isnan(atr_s):
            continue
        # Fill gaps in the later days so a missing day does not end the path.
        c = pd.Series(c).ffill().to_numpy()
        o = pd.Series(o).fillna(pd.Series(c).shift(1)).ffill().to_numpy()
        h = pd.Series(h).fillna(pd.Series(c)).to_numpy()
        lo = pd.Series(lo).fillna(pd.Series(c)).to_numpy()
        meta = {
            "date": pd.Timestamp(s.date),
            "ticker": t,
            "regime": s.regime,
            "set": s.set,
            "cost": COST
            + spread_estimate(float(np.exp(s.log_adv)) if s.log_adv == s.log_adv else float("nan")),
        }
        out.append((meta, PricePath(o, h, lo, c, atr_s, sc)))
    return out


# --------------------------------------------------------------------------- statistics


def _stats(
    rets: np.ndarray,
    days: np.ndarray | None = None,
    stopped: np.ndarray | None = None,
    recovered: np.ndarray | None = None,
) -> dict[str, float | int | None]:
    if len(rets) == 0:
        return {"n": 0}
    tail = np.sort(rets)[: max(1, int(len(rets) * TAIL))]
    out: dict[str, float | int | None] = {
        "n": int(len(rets)),
        "mean": float(rets.mean()),
        "median": float(np.median(rets)),
        "hit_rate": float((rets > 0).mean()),
        "worst5": float(tail.mean()),
        "score": float(rets.mean() - TAIL_WEIGHT * abs(tail.mean())),
    }
    if days is not None:
        out["avg_days"] = float(days.mean())
    if stopped is not None and recovered is not None:
        s = int(stopped.sum())
        out["stopped_share"] = float(stopped.mean())
        out["recovered_after_stop"] = float(recovered.sum() / s) if s else None
    return out


def evaluate(ps: list[tuple[dict[str, Any], PricePath]]) -> dict[str, Any]:
    rows = []
    for meta, p in ps:
        for name, rule in EXITS.items():
            x = rule(p)
            rows.append(
                {
                    **meta,
                    "rule": name,
                    "ret": x.ret - meta["cost"],
                    "days": x.days,
                    "stopped": x.stopped,
                    "recovered": x.recovered,
                }
            )
    ex = pd.DataFrame(rows)
    ent_rows = []
    for meta, p in ps:
        if meta["set"] != "model":
            continue
        for name, method in ENTRIES.items():
            f = method(p)
            ent_rows.append(
                {
                    **meta,
                    "method": name,
                    "ret": f.ret63 - (meta["cost"] if f.filled else 0.0),
                    "filled": f.filled,
                }
            )
    en = pd.DataFrame(ent_rows)

    def exit_table(df: pd.DataFrame) -> dict[str, Any]:
        return {
            r: _stats(
                g["ret"].to_numpy(),
                g["days"].to_numpy(),
                g["stopped"].to_numpy(),
                g["recovered"].to_numpy(),
            )
            for r, g in df.groupby("rule")
        }

    def in_half(df: pd.DataFrame, h: tuple[int, int]) -> pd.DataFrame:
        y = df["date"].dt.year
        return df[(y >= h[0]) & (y <= h[1])]

    model = ex[ex["set"] == "model"]
    result: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "protocol_digest": protocol_digest(),
        "period": f"{FIRST_YEAR}-{LAST_YEAR}",
        "signals": {
            "model": int((ex["set"] == "model").sum() // len(EXITS)),
            "control": int((ex["set"] == "control").sum() // len(EXITS)),
        },
        "exits": {
            "model": exit_table(model),
            "control": exit_table(ex[ex["set"] == "control"]),
            "halves": {f"{h[0]}-{h[1]}": exit_table(in_half(model, h)) for h in HALVES},
            "regimes": {str(k): exit_table(g) for k, g in model.groupby("regime")},
        },
        "entries": {
            "model": {
                m: {**_stats(g["ret"].to_numpy()), "filled": float(g["filled"].mean())}
                for m, g in en.groupby("method")
            },
            "halves": {
                f"{h[0]}-{h[1]}": {
                    m: {**_stats(g["ret"].to_numpy()), "filled": float(g["filled"].mean())}
                    for m, g in in_half(en, h).groupby("method")
                }
                for h in HALVES
            },
        },
        "text": {"exits": EXIT_TEXT, "entries": ENTRY_TEXT},
    }
    result["decision"] = decide(result)
    return result


def decide(r: dict[str, Any]) -> dict[str, Any]:
    """Apply the fixed protocol to the results."""
    scores = {k: v["score"] for k, v in r["exits"]["model"].items() if v.get("n")}
    best = max(scores, key=lambda k: scores[k])
    in_top3 = []
    for h in r["exits"]["halves"].values():
        hs = sorted(((v["score"], k) for k, v in h.items() if v.get("n")), reverse=True)
        in_top3.append(best in [k for _, k in hs[:3]])
    exit_rule = best if all(in_top3) else "hold_63"
    base = r["entries"]["halves"]
    better = [
        m
        for m in ENTRIES
        if m != "next_open"
        and all(
            (h.get(m, {}).get("mean", -math.inf) - h["next_open"]["mean"]) >= ENTRY_MARGIN
            for h in base.values()
        )
    ]
    entry = max(better, key=lambda m: r["entries"]["model"][m]["mean"]) if better else "next_open"
    return {
        "exit": exit_rule,
        "exit_best_overall": best,
        "exit_robust": all(in_top3),
        "entry": entry,
        "entry_better_in_both_halves": better,
    }
