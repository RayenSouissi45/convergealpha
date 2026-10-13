"""One opportunity badge per stock, built from the signals the app already has.

It joins fresh events (insider buying, earnings, dividends, gaps, estimate changes, analyst
upgrades, news tags) with what the event-pattern engine found for that kind of event (the luck
test), the evidence families, the validated chance of rising and the blocking/risk checks.
Every threshold is fixed here and in docs/METHODOLOGY.md ("Opportunity badge"); none was fitted.

GREEN  "Confirmed opportunity": a fresh positive event (last 7 days) whose kind of event PASSED the
       luck test with a positive average, at least 3 families >= 60, the validated chance up at
       least 3 points above the usual rate for that horizon, eligible and not blocked.
AMBER  "Possible, not confirmed": a fresh positive event, but some of that is missing or weak.
RED    "Hype / be careful": a big jump (or a gap up on heavy volume) or loud news, together with
       weak evidence or a risk flag (heavy short interest, share offering, going concern, ...).
News alone is never green: headlines have no luck-tested history.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from convergealpha.features.evidence import Sources, tradable_reaction
from convergealpha.features.families import FAMILIES, FAMILY_NAMES
from convergealpha.util.calendar import trading_days_between

FRESH_DAYS = 7  # calendar days: an event is fresh if it became public in the last 7 days
STRONG = 60.0  # a family "agrees" at 60 or more (the BUY rules use the same line)
GREEN_FAMILIES = 3
WEAK_FAMILIES = 2  # fewer than 2 families at 60+ = weak evidence
PUP_MARGIN = 0.03  # validated chance up >= usual rate + 3 points
JUMP_1D, JUMP_1W = 0.10, 0.20
SHORT_HIGH = 0.15
EST_RAISE = 0.01  # this year's EPS estimate up at least 1% in 7 days
GAP, GAP_VOLUME = 0.05, 2.0  # same definition as the pattern engine
DIV_RAISE = 0.10
POSITIVE_NEWS_TAGS = ("guidance_up", "buyback", "dividend_up", "upgrade")
WINDOW_PREF = ("21 trading days", "5 trading days")

GREEN, AMBER, RED = "green", "amber", "red"
TITLES = {
    GREEN: "Confirmed opportunity",
    AMBER: "Possible, not confirmed",
    RED: "Hype / be careful",
}
# Most telling first (also the order events are listed in).
PRIORITY = (
    "insider_cluster", "earnings_beat", "earnings_growth", "dividend_raise", "gap_up",
    "upgrade", "estimates_raised", "insider_buy", "news",
)  # fmt: skip
UNTESTED_WHY = {
    "insider_buy": "A single insider's purchase is not tested on its own (only clusters of 2 or more insiders are).",
    "estimates_raised": "Estimate changes have no free dated history, so they cannot be luck-tested.",
    "upgrade": "Analyst upgrades are not luck-tested by the pattern engine yet.",
    "news": "Headlines have no luck-tested history: news alone is never confirmation.",
}


def _sec(cik: Any, form: str) -> str | None:
    try:
        c = int(cik)
    except (TypeError, ValueError):
        return None
    return f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={c:010d}&type={form}&dateb=&owner=include&count=40"


@dataclass
class Event:
    kind: str
    date: str  # YYYY-MM-DD, when it became public
    text: str
    source: str
    url: str | None = None
    patterns: tuple[str, ...] = ()  # tested pattern names for this kind of event
    news: bool = False
    history: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "date": self.date,
            "text": self.text,
            "source": self.source,
            "url": self.url,
            "history": self.history,
            "history_note": None if self.history else self.untested_note(),
        }

    def untested_note(self) -> str:
        if self.kind in UNTESTED_WHY:
            return UNTESTED_WHY[self.kind]
        return "Not enough past events of this kind for this stock or its industry to test (needs 20, or 200 across peers)."


@dataclass
class Badge:
    color: str
    events: list[Event]
    checks: list[dict[str, Any]] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    summary: str = ""
    days_since_event: int | None = None  # trading days since the freshest confirmed event


# --------------------------------------------------------------------------- event detection


def _day(x: Any) -> str:
    return str(pd.Timestamp(x).strftime("%Y-%m-%d"))


def _fresh(ts: pd.Series, as_of: pd.Timestamp, hours: int = 0) -> pd.Series:
    lo = as_of - pd.Timedelta(days=FRESH_DAYS)
    return (ts > lo) & (ts <= as_of + pd.Timedelta(hours=hours))


def _usd(v: float) -> str:
    if v >= 1e6:
        return f"${v / 1e6:.1f}M"
    if v >= 1e3:
        return f"${v / 1e3:.0f}K"
    return f"${v:,.0f}"


def insider_events(t: pd.DataFrame, trades: pd.DataFrame, as_of: pd.Timestamp) -> dict[str, list[Event]]:  # fmt: skip
    """Opportunistic open-market buys filed in the last 7 days: a cluster (2+ insiders within 30
    days, like the pattern engine) or a single insider."""
    out: dict[str, list[Event]] = {}
    if trades.empty or "cik" not in t:
        return out
    b = trades[
        (trades["code"] == "P")
        & trades["opportunistic"].astype(bool)
        & (trades["filing_date"] <= as_of)
        & (trades["filing_date"] > as_of - pd.Timedelta(days=30))
    ]
    if b.empty:
        return out
    cik_to_t: dict[int, list[str]] = {}
    for tk, c in t["cik"].dropna().items():
        cik_to_t.setdefault(int(c), []).append(str(tk))
    for cik, g in b.groupby("issuer_cik"):
        recent = g[_fresh(g["filing_date"], as_of)]
        if recent.empty or int(cik) not in cik_to_t:
            continue
        buyers = g["owner_cik"].nunique()
        last = recent["filing_date"].max()
        value = float(g["value"].sum())
        roles = ", ".join(sorted({str(x) for x in g["title"].dropna() if str(x).strip()})[:3])
        if buyers >= 2:
            ev = Event(
                "insider_cluster",
                _day(last),
                f"{buyers} insiders bought {_usd(value)} of shares on the open market in 30 days"
                + (f" ({roles})" if roles else "")
                + ", not routine or pre-planned trades",
                "SEC Form 4 filings",
                _sec(cik, "4"),
                ("Opportunistic insider buying cluster",),
            )
        else:
            # Form 4 names are "Last First Middle": say the role instead, it reads better.
            role = str(recent.iloc[-1].get("title") or "").strip()
            who = f"An insider ({role})" if role and role.lower() != "nan" else "An insider"
            ev = Event(
                "insider_buy",
                _day(last),
                f"{who} bought {_usd(float(recent['value'].sum()))} of shares on the open market",
                "SEC Form 4 filings",
                _sec(cik, "4"),
            )
        for tk in cik_to_t[int(cik)]:
            out.setdefault(tk, []).append(ev)
    return out


def earnings_events(t: pd.DataFrame, src: Sources, as_of: pd.Timestamp, eps_sue: pd.DataFrame | None) -> dict[str, list[Event]]:  # fmt: skip
    """Beat expectations with a positive first trading day (Yahoo calendar), and EPS above the
    same quarter last year in a 10-Q/10-K filed in the last 7 days (SEC XBRL)."""
    out: dict[str, list[Event]] = {}
    e = src.earnings_dates
    if not e.empty and {"eps_actual", "eps_estimate"} <= set(e.columns):
        w = e[_fresh(pd.to_datetime(e["datetime"]), as_of, hours=23)]
        w = w.dropna(subset=["eps_actual", "eps_estimate"])
        w = w[(w["eps_actual"] > w["eps_estimate"]) & w["ticker"].isin(t.index)]
        for r in w.sort_values("datetime").drop_duplicates("ticker", keep="last").itertuples():
            r1, _r5, first = tradable_reaction(
                src.panel,
                r.ticker,
                pd.Timestamp(r.datetime),
                bool(getattr(r, "after_close", False)),
            )
            if first is not None and first <= as_of and math.isfinite(r1) and r1 <= 0:
                continue  # beat, but the stock fell when it could first be traded: not positive
            sue = float(t.at[r.ticker, "sue"]) if "sue" in t and pd.notna(t.at[r.ticker, "sue"]) else math.nan  # fmt: skip
            pct = getattr(r, "surprise_pct", math.nan)
            beat = f"{float(pct):+.0f}%" if pct is not None and pd.notna(pct) else "above estimates"
            known = first is not None and first <= as_of and math.isfinite(r1)
            react = (
                f", and the stock rose {r1:.1%} on the first trading day"
                if known
                else "; the first trading reaction is not known yet"
            )
            out.setdefault(r.ticker, []).append(
                Event(
                    "earnings_beat" if known else "earnings_beat_pending",
                    _day(r.datetime),
                    f"Earnings beat expectations ({beat}){react}",
                    "Earnings calendar (Yahoo Finance) and company 8-K",
                    _sec(t.at[r.ticker, "cik"], "8-K"),
                    ("Earnings well above last year (SUE ≥ 2)",)
                    if sue >= 2
                    else ("Earnings above last year",),
                )
            )
    if eps_sue is not None and not eps_sue.empty and "cik" in t:
        s = eps_sue[_fresh(pd.to_datetime(eps_sue["known"]), as_of) & (eps_sue["sue"] > 0)]
        cik_to_t = {int(c): str(tk) for tk, c in t["cik"].dropna().items()}
        for r in s.sort_values("known").drop_duplicates("cik", keep="last").itertuples():
            tk = cik_to_t.get(int(r.cik))
            if tk is None:
                continue
            well = float(r.sue) >= 2
            out.setdefault(tk, []).append(
                Event(
                    "earnings_growth",
                    _day(r.known),
                    f"Earnings per share {'well ' if well else ''}above the same quarter last year "
                    f"(standardized surprise {float(r.sue):.1f}) in a new SEC filing",
                    "SEC XBRL financial statements (10-Q/10-K)",
                    _sec(r.cik, "10-Q"),
                    ("Earnings well above last year (SUE ≥ 2)",)
                    if well
                    else ("Earnings above last year",),
                )
            )
    return out


def price_events(t: pd.DataFrame, src: Sources, as_of: pd.Timestamp) -> dict[str, list[Event]]:
    """Dividend raised >= 10% (ex-date in the last 7 days) and gaps up >= 5% on >= 2x volume in
    the last 5 sessions (the pattern engine's definitions)."""
    out: dict[str, list[Event]] = {}
    p = src.panel
    cols = [c for c in t.index if c in p.close.columns]
    if not cols:
        return out
    tail = p.close.index[-300:]
    div = p.dividend.loc[tail, cols].astype("float64")
    recent_rows = div.index[div.index > as_of - pd.Timedelta(days=FRESH_DAYS)]
    has = div.loc[recent_rows].gt(0).any()
    for tk in has[has].index:
        s = div[tk]
        s = s[s > 0]
        if len(s) < 2 or s.index[-1] not in recent_rows:
            continue
        last, prev = float(s.iloc[-1]), float(s.iloc[-2])
        if prev > 0 and last / prev - 1 >= DIV_RAISE:
            out.setdefault(str(tk), []).append(
                Event(
                    "dividend_raise",
                    _day(s.index[-1]),
                    f"Dividend raised {last / prev - 1:.0%} (${last:.2f} a share, was ${prev:.2f})",
                    "Daily prices and dividends (Yahoo Finance)",
                    _sec(t.at[tk, "cik"], "8-K"),
                    ("Dividend raised ≥ 10%",),
                )
            )
    o = p.open.loc[tail, cols].astype("float64")
    c = p.close.loc[tail, cols].astype("float64").ffill().shift(1)
    v = p.volume.loc[tail, cols].astype("float64")
    gap = o / c - 1
    vr = v / v.rolling(50, min_periods=20).mean().shift(1)
    big = (gap >= GAP) & (vr >= GAP_VOLUME)
    last5 = big.iloc[-5:]
    for tk in last5.columns[last5.any().to_numpy()]:
        d = last5.index[last5[tk].to_numpy()][-1]
        out.setdefault(str(tk), []).append(
            Event(
                "gap_up",
                _day(d),
                f"Opened {gap.at[d, tk]:.0%} higher on {vr.at[d, tk]:.1f}x its usual volume",
                "Daily prices (Yahoo Finance)",
                None,
                ("Gap up ≥ 5% on heavy volume",),
            )
        )
    return out


def analyst_events(t: pd.DataFrame, src: Sources, as_of: pd.Timestamp) -> dict[str, list[Event]]:
    """This year's EPS estimate raised in the last 7 days, and analyst upgrades (not luck-tested)."""
    out: dict[str, list[Event]] = {}
    y = src.yahoo
    need = {"eps_0y_cur", "eps_0y_7d", "fetched_at"}
    if not y.empty and need <= set(y.columns):
        yy = y[y.index.isin(t.index)]
        fetched = pd.to_datetime(yy["fetched_at"], utc=True, errors="coerce").dt.tz_localize(None)
        cur, ago = pd.to_numeric(yy["eps_0y_cur"], errors="coerce"), pd.to_numeric(yy["eps_0y_7d"], errors="coerce")  # fmt: skip
        chg = ((cur - ago) / ago.abs()).where(ago.abs() > 0.01)
        up = pd.to_numeric(yy.get("eps_0y_up7"), errors="coerce") if "eps_0y_up7" in yy else pd.Series(np.nan, index=yy.index)  # fmt: skip
        dn = pd.to_numeric(yy.get("eps_0y_down7"), errors="coerce") if "eps_0y_down7" in yy else pd.Series(np.nan, index=yy.index)  # fmt: skip
        counts_ok = up.isna() | (up.fillna(0) > dn.fillna(0))
        ok = (chg >= EST_RAISE) & counts_ok & _fresh(fetched, as_of, hours=23)
        for tk in yy.index[ok.fillna(False).to_numpy()]:
            n_up = (
                "" if pd.isna(up.get(tk)) else f" ({int(up[tk])} up, {int(dn.get(tk) or 0)} down)"
            )
            out.setdefault(str(tk), []).append(
                Event(
                    "estimates_raised",
                    _day(fetched[tk]),
                    f"Analysts raised this year's earnings estimate by {chg[tk]:.1%} in 7 days{n_up}",
                    "Analyst estimates (Yahoo Finance)",
                    f"https://finance.yahoo.com/quote/{tk}/analysis",
                )
            )
    u = src.upgrades
    if not u.empty and {"action", "date"} <= set(u.columns):
        w = u[_fresh(pd.to_datetime(u["date"]), as_of, hours=23) & (u["action"].astype(str).str.lower() == "up")]  # fmt: skip
        w = w[w["ticker"].isin(t.index)]
        for tk, g in w.sort_values("date").groupby("ticker"):
            r = g.iloc[-1]
            frm = f" from {r['from_grade']}" if str(r.get("from_grade") or "").strip() else ""
            out.setdefault(str(tk), []).append(
                Event(
                    "upgrade",
                    _day(r["date"]),
                    f"{len(g)} analyst upgrade{'s' if len(g) > 1 else ''}: {r['firm']} to {r['to_grade']}{frm}",
                    "Analyst rating changes (Yahoo Finance)",
                    f"https://finance.yahoo.com/quote/{tk}/analysis",
                )
            )
    return out


_NAME_STOP = {
    "the", "inc", "incorporated", "corp", "corporation", "co", "company", "holdings", "holding",
    "group", "plc", "ltd", "limited", "lp", "nv", "sa", "ag", "se", "class", "common", "stock",
    "ordinary", "shares", "of", "and",
}  # fmt: skip
SUBJECT_WORDS = 5  # the company must be named in the first words of the headline


def subject_tokens(ticker: str, name: Any) -> set[str]:
    """Ways a headline names the company: its ticker, the first word of its name, and the first
    two words joined ("JP Morgan" -> "jpmorgan")."""
    toks = {re.sub(r"[^a-z0-9]", "", ticker.lower())}
    n = str(name or "")
    n = re.split(r" - |\(|American Depositary|Depositary|,", n, maxsplit=1)[0]
    words = [w for w in re.findall(r"[A-Za-z0-9]+", n) if w.lower() not in _NAME_STOP]
    if words:
        toks.add(words[0].lower())
    if len(words) >= 2:
        toks.add((words[0] + words[1]).lower())
    return {x for x in toks if len(x) >= 2}


def is_about(headline: str, tokens: set[str]) -> bool:
    """True if the company is the headline's subject: news feeds attach articles to every company
    they mention ("Biogen upgraded at J.P. Morgan" is not news about JPMorgan)."""
    words = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", headline or "")][:SUBJECT_WORDS]
    pairs = {a + b for a, b in zip(words, words[1:], strict=False)}
    return bool(tokens & (set(words) | pairs))


def news_events(t: pd.DataFrame, src: Sources, as_of: pd.Timestamp) -> dict[str, list[Event]]:
    """Headlines tagged positive (guidance raised, buyback, dividend raised, upgrade) whose subject
    is the company itself."""
    out: dict[str, list[Event]] = {}
    n = src.news
    if n.empty or "tags" not in n:
        return out
    w = n[_fresh(pd.to_datetime(n["datetime"]), as_of, hours=23) & (n["tag_direction"] > 0)]
    w = w[w["ticker"].isin(t.index)]
    w = w[w["tags"].fillna("").apply(lambda s: bool(set(str(s).split(",")) & set(POSITIVE_NEWS_TAGS)))]  # fmt: skip
    names = t["name"] if "name" in t else pd.Series("", index=t.index)
    w = w[[is_about(str(h), subject_tokens(str(tk), names.get(tk))) for tk, h in zip(w["ticker"], w["headline"], strict=True)]]  # fmt: skip
    for tk, g in w.sort_values("datetime").groupby("ticker"):
        r = g.iloc[-1]
        out.setdefault(str(tk), []).append(
            Event(
                "news",
                _day(r["datetime"]),
                f"News: “{str(r['headline'])[:140]}”",
                f"{r.get('source') or 'News'} (via Finnhub)",
                str(r["url"]) if r.get("url") else None,
                news=True,
            )
        )
    return out


def detect(t: pd.DataFrame, src: Sources, as_of: pd.Timestamp, eps_sue: pd.DataFrame | None = None) -> dict[str, list[Event]]:  # fmt: skip
    out: dict[str, list[Event]] = {}
    for part in (
        insider_events(t, src.trades, as_of),
        earnings_events(t, src, as_of, eps_sue),
        price_events(t, src, as_of),
        analyst_events(t, src, as_of),
        news_events(t, src, as_of),
    ):
        for tk, evs in part.items():
            out.setdefault(tk, []).extend(evs)
    order = {k: i for i, k in enumerate(PRIORITY)}
    for evs in out.values():
        evs.sort(key=lambda e: (order.get(e.kind.replace("_pending", ""), 99), e.date))
    return out


# --------------------------------------------------------------------------- history (luck test)


def history_for(
    ticker: str, group: Any, patterns: tuple[str, ...], hist: dict[str, Any] | None
) -> dict[str, Any] | None:
    """What history says about this kind of event: the stock's own record if it was tested,
    else its industry peers'. A window that passed is preferred, then 21 days, then 5 days."""
    if not hist or not patterns:
        return None
    scopes = [("stock", str(ticker))]
    if group is not None and not (isinstance(group, float) and math.isnan(group)):
        scopes.append(("peers", str(group)))
    for scope, key in scopes:
        for pat in patterns:
            recs = ((hist.get(scope) or {}).get(key) or {}).get(pat)
            if not recs:
                continue
            passing = [w for w in WINDOW_PREF if (recs.get(w) or {}).get("passed")]
            w = passing[0] if passing else next((w for w in WINDOW_PREF if w in recs), None)
            if w is None:
                continue
            return {"pattern": pat, "scope": scope, "window": w, **recs[w]}
    return None


# --------------------------------------------------------------------------- the badge


def base_rates(reliability: dict[str, Any] | None) -> dict[str, float]:
    """How often any stock went up over each horizon in 2016-2023 (pooled reliability buckets)."""
    out: dict[str, float] = {}
    for h, v in ((reliability or {}).get("horizons") or {}).items():
        b = v.get("up") or []
        n = sum(int(x["n"]) for x in b)
        hits = sum(int(x.get("hits", round(x["rate"] * x["n"]))) for x in b)
        if n:
            out[h] = hits / n
    return out


def _num(row: pd.Series, k: str) -> float:
    try:
        v = float(row.get(k))
    except (TypeError, ValueError):
        return math.nan
    return v


def risk_flags(row: pd.Series) -> list[str]:
    tags = set(str(row.get("news_negative_tags") or "").split(","))
    out = []
    si = _num(row, "short_pct_float")
    if si >= SHORT_HIGH:
        out.append(f"Heavily shorted: {si:.0%} of the tradable shares are sold short.")
    if bool(row.get("offering_recent")) or "offering" in tags:
        out.append("A share offering was announced: new shares can push the price down.")
    if "going_concern" in tags:
        out.append("Going-concern warning in the news: doubts that the company can keep operating.")
    if bool(row.get("restatement")) or "restatement" in tags:
        out.append("Restatement: earlier financial statements can no longer be relied on.")
    if bool(row.get("auditor_change")) or "auditor" in tags:
        out.append("The auditor changed or resigned.")
    if "investigation" in tags:
        out.append("An SEC/DOJ investigation is in the news.")
    if bool(row.get("late_filing")):
        out.append("A late-filing notice was filed (NT 10-K/10-Q).")
    if bool(row.get("merger_pending")) or "merger_target" in tags:
        out.append("A merger or takeover is pending: the upside is usually capped at the offer.")
    if str(row.get("label")) == "SELL / RISK WARNING":
        out.append("The app's label is SELL / RISK WARNING.")
    return out


def classify(
    row: pd.Series,
    events: list[Event],
    base: dict[str, float],
    validated: list[str],
    as_of: pd.Timestamp | None = None,
) -> Badge | None:
    """The badge for one stock (None = nothing to flag). `events` already carry their history."""
    chg1, chg5 = _num(row, "change_1d"), _num(row, "ret_1w")
    jump = (chg1 >= JUMP_1D) or (chg5 >= JUMP_1W)
    if not events and not jump:
        return None
    fams = [_num(row, f) for f in FAMILIES]
    strong = [f for f, v in zip(FAMILIES, fams, strict=True) if v >= STRONG]
    n_strong = len(strong)
    real = [e for e in events if not e.news]
    risks = risk_flags(row)
    for e in events:
        h = e.history
        if h and h.get("passed") and float(h.get("mean_excess") or 0) < 0:
            risks.append(
                f"After “{h['pattern'].lower()}”, this {'stock' if h['scope'] == 'stock' else 'industry'} usually did worse than normal "
                f"({h['mean_excess']:+.1%} over {h['window']}, {h['n']} cases, luck test passed)."
            )
    jump_text = (
        f"The price jumped {chg1:+.0%} today" if chg1 >= JUMP_1D else f"The price jumped {chg5:+.0%} in a week"
    ) if jump else ""  # fmt: skip
    weak = n_strong < WEAK_FAMILIES
    weak_text = (
        f"Weak evidence: only {n_strong} of 6 evidence families are at {STRONG:.0f} or more."
    )
    # Hype needs a trigger first: a big jump (or a gap up on volume) or loud news.
    hype = jump or any(e.kind == "gap_up" for e in events) or any(e.news for e in events)
    if hype and (risks or weak):
        return _finish(Badge(RED, events, risks=risks or [weak_text]), jump_text)
    if not events:
        return None  # a jump with decent evidence and no known reason: nothing to say
    # Green checks.
    confirmed = [
        e
        for e in real
        if e.kind != "earnings_beat_pending"
        and e.history
        and e.history.get("passed")
        and float(e.history.get("mean_excess") or 0) > 0
    ]
    h_used = "1m" if "P(up) 1m" in validated else ("6m" if "P(up) 6m" in validated else None)
    p = _num(row, f"p_up_{h_used}") if h_used else math.nan
    b = base.get(h_used or "", math.nan)
    pup_ok = bool(h_used) and math.isfinite(p) and math.isfinite(b) and p >= b + PUP_MARGIN
    eligible = bool(row.get("eligible"))
    blocked = bool(row.get("blocked"))
    sell = str(row.get("label")) == "SELL / RISK WARNING"
    checks = [
        {
            "text": "Needs a fresh event of a kind that passed the luck test (positive on average)",
            "ok": bool(confirmed),
        },
        {
            "text": f"Needs at least {GREEN_FAMILIES} of 6 evidence families at {STRONG:.0f}+ (now {n_strong}"
            + (f": {', '.join(FAMILY_NAMES[f] for f in strong)})" if strong else ")"),
            "ok": n_strong >= GREEN_FAMILIES,
        },
        {
            "text": (
                f"Needs a validated chance up ({h_used.upper()}) at least {PUP_MARGIN * 100:.0f} points above the usual {b:.0%} (now {p:.0%})"
                if h_used and math.isfinite(p) and math.isfinite(b)
                else "Needs a validated chance up (1 month or 6 months) above the usual rate"
            ),
            "ok": pup_ok,
        },
        {
            "text": "Needs eligible, not blocked and not SELL / RISK WARNING"
            + (f" (blocked: {row.get('block_reason')})" if blocked else "")
            + ("" if eligible else " (not eligible: price under $5 or under $10M traded a day)")
            + (" (label: SELL / RISK WARNING)" if sell else ""),
            "ok": eligible and not blocked and not sell,
        },
    ]
    missing = []
    if not confirmed:
        if not real:
            missing.append(
                "Only news: headlines have no luck-tested history, so news alone is never confirmation."
            )
        else:
            tested = [e for e in real if e.history]
            if tested:
                h = tested[0].history or {}
                missing.append(
                    f"“{h.get('pattern')}” did not pass the luck test for this "
                    f"{'stock' if h.get('scope') == 'stock' else 'industry'} ({h.get('n')} past cases)."
                    if not h.get("passed")
                    else "History for this kind of event points down, not up."
                )
            elif any(e.kind == "earnings_beat_pending" for e in real):
                missing.append("The first trading reaction to the report is not known yet.")
            else:
                missing.append(real[0].untested_note())
    if n_strong < GREEN_FAMILIES:
        missing.append(f"Only {n_strong} of 6 evidence families are at {STRONG:.0f} or more (needs {GREEN_FAMILIES}).")  # fmt: skip
    if not pup_ok:
        if h_used is None:
            missing.append("The chance up has not passed validation for 1 month or 6 months yet.")
        elif not math.isfinite(p) or not math.isfinite(b):
            missing.append("No calibrated model chance up for this stock today.")
        else:
            missing.append(
                f"The validated chance up ({h_used.upper()}) is {p:.0%}: not {PUP_MARGIN * 100:.0f} points above the usual {b:.0%}."
            )
    if blocked:
        missing.append(f"Blocked for new buys: {row.get('block_reason')}.")
    if not eligible:
        missing.append("Not eligible for signals (price under $5 or under $10M traded a day).")
    color = GREEN if all(c["ok"] for c in checks) else AMBER
    badge = Badge(color, events, checks=checks, risks=risks, missing=missing)
    if confirmed and as_of is not None:
        badge.days_since_event = min(
            trading_days_between(pd.Timestamp(e.date).date(), as_of.date()) for e in confirmed
        )
    return _finish(badge, jump_text)


def _finish(badge: Badge, jump_text: str) -> Badge:
    lead = badge.events[0].text if badge.events else jump_text
    if badge.color == GREEN:
        badge.summary = f"{lead}. This kind of event passed the luck test, the evidence agrees and the validated chance up is above usual."
    elif badge.color == AMBER:
        badge.summary = (
            f"{lead}. Not confirmed: {badge.missing[0][0].lower()}{badge.missing[0][1:]}"
            if badge.missing
            else f"{lead}."
        )
    else:
        # Lead with what triggered the hype check: the jump, a gap up or the headline.
        trigger = jump_text or next(
            (e.text for e in badge.events if e.kind == "gap_up" or e.news), lead
        )
        first = badge.risks[0] if badge.risks else ""
        badge.summary = (
            f"{trigger or 'Big move'}. Be careful: {first[0].lower()}{first[1:]}"
            if first
            else f"{trigger}."
        )
    if jump_text and badge.color == RED and badge.events:
        badge.risks.insert(0, f"{jump_text}.")
    return badge


def short_text(b: Badge) -> str:
    """One line for tables and lists: the main event and its date."""
    if b.events:
        e = b.events[0]
        words = {
            "insider_cluster": "Insider cluster buy", "insider_buy": "Insider buy",
            "earnings_beat": "Earnings beat", "earnings_beat_pending": "Earnings beat",
            "earnings_growth": "EPS up vs last year", "dividend_raise": "Dividend raised",
            "gap_up": "Gap up on volume", "estimates_raised": "Estimates raised",
            "upgrade": "Analyst upgrade", "news": "Positive news",
        }  # fmt: skip
        d = pd.Timestamp(e.date)
        more = f" +{len(b.events) - 1}" if len(b.events) > 1 else ""
        return f"{words.get(e.kind, e.kind)} ({d.strftime('%b')} {d.day}){more}"
    return "Big price jump"


def compute(
    t: pd.DataFrame,
    src: Sources,
    as_of: pd.Timestamp,
    history: dict[str, Any] | None,
    reliability: dict[str, Any] | None,
    validated: list[str],
    eps_sue: pd.DataFrame | None = None,
) -> tuple[dict[str, Badge], dict[str, float]]:
    """Badges for every stock that has one, and the base rates used."""
    events = detect(t, src, as_of, eps_sue)
    base = base_rates(reliability)
    groups = t["industry_group"] if "industry_group" in t else pd.Series(None, index=t.index)
    out: dict[str, Badge] = {}
    candidates = set(events) | set(
        t.index[
            (pd.to_numeric(t.get("change_1d"), errors="coerce") >= JUMP_1D)
            | (pd.to_numeric(t.get("ret_1w"), errors="coerce") >= JUMP_1W)
        ]
    )
    for tk in candidates:
        if tk not in t.index:
            continue
        evs = events.get(tk, [])
        for e in evs:
            e.history = history_for(tk, groups.get(tk), e.patterns, history)
        b = classify(t.loc[tk], evs, base, validated, as_of)
        if b is not None:
            out[str(tk)] = b
    return out, base


def export(b: Badge, as_of: str) -> dict[str, Any]:
    return {
        "color": b.color,
        "title": TITLES[b.color],
        "summary": b.summary,
        "short": short_text(b),
        "events": [e.as_dict() for e in b.events],
        "checks": b.checks,
        "risks": b.risks,
        "missing": b.missing,
        "days_since_event": b.days_since_event,
        "as_of": as_of,
    }
