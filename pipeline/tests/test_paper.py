"""Paper trading: cost model, euros, whole shares, no look-ahead, anti-churn, each strategy's
rules, idempotent re-runs and the trade ledger's tamper test. Synthetic data only."""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from convergealpha.decide import costs as C
from convergealpha.ledger import ledger as LG
from convergealpha.paper import engine as E
from convergealpha.paper import export as X
from convergealpha.paper import strategies as S
from convergealpha.sources.prices import Panel

START = date(2026, 10, 13)
DAYS = pd.bdate_range("2026-10-01", periods=40)
FX = pd.Series(1.10, index=pd.bdate_range("2026-09-01", "2026-12-31"))


# --------------------------------------------------------------------------- helpers


def panel(prices: dict[str, list[float]], opens: dict[str, list[float]] | None = None, splits: list[tuple[str, str, float]] | None = None) -> Panel:  # fmt: skip
    idx = DAYS[: len(next(iter(prices.values())))]
    close = pd.DataFrame(prices, index=idx, dtype="float64")
    op = pd.DataFrame(opens, index=idx, dtype="float64") if opens else close.shift(1).fillna(close)
    ev = pd.DataFrame(splits or [], columns=["ticker", "date", "ratio"])
    if not ev.empty:
        ev["date"] = pd.to_datetime(ev["date"])
    return Panel(
        open=op, high=close, low=close, close=close, volume=close * 0 + 1e6,
        dividend=close * 0.0, tr=close / close.iloc[0], split_events=ev,
    )  # fmt: skip


def table(rows: dict[str, dict[str, object]]) -> pd.DataFrame:
    base = {
        "zero": True, "eligible": True, "blocked": False, "label": "NO TRADE", "price": 50.0,
        "adv_dollar": 5e8, "p_up_1m": 0.58, "med_1m": 0.03, "p10_1m": -0.06, "p90_1m": 0.10,
        "hit_up_1m_lo": 0.55, "f5": 60.0, "pick_passes": True, "pick_balanced": 80.0,
        "pick_safety": 80.0, "pick_upside": 70.0, "pick_confidence": 70.0, "opp": None,
        "opp_days": np.nan, "opp_event": None, "name": "x",
    }  # fmt: skip
    out = pd.DataFrame({tk: {**base, **r} for tk, r in rows.items()}).T.infer_objects()
    out.index.name = "ticker"  # like the build's table
    return out


VAL = ["P(up) 1m", "P(up) 6m"]


def today(t: pd.DataFrame, **kw: object) -> E.Today:
    return E.Today(table=t, validated=kw.get("validated", VAL), base_up_1m=kw.get("base", 0.56))  # type: ignore[arg-type]


def spec(sid: str) -> S.Spec:
    return next(s for s in S.SPECS if s.id == sid)


def run_days(tmp: Path, pnl: Panel, tables: dict[str, pd.DataFrame], specs: tuple[S.Spec, ...], until: str) -> dict[str, E.Book]:  # fmt: skip
    """Run the engine day by day, as the daily build would (one run per trading day)."""
    books: dict[str, E.Book] = {}
    for d in pnl.close.index:
        if d < pd.Timestamp(START) or d > pd.Timestamp(until):
            continue
        t = tables.get(d.strftime("%Y-%m-%d"))
        books, _ = E.run(tmp, pnl, FX, d, today(t) if t is not None else None, "2026-10-13T21:00:00+00:00", specs)  # fmt: skip
    return books


def entries(tmp: Path) -> list[dict[str, object]]:
    return LG.read(tmp / E.LEDGER)


def kinds(tmp: Path, kind: str, strategy: str | None = None) -> list[dict[str, object]]:
    return [e for e in entries(tmp) if e["kind"] == kind and (strategy is None or e["strategy"] == strategy)]  # fmt: skip


# --------------------------------------------------------------------------- cost model


def test_100_euros_buy_99_euros_of_stock_and_break_even() -> None:
    b = C.buy(100.0, 10.0, 1.0, 0.0, C.Fees(fractional=True))
    assert b.fee == 1.0 and b.invested == pytest.approx(99.0) and b.leftover == pytest.approx(0.0)
    # Selling costs 1 € again: the stock must rise 101/99 − 1 = 2.02% to get 100 € back.
    assert C.break_even(b, 0.0, 1.0) == pytest.approx(101 / 99 - 1)
    assert C.result(b, 101 / 99 - 1, 0.0, 1.0) == pytest.approx(0.0, abs=1e-9)
    # A spread makes it a little more: half on the way in, half on the way out.
    b2 = C.buy(100.0, 10.0, 1.0, 0.002, C.Fees(fractional=True))
    assert C.break_even(b2, 0.002, 1.0) > C.break_even(b, 0.0, 1.0) + 0.0019


def test_euro_conversion_whole_shares_and_leftover() -> None:
    # $150 a share at 1.10 dollars per euro = €136.36; 200 € buys 1 whole share.
    b = C.buy(200.0, 150.0, 1.10, 0.0006)
    assert b.mid_eur == pytest.approx(150 / 1.10)
    assert b.shares == 1
    assert b.pay_eur == pytest.approx(150 / 1.10 * 1.0003)
    assert b.leftover == pytest.approx(200 - 1 - 150 / 1.10 * 1.0003)
    assert C.buy(100.0, 150.0, 1.10, 0.0006).shares == 0  # cannot afford one share: no order
    assert C.buy(100.0, 150.0, 1.10, 0.0006).fee == 0.0
    assert C.buy(200.0, 150.0, 1.10, 0.0006, C.Fees(fractional=True)).shares == pytest.approx(199 / (150 / 1.10 * 1.0003))  # fmt: skip
    # Round trip and switching costs as a share of the position.
    assert C.round_trip_cost(100.0, 0.001) == pytest.approx(0.02 + 0.001)
    assert C.switch_cost(100.0, 0.001, 0.003) == pytest.approx(0.02 + 0.002)


