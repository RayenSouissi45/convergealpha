"""The challenger model: compared fairly with the champion on 2016-2023, live in the shadow."""

from __future__ import annotations

import numpy as np
import pandas as pd

from convergealpha.models import challenger as CH
from convergealpha.models import train as T


def oos(noise: float, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2016-01-31", "2023-12-31", freq="ME")
    n = len(dates) * 300
    truth = rng.uniform(0.3, 0.7, n)
    rows = {
        "date": np.repeat(dates, 300),
        "up_1m": (rng.uniform(size=n) < truth).astype(float),
        "up_6m": (rng.uniform(size=n) < truth).astype(float),
    }
    # The raw score is the truth plus noise: less noise = a better model.
    rows["raw_up_1m"] = truth + rng.normal(0, noise, n)
    rows["raw_up_6m"] = truth + rng.normal(0, noise, n)
    return pd.DataFrame(rows)


def test_the_challenger_must_win_in_both_halves_for_both_horizons() -> None:
    champ, better, worse = oos(0.30, 1), oos(0.05, 2), oos(0.60, 3)
    assert CH.compare(champ, better)["ahead_on_history"] is True
    res = CH.compare(champ, worse)
    assert res["ahead_on_history"] is False
    h = res["horizons"]["1m"]
    assert set(h["champion"]) == {"2016-2019", "2020-2023"} and h["challenger_better"] is False


def test_the_challenger_is_fixed_in_advance_and_more_regularised() -> None:
    champ = T.TrainConfig()
    ch = CH.config(champ)
    assert ch.num_leaves < champ.num_leaves and ch.min_child_samples > champ.min_child_samples
    assert ch.features == champ.features and CH.protocol_digest() == CH.protocol_digest(champ)


def test_live_shadow_comparison_needs_enough_periods() -> None:
    days = [f"2026-10-{d:02d}" for d in range(1, 29)]
    rows = [(d, f"T{i}", "1m", 0.6, 0.6 if i < 60 else 0.4, 0.01 if i < 60 else -0.01) for d in days for i in range(100)]  # fmt: skip
    df = pd.DataFrame(rows, columns=["day", "ticker", "horizon", "p_up", "p_ch", "ret"])
    live = CH.live_compare(df)
    assert (
        live["1m"]["challenger_better"] is True and live["1m"]["enough"] is False
    )  # 28 days = 1.3 months
    assert live["6m"] == {"n": 0, "periods": 0.0}
