from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from convergealpha.sources import prices as P


def rows(
    ticker: str, dates: list[str], closes: list[float], basis: str, **extra: list[float]
) -> pd.DataFrame:
    n = len(dates)
    df = pd.DataFrame(
        {
            "ticker": ticker,
            "date": pd.to_datetime(dates),
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": extra.get("volume", [1000.0] * n),
            "dividend": extra.get("dividend", [0.0] * n),
            "split": extra.get("split", [0.0] * n),
            "basis": pd.Timestamp(basis),
        }
    )
    return df


def test_split_after_backfill_is_applied_using_basis_day() -> None:
    # Backfill on Oct 2 (pre-split basis), 2:1 split on Oct 5, daily rows downloaded after it.
    hist = rows(
        "X", ["2026-10-01", "2026-10-02"], [100.0, 102.0], "2026-10-02", volume=[10.0, 10.0]
    )
    daily = rows("X", ["2026-10-05", "2026-10-06"], [51.5, 52.0], "2026-10-06", split=[2.0, 0.0])
    panel = P.build_panel(pd.concat([hist, daily]))
    c = panel.close["X"]
    assert c.loc["2026-10-01"] == pytest.approx(50.0)
    assert c.loc["2026-10-02"] == pytest.approx(51.0)
    assert c.loc["2026-10-05"] == pytest.approx(51.5)
    assert panel.volume["X"].loc["2026-10-01"] == pytest.approx(20.0)
    # Returns are continuous across the split.
    assert panel.tr["X"].loc["2026-10-05"] / panel.tr["X"].loc["2026-10-02"] - 1 == pytest.approx(
        51.5 / 51 - 1
    )


def test_split_already_in_basis_is_not_applied_twice() -> None:
    # Downloaded after the split: Yahoo already adjusted history; the split row is informational.
    hist = rows("X", ["2026-10-02", "2026-10-05"], [51.0, 51.5], "2026-10-07", split=[0.0, 2.0])
    panel = P.build_panel(hist)
    assert panel.close["X"].loc["2026-10-02"] == pytest.approx(51.0)


def test_total_return_includes_dividends() -> None:
    df = rows("D", ["2026-10-01", "2026-10-02"], [100.0, 99.0], "2026-10-02", dividend=[0.0, 2.0])
    panel = P.build_panel(df)
    assert panel.tr["D"].loc["2026-10-02"] == pytest.approx(1.01)


def test_latest_download_wins_for_duplicates() -> None:
    a = rows("X", ["2026-10-01"], [100.0], "2026-10-01")
    b = rows("X", ["2026-10-01"], [100.5], "2026-10-02")  # Yahoo revised the bar
    assert P.build_panel(pd.concat([a, b])).close["X"].iloc[0] == pytest.approx(100.5)


def test_non_trading_days_are_dropped() -> None:
    df = rows("^VIX", ["2026-09-04", "2026-09-07", "2026-09-08"], [15.0, 15.3, 15.1], "2026-09-08")
    panel = P.build_panel(df)
    assert pd.Timestamp("2026-09-07") not in panel.close.index  # Labor Day


def test_finalize_drops_unfinished_bar_and_bad_prices() -> None:
    raw = rows(
        "X", ["2026-10-08", "2026-10-09", "2026-10-12"], [10.0, 0.0, 11.0], "2026-10-12"
    ).drop(columns="basis")
    # Monday Oct 12, 11:30 New York: today's bar is not final yet.
    now = datetime(2026, 10, 12, 15, 30, tzinfo=UTC)
    out = P.finalize_rows(raw, now)
    assert out["date"].max() == pd.Timestamp(
        "2026-10-08"
    )  # zero price on Oct 9 removed, Oct 12 unfinished
    assert (out["basis"] == pd.Timestamp("2026-10-12")).all()
    # After 16:15 New York the bar is final.
    later = P.finalize_rows(raw, datetime(2026, 10, 12, 20, 30, tzinfo=UTC))
    assert later["date"].max() == pd.Timestamp("2026-10-12")


def test_no_stored_bar_is_after_its_decision_time(tmp_path: Path) -> None:
    """Leakage guard: a bar dated D may only exist if it was downloaded after D's close."""
    raw = rows("X", ["2026-10-09", "2026-10-12"], [10.0, 11.0], "2026-10-12").drop(columns="basis")
    out = P.finalize_rows(raw, datetime(2026, 10, 12, 15, 0, tzinfo=UTC))
    P.write_daily(tmp_path, out, date(2026, 10, 12))
    stored = P.load_rows(tmp_path)
    assert (pd.to_datetime(stored["date"]) <= pd.to_datetime(stored["basis"])).all()
    assert pd.Timestamp("2026-10-12") not in set(pd.to_datetime(stored["date"]))


def test_storage_is_append_only(tmp_path: Path) -> None:
    df = rows("X", ["2026-10-01"], [10.0], "2026-10-01")
    a = P.write_history_chunk(tmp_path, df, date(2026, 10, 1), "backfill")
    b = P.write_history_chunk(tmp_path, df, date(2026, 10, 1), "backfill")
    assert a != b and a is not None and b is not None and a.exists() and b.exists()
    P.write_daily(tmp_path, rows("X", ["2026-10-02"], [11.0], "2026-10-02"), date(2026, 10, 2))
    P.write_daily(
        tmp_path,
        rows("X", ["2026-10-02", "2026-10-05"], [11.0, 12.0], "2026-10-05"),
        date(2026, 10, 2),
    )
    daily = pd.read_parquet(tmp_path / "prices" / "daily" / "2026" / "20261002.parquet")
    assert len(daily) == 2  # the duplicate Oct 2 row was not added twice


def test_unexplained_adjustment_triggers_repair() -> None:
    stored = rows("X", ["2026-10-01", "2026-10-02"], [100.0, 102.0], "2026-10-02")
    stored = pd.concat(
        [stored, rows("Y", ["2026-10-01", "2026-10-02"], [50.0, 50.0], "2026-10-02")]
    )
    panel = P.build_panel(stored)
    fresh = pd.concat(
        [
            # X: Yahoo now shows history halved but reports no split -> repair.
            rows("X", ["2026-10-02", "2026-10-05"], [51.0, 52.0], "2026-10-05"),
            # Y: consistent with what we stored.
            rows("Y", ["2026-10-02", "2026-10-05"], [50.0, 50.5], "2026-10-05"),
        ]
    )
    assert P.unexplained_adjustments(panel, fresh) == ["X"]
    # With the split reported, the halving is explained.
    fresh_ok = rows("X", ["2026-10-02", "2026-10-05"], [51.0, 52.0], "2026-10-05", split=[0.0, 2.0])
    assert P.unexplained_adjustments(panel, fresh_ok) == []


def test_plan_update_routes_stale_and_new_tickers_to_full_download() -> None:
    panel = P.build_panel(
        pd.concat(
            [
                rows("FRESH", ["2026-10-08", "2026-10-09"], [1.0, 1.0], "2026-10-09"),
                rows("STALE", ["2026-08-03", "2026-08-04"], [1.0, 1.0], "2026-08-04"),
            ]
        )
    )
    inc, full = P.plan_update(panel, ["FRESH", "STALE", "NEW"], date(2026, 10, 12))
    assert inc == ["FRESH"]
    assert sorted(full) == ["NEW", "STALE"]
    assert not np.isnan(panel.close["FRESH"].iloc[-1])