def test_ecb_rate_parsed_and_preferred_for_your_numbers_fred_kept_for_the_first_strategies() -> (
    None
):
    from convergealpha.sources import macro as M

    csv = "\n".join(
        [
            "KEY,FREQ,CURRENCY,TIME_PERIOD,OBS_VALUE",
            "EXR.D.USD.EUR.SP00.A,D,USD,2026-10-12,1.1201",
            "EXR.D.USD.EUR.SP00.A,D,USD,2026-10-13,1.1188",
        ]
    )
    ecb = M.parse_ecb_csv(csv)
    assert list(ecb["value"]) == [1.1201, 1.1188] and set(ecb["series"]) == {"ECB_USD"}
    fred = pd.DataFrame(
        {"ECB_USD": [1.1201, 1.1188], "DEXUSEU": [1.1193, np.nan]},
        index=pd.to_datetime(["2026-10-12", "2026-10-13"]),
    )
    s, sid, src = C.user_fx_series(fred)
    assert (sid, src) == ("ECB_USD", "ECB") and C.fx_on(s, pd.Timestamp("2026-10-13")) == (
        1.1188,
        "2026-10-13",
    )
    assert C.fx_on(C.fx_series(fred), pd.Timestamp("2026-10-13")) == (1.1193, "2026-10-12")
    assert C.fx_gap(fred) == pytest.approx(1.1201 / 1.1193 - 1)
    assert C.user_fx_series(fred.drop(columns=["ECB_USD"]))[2] == "FRED"


def test_zero_fee_rule_free_from_500_euros_else_1_euro() -> None:
    # Same reference values as the web tests (web/src/test/plan.test.ts).
    small = C.buy(400, 50, 1.1, 0.001, C.ZERO_FEES)
    assert small.fee == 1.0 and small.shares == math.floor(399 / (50 / 1.1 * 1.0005))
    big = C.buy(600, 50, 1.1, 0.001, C.ZERO_FEES)
    assert big.fee == 0.0 and big.shares == math.floor(600 / (50 / 1.1 * 1.0005))
    assert C.round_trip_cost(600, 0.001, C.ZERO_FEES) == pytest.approx(0.001)
    assert C.round_trip_cost(400, 0.001, C.ZERO_FEES) == pytest.approx(2 / 400 + 0.001)
    # The first strategies keep a flat 1 € each way.
    assert C.buy(600, 50, 1.1, 0.001).fee == 1.0


def test_fx_uses_the_latest_rate_published_on_or_before_the_day() -> None:
    s = pd.Series([1.10, 1.12], index=pd.to_datetime(["2026-10-01", "2026-10-08"]))
    assert C.fx_on(s, pd.Timestamp("2026-10-07")) == (1.10, "2026-10-01")
    assert C.fx_on(s, pd.Timestamp("2026-10-09")) == (1.12, "2026-10-08")
    assert C.fx_on(s, pd.Timestamp("2026-09-30")) is None


# --------------------------------------------------------------------------- rules are fixed


def test_parameters_are_fixed() -> None:
    # Changing any number is a NEW version that starts again from 200 € (update METHODOLOGY too).
    got = {s.key: s.params() for s in S.ALL_SPECS if s.version == 1}
    zero = {
        "balanced-v1": (2, 0.06, 0.08, None, 63, 10.0, {"min_balanced": 60.0, "min_p_up_1m": 0.52}),
        "high_risk-v1": (1, 0.12, 0.20, 0.10, 21, 10.0, {"w_momentum": 0.4, "w_p90_1m": 0.6}),
        "safe_upside-v1": (2, 0.05, 0.06, None, 63, 10.0, {"min_safety": 75.0}),
        "confidence-v1": (2, 0.07, None, None, 21, 2.0, {}),
        "opportunity-v1": (1, 0.08, 0.12, None, 15, 10.0, {"freshness_step": 10.0}),
    }
    # The same rules on all stocks: their own keys, the same numbers.
    want = {**zero, **{k.replace("-v1", "-all-v1"): v for k, v in zero.items()}, "sp500-v1": (1, None, None, None, None, 0.0, {})}  # fmt: skip
    assert set(got) == set(want)
    for k, (mp, stop, tp, trail, hold, margin, extra) in want.items():
        p = got[k]
        assert (p["max_positions"], p["stop"], p["take_profit"], p["trailing"], p["max_hold"], p["switch_margin"], p["extra"]) == (mp, stop, tp, trail, hold, margin, extra)  # fmt: skip
        assert p["min_hold"] == 3 and p["rebuy_cooldown"] == 5 and p["capital"] == 200.0
        assert p["start"] == "2026-10-13"
        assert p.get("universe") == ("all" if "-all-" in k else None)
    assert (C.FEE_BUY_EUR, C.FEE_SELL_EUR, C.DIVIDEND_WITHHOLDING) == (1.0, 1.0, 0.15)


