"""Data quality checks (impossible, jumping and frozen prices, a second source) and the incident
log (opened once, resolved when the check passes, hash-chained, a same-day re-run adds nothing)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from convergealpha import quality as Q
from convergealpha.decide import rules as R
from convergealpha.ledger import incidents as INC
from convergealpha.ledger import ledger as LG

DAYS = pd.bdate_range("2026-10-01", periods=10)
AS_OF = DAYS[-1]


def frames(**cols: list[float]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    close = pd.DataFrame(cols, index=DAYS[: len(next(iter(cols.values())))])
    return close, close * 1.01, close * 0.99


def walk(start: float = 50.0) -> list[float]:
    return list(start * np.cumprod(1 + 0.01 * np.sin(np.arange(10))))


def test_impossible_jump_and_frozen_prices_are_found() -> None:
    close, high, low = frames(
        OK=walk(), NEG=[*walk()[:9], -1.0], JUMP=[*walk()[:9], walk()[8] * 1.8],
        FROZEN=[*walk()[:5], *([20.0] * 5)], SPLIT=[*walk()[:9], walk()[8] / 2],
    )  # fmt: skip
    high.loc[AS_OF, "OK"] = low.loc[AS_OF, "OK"] * 0.5  # high below low
    issues = Q.check_prices(close, high, low, AS_OF, list(close.columns), {("SPLIT", AS_OF)})
    got = {i.ticker: i.kind for i in issues}
    assert got == {"OK": "impossible", "NEG": "impossible", "JUMP": "jump", "FROZEN": "frozen"}
    assert all(i.blocks for i in issues)


def test_close_outside_the_days_range_is_impossible() -> None:
    close, high, low = frames(A=walk())
    close.loc[AS_OF, "A"] = high.loc[AS_OF, "A"] * 1.05
    assert [i.kind for i in Q.check_prices(close, high, low, AS_OF, ["A"])] == ["impossible"]


def test_second_source_confirms_a_real_jump_and_catches_wrong_prices() -> None:
    close, high, low = frames(JUMP=[*walk()[:9], walk()[8] * 1.8], A=walk(), B=walk(), C=walk())
    quotes = {
        "JUMP": {"c": float(close.loc[AS_OF, "JUMP"]) * 1.005},  # agrees: real news
        "A": {"c": float(close.loc[AS_OF, "A"]) * 1.03},  # 3% apart: a warning only
        "B": {"c": float(close.loc[AS_OF, "B"]) * 1.25},  # 25% apart: wrong data
    }
    asked: list[str] = []

    def source(tks: list[str], d: pd.Timestamp) -> dict[str, dict[str, float]]:
        asked.extend(tks)
        return {t: quotes[t] for t in tks if t in quotes}

    rep = Q.run(close, high, low, AS_OF, ["JUMP", "A", "B", "C"], set(), ["A", "B"], ["C"], source)
    assert asked[0] == "JUMP"  # flagged jumps are asked first
    kinds = {(i.ticker, i.kind, i.blocks) for i in rep.issues}
    assert kinds == {("A", "mismatch", False), ("B", "mismatch", True)}
    assert set(rep.blocked) == {"B"} and rep.confirmed == 1 and rep.source == "Finnhub"


def test_a_failing_second_source_never_stops_the_build() -> None:
    close, high, low = frames(JUMP=[*walk()[:9], walk()[8] * 1.8])

    def broken(tks: list[str], d: pd.Timestamp) -> dict[str, dict[str, float]]:
        raise TimeoutError("down")

    rep = Q.run(close, high, low, AS_OF, ["JUMP"], set(), [], [], broken)
    assert set(rep.blocked) == {"JUMP"} and rep.source is None  # unconfirmed jump stays blocked


def test_a_failed_price_check_blocks_new_buys_with_its_reason() -> None:
    close, high, low = frames(A=walk(), B=[*walk()[:9], -1.0])
    rep = Q.run(close, high, low, AS_OF, ["A", "B"], set(), [], [], None)
    t = pd.DataFrame(index=pd.Index(["A", "B"], name="ticker"))
    assert Q.apply(t, rep) == 1
    blocks = R.blocking_events(t)
    assert blocks["A"] == [] and blocks["B"][0].startswith("price data failed a check (impossible")


def health(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {"sources": [{"id": "prices", "name": "Prices", "status": "ok", "coverage": 0.98, "optional": False}]}  # fmt: skip
    return {**base, **kw}


def test_incidents_open_once_and_resolve_when_the_check_passes(tmp_path: Path) -> None:
    bad = health(trade_ledger={"verified": False, "detail": "hash mismatch at line 3"})
    assert set(INC.detect(bad)) == {"trade_ledger"}
    INC.record(tmp_path, "2026-10-14", INC.detect(bad), "t1")
    assert INC.record(tmp_path, "2026-10-14", INC.detect(bad), "t2") == []  # same-day re-run
    INC.record(tmp_path, "2026-10-15", INC.detect(bad), "t3")  # still open: no second "open"
    INC.record(tmp_path, "2026-10-16", INC.detect(health()), "t4")  # fixed
    INC.record(tmp_path, "2026-10-19", INC.detect(health()), "t5")  # a quiet day is recorded too
    es = LG.read(INC.path(tmp_path))
    assert [(e["kind"], e["status"]) for e in es] == [
        ("incident", "open"), ("check", "unchanged"), ("incident", "resolved"), ("check", "ok"),
    ]  # fmt: skip
    out = INC.export(tmp_path)
    assert out["verified"] and out["open"] == [] and out["days_checked"] == 4
    assert out["days_with_open_incident"] == 2 and out["events"][0]["status"] == "resolved"
    assert out["events"][0]["opened"] == "2026-10-14"


def test_what_counts_as_an_incident() -> None:
    h = health(
        sources=[
            {"id": "prices", "name": "Prices", "status": "ok", "coverage": 0.42, "optional": False},
            {"id": "news", "name": "News", "status": "failed", "optional": False},
            {"id": "danelfin", "name": "Danelfin", "status": "failed", "optional": True},
        ],
        data_quality={"blocked": 1, "issues": [{"ticker": "BOXL", "blocks": True}]},
        fx_check={"ok": False, "max_gap_30d": 0.004, "limit": 0.002},
        kill_switch={"active": True, "reasons": ["data"]},
        forecast_method="fallback",
        trade_ledger={"verified": True, "status": "waiting for the EUR/USD rate from FRED"},
    )
    found = INC.detect(h)
    assert set(found) == {"source_failed", "price_coverage", "price_check", "fx_gap", "kill_switch", "model_fallback", "paper_trading"}  # fmt: skip
    assert found["source_failed"]["detail"] == "News" and found["price_coverage"]["severity"] == "serious"  # fmt: skip
    assert "BOXL" in found["price_check"]["detail"]


def test_tampering_with_the_incident_log_is_detected(tmp_path: Path) -> None:
    INC.record(tmp_path, "2026-10-14", {"fx_gap": {"severity": "warning", "detail": "x"}}, "t")
    INC.record(tmp_path, "2026-10-15", {}, "t")
    p = INC.path(tmp_path)
    p.write_text(p.read_text(encoding="utf-8").replace('"warning"', '"minor"'), encoding="utf-8")
    assert INC.export(tmp_path)["verified"] is False


@pytest.mark.parametrize("n", [0, 3])
def test_sample_puts_jumps_first_and_stays_within_the_free_limit(n: int) -> None:
    issues = [Q.Issue(f"J{i}", "jump", "", True) for i in range(n)]
    s = Q.sample(issues, ["SPY", "AAA"], [f"P{i}" for i in range(100)])
    assert s[:n] == [f"J{i}" for i in range(n)] and len(s) == Q.SAMPLE and s[n] == "SPY"
