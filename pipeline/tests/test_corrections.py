"""Sector and stock corrections: the fixed protocol adopts a correction only when it helps on the
test years, and the weekly refit only for what was adopted."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from convergealpha.research import corrections as RC


def oos(biased: bool, seed: int = 1) -> pd.DataFrame:
    """96 month-ends x 200 stocks. The raw score is honest overall; with `biased`, stocks in sector
    'Hype' rise much less often than their score says (a sector-level miscalibration)."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2016-01-31", "2023-12-31", freq="ME")
    rows = []
    for d in dates:
        for i in range(200):
            sector = "Hype" if i < 50 else "Steady"
            raw = rng.uniform(0.3, 0.7)
            p_true = raw - (0.15 if biased and sector == "Hype" else 0.0) + (0.05 if biased and sector == "Steady" else 0.0)  # fmt: skip
            up = float(rng.uniform() < p_true)
            rows.append((d, f"T{i}", sector, raw, up))
    df = pd.DataFrame(rows, columns=["date", "ticker", "sector", "raw_up_1m", "up_1m"])
    return df


def test_a_real_sector_bias_is_adopted_and_noise_is_not() -> None:
    res = RC.evaluate(oos(True))["horizons"]["1m"]
    assert res["adopt_sector"] and res["gain_sector"] > RC.MIN_GAIN
    assert res["sectors"]["Hype"] < 0 < res["sectors"]["Steady"]
    noise = RC.evaluate(oos(False, seed=2))["horizons"]["1m"]
    assert not noise["adopt_sector"] and not noise["adopt_stock"]


def test_shifts_are_weighted_and_capped() -> None:
    d = pd.DataFrame({"ticker": [f"T{i}" for i in range(10)] * 3, "sector": "S", "month": ["2016-01"] * 10 + ["2016-02"] * 10 + ["2016-03"] * 10, "p": 0.9, "y": 0.0})  # fmt: skip
    s = RC.sector_shifts(d)
    assert s["S"] == -RC.CAP  # 3 months: weight 3/27, gap huge, capped anyway
    p = RC.apply(np.array([0.5]), pd.Series(["S"]), pd.Series(["T0"]), s, {"T0": -0.3})
    assert p[0] == pytest.approx(1 / (1 + np.exp(RC.CAP)))  # total shift capped at 0.3


def test_weekly_refit_only_for_adopted_horizons() -> None:
    from convergealpha.models import train as T

    df = oos(True)
    cal = {"1m": T._iso(df["raw_up_1m"].to_numpy(), df["up_1m"].to_numpy(), 500)}
    out = RC.refit(df, cal, {"1m": {"sector": True, "stock": False}, "1w": {"sector": False, "stock": False}})  # fmt: skip
    assert set(out) == {"1m"} and set(out["1m"]) == {"sector"} and out["1m"]["sector"]["Hype"] < 0
    assert RC.protocol_digest() == RC.protocol_digest() and len(RC.protocol_digest()) == 12


def test_quality_filters_follow_the_fixed_protocol() -> None:
    from convergealpha.research import filters as RF

    rng = np.random.default_rng(3)
    dates = pd.date_range("2016-01-31", "2023-12-31", freq="ME")
    rows, feats = [], []
    for d in dates:
        for i in range(100):
            burn = i % 10 == 0  # 10% of stocks burn cash, and among the top picks they lose
            l1 = rng.uniform() + (1.0 if i < 5 else 0.0)  # T0..T4 are the model's top picks
            exc = (-0.2 if burn else 0.02) + rng.normal(0, 0.01)
            rows.append((d, f"T{i}", l1, exc))
            feats.append((d, f"T{i}", "S", True, -0.05 if burn else 0.05, 1.0, 0.0))
    oos = pd.DataFrame(rows, columns=["date", "ticker", "l1", "exc_3m"])
    ds = pd.DataFrame(feats, columns=["date", "ticker", "sector", "eligible", "fcf_yield", "debt_ebitda", "accruals"])  # fmt: skip
    res = RF.evaluate(oos, ds)
    assert res["picks"] == 2 * len(dates)  # top 2% of 100 = 2 a month
    cb = res["filters"]["cash_burn"]
    assert cb["adopted"] and cb["all"]["score"] > res["no_filter"]["all"]["score"] and cb["keep_share"] >= 0.7  # fmt: skip
    assert not res["filters"]["heavy_debt"][
        "adopted"
    ]  # removes nothing, so it cannot beat no filter
    assert RF.protocol_digest() == RF.protocol_digest()
