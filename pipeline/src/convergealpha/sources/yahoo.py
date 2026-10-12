"""Analyst, estimate, ownership and options data from Yahoo Finance (via yfinance).

One quoteSummary request per ticker returns consensus, targets, estimate trends and revisions,
recommendation counts, rating-change history, the earnings calendar, earnings history,
institutional holders and short interest. Earnings dates with EPS estimates (~6 years) come from
a second request. Options chains are fetched for the top candidates only.

Every row is stamped with `fetched_at`; daily snapshots are append-only so history builds up.
"""

from __future__ import annotations

import math
import threading
import time
import warnings
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from convergealpha.util.http import RateLimiter
from convergealpha.util.io import row_keys, write_parquet
from convergealpha.util.log import get

log = get(__name__)

MODULES = [
    "financialData", "defaultKeyStatistics", "summaryDetail", "assetProfile", "earningsTrend",
    "recommendationTrend", "upgradeDowngradeHistory", "calendarEvents", "earningsHistory",
    "institutionOwnership", "netSharePurchaseActivity", "price",
]  # fmt: skip
PERIODS = {"0q": "0q", "+1q": "1q", "0y": "0y", "+1y": "1y"}
UPGRADE_YEARS = 3

_limiter = RateLimiter(2.5)  # per runner; each shard runs on its own machine


def _raw(d: Any, *path: str) -> Any:
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    if isinstance(d, dict):
        return d.get("raw")
    return d


def _num(v: Any) -> float:
    try:
        f = float(v)
        return f if math.isfinite(f) else math.nan
    except (TypeError, ValueError):
        return math.nan


def _ts(epoch: Any) -> pd.Timestamp | None:
    try:
        return pd.Timestamp(int(epoch), unit="s")
    except (TypeError, ValueError):
        return None


