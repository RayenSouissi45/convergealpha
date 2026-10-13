"""plan.json: everything the Plan builder needs, computed in your browser for your own amount.

One compact row per Picks candidate (eligible, not SELL / RISK WARNING, not blocked, with a full
forecast): the Picks sub-scores, the forecast at each horizon, price, spread, earnings date,
finanzen.net zero flag and opportunity badge. The file also carries the "how often right" tables,
the usual up rates, the EUR/USD rate and the fixed thresholds (docs/METHODOLOGY.md, "Plan builder").
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from convergealpha.config import HORIZON_NAMES, HORIZONS
from convergealpha.decide import costs as C

# Fixed in advance (never fitted). The site mirrors them in web/src/lib/plan.ts; a test pins both.
THRESHOLDS = {
    "green_p_profit": 0.55,  # chance of ending with more money than you put in, after costs
    "green_reliability_lo": 0.52,  # lower end of "how often right"
    "amber_p_profit": 0.50,
    "slider_min_score": {"1": 0.0, "10": 90.0},  # slider s -> minimum sub-score 10 * (s - 1)
    "confidence_weight": 5.0,  # weight of Confidence in the ranking mix (a middle slider)
    "trading_days_per_day": 0.7,  # 30 calendar days = 21 trading days
}

FIELDS = (
    "ticker", "name", "sector", "zero", "label", "price", "spread", "safety", "upside", "confidence",
    "balanced", "days_to_earnings", "next_earnings", "opp", "opp_event",
    *[f"{k}_{h}" for h in HORIZON_NAMES.values() for k in ("p_up", "med", "p10", "p90")],
)  # fmt: skip


def _cell(v: Any, digits: int = 4) -> Any:
    if v is None:
        return None
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, str):
        return v
    if isinstance(v, pd.Timestamp):
        return None if pd.isna(v) else v.strftime("%Y-%m-%d")
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(x):
        return None
    return round(x, digits)


def export(
    t: pd.DataFrame,
    as_of: str,
    now: datetime,
    validated: Sequence[str],
    reliability: dict[str, Any] | None,
    base_rates: dict[str, float],
    fx: tuple[float, str] | None,
) -> dict[str, Any]:
    keep = t["pick_safety"].notna() if "pick_safety" in t else pd.Series(False, index=t.index)
    c = t[keep]
    rows = []
    for tk, r in c.iterrows():
        vals: dict[str, Any] = {
            "ticker": str(tk),
            "name": r.get("name") if isinstance(r.get("name"), str) else None,
            "sector": r.get("sector") if isinstance(r.get("sector"), str) else None,
            "zero": bool(r["zero"]) if isinstance(r.get("zero"), (bool, np.bool_)) else None,
            "label": str(r.get("label")),
            "price": _cell(r.get("price"), 4),
            "spread": round(C.spread(_cell(r.get("adv_dollar"))), 5),
            "safety": _cell(r.get("pick_safety"), 1),
            "upside": _cell(r.get("pick_upside"), 1),
            "confidence": _cell(r.get("pick_confidence"), 1),
            "balanced": _cell(r.get("pick_balanced"), 1),
            "days_to_earnings": _cell(r.get("days_to_earnings"), 0),
            "next_earnings": _cell(pd.Timestamp(r["next_earnings"]))
            if pd.notna(r.get("next_earnings"))
            else None,
            "opp": r.get("opp") if isinstance(r.get("opp"), str) else None,
            "opp_event": r.get("opp_event") if isinstance(r.get("opp_event"), str) else None,
        }
        for h in HORIZON_NAMES.values():
            for k in ("p_up", "med", "p10", "p90"):
                vals[f"{k}_{h}"] = _cell(r.get(f"{k}_{h}"), 4)
        rows.append([vals[f] for f in FIELDS])
    rel_up = {
        h: [
            {k: b[k] for k in ("lo", "hi", "n", "rate", "wilson_lo", "wilson_hi")}
            for b in v.get("up", [])
        ]
        for h, v in ((reliability or {}).get("horizons") or {}).items()
    }
    return {
        "schema_version": 1,
        "generated_at": now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "as_of": as_of,
        "research_mode": True,
        "validated": list(validated),
        "horizons": {HORIZON_NAMES[h]: h for h in HORIZONS},
        "fx": {"rate": fx[0], "date": fx[1], "series": C.FX_SERIES, "source": "FRED"}
        if fx
        else None,
        "base_up": {k: round(v, 4) for k, v in base_rates.items()},
        "reliability": rel_up,
        "reliability_years": (reliability or {}).get("years"),
        "costs": {"fee_buy": C.FEE_BUY_EUR, "fee_sell": C.FEE_SELL_EUR},
        "thresholds": THRESHOLDS,
        "count": len(rows),
        "fields": list(FIELDS),
        "rows": rows,
    }
