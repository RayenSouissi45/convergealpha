"""Live estimate of every paper strategy during US trading hours (paper money only).

The sealed trade ledger is written only after the close. During the day this estimates what each
strategy is worth right now, the same way the engine will value it tonight:

- orders waiting for today's open are filled at today's official opening price, sells first, then
  the buys share the cash equally, with half the spread and the fee (the engine's rules);
- every holding is marked at its latest price (Yahoo, about 15 minutes delayed), in euros at the
  same EUR/USD rate the last official update used.

Nothing here is recorded anywhere: strategies_live.json is replaced by the official numbers after
the close, and the page says it is an estimate.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from time import sleep as _sleep
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from convergealpha.decide import costs as C
from convergealpha.util.calendar import is_trading_day
from convergealpha.util.io import write_json
from convergealpha.util.log import get

log = get(__name__)

NEW_YORK = ZoneInfo("America/New_York")
OPEN, CLOSE = time(9, 30), time(16, 0)
DEFAULT_SPREAD = 0.002  # when an order or holding carries no spread (files from before Oct 14)


@dataclass(frozen=True)
class Quote:
    open: float | None  # today's official opening price (None before the open)
    last: float  # latest price
    at: str  # when the latest price was taken, ISO time


def market_state(now: datetime) -> str:
    """pre-open | open | closed (after the close, a weekend or a holiday)."""
    ny = now.astimezone(NEW_YORK)
    if not is_trading_day(ny.date()):
        return "closed"
    if ny.time() < OPEN:
        return "pre-open"
    if ny.time() < CLOSE:
        return "open"
    return "closed"


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def _spread(item: Mapping[str, Any]) -> float:
    s = _f(item.get("spread"))
    return s if s is not None and s >= 0 else DEFAULT_SPREAD


def card_fees(card: Mapping[str, Any]) -> C.Fees:
    """The card's fee rule (version 2 orders of 500 € or more are free on finanzen.net zero)."""
    zero = card.get("fee_rule") == "zero"
    return C.Fees(fractional=bool(card.get("benchmark")), free_from=C.ZERO_FEE_FREE_FROM if zero else None)  # fmt: skip


def estimate(card: Mapping[str, Any], quotes: Mapping[str, Quote], fx: float, today: date, capital: float = 200.0) -> dict[str, Any]:  # fmt: skip
    """One strategy's value right now, from its last official card and today's prices. The card's
    own capital and EUR/USD rate win over the defaults (version 2 uses 5,000 € and the ECB)."""
    fees = card_fees(card)
    capital = _f(card.get("capital")) or capital
    fx = _f(card.get("fx_rate")) or fx
    cash = float(card.get("cash") or 0.0)
    held: dict[str, dict[str, Any]] = {
        h["ticker"]: {
            "ticker": h["ticker"],
            "shares": float(h["shares"]),
            "entry_usd": _f(h.get("entry_usd")),
            "prev_usd": _f(h.get("close_usd")),
            "cost_eur": _f(h.get("cost_eur")),
            "bought_today": False,
        }
        for h in card.get("holdings") or []
    }
    filled: list[dict[str, Any]] = []
    waiting: list[dict[str, Any]] = []
    due = [o for o in card.get("pending") or [] if str(o.get("fill_on", "")) <= today.isoformat()]
    later = [o for o in card.get("pending") or [] if o not in due]

    def opened(tk: str) -> float | None:
        q = quotes.get(tk)
        return q.open if q is not None and q.open is not None and q.open > 0 else None

    for o in [o for o in due if o["side"] == "sell"]:
        h = held.get(o["ticker"])
        op = opened(o["ticker"])
        if h is None or op is None:
            waiting.append(o)
            continue
        got = C.sell_value_fees(h["shares"], op, fx, _spread(o), fees)
        cash += got
        filled.append({"side": "sell", "ticker": o["ticker"], "shares": h["shares"], "open_usd": op, "amount_eur": got})  # fmt: skip
        del held[o["ticker"]]
    buys = [o for o in due if o["side"] == "buy"]
    for i, o in enumerate(buys):
        op = opened(o["ticker"])
        if op is None:
            waiting += buys[i:]
            break
        b = C.buy(cash / (len(buys) - i), op, fx, _spread(o), fees)
        if b.shares <= 0:
            filled.append({"side": "buy", "ticker": o["ticker"], "shares": 0.0, "open_usd": op, "amount_eur": 0.0, "note": "one share cost more than the money available"})  # fmt: skip
            continue
        cash -= b.spent
        held[o["ticker"]] = {"ticker": o["ticker"], "shares": b.shares, "entry_usd": op, "prev_usd": op, "cost_eur": b.spent, "bought_today": True}  # fmt: skip
        filled.append({"side": "buy", "ticker": o["ticker"], "shares": b.shares, "open_usd": op, "amount_eur": b.spent})  # fmt: skip

    value = cash
    holdings = []
    priced = True
    for h in held.values():
        q = quotes.get(h["ticker"])
        px = q.last if q is not None and q.last > 0 else h["prev_usd"]
        if q is None:
            priced = False
        if px is None:
            continue
        v = h["shares"] * px / fx
        value += v
        holdings.append({
            "ticker": h["ticker"], "shares": h["shares"], "price_usd": px, "value_eur": v,
            "entry_usd": h["entry_usd"], "cost_eur": h["cost_eur"],
            "move": px / h["entry_usd"] - 1 if h["entry_usd"] else None,
            "day_move": px / h["prev_usd"] - 1 if h["prev_usd"] else None,
            "gain_eur": v - h["cost_eur"] if h["cost_eur"] is not None else None,
            "bought_today": h["bought_today"], "live": q is not None,
        })  # fmt: skip
    official = _f(card.get("value"))
    return {
        "key": card["key"],
        "value": value,
        "pct": value / capital - 1,
        "day_change_eur": value - official if official is not None else None,
        "cash": cash,
        "holdings": holdings,
        "filled_today": filled,
        "waiting": [{"side": o["side"], "ticker": o["ticker"]} for o in [*waiting, *later]],
        "all_priced": priced,
    }