def parse_summary(
    ticker: str, res: dict[str, Any], fetched: datetime
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Flatten one quoteSummary result -> (row, upgrade events, earnings history events)."""
    fd = res.get("financialData") or {}
    ks = res.get("defaultKeyStatistics") or {}
    sd = res.get("summaryDetail") or {}
    ap = res.get("assetProfile") or {}
    pr = res.get("price") or {}
    row: dict[str, Any] = {
        "ticker": ticker,
        "fetched_at": pd.Timestamp(fetched).tz_localize(None)
        if pd.Timestamp(fetched).tzinfo
        else pd.Timestamp(fetched),
        "rec_mean": _num(_raw(fd, "recommendationMean")),
        "rec_key": fd.get("recommendationKey"),
        "n_analysts": _num(_raw(fd, "numberOfAnalystOpinions")),
        "target_mean": _num(_raw(fd, "targetMeanPrice")),
        "target_median": _num(_raw(fd, "targetMedianPrice")),
        "target_high": _num(_raw(fd, "targetHighPrice")),
        "target_low": _num(_raw(fd, "targetLowPrice")),
        "price_y": _num(_raw(fd, "currentPrice"))
        if _raw(fd, "currentPrice") is not None
        else _num(_raw(pr, "regularMarketPrice")),
        "shares_short": _num(_raw(ks, "sharesShort")),
        "short_pct_float": _num(_raw(ks, "shortPercentOfFloat")),
        "short_ratio": _num(_raw(ks, "shortRatio")),
        "short_date": _ts(_raw(ks, "dateShortInterest")),
        "shares_out_y": _num(_raw(ks, "sharesOutstanding")),
        "float_shares": _num(_raw(ks, "floatShares")),
        "inst_pct": _num(_raw(ks, "heldPercentInstitutions")),
        "insider_pct": _num(_raw(ks, "heldPercentInsiders")),
        "beta": _num(_raw(sd, "beta")),
        "market_cap_y": _num(_raw(sd, "marketCap"))
        if _raw(sd, "marketCap") is not None
        else _num(_raw(pr, "marketCap")),
        "sector_y": ap.get("sector"),
        "industry_y": ap.get("industry"),
    }
    # Recommendation counts: 0m (now) .. -3m.
    for t in (res.get("recommendationTrend") or {}).get("trend", []) or []:
        p = str(t.get("period", "")).replace("-", "m")  # "0m", "m1m"...
        if p in ("0m", "m1m", "m2m", "m3m"):
            for k in ("strongBuy", "buy", "hold", "sell", "strongSell"):
                row[f"rt_{p}_{k}"] = _num(t.get(k))
    # Estimate trends and revisions.
    for t in (res.get("earningsTrend") or {}).get("trend", []) or []:
        period = PERIODS.get(str(t.get("period")))
        if not period:
            continue
        p = period
        et = t.get("epsTrend") or {}
        er = t.get("epsRevisions") or {}
        ee = t.get("earningsEstimate") or {}
        re_ = t.get("revenueEstimate") or {}
        row[f"eps_{p}_end"] = t.get("endDate")
        for k, name in (
            ("current", "cur"),
            ("7daysAgo", "7d"),
            ("30daysAgo", "30d"),
            ("60daysAgo", "60d"),
            ("90daysAgo", "90d"),
        ):
            row[f"eps_{p}_{name}"] = _num(_raw(et, k))
        for k, name in (
            ("upLast7days", "up7"),
            ("upLast30days", "up30"),
            ("downLast30days", "down30"),
            ("downLast7Days", "down7"),
        ):
            row[f"eps_{p}_{name}"] = _num(_raw(er, k))
        row[f"eps_{p}_n"] = _num(_raw(ee, "numberOfAnalysts"))
        row[f"eps_{p}_avg"] = _num(_raw(ee, "avg"))
        row[f"rev_{p}_avg"] = _num(_raw(re_, "avg"))
        row[f"rev_{p}_n"] = _num(_raw(re_, "numberOfAnalysts"))
    cal = (res.get("calendarEvents") or {}).get("earnings") or {}
    dates = cal.get("earningsDate") or []
    row["next_earnings"] = _ts(dates[0]) if dates else None
    row["next_earnings_is_estimate"] = cal.get("isEarningsDateEstimate")
    row["ex_dividend"] = _ts(_raw(res.get("calendarEvents") or {}, "exDividendDate"))
    ns = res.get("netSharePurchaseActivity") or {}
    row["insider_net_6m_pct"] = _num(_raw(ns, "netPercentInsiderShares"))
    row["inst_net_buying_pct"] = _num(_raw(ns, "netInstBuyingPercent"))
    holders = (res.get("institutionOwnership") or {}).get("ownershipList") or []
    w = np.array([_num(_raw(h, "pctHeld")) for h in holders])
    c = np.array([_num(_raw(h, "pctChange")) for h in holders])
    ok = np.isfinite(w) & np.isfinite(c) & (w > 0)
    row["inst_top_change"] = float((w[ok] * c[ok]).sum() / w[ok].sum()) if ok.any() else math.nan

    cutoff = (
        pd.Timestamp(fetched).tz_localize(None) - pd.DateOffset(years=UPGRADE_YEARS)
        if pd.Timestamp(fetched).tzinfo
        else pd.Timestamp(fetched) - pd.DateOffset(years=UPGRADE_YEARS)
    )
    upgrades = []
    for h in (res.get("upgradeDowngradeHistory") or {}).get("history", []) or []:
        d = _ts(h.get("epochGradeDate"))
        if d is None or d < cutoff:
            continue
        upgrades.append(
            {
                "ticker": ticker,
                "date": d,
                "firm": h.get("firm"),
                "to_grade": h.get("toGrade"),
                "from_grade": h.get("fromGrade"),
                "action": h.get("action"),
                "pt_action": h.get("priceTargetAction"),
                "pt_current": _num(h.get("currentPriceTarget")),
                "pt_prior": _num(h.get("priorPriceTarget")),
            }
        )
    history = []
    for h in (res.get("earningsHistory") or {}).get("history", []) or []:
        q = _ts(_raw(h, "quarter"))
        if q is None:
            continue
        history.append(
            {
                "ticker": ticker,
                "quarter_end": q,
                "eps_actual": _num(_raw(h, "epsActual")),
                "eps_estimate": _num(_raw(h, "epsEstimate")),
                "surprise_pct": _num(_raw(h, "surprisePercent")),
            }
        )
    return row, upgrades, history


def fetch_summary(
    ticker: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]] | None:
    import yfinance as yf

    _limiter.wait()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            raw = yf.Ticker(ticker)._quote._fetch(modules=MODULES)
        res = ((raw or {}).get("quoteSummary") or {}).get("result") or []
        if not res:
            return None
        return parse_summary(ticker, res[0], datetime.now(UTC))
    except Exception as e:
        log.debug("yahoo summary %s: %s", ticker, e)
        return None


def fetch_earnings_dates(ticker: str, limit: int = 28) -> list[dict[str, Any]]:
    """Past and next earnings dates with EPS estimate/actual (Yahoo's earnings calendar)."""
    import yfinance as yf

    _limiter.wait()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df = yf.Ticker(ticker).get_earnings_dates(limit=limit)
    except Exception as e:
        log.debug("earnings dates %s: %s", ticker, e)
        return []
    if df is None or df.empty:
        return []
    out = []
    for ts, r in df.iterrows():
        t = pd.Timestamp(ts)
        when = t.tz_convert("America/New_York") if t.tzinfo else t.tz_localize("America/New_York")
        out.append(
            {
                "ticker": ticker,
                "datetime": when.tz_convert("UTC").tz_localize(None),
                # Reports at/after 16:00 New York are tradable from the next session.
                "after_close": when.hour >= 16,
                "before_open": when.hour < 9 or (when.hour == 9 and when.minute < 30),
                "eps_estimate": _num(r.get("EPS Estimate")),
                "eps_actual": _num(r.get("Reported EPS")),
                "surprise_pct": _num(r.get("Surprise(%)")) / 100.0,
            }
        )
    return out


def _atm_iv(chain: Any, spot: float) -> tuple[float, float, float, float]:
    """(atm iv, call volume, put volume, call open interest) for one expiry."""
    calls, puts = chain.calls, chain.puts
    if calls is None or puts is None or calls.empty or puts.empty:
        return math.nan, math.nan, math.nan, math.nan
    ivs = []
    for df in (calls, puts):
        d = df.dropna(subset=["impliedVolatility"])
        d = d[(d["impliedVolatility"] > 0.01) & (d["impliedVolatility"] < 5)]
        if d.empty:
            continue
        near = d.iloc[(d["strike"] - spot).abs().argsort()[:2]]
        ivs.append(float(near["impliedVolatility"].mean()))
    iv = float(np.mean(ivs)) if ivs else math.nan
    return (
        iv,
        float(calls["volume"].fillna(0).sum()),
        float(puts["volume"].fillna(0).sum()),
        float(calls["openInterest"].fillna(0).sum()),
    )


def fetch_options(ticker: str, spot: float, today: pd.Timestamp) -> dict[str, Any]:
    """Implied volatility ~1 week and ~1 month out, implied moves, put/call volume."""
    import yfinance as yf

    out: dict[str, Any] = {"ticker": ticker}
    if not (spot and spot > 0):
        return out
    try:
        tk = yf.Ticker(ticker)
        _limiter.wait()
        exps = [pd.Timestamp(e) for e in tk.options]
    except Exception:
        return out
    if not exps:
        return out
    days = np.array([(e - today).days for e in exps])
    targets = {"1w": 7, "1m": 30}
    for name, target in targets.items():
        ok = np.where(days >= max(3, target - 4))[0]
        if not len(ok):
            continue
        i = int(ok[np.argmin(np.abs(days[ok] - target))])
        try:
            _limiter.wait()
            chain = tk.option_chain(exps[i].strftime("%Y-%m-%d"))
        except Exception:
            continue
        iv, cv, pv, coi = _atm_iv(chain, spot)
        t_years = max(days[i], 1) / 365.0
        out[f"iv_{name}"] = iv
        out[f"iv_{name}_days"] = int(days[i])
        out[f"implied_move_{name}"] = iv * math.sqrt(t_years) if math.isfinite(iv) else math.nan
        if name == "1m":
            out["put_call_volume"] = pv / cv if cv > 0 else math.nan
            out["call_volume_oi"] = cv / coi if coi > 0 else math.nan
    return out


def run(
    tickers: Sequence[str],
    option_tickers: Sequence[str],
    spots: dict[str, float],
    with_dates: bool = True,
    workers: int = 3,
) -> dict[str, pd.DataFrame]:
    """Fetch everything for a list of tickers (one runner). Returns frames ready to store."""
    rows: list[dict[str, Any]] = []
    ups: list[dict[str, Any]] = []
    hist: list[dict[str, Any]] = []
    dates: list[dict[str, Any]] = []
    opts: list[dict[str, Any]] = []
    lock = threading.Lock()
    t0 = time.time()
    done = [0]

    def one(t: str) -> None:
        s = fetch_summary(t)
        d = fetch_earnings_dates(t) if with_dates else []
        with lock:
            if s is not None:
                rows.append(s[0])
                ups.extend(s[1])
                hist.extend(s[2])
            dates.extend(d)
            done[0] += 1
            if done[0] % 200 == 0:
                log.info("yahoo: %d/%d tickers (%.0fs)", done[0], len(tickers), time.time() - t0)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, tickers))
    today = pd.Timestamp(datetime.now(UTC).date())
    with ThreadPoolExecutor(max_workers=2) as pool:
        opts = [
            o
            for o in pool.map(
                lambda t: fetch_options(t, spots.get(t, math.nan), today), option_tickers
            )
            if len(o) > 1
        ]
    log.info(
        "yahoo: %d summaries, %d upgrade rows, %d earnings dates, %d option sets in %.0fs",
        len(rows),
        len(ups),
        len(dates),
        len(opts),
        time.time() - t0,
    )
    fetched = pd.Timestamp(datetime.now(UTC)).tz_localize(None)
    return {
        "summary": pd.DataFrame(rows),
        "upgrades": pd.DataFrame(ups),
        "earnings_history": pd.DataFrame(hist),
        "earnings_dates": pd.DataFrame(dates),
        "options": pd.DataFrame(opts).assign(fetched_at=fetched) if opts else pd.DataFrame(),
    }


