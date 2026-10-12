"""Triple-barrier labels (spec section 5): entry next open, upper E + 3 ATR, lower E - 2 ATR,
60 trading days; correct = exit return - S&P 500 return - costs > 0."""

import numpy as np
import pandas as pd
import pytest

from convergealpha.models import dataset as D
from convergealpha.sources import prices as P
from convergealpha.util.calendar import add_trading_days

N = 140


def make_panel(paths: dict[str, np.ndarray], spy: np.ndarray | None = None) -> P.Panel:
    start = pd.Timestamp("2025-01-02").date()
    dates = [pd.Timestamp(add_trading_days(start, i)) for i in range(N)]
    frames = []
    for t, c in {**paths, "SPY": spy if spy is not None else np.full(N, 100.0)}.items():
        frames.append(
            pd.DataFrame(
                {
                    "ticker": t,
                    "date": dates,
                    "open": c,
                    "high": c * 1.005,
                    "low": c * 0.995,
                    "close": c,
                    "volume": 1e6,
                    "dividend": 0.0,
                    "split": 0.0,
                    "basis": dates[-1],
                }
            )
        )
    return P.build_panel(pd.concat(frames, ignore_index=True))


def history(panel: P.Panel) -> D.History:
    from convergealpha.features.price_features import wilder_atr

    atr = wilder_atr(
        panel.high.astype("float64"), panel.low.astype("float64"), panel.close.astype("float64")
    )
    stocks = pd.DataFrame(
        {"sector": "X", "industry_group": "1", "cik": np.nan},
        index=[t for t in panel.close.columns if t != "SPY"],
    )
    empty = pd.DataFrame()
    return D.History(
        panel,
        stocks,
        empty,
        empty,
        empty,
        empty,
        pd.DataFrame(columns=["cik", "end", "known", "sue"]),
        empty,
        atr,
        empty,
    )


def flat_then(after: np.ndarray, at: int = 40) -> np.ndarray:
    base = 100 + 0.1 * np.sin(np.arange(N))  # ATR ~ 1
    out = base.copy()
    out[at + 1 :] = after[: N - at - 1]
    return out


def test_win_loss_and_time_exit() -> None:
    k = N - 41
    winner = flat_then(100 + np.linspace(0.5, 10, k))  # climbs past +3 ATR
    loser = flat_then(100 - np.linspace(0.5, 10, k))  # falls past -2 ATR
    drifter = flat_then(100 + 0.1 * np.sin(np.arange(k)))  # stays inside -> time exit
    h = history(make_panel({"WIN": winner, "LOSE": loser, "FLAT": drifter}))
    d = h.panel.close.index[40]
    lab = D.labels_at(h, d, ["WIN", "LOSE", "FLAT"])
    assert lab.loc["WIN", "tb_outcome"] == 1 and lab.loc["WIN", "tb_correct"] == 1
    assert lab.loc["LOSE", "tb_outcome"] == -1 and lab.loc["LOSE", "tb_correct"] == 0
    assert lab.loc["FLAT", "tb_outcome"] == 0 and lab.loc["FLAT", "tb_days"] == 60
    atr = h.atr.loc[d, "LOSE"]
    entry = h.panel.open["LOSE"].iloc[41]
    # Exit at the lower barrier (no gap): return = -2 ATR / E.
    assert lab.loc["LOSE", "tb_ret"] == pytest.approx(-2 * atr / entry, rel=0.05)


def test_gap_through_the_lower_barrier_exits_at_the_open() -> None:
    k = N - 41
    after = np.full(k, 100.0)
    after[5:] = 90.0  # overnight gap far below the barrier
    h = history(make_panel({"GAP": flat_then(after)}))
    d = h.panel.close.index[40]
    lab = D.labels_at(h, d, ["GAP"])
    entry = h.panel.open["GAP"].iloc[41]
    assert lab.loc["GAP", "tb_ret"] == pytest.approx(90.0 / entry - 1, rel=1e-3)


def test_excess_return_subtracts_the_market_and_costs() -> None:
    k = N - 41
    stock = flat_then(100 + 0.1 * np.sin(np.arange(k)))
    spy = flat_then(np.linspace(100, 110, k))  # market up ~10% while the stock is flat
    h = history(make_panel({"S": stock}, spy))
    lab = D.labels_at(h, h.panel.close.index[40], ["S"])
    assert lab.loc["S", "tb_excess"] < -0.05
    assert lab.loc["S", "tb_correct"] == 0


def test_no_label_without_enough_future() -> None:
    h = history(make_panel({"S": np.full(N, 100.0)}))
    lab = D.labels_at(h, h.panel.close.index[-10], ["S"])
    assert "tb_correct" not in lab or lab["tb_correct"].isna().all()
    assert "ret_6m" not in lab