def _plausible_open(r: Mapping[str, Any]) -> float | None:
    """The bar's open, or None when it cannot be today's. Early in the session Yahoo's bar for
    today can still carry yesterday's open (15 Oct 2026: HIG "opened" at 130.47, yesterday's open,
    while it traded between 133.62 and 134.66 all morning). A real open lies within the day's range."""
    op = _f(r.get("open"))
    lo, hi = _f(r.get("low")), _f(r.get("high"))
    if op is None or lo is None or hi is None:
        return op
    return op if lo * (1 - 1e-4) <= op <= hi * (1 + 1e-4) else None


def yahoo_quotes(tickers: list[str], today: date) -> dict[str, Quote]:
    """Today's open and latest price from Yahoo's daily bar (about 15 minutes delayed). An open
    outside the day's range is left out (None), so it is asked from the fallback source."""
    from datetime import timedelta

    from convergealpha.sources.prices import download

    out: dict[str, Quote] = {}
    if not tickers:
        return out
    bars = download(tickers, today - timedelta(days=5), batch_size=150, pause=0.5)
    if bars.empty:
        return out
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    for tk, g in bars.sort_values("date").groupby("ticker"):
        r = g.iloc[-1]
        if pd.Timestamp(r["date"]).date() != today:
            continue
        last = _f(r["close"])
        if last is None or last <= 0:
            continue
        out[str(tk)] = Quote(open=_plausible_open(r), last=last, at=stamp)
    return out


def finnhub_quotes(api_key: str) -> Callable[[list[str], date], dict[str, Quote]]:
    """Finnhub's free quote (real time for US stocks), polite to its 60 calls a minute."""

    def get(tickers: list[str], today: date) -> dict[str, Quote]:
        import time as _time

        from convergealpha.sources import finnhub as FH

        s = FH.session(api_key)
        out: dict[str, Quote] = {}
        for tk in tickers[:50]:
            q = FH.quote(s, tk)
            _time.sleep(1.1)
            if not q or not q.get("c"):
                continue
            t = q.get("t")
            when = datetime.fromtimestamp(t, UTC) if t else datetime.now(UTC)
            if when.astimezone(NEW_YORK).date() != today:
                continue
            out[tk] = Quote(
                open=q.get("o") or None, last=q["c"], at=when.isoformat(timespec="seconds")
            )
        return out

    return get