# --------------------------------------------------------------------------- storage


EVENT_KEYS: dict[str, list[str]] = {
    "upgrades": ["ticker", "date", "firm", "to_grade", "from_grade", "action", "pt_current"],
    "earnings_history": ["ticker", "quarter_end", "eps_actual", "eps_estimate"],
    "earnings_dates": ["ticker", "datetime", "eps_estimate", "eps_actual"],
}


def store(data_dir: Path, frames: dict[str, pd.DataFrame], day: pd.Timestamp, shard: str) -> None:
    """Snapshots are stored whole; event histories only for rows not stored before."""
    base = data_dir / "snapshots" / f"{day:%Y}" / f"{day:%Y%m%d}"
    for name in ("summary", "options"):
        df = frames.get(name)
        if df is not None and not df.empty:
            write_parquet(df, base / f"yahoo_{name}-{shard}.parquet")
    for name, keys in EVENT_KEYS.items():
        df = frames.get(name)
        if df is None or df.empty:
            continue
        old = load_events(data_dir, name, keys)
        if not old.empty:
            df = df[~row_keys(df, keys).isin(set(row_keys(old, keys)))]
        df = df.drop_duplicates(keys)
        if not df.empty:
            write_parquet(df, data_dir / "events" / name / f"{day:%Y%m%d}-{shard}.parquet")


