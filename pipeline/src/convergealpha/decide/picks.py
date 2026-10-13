"""Picks: the app's best-balanced suggestions, mixing safety, upside and confidence.

Every weight below was fixed before any result was looked at and is never fitted to past data
(docs/METHODOLOGY.md, "Picks"). The page stays in RESEARCH MODE until this strategy proves itself
in the live baseline race ("Picks - Balanced top 25"), which starts on the first day it ran.

1. Universe: eligible stocks without a SELL / RISK WARNING label, without a blocking event and
   with a complete 6-month forecast.
2. Each component is a sector-neutral percentile rank (0-100) among those candidates: 0 = worst
   in its sector, 100 = best. Sectors with fewer than MIN_SECTOR candidates are ranked against
   all candidates instead (a rank among 3 stocks says little).
3. A sub-score is the weighted average of its components, ranked again the same way, so each
   sub-score is itself a percentile: Confidence, Upside, Safety.
4. Balanced = the average of the three. A pick needs at least FLOOR on every sub-score.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from convergealpha.config import HORIZON_NAMES
from convergealpha.features.families import FAMILY_NAMES

WEIGHTS: dict[str, dict[str, float]] = {
    # The chance of rising (validated P(up) 6m, else validated P(up) 1m, else p̂) and how often
    # the app was right for that probability bucket (lower end of the 95% Wilson range).
    "confidence": {"probability": 0.7, "reliability": 0.3},
    # Median expected 6-month return, and a smaller weight on the optimistic (90th pct) case.
    "upside": {"median_6m": 0.75, "p90_6m": 0.25},
    # Low volatility, a smaller pessimistic (10th pct) 6-month outcome, quality family F6, and
    # no earnings report in the next 5 trading days (known date = 100, unknown date = 50).
    "safety": {"low_volatility": 0.35, "small_downside": 0.35, "quality_f6": 0.20, "no_earnings_5d": 0.10},
}  # fmt: skip
FLOOR = 40.0
TOP = 25
MIN_SECTOR = 10
SELL = "SELL / RISK WARNING"
TABS: dict[str, str] = {
    "balanced": "balanced",
    "safest": "safety",
    "upside": "upside",
    "likely": "confidence",
}

REASON_TEXT = {
    "f1": "Analysts are positive",
    "f2": "Earnings estimates are being raised",
    "f3": "Recent earnings beat expectations",
    "f4": "Insiders have been buying",
    "f5": "Strong price trend for its sector",
    "f6": "Solid business: profits, cash flow and debt",
}


def _num(t: pd.DataFrame, col: str) -> pd.Series:
    return (
        pd.to_numeric(t[col], errors="coerce")
        if col in t
        else pd.Series(np.nan, index=t.index, dtype=float)
    )


def sector_rank(values: pd.Series, sector: pd.Series, min_sector: int = MIN_SECTOR) -> pd.Series:
    """0-100 percentile rank within the sector (higher value = higher rank); NaN stays NaN.

    (rank - 1) / (n - 1): the lowest gets 0, the highest 100; a group of one gets 50.
    """

    def pct(s: pd.Series) -> pd.Series:
        s = s.dropna()
        if s.empty:
            return s
        if len(s) == 1:
            return pd.Series(50.0, index=s.index)
        return (s.rank(method="average") - 1) / (len(s) - 1) * 100

    v = values.astype(float)
    sec = sector.fillna("Unknown").astype(str)
    counts = v.notna().groupby(sec).transform("sum")
    small = counts < min_sector
    out = pd.Series(np.nan, index=v.index, dtype=float)
    for _, idx in v[~small].groupby(sec[~small]).groups.items():
        out.loc[idx] = pct(v.loc[idx])
    if small.any():
        # Small sectors: rank against every candidate, then keep their rows.
        allr = pct(v)
        out.loc[small[small].index] = allr.reindex(small[small].index)
    return out


def _weighted(parts: Mapping[str, pd.Series], weights: Mapping[str, float]) -> pd.Series:
    """Weighted mean of the available components (weights of missing ones are spread out)."""
    num = None
    den = None
    for k, w in weights.items():
        s = parts[k]
        ok = s.notna().astype(float)
        num = s.fillna(0) * w if num is None else num + s.fillna(0) * w
        den = ok * w if den is None else den + ok * w
    assert num is not None and den is not None
    return (num / den.replace(0, np.nan)).astype(float)


def probability_source(validated: Sequence[str]) -> tuple[str, str, str | None]:
    """(label, probability column, reliability-low column) for the Confidence score."""
    if "P(up) 6m" in validated:
        return "P(up) 6m", "p_up_6m", "hit_up_6m_lo"
    if "P(up) 1m" in validated:
        return "P(up) 1m", "p_up_1m", "hit_up_1m_lo"
    return "p̂ (60-day trade)", "p_hat", "p_lower"


def candidates(t: pd.DataFrame) -> tuple[pd.Series, dict[str, int]]:
    elig = t["eligible"].eq(True) if "eligible" in t else pd.Series(False, index=t.index)
    sell = t["label"].astype(str).eq(SELL) if "label" in t else pd.Series(False, index=t.index)
    blocked = t["blocked"].eq(True) if "blocked" in t else pd.Series(False, index=t.index)
    fc = pd.concat([_num(t, c) for c in ("p_up_6m", "med_6m", "p90_6m", "p10_6m")], axis=1)
    no_fc = fc.isna().any(axis=1)
    keep = elig & ~sell & ~blocked & ~no_fc
    return keep, {
        "eligible": int(elig.sum()),
        "sell": int((elig & sell).sum()),
        "blocked": int((elig & ~sell & blocked).sum()),
        "no_forecast": int((elig & ~sell & ~blocked & no_fc).sum()),
        "candidates": int(keep.sum()),
    }


def compute(t: pd.DataFrame, validated: Sequence[str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Sub-scores for every candidate (NaN for the rest) and a summary."""
    keep, counts = candidates(t)
    c = t[keep]
    sec = c["sector"] if "sector" in c else pd.Series("Unknown", index=c.index)
    src_label, p_col, rel_col = probability_source(validated)

    def r(v: pd.Series) -> pd.Series:
        return sector_rank(v, sec)

    conf_parts = {
        "probability": r(_num(c, p_col)),
        "reliability": r(_num(c, rel_col)) if rel_col else pd.Series(np.nan, index=c.index),
    }
    up_parts = {"median_6m": r(_num(c, "med_6m")), "p90_6m": r(_num(c, "p90_6m"))}
    dte = _num(c, "days_to_earnings")
    earn = pd.Series(np.where(dte.isna(), 50.0, np.where(dte.between(0, 5), 0.0, 100.0)), c.index)
    safe_parts = {
        "low_volatility": r(-_num(c, "vol_63")),
        "small_downside": r(_num(c, "p10_6m")),
        "quality_f6": r(_num(c, "f6").fillna(50.0)),
        "no_earnings_5d": earn,
    }
    out = pd.DataFrame(index=t.index, dtype=float)
    for name, parts in (
        ("confidence", conf_parts),
        ("upside", up_parts),
        ("safety", safe_parts),
    ):
        out[name] = r(_weighted(parts, WEIGHTS[name])).reindex(t.index)
    out["balanced"] = out[["confidence", "upside", "safety"]].mean(axis=1, skipna=False)
    floor_ok = (out[["confidence", "upside", "safety"]] >= FLOOR).all(axis=1)
    out["passes_floor"] = floor_ok & out["balanced"].notna()
    ranked = out.loc[out["passes_floor"], "balanced"].sort_values(ascending=False)
    out["pick_rank"] = pd.Series(np.arange(1, len(ranked) + 1), index=ranked.index).reindex(t.index)
    summary = {
        **counts,
        "passing_floor": int(out["passes_floor"].sum()),
        "probability_source": src_label,
        "reliability_available": bool(rel_col and _num(c, rel_col).notna().any()),
    }
    return out, summary