def run(
    site_dir: Path,
    now: datetime,
    quote_source: Callable[[list[str], date], dict[str, Quote]] = yahoo_quotes,
    fallback: Callable[[list[str], date], dict[str, Quote]] | None = None,
) -> dict[str, Any] | None:
    """Write strategies_live.json next to strategies.json. Returns what was written (None if the
    strategies are not live yet)."""
    path = site_dir / "strategies.json"
    if not path.is_file():
        return None
    f = json.loads(path.read_text(encoding="utf-8"))
    fx = _f((f.get("fx") or {}).get("rate"))
    if f.get("status") != "live" or not fx:
        return None
    v2 = f.get("v2") or {}
    groups = [
        ([*(f.get("strategies") or []), *(f.get("strategies_all") or [])], f.get("benchmark"), "benchmark"),
        ([*(v2.get("strategies") or []), *(v2.get("strategies_all") or [])], v2.get("benchmark"), "benchmark_v2"),
    ]  # fmt: skip
    cards = [c for g in groups for c in g[0]]
    benches = [g[1] for g in groups if g[1]]
    state = market_state(now)
    today = now.astimezone(NEW_YORK).date()
    out: dict[str, Any] = {
        "generated_at": now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "official_as_of": f.get("as_of"),
        "market": state,
        "fx": fx,
        "source": "Yahoo daily bar, about 15 minutes delayed",
        "strategies": {},
        "benchmark": None,
        "benchmark_v2": None,
    }
    if (
        state == "pre-open"
        or not is_trading_day(today)
        or (f.get("as_of") or "") >= today.isoformat()
    ):
        # Nothing has traded since the official numbers: the page shows those.
        out["note"] = (
            "waiting for the open"
            if state == "pre-open"
            else "no trading since the official numbers"
        )
        write_json(out, site_dir / "strategies_live.json")
        return out
    tickers = sorted({
        t for c in [*cards, *benches]
        for t in [*(h["ticker"] for h in c.get("holdings") or []), *(o["ticker"] for o in c.get("pending") or [])]
    })  # fmt: skip
    quotes = quote_source(tickers, today)
    # Orders due today need today's opening price; ask the fallback for those Yahoo has no open for.
    due = {
        o["ticker"] for c in [*cards, *benches] for o in c.get("pending") or []
        if str(o.get("fill_on", "")) <= today.isoformat()
    }  # fmt: skip
    missing = [t for t in tickers if t not in quotes or (t in due and quotes[t].open is None)]
    if missing and fallback is not None:
        got = fallback(missing, today)
        quotes = {**quotes, **{t: q for t, q in got.items() if t not in quotes or quotes[t].open is None}}  # fmt: skip
        out["source"] += "; Finnhub for the rest and for opening prices Yahoo did not have"
    times = sorted(q.at for q in quotes.values())
    out["prices_at"] = times[-1] if times else None
    out["priced"] = f"{len(quotes)} of {len(tickers)} stocks"
    capital = _f(f.get("capital")) or 200.0
    for group, bench, slot in groups:
        bench_est = estimate(bench, quotes, fx, today, capital) if bench else None
        bench_pct = bench_est["pct"] if bench_est else None
        for c in group:
            e = estimate(c, quotes, fx, today, capital)
            e["vs_benchmark"] = e["pct"] - bench_pct if bench_pct is not None else None
            out["strategies"][c["key"]] = e
        out[slot] = bench_est
    write_json(out, site_dir / "strategies_live.json")
    log.info("live strategies: %s, %s priced", state, out["priced"])
    return out


QuoteSource = Callable[[list[str], date], dict[str, Quote]]
LAST_LOOK = time(16, 10)  # a few minutes after the close, so the closing prices are in


def remembered(source: QuoteSource, opens: dict[str, float]) -> QuoteSource:
    """The same source, but an opening price seen once today is kept: a stock whose Yahoo open is
    missing is asked from Finnhub once, not every minute."""

    def get(tickers: list[str], today: date) -> dict[str, Quote]:
        out: dict[str, Quote] = {}
        for tk, q in source(tickers, today).items():
            if q.open is not None:
                opens[tk] = q.open
            elif tk in opens:
                q = Quote(open=opens[tk], last=q.last, at=q.at)
            out[tk] = q
        return out

    return get


TAG_PREFIX = "live-"


def minute_tag(at: datetime) -> str:
    """live-20261015-1353: the tag of one minute's values (UTC), as the page builds it."""
    return TAG_PREFIX + at.astimezone(UTC).strftime("%Y%m%d-%H%M")


