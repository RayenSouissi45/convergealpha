import math

import numpy as np
import pytest

from convergealpha.core import stats


def test_norm_cdf_reference_points() -> None:
    assert stats.norm_cdf(0.0) == pytest.approx(0.5)
    assert stats.norm_cdf(1.96) == pytest.approx(0.975, abs=1e-4)
    assert stats.norm_cdf(-1.96) == pytest.approx(0.025, abs=1e-4)


# --- Wilson interval: spec reference 230/400 -> 57.5% (52.6%-62.3%) ---


def test_wilson_reference_230_of_400() -> None:
    lo, hi = stats.wilson_interval(230, 400)
    assert round(lo, 3) == 0.526
    assert round(hi, 3) == 0.623


def test_wilson_edges_stay_in_unit_interval() -> None:
    lo, hi = stats.wilson_interval(0, 10)
    assert lo == pytest.approx(0.0, abs=1e-12) and 0 < hi < 1
    lo, hi = stats.wilson_interval(10, 10)
    assert 0 < lo < 1 and hi == pytest.approx(1.0)


def test_wilson_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        stats.wilson_interval(5, 0)
    with pytest.raises(ValueError):
        stats.wilson_interval(11, 10)


# --- N_eff: spec references 6 @ rho 0.6 -> 1.5; 4 @ rho 0.2 -> 2.5 ---


@pytest.mark.parametrize(("n", "rho", "expected"), [(6, 0.6, 1.5), (4, 0.2, 2.5)])
def test_n_eff_reference(n: int, rho: float, expected: float) -> None:
    assert stats.n_eff(np.ones(n), stats.uniform_corr(n, rho)) == pytest.approx(expected)


def test_n_eff_independent_sources_count_fully() -> None:
    assert stats.n_eff(np.ones(5), np.eye(5)) == pytest.approx(5.0)


def test_n_eff_shape_mismatch() -> None:
    with pytest.raises(ValueError):
        stats.n_eff(np.ones(3), np.eye(4))


# --- Costs: spec reference sigma 2%, order 1% ADV, spread 0.05%, commission 0.02% -> 0.29% ---


def test_trading_cost_reference() -> None:
    assert stats.trading_cost(0.0005, 0.0002, 0.02, 0.01) == pytest.approx(0.0029)


def test_expected_value() -> None:
    # 55% chance of +8%, 45% chance of -5%, 0.29% cost -> 1.86%
    assert stats.expected_value(0.55, 0.08, 0.05, 0.0029) == pytest.approx(0.0186)


# --- Kelly: spec reference p 0.53, b 11/7 -> 23.1% ---


def test_kelly_reference() -> None:
    assert stats.kelly_fraction(0.53, 11 / 7) == pytest.approx(0.2309, abs=1e-4)


# --- Position sizing: spec reference -> 5 shares ---


def test_position_sizing_reference() -> None:
    shares = stats.position_shares(
        equity=10_000, entry=100, exit_level=92, gap=9, p_lower=0.53, payoff_b=11 / 7
    )
    assert shares == 5


def test_position_sizing_tier2_is_half_risk() -> None:
    # Without the Kelly cap binding: risk 0.75% * 10,000 * 0.5 / 9 = 4.17 -> 4 shares
    shares = stats.position_shares(
        equity=10_000,
        entry=100,
        exit_level=92,
        gap=9,
        p_lower=0.70,
        payoff_b=2.0,
        tier_multiplier=0.5,
    )
    assert shares == 4


def test_position_sizing_adv_cap_and_negative_kelly() -> None:
    common = {"equity": 1_000_000, "entry": 50, "exit_level": 46, "gap": 1}
    assert stats.position_shares(**common, p_lower=0.6, payoff_b=2.0, adv_shares=10_000) == 100
    assert stats.position_shares(**common, p_lower=0.3, payoff_b=1.0) == 0


def test_planned_exit_uses_the_tighter_of_atr_and_8pct() -> None:
    assert stats.planned_exit(100, 3) == 94  # E - 2·ATR is higher than 92
    assert stats.planned_exit(100, 6) == 92  # 8% floor


def test_gap_stress_worst_two_percent() -> None:
    returns = np.concatenate([np.full(490, 0.001), np.full(10, -0.05)])
    assert stats.gap_stress(100, returns) == pytest.approx(5.0)


# --- Normalization ---


def test_robust_scores_median_is_50_and_clipped() -> None:
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
    scores = stats.robust_sector_scores(values, ["Tech"] * 7)
    assert scores[3] == pytest.approx(50.0)
    assert np.all(np.diff(scores) > 0)
    assert scores.max() <= 100 * stats.norm_cdf(3.0) + 1e-9


def test_robust_scores_are_sector_relative() -> None:
    tech = [10.0, 11.0, 12.0, 13.0, 14.0]
    utilities = [1.0, 2.0, 3.0, 4.0, 5.0]
    scores = stats.robust_sector_scores(tech + utilities, ["Tech"] * 5 + ["Util"] * 5)
    # The median of each sector scores 50 even though raw levels differ a lot.
    assert scores[2] == pytest.approx(50.0)
    assert scores[7] == pytest.approx(50.0)


def test_robust_scores_keep_missing_as_nan() -> None:
    scores = stats.robust_sector_scores([1.0, np.nan, 3.0, 4.0, 5.0, 6.0], ["A"] * 6)
    assert math.isnan(scores[1])
    assert not np.isnan(scores[[0, 2, 3, 4, 5]]).any()


def test_robust_scores_constant_signal_is_neutral() -> None:
    scores = stats.robust_sector_scores([2.0] * 6, ["A"] * 6)
    assert np.allclose(scores, 50.0)


# --- Fallback probability ---


def test_p_up_fallback_zero_drift_after_ito_is_half() -> None:
    sigma = 0.3
    assert stats.p_up_fallback(sigma**2 / 2, sigma, 126) == pytest.approx(0.5)


def test_p_up_fallback_positive_drift_rises_with_horizon() -> None:
    short = stats.p_up_fallback(0.15, 0.25, 5)
    long = stats.p_up_fallback(0.15, 0.25, 126)
    assert 0.5 < short < long < 1.0


def test_robust_scores_sparse_signal_still_ranks() -> None:
    # Most stocks have no insider buying (0): MAD is 0, so the standard deviation is used.
    values = [0.0] * 20 + [2.0, 5.0]
    scores = stats.robust_sector_scores(values, ["A"] * 22)
    assert scores[0] == pytest.approx(50.0)  # the median (no buying) is neutral
    assert 50 < scores[20] < scores[21]
