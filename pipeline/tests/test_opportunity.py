"""Opportunity badge: green only with a luck-tested event, agreeing evidence and a validated chance
up; news alone never green; hype and risk flags are red."""

from __future__ import annotations

import numpy as np
import pandas as pd

from convergealpha.decide import opportunity as O

VAL = ["P(up) 1m", "P(up) 6m"]
BASE = {"1m": 0.56, "6m": 0.60}


def row(**kw: object) -> pd.Series:
    base = {
        "f1": 65.0, "f2": 62.0, "f3": 70.0, "f4": 40.0, "f5": 50.0, "f6": 55.0,
        "p_up_1m": 0.60, "p_up_6m": 0.62, "eligible": True, "blocked": False, "block_reason": None,
        "label": "NO TRADE", "short_pct_float": 0.03, "change_1d": 0.01, "ret_1w": 0.02,
        "offering_recent": False, "merger_pending": False, "news_negative_tags": None,
    }  # fmt: skip
    return pd.Series({**base, **kw})


def passed(mean: float = 0.02, ok: bool = True) -> dict[str, object]:
    return {"pattern": "Opportunistic insider buying cluster", "scope": "stock", "window": "21 trading days",
            "n": 31, "up_rate": 0.65, "mean_return": 0.03, "mean_excess": mean, "hit_rate": 0.6,
            "q_value": 0.04, "passed": ok, "halves_ok": True, "holdout_ok": True}  # fmt: skip


def cluster(hist: dict[str, object] | None) -> O.Event:
    return O.Event("insider_cluster", "2026-10-12", "3 insiders bought $1.2M", "SEC Form 4 filings",
                   "https://www.sec.gov/", ("Opportunistic insider buying cluster",), history=hist)  # fmt: skip


def news() -> O.Event:
    return O.Event("news", "2026-10-12", "News: “Company raises guidance”", "Reuters", "https://x", news=True)  # fmt: skip


def test_green_needs_every_check() -> None:
    b = O.classify(row(), [cluster(passed())], BASE, VAL, pd.Timestamp("2026-10-13"))
    assert b is not None and b.color == O.GREEN
    assert all(c["ok"] for c in b.checks) and b.missing == []
    assert b.days_since_event == 1


def test_amber_when_something_is_missing() -> None:
    cases = [
        (row(), [cluster(passed(ok=False))], VAL, "did not pass the luck test"),
        (row(f1=50.0, f2=50.0), [cluster(passed())], VAL, "evidence families"),
        (row(p_up_1m=0.58), [cluster(passed())], VAL, "not 3 points above"),
        (row(), [cluster(passed())], [], "not passed validation"),
        (
            row(blocked=True, block_reason="earnings in 3 trading days"),
            [cluster(passed())],
            VAL,
            "Blocked",
        ),
        (row(), [cluster(None)], VAL, "Not enough past events"),
    ]
    for r, evs, val, text in cases:
        b = O.classify(r, evs, BASE, val, pd.Timestamp("2026-10-13"))
        assert b is not None and b.color == O.AMBER, text
        assert any(text in m for m in b.missing), (text, b.missing)


def test_news_alone_is_never_green() -> None:
    # Strong evidence, validated chance up, not blocked: still amber with only a headline.
    strong = row(f4=80.0, f5=75.0, p_up_1m=0.70)
    b = O.classify(strong, [news()], BASE, VAL)
    assert b is not None and b.color == O.AMBER
    assert "news alone is never confirmation" in b.missing[0]
    # Loud news with weak evidence: be careful.
    weak = row(f1=40.0, f2=40.0, f3=40.0)
    b2 = O.classify(weak, [news()], BASE, VAL)
    assert b2 is not None and b2.color == O.RED


def gap() -> O.Event:
    return O.Event("gap_up", "2026-10-12", "Opened 12% higher on 3.1x its usual volume", "Daily prices", None, ("Gap up ≥ 5% on heavy volume",))  # fmt: skip