def test_zero_strategies_keep_the_rules_recorded_at_their_start() -> None:
    # Digests written in the live trade ledger on 2026-10-13: adding the all-stocks versions must
    # not change them (the engine would refuse to trade).
    recorded = {
        "balanced-v1": "1981d0ceb492", "high_risk-v1": "9bb8d2f7d838", "safe_upside-v1": "a6cca2e052f6",
        "confidence-v1": "5316bfed2a2b", "opportunity-v1": "45d81d558ebb", "sp500-v1": "4356200233cc",
    }  # fmt: skip
    assert {s.key: s.digest() for s in (*S.SPECS, S.BENCHMARK)} == recorded
    assert all(s.digest() != recorded[s.key.replace("-all", "")] for s in S.SPECS_ALL)


# --------------------------------------------------------------------------- version 2

FX2 = {"FRED": FX, "ECB": pd.Series(1.20, index=FX.index)}  # two different rates on purpose


def v2(sid: str) -> S.Spec:
    return next(s for s in S.SPECS_V2 if s.id == sid)


def test_version_2_rules_are_fixed() -> None:
    # Recorded in the trade ledger at its start (14 Oct 2026): any change needs version 3.
    recorded = {
        "balanced-v2": "7a7added97f1", "high_risk-v2": "0e3584b10b83", "safe_upside-v2": "0edd36ec0de5",
        "confidence-v2": "c399001873d5", "opportunity-v2": "c61531a4c897",
        "balanced-all-v2": "6dc24195057a", "high_risk-all-v2": "deee6afa030c",
        "safe_upside-all-v2": "1a85087a58a8", "confidence-all-v2": "b7c4bf4b8e2e",
        "opportunity-all-v2": "5920d4d9014d", "sp500-v2": "4565b9ef7dbf",
    }  # fmt: skip
    assert {s.key: s.digest() for s in (*S.SPECS_V2, *S.SPECS_V2_ALL, S.BENCHMARK_V2)} == recorded
    slots = {"balanced": 8, "high_risk": 4, "safe_upside": 8, "confidence": 8, "opportunity": 4}
    for s in (*S.SPECS_V2, *S.SPECS_V2_ALL):
        p = s.params()
        # The sell rule chosen by the research protocol (2016-2023 only), the same for all five.
        assert (p["stop"], p["take_profit"], p["trailing"], p["max_hold"]) == (0.05, 0.06, None, 63)  # fmt: skip
        assert (p["capital"], p["start"], p["fee_rule"], p["fx_source"]) == (5000.0, "2026-10-14", "zero", "ECB")  # fmt: skip
        assert p["max_positions"] == slots[s.id] and p["version"] == 2
        # The ideas themselves (scores, entry filters, special exits) are version 1's.
        assert p["extra"] == spec(s.id).params()["extra"] and p["switch_margin"] == spec(s.id).switch_margin  # fmt: skip
    assert S.START_V2 > S.START and len({s.key for s in S.ALL_SPECS}) == len(S.ALL_SPECS)


def test_version_2_starts_on_its_own_day_with_5000_euros(tmp_path: Path) -> None:
    pnl = panel({"AAA": [50.0] * 12})
    t = table({"AAA": {}})
    both = (spec("balanced"), v2("balanced"))
    E.run(tmp_path, pnl, FX2, DAYS[8], today(t), "x", both)  # Oct 13: only version 1 starts
    assert [e["strategy"] for e in kinds(tmp_path, "start")] == ["balanced-v1"]
    E.run(tmp_path, pnl, FX2, DAYS[9], today(t), "x", both)  # Oct 14: version 2 starts too
    st = kinds(tmp_path, "start", "balanced-v2")
    assert len(st) == 1 and st[0]["date"] == "2026-10-14" and st[0]["capital"] == 5000.0
    assert st[0]["fee_free_from"] == 500.0 and st[0]["params_digest"] == v2("balanced").digest()
    assert {d["date"] for d in kinds(tmp_path, "day", "balanced-v2")} == {"2026-10-14"}
    # Replaying the ledger gives version 2 its own 5,000 € and leaves version 1's 200 € alone.
    books = E.replay(entries(tmp_path), both)
    assert books["balanced-v2"].cash == pytest.approx(5000.0)
    assert books["balanced-v1"].cash < 200.0  # version 1 bought at the Oct 14 open


def test_version_2_uses_the_ecb_rate_free_orders_from_500_and_8_slots(tmp_path: Path) -> None:
    tks = [f"S{i}" for i in range(10)]
    pnl = panel({tk: [50.0] * 12 for tk in tks})
    t = table({tk: {"pick_balanced": 90.0 - i} for i, tk in enumerate(tks)})
    for i in (9, 10):
        E.run(tmp_path, pnl, FX2, DAYS[i], today(t), "x", (v2("balanced"),))
    fills = kinds(tmp_path, "fill", "balanced-v2")
    assert len(fills) == 8  # up to 8 stocks, 625 € each
    s = C.spread(5e8)
    for f in fills:
        assert f["fx"] == 1.20 and f["fee"] == 0.0  # the ECB rate; orders of 500 € or more: free
        assert float(f["amount_eur"]) >= 500
    # The first buy gets 5,000 / 8 = 625 €: 14 shares of ~41.7 €; leftovers carry to later buys.
    assert float(fills[0]["shares"]) == math.floor(625 / (50.0 / 1.20 * (1 + s / 2))) == 14
    assert sum(float(f["amount_eur"]) for f in fills) <= 5000
    # Version 1's rule on the same day uses FRED and pays 1 € (not run here: the rate is per spec).
    assert E.fx_for(FX2, spec("balanced")) is FX and E.fx_for(FX, v2("balanced")) is FX


