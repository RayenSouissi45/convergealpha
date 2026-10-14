"""Sell rules and entry timing research: each rule on hand-made price paths, the fixed decision
protocol, and the cut-off that keeps every price before 2024 (the holdout years)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from convergealpha.ledger import experiments as X
from convergealpha.research import rules as R


def path(
    closes: list[float], opens: list[float] | None = None, atr: float = 2.0, signal: float = 100.0
) -> R.PricePath:
    n = R.WINDOW + 1 + 21
    c = np.array((closes + [closes[-1]] * n)[:n], dtype=float)
    o = np.array(((opens or [closes[0]] + closes[:-1]) + [closes[-1]] * n)[:n], dtype=float)
    return R.PricePath(o, np.maximum(o, c) * 1.001, np.minimum(o, c) * 0.999, c, atr, signal)


def test_fixed_stop_sells_at_the_next_open_so_a_gap_counts() -> None:
    p = path(
        [100, 99, 96, 93, 90], opens=[100, 100, 98, 95, 85]
    )  # close 93 <= 94: sell at the next open, 85
    x = R.EXITS["fixed_6_tp_8"](p)
    assert x.stopped and x.days == 4 and x.ret == pytest.approx(85 / 100 - 1)


def test_take_profit_and_hold_to_the_end() -> None:
    up = path([100, 104, 109, 112], opens=[100, 101, 106, 110])
    x = R.EXITS["fixed_6_tp_8"](up)
    assert not x.stopped and x.ret == pytest.approx(110 / 100 - 1)
    flat = path([100] * 70)
    h = R.EXITS["hold_63"](flat)
    assert h.days == R.WINDOW and h.ret == pytest.approx(0)


def test_recovery_after_a_stop_is_counted() -> None:
    closes = [100, 97, 93] + [95] * 5 + [105] * 80
    x = R.EXITS["fixed_6_tp_8"](path(closes))
    assert x.stopped and x.recovered


def test_swing_based_plan_moves_to_break_even_and_sells_a_third() -> None:
    # ATR 2: exit at max(100 - 4, 92) = 96; break-even after 103; a third at 106; trail 3 ATR.
    closes = [100, 102, 104, 107, 109, 110, 104, 103]
    x = R.EXITS["atr_plan"](path(closes, atr=2.0))
    # A third sold at the open after the 107 close (= 107), the rest when 103 <= 110 - 6 = 104.
    assert x.ret == pytest.approx((107 / 100) / 3 + (104 / 100) * 2 / 3 - 1, rel=1e-6)
    assert not x.stopped


def test_trailing_stop_from_the_highest_close() -> None:
    closes = [100, 110, 120, 107, 100]
    x = R.EXITS["trail_10"](path(closes))
    assert x.stopped and x.days == 4  # 107 <= 120 x 0.9 = 108: sold at the next open (107)


def test_entry_methods() -> None:
    gap = path([104] * 70, opens=[104] * 70, signal=100.0)
    assert R.ENTRIES["limit_1pct_skip_gap_3pct"](gap).filled == 0.0  # opened 4% higher: skipped
    dip = path([100, 98, 96.5] + [100] * 70, opens=[100, 99, 97] + [100] * 70, signal=100.0)
    f = R.ENTRIES["wait_for_3pct_dip"](dip)
    assert f.filled == 1.0 and f.ret63 > 0
    assert R.ENTRIES["next_open"](path([100] * 70)).ret63 == pytest.approx(0)


def test_signals_top_2_percent_and_a_random_control(tmp_path: Path) -> None:
    dates = pd.to_datetime(["2016-01-29"] * 200 + ["2024-01-31"] * 10)
    oos = pd.DataFrame(
        {
            "date": dates,
            "ticker": [f"T{i}" for i in range(210)],
            "regime": "Normal",
            "log_adv": 18.0,
            "l1_ridge": np.arange(210.0),
            "l1_lgbm": np.arange(210.0),
        }
    )
    s = R.signals(oos)
    model = s[s["set"] == "model"]
    assert (
        set(model["ticker"]) == {"T196", "T197", "T198", "T199"}
        and (s["date"].dt.year <= 2023).all()
    )
    assert (s["set"] == "control").sum() == R.CONTROL_PER_MONTH


def test_no_signal_reads_a_price_from_2024() -> None:
    idx = pd.bdate_range("2023-06-01", "2024-03-29")
    m = pd.DataFrame({"AAA": 100.0}, index=idx)
    sig = pd.DataFrame(
        {
            "date": pd.to_datetime(["2023-06-30", "2023-11-30"]),
            "ticker": "AAA",
            "regime": "Normal",
            "log_adv": 18.0,
            "set": "model",
        }
    )
    ps = R.paths(sig, m, m * 1.01, m * 0.99, m)
    assert [meta["date"].month for meta, _ in ps] == [6]  # November's window would end in 2024


def test_decision_follows_the_fixed_protocol() -> None:
    def table(scores: dict[str, float]) -> dict[str, dict[str, float]]:
        return {k: {"n": 10, "score": v, "mean": v} for k, v in scores.items()}

    base = {k: 0.0 for k in R.EXITS}
    res = {
        "exits": {
            "model": table({**base, "atr_2": 0.05}),
            "halves": {"a": table({**base, "atr_2": 0.04}), "b": table({**base, "atr_2": 0.01})},
        },
        "entries": {
            "model": table({m: 0.01 for m in R.ENTRIES}),
            "halves": {
                "a": table({m: 0.01 for m in R.ENTRIES}),
                "b": table({m: 0.01 for m in R.ENTRIES}),
            },
        },
    }
    d = R.decide(res)
    assert d["exit"] == "atr_2" and d["entry"] == "next_open"
    # Not in the top 3 of one half: the simplest rule stays.
    res["exits"]["halves"]["b"] = table({**base, "atr_2": -0.5})
    assert R.decide(res)["exit"] == "hold_63"


def test_experiment_log_counts_every_try_and_a_protocol_runs_once(tmp_path: Path) -> None:
    assert not X.already_run(tmp_path, "p1", "d1")
    X.record(
        tmp_path,
        {"experiment": "x", "protocol_id": "p1", "protocol_digest": "d1", "status": "failed"},
    )
    assert not X.already_run(
        tmp_path, "p1", "d1"
    )  # a failed try does not count as run, but is kept
    X.record(
        tmp_path,
        {"experiment": "x", "protocol_id": "p1", "protocol_digest": "d1", "status": "done"},
    )
    assert X.already_run(tmp_path, "p1", "d1")
    out = X.export(tmp_path)
    assert out["verified"] and out["count"] == 2 and out["experiments"][0]["status"] == "done"