def load_latest(
    data_dir: Path, name: str = "summary", days: int = 21, today: pd.Timestamp | None = None
) -> pd.DataFrame:
    """Most recent snapshot row per ticker from the last `days` days of snapshots."""
    today = today or pd.Timestamp.now().normalize()
    frames = []
    for d in pd.date_range(today - pd.Timedelta(days=days), today):
        base = data_dir / "snapshots" / f"{d:%Y}" / f"{d:%Y%m%d}"
        for f in base.glob(f"yahoo_{name}-*.parquet"):
            frames.append(pd.read_parquet(f))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    return df.sort_values("fetched_at").drop_duplicates("ticker", keep="last").set_index("ticker")


def load_snapshots(
    data_dir: Path, name: str = "summary", columns: list[str] | None = None
) -> pd.DataFrame:
    files = sorted((data_dir / "snapshots").glob(f"*/*/yahoo_{name}-*.parquet"))
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_parquet(f, columns=columns) for f in files], ignore_index=True)


def load_events(data_dir: Path, name: str, keys: list[str]) -> pd.DataFrame:
    files = sorted((data_dir / "events" / name).glob("*.parquet"))
    if not files:
        return pd.DataFrame()
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    return df.drop_duplicates(keys, keep="last").reset_index(drop=True)