def test_version_2_small_orders_pay_1_euro_and_are_not_skipped(tmp_path: Path) -> None:
    # A $500 stock: 625 € buys one share (~417 €), under 500 €: bought anyway, with the 1 € fee.
    pnl = panel({"BIG": [500.0] * 12})
    t = table({"BIG": {"price": 500.0}})
    for i in (9, 10):
        E.run(tmp_path, pnl, FX2, DAYS[i], today(t), "x", (v2("balanced"),))
    f = kinds(tmp_path, "fill", "balanced-v2")
    assert (
        len(f) == 1 and float(f[0]["shares"]) > 1 and f[0]["fee"] == 0.0
    )  # all 5,000 €: 11 shares
    # The sell fee follows the sale's value too.
    fees = v2("balanced").fees()
    assert C.sell_value_fees(1, 500.0, 1.2, 0.0, fees) == pytest.approx(500 / 1.2 - 1)
    assert C.sell_value_fees(2, 500.0, 1.2, 0.0, fees) == pytest.approx(1000 / 1.2)


def test_version_2_waits_without_its_rate(tmp_path: Path) -> None:
    pnl = panel({"AAA": [50.0] * 12})
    t = table({"AAA": {}})
    _, new = E.run(tmp_path, pnl, {"FRED": FX}, DAYS[9], today(t), "x", (v2("balanced"),))
    assert [e["kind"] for e in new] == ["start"]  # started, but no day without the ECB rate


def test_export_has_version_2_with_its_own_capital_and_rate(tmp_path: Path) -> None:
    pnl = panel({"AAA": [50.0] * 12, "SPY": [660.0] * 12})
    t = table({"AAA": {}, "SPY": {"price": 660.0, "adv_dollar": 3e10, "eligible": False}})
    books, _ = E.run(tmp_path, pnl, FX2, DAYS[9], today(t), "x")
    from datetime import UTC, datetime

    out = X.export(books, t, "2026-10-14", datetime(2026, 10, 14, 21, tzinfo=UTC), (1.10, "2026-10-14"), (True, "ok", 0), VAL, 0.56, fx_ecb=(1.20, "2026-10-14"))  # fmt: skip
    v = out["v2"]
    assert v["started"] and v["capital"] == 5000.0 and v["start"] == "2026-10-14"
    assert v["fx"]["source"] == "ECB" and v["costs"]["free_from"] == 500.0
    assert [c["key"] for c in v["strategies"]] == [s.key for s in S.SPECS_V2]
    assert [c["key"] for c in v["strategies_all"]] == [s.key for s in S.SPECS_V2_ALL]
    c = v["strategies"][0]
    assert (c["capital"], c["fx_rate"], c["fee_rule"], c["value"], c["pct"]) == (5000.0, 1.2, "zero", 5000.0, 0.0)  # fmt: skip
    o = c["pending"][0]
    assert o["ticker"] == "AAA" and o["est_eur"] > 4900  # one stock to buy: all 5,000 €, no fee
    spy = v["benchmark"]["pending"][0]
    assert spy["est_eur"] == pytest.approx(5000.0) and "5,000 €" in spy["reason"]
    assert out["strategies"][0]["capital"] == 200.0 and out["strategies"][0]["fx_rate"] == 1.1


def test_all_stocks_version_may_buy_what_finanzen_net_zero_does_not_offer(tmp_path: Path) -> None:
    pnl = panel({"AAA": [50.0] * 12, "BBB": [50.0] * 12, "CCC": [50.0] * 12})
    t = table({
        "AAA": {"zero": False, "pick_balanced": 95.0},
        "BBB": {"zero": None, "pick_balanced": 90.0},  # "not sure" counts as not buyable
        "CCC": {"zero": True, "pick_balanced": 70.0},
    })  # fmt: skip
    z, a = spec("balanced"), S.SPECS_ALL[0]
    assert (z.key, a.key, a.id, a.universe) == ("balanced-v1", "balanced-all-v1", "balanced", "all")
    E.run(tmp_path, pnl, FX, DAYS[8], today(t), "x", (z, a))
    bought = {(str(o["strategy"]), str(o["ticker"])) for o in kinds(tmp_path, "order")}
    assert bought == {
        ("balanced-v1", "CCC"),
        ("balanced-all-v1", "AAA"),
        ("balanced-all-v1", "BBB"),
    }


def test_export_splits_the_two_versions_and_estimates_waiting_orders(tmp_path: Path) -> None:
    pnl = panel({"AAA": [50.0] * 12, "SPY": [660.0] * 12})
    t = table({"AAA": {}, "SPY": {"price": 660.0, "adv_dollar": 3e10}})
    books, _ = E.run(tmp_path, pnl, FX, DAYS[8], today(t), "x")
    from datetime import UTC, datetime

    out = X.export(books, t, "2026-10-13", datetime(2026, 10, 13, 21, tzinfo=UTC), (1.10, "2026-10-09"), (True, "ok", 0), VAL, 0.56)  # fmt: skip
    assert [c["key"] for c in out["strategies"]] == [s.key for s in S.SPECS]
    assert [c["key"] for c in out["strategies_all"]] == [s.key for s in S.SPECS_ALL]
    assert {c["universe"] for c in out["strategies"]} == {"zero"}
    assert out["benchmark"]["universe"] is None and set(out["universes"]) == {"zero", "all"}
    assert set(out["suggestions_all"]) == {s.id for s in S.SPECS}
    # Balanced buys AAA with all 200 € at the next open: about 3 whole shares... of a $50 stock.
    o = next(c for c in out["strategies"] if c["id"] == "balanced")["pending"][0]
    s = C.spread(5e8)
    each = 50.0 / 1.10 * (1 + s / 2)
    assert o["ticker"] == "AAA" and o["est_shares"] == math.floor((200 - 1) / each)
    assert o["est_eur"] == pytest.approx(o["est_shares"] * each + 1, abs=0.01)
    spy = out["benchmark"]["pending"][0]
    assert 0 < spy["est_shares"] < 1 and spy["est_eur"] == pytest.approx(200.0)


