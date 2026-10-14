"""Long market history for the goal planner: the French data library format and inflation."""

from __future__ import annotations

import pandas as pd
import pytest

from convergealpha.sources import history as H

SAMPLE = "\n".join(
    [
        "This file was created using the 202608 CRSP database.",
        "",
        ",Mkt-RF,SMB,HML,RF",
        "192607,   2.89,  -2.42,  -2.75,   0.22",
        "192608,   2.64,  -1.44,   4.13,   0.25",
        "",
        " Annual Factors: January-December ",
        ",Mkt-RF,SMB,HML,RF",
        "  1927,  29.47,  -2.04,  -3.65,   3.12",
    ]
)


def test_monthly_block_only_market_is_mkt_rf_plus_rf() -> None:
    df = H.parse_french(SAMPLE)
    assert list(df["month"]) == ["1926-07", "1926-08"]
    assert df["market"].iloc[0] == pytest.approx((2.89 + 0.22) / 100)
    assert df["rf"].iloc[1] == pytest.approx(0.0025)


def test_inflation_from_cpi_levels() -> None:
    cpi = pd.Series(
        [100.0, 101.0, 100.0], index=pd.to_datetime(["1926-06-01", "1926-07-01", "1926-08-01"])
    )
    infl = H.inflation_from_cpi(cpi)
    assert infl["1926-07"] == pytest.approx(0.01) and infl["1926-08"] == pytest.approx(-1 / 101)


def test_export_keeps_months_aligned_and_missing_inflation_as_null() -> None:
    df = H.parse_french(SAMPLE)
    df["inflation"] = [0.01, None]
    out = H.export(df)
    assert out["months"] == ["1926-07", "1926-08"]
    assert out["inflation"] == [0.01, None] and len(out["market"]) == 2
