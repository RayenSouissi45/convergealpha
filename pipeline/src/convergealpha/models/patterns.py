"""Per-stock event-pattern engine with a luck test (spec section 8).

Returns are measured from the first tradable price after the event (the next session's open) and
compared with the stock's own average return over the same window in the same calendar years.
A pattern passes only with >= 20 events for the stock (or >= 200 across its industry peers), a
Benjamini-Hochberg false discovery rate <= 10% across ALL patterns tested, the same sign in both
halves of history, and the same sign in the holdout (2024+).

Event types testable with free point-in-time history: earnings vs the prior year (XBRL EPS),
earnings vs consensus (Yahoo earnings dates, ~6 years), opportunistic insider clusters, dividend
raises/cuts, and large gaps on heavy volume. Guidance changes, buybacks, index inclusion and
8-K item history are not available for free with dates, so they are not tested.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
from scipy import stats as st

if TYPE_CHECKING:
    from convergealpha.models.dataset import History

WINDOWS = {"5 trading days": 5, "21 trading days": 21}
HOLDOUT_START = pd.Timestamp("2024-01-01")
MIN_STOCK, MIN_PEERS, FDR = 20, 200, 0.10
METHOD = "Abnormal return = return from the next open minus the stock's own average for that window in the same years. t-test, Benjamini–Hochberg FDR 10%."


def _events(h: History) -> pd.DataFrame:
    p = h.panel
    rows: list[tuple[str, pd.Timestamp, str]] = []
    cik_to_t = {int(c): t for t, c in h.stocks["cik"].dropna().items()}
    # Earnings vs the same quarter last year (XBRL, known from the filing date).
    for r in h.eps_sue.itertuples():
        t = cik_to_t.get(int(r.cik))
        if t is None:
            continue
        kind = (
            "Earnings well above last year (SUE ≥ 2)"
            if r.sue >= 2
            else "Earnings above last year"
            if r.sue > 0
            else "Earnings well below last year (SUE ≤ −2)"
            if r.sue <= -2
            else "Earnings below last year"
        )
        rows.append((t, pd.Timestamp(r.known), kind))
    # Opportunistic insider clusters: the second different buyer within 30 days.
    if not h.trades.empty:
        b = h.trades[(h.trades["code"] == "P") & h.trades["opportunistic"]].sort_values(
            "filing_date"
        )
        for cik, g in b.groupby("issuer_cik"):
            t = cik_to_t.get(int(cik))
            if t is None:
                continue
            last_event = None
            dates = g["filing_date"].to_numpy()
            owners = g["owner_cik"].astype(str).to_numpy()
            for i in range(len(g)):
                window = (dates > dates[i] - np.timedelta64(30, "D")) & (dates <= dates[i])
                if len(set(owners[window])) >= 2 and (
                    last_event is None or dates[i] - last_event > np.timedelta64(60, "D")
                ):
                    rows.append((t, pd.Timestamp(dates[i]), "Opportunistic insider buying cluster"))
                    last_event = dates[i]
    # Dividend raises / cuts (>= 10% vs the previous payment).
    divs = p.dividend
    for t in [c for c in h.stocks.index if c in divs.columns]:
        s = divs[t]
        s = s[s > 0]
        if len(s) < 3:
            continue
        ch = s / s.shift(1) - 1
        for d, v in ch.items():
            if v >= 0.10:
                rows.append((t, d, "Dividend raised ≥ 10%"))
            elif v <= -0.10:
                rows.append((t, d, "Dividend cut ≥ 10%"))
    # Large gaps on heavy volume.
    o, c, v = p.open, p.close.ffill().shift(1), p.volume
    gap = o / c - 1
    vol_ratio = v / v.rolling(50, min_periods=20).mean().shift(1)
    big = (gap.abs() >= 0.05) & (vol_ratio >= 2)
    for t in [x for x in h.stocks.index if x in big.columns]:
        idx = big.index[big[t].fillna(False).to_numpy()]
        for d in idx:
            rows.append(
                (
                    t,
                    d,
                    "Gap up ≥ 5% on heavy volume"
                    if gap.at[d, t] > 0
                    else "Gap down ≥ 5% on heavy volume",
                )
            )
    return pd.DataFrame(rows, columns=["ticker", "date", "event"])


def _abnormal(h: History, ev: pd.DataFrame) -> pd.DataFrame:
    """Return from the first tradable open after the event (`ret`), and the same minus the
    stock's own average for that window in the same year (`abn`)."""
    p = h.panel
    idx = p.close.index
    opens, closes = p.open, p.close
    out = []
    base_cache: dict[tuple[str, int, int], float] = {}
    for name, n in WINDOWS.items():
        fwd = (closes.shift(-(n - 1)) / opens) - 1  # open of day d -> close of day d+n-1
        years = fwd.index.year
        for r in ev.itertuples():
            # Events dated d (news by/after the close) are tradable at the next session's open.
            pos = idx.searchsorted(r.date, side="right")
            if pos >= len(idx) or r.ticker not in fwd.columns:
                continue
            d = idx[pos]
            val = fwd.at[d, r.ticker]
            if pd.isna(val):
                continue
            key = (r.ticker, d.year, n)
            if key not in base_cache:
                col = fwd[r.ticker]
                base_cache[key] = float(col[years == d.year].mean())
            out.append((r.ticker, r.event, name, d, float(val) - base_cache[key], float(val)))
    return pd.DataFrame(out, columns=["ticker", "event", "window", "date", "abn", "ret"])


