"""Plain answers: why a stock moved today, what is in the price, and the distress check."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from convergealpha.decide import rules as R
from convergealpha.features import explain as EX
from convergealpha.features.news import tag

DAY = pd.Timestamp("2026-10-14")


def table() -> pd.DataFrame:
    t = pd.DataFrame(
        {
            "change_1d": [-0.06, -0.02, -0.02, 0.01, -0.02, 0.0],
            "sector": ["Tech"] * 5 + ["Energy"],
            "eligible": True,
            "cik": [1, 2, 3, 4, 5, 6],
        },
        index=pd.Index(["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"], name="ticker"),
    )
    return t


def test_a_move_is_split_into_market_sector_and_own_part_with_its_news() -> None:
    news = pd.DataFrame({"ticker": ["AAA", "AAA", "AAA"], "datetime": [DAY + pd.Timedelta(hours=14), DAY + pd.Timedelta(hours=15), DAY - pd.Timedelta(days=1)], "headline": ["AAA cuts its guidance", "If you own SPY, this fund beats Acme and AAA", "old news"], "source": "Reuters", "url": "u"})  # fmt: skip
    filings = pd.DataFrame(
        {"cik": [2], "form": ["8-K"], "filing_date": [DAY], "items": ["5.02,9.01"]}
    )
    out = EX.why_move(table(), news, filings, DAY, spy_move=-0.01)
    a = out["AAA"]
    # Tech's median move is -2%: market -1%, sector -1% beyond it, AAA's own part -4%.
    assert a["market"] == pytest.approx(-0.01) and a["sector"] == pytest.approx(-0.01) and a["own"] == pytest.approx(-0.04)  # fmt: skip
    assert (
        "News: AAA cuts its guidance" in a["text"] and len(a["news"]) == 1
    )  # not the article that only mentions it
    assert "Filing: Director or officer change" in out["BBB"]["text"]
    assert out["DDD"]["text"].endswith(
        "No public reason found in the news and filings the app reads."
    )


def test_valuation_is_a_sector_percentile() -> None:
    t = table().assign(fcf_yield=[0.10, 0.05, 0.02, 0.01, -0.01, 0.03], net_income_ttm=[10, 5, 2, 1, -1, 3], market_cap=100.0)  # fmt: skip
    v = EX.valuation(t)
    assert v.at["AAA", "value_pct"] == 100 and v.at["AAA", "value_view"] == "cheap for its sector"
    assert v.at["EEE", "value_view"] == "expensive for its sector"
    assert pd.isna(v.at["FFF", "value_pct"])  # one Energy stock: no sector comparison


def test_distress_flags_and_levels() -> None:
    t = table().assign(
        assets=[100, 100, 100, np.nan, 100, 100], liabilities=[95, 50, 50, np.nan, 50, 50],
        equity=[5, 50, -1, np.nan, 50, 50], cash=[1, 50, 50, np.nan, 50, 50],
        fcf_ttm=[-10, 5, 5, np.nan, 5, 5], debt_ebitda=[20.0, 1, 1, np.nan, 1, 1],
        news_negative_tags=[None, None, None, None, "going_concern", None], late_filing=False,
    )  # fmt: skip
    bank = t.assign(sector="Financials").loc[["AAA"]].assign(fcf_ttm=5.0, debt_ebitda=1.0)
    assert EX.distress(bank).at["AAA", "distress"] == "low"  # 95% liabilities is normal for a bank
    filings = pd.DataFrame({"cik": [6], "form": ["8-K"], "filing_date": [DAY - pd.Timedelta(days=5)], "items": ["3.01"]})  # fmt: skip
    d = EX.distress(t, filings, DAY)
    assert (
        d.at["AAA", "distress"] == "high"
    )  # liabilities 95%, cash < burn, debt with negative EBITDA
    assert d.at["BBB", "distress"] == "low" and d.at["CCC", "distress"] == "elevated"
    assert pd.isna(d.at["DDD", "distress"])  # no company data
    assert d.at["EEE", "distress"] == "high" and "going-concern" in d.at["EEE", "distress_why"]
    assert d.at["FFF", "distress"] == "high" and "delisting" in d.at["FFF", "distress_why"]


def test_bankruptcy_and_delisting_block_new_buys_and_ceo_exits_are_tagged() -> None:
    t = pd.DataFrame({"bankruptcy_filed": [True, False], "delisting_notice": [False, True]}, index=["X", "Y"])  # fmt: skip
    b = R.blocking_events(t)
    assert b["X"] == ["bankruptcy or receivership filed (8-K 1.03)"] and b["Y"] == ["delisting notice (8-K 3.01)"]  # fmt: skip
    assert ("ceo_exit", -1) in tag("Acme CEO John Smith steps down effective immediately")
    assert ("ceo_exit", -1) not in tag("Acme names new CEO")
