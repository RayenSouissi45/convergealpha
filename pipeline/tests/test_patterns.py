"""Event-pattern engine: the luck test and the per-event history used by the opportunity badge."""

import numpy as np
import pandas as pd

from convergealpha.models import dataset as D
from convergealpha.models import patterns as PT
from convergealpha.sources.prices import Panel


def _history(drift_after_gap: float, seed: int = 5, close_jump: bool = True) -> D.History:
    """Two stocks, 2012-2026. AAA gaps up on heavy volume every ~60 sessions and then drifts."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2012-01-02", "2026-09-30")
    n = len(idx)
    close = {}
    opens = {}
    vol = {}
    for t in ("AAA", "BBB"):
        r = rng.normal(0.0002, 0.01, n)
        v = np.full(n, 1e6)
        gaps = np.zeros(n, dtype=bool)
        if t == "AAA":
            for k in range(100, n - 30, 60):
                gaps[k] = True
                r[k] += 0.06 if close_jump else 0.0  # the close jumps too (or the gap fades)
                v[k] = 3e6
                r[k + 1 : k + 21] += drift_after_gap / 20
        c = 100 * np.cumprod(1 + r)
        o = np.r_[c[0], c[:-1]] * np.where(gaps, 1.057, 1.0)
        close[t], opens[t], vol[t] = c, o, v
    cl = pd.DataFrame(close, index=idx)
    op = pd.DataFrame(opens, index=idx)
    panel = Panel(
        open=op, high=cl, low=cl, close=cl, volume=pd.DataFrame(vol, index=idx),
        dividend=pd.DataFrame(0.0, index=idx, columns=cl.columns), tr=cl / cl.iloc[0],
        split_events=pd.DataFrame(columns=["ticker", "date", "ratio"]),
    )  # fmt: skip
    stocks = pd.DataFrame(
        {"sector": ["Tech", "Tech"], "industry_group": ["357", "357"], "cik": [1, 2]},
        index=["AAA", "BBB"],
    )
    empty = pd.DataFrame()
    return D.History(
        panel, stocks, empty, empty, pd.DataFrame(), empty,
        pd.DataFrame(columns=["cik", "end", "known", "sue"]), empty, empty, empty,
    )  # fmt: skip


def test_history_records_every_tested_event_type() -> None:
    h = _history(drift_after_gap=0.05)
    out = PT.run(h, h.stocks)
    rec = out["history"]["stock"]["AAA"]["Gap up ≥ 5% on heavy volume"]["21 trading days"]
    assert rec["n"] >= PT.MIN_STOCK
    # Returns are measured from the first tradable open after the event: the drift is caught.
    assert rec["mean_return"] > 0.02 and rec["up_rate"] > 0.6
    assert rec["passed"] is True and rec["mean_excess"] > 0
    assert out["groups"]["AAA"] == "357"


def test_history_keeps_failed_patterns_too() -> None:
    # A gap that fades the same day, then no drift: nothing to find. The record exists anyway.
    h = _history(drift_after_gap=0.0, seed=11, close_jump=False)
    out = PT.run(h, h.stocks)
    rec = out["history"]["stock"]["AAA"]["Gap up ≥ 5% on heavy volume"]["21 trading days"]
    assert rec["n"] >= PT.MIN_STOCK
    assert rec["passed"] is False
    assert "Gap up ≥ 5% on heavy volume" not in {
        p["event"] for p in out["by_ticker"].get("AAA", {}).get("passed", [])
    }
