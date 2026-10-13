"""'How often was it right?' tables, the finanzen.net zero list, and the live Picks race."""

import io
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from convergealpha.config import SPY
from convergealpha.ledger import monitor as MON
from convergealpha.models import reliability as RL
from convergealpha.sources import brokers as B

# --------------------------------------------------------------------------- reliability


def test_buckets_hold_at_least_200_cases_with_wilson_ranges() -> None:
    rng = np.random.default_rng(1)
    p = np.concatenate([rng.uniform(0.40, 0.70, 5000), [0.95] * 30])  # few extreme cases
    y = (rng.uniform(size=len(p)) < p).astype(float)
    tab = RL.table(p, y)
    assert all(b["n"] >= RL.MIN_CASES for b in tab)
    assert sum(b["n"] for b in tab) == len(p)
    assert tab[0]["lo"] == 0.0 and tab[-1]["hi"] == 1.01
    for a, b in zip(tab[:-1], tab[1:], strict=True):
        assert a["hi"] == b["lo"]  # no gaps
    for b in tab:
        assert b["wilson_lo"] <= b["rate"] <= b["wilson_hi"]
    # The 30 cases at 0.95 cannot stand alone: they join the bucket below.
    assert tab[-1]["lo"] < 0.95 <= tab[-1]["hi"]


def test_lookup_returns_the_bucket_of_a_probability() -> None:
    tab = [
        {"lo": 0.0, "hi": 0.55, "n": 300, "rate": 0.5, "wilson_lo": 0.44, "wilson_hi": 0.56},
        {"lo": 0.55, "hi": 1.01, "n": 400, "rate": 0.6, "wilson_lo": 0.55, "wilson_hi": 0.65},
    ]
    got = RL.lookup(tab, 0.57)
    assert got == {"rate": 0.6, "lo": 0.55, "hi": 0.65, "n": 400, "p_lo": 0.55, "p_hi": 1.0}
    assert RL.lookup(tab, 0.55)["rate"] == 0.6
    assert RL.lookup(tab, float("nan")) is None
    assert RL.lookup(None, 0.5) is None


def test_crossfit_never_calibrates_a_year_on_itself() -> None:
    # Year 2020: the raw score is inversely related to the outcome; other years: positively.
    rng = np.random.default_rng(2)
    n = 3000
    years = np.repeat([2018, 2019, 2020], n)
    raw = rng.uniform(size=3 * n)
    y = np.where(years == 2020, raw < 0.5, raw > 0.5).astype(float)
    p = RL.crossfit(raw, y, years, min_bin=200)
    hi_2020 = p[(years == 2020) & (raw > 0.8)]
    # Fitted on 2018-2019 only, so a high score in 2020 still gets a high probability...
    assert hi_2020.mean() > 0.8
    # ...and the bucket's actual hit rate for 2020 reveals it was wrong.
    tab = RL.table(p[years == 2020], y[years == 2020])
    assert tab[-1]["rate"] < 0.2


def test_build_uses_every_horizon_and_kind() -> None:
    rng = np.random.default_rng(3)
    n = 4000
    oos = pd.DataFrame({"date": pd.to_datetime(rng.choice(["2017-06-30", "2019-06-28"], n))})
    for h in ("1w", "1m", "3m", "6m"):
        for k in ("up", "beat"):
            oos[f"raw_{k}_{h}"] = rng.uniform(size=n)
            oos[f"{k}_{h}"] = (rng.uniform(size=n) < oos[f"raw_{k}_{h}"]).astype(float)
    rel = RL.build(oos)
    assert set(rel["horizons"]) == {"1w", "1m", "3m", "6m"}
    assert set(rel["horizons"]["6m"]) == {"up", "beat"}
    assert rel["years"] == [2017, 2019]


# --------------------------------------------------------------------------- broker list


def test_isin_check_digit_and_cusip() -> None:
    assert B.isin_valid("US0378331005")  # Apple
    assert B.isin_valid("CA82509L1076")  # Shopify
    assert B.isin_valid("DE0007164600")  # SAP
    assert not B.isin_valid("US0378331006")
    assert not B.isin_valid("US03783310")
    assert B.us_isin("037833100") == "US0378331005"
    assert B.normalize_ticker("BRK/B") == "BRK-B"


