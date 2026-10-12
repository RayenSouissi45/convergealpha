"""Finnhub (free tier, 60 calls/minute): earnings calendar, recommendation trends, company news.

The API key is sent in a header (never in a URL), so it cannot leak into logs or errors.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import pandas as pd

from convergealpha.util import http
from convergealpha.util.log import get

log = get(__name__)

BASE = "https://finnhub.io/api/v1"


def session(api_key: str) -> Any:
    return http.make_session({"X-Finnhub-Token": api_key}, retries=3)


def _get(s: Any, path: str, **params: Any) -> Any:
    r = http.get(s, BASE + path, params=params, timeout=30)
    return json.loads(r.content.decode("utf-8", errors="replace")) if r is not None else None


def fix_text(text: str) -> str:
    """Repair UTF-8 text that was decoded as Latin-1 somewhere upstream (e.g. 'â€™' -> '’')."""
    if "Ã" in text or "â€" in text:
        try:
            return text.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return text
    return text


def earnings_calendar(s: Any, start: date, end: date) -> pd.DataFrame:
    """All US earnings in [start, end], fetched a week at a time (the API caps result size)."""
    frames = []
    d = start
    while d <= end:
        stop = min(d + timedelta(days=6), end)
        try:
            j = _get(s, "/calendar/earnings", **{"from": d.isoformat(), "to": stop.isoformat()})
            rows = (j or {}).get("earningsCalendar") or []
            if rows:
                frames.append(pd.DataFrame(rows))
        except http.HttpError as e:
            log.warning("finnhub calendar %s: %s", d, e)
        d = stop + timedelta(days=1)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True).rename(columns={"symbol": "ticker", "hour": "time"})
    df["ticker"] = df["ticker"].str.upper().str.replace(".", "-", regex=False)
    df["date"] = pd.to_datetime(df["date"])
    return df.drop_duplicates(["ticker", "date"])


def recommendation_trends(s: Any, tickers: Sequence[str]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        try:
            j = _get(s, "/stock/recommendation", symbol=t.replace("-", "."))
        except http.HttpError as e:
            log.debug("finnhub rec %s: %s", t, e)
            continue
        for r in (j or [])[:4]:
            rows.append(
                {
                    "ticker": t,
                    "period": r.get("period"),
                    "strong_buy": r.get("strongBuy"),
                    "buy": r.get("buy"),
                    "hold": r.get("hold"),
                    "sell": r.get("sell"),
                    "strong_sell": r.get("strongSell"),
                }
            )
    df = pd.DataFrame(rows)
    if not df.empty:
        df["period"] = pd.to_datetime(df["period"])
    return df


def company_news(
    s: Any, tickers: Sequence[str], start: date, end: date, per_ticker: int = 15
) -> pd.DataFrame:
    rows = []
    for t in tickers:
        try:
            j = _get(
                s,
                "/company-news",
                symbol=t.replace("-", "."),
                **{"from": start.isoformat(), "to": end.isoformat()},
            )
        except http.HttpError as e:
            log.debug("finnhub news %s: %s", t, e)
            continue
        items = sorted(j or [], key=lambda x: x.get("datetime", 0), reverse=True)[:per_ticker]
        for n in items:
            rows.append(
                {
                    "ticker": t,
                    "datetime": pd.Timestamp(int(n.get("datetime", 0)), unit="s"),
                    "headline": fix_text(n.get("headline") or "")[:300],
                    "summary": fix_text(n.get("summary") or "")[:500],
                    "source": n.get("source"),
                    "url": n.get("url"),
                    "id": n.get("id"),
                }
            )
    return pd.DataFrame(rows)
