"""Intraday risk/event check (every 2 hours during US market hours) for candidates and holdings.

Reads the last daily site export (screener.json + stock plans), looks at today's prices, the SEC
EDGAR live filing feed and recent news, and writes intraday.json with alerts. It never changes
labels (those are decided after the close); it only warns.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from convergealpha.config import holdings_from_env, secret
from convergealpha.util import http
from convergealpha.util.io import stock_file_stem, write_json
from convergealpha.util.log import get

log = get(__name__)

EDGAR_CURRENT = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type={form}&company=&dateb=&owner=include&start=0&count=100&output=atom"
WATCH_FORMS = {
    "8-K": "8-K filed",
    "424B5": "prospectus supplement (offering)",
    "424B4": "prospectus (offering)",
    "SC 14D9": "tender offer response (takeover)",
    "SC TO-T": "tender offer (takeover)",
    "NT 10-Q": "late filing notice",
    "NT 10-K": "late filing notice",
}
_ENTRY = re.compile(
    r"<entry>.*?<title>(?P<title>.*?)</title>.*?<updated>(?P<updated>.*?)</updated>.*?</entry>",
    re.S,
)
_CIK = re.compile(r"\((\d{10})\)")


def edgar_current(session: Any) -> pd.DataFrame:
    rows = []
    for form, what in WATCH_FORMS.items():
        try:
            r = http.get(session, EDGAR_CURRENT.format(form=form.replace(" ", "+")), timeout=30)
        except http.HttpError as e:
            log.warning("edgar current %s: %s", form, e)
            continue
        assert r is not None
        for m in _ENTRY.finditer(r.text):
            cik = _CIK.search(m.group("title"))
            if cik:
                rows.append(
                    {
                        "cik": int(cik.group(1)),
                        "form": form,
                        "what": what,
                        "time": m.group("updated"),
                        "title": re.sub(r"\s+", " ", m.group("title")),
                    }
                )
    return pd.DataFrame(rows)


def run(site_dir: Path, now: datetime, env: dict[str, str]) -> dict[str, Any]:
    sc = json.loads((site_dir / "screener.json").read_text(encoding="utf-8"))
    rows = pd.DataFrame(sc["rows"], columns=sc["fields"]).set_index("ticker")
    holdings = set(holdings_from_env(env))
    focus = rows[
        (rows["label"].isin(["BUY", "STRONG BUY — TOP CONVICTION", "WATCH"]))
        | rows.index.isin(holdings)
    ]
    tickers = focus.index.tolist()[:450]
    alerts: list[dict[str, Any]] = []

    # Prices: today's bar so far.
    if tickers:
        from convergealpha.sources.prices import download

        today = now.date()
        bars = download(tickers, today - timedelta(days=5), batch_size=150, pause=0.5)
        if not bars.empty:
            bars = bars.sort_values("date")
            last = bars.groupby("ticker").tail(1).set_index("ticker")
            for t in tickers:
                if t not in last.index or last.at[t, "date"].date() != today:
                    continue
                prev_close = rows.at[t, "price"]
                o, px = float(last.at[t, "open"]), float(last.at[t, "close"])
                if (
                    prev_close
                    and o / prev_close - 1 > 0.03
                    and rows.at[t, "label"] in ("BUY", "STRONG BUY — TOP CONVICTION")
                ):
                    alerts.append(
                        {
                            "ticker": t,
                            "type": "gap",
                            "severity": "info",
                            "text": f"Opened {100 * (o / prev_close - 1):.1f}% above the signal close: the plan says skip the entry today.",
                        }
                    )
                plan = _plan(site_dir, t)
                if plan and px <= plan["planned_exit"]:
                    alerts.append(
                        {
                            "ticker": t,
                            "type": "exit",
                            "severity": "high",
                            "text": f"Trading at {px:.2f}, at or below the planned exit level {plan['planned_exit']:.2f}.",
                        }
                    )
                if prev_close and px / prev_close - 1 < -0.08:
                    alerts.append(
                        {
                            "ticker": t,
                            "type": "drop",
                            "severity": "high",
                            "text": f"Down {100 * (1 - px / prev_close):.1f}% today.",
                        }
                    )

    # SEC live filings for the focus list.
    ua = env.get("SEC_USER_AGENT")
    if ua and "cik" in rows:
        cik_to_t = {int(c): t for t, c in rows.loc[tickers, "cik"].dropna().items()}
        feed = edgar_current(http.make_session({"User-Agent": ua}))
        if not feed.empty:
            hits = feed[feed["cik"].isin(cik_to_t)]
            for r in hits.drop_duplicates(["cik", "form"]).itertuples():
                sev = "high" if r.form != "8-K" else "info"
                alerts.append(
                    {
                        "ticker": cik_to_t[int(r.cik)],
                        "type": "filing",
                        "severity": sev,
                        "text": f"New SEC filing: {r.form} — {r.what} ({r.time[:16].replace('T', ' ')} UTC).",
                    }
                )

    # News (Finnhub) with negative keyword tags.
    key = secret("FINNHUB_API_KEY", env)
    if key and tickers:
        from convergealpha.features.news import Lexicon, score_news
        from convergealpha.sources import finnhub as FH

        news = FH.company_news(
            FH.session(key), tickers[:120], now.date() - timedelta(days=1), now.date(), per_ticker=5
        )
        if not news.empty:
            news = score_news(news, Lexicon(set(), set(), set(), set(), "keywords"))
            recent = news[
                (news["datetime"] > pd.Timestamp(now.replace(tzinfo=None)) - pd.Timedelta(hours=8))
                & (news["tag_direction"] < 0)
            ]
            for r in recent.itertuples():
                alerts.append(
                    {
                        "ticker": r.ticker,
                        "type": "news",
                        "severity": "medium",
                        "text": f"News ({str(r.tags).replace('_', ' ')}): {r.headline}",
                        "url": r.url,
                    }
                )

    # Live estimate of the paper strategies (never written to the trade ledger).
    try:
        from convergealpha.paper import live

        live.run(site_dir, now, fallback=live.finnhub_quotes(key) if key else None)
    except Exception:
        log.exception("live strategies failed; the page shows the last official numbers")

    out = {
        "generated_at": now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "checked": len(tickers),
        "alerts": alerts,
    }
    write_json(out, site_dir / "intraday.json", pretty=True)
    log.info("intraday: %d tickers checked, %d alerts", len(tickers), len(alerts))
    return out


def _plan(site_dir: Path, ticker: str) -> dict[str, Any] | None:
    p = site_dir / "stocks" / f"{stock_file_stem(ticker)}.json"
    if not p.is_file():
        return None
    plan = json.loads(p.read_text(encoding="utf-8")).get("plan")
    return plan if isinstance(plan, dict) else None