def test_red_needs_a_jump_or_loud_news_plus_a_risk() -> None:
    for kw, text in (
        ({"offering_recent": True}, "share offering"),
        ({"short_pct_float": 0.22}, "Heavily shorted"),
        ({"news_negative_tags": "going_concern"}, "Going-concern"),
        ({"label": "SELL / RISK WARNING"}, "SELL / RISK WARNING"),
    ):
        # A jump (gap up on volume, or a big daily move) with a risk: be careful.
        b = O.classify(row(**kw), [cluster(passed()), gap()], BASE, VAL)
        assert b is not None and b.color == O.RED and any(text in r for r in b.risks), text
        b = O.classify(row(change_1d=0.14, **kw), [cluster(passed())], BASE, VAL)
        assert b is not None and b.color == O.RED, text
    # Without a jump or loud news it is not hype; the risk is still listed. Offerings and going
    # concern are blocking events (blocked = True in the build), and SELL never goes green.
    for kw, color in (
        ({"short_pct_float": 0.22}, O.GREEN),
        (
            {"offering_recent": True, "blocked": True, "block_reason": "share offering announced"},
            O.AMBER,
        ),
        ({"news_negative_tags": "going_concern", "blocked": True}, O.AMBER),
        ({"label": "SELL / RISK WARNING"}, O.AMBER),
    ):
        b = O.classify(row(**kw), [cluster(passed())], BASE, VAL)
        assert b is not None and b.color == color and b.risks, kw
    # A big jump with weak evidence and no event: hype.
    b = O.classify(row(change_1d=0.25, f1=30.0, f2=30.0, f3=30.0), [], BASE, VAL)
    assert b is not None and b.color == O.RED and "jumped" in b.summary
    # A big jump with decent evidence and no known reason: no badge.
    assert O.classify(row(change_1d=0.12), [], BASE, VAL) is None
    # History says this kind of event is usually followed by a fall: never green; red with a jump.
    b = O.classify(row(), [cluster(passed(mean=-0.03))], BASE, VAL)
    assert b is not None and b.color == O.AMBER and any("worse than normal" in r for r in b.risks)
    b = O.classify(row(change_1d=0.12), [cluster(passed(mean=-0.03))], BASE, VAL)
    assert b is not None and b.color == O.RED


def test_nothing_to_flag() -> None:
    assert O.classify(row(), [], BASE, VAL) is None


def test_history_prefers_the_stock_then_its_industry() -> None:
    rec = {"n": 25, "passed": False, "mean_excess": 0.01}
    hist = {
        "stock": {"AAA": {"Dividend raised ≥ 10%": {"21 trading days": rec}}},
        "peers": {"357": {"Dividend raised ≥ 10%": {"5 trading days": {**rec, "n": 300, "passed": True}, "21 trading days": {**rec, "n": 300}}}},
    }  # fmt: skip
    a = O.history_for("AAA", "357", ("Dividend raised ≥ 10%",), hist)
    assert a is not None and a["scope"] == "stock" and a["n"] == 25
    b = O.history_for("BBB", "357", ("Dividend raised ≥ 10%",), hist)
    # Peers: the window that passed is shown.
    assert (
        b is not None and b["scope"] == "peers" and b["window"] == "5 trading days" and b["passed"]
    )
    assert O.history_for("CCC", np.nan, ("Dividend raised ≥ 10%",), hist) is None


def test_base_rates_pool_the_reliability_buckets() -> None:
    rel = {"horizons": {"1m": {"up": [{"n": 300, "hits": 150, "rate": 0.5}, {"n": 700, "hits": 420, "rate": 0.6}]}}}  # fmt: skip
    assert O.base_rates(rel) == {"1m": 0.57}


def test_export_shape() -> None:
    b = O.classify(row(), [cluster(passed()), news()], BASE, VAL, pd.Timestamp("2026-10-13"))
    assert b is not None
    out = O.export(b, "2026-10-13")
    assert out["color"] == "green" and out["title"] == "Confirmed opportunity"
    assert out["short"] == "Insider cluster buy (Oct 12) +1"
    assert out["events"][0]["history"]["n"] == 31 and out["events"][1]["history"] is None
    assert "luck-tested" in out["events"][1]["history_note"]


def test_news_counts_only_when_the_company_is_the_subject() -> None:
    jpm = O.subject_tokens("JPM", "JP Morgan Chase & Co. Common Stock")
    assert not O.is_about(
        "Biogen Upgraded to Buy at J.P. Morgan. How the Stock Could Rise 28%.", jpm
    )
    assert O.is_about("JPMorgan raises its dividend by 10%", jpm)
    assert O.is_about("JPM stock: analysts upgrade the bank", jpm)
    crm = O.subject_tokens("CRM", "Salesforce, Inc. Common Stock")
    assert O.is_about("Salesforce's AI Strategy Reduces Risk, BofA Says in Upgrade", crm)
    assert not O.is_about("Oracle raises guidance as cloud demand beats Salesforce", crm)
    ter = O.subject_tokens(
        "TX", "Ternium S.A. Ternium S.A. American Depositary Shares (each representing ten shares)"
    )
    assert "ternium" in ter and "american" not in ter