class GitPublisher:
    """Publish the live file to `work`'s origin, as the only content of a one-commit commit:
    - the `live` branch is replaced each minute (repository history does not grow), but GitHub's
      raw file server keeps a branch's old content for up to 5 minutes;
    - so the same commit also gets a tag named after its minute (live-20261015-1353): a name never
      asked for before is never stale, and the page asks for the last few minutes' names.
    Tags older than `keep` are deleted as the day goes on, and all of them after the close."""

    def __init__(self, work: Path, branch: str = "live", keep: timedelta = timedelta(minutes=15)) -> None:  # fmt: skip
        self.work, self.branch, self.keep = work, branch, keep
        self.tags: dict[str, datetime] = {}
        # Tags left by an earlier run (another run of today, or a day that ended early).
        for line in self._git("ls-remote", "--tags", "origin", f"refs/tags/{TAG_PREFIX}*").splitlines():  # fmt: skip
            name = line.split("refs/tags/", 1)[-1]
            try:
                at = datetime.strptime(name, TAG_PREFIX + "%Y%m%d-%H%M").replace(tzinfo=UTC)
            except ValueError:
                continue
            self.tags[name] = at

    def _git(self, *args: str, check: bool = True) -> str:
        import subprocess

        r = subprocess.run(["git", "-C", str(self.work), *args], check=check, capture_output=True, text=True)  # fmt: skip
        return r.stdout.strip()

    def _delete(self, names: list[str]) -> None:
        if names:  # best effort: a tag already gone must not block the next minute
            self._git("push", "-q", "origin", *(f":refs/tags/{n}" for n in names), check=False)
            for n in names:
                self.tags.pop(n, None)

    def __call__(self, src: Path, at: datetime) -> None:
        import shutil

        shutil.copyfile(src, self.work / src.name)
        self._git("add", src.name)
        stamp = at.astimezone(UTC).isoformat(timespec="seconds")
        commit = self._git("commit-tree", self._git("write-tree"), "-m", f"live strategy values {stamp}")  # fmt: skip
        tag = minute_tag(at)
        self._git("push", "-q", "-f", "origin", f"{commit}:refs/heads/{self.branch}", f"{commit}:refs/tags/{tag}")  # fmt: skip
        self.tags[tag] = at
        self._delete([n for n, t in self.tags.items() if at - t > self.keep])

    def finish(self) -> None:
        """After the close: the branch alone is enough (its 5-minute delay no longer matters)."""
        self._delete(list(self.tags))


def loop(
    site_dir: Path,
    publish: Callable[[Path, datetime], None],
    minutes: float,
    quote_source: QuoteSource = yahoo_quotes,
    fallback: QuoteSource | None = None,
    every: float = 60.0,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = _sleep,
    day_over: Callable[[], None] | None = None,
) -> bool:
    """Write and publish the live estimate every `every` seconds while New York trades, until a few
    minutes after the close or for at most `minutes`. Returns True when the trading day is not over
    yet, so the caller starts another run (a GitHub job may last at most 6 hours)."""
    opens: dict[str, float] = {}
    source = remembered(quote_source, opens)
    backup = remembered(fallback, opens) if fallback is not None else None
    end = clock() + timedelta(minutes=minutes)
    published = 0
    while True:
        now = clock()
        ny = now.astimezone(NEW_YORK)
        if not is_trading_day(ny.date()) or ny.time() >= LAST_LOOK:
            log.info("live loop: trading day over, %d updates published", published)
            if day_over is not None:
                day_over()
            return False
        if now >= end:
            log.info("live loop: time is up, %d updates published; another run continues", published)  # fmt: skip
            return True
        if ny.time() >= OPEN:
            try:
                if run(site_dir, now, source, backup) is not None:
                    publish(site_dir / "strategies_live.json", now)
                    published += 1
            except Exception:  # one bad minute (a price source, a push) must not end the day
                log.exception("live update failed; trying again next minute")
        # On the minute: each minute's tag is up a few seconds after it starts, and the page asks
        # for the current minute only from second 20 (a name asked for too early stays "not found"
        # on GitHub's raw server for minutes).
        sleep(max(1.0, (math.floor(now.timestamp() / every) + 1) * every - clock().timestamp()))


__all__ = [
    "GitPublisher",
    "Quote",
    "card_fees",
    "estimate",
    "finnhub_quotes",
    "loop",
    "market_state",
    "minute_tag",
    "remembered",
    "run",
    "yahoo_quotes",
]
