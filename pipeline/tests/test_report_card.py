"""The live report card: published forecasts against what really happened, losers included, only
once the horizon has passed; and the public monthly forecast archive."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from convergealpha.ledger import report_card as RC

DAYS = pd.bdate_range("2026-10-01", periods=40)


def snap(data: Path, day: pd.Timestamp, p1w: dict[str, float], eligible: bool = True) -> None:
    d = data / "snapshots" / f"{day:%Y}" / f"{day:%Y%m%d}"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({
        "ticker": list(p1w), "p_up_1w": list(p1w.values()), "p_up_1m": 0.55, "p_up_3m": np.nan,
        "p_up_6m": 0.6, "eligible": eligible, "label": "NO TRADE",
    }).to_parquet(d / "scores.parquet")  # fmt: skip
    # A same-day re-run's file is not the published forecast: it is ignored.
    pd.DataFrame({"ticker": list(p1w), "p_up_1w": 0.99, "eligible": True}).to_parquet(d / "scores-221332.parquet")  # fmt: skip


def tr(up: list[str], down: list[str]) -> pd.DataFrame:
    n = len(DAYS)
    cols = {t: np.linspace(100, 110, n) for t in up} | {t: np.linspace(100, 90, n) for t in down}
    return pd.DataFrame(cols, index=DAYS)


def test_only_finished_horizons_are_scored_and_losers_count(tmp_path: Path) -> None:
    ups = [f"U{i}" for i in range(20)]
    downs = [f"D{i}" for i in range(20)]
    snap(tmp_path, DAYS[0], {**{t: 0.7 for t in ups}, **{t: 0.7 for t in downs[:10]}, **{t: 0.3 for t in downs[10:]}})  # fmt: skip
    total = tr(ups, downs)
    early = RC.export(tmp_path, total, DAYS[4], {"1w": 0.56})
    assert early["horizons"]["1w"]["n"] == 0  # 5 trading days have not passed yet
    out = RC.export(tmp_path, total, DAYS[5], {"1w": 0.56, "1m": 0.58})
    w = out["horizons"]["1w"]
    assert w["n"] == 40 and w["days"] == 1 and w["enough"]
    # We said 70% for 30 stocks: 20 rose (67%); we said 30% for 10: none rose.
    assert w["confident_up"]["n"] == 30 and w["confident_up"]["rate"] == pytest.approx(20 / 30)
    assert w["confident_down"]["n"] == 10 and w["confident_down"]["rate"] == 1.0
    assert w["brier"] == pytest.approx((20 * 0.09 + 10 * 0.49 + 10 * 0.09) / 40)
    assert w["skill"] == pytest.approx(1 - w["brier"] / ((20 * 0.44**2 + 20 * 0.56**2) / 40))
    assert out["horizons"]["1m"]["n"] == 0 and out["horizons"]["3m"]["n"] == 0
    assert out["first_result"]["1w"] == "2026-10-08" and out["since"] == "2026-10-01"


def test_ineligible_stocks_and_rerun_files_are_left_out(tmp_path: Path) -> None:
    snap(tmp_path, DAYS[0], {"A": 0.7})
    snap(tmp_path, DAYS[1], {"B": 0.7}, eligible=False)
    df = RC.outcomes(tmp_path, tr(["A", "B"], []), DAYS[30])
    assert set(df["ticker"]) == {"A"} and set(df["horizon"]) == {"1w", "1m"}
    assert df[df["horizon"] == "1w"]["p_up"].tolist() == [0.7]  # not the re-run's 0.99


def test_monthly_archive_keeps_every_published_forecast(tmp_path: Path) -> None:
    snap(tmp_path, DAYS[0], {"A": 0.583, "B": 0.4})
    snap(tmp_path, DAYS[25], {"A": 0.5})  # November
    arc = RC.archive(tmp_path)
    assert set(arc) == {"2026-10", "2026-11"}
    oct_ = arc["2026-10"]
    assert oct_["fields"] == ["ticker", "p_up_1w", "p_up_1m", "p_up_3m", "p_up_6m", "label"]
    assert oct_["days"]["2026-10-01"][0] == ["A", 583, 550, None, 600, ""]  # "" = NO TRADE
    assert oct_["labels"][""] == "NO TRADE" and oct_["labels"]["X"] == "SELL / RISK WARNING"


def test_live_correction_follows_its_fixed_rule() -> None:
    from convergealpha.models import live_calibration as LC

    # 1-week forecasts on 30 days = 6 independent weeks: the app said 60% on average, 45% rose.
    rows = [(f"2026-10-{d:02d}", f"T{i}", "1w", 0.6, 0.01 if i < 45 else -0.01) for d in range(1, 31) for i in range(100)]  # fmt: skip
    df = pd.DataFrame(rows, columns=["day", "ticker", "horizon", "p_up", "ret"])
    c = LC.fit(df)
    w = c["1w"]
    gap = np.log(0.45 / 0.55) - np.log(0.6 / 0.4)
    assert w["active"] and w["periods"] == 6 and w["weight"] == pytest.approx(6 / 32)
    assert w["shift"] == pytest.approx(6 / 32 * gap)
    assert not c["1m"]["active"] and c["1m"]["shift"] == 0  # 30 days is not 4 months yet
    p = np.array([0.6, 0.7, np.nan])
    q = LC.apply(p, w["shift"])
    assert q[0] < 0.6 and q[1] < 0.7 and q[0] < q[1] and np.isnan(q[2])  # same order, less sure
    assert LC.apply(p, 0.0) is p
    # A huge gap is capped.
    big = LC.fit(df.assign(p_up=0.98))
    assert big["1w"]["shift"] >= -LC.CAP