def test_changed_rules_without_a_new_version_do_not_trade(tmp_path: Path) -> None:
    pnl = panel({"AAA": [50.0] * 12})
    t = table({"AAA": {}})
    E.run(tmp_path, pnl, FX, DAYS[8], today(t), "x", (spec("balanced"),))
    changed = S.Spec(**{**spec("balanced").__dict__, "stop": 0.05})
    books, new = E.run(tmp_path, pnl, FX, DAYS[9], today(t), "x", (changed,))
    assert new == [] and books[changed.key].locked


# --------------------------------------------------------------------------- engine


def test_first_decision_at_the_close_fill_at_the_next_open(tmp_path: Path) -> None:
    # Oct 13 is DAYS[8]. The next open (Oct 14) is far from the Oct 13 close: the fill uses it.
    closes = [50.0] * 12
    opens = [50.0] * 9 + [53.0, 53.0, 53.0]
    pnl = panel({"AAA": closes}, {"AAA": opens})
    t = table({"AAA": {"price": 50.0}})
    E.run(tmp_path, pnl, FX, DAYS[8], today(t), "x", (spec("balanced"),))
    assert [e["kind"] for e in entries(tmp_path)] == ["start", "order", "day"]
    o = kinds(tmp_path, "order")[0]
    assert o["date"] == "2026-10-13" and o["side"] == "buy" and o["ticker"] == "AAA"
    assert "Bought AAA" in str(o["reason"])
    E.run(tmp_path, pnl, FX, DAYS[9], today(t), "x", (spec("balanced"),))
    f = kinds(tmp_path, "fill")[0]
    assert f["date"] == "2026-10-14" and f["open_usd"] == 53.0
    s = C.spread(5e8)
    assert f["price_eur"] == pytest.approx(53.0 / 1.10 * (1 + s / 2))
    assert float(f["shares"]) == math.floor((200 - 1) / (53.0 / 1.10 * (1 + s / 2)))  # whole shares
    day = kinds(tmp_path, "day")[-1]
    assert float(day["cash_eur"]) == pytest.approx(200 - float(f["amount_eur"]))  # leftover is cash


def test_no_look_ahead_future_prices_do_not_change_a_decision(tmp_path: Path) -> None:
    t = table({"AAA": {"pick_balanced": 85.0}, "BBB": {"pick_balanced": 75.0}})
    short = panel({"AAA": [50.0] * 9, "BBB": [40.0] * 9})
    future = panel({"AAA": [50.0] * 9 + [10.0] * 5, "BBB": [40.0] * 9 + [400.0] * 5})
    a, b = tmp_path / "a", tmp_path / "b"
    E.run(a, short, FX, DAYS[8], today(t), "x", (spec("balanced"),))
    E.run(b, future, FX, DAYS[8], today(t), "x", (spec("balanced"),))
    strip = lambda es: [{k: v for k, v in e.items() if k not in ("hash", "prev_hash")} for e in es]  # noqa: E731
    assert strip(entries(a)) == strip(entries(b))


def test_same_day_rerun_adds_nothing(tmp_path: Path) -> None:
    pnl = panel({"AAA": [50.0] * 12})
    t = table({"AAA": {}})
    E.run(tmp_path, pnl, FX, DAYS[8], today(t), "x")
    before = (tmp_path / E.LEDGER).read_text(encoding="utf-8")
    _, new = E.run(tmp_path, pnl, FX, DAYS[8], today(t), "y")
    assert new == []
    assert (tmp_path / E.LEDGER).read_text(encoding="utf-8") == before
    # Every strategy (both versions) and the benchmark decided once for Oct 13, nothing filled yet.
    days = kinds(tmp_path, "day")
    assert len(days) == 11 and {d["date"] for d in days} == {"2026-10-13"}
    assert kinds(tmp_path, "fill") == []


