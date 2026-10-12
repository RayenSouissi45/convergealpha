import math

import pandas as pd
import pytest

from convergealpha.core import stats
from convergealpha.decide import rules as R


def test_fallback_ev_equals_expected_excess_minus_costs() -> None:
    fi = R.ForecastInputs(mu=0.10, sigma=0.30, alpha=0.04, tracking=0.25)
    win, loss = R.conditional_win_loss(fi, 63)
    t = 63 / 252
    p = R.forecast(fi)["3m"]["p_beat"]
    ev = stats.expected_value(p, win, loss, 0.002)
    assert ev == pytest.approx(fi.alpha * t - 0.002, abs=1e-6)


def test_fallback_probability_matches_formula() -> None:
    fi = R.ForecastInputs(mu=0.08, sigma=0.25, alpha=0.0, tracking=0.2)
    f = R.forecast(fi)
    t = 126 / 252
    expected = stats.p_up_fallback(0.08, 0.25, 126)
    assert f["6m"]["p_up"] == pytest.approx(expected)
    assert f["6m"]["p_beat"] == pytest.approx(0.5)
    assert f["6m"]["p10"] < f["6m"]["median"] < f["6m"]["p90"]
    assert f["6m"]["median"] == pytest.approx(math.exp((0.08 - 0.25**2 / 2) * t) - 1)


def _row(**kw: object) -> pd.Series:
    base = {f"f{i}": 70.0 for i in range(1, 7)} | {
        "l1_rank_pct": 0.99, "n_eff": 3.2, "disagreement": 10.0, "price": 50.0, "adv_dollar": 50e6,
        "vol_63": 0.25, "trend_up": True, "top_rated_sources": 1, "insider_buy_usd": 0.0, "f2_pct": 0.5,
    }  # fmt: skip
    base.update(kw)
    return pd.Series(base)


def test_buy_when_every_rule_passes_and_tiers() -> None:
    label, _rules, extra = R.evaluate(
        _row(), "Normal", [], {"p_hat": 0.62, "p_lower": 0.56, "meta": 0.6, "ev": 0.02}
    )
    assert label == R.LABEL_BUY
    assert extra["tier"] == 1
    label2, _, extra2 = R.evaluate(
        _row(n_eff=2.6), "Normal", [], {"p_hat": 0.58, "p_lower": 0.53, "meta": 0.6, "ev": 0.02}
    )
    assert label2 == R.LABEL_BUY and extra2["tier"] == 2


def test_blocking_event_stress_regime_and_illiquidity_prevent_buys() -> None:
    pf = {"p_hat": 0.62, "p_lower": 0.56, "meta": 0.6, "ev": 0.02}
    assert R.evaluate(_row(), "Normal", ["earnings in 3 trading days"], pf)[0] != R.LABEL_BUY
    assert R.evaluate(_row(), "Stress", [], pf)[0] != R.LABEL_BUY
    assert R.evaluate(_row(price=4.0), "Normal", [], pf)[0] != R.LABEL_BUY


def test_caution_regime_raises_the_probability_bar() -> None:
    pf = {"p_hat": 0.56, "p_lower": 0.53, "meta": 0.6, "ev": 0.02}
    assert R.evaluate(_row(), "Normal", [], pf)[0] == R.LABEL_BUY
    assert R.evaluate(_row(), "Caution", [], pf)[0] != R.LABEL_BUY


def test_watch_when_exactly_one_rule_misses_by_a_small_margin() -> None:
    pf = {"p_hat": 0.62, "p_lower": 0.56, "meta": 0.6, "ev": 0.007}  # R9 misses: 0.7% < 1.0%
    assert R.evaluate(_row(), "Normal", [], pf)[0] == R.LABEL_WATCH
    pf_far = {"p_hat": 0.62, "p_lower": 0.56, "meta": 0.6, "ev": 0.001}
    assert R.evaluate(_row(), "Normal", [], pf_far)[0] == R.LABEL_NONE


def test_top_conviction_needs_every_c_rule_including_analogs() -> None:
    row = _row(
        f1=75.0,
        f2=80.0,
        f3=72.0,
        f4=71.0,
        f5=78.0,
        f6=65.0,
        n_eff=3.5,
        disagreement=5.0,
        top_rated_sources=3,
        insider_buy_usd=250_000.0,
    )
    pf = {"p_hat": 0.66, "p_lower": 0.60, "meta": 0.62, "ev": 0.03, "analog_pass": True}
    assert R.evaluate(row, "Normal", [], pf)[0] == R.LABEL_TOP
    assert R.evaluate(row, "Normal", [], {**pf, "analog_pass": None})[0] == R.LABEL_BUY
    assert (
        R.evaluate(row, "Caution", [], {**pf, "p_lower": 0.60})[0] == R.LABEL_BUY
    )  # C6 needs Normal


def test_provisional_labels_cannot_be_buy_without_wilson_bound_unless_marked() -> None:
    # No Wilson bound and not provisional: R7 cannot be evaluated, so no BUY.
    assert (
        R.evaluate(_row(), "Normal", [], {"p_hat": 0.62, "meta": 0.6, "ev": 0.02})[0] != R.LABEL_BUY
    )


def test_risk_label_for_hard_risks() -> None:
    label, _, extra = R.evaluate(
        _row(), "Normal", ["restatement / non-reliance (8-K item 4.02)"], {"p_hat": 0.5, "ev": 0.0}
    )
    assert label == R.LABEL_RISK and extra["risk_reasons"]


def test_plan_reference_numbers() -> None:
    plan = R.plan(
        pd.Series({"price": 100.0, "atr14": 4.0, "gap_stress_pct": 0.09, "adv_shares": 1e6}),
        0.53,
        11 / 7,
        1,
    )
    assert plan is not None
    assert plan["planned_exit"] == pytest.approx(92.0)
    assert plan["risk_per_share"] == pytest.approx(9.0)  # gap stress dominates
    assert plan["sell_third_at"] == pytest.approx(112.0)
    assert plan["breakeven_after"] == pytest.approx(106.0)


def test_blocking_events_from_evidence() -> None:
    t = pd.DataFrame(
        {
            "days_to_earnings": [3, 30, 2, 40],
            "days_since_report": [60, 20, 5, 40],
            "offering_recent": [False, True, False, False],
            "merger_pending": [False, False, False, False],
            "lockup_soon": [False, False, False, False],
            "auditor_change": [False, False, False, False],
            "restatement": [False, False, False, True],
            "late_filing": [False, False, False, False],
            "news_negative_tags": [None, None, None, "investigation"],
        },
        index=["EARN", "OFFR", "POST", "BAD"],
    )
    b = R.blocking_events(t)
    assert b["EARN"] == ["earnings in 3 trading days"]
    assert b["OFFR"] == ["share offering announced"]
    assert b["POST"] == []  # 1-10 days after a report is a post-earnings entry
    assert len(b["BAD"]) == 2
