from datetime import date

import pandas as pd

from convergealpha.sources import universe as U


def _nasdaq(rows: list[tuple[str, str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Symbol": s,
                "Security Name": n,
                "Market Category": "Q",
                "Test Issue": t,
                "Financial Status": "N",
                "Round Lot Size": "100",
                "ETF": e,
                "NextShares": "N",
            }
            for s, n, e, t in rows
        ]
    )


def _other(rows: list[tuple[str, str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ACT Symbol": s,
                "Security Name": n,
                "Exchange": x,
                "CQS Symbol": s,
                "ETF": e,
                "Round Lot Size": "100",
                "Test Issue": "N",
                "NASDAQ Symbol": s,
            }
            for s, n, x, e in rows
        ]
    )


SEC = pd.DataFrame(
    [
        [320193, "Apple Inc.", "AAPL", "Nasdaq"],
        [1067983, "BERKSHIRE HATHAWAY INC", "BRK-B", "NYSE"],
        [1046179, "TSMC", "TSM", "NYSE"],
    ],
    columns=["cik", "name", "ticker", "exchange"],
)


def build() -> pd.DataFrame:
    nasdaq = _nasdaq(
        [
            ("AAPL", "Apple Inc. - Common Stock", "N", "N"),
            ("QQQ", "Invesco QQQ Trust", "Y", "N"),
            ("ZXZZT", "NASDAQ TEST STOCK", "N", "Y"),
            ("ABCDW", "Abcd Corp - Warrant", "N", "N"),
            ("SPCX", "Space Acquisition Corp. - Class A Ordinary Shares", "N", "N"),
        ]
    )
    other = _other(
        [
            ("BRK.B", "Berkshire Hathaway Inc. New Common Stock", "N", "N"),
            ("BAC.PL", "Bank of America Corp 7.25% Non-Cumulative Perpetual Pfd Ser L", "N", "N"),
            ("EVV", "Eaton Vance Limited Duration Income Fund Common Shares", "A", "N"),
            (
                "TSM",
                "Taiwan Semiconductor American Depositary Shares, each representing 5 shares",
                "N",
                "N",
            ),
            ("ARCX", "Some Arca Listed Common Stock", "P", "N"),
            ("SPY", "SPDR S&P 500 ETF Trust", "P", "Y"),
        ]
    )
    return U.build_universe(nasdaq, other, SEC)


def test_filters_keep_only_common_stocks() -> None:
    u = build().set_index("ticker")
    kept = set(u.index[u["excluded_reason"].isna()])
    assert kept == {"AAPL", "BRK-B", "TSM"}
    assert u.loc["ABCDW", "excluded_reason"] == "not common stock"
    assert u.loc["BAC-PL", "excluded_reason"] == "not common stock"
    assert u.loc["EVV", "excluded_reason"] == "not common stock"
    assert u.loc["SPCX", "excluded_reason"] == "blank-check (SPAC)"
    assert "QQQ" not in u.index and "ZXZZT" not in u.index and "ARCX" not in u.index


def test_adrs_are_kept_and_flagged_and_ciks_joined() -> None:
    u = build().set_index("ticker")
    assert bool(u.loc["TSM", "is_adr"]) is True
    assert bool(u.loc["AAPL", "is_adr"]) is False
    assert u.loc["BRK-B", "cik"] == 1067983
    assert u.loc["BRK-B", "exchange"] == "NYSE"


def test_yahoo_symbols() -> None:
    assert U.yahoo_symbol("BRK.B") == "BRK-B"
    assert U.yahoo_symbol("bf/b") == "BF-B"


def test_history_never_forgets_a_ticker() -> None:
    day1 = U.merge_history(None, build(), date(2026, 10, 1))
    today = build()
    today = today[today["ticker"] != "TSM"]
    day2 = U.merge_history(day1, today, date(2026, 10, 2)).set_index("ticker")
    assert bool(day2.loc["TSM", "active"]) is False
    assert pd.Timestamp(day2.loc["TSM", "last_seen"]).date() == date(
        2026, 10, 2
    )  # the day it disappeared
    assert day2.loc["AAPL", "first_seen"] == date(2026, 10, 1)
    assert pd.isna(day2.loc["AAPL", "last_seen"])  # still listed
    assert len(U.active_stocks(day2.reset_index())) == 2
