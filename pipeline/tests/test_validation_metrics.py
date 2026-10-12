from typing import Any

import numpy as np
import pytest

from convergealpha.validate import metrics as V


def test_t_stat_and_sharpe() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(0.01, 0.02, 400)
    assert V.t_stat(x) == pytest.approx(x.mean() / (x.std(ddof=1) / 20), rel=1e-9)
    assert V.sharpe(x) == pytest.approx(x.mean() / x.std(ddof=1))


def test_max_drawdown() -> None:
    assert V.max_drawdown(np.array([0.10, -0.50, 0.20])) == pytest.approx(-0.5)
    assert V.max_drawdown(np.array([0.01, 0.02])) == pytest.approx(0.0)


def test_deflated_sharpe_penalizes_many_trials() -> None:
    rng = np.random.default_rng(1)
    x = rng.normal(0.01, 0.03, 120)
    one = V.deflated_sharpe(x, 1, 0.0)
    many = V.deflated_sharpe(x, 200, 0.02)
    assert 0 <= many < one <= 1


def test_expected_max_sharpe_grows_with_trials() -> None:
    assert V.expected_max_sharpe(1, 0.01) == 0
    assert V.expected_max_sharpe(10, 0.01) < V.expected_max_sharpe(1000, 0.01)


def test_pbo_low_for_a_genuinely_better_strategy_high_for_noise() -> None:
    rng = np.random.default_rng(2)
    noise = rng.normal(0, 0.02, (160, 8))
    assert V.pbo(noise) > 0.2  # picking the best of pure noise generalizes badly
    good = noise.copy()
    good[:, 0] += 0.02  # one strategy is truly better everywhere
    assert V.pbo(good) < 0.1


def test_brier_and_calibration_slope() -> None:
    rng = np.random.default_rng(3)
    p = rng.uniform(0.2, 0.8, 20000)
    y = (rng.uniform(size=p.size) < p).astype(float)
    assert V.calibration_slope(p, y) == pytest.approx(1.0, abs=0.08)
    assert V.brier(p, y) < V.brier(np.full_like(p, y.mean()), y)
    # Overconfident forecasts have a slope below 1.
    stretched = np.clip(0.5 + 2 * (p - 0.5), 0.01, 0.99)
    assert V.calibration_slope(stretched, y) < 0.7


def test_verdict_shows_halved_excess_and_keeps_pass_logic() -> None:
    from convergealpha.validate.lab import verdict

    def strat(app: float, t: float, base: float) -> dict[str, Any]:
        return {
            "app": {"net_excess_annual": app, "t_stat": t, "max_drawdown": -0.1},
            "baseline_momentum": {"net_excess_annual": base},
        }

    report = {
        "periods": {
            "development": {"strategies": strat(0.10, 2.5, 0.02)},
            "validation": {"strategies": strat(0.08, 2.1, 0.01)},
        },
        "holdout": {"strategies": strat(0.06, 2.0, 0.0), "calibration": {}},
        "overfitting": {"deflated_sharpe": 0.97, "trials": 8, "pbo": 0.1},
        "holdout_touches": 1,
    }
    v = verdict(report)
    first = v["checks"][0]
    assert first["passed"] is True
    assert first["value"].startswith("+5.00%/yr (halved)")
    # The slope check has no holdout calibration -> unknown, so the label is not validated.
    assert v["label_pass"] is False
    assert all(c["passed"] for c in v["checks"] if c["check"].startswith("Net excess"))
