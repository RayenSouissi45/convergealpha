"""Picks page rules: exclusions, sector-neutral ranks, fixed weights, the minimum-40 rule."""

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from convergealpha.decide import picks as PK


def table(n: int = 60, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = [f"S{i:02d}" for i in range(n)]
    t = pd.DataFrame(
        {
            "name": [f"Stock {i}" for i in range(n)],
            "sector": ["Tech" if i % 2 else "Health" for i in range(n)],
            "eligible": True,
            "label": "NO TRADE",
            "blocked": False,
            "p_up_6m": rng.uniform(0.45, 0.70, n),
            "p_up_1m": rng.uniform(0.45, 0.60, n),
            "p_hat": rng.uniform(0.40, 0.60, n),
            "p_lower": rng.uniform(0.35, 0.55, n),
            "hit_up_6m_lo": rng.uniform(0.45, 0.65, n),
            "med_6m": rng.normal(0.03, 0.05, n),
            "p90_6m": rng.normal(0.30, 0.08, n),
            "p10_6m": rng.normal(-0.25, 0.08, n),
            "vol_63": rng.uniform(0.15, 0.6, n),
            "f6": rng.uniform(0, 100, n),
            "days_to_earnings": rng.integers(6, 60, n).astype(float),
        },
        index=idx,
    )
    for f in ("f1", "f2", "f3", "f4", "f5"):
        t[f] = rng.uniform(0, 100, n)
    return t


def test_weights_are_fixed_and_sum_to_one() -> None:
    # Changing a weight is a methodology change: update docs/METHODOLOGY.md and this test.
    assert PK.WEIGHTS == {
        "confidence": {"probability": 0.7, "reliability": 0.3},
        "upside": {"median_6m": 0.75, "p90_6m": 0.25},
        "safety": {
            "low_volatility": 0.35,
            "small_downside": 0.35,
            "quality_f6": 0.20,
            "no_earnings_5d": 0.10,
        },
    }
    for parts in PK.WEIGHTS.values():
        assert sum(parts.values()) == pytest.approx(1.0)
    assert PK.FLOOR == 40 and PK.TOP == 25


def test_exclusions_sell_blocked_ineligible_and_missing_forecasts() -> None:
    t = table()
    t.loc["S00", "label"] = PK.SELL
    t.loc["S01", "blocked"] = True
    t.loc["S02", "eligible"] = False
    t.loc["S03", "med_6m"] = np.nan
    scores, summary = PK.compute(t, ["P(up) 6m"])
    for tk in ("S00", "S01", "S02", "S03"):
        assert scores.loc[tk, ["confidence", "upside", "safety"]].isna().all()
        assert not scores.loc[tk, "passes_floor"]
    assert summary["sell"] == 1 and summary["blocked"] == 1 and summary["no_forecast"] == 1
    assert summary["candidates"] == len(t) - 4
    shown = {x for lst in PK.tabs(scores).values() for x in lst}
    assert not shown & {"S00", "S01", "S02", "S03"}


def test_every_pick_scores_at_least_40_on_each_sub_score() -> None:
    t = table(120)
    scores, _ = PK.compute(t, ["P(up) 6m"])
    lists = PK.tabs(scores)
    assert set(lists) == {"balanced", "safest", "upside", "likely"}
    for tab, tickers in lists.items():
        assert 0 < len(tickers) <= PK.TOP
        sub = scores.loc[tickers, ["confidence", "upside", "safety"]]
        assert (sub >= PK.FLOOR).all().all(), tab
    # A stock strong in one area and terrible in another is never a pick.
    bad = scores[(scores["upside"] > 90) & (scores["safety"] < PK.FLOOR)]
    assert not bad.empty
    assert not bad["passes_floor"].any()
    # Balanced is the plain average, and the balanced tab is sorted by it.
    ok = scores[scores["passes_floor"]]
    assert np.allclose(ok["balanced"], ok[["confidence", "upside", "safety"]].mean(axis=1))
    b = scores.loc[lists["balanced"], "balanced"].to_numpy()
    assert (np.diff(b) <= 1e-12).all()
    assert scores.loc[lists["balanced"][0], "pick_rank"] == 1


def test_sector_neutral_ranks_and_small_sectors() -> None:
    v = pd.Series([1.0, 2.0, 3.0, 10.0, 20.0, 30.0, 5.0])
    sec = pd.Series(["A", "A", "A", "B", "B", "B", "C"])
    r = PK.sector_rank(v, sec, min_sector=3)
    # Within A and B: 0, 50, 100 regardless of the level of the values.
    assert r.iloc[:3].tolist() == [0.0, 50.0, 100.0]
    assert r.iloc[3:6].tolist() == [0.0, 50.0, 100.0]
    # C has one stock (< min_sector): ranked against everyone (5.0 is 4th of 7 -> 50).
    assert r.iloc[6] == pytest.approx(50.0)


def test_confidence_source_follows_validation() -> None:
    assert PK.probability_source(["P(up) 6m", "P(up) 1m"])[1] == "p_up_6m"
    assert PK.probability_source(["P(up) 1m"])[1] == "p_up_1m"
    assert PK.probability_source([])[1:] == ("p_hat", "p_lower")


def test_export_reasons_and_risk_in_plain_english() -> None:
    t = table()
    t["zero"] = pd.Series([True, False, None] * 20, index=t.index, dtype=object)
    t["next_earnings"] = pd.Timestamp("2026-11-02")
    scores, summary = PK.compute(t, ["P(up) 6m"])
    out = PK.export(
        t, scores, summary, "2026-10-13", datetime(2026, 10, 13, 22, tzinfo=UTC), ["P(up) 6m"], None
    )
    assert out["research_mode"] is True
    assert out["weights"] == PK.WEIGHTS
    tk = out["tabs"]["balanced"][0]
    s = out["stocks"][tk]
    assert 2 <= len(s["reasons"]) <= 3 and all(isinstance(x, str) and x for x in s["reasons"])
    assert s["risk"]
    assert s["next_earnings"] == "2026-11-02"
    assert s["zero"] in (True, False, None)
    assert set(s["horizons"]) == {"1w", "1m", "3m", "6m"}
    assert s["horizons"]["6m"]["validated"] is True and s["horizons"]["1w"]["validated"] is False
    # The finanzen.net zero lists never contain a stock known to be unavailable there.
    for tab, lst in out["tabs_zero"].items():
        assert all(out["stocks"][x]["zero"] is not False for x in lst), tab
        assert 0 < len(lst) <= len(out["tabs"][tab])


def test_main_risk_prefers_the_most_important_fact() -> None:
    row = pd.Series({"short_pct_float": 0.22, "f1": 80.0, "f2": 10.0, "p10_6m": -0.3})
    assert "shorted" in PK.main_risk(row)
    row = pd.Series({"short_pct_float": 0.02, "f1": 80.0, "f2": 10.0, "p10_6m": -0.3})
    assert "revisions" in PK.main_risk(row).lower()
    row = pd.Series({"f1": 60.0, "vol_63": 0.2, "p10_6m": -0.18})
    assert PK.main_risk(row) == "1 in 10 chance of losing 18% or more in 6 months."