def test_trade_ledger_tamper_detection(tmp_path: Path) -> None:
    pnl = panel({"AAA": [50.0] * 12})
    t = table({"AAA": {}})
    for i in (8, 9, 10):
        E.run(tmp_path, pnl, FX, DAYS[i], today(t), "x")
    assert E.verify(tmp_path) == (True, "ok")
    p = tmp_path / E.LEDGER
    lines = p.read_text(encoding="utf-8").splitlines()
    i = next(i for i, x in enumerate(lines) if json.loads(x)["kind"] == "fill")
    e = json.loads(lines[i])
    e["open_usd"] = 1.0  # a better past price
    lines[i] = json.dumps(e, sort_keys=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, why = E.verify(tmp_path)
    assert not ok and f"line {i + 1}" in why


def test_minimum_hold_unless_a_stop(tmp_path: Path) -> None:
    # Take-profit (+8%) on the first close is not taken before 3 trading days...
    pnl = panel({"AAA": [50.0] * 9 + [50.0, 55.0, 55.0, 55.0, 55.0]})
    t = table({"AAA": {}})
    books = run_days(tmp_path, pnl, {d.strftime("%Y-%m-%d"): t for d in DAYS}, (spec("balanced"),), "2026-10-16")  # fmt: skip
    sells = [o for o in kinds(tmp_path, "order") if o["side"] == "sell"]
    assert len(sells) == 1 and sells[0]["date"] == "2026-10-16" and "take-profit" in str(sells[0]["reason"])  # fmt: skip
    notes = [n for d in kinds(tmp_path, "day") for n in d["notes"]]  # type: ignore[union-attr]
    assert any("minimum 3 trading days" in n for n in notes)
    # ...but a stop sells at once.
    p2 = tmp_path / "stop"
    pnl2 = panel({"AAA": [50.0] * 9 + [50.0, 46.0, 46.0, 46.0]})
    run_days(p2, pnl2, {d.strftime("%Y-%m-%d"): t for d in DAYS}, (spec("balanced"),), "2026-10-15")
    sells2 = [o for o in kinds(p2, "order") if o["side"] == "sell"]
    assert len(sells2) == 1 and sells2[0]["date"] == "2026-10-15" and "stop" in str(sells2[0]["reason"])  # fmt: skip
    assert books


def test_switch_needs_the_margin_and_more_expected_gain_than_the_cost(tmp_path: Path) -> None:
    pnl = panel({"AAA": [50.0] * 16, "BBB": [50.0] * 16, "CCC": [50.0] * 16})
    first = table({"AAA": {"pick_balanced": 70.0, "med_1m": 0.02}})
    # BBB: 12 points ahead but only +0.5% more expected gain (switching costs > 2% here): keep.
    small = table({"AAA": {"pick_balanced": 70.0, "med_1m": 0.02}, "BBB": {"pick_balanced": 82.0, "med_1m": 0.025}})  # fmt: skip
    # CCC: 15 points ahead and +6% more expected gain: switch.
    big = table({"AAA": {"pick_balanced": 70.0, "med_1m": 0.02}, "CCC": {"pick_balanced": 85.0, "med_1m": 0.08}})  # fmt: skip
    one = S.Spec(**{**spec("balanced").__dict__, "max_positions": 1, "version": 99})
    tables = {"2026-10-13": first, "2026-10-14": small, "2026-10-15": small, "2026-10-16": small, "2026-10-19": big}  # fmt: skip
    run_days(tmp_path, pnl, tables, (one,), "2026-10-19")
    orders = kinds(tmp_path, "order")
    assert [(o["date"], o["side"], o["ticker"]) for o in orders] == [
        ("2026-10-13", "buy", "AAA"),
        ("2026-10-19", "sell", "AAA"),
        ("2026-10-19", "buy", "CCC"),
    ]
    assert "switch" in str(orders[1]["reason"]) and "cost of switching" in str(orders[1]["reason"])
    kept = [n for d in kinds(tmp_path, "day") if d["date"] == "2026-10-16" for n in d["notes"]]  # type: ignore[union-attr]
    assert any(n.startswith("Kept AAA") and "enough extra expected gain" in n for n in kept)


def test_balanced_entry_rules(tmp_path: Path) -> None:
    t = table({
        "LOW": {"p_up_1m": 0.51},  # chance up below 52%
        "NOPICK": {"pick_passes": False},  # fails the Picks minimum of 40
        "WEAK": {"pick_balanced": 59.0},  # would be sold at once (below 60)
        "THIN": {"med_1m": 0.005, "pick_balanced": 99.0},  # gain does not cover the round trip
        "NOZERO": {"zero": None, "pick_balanced": 99.0},  # not sure it is on finanzen.net zero
        "SELL": {"label": "SELL / RISK WARNING", "pick_balanced": 99.0},
        "BLOCK": {"blocked": True, "pick_balanced": 99.0},
        "OK": {"pick_balanced": 70.0},
    })  # fmt: skip
    pnl = panel({k: [50.0] * 9 for k in t.index})
    E.run(tmp_path, pnl, FX, DAYS[8], today(t), "x", (spec("balanced"),))
    assert [o["ticker"] for o in kinds(tmp_path, "order")] == ["OK"]
    # Without a validated 1-month chance up, it does not buy at all.
    p2 = tmp_path / "noval"
    E.run(p2, pnl, FX, DAYS[8], today(t, validated=["P(up) 6m"]), "x", (spec("balanced"),))
    assert kinds(p2, "order") == []
    assert any("not validated" in n for n in kinds(p2, "day")[0]["notes"])  # type: ignore[union-attr]


def test_balanced_sells_when_the_score_falls_below_60(tmp_path: Path) -> None:
    pnl = panel({"AAA": [50.0] * 16})
    good, bad = table({"AAA": {"pick_balanced": 75.0}}), table({"AAA": {"pick_balanced": 55.0}})
    tables = {"2026-10-13": good, "2026-10-14": good, "2026-10-15": good, "2026-10-16": bad}
    run_days(tmp_path, pnl, tables, (spec("balanced"),), "2026-10-16")
    sell = next(o for o in kinds(tmp_path, "order") if o["side"] == "sell")
    assert sell["date"] == "2026-10-16" and "Balanced score fell to 55" in str(sell["reason"])


def test_high_risk_trailing_stop_and_ranking(tmp_path: Path) -> None:
    t = table({"AAA": {"p90_1m": 0.30, "f5": 90.0}, "BBB": {"p90_1m": 0.10, "f5": 40.0}})
    # Up 15% to a peak, then 11% below the peak (still +2% from the buy): the trailing stop sells.
    pnl = panel({"AAA": [20.0] * 9 + [20.0, 23.0, 20.4, 20.4], "BBB": [20.0] * 13})
    tables = {d.strftime("%Y-%m-%d"): t for d in DAYS}
    run_days(tmp_path, pnl, tables, (spec("high_risk"),), "2026-10-16")
    orders = kinds(tmp_path, "order")
    assert orders[0]["ticker"] == "AAA" and orders[0]["side"] == "buy"
    sell = next(o for o in orders if o["side"] == "sell")
    assert sell["date"] == "2026-10-16" and "trailing stop" in str(sell["reason"])


def test_safe_upside_needs_safety_75_and_takes_6_percent(tmp_path: Path) -> None:
    t = table({
        "RISKY": {"pick_safety": 70.0, "pick_upside": 99.0},
        "SAFE1": {"pick_safety": 80.0, "pick_upside": 60.0},
        "SAFE2": {"pick_safety": 90.0, "pick_upside": 50.0},
    })  # fmt: skip
    pnl = panel({"RISKY": [30.0] * 16, "SAFE1": [30.0] * 9 + [30.0, 30.5, 31.0, 32.0, 32.0, 32.0, 32.0], "SAFE2": [30.0] * 16})  # fmt: skip
    tables = {d.strftime("%Y-%m-%d"): t for d in DAYS}
    run_days(tmp_path, pnl, tables, (spec("safe_upside"),), "2026-10-20")
    orders = kinds(tmp_path, "order")
    assert {o["ticker"] for o in orders if o["date"] == "2026-10-13"} == {"SAFE1", "SAFE2"}
    sell = next(o for o in orders if o["side"] == "sell")
    assert sell["ticker"] == "SAFE1" and sell["date"] == "2026-10-19"
    assert "lock it in" in str(sell["reason"])
    # Rotates, but never straight back into the stock it just took profit on.
    assert not any(o["side"] == "buy" and o["ticker"] == "SAFE1" and o["date"] >= "2026-10-16" for o in orders)  # fmt: skip


def test_confidence_exits_below_the_usual_rate(tmp_path: Path) -> None:
    pnl = panel({"AAA": [50.0] * 16})
    good = table({"AAA": {"p_up_1m": 0.60, "hit_up_1m_lo": 0.56}})
    low = table({"AAA": {"p_up_1m": 0.54, "hit_up_1m_lo": 0.52}})
    tables = {"2026-10-13": good, "2026-10-14": good, "2026-10-15": good, "2026-10-16": low}
    run_days(tmp_path, pnl, tables, (spec("confidence"),), "2026-10-16")
    sell = next(o for o in kinds(tmp_path, "order") if o["side"] == "sell")
    assert "below the usual 56%" in str(sell["reason"])
    # A chance up below the usual rate is never bought.
    p2 = tmp_path / "b"
    E.run(p2, pnl, FX, DAYS[8], today(low), "x", (spec("confidence"),))
    assert kinds(p2, "order") == []


def test_opportunity_hunter_only_green_and_sells_on_red(tmp_path: Path) -> None:
    pnl = panel({"AMB": [50.0] * 16, "GRN": [50.0] * 16, "OLD": [50.0] * 16})
    t = table({
        "AMB": {"opp": "amber", "opp_days": 0.0},
        "GRN": {"opp": "green", "opp_days": 1.0, "opp_event": "Insider cluster buy (Oct 12)"},
        "OLD": {"opp": "green", "opp_days": 4.0},
    })  # fmt: skip
    red = t.copy()
    red.loc["GRN", "opp"] = "red"
    tables = {"2026-10-13": t, "2026-10-14": red}
    run_days(tmp_path, pnl, tables, (spec("opportunity"),), "2026-10-14")
    orders = kinds(tmp_path, "order")
    assert orders[0]["ticker"] == "GRN" and "green opportunity" in str(orders[0]["reason"])
    sell = next(o for o in orders if o["side"] == "sell")
    assert sell["date"] == "2026-10-14" and "turned red" in str(
        sell["reason"]
    )  # a stop: no minimum hold
    # Nothing green: it stays in cash.
    p2 = tmp_path / "cash"
    amber = table({"AMB": {"opp": "amber", "opp_days": 0.0}})
    E.run(p2, pnl, FX, DAYS[8], today(amber), "x", (spec("opportunity"),))
    assert kinds(p2, "order") == []
    assert any("green" in n for n in kinds(p2, "day")[0]["notes"])  # type: ignore[union-attr]


def test_missed_day_is_caught_up_from_prices_only(tmp_path: Path) -> None:
    pnl = panel({"AAA": [50.0] * 9 + [50.0, 45.0, 45.0, 45.0], "BBB": [50.0] * 13})
    t = table({"AAA": {"pick_balanced": 90.0}, "BBB": {"pick_balanced": 85.0}})
    E.run(tmp_path, pnl, FX, DAYS[8], today(t), "x", (spec("balanced"),))
    # The builds of Oct 14 and 15 did not run; Oct 16 catches up.
    E.run(tmp_path, pnl, FX, DAYS[11], today(t), "x", (spec("balanced"),))
    days = kinds(tmp_path, "day")
    assert [d["data"] for d in days] == ["full", "prices only", "prices only", "full"]
    # Oct 15 (prices only): AAA's stop is checked from prices; no new buys that day.
    oct15 = [o for o in kinds(tmp_path, "order") if o["date"] == "2026-10-15"]
    assert [(o["side"], o["ticker"]) for o in oct15] == [("sell", "AAA")]


def test_split_changes_the_share_count_not_the_value(tmp_path: Path) -> None:
    # 2-for-1 split on Oct 16: the panel (adjusted to today) halves every earlier price.
    adj = [25.0] * 9 + [25.0, 25.0, 25.0, 25.0]
    pnl = panel({"AAA": adj}, splits=[("AAA", "2026-10-16", 2.0)])
    t = table({"AAA": {"price": 50.0}})
    E.run(tmp_path, pnl, FX, DAYS[8], today(t), "x", (spec("balanced"),))
    E.run(tmp_path, pnl, FX, DAYS[9], today(t.assign(price=50.0)), "x", (spec("balanced"),))
    fill = kinds(tmp_path, "fill")[0]
    assert fill["open_usd"] == pytest.approx(50.0)  # the real price paid before the split
    t2 = t.assign(price=25.0)
    E.run(tmp_path, pnl, FX, DAYS[11], today(t2), "x", (spec("balanced"),))
    sp = kinds(tmp_path, "split")[0]
    assert sp["shares_after"] == 2 * float(fill["shares"])
    last = kinds(tmp_path, "day")[-1]
    pos = last["positions"][0]  # type: ignore[index]
    assert pos["stock_move"] == pytest.approx(0.0)  # no fake 50% loss


def test_benchmark_buys_once_with_a_fraction_and_holds(tmp_path: Path) -> None:
    pnl = panel({"SPY": [660.0] * 9 + [670.0, 680.0, 690.0]})
    t = table({"SPY": {"price": 660.0, "adv_dollar": 3e10}})
    for i in (8, 9, 10, 11):
        E.run(tmp_path, pnl, FX, DAYS[i], today(t), "x", (S.BENCHMARK,))
    fills = kinds(tmp_path, "fill")
    assert len(fills) == 1 and 0 < float(fills[0]["shares"]) < 1
    assert float(fills[0]["amount_eur"]) == pytest.approx(200.0)
    assert len([o for o in kinds(tmp_path, "order")]) == 1


def test_max_drawdown() -> None:
    assert E.max_drawdown([200, 210, 189, 220]) == pytest.approx(189 / 210 - 1)
    assert E.max_drawdown([200, 201]) == 0.0


# --------------------------------------------------------------------------- replay


def test_a_past_day_replays_exactly_from_the_stored_inputs(tmp_path: Path) -> None:
    from convergealpha.paper import replay as RP

    pnl = panel({"AAA": [50.0] * 9 + [51.0, 49.0, 52.0], "BBB": [40.0] * 12, "SPY": [660.0] * 12})
    t = table(
        {"AAA": {"pick_balanced": 85.0}, "BBB": {}, "SPY": {"price": 660.0, "eligible": False}}
    )
    specs = (spec("balanced"), S.SPECS_V2[0], S.BENCHMARK_V2)
    for i in (8, 9, 10):
        d = DAYS[i]
        rel, sha = RP.save_inputs(tmp_path, t, d, pd.Timestamp("2026-10-15 21:00"))
        inputs = {"paper_inputs": rel, "paper_inputs_sha256": sha, "validated": VAL, "base_up_1m": 0.56, "why_not": None}  # fmt: skip
        E.run(tmp_path, pnl, FX2, d, E.Today(t, VAL, 0.56, True, None, inputs), f"r{i}", specs)
    out = RP.replay_day(tmp_path, pnl, "2026-10-15", specs)
    assert out["mismatched"] == 0 and out["matched"] == 3, out
    # A changed price shows up as a mismatch, naming what differs.
    bad = panel({"AAA": [50.0] * 9 + [51.0, 47.0, 52.0], "BBB": [40.0] * 12, "SPY": [660.0] * 12})
    out = RP.replay_day(tmp_path, bad, "2026-10-15", specs)
    assert out["strategies"]["balanced-v1"]["status"] == "mismatch"
    assert any("value_eur" in d for d in out["strategies"]["balanced-v1"]["differences"])
    # An edited inputs file is caught by its SHA-256.
    p = tmp_path / rel
    df = pd.read_parquet(p)
    df.loc[0, "price"] = 1.0
    df.to_parquet(p)
    assert RP.replay_day(tmp_path, pnl, "2026-10-15", specs)["strategies"]["balanced-v1"]["why"].endswith("(SHA-256 differs)")  # fmt: skip


def test_stored_inputs_keep_yes_no_and_not_sure(tmp_path: Path) -> None:
    from convergealpha.paper import replay as RP

    t = table({"AAA": {"zero": True}, "BBB": {"zero": None}, "CCC": {"zero": False}})
    rel, _ = RP.save_inputs(tmp_path, t, DAYS[8], pd.Timestamp("2026-10-13 21:00"))
    back = RP.load_inputs(tmp_path, rel)
    assert back["zero"].tolist() == [True, None, False] and back["name"].tolist() == ["x"] * 3
    assert list(S.universe(back).index) == ["AAA"]  # "not sure" is not buyable, as in the build
    # Files of 14 Oct 2026 stored the column as text: read back the same way.
    legacy = t.assign(zero=["True", None, "False"]).reset_index()
    legacy.to_parquet(tmp_path / "legacy.parquet")
    assert RP.load_inputs(tmp_path, "legacy.parquet")["zero"].tolist() == [True, None, False]
