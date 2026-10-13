"""The five strategies' fixed rules (and the S&P 500 benchmark).

Every number here was fixed before the first decision (2026-10-13) and is never optimized on past
data; tests/test_paper.py pins them. Changing any rule means a NEW version (the `version` field):
it gets its own key, starts again from 200 EUR, and the old version's history stays untouched. The
engine refuses to trade a version whose rules differ from the ones recorded at its start.

All five use the app's daily numbers (Picks sub-scores, calibrated forecasts, the opportunity
badge) with a different mindset. Shared rules live in engine.py: decisions after the close,
fills at the next official open in euros with spread and fees, whole shares, finanzen.net zero
stocks only, minimum hold of 3 trading days unless a stop triggers, and the switch rule.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

START = date(2026, 10, 13)  # first decision at this close; first fills at the next open
CAPITAL = 200.0  # euros per strategy
MIN_HOLD = 3  # trading days, unless a stop triggers
REBUY_COOLDOWN = 5  # trading days before a strategy may buy a stock it just sold again
SELL_LABEL = "SELL / RISK WARNING"


@dataclass(frozen=True)
class Spec:
    id: str
    version: int
    name: str
    mindset: str
    max_positions: int
    stop: float | None  # sell if the price falls this much below the buy price
    take_profit: float | None
    trailing: float | None  # sell if the price falls this much below its highest close
    max_hold: int | None  # trading days
    switch_margin: float  # score points a candidate must be ahead by to replace a holding
    extra: dict[str, float] = field(default_factory=dict)
    rules: tuple[str, ...] = ()
    benchmark: bool = False

    @property
    def key(self) -> str:
        return f"{self.id}-v{self.version}"

    def params(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "max_positions": self.max_positions,
            "stop": self.stop,
            "take_profit": self.take_profit,
            "trailing": self.trailing,
            "max_hold": self.max_hold,
            "switch_margin": self.switch_margin,
            "min_hold": MIN_HOLD,
            "rebuy_cooldown": REBUY_COOLDOWN,
            "capital": CAPITAL,
            "start": START.isoformat(),
            "extra": dict(sorted(self.extra.items())),
            "benchmark": self.benchmark,
        }

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.params(), sort_keys=True).encode()).hexdigest()[:12]


SHARED_RULES = (
    "Decides after each US close with that day's data only; orders fill at the next trading day's official opening price.",
    "Euros: 1 € fee per buy and per sell, half the estimated spread each way, US prices converted with the EUR/USD rate (FRED).",
    "Whole shares only; money left over stays as cash.",
    "Only stocks buyable on finanzen.net zero (not “not sure”), eligible for signals, not blocked by an event, never SELL / RISK WARNING. A holding that turns SELL / RISK WARNING is sold like a stop.",
    "Keeps a stock at least 3 trading days unless a stop triggers, and does not buy back a stock it sold in the last 5 trading days.",
    "Switches only if the new stock's score is ahead by the strategy's margin AND its expected 1-month gain beats the holding's by more than the cost of switching (both fees and spreads).",
)

SPECS: tuple[Spec, ...] = (
    Spec(
        id="balanced",
        version=1,
        name="Best overall (Balanced)",
        mindset="Buys the best all-round stocks: safe enough, enough upside, and a validated chance of rising.",
        max_positions=2,
        stop=0.06,
        take_profit=0.08,
        trailing=None,
        max_hold=63,
        switch_margin=10.0,
        extra={"min_p_up_1m": 0.52, "min_balanced": 60.0},
        rules=(
            "Up to 2 stocks, ranked by the Picks Balanced score (only stocks that pass the Picks minimum of 40 on Safety, Upside and Confidence).",
            "Buys only with a validated chance up (1 month) of at least 52% and an expected 1-month gain larger than the round-trip cost.",
            "Sells at +8% (take-profit), −6% (stop), when the Balanced score falls below 60, when the label turns SELL, or after 63 trading days.",
        ),
    ),
    Spec(
        id="high_risk",
        version=1,
        name="High risk, high reward",
        mindset="Goes for the biggest possible 1-month jump and accepts big swings.",
        max_positions=1,
        stop=0.12,
        take_profit=0.20,
        trailing=0.10,
        max_hold=21,
        switch_margin=10.0,
        extra={"w_p90_1m": 0.6, "w_momentum": 0.4},
        rules=(
            "1 stock. Score = 60% rank of the good case (90th percentile 1-month forecast) + 40% rank of momentum (F5 trend family), among the stocks it may buy. Volatile stocks allowed.",
            "Sells at −12% (stop), 10% below its highest close since buying (trailing stop), +20% (take-profit), or after 21 trading days.",
        ),
    ),
    Spec(
        id="safe_upside",
        version=1,
        name="Safest with the most upside",
        mindset="Only calm, solid stocks; among them the one with the most upside. Takes small gains and moves on.",
        max_positions=2,
        stop=0.05,
        take_profit=0.06,
        trailing=None,
        max_hold=63,
        switch_margin=10.0,
        extra={"min_safety": 75.0},
        rules=(
            "Up to 2 stocks with a Picks Safety score of 75 or more, ranked by the Upside score.",
            "Sells at −5% (stop), at +6% (“it rose a lot, lock it in”) and rotates into the next safe stock, or after 63 trading days.",
        ),
    ),
    Spec(
        id="confidence",
        version=1,
        name="Most likely to rise (Confidence)",
        mindset="Buys the stocks the app is most sure will be higher in a month, counting how often it was right before.",
        max_positions=2,
        stop=0.07,
        take_profit=None,
        trailing=None,
        max_hold=21,
        switch_margin=2.0,
        extra={},
        rules=(
            "Up to 2 stocks, ranked by validated chance up (1 month) × the lower end of how often that chance was right before (score = 100 × both).",
            "Buys only if the chance up is at or above the usual 1-month rate.",
            "Sells at −7% (stop), when the chance up drops below the usual rate, or after 21 trading days.",
        ),
    ),
    Spec(
        id="opportunity",
        version=1,
        name="Opportunity hunter",
        mindset="Waits for a confirmed opportunity (green badge) and acts fast; happy to sit in cash.",
        max_positions=1,
        stop=0.08,
        take_profit=0.12,
        trailing=None,
        max_hold=15,
        switch_margin=10.0,
        extra={"freshness_step": 10.0},
        rules=(
            "1 stock, only with a GREEN opportunity badge; the freshest event first (score = 100 − 10 per trading day since the event).",
            "Sells at −8% (stop), +12% (take-profit), when the badge turns red, or after 15 trading days. Stays in cash when there is no green opportunity.",
        ),
    ),
)

BENCHMARK = Spec(
    id="sp500",
    version=1,
    name="S&P 500 (SPY), bought once",
    mindset="The yardstick: 200 € into the S&P 500 at the first open, one buy fee, then held.",
    max_positions=1,
    stop=None,
    take_profit=None,
    trailing=None,
    max_hold=None,
    switch_margin=0.0,
    extra={},
    rules=(
        "Buys SPY (an S&P 500 fund) with all 200 € at the first open (a fraction of a share: one share costs more than 200 €; SPY itself is not sold to EU investors, it is only the yardstick), then holds.",
    ),
    benchmark=True,
)

BY_KEY = {s.key: s for s in (*SPECS, BENCHMARK)}


# --------------------------------------------------------------------------- scores


def _n(row: pd.Series | None, k: str) -> float:
    if row is None:
        return math.nan
    try:
        return float(row.get(k))
    except (TypeError, ValueError):
        return math.nan


def _pct_rank(s: pd.Series) -> pd.Series:
    s = s.astype(float)
    ok = s.dropna()
    if ok.empty:
        return s
    if len(ok) == 1:
        return pd.Series(50.0, index=ok.index).reindex(s.index)
    return ((ok.rank(method="average") - 1) / (len(ok) - 1) * 100).reindex(s.index)


def universe(t: pd.DataFrame) -> pd.DataFrame:
    """Stocks any strategy may buy today: buyable on finanzen.net zero (true, not unknown),
    eligible, not blocked, not SELL / RISK WARNING, with a price and a 1-month forecast."""
    zero = t["zero"].map(lambda v: v is True or v is np.True_) if "zero" in t else pd.Series(False, index=t.index)  # fmt: skip
    ok = (
        zero.astype(bool)
        & t.get("eligible", pd.Series(False, index=t.index)).eq(True)
        & ~t.get("blocked", pd.Series(False, index=t.index)).eq(True)
        & t.get("label", pd.Series("", index=t.index)).astype(str).ne(SELL_LABEL)
        & pd.to_numeric(t.get("price"), errors="coerce").gt(0)
        & pd.to_numeric(t.get("p_up_1m"), errors="coerce").notna()
        & pd.to_numeric(t.get("med_1m"), errors="coerce").notna()
    )
    return t[ok]


def scores(spec: Spec, t: pd.DataFrame, validated: list[str], base_up_1m: float | None) -> pd.DataFrame:  # fmt: skip
    """Each candidate's score and whether it may be bought today (`ok`), with the reason when not.

    Scores are computed for the whole universe, so a holding that is still in it can be compared
    with candidates for the switch rule."""
    u = universe(t)
    out = pd.DataFrame(index=u.index)
    out["score"] = np.nan
    out["ok"] = False
    if u.empty:
        return out

    def num(k: str) -> pd.Series:
        if k not in u:
            return pd.Series(np.nan, index=u.index, dtype=float)
        return pd.to_numeric(u[k], errors="coerce").astype(float)

    val_1m = "P(up) 1m" in validated
    if spec.id == "balanced":
        out["score"] = num("pick_balanced")
        out["ok"] = (
            u.get("pick_passes", pd.Series(False, index=u.index)).eq(True)
            & (num("pick_balanced") >= spec.extra["min_balanced"])
            & (num("p_up_1m") >= spec.extra["min_p_up_1m"])
            & val_1m
        )
    elif spec.id == "high_risk":
        p90 = _pct_rank(num("p90_1m"))
        mom = _pct_rank(num("f5")).fillna(50.0)
        out["score"] = spec.extra["w_p90_1m"] * p90 + spec.extra["w_momentum"] * mom
        out["ok"] = num("p90_1m").notna()
    elif spec.id == "safe_upside":
        out["score"] = num("pick_upside")
        out["ok"] = (num("pick_safety") >= spec.extra["min_safety"]) & num("pick_upside").notna()
    elif spec.id == "confidence":
        out["score"] = 100 * num("p_up_1m") * num("hit_up_1m_lo")
        base = base_up_1m if base_up_1m is not None else math.inf
        out["ok"] = val_1m & num("hit_up_1m_lo").notna() & (num("p_up_1m") >= base)
    elif spec.id == "opportunity":
        days = num("opp_days")
        out["score"] = (100 - spec.extra["freshness_step"] * days).where(days.notna())
        out["ok"] = u.get("opp", pd.Series(None, index=u.index)).eq("green") & days.notna()
    out["ok"] = out["ok"].fillna(False).astype(bool) & out["score"].notna()
    return out


def ranked(spec: Spec, t: pd.DataFrame, validated: list[str], base_up_1m: float | None) -> pd.DataFrame:  # fmt: skip
    """Buyable candidates, best first (ties: Balanced score, then ticker)."""
    s = scores(spec, t, validated, base_up_1m)
    s = s[s["ok"]].copy().rename_axis(None)
    if s.empty:
        return s
    s["balanced"] = pd.to_numeric(t["pick_balanced"], errors="coerce").reindex(s.index).fillna(-1) if "pick_balanced" in t else -1.0  # fmt: skip
    s["ticker"] = s.index
    return s.sort_values(["score", "balanced", "ticker"], ascending=[False, False, True])


def why_no_candidates(spec: Spec, validated: list[str]) -> str:
    if spec.id in ("balanced", "confidence") and "P(up) 1m" not in validated:
        return "the 1-month chance up is not validated today, and this strategy needs it"
    if spec.id == "opportunity":
        return "no stock it may buy has a green opportunity badge today"
    return "no stock passes its buying rules today"


def score_text(spec: Spec, row: pd.Series | None, score: float) -> str:
    if not math.isfinite(score):
        return "no score today"
    if spec.id == "balanced":
        return f"Balanced score {score:.0f}"
    if spec.id == "high_risk":
        return f"upside score {score:.0f} (good case 1M {_n(row, 'p90_1m'):+.0%}, trend F5 {_n(row, 'f5'):.0f})"
    if spec.id == "safe_upside":
        return f"Upside score {score:.0f} with Safety {_n(row, 'pick_safety'):.0f}"
    if spec.id == "confidence":
        return f"chance up 1M {_n(row, 'p_up_1m'):.0%} × right before (low end) {_n(row, 'hit_up_1m_lo'):.0%} = {score:.1f}"
    if spec.id == "opportunity":
        return f"green opportunity, event {int(round((100 - score) / spec.extra['freshness_step']))} trading days ago"
    return f"score {score:.1f}"


def exit_check(
    spec: Spec,
    gain: float,
    close: float,
    peak: float,
    days_held: int,
    row: pd.Series | None,
    base_up_1m: float | None,
) -> tuple[str | None, bool, str | None]:
    """(reason to sell, is it a stop, reason it waits for the minimum hold).

    `row` is today's data for the stock (None on a prices-only day): score rules then wait."""

    def pct(x: float) -> str:
        return f"{abs(x) * 100:.0f}%"

    if spec.benchmark:
        return None, False, None
    if spec.stop is not None and gain <= -spec.stop:
        return f"fell {abs(gain):.1%} from the buy price (stop at −{pct(spec.stop)})", True, None
    if spec.trailing is not None and close <= peak * (1 - spec.trailing):
        drop = 1 - close / peak
        return (
            f"{drop:.1%} below its highest close since buying (${peak:,.2f}; trailing stop {pct(spec.trailing)})",
            True,
            None,
        )
    if row is not None and str(row.get("label")) == SELL_LABEL:
        return "the app's label turned SELL / RISK WARNING (treated as a stop)", True, None
    if spec.id == "opportunity" and row is not None and row.get("opp") == "red":
        return "its opportunity badge turned red (treated as a stop)", True, None
    soft: str | None = None
    if spec.take_profit is not None and gain >= spec.take_profit:
        soft = f"up {gain:.1%}, hit the +{pct(spec.take_profit)} take-profit" + (
            ": it rose a lot, lock it in and rotate into the next safe stock"
            if spec.id == "safe_upside"
            else ""
        )
    elif spec.max_hold is not None and days_held >= spec.max_hold:
        soft = f"held {days_held} trading days (maximum {spec.max_hold})"
    elif spec.id == "balanced" and row is not None:
        b = _n(row, "pick_balanced")
        if math.isfinite(b) and b < spec.extra["min_balanced"]:
            soft = (
                f"its Balanced score fell to {b:.0f} (sells below {spec.extra['min_balanced']:.0f})"
            )
    elif spec.id == "confidence" and row is not None and base_up_1m is not None:
        p = _n(row, "p_up_1m")
        if math.isfinite(p) and p < base_up_1m:
            soft = f"its chance up 1M fell to {p:.0%}, below the usual {base_up_1m:.0%}"
    if soft is None:
        return None, False, None
    if days_held < MIN_HOLD:
        return (
            None,
            False,
            f"would sell ({soft}) but keeps it for the minimum {MIN_HOLD} trading days",
        )
    return soft, False, None
