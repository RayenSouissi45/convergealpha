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
    got = {s.key: s.params() for s in S.ALL_SPECS}
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
