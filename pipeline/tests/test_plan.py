"""plan.json: fixed thresholds (mirrored in web/src/lib/plan.ts) and the export shape."""

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from convergealpha.decide import plan as PLAN


def test_thresholds_are_fixed() -> None:
    # Changing one is a methodology change: update docs/METHODOLOGY.md, plan.ts and its test.
    assert PLAN.THRESHOLDS == {
        "green_p_profit": 0.55,
        "green_reliability_lo": 0.52,
        "amber_p_profit": 0.50,
        "slider_min_score": {"1": 0.0, "10": 90.0},
        "confidence_weight": 5.0,
        "trading_days_per_day": 0.7,
    }


def test_export_keeps_only_picks_candidates_with_their_forecasts() -> None:
    t = pd.DataFrame(
        {
            "name": ["A", "B"],
            "sector": ["Tech", "Tech"],
            "zero": [True, None],
            "label": ["NO TRADE", "NO TRADE"],
            "price": [50.0, 20.0],
            "adv_dollar": [5e8, 2e7],
            "pick_safety": [80.0, np.nan],  # B is not a Picks candidate
            "pick_upside": [60.0, np.nan],
            "pick_confidence": [70.0, np.nan],
            "pick_balanced": [70.0, np.nan],
            "days_to_earnings": [12.0, 3.0],
            "next_earnings": [pd.Timestamp("2026-10-29"), pd.NaT],
            "opp": ["amber", None],
            "opp_event": ["Estimates raised (Oct 12)", None],
            **{
                f"{k}_{h}": [0.55, 0.5]
                for h in ("1w", "1m", "3m", "6m")
                for k in ("p_up", "med", "p10", "p90")
            },
        },
        index=pd.Index(["AAA", "BBB"], name="ticker"),
    )
    rel = {"years": [2016, 2023], "horizons": {"1m": {"up": [{"lo": 0.0, "hi": 1.01, "n": 500, "hits": 270, "rate": 0.54, "wilson_lo": 0.5, "wilson_hi": 0.58}]}}}  # fmt: skip
    out = PLAN.export(t, "2026-10-13", datetime(2026, 10, 13, 21, tzinfo=UTC), ["P(up) 1m"], rel, {"1m": 0.54}, (1.1259, "2026-10-02"))  # fmt: skip
    assert out["count"] == 1 and out["fields"][0] == "ticker"
    row = dict(zip(out["fields"], out["rows"][0], strict=True))
    assert row["ticker"] == "AAA" and row["zero"] is True and row["opp"] == "amber"
    assert row["spread"] == 0.0003 and row["next_earnings"] == "2026-10-29"
    assert out["fx"]["rate"] == 1.1259 and out["reliability"]["1m"][0]["n"] == 500
    assert out["horizons"] == {"1w": 5, "1m": 21, "3m": 63, "6m": 126}
