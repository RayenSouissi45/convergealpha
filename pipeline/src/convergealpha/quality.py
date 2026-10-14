"""Data quality: today's prices are checked before anything uses them.

1. Impossible values: a close at or below zero, a high below the low, a close outside the day's range.
2. Jumps: a move of more than 50% in one day without a recorded split (often a missed split or a
   bad tick, sometimes real news).
3. Frozen prices: the same close for 5 trading days in a row (a halted stock or a feed that stopped).
4. A second source: Finnhub's free quote for the stocks that matter most (the paper strategies'
   holdings and orders, the top picks, SPY and every stock flagged above). A close more than 2% away
   from Finnhub's is a warning; more than 10% is treated as wrong data.

A stock with impossible, frozen or clearly wrong prices, or with a jump the second source does not
confirm, is blocked for new buys that day ("price data failed a check"); nothing is deleted or
changed in the stored prices. The result is on Health and in the incident log.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

from convergealpha.util.log import get

log = get(__name__)

JUMP = 0.5  # one-day move that needs a second look
FROZEN_DAYS = 5
WARN_GAP = 0.02  # second source more than 2% away: a warning
BAD_GAP = 0.10  # more than 10% away: wrong data
SAMPLE = 55  # Finnhub's free tier allows 60 calls a minute


@dataclass(frozen=True)
class Issue:
    ticker: str
    kind: str  # impossible | jump | frozen | mismatch
    detail: str
    blocks: bool  # blocks new buys today

    def export(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "kind": self.kind,
            "detail": self.detail,
            "blocks": self.blocks,
        }


def _col(frame: pd.DataFrame | None, day: pd.Timestamp) -> pd.Series:
    if frame is None or frame.empty or day not in frame.index:
        return pd.Series(dtype=float)
    return frame.loc[day]


def split_days(events: pd.DataFrame | None) -> set[tuple[str, pd.Timestamp]]:
    if events is None or events.empty:
        return set()
    return {(str(r.ticker), pd.Timestamp(r.date)) for r in events.itertuples()}


def check_prices(
    close: pd.DataFrame,
    high: pd.DataFrame | None,
    low: pd.DataFrame | None,
    as_of: pd.Timestamp,
    tickers: Iterable[str],
    splits: set[tuple[str, pd.Timestamp]] | None = None,
) -> list[Issue]:
    """Checks 1-3 on the stocks priced on `as_of`."""
    if close.empty or as_of not in close.index:
        return []
    want = [t for t in tickers if t in close.columns]
    c = close.loc[:as_of, want].iloc[-30:]
    today = c.iloc[-1]
    priced = today.dropna()
    hi, lo = _col(high, as_of).reindex(priced.index), _col(low, as_of).reindex(priced.index)
    prev = c.iloc[:-1].ffill().iloc[-1].reindex(priced.index) if len(c) > 1 else None
    splits = splits or set()
    out: list[Issue] = []
    for tk, px in priced.items():
        tk = str(tk)
        h, low_ = hi.get(tk), lo.get(tk)
        if not (px > 0):
            out.append(Issue(tk, "impossible", f"close {px:g}", True))
            continue
        if pd.notna(h) and pd.notna(low_):
            if h < low_:
                out.append(Issue(tk, "impossible", f"high {h:g} below low {low_:g}", True))
                continue
            if px > h * 1.01 or px < low_ * 0.99:
                out.append(Issue(tk, "impossible", f"close {px:g} outside the day's range {low_:g}–{h:g}", True))  # fmt: skip
                continue
        if prev is not None:
            p0 = prev.get(tk)
            if pd.notna(p0) and p0 > 0 and abs(px / p0 - 1) > JUMP and (tk, as_of) not in splits:
                out.append(Issue(tk, "jump", f"{px / p0 - 1:+.0%} in one day without a recorded split", True))  # fmt: skip
                continue
        tail = c[tk].dropna().iloc[-FROZEN_DAYS:]
        if len(tail) == FROZEN_DAYS and tail.nunique() == 1:
            out.append(Issue(tk, "frozen", f"the same close ({px:g}) for {FROZEN_DAYS} trading days", True))  # fmt: skip
    return out


def sample(issues: Sequence[Issue], must: Sequence[str], ranked: Sequence[str], n: int = SAMPLE) -> list[str]:  # fmt: skip
    """Which stocks to ask the second source about: flagged jumps first (a confirmation lifts the
    block), then what the paper strategies hold or will trade, then the top of the list."""
    jumps = [i.ticker for i in issues if i.kind == "jump"]
    return list(dict.fromkeys([*jumps, *must, *ranked]))[:n]


def cross_check(
    close: pd.DataFrame,
    as_of: pd.Timestamp,
    quotes: Mapping[str, Mapping[str, float]],
) -> tuple[list[Issue], set[str]]:
    """Compare today's close with the second source. Returns (mismatches, confirmed): `confirmed`
    are the stocks the second source agrees with (within 2%)."""
    out: list[Issue] = []
    ok: set[str] = set()
    if close.empty or as_of not in close.index:
        return out, ok
    today = close.loc[as_of]
    for tk, q in quotes.items():
        px = today.get(tk)
        other = q.get("c")
        if px is None or pd.isna(px) or not other or other <= 0:
            continue
        gap = abs(float(px) / float(other) - 1)
        if gap <= WARN_GAP:
            ok.add(tk)
        else:
            out.append(Issue(tk, "mismatch", f"close {float(px):g} vs {float(other):g} at Finnhub ({gap:.1%} apart)", gap > BAD_GAP))  # fmt: skip
    return out, ok


def finnhub_quotes(api_key: str, pause: float = 1.05) -> Callable[[Sequence[str], pd.Timestamp], dict[str, dict[str, float]]]:  # fmt: skip
    """Finnhub's free quote, only when it is for `as_of` (its time stamp's New York date)."""

    def get(tickers: Sequence[str], as_of: pd.Timestamp) -> dict[str, dict[str, float]]:
        from datetime import UTC, datetime

        from convergealpha.config import NEW_YORK
        from convergealpha.sources import finnhub as FH

        s = FH.session(api_key)
        out: dict[str, dict[str, float]] = {}
        for tk in tickers:
            q = FH.quote(s, tk.replace("-", "."))
            time.sleep(pause)
            if not q or not q.get("t"):
                continue
            day = datetime.fromtimestamp(q["t"], UTC).astimezone(NEW_YORK).date()
            if day == as_of.date():
                out[tk] = q
        return out

    return get


@dataclass
class Report:
    checked: int
    issues: list[Issue]
    cross_checked: int
    confirmed: int
    source: str | None

    @property
    def blocked(self) -> dict[str, str]:
        return {i.ticker: f"{i.kind}: {i.detail}" for i in self.issues if i.blocks}

    def export(self) -> dict[str, Any]:
        kinds = {k: sum(1 for i in self.issues if i.kind == k) for k in ("impossible", "jump", "frozen", "mismatch")}  # fmt: skip
        return {
            "checked": self.checked,
            "cross_checked": self.cross_checked,
            "confirmed": self.confirmed,
            "second_source": self.source,
            "counts": kinds,
            "blocked": len(self.blocked),
            "issues": [i.export() for i in self.issues[:50]],
        }


def run(
    close: pd.DataFrame,
    high: pd.DataFrame | None,
    low: pd.DataFrame | None,
    as_of: pd.Timestamp,
    tickers: Sequence[str],
    splits: set[tuple[str, pd.Timestamp]],
    must: Sequence[str],
    ranked: Sequence[str],
    quote_source: Callable[[Sequence[str], pd.Timestamp], Mapping[str, Mapping[str, float]]] | None,
) -> Report:
    issues = check_prices(close, high, low, as_of, tickers, splits)
    checked = int(close.loc[as_of].reindex([t for t in tickers if t in close.columns]).notna().sum()) if as_of in close.index else 0  # fmt: skip
    if quote_source is None:
        return Report(checked, issues, 0, 0, None)
    asked = sample(issues, must, ranked)
    try:
        quotes = dict(quote_source(asked, as_of))
    except Exception as e:  # the second source failing must never stop the build
        log.warning("second-source price check failed: %s", e)
        return Report(checked, issues, 0, 0, None)
    mismatches, ok = cross_check(close, as_of, quotes)
    # A jump the second source confirms is real news, not bad data: no block for bad data.
    issues = [i for i in issues if not (i.kind == "jump" and i.ticker in ok)]
    issues += mismatches
    log.info(
        "price check: %d stocks, %d issues, %d of %d confirmed by Finnhub",
        checked, len(issues), len(ok), len(quotes),
    )  # fmt: skip
    return Report(checked, issues, len(quotes), len(ok), "Finnhub")


def apply(t: pd.DataFrame, report: Report) -> int:
    """Mark the stocks whose price failed a check (read by the blocking rules)."""
    t["price_check"] = pd.Series(report.blocked, dtype=object).reindex(t.index)
    return int(t["price_check"].notna().sum())


__all__ = ["Issue", "Report", "apply", "check_prices", "cross_check", "finnhub_quotes", "run", "sample"]  # fmt: skip