def tabs(scores: pd.DataFrame, top: int = TOP) -> dict[str, list[str]]:
    ok = scores[scores["passes_floor"]]
    res = {}
    for tab, col in TABS.items():
        order = ok.sort_values([col, "balanced"], ascending=[False, False])
        res[tab] = [str(x) for x in order.index[:top]]
    return res


def reasons(row: pd.Series, scores: pd.Series) -> list[str]:
    """2-3 plain-English reasons: the strongest evidence families, then the best sub-score."""
    fams = [
        (f, float(row[f]))
        for f in FAMILY_NAMES
        if f in row.index and row[f] is not None and not _isnan(row[f]) and float(row[f]) >= 55
    ]
    fams.sort(key=lambda x: -x[1])
    out = [f"{REASON_TEXT[f]} ({FAMILY_NAMES[f]} {round(s)}/100)" for f, s in fams[:3]]
    if len(out) < 2:
        best = max(("safety", "upside", "confidence"), key=lambda k: float(scores[k]))
        text = {
            "safety": "Calmer and safer than most stocks in its sector",
            "upside": "Larger expected 6-month gain than most stocks in its sector",
            "confidence": "Higher chance of rising than most stocks in its sector",
        }[best]
        out.append(f"{text} ({best} {round(float(scores[best]))}/100)")
    return out[:3]


