import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from convergealpha.export import site
from convergealpha.features import price_features as PF
from convergealpha.sources import prices as P
from convergealpha.util.calendar import add_trading_days
from convergealpha.util.io import stock_file_stem


def synthetic_panel(n: int = 300) -> P.Panel:
    start = pd.Timestamp("2025-06-02").date()
    dates = [pd.Timestamp(add_trading_days(start, i)) for i in range(n)]
    up = 20.0 * (1.001 ** np.arange(n))  # steady riser, liquid
    flat = np.full(n, 3.0)  # penny stock
    frames = []
    for ticker, closes, vol in (("UP", up, 2_000_000.0), ("PENNY", flat, 10_000.0)):
        frames.append(
            pd.DataFrame(
                {
                    "ticker": ticker,
                    "date": dates,
                    "open": closes,
                    "high": closes * 1.02,
                    "low": closes * 0.98,
                    "close": closes,
                    "volume": vol,
                    "dividend": 0.0,
                    "split": 0.0,
                    "basis": dates[-1],
                }
            )
        )
    return P.build_panel(pd.concat(frames, ignore_index=True))


def test_snapshot_returns_trend_and_eligibility() -> None:
    snap = PF.snapshot(synthetic_panel())
    up = snap.loc["UP"]
    assert up["ret_1m"] == pytest.approx(1.001**21 - 1, rel=1e-6)
    assert up["ret_1y"] == pytest.approx(1.001**252 - 1, rel=1e-6)
    assert bool(up["trend_up"]) is True
    assert up["dist_52w_high"] == pytest.approx(1 / 1.02 - 1, rel=1e-4)
    assert up["atr_pct"] == pytest.approx(0.04, abs=0.004)
    assert bool(up["eligible"]) is True  # price >= $5 and ADV >= $10M
    assert bool(snap.loc["PENNY", "eligible"]) is False
    assert snap.loc["PENNY", "vol_63"] == pytest.approx(0.0)


def test_screener_is_columnar_and_nan_free(tmp_path: Path) -> None:
    table = pd.DataFrame(
        {
            "name": ["A Inc", "B Inc"],
            "price": [12.3456, np.nan],
            "ret_1m": [0.123456, np.inf],
            "eligible": [True, False],
        },
        index=pd.Index(["A", "B"], name="ticker"),
    )
    path = site.write_screener(
        tmp_path,
        table,
        ["ticker", "name", "price", "ret_1m", "eligible", "missing_field"],
        "2026-10-09",
        datetime(2026, 10, 12, tzinfo=UTC),
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["fields"] == ["ticker", "name", "price", "ret_1m", "eligible"]
    assert data["rows"][0] == ["A", "A Inc", 12.35, 0.1235, True]
    assert data["rows"][1] == ["B", "B Inc", None, None, False]
    assert "NaN" not in path.read_text(encoding="utf-8")


def test_windows_reserved_names_get_a_suffix() -> None:
    assert stock_file_stem("CON") == "CON_"
    assert stock_file_stem("AAPL") == "AAPL"
    assert stock_file_stem("COM1") == "COM1_"


def test_chart_series_is_compact() -> None:
    chart = PF.chart_series(synthetic_panel(), "UP", daily_sessions=10)
    daily = chart["daily"]
    assert isinstance(daily, dict)
    assert len(daily["t"]) == 10 and len(daily["c"]) == 10
    assert daily["t"][-1] > daily["t"][0]
