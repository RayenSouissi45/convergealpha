"""Live estimate of the paper strategies during US trading hours: never written to the ledger, and
equal to the official value the engine records that night when the last price is the close."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from convergealpha.paper import engine as E
from convergealpha.paper import export as X
from convergealpha.paper import live as L
from convergealpha.paper import strategies as S
from tests.test_paper import DAYS, FX, VAL, panel, table, today


def test_market_state_follows_new_york_hours() -> None:
    assert L.market_state(datetime(2026, 10, 14, 13, 0, tzinfo=UTC)) == "pre-open"  # 9:00 New York
    assert L.market_state(datetime(2026, 10, 14, 14, 0, tzinfo=UTC)) == "open"  # 10:00
    assert L.market_state(datetime(2026, 10, 14, 20, 30, tzinfo=UTC)) == "closed"  # 16:30
    assert L.market_state(datetime(2026, 10, 17, 15, 0, tzinfo=UTC)) == "closed"  # Saturday


def _card(tmp: Path, until: int, closes: list[float], opens: list[float]) -> tuple[dict, dict]:  # type: ignore[type-arg]
    pnl = panel(
        {"AAA": closes, "SPY": [660.0] * len(closes)}, {"AAA": opens, "SPY": [660.0] * len(closes)}
    )
    t = table({"AAA": {"price": closes[until]}, "SPY": {"price": 660.0, "adv_dollar": 3e10}})
    books, _ = E.run(tmp, pnl, FX, DAYS[until], today(t), "x", (S.SPECS[0], S.BENCHMARK))
    out = X.export(books, t, DAYS[until].strftime("%Y-%m-%d"), datetime(2026, 10, 13, 21, tzinfo=UTC), (1.10, "2026-10-09"), (True, "ok", 0), VAL, 0.56)  # fmt: skip
    return out, {"pnl": pnl, "t": t}


def test_live_value_equals_the_official_value_when_the_last_price_is_the_close(
    tmp_path: Path,
) -> None:
    closes = [50.0] * 9 + [51.5, 52.0, 52.0]
    opens = [50.0] * 9 + [50.8, 51.6, 52.0]
    f, ctx = _card(
        tmp_path, 8, closes, opens
    )  # official numbers after the Oct 13 close: a buy waits
    card = f["strategies"][0]
    assert card["pending"] and card["pending"][0]["spread"] > 0
    day = DAYS[9].date()
    q = {
        "AAA": L.Quote(open=50.8, last=51.5, at="x"),
        "SPY": L.Quote(open=660.0, last=660.0, at="x"),
    }
    est = L.estimate(card, q, 1.10, day, f["capital"])
    assert [x["ticker"] for x in est["filled_today"]] == ["AAA"]
    # The engine's own day, run the same way the daily build would tonight.
    books, _ = E.run(
        tmp_path, ctx["pnl"], FX, DAYS[9], today(ctx["t"]), "y", (S.SPECS[0], S.BENCHMARK)
    )
    official = books[S.SPECS[0].key].values[-1][1]
    assert est["value"] == pytest.approx(official, abs=1e-6)
    assert est["holdings"][0]["bought_today"] and est["holdings"][0]["move"] == pytest.approx(51.5 / 50.8 - 1)  # fmt: skip


def test_before_the_open_nothing_fills_and_cash_is_the_value(tmp_path: Path) -> None:
    f, _ = _card(tmp_path, 8, [50.0] * 12, [50.0] * 12)
    card = f["strategies"][0]
    est = L.estimate(
        card, {"AAA": L.Quote(open=None, last=50.0, at="x")}, 1.10, DAYS[9].date(), 200.0
    )
    assert est["filled_today"] == [] and est["value"] == pytest.approx(200.0)
    assert [w["ticker"] for w in est["waiting"]] == ["AAA"]


def test_a_holding_is_marked_at_its_latest_price_and_a_waiting_sell_fills_at_the_open() -> None:
    card = {
        "key": "x-v1", "benchmark": False, "cash": 10.0, "value": 210.0,
        "holdings": [{"ticker": "BBB", "shares": 4.0, "entry_usd": 50.0, "close_usd": 55.0, "cost_eur": 190.0, "spread": 0.001}],
        "pending": [],
    }  # fmt: skip
    est = L.estimate(card, {"BBB": L.Quote(open=55.0, last=57.2, at="x")}, 1.10, date(2026, 10, 15))
    assert est["value"] == pytest.approx(10.0 + 4 * 57.2 / 1.10)
    assert est["holdings"][0]["day_move"] == pytest.approx(57.2 / 55.0 - 1)
    assert est["day_change_eur"] == pytest.approx(est["value"] - 210.0)
    card["pending"] = [{"side": "sell", "ticker": "BBB", "fill_on": "2026-10-15", "spread": 0.001}]
    est = L.estimate(card, {"BBB": L.Quote(open=56.0, last=57.2, at="x")}, 1.10, date(2026, 10, 15))
    assert est["holdings"] == [] and est["value"] == pytest.approx(
        10.0 + 4 * 56.0 / 1.10 * (1 - 0.0005) - 1.0
    )


def _site(tmp: Path, f: dict) -> Path:  # type: ignore[type-arg]
    (tmp / "strategies.json").write_text(json.dumps(f), encoding="utf-8")
    return tmp


def test_run_writes_the_live_file_and_never_the_ledger(tmp_path: Path) -> None:
    f, _ = _card(tmp_path / "d", 8, [50.0] * 12, [50.0] * 12)
    ledger_before = (tmp_path / "d" / E.LEDGER).read_text(encoding="utf-8")
    site = _site(tmp_path, f)

    def fake(tks: list[str], d: date) -> dict[str, L.Quote]:
        aaa = {"open": 50.0, "last": 51.0}
        spy = {"open": 660.0, "last": 661.0}
        return {
            t: L.Quote(**(aaa if t == "AAA" else spy), at="2026-10-14T15:00:00+00:00") for t in tks
        }  # type: ignore[arg-type]

    out = L.run(site, datetime(2026, 10, 14, 15, 0, tzinfo=UTC), quote_source=fake)
    assert out is not None and out["market"] == "open"
    live = json.loads((site / "strategies_live.json").read_text(encoding="utf-8"))
    assert set(live["strategies"]) == {S.SPECS[0].key} and live["benchmark"]["key"] == "sp500-v1"
    assert live["strategies"][S.SPECS[0].key]["vs_benchmark"] is not None
    assert (tmp_path / "d" / E.LEDGER).read_text(encoding="utf-8") == ledger_before


def test_run_before_the_open_only_says_it_waits(tmp_path: Path) -> None:
    f, _ = _card(tmp_path / "d", 8, [50.0] * 12, [50.0] * 12)
    site = _site(tmp_path, f)
    called: list[int] = []
    out = L.run(
        site,
        datetime(2026, 10, 14, 12, 0, tzinfo=UTC),
        quote_source=lambda t, d: called.append(1) or {},
    )  # type: ignore[func-returns-value]
    assert (
        out is not None and out["market"] == "pre-open" and out["strategies"] == {} and not called
    )


def test_yahoo_quotes_keep_only_todays_bar(monkeypatch: pytest.MonkeyPatch) -> None:
    bars = pd.DataFrame({
        "ticker": ["AAA", "AAA", "BBB"], "date": pd.to_datetime(["2026-10-13", "2026-10-14", "2026-10-13"]),
        "open": [50.0, 50.5, 20.0], "close": [50.2, 51.0, 20.1],
    })  # fmt: skip
    import convergealpha.sources.prices as P

    monkeypatch.setattr(P, "download", lambda *a, **k: bars)
    q = L.yahoo_quotes(["AAA", "BBB"], date(2026, 10, 14))
    assert set(q) == {"AAA"} and q["AAA"].open == 50.5 and q["AAA"].last == 51.0


def test_a_stale_yahoo_open_is_not_used_and_the_fallback_gives_the_real_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 15 Oct 2026, minutes after the open: Yahoo's bar for today still carried yesterday's open
    # (HIG 130.47), below everything HIG traded at that morning (133.62 to 134.66).
    bars = pd.DataFrame({
        "ticker": ["HIG", "HIG", "CINF"], "date": pd.to_datetime(["2026-10-14", "2026-10-15", "2026-10-15"]),
        "open": [130.47, 130.47, 169.97], "high": [132.15, 134.66, 170.59],
        "low": [129.36, 133.62, 169.36], "close": [131.96, 134.32, 170.04],
    })  # fmt: skip
    import convergealpha.sources.prices as P

    monkeypatch.setattr(P, "download", lambda *a, **k: bars)
    q = L.yahoo_quotes(["HIG", "CINF"], date(2026, 10, 15))
    assert q["HIG"].open is None and q["HIG"].last == 134.32 and q["CINF"].open == 169.97

    # In the live run, an order due today with no Yahoo open takes the fallback's open.
    f, _ = _card(tmp_path / "d", 8, [50.0] * 12, [50.0] * 12)
    site = _site(tmp_path, f)
    asked: list[list[str]] = []

    def yahoo(tks: list[str], d: date) -> dict[str, L.Quote]:
        return {t: L.Quote(open=None if t == "AAA" else 660.0, last=51.0 if t == "AAA" else 661.0, at="y") for t in tks}  # fmt: skip

    def finnhub(tks: list[str], d: date) -> dict[str, L.Quote]:
        asked.append(tks)
        return {t: L.Quote(open=50.5, last=51.0, at="f") for t in tks}

    out = L.run(site, datetime(2026, 10, 14, 15, 0, tzinfo=UTC), quote_source=yahoo, fallback=finnhub)  # fmt: skip
    assert out is not None and asked == [["AAA"]]
    est = out["strategies"][S.SPECS[0].key]
    assert [x["open_usd"] for x in est["filled_today"]] == [50.5] and est["waiting"] == []


def test_version_2_live_value_uses_its_own_capital_rate_and_free_orders(tmp_path: Path) -> None:
    from tests.test_paper import FX2

    closes = [50.0] * 10 + [51.5, 52.0]
    opens = [50.0] * 10 + [50.8, 52.0]
    pnl = panel({"AAA": closes, "SPY": [660.0] * 12}, {"AAA": opens, "SPY": [660.0] * 12})
    t = table({"AAA": {"price": 50.0}, "SPY": {"price": 660.0, "adv_dollar": 3e10, "eligible": False}})  # fmt: skip
    specs = (S.SPECS_V2[0], S.BENCHMARK_V2)
    books, _ = E.run(tmp_path / "d", pnl, FX2, DAYS[9], today(t), "x", specs)  # Oct 14
    f = X.export(books, t, "2026-10-14", datetime(2026, 10, 14, 21, tzinfo=UTC), (1.10, "2026-10-14"), (True, "ok", 0), VAL, 0.56, fx_ecb=(1.20, "2026-10-14"))  # fmt: skip
    card = f["v2"]["strategies"][0]
    q = {"AAA": L.Quote(open=50.8, last=51.5, at="x"), "SPY": L.Quote(open=660.0, last=660.0, at="x")}  # fmt: skip
    # The page-level defaults (200 €, FRED) are ignored: the card carries 5,000 € and the ECB rate.
    est = L.estimate(card, q, 1.10, DAYS[10].date(), 200.0)
    assert est["filled_today"][0]["amount_eur"] > 4900  # one order for ~5,000 €: no fee
    books, _ = E.run(tmp_path / "d", pnl, FX2, DAYS[10], today(t), "y", specs)  # Oct 15
    assert est["value"] == pytest.approx(books[S.SPECS_V2[0].key].values[-1][1], abs=1e-6)
    assert est["pct"] == pytest.approx(est["value"] / 5000 - 1)
    # The live file carries both versions, each against its own S&P 500 yardstick.
    site = _site(tmp_path, f)
    out = L.run(site, datetime(2026, 10, 15, 15, 0, tzinfo=UTC), quote_source=lambda tks, d: {k: q[k] for k in tks if k in q})  # fmt: skip
    assert out is not None and out["benchmark_v2"]["key"] == "sp500-v2"
    assert S.SPECS_V2[0].key in out["strategies"]
    assert out["strategies"][S.SPECS_V2[0].key]["vs_benchmark"] is not None


def test_an_opening_price_seen_once_is_kept_for_the_rest_of_the_day() -> None:
    calls = iter([
        {"AAA": L.Quote(open=50.5, last=51.0, at="1")},
        {"AAA": L.Quote(open=None, last=52.0, at="2")},
    ])  # fmt: skip
    opens: dict[str, float] = {}
    src = L.remembered(lambda tks, d: next(calls), opens)
    assert src(["AAA"], date(2026, 10, 15))["AAA"].open == 50.5
    q = src(["AAA"], date(2026, 10, 15))["AAA"]
    assert q.open == 50.5 and q.last == 52.0


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, s: float) -> None:
        self.now += pd.Timedelta(seconds=s).to_pytimedelta()


def test_the_loop_waits_for_the_open_publishes_every_minute_and_stops_after_the_close(
    tmp_path: Path,
) -> None:
    f, _ = _card(tmp_path / "d", 8, [50.0] * 12, [50.0] * 12)
    site = _site(tmp_path, f)
    clock = _Clock(datetime(2026, 10, 14, 13, 25, tzinfo=UTC))  # 9:25 New York
    published: list[str] = []
    fails = iter([True])  # the first update fails once (a push, a price source): the loop goes on

    def publish(p: Path, at: datetime) -> None:
        if next(fails, False):
            raise RuntimeError("push failed")
        published.append(json.loads(p.read_text(encoding="utf-8"))["generated_at"])

    def quotes(tks: list[str], d: date) -> dict[str, L.Quote]:
        return {t: L.Quote(open=50.0 if t == "AAA" else 660.0, last=51.0, at="x") for t in tks}

    over: list[int] = []
    more = L.loop(site, publish, 600, quotes, every=60, clock=clock, sleep=clock.sleep, day_over=lambda: over.append(1))  # fmt: skip
    # 9:30 to 16:09: 400 minutes, the first one failed; nothing before the open
    assert more is False and len(published) == 399 and over == [1]
    assert published[0] == "2026-10-14T13:31:00Z" and published[-1] == "2026-10-14T20:09:00Z"


def test_the_loop_hands_over_when_its_time_is_up(tmp_path: Path) -> None:
    f, _ = _card(tmp_path / "d", 8, [50.0] * 12, [50.0] * 12)
    site = _site(tmp_path, f)
    clock = _Clock(datetime(2026, 10, 14, 14, 0, tzinfo=UTC))
    n: list[int] = []
    over: list[int] = []
    more = L.loop(site, lambda p, at: n.append(1), 30, lambda t, d: {}, every=60, clock=clock, sleep=clock.sleep, day_over=lambda: over.append(1))  # fmt: skip
    assert more is True and len(n) == 30 and over == []  # the next run keeps the minute tags


def test_the_live_branch_is_one_commit_and_each_minute_gets_a_tag_kept_15_minutes(
    tmp_path: Path,
) -> None:
    import subprocess

    def git(cwd: Path, *a: str) -> str:
        return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()  # fmt: skip

    origin, work = tmp_path / "origin.git", tmp_path / "work"
    origin.mkdir()
    work.mkdir()
    git(origin, "init", "-q", "--bare")
    git(work, "init", "-q")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "config", "user.name", "t")
    git(work, "config", "user.email", "t@example.com")
    src = tmp_path / "strategies_live.json"
    publish = L.GitPublisher(work)
    t0 = datetime(2026, 10, 15, 13, 53, 31, tzinfo=UTC)
    assert L.minute_tag(t0) == "live-20261015-1353"
    for i in range(18):  # 13:53 to 14:10
        src.write_text(f'{{"v": {i}}}', encoding="utf-8")
        publish(src, t0 + pd.Timedelta(minutes=i).to_pytimedelta())
    assert git(origin, "rev-list", "--count", "live") == "1"
    assert git(origin, "show", "live:strategies_live.json") == '{"v": 17}'
    tags = git(origin, "tag", "--list").split()
    assert tags[0] == "live-20261015-1355" and tags[-1] == "live-20261015-1410" and len(tags) == 16
    assert git(origin, "show", "live-20261015-1400:strategies_live.json") == '{"v": 7}'
    # A new run (a hand-over) finds the tags already there; after the close all of them go.
    again = L.GitPublisher(work)
    assert len(again.tags) == 16
    again.finish()
    assert git(origin, "tag", "--list") == ""