def _test(x: np.ndarray) -> float:
    if len(x) < 3 or np.std(x, ddof=1) == 0:
        return 1.0
    return float(st.ttest_1samp(x, 0.0).pvalue)


def _robust(g: pd.DataFrame) -> tuple[bool, bool | None]:
    sign = np.sign(g["abn"].mean())
    g = g.sort_values("date")
    dev = g[g["date"] < HOLDOUT_START]
    half = len(dev) // 2
    halves_ok = (
        half >= 3
        and np.sign(dev["abn"].iloc[:half].mean()) == sign
        and np.sign(dev["abn"].iloc[half:].mean()) == sign
    )
    hold = g[g["date"] >= HOLDOUT_START]
    holdout_ok = None if len(hold) < 3 else bool(np.sign(hold["abn"].mean()) == sign)
    return bool(halves_ok), holdout_ok


def benjamini_hochberg(p: np.ndarray) -> np.ndarray:
    """q-values (BH adjusted p-values)."""
    n = len(p)
    if n == 0:
        return p
    order = np.argsort(p)
    ranked = p[order] * n / (np.arange(n) + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.minimum(q, 1.0)
    return out


def run(h: History, stocks: pd.DataFrame) -> dict[str, Any]:
    ev = _events(h)
    if ev.empty:
        return {"tested": 0, "by_ticker": {}, "method": METHOD}
    ab = _abnormal(h, ev)
    groups = stocks["industry_group"].reindex(ab["ticker"]).to_numpy()
    ab["group"] = groups
    tests = []
    for (t, e, w), g in ab.groupby(["ticker", "event", "window"]):
        if len(g) >= MIN_STOCK:
            tests.append(("stock", t, e, w, g))
    for (grp, e, w), g in ab.dropna(subset=["group"]).groupby(["group", "event", "window"]):
        if len(g) >= MIN_PEERS:
            tests.append(("peers", grp, e, w, g))
    if not tests:
        return {"tested": 0, "by_ticker": {}, "method": METHOD}
    pvals = np.array([_test(g["abn"].to_numpy()) for *_, g in tests])
    qvals = benjamini_hochberg(pvals)
    by_ticker: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {"passed": [], "likely_luck": []}
    )
    # Every test's result, so the opportunity badge can say what history shows for an event type
    # even when the pattern did not pass (stock-level tests first, else the industry peers').
    history: dict[str, dict[str, dict[str, dict[str, dict[str, Any]]]]] = {
        "stock": defaultdict(lambda: defaultdict(dict)),
        "peers": defaultdict(lambda: defaultdict(dict)),
    }
    for (scope, key, e, w, g), pv, qv in zip(tests, pvals, qvals, strict=True):
        halves_ok, holdout_ok = _robust(g)
        passed = bool(qv <= FDR and halves_ok and holdout_ok is True)
        rec = {
            "event": e,
            "n": len(g),
            "horizon": w,
            "mean_excess": float(g["abn"].mean()),
            "hit_rate": float((g["abn"] > 0).mean()),
            "mean_return": float(g["ret"].mean()),
            "up_rate": float((g["ret"] > 0).mean()),
            "p_value": float(pv),
            "q_value": float(qv),
            "halves_ok": halves_ok,
            "holdout_ok": holdout_ok,
            "scope": scope,
        }
        history[scope][str(key)][e][w] = {
            k: round(v, 5) if isinstance(v, float) else v
            for k, v in rec.items()
            if k not in ("event", "horizon", "scope")
        } | {"passed": passed}
        looks = pv < 0.05 and not passed
        if not (passed or looks):
            continue
        targets = (
            [key] if scope == "stock" else stocks.index[stocks["industry_group"] == key].tolist()
        )
        for t in targets:
            by_ticker[str(t)]["passed" if passed else "likely_luck"].append(rec)
    for v in by_ticker.values():
        v["passed"] = sorted(v["passed"], key=lambda r: r["q_value"])[:6]
        v["likely_luck"] = sorted(v["likely_luck"], key=lambda r: r["p_value"])[:4]
    n_tests = len(tests)
    return {
        "tested": n_tests,
        "passed_total": int(
            sum(1 for q, (_s, _k, _e, _w, g) in zip(qvals, tests, strict=True) if q <= FDR)
        ),
        "by_ticker": {t: {**v, "tested": n_tests, "method": METHOD} for t, v in by_ticker.items()},
        "history": {s: {k: dict(v) for k, v in d.items()} for s, d in history.items()},
        "groups": {
            str(t): str(g) for t, g in stocks["industry_group"].dropna().items() if str(g) != "nan"
        },
        "method": METHOD,
        "events": len(ev),
    }


def _unused() -> float:
    return math.nan
