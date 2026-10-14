"""Decision rules (spec sections 5-7): blocking events, costs, fallback forecasts, labels
R1-R12 / C1-C7, tiers, WATCH, the risk label and the position plan inputs."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm as N

from convergealpha.config import HORIZON_NAMES, HORIZONS, MIN_ADV_DOLLARS, MIN_PRICE
from convergealpha.core import stats
from convergealpha.features.families import FAMILIES

DEFAULT_ORDER_USD = (
    10_000.0  # costs and R11 assume this order size; your own size is used in the browser
)
COMMISSION = 0.0002  # per side (conservative; many brokers charge 0)
EQUITY_PREMIUM = 0.05
MAX_ALPHA = 0.04  # fallback: a top composite score maps to at most +4%/year expected excess

LABEL_TOP = "STRONG BUY — TOP CONVICTION"
LABEL_BUY = "BUY"
LABEL_WATCH = "WATCH"
LABEL_RISK = "SELL / RISK WARNING"
LABEL_NONE = "NO TRADE"


# --------------------------------------------------------------------------- blocking events (F7)


def blocking_events(t: pd.DataFrame) -> pd.Series:
    """List of blocking reasons per stock (empty list = none)."""
    neg = t.get("news_negative_tags", pd.Series(None, index=t.index)).fillna("").astype(str)
    fda_tag = pd.Series(False, index=t.index)
    out: dict[str, list[str]] = {}
    for tk, r in t.iterrows():
        reasons = []
        dte = r.get("days_to_earnings")
        dsr = r.get("days_since_report")
        post_earnings_entry = pd.notna(dsr) and 1 <= dsr <= 10
        if pd.notna(dte) and 0 <= dte <= 5 and not post_earnings_entry:
            reasons.append(f"earnings in {int(dte)} trading day{'s' if dte != 1 else ''}")
        if pd.notna(dsr) and dsr == 0:
            reasons.append("earnings reported today")
        tags = set(neg[tk].split(",")) if neg[tk] else set()
        if bool(r.get("offering_recent")) or "offering" in tags:
            reasons.append("share offering announced")
        if bool(r.get("merger_pending")) or "merger_target" in tags:
            reasons.append("merger or takeover pending")
        if bool(r.get("lockup_soon")):
            reasons.append("IPO lock-up expiry within ~10 days")
        if "going_concern" in tags:
            reasons.append("going-concern warning in the news")
        if bool(r.get("auditor_change")) or "auditor" in tags:
            reasons.append("auditor change (8-K item 4.01)")
        if bool(r.get("restatement")) or "restatement" in tags:
            reasons.append("restatement / non-reliance (8-K item 4.02)")
        if "investigation" in tags:
            reasons.append("SEC/DOJ investigation in the news")
        if bool(r.get("late_filing")):
            reasons.append("late filing notice (NT 10-K/10-Q)")
        if bool(fda_tag.get(tk, False)):
            reasons.append("FDA decision pending")
        pc = r.get("price_check")
        if isinstance(pc, str) and pc:
            reasons.append(f"price data failed a check ({pc})")
        out[tk] = reasons
    return pd.Series(out)


HARD_RISKS = ("going-concern", "auditor", "restatement", "investigation", "late filing", "offering")


# --------------------------------------------------------------------------- costs and forecasts


def spread_estimate(adv_dollar: float) -> float:
    """Typical quoted spread as a fraction of price, from liquidity."""
    if not adv_dollar or math.isnan(adv_dollar):
        return 0.005
    if adv_dollar >= 200e6:
        return 0.0003
    if adv_dollar >= 50e6:
        return 0.0006
    if adv_dollar >= 10e6:
        return 0.0012
    return 0.003


def round_trip_cost(r: pd.Series, order_usd: float = DEFAULT_ORDER_USD) -> float:
    adv = float(r.get("adv_dollar") or 0)
    sigma_d = float(r.get("vol_63") or 0.3) / math.sqrt(252)
    return stats.trading_cost(
        spread_estimate(adv), COMMISSION, sigma_d, min(order_usd / adv, 1.0) if adv > 0 else 0.01
    )


@dataclass
class ForecastInputs:
    mu: float  # expected annual total return
    sigma: float  # annual volatility
    alpha: float  # expected annual excess return vs the S&P 500
    tracking: float  # annual tracking volatility vs the S&P 500
    method: str = "estimate — not calibrated"
    notes: list[str] = field(default_factory=list)


def fallback_inputs(r: pd.Series, rf: float, beta: float) -> ForecastInputs | None:
    """Transparent pre-model estimate: CAPM-style market return plus a small alpha from the
    composite evidence score; volatility blends realized and implied."""
    vol = r.get("vol_63")
    if vol is None or pd.isna(vol) or vol <= 0:
        return None
    realized = 0.5 * float(vol) + 0.5 * float(
        r.get("vol_252") if pd.notna(r.get("vol_252")) else vol
    )
    iv = r.get("iv_1m")
    sigma = (
        0.5 * realized + 0.5 * float(iv)
        if iv is not None and pd.notna(iv) and 0.05 < iv < 3
        else realized
    )
    comp = r.get("composite")
    alpha = (
        0.0
        if comp is None or pd.isna(comp)
        else float(np.clip((comp - 50.0) / 50.0, -1, 1)) * MAX_ALPHA
    )
    b = beta if math.isfinite(beta) else 1.0
    mu = rf + b * EQUITY_PREMIUM + alpha
    market_vol = 0.17
    tracking = math.sqrt(max(sigma**2 - (b * market_vol) ** 2, (0.35 * sigma) ** 2))
    return ForecastInputs(mu=mu, sigma=sigma, alpha=alpha, tracking=tracking)


def forecast(fi: ForecastInputs) -> dict[str, dict[str, float]]:
    """P(up), P(beat), median and 10th/90th percentile move at each horizon (lognormal)."""
    out = {}
    for h in HORIZONS:
        t = h / 252.0
        drift = (fi.mu - fi.sigma**2 / 2) * t
        sd = fi.sigma * math.sqrt(t)
        out[HORIZON_NAMES[h]] = {
            "days": h,
            "p_up": float(N.cdf(drift / sd)),
            "p_beat": float(N.cdf(fi.alpha * t / (fi.tracking * math.sqrt(t)))),
            "median": math.exp(drift) - 1,
            "p10": math.exp(drift - 1.2816 * sd) - 1,
            "p90": math.exp(drift + 1.2816 * sd) - 1,
            "p25": math.exp(drift - 0.6745 * sd) - 1,
        }
    return out


def conditional_win_loss(fi: ForecastInputs, days: int) -> tuple[float, float]:
    """E[excess | excess > 0] and E[-excess | excess < 0] for a normal excess return."""
    t = days / 252.0
    m = fi.alpha * t
    s = fi.tracking * math.sqrt(t)
    z = m / s
    p = float(N.cdf(z))
    phi = float(N.pdf(z))
    win = m + s * phi / p if p > 0 else 0.0
    loss = -(m - s * phi / (1 - p)) if p < 1 else 0.0
    return win, loss


# --------------------------------------------------------------------------- labels


@dataclass
class RuleResult:
    id: str
    text: str
    passed: bool | None  # None = cannot be evaluated yet
    value: str
    margin_ok: bool = False  # for WATCH: failed by a small margin


def evaluate(
    r: pd.Series, regime: str | None, blocks: list[str], pf: dict[str, Any]
) -> tuple[str, list[RuleResult], dict[str, Any]]:
    """Apply R1-R12 and C1-C7 to one stock. Returns (label, rule results, extra)."""
    fam = {f: r.get(f) for f in FAMILIES}
    vals = [v for v in fam.values() if v is not None and not pd.isna(v)]
    n_fresh = len(vals)
    p_hat = pf.get("p_hat")
    wilson_lb = pf.get("p_lower")
    meta = pf.get("meta")
    ev = pf.get("ev")
    caution = regime == "Caution"
    p_min = 0.55 + (0.03 if caution else 0.0)
    lb_min = 0.52 + (0.03 if caution else 0.0)
    rank_pct = r.get("l1_rank_pct")
    n_eff = r.get("n_eff") or 0.0
    d = r.get("disagreement")
    ge60 = sum(v >= 60 for v in vals)
    le25 = sum(v <= 25 for v in vals)

    rules = [
        RuleResult(
            "R1",
            "At least 5 of 6 evidence families have fresh data",
            n_fresh >= 5,
            f"{n_fresh} of 6",
        ),
        RuleResult(
            "R2",
            "Market regime is not Stress",
            regime != "Stress" if regime else None,
            regime or "unknown",
        ),
        RuleResult(
            "R3",
            "Overall rank in the top 2% of eligible stocks",
            (rank_pct is not None and not pd.isna(rank_pct) and rank_pct >= 0.98),
            f"top {100 * (1 - rank_pct):.1f}%"
            if rank_pct is not None and not pd.isna(rank_pct)
            else "—",
        ),
        RuleResult(
            "R4",
            "At least 4 of 6 families ≥ 60 and none ≤ 25",
            ge60 >= 4 and le25 == 0,
            f"{ge60} families ≥ 60, {le25} ≤ 25",
            margin_ok=(ge60 == 3 and le25 == 0) or (ge60 >= 4 and le25 == 1),
        ),
        RuleResult(
            "R5",
            "Independent evidence N_eff ≥ 2.5",
            n_eff >= 2.5,
            f"{n_eff:.2f}",
            margin_ok=n_eff >= 2.2,
        ),
        RuleResult(
            "R6",
            "Disagreement D ≤ 22",
            d is not None and not pd.isna(d) and d <= 22,
            "—" if d is None or pd.isna(d) else f"{d:.1f}",
            margin_ok=d is not None and not pd.isna(d) and d <= 25,
        ),
        RuleResult(
            "R7",
            f"Chance p̂ ≥ {p_min:.0%} and its Wilson lower bound ≥ {lb_min:.0%}",
            None
            if p_hat is None
            else (
                p_hat >= p_min and (wilson_lb is None or wilson_lb >= lb_min)
                if wilson_lb is not None
                else (p_hat >= p_min if pf.get("provisional") else None)
            ),
            "—"
            if p_hat is None
            else f"p̂ {p_hat:.1%}" + ("" if wilson_lb is None else f", lower bound {wilson_lb:.1%}"),
            margin_ok=p_hat is not None and p_hat >= p_min - 0.02,
        ),
        RuleResult(
            "R8",
            "Meta-model ≥ 55%",
            None if meta is None else meta >= 0.55,
            "not trained yet" if meta is None else f"{meta:.1%}",
            margin_ok=meta is not None and meta >= 0.53,
        ),
        RuleResult(
            "R9",
            "Expected value after costs ≥ +1.0%",
            None if ev is None else ev >= 0.01,
            "—" if ev is None else f"{ev:+.2%}",
            margin_ok=ev is not None and ev >= 0.005,
        ),
        RuleResult("R10", "No blocking event", not blocks, "; ".join(blocks) if blocks else "none"),
        RuleResult(
            "R11",
            "Price ≥ $5, average daily traded value ≥ $10M, order ≤ 1% of volume",
            bool(r.get("price", 0) >= MIN_PRICE and (r.get("adv_dollar") or 0) >= MIN_ADV_DOLLARS),
            f"${r.get('price', float('nan')):.2f}, ${(r.get('adv_dollar') or 0) / 1e6:.0f}M/day",
        ),
        RuleResult(
            "R12", "Portfolio limits pass", None, "checked against your portfolio in your browser"
        ),
    ]
    by = {x.id: x for x in rules}
    must = ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R9", "R10", "R11"]
    provisional = bool(pf.get("provisional"))
    # Before models exist R8 cannot be evaluated; provisional labels say so explicitly.
    if not provisional:
        must.append("R8")
    core_pass = all(by[k].passed is True for k in must)
    label = LABEL_NONE
    tier = None
    if core_pass:
        label = LABEL_BUY
        tier = 1 if (p_hat or 0) >= 0.60 and n_eff >= 3 else 2
    else:
        watch_set = ["R4", "R5", "R6", "R7", "R8", "R9"]
        failed = [
            k for k in watch_set if by[k].passed is not True and not (k == "R8" and provisional)
        ]
        others_ok = all(by[k].passed is True for k in ("R1", "R2", "R3", "R10", "R11"))
        if others_ok and len(failed) == 1 and by[failed[0]].margin_ok:
            label = LABEL_WATCH

    # Top Conviction C1-C7.
    conv = [
        RuleResult(
            "C1", "Tier 1 candidate", tier == 1, f"tier {tier}" if tier else "not a candidate"
        ),
        RuleResult(
            "C2",
            "All 6 families ≥ 60 and ≥ 5 of them ≥ 70",
            n_fresh == 6 and min(vals or [0]) >= 60 and sum(v >= 70 for v in vals) >= 5,
            f"min {min(vals) if vals else 0:.0f}, {sum(v >= 70 for v in vals)} ≥ 70",
        ),
        RuleResult(
            "C3",
            "N_eff ≥ 3 and D ≤ 15",
            n_eff >= 3 and d is not None and not pd.isna(d) and d <= 15,
            f"N_eff {n_eff:.2f}, D {d if d is not None and not pd.isna(d) else float('nan'):.1f}",
        ),
        RuleResult(
            "C4",
            "≥ 3 opinion sources at their top rating",
            int(r.get("top_rated_sources") or 0) >= 3,
            f"{int(r.get('top_rated_sources') or 0)} sources",
        ),
        RuleResult(
            "C5",
            "Opportunistic insider buying in 90 days or revisions in the top 10%",
            bool((r.get("insider_buy_usd") or 0) > 0 or (r.get("f2_pct") or 0) >= 0.90),
            f"insider buys ${(r.get('insider_buy_usd') or 0) / 1e3:.0f}K",
        ),
        RuleResult(
            "C6",
            "Regime Normal, volatility ≤ 30%/year, no blocking event",
            regime == "Normal" and (r.get("vol_63") or 1) <= 0.30 and not blocks,
            f"{regime}, vol {(r.get('vol_63') or float('nan')):.0%}",
        ),
        RuleResult(
            "C7",
            "≥ 100 similar past setups with a 6-month up rate whose Wilson lower bound ≥ 65%",
            pf.get("analog_pass"),
            pf.get("analog_text", "analog check not available yet"),
        ),
    ]
    if label == LABEL_BUY and all(c.passed is True for c in conv):
        label = LABEL_TOP

    # Risk label for stocks nobody should buy now (and that holders should review).
    hard = [b for b in blocks if any(h in b for h in HARD_RISKS)]
    decay = sum(v < 35 for v in vals) >= 4 and r.get("trend_up") is False
    if label in (LABEL_NONE, LABEL_WATCH) and (hard or decay):
        label = LABEL_RISK
    extra = {
        "tier": tier,
        "provisional": provisional,
        "risk_reasons": hard
        + (["evidence decay: 4 or more families below 35 and in a downtrend"] if decay else []),
    }
    return label, rules + conv, extra


def why(label: str, r: pd.Series, rules: list[RuleResult], extra: dict[str, Any]) -> str:
    """One plain sentence."""
    failed = [x for x in rules if x.id.startswith("R") and x.passed is False]
    if label == LABEL_TOP:
        return "Almost all independent evidence agrees and similar past setups usually rose over 6 months."
    if label == LABEL_BUY:
        top = sorted(((r.get(f) or 0, f) for f in FAMILIES), reverse=True)[:2]
        names = " and ".join(f.upper() for _, f in top)
        return (
            f"Passes every trade rule (tier {extra.get('tier')}); strongest evidence from {names}."
        )
    if label == LABEL_RISK:
        return (
            "Risk warning: "
            + "; ".join(extra.get("risk_reasons") or ["see the blocking events"])
            + "."
        )
    if label == LABEL_WATCH:
        miss = next(
            (
                x
                for x in rules
                if x.id in ("R4", "R5", "R6", "R7", "R8", "R9") and x.passed is not True
            ),
            None,
        )
        return (
            f"Close to a buy: misses only {miss.id} ({miss.text.lower()}: {miss.value})."
            if miss
            else "Close to a buy."
        )
    if failed:
        f = failed[0]
        return f"No trade: rule {f.id} not met — {f.text[0].lower()}{f.text[1:]} (now: {f.value})."
    return "No trade: the evidence is not strong enough."


def plan(
    r: pd.Series, p_lower: float | None, b: float | None, tier: int | None
) -> dict[str, Any] | None:
    """Position plan inputs (shares are computed in the browser from your own capital)."""
    e = r.get("price")
    atr = r.get("atr14")
    if e is None or pd.isna(e) or atr is None or pd.isna(atr) or e <= 0:
        return None
    x = stats.planned_exit(float(e), float(atr))
    g = float(e) * float(r.get("gap_stress_pct") or 0.0)
    return {
        "entry": float(e),
        "entry_limit": float(e) * 1.01,
        "skip_if_gap_above": 0.03,
        "planned_exit": x,
        "gap_stress": g,
        "risk_per_share": max(float(e) - x, g),
        "atr": float(atr),
        "breakeven_after": float(e) + 1.5 * float(atr),
        "sell_third_at": float(e) + 3 * float(atr),
        "trail_atr_multiple": 3,
        "time_stop_days": 60,
        "tier": tier,
        "tier_multiplier": 1.0 if tier == 1 else 0.5,
        "p_lower": p_lower,
        "payoff_b": b,
        "adv_shares": None if pd.isna(r.get("adv_shares")) else float(r.get("adv_shares")),
    }