def main_risk(row: pd.Series) -> str:
    """The single most important risk, from the data (never empty)."""
    dte = row.get("days_to_earnings")
    if dte is not None and not _isnan(dte) and 0 <= float(dte) <= 5:
        return f"Reports earnings in {int(dte)} trading days: the price can jump either way."
    short = row.get("short_pct_float")
    if short is not None and not _isnan(short) and float(short) >= 0.15:
        return f"Heavily shorted: {float(short):.0%} of the tradable shares are sold short."
    fams = [
        (f, float(row[f]))
        for f in FAMILY_NAMES
        if f in row.index and row[f] is not None and not _isnan(row[f])
    ]
    if fams:
        f, s = min(fams, key=lambda x: x[1])
        if s <= 25:
            return f"Weak {FAMILY_NAMES[f].lower()} evidence ({round(s)}/100 in its sector)."
    vol = row.get("vol_63")
    if vol is not None and not _isnan(vol) and float(vol) >= 0.5:
        return f"Very volatile: it moves about {float(vol):.0%} a year."
    p10 = row.get("p10_6m")
    if p10 is not None and not _isnan(p10) and float(p10) < 0:
        return f"1 in 10 chance of losing {abs(float(p10)):.0%} or more in 6 months."
    return "Forecasts can be wrong: no outcome is guaranteed."


def _isnan(v: Any) -> bool:
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return True


def _f(v: Any, digits: int = 4) -> float | None:
    return None if _isnan(v) else round(float(v), digits)


def export(
    t: pd.DataFrame,
    scores: pd.DataFrame,
    summary: Mapping[str, Any],
    as_of: str,
    now: datetime,
    validated: Sequence[str],
    brokers: Mapping[str, Any] | None,
    race: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """picks.json: the four tabs (top 25 each) and one record per stock shown."""
    tab_lists = tabs(scores)
    # With "Only stocks I can buy on finanzen.net zero" ticked, the page shows these instead:
    # the top 25 among stocks not known to be unavailable (unknown counts as possibly buyable).
    zero = t["zero"] if "zero" in t else pd.Series(None, index=t.index, dtype=object)
    not_unavailable = zero.reindex(scores.index).map(
        lambda v: v is not False and v is not np.False_
    )
    tab_zero = tabs(scores[not_unavailable.astype(bool)])
    shown = list(dict.fromkeys(x for lst in [*tab_lists.values(), *tab_zero.values()] for x in lst))
    stocks: dict[str, Any] = {}
    for tk in shown:
        row, s = t.loc[tk], scores.loc[tk]
        hz = {}
        for name in HORIZON_NAMES.values():
            rel = None
            if _f(row.get(f"hit_up_{name}")) is not None:
                rel = {
                    "rate": _f(row.get(f"hit_up_{name}")),
                    "lo": _f(row.get(f"hit_up_{name}_lo")),
                    "hi": _f(row.get(f"hit_up_{name}_hi")),
                    "n": None
                    if _isnan(row.get(f"hit_up_{name}_n"))
                    else int(row[f"hit_up_{name}_n"]),
                }
            hz[name] = {
                "median": _f(row.get(f"med_{name}")),
                "p10": _f(row.get(f"p10_{name}")),
                "p90": _f(row.get(f"p90_{name}")),
                "p_up": _f(row.get(f"p_up_{name}")),
                "validated": f"P(up) {name}" in validated,
                "reliability": rel,
            }
        ne = row.get("next_earnings")
        stocks[tk] = {
            "ticker": tk,
            "name": None if _missing(row.get("name")) else str(row.get("name")),
            "sector": None if _missing(row.get("sector")) else str(row.get("sector")),
            "label": str(row.get("label")),
            "next_earnings": None if _missing(ne) else str(ne)[:10],
            "zero": None if _missing(row.get("zero")) else bool(row.get("zero")),
            "price": _f(row.get("price"), 2),
            "scores": {k: _f(s[k], 1) for k in ("safety", "upside", "confidence", "balanced")},
            "rank": None if _isnan(s.get("pick_rank")) else int(s["pick_rank"]),
            "horizons": hz,
            "reasons": reasons(row, s),
            "risk": main_risk(row),
        }
    return {
        "schema_version": 1,
        "generated_at": now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "as_of": as_of,
        "research_mode": True,
        "validated": list(validated),
        "weights": WEIGHTS,
        "floor": FLOOR,
        "top": TOP,
        "min_sector": MIN_SECTOR,
        "summary": dict(summary),
        "brokers": dict(brokers) if brokers else None,
        "race": dict(race) if race else None,
        "tabs": tab_lists,
        "tabs_zero": tab_zero,
        "stocks": stocks,
    }


def _missing(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() == "" or v.lower() == "nan"
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False