FIRDS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<BizData xmlns="urn:iso:std:iso:20022:tech:xsd:head.003.001.01"><Pyld>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:auth.017.001.02"><FinInstrmRptgRefDataRpt>
<RefData><FinInstrmGnlAttrbts><Id>US0378331005</Id><FullNm>APPLE INC.</FullNm>
<ClssfctnTp>ESVUFR</ClssfctnTp><NtnlCcy>USD</NtnlCcy></FinInstrmGnlAttrbts>
<TradgVnRltdAttrbts><Id>MUND</Id><FrstTradDt>2014-01-02T06:00:00Z</FrstTradDt></TradgVnRltdAttrbts></RefData>
<RefData><FinInstrmGnlAttrbts><Id>US0378331005</Id><FullNm>APPLE INC.</FullNm>
<ClssfctnTp>ESVUFR</ClssfctnTp><NtnlCcy>EUR</NtnlCcy></FinInstrmGnlAttrbts>
<TradgVnRltdAttrbts><Id>XETR</Id></TradgVnRltdAttrbts></RefData>
<RefData><FinInstrmGnlAttrbts><Id>US1234567890</Id><FullNm>GONE CORP</FullNm>
<ClssfctnTp>ESVUFR</ClssfctnTp><NtnlCcy>USD</NtnlCcy></FinInstrmGnlAttrbts>
<TradgVnRltdAttrbts><Id>MUND</Id><TermntnDt>2026-01-05T00:00:00Z</TermntnDt></TradgVnRltdAttrbts></RefData>
<RefData><FinInstrmGnlAttrbts><Id>US03027X1000</Id><FullNm>AMERICAN TOWER DL -,01</FullNm>
<ClssfctnTp>CBOJXS</ClssfctnTp><NtnlCcy>EUR</NtnlCcy></FinInstrmGnlAttrbts>
<TradgVnRltdAttrbts><Id>MUND</Id></TradgVnRltdAttrbts></RefData>
<RefData><FinInstrmGnlAttrbts><Id>US78463V1070</Id><FullNm>SPDR GOLD TRT</FullNm>
<ClssfctnTp>CEOICS</ClssfctnTp><NtnlCcy>EUR</NtnlCcy></FinInstrmGnlAttrbts>
<TradgVnRltdAttrbts><Id>MUND</Id></TradgVnRltdAttrbts></RefData>
<RefData><FinInstrmGnlAttrbts><Id>DE000A1EWWW0</Id><FullNm>SOME CERTIFICATE</FullNm>
<ClssfctnTp>EYXXXX</ClssfctnTp><NtnlCcy>EUR</NtnlCcy></FinInstrmGnlAttrbts>
<TradgVnRltdAttrbts><Id>MUND</Id></TradgVnRltdAttrbts></RefData>
</FinInstrmRptgRefDataRpt></Document></Pyld></BizData>"""


def test_firds_keeps_live_gettex_shares_only() -> None:
    df = B.parse_firds(io.BytesIO(FIRDS_XML))
    # Xetra rows, gettex certificates (CFI "EY...") and ETFs ("CE...") are dropped; REITs
    # (CFI "CB...", filed as collective investment vehicles) are kept.
    assert sorted(df["isin"]) == ["US03027X1000", "US0378331005", "US1234567890"]
    live = B.active(df, pd.Timestamp("2026-10-13").date())
    assert sorted(live["isin"]) == ["US03027X1000", "US0378331005"]  # one ended in January


def test_isin_map_cache_maps_only_new_isins(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake(isins: list[str], key: str | None) -> pd.DataFrame:
        calls.append(list(isins))
        return pd.DataFrame(
            {
                "isin": isins,
                "ticker": ["AAPL" if x.startswith("US03") else None for x in isins],
                "figi": None,
                "security_type": None,
            }
        )

    cache = tmp_path / "isin_map.parquet"
    day = pd.Timestamp("2026-10-13").date()
    B.update_map(cache, ["US0378331005", "DE0007164600"], day, None, 10, mapper=fake)
    B.update_map(
        cache, ["US0378331005", "DE0007164600", "CA82509L1076"], day, None, 10, mapper=fake
    )
    assert calls == [["US0378331005", "DE0007164600"], ["CA82509L1076"]]
    later = pd.Timestamp("2026-12-01").date()  # older than REMAP_AFTER_DAYS: re-checked
    B.update_map(cache, ["US0378331005"], later, None, 10, mapper=fake)
    assert calls[-1] == ["US0378331005"]


def stocks() -> pd.DataFrame:
    return pd.DataFrame(
        {"eligible": [True, True, True, False], "history_days": [3000, 3000, 12, 3000]},
        index=["AAPL", "XYZ", "NEWCO", "SMALL"],
    )


def test_zero_flags_true_false_and_unknown() -> None:
    t = stocks()
    as_of = pd.Timestamp("2026-10-13")
    listed = ({"AAPL", "SMALL"}, {"list_date": "2026-10-10", "source": B.SOURCE})
    flags, summary = B.zero_flags(t, listed, as_of)
    assert flags.to_dict() == {"AAPL": True, "XYZ": False, "NEWCO": None, "SMALL": True}
    assert summary is not None
    assert summary["matched"] == 2 and summary["matched_eligible"] == 1
    assert summary["unknown"] == 1 and not summary["stale"]
    # No list at all: every stock is unknown, never "not buyable".
    flags, summary = B.zero_flags(t, None, as_of)
    assert flags.isna().all() and summary is None
    # A list older than 35 days is not trusted.
    old = ({"AAPL"}, {"list_date": "2026-08-01", "source": B.SOURCE})
    flags, summary = B.zero_flags(t, old, as_of)
    assert flags.isna().all() and summary is not None and summary["stale"]


def test_manual_list_wins_over_firds(tmp_path: Path) -> None:
    (tmp_path / "manual" / "brokers").mkdir(parents=True)
    (tmp_path / "manual" / "brokers" / "finanzen_zero.csv").write_text(
        "ticker\nAAPL\nbrk/b\n", encoding="utf-8"
    )
    (tmp_path / "brokers").mkdir()
    pd.DataFrame({"isin": ["X"], "ticker": ["MSFT"]}).to_parquet(
        tmp_path / "brokers" / "finanzen_zero.parquet"
    )
    got = B.load_list(tmp_path)
    assert got is not None
    tickers, meta = got
    assert tickers == {"AAPL", "BRK-B"}
    assert "manual" in meta["source"].lower()


# --------------------------------------------------------------------------- live race


def test_picks_join_the_live_race_from_their_first_snapshot(tmp_path: Path) -> None:
    dates = pd.bdate_range("2026-09-01", periods=80)
    tr = pd.DataFrame(
        {SPY: np.linspace(100, 104, 80), "AAA": np.linspace(10, 12, 80), "BBB": 10.0},
        index=dates,
    )

    def snap(day: pd.Timestamp, with_picks: bool) -> None:
        d = tmp_path / "snapshots" / f"{day:%Y}" / f"{day:%Y%m%d}"
        d.mkdir(parents=True)
        df = pd.DataFrame(
            {"ticker": ["AAA", "BBB"], "label": "NO TRADE", "l1": [0.9, 0.1], "ret_6m": [0.1, 0]}
        )
        if with_picks:
            df["pick_rank"] = [1.0, np.nan]
        df.to_parquet(d / "scores.parquet")

    snap(dates[0], False)  # September: before the Picks page existed
    snap(dates[2], True)  # first day with picks (later in September)
    snap(dates[22], True)  # October's first snapshot
    out = MON.race(tmp_path, tr)
    picks = out["strategies"][MON.PICKS_STRATEGY]
    assert out["picks_since"] == f"{dates[2]:%Y%m%d}"
    assert [p["date"] for p in picks["points"]] == [f"{dates[2]:%Y-%m-%d}", f"{dates[22]:%Y-%m-%d}"]
    i = 2
    expect = (
        (tr["AAA"].iloc[i + 21] / tr["AAA"].iloc[i] - 1)
        - (tr[SPY].iloc[i + 21] / tr[SPY].iloc[i] - 1)
        - 0.002
    )
    assert picks["points"][0]["excess"] == pytest.approx(expect)
    # The model strategies keep using each month's first snapshot.
    assert out["strategies"]["App (model rank)"]["points"][0]["date"] == f"{dates[0]:%Y-%m-%d}"
