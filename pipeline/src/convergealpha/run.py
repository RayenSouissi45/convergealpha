"""Pipeline jobs. In GitHub Actions they run as separate jobs (prepare -> fetch shards + finnhub ->
build); locally `daily` runs them one after the other. Each job writes only its own paths in the
data repo, so parallel jobs never conflict in git."""

from __future__ import annotations

import os
import time
import zlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from convergealpha.config import (
    BENCHMARKS,
    GSPC,
    NEW_YORK,
    SPY,
    VIX,
    Paths,
    holdings_from_env,
    secret,
)
from convergealpha.export import health as H
from convergealpha.export import site
from convergealpha.sources import fundamentals as F
from convergealpha.sources import insiders as I
from convergealpha.sources import prices as P
from convergealpha.sources import sec_meta as S
from convergealpha.sources import universe as U
from convergealpha.util import http
from convergealpha.util.calendar import last_completed_session
from convergealpha.util.io import merge_parquet, read_json, write_json, write_parquet
from convergealpha.util.log import get

log = get(__name__)

DEMO_TICKERS: tuple[str, ...] = (
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK-B", "JPM", "V", "UNH",
    "XOM", "JNJ", "PG", "HD", "COST", "LLY", "AVGO", "KO", "PEP", "MRK",
    "CAT", "DE", "NKE", "DIS", "INTC", "AMD", "CRM", "NFLX", "CON", "PLTR",
)  # fmt: skip

ROTATION_DAYS = 5  # slow data refreshed for 1/5 of the universe per trading day
CANDIDATES = 400


@dataclass
class RunContext:
    paths: Paths
    now: datetime
    env: dict[str, str] = field(default_factory=lambda: dict(os.environ))
    tickers_override: Sequence[str] | None = None
    states: dict[str, dict[str, Any]] = field(default_factory=dict)
    job: str = "build"
    touched: set[str] = field(default_factory=set)
    extras_tr: Any = None  # total-return panel shared with the ledger step

    @property
    def today(self) -> pd.Timestamp:
        return pd.Timestamp(self.now.astimezone(NEW_YORK).date())

    @property
    def session(self) -> date:
        return last_completed_session(self.now)

    def sec_session(self) -> Any:
        ua = self.env.get("SEC_USER_AGENT") or "ConvergeAlpha (contact not configured)"
        return http.make_session({"User-Agent": ua, "Accept-Encoding": "gzip, deflate"})

    def record(self, source: str, ok: bool, **kw: Any) -> None:
        H.record(self.states, source, self.now, ok=ok, **kw)
        self.touched.add(source)

    def save(self) -> None:
        H.save_states(self.paths.data, self.states, self.job, self.touched)

    def load(self) -> None:
        self.paths.ensure()
        self.states = H.load_states(self.paths.data)


def shard_of(ticker: str, shards: int) -> int:
    return zlib.crc32(ticker.encode()) % shards


def rotation_slice(ticker: str, session: date) -> bool:
    return zlib.crc32(ticker.encode()) % ROTATION_DAYS == session.weekday() % ROTATION_DAYS


def universe_tickers(ctx: RunContext) -> tuple[pd.DataFrame, list[str]]:
    uni = U.load(ctx.paths.data)
    if uni is None:
        uni = U.update(ctx.paths.data, ctx.today.date(), ctx.sec_session())
    stocks = U.active_stocks(uni).set_index("ticker")
    if ctx.tickers_override:
        stocks = stocks.loc[[t for t in ctx.tickers_override if t in stocks.index]]
    return stocks, stocks.index.tolist()


def candidates(ctx: RunContext) -> list[str]:
    c = read_json(ctx.paths.data / "state" / "candidates.json", {})
    out = list(c.get("tickers", [])) if isinstance(c, dict) else []
    return sorted(set(out) | set(holdings_from_env(ctx.env)))


# =========================================================================== prepare


def step_universe(ctx: RunContext) -> pd.DataFrame:
    try:
        uni = U.update(ctx.paths.data, ctx.today.date(), ctx.sec_session())
        stocks = U.active_stocks(uni)
        ctx.record(
            "universe",
            True,
            as_of=ctx.today.strftime("%Y-%m-%d"),
            records=len(stocks),
            detail=f"{len(stocks)} common stocks; {len(uni)} tickers ever seen",
        )
        return uni
    except Exception as e:
        log.error("universe update failed: %s", e)
        ctx.record("universe", False, detail=f"Update failed: {type(e).__name__}")
        prev = U.load(ctx.paths.data)
        if prev is None:
            raise
        return prev


def job_prepare(ctx: RunContext) -> int:
    from convergealpha.sources import macro as M

    ctx.job = "prepare"
    ctx.load()
    uni = step_universe(ctx)
    stocks = U.active_stocks(uni)
    if ctx.tickers_override:
        stocks = stocks[stocks["ticker"].isin(set(ctx.tickers_override))]
    ciks = sorted({int(c) for c in stocks["cik"].dropna()})
    sec = ctx.sec_session()
    today = ctx.today.date()

    # --- SEC daily index: who filed what over the last few days.
    try:
        idx = S.recent_index(sec, today, days=5)
    except Exception as e:
        log.error("daily index failed: %s", e)
        idx = pd.DataFrame()

    # --- company records + recent filings for companies that filed relevant forms, plus a rotation.
    try:
        known = S.load_companies(ctx.paths.data)
        filers = S.ciks_with_forms(idx, S.RELEVANT_FORMS) & set(ciks)
        stale_cut = pd.Timestamp(ctx.now.replace(tzinfo=None)) - pd.Timedelta(days=30)
        fresh = (
            set(known.loc[pd.to_datetime(known["fetched_at"]) > stale_cut, "cik"].astype(int))
            if not known.empty
            else set()
        )
        missing = [c for c in ciks if c not in fresh]
        todo = sorted(filers | set(missing[:700]))
        if todo:
            comp, fil, failed = S.fetch_submissions(sec, todo)
            S.save_companies(ctx.paths.data, comp, today)
            added = S.append_filings(ctx.paths.data, fil, today, since=today - timedelta(days=400))
            log.info(
                "sec: %d companies refreshed, %d filings added, %d failed",
                len(comp),
                added,
                len(failed),
            )
        known = S.load_companies(ctx.paths.data)
        cov = len(set(known["cik"].astype(int)) & set(ciks)) / max(1, len(ciks))
        ctx.record(
            "sec_meta",
            cov > 0.5,
            as_of=today.isoformat(),
            records=int(cov * len(ciks)),
            coverage=round(cov, 4),
            detail=f"Industry codes for {cov:.0%} of stocks",
        )
    except Exception as e:
        log.error("sec submissions failed: %s", e)
        ctx.record("sec_meta", False, detail=f"Update failed: {type(e).__name__}")

    # --- insiders: new quarterly data sets + Form 4 XML for days after the last data set.
    small = bool(ctx.tickers_override)  # demo / test runs: lighter history
    try:
        I.update_datasets(
            sec, ctx.paths.data, since_year=today.year - 1 if small else 2010, refresh_last=0
        )
        for d in I.needs_xml_days(ctx.paths.data, today)[-8:]:
            day_idx = S.fetch_daily_index(sec, d)
            trades = I.fetch_form4s(sec, day_idx, ciks)
            if trades.empty:  # an empty file still records that the day was processed
                write_parquet(
                    pd.DataFrame({c: pd.Series(dtype="object") for c in I.COLS}),
                    I.daily_dir(ctx.paths.data) / f"{d:%Y%m%d}.parquet",
                )
            else:
                I.write_daily(ctx.paths.data, trades, d)
        end = I.last_dataset_end(ctx.paths.data)
        ctx.record(
            "insiders",
            end is not None,
            as_of=today.isoformat(),
            detail=f"SEC data sets through {end}, then Form 4 filings parsed daily"
            if end
            else "No insider data sets yet",
        )
    except Exception as e:
        log.error("insiders failed: %s", e)
        ctx.record("insiders", False, detail=f"Update failed: {type(e).__name__}")

    # --- fundamentals for companies with new 10-K / 10-Q.
    try:
        new_filers = S.ciks_with_forms(
            idx, ("10-K", "10-Q", "10-K/A", "10-Q/A", "20-F", "40-F")
        ) & set(ciks)
        if small:  # no bulk bootstrap for small runs: fetch each company's facts directly
            stored = F.load_facts(ctx.paths.data)
            have_ciks = set(stored["cik"].astype(int)) if not stored.empty else set()
            new_filers |= set(ciks) - have_ciks
        if new_filers:
            facts = F.fetch_companyfacts(sec, sorted(new_filers))
            n = F.append_facts(ctx.paths.data, facts, today)
            log.info("fundamentals: %d new facts from %d filers", n, len(new_filers))
        have = any(F.facts_dir(ctx.paths.data).glob("*.parquet"))
        ctx.record(
            "fundamentals",
            have,
            as_of=today.isoformat(),
            detail="SEC XBRL company facts (first-reported values)"
            if have
            else "Not bootstrapped yet",
        )
    except Exception as e:
        log.error("fundamentals failed: %s", e)
        ctx.record("fundamentals", False, detail=f"Update failed: {type(e).__name__}")

    # --- macro (FRED) and short interest (FINRA).
    key = secret("FRED_API_KEY", ctx.env)
    if key:
        try:
            fred = M.fetch_fred(key, date(2009, 1, 1))
            M.store_fred(ctx.paths.data, fred)
            last = fred["date"].max()
            ctx.record(
                "macro",
                True,
                as_of=pd.Timestamp(last).strftime("%Y-%m-%d"),
                records=len(fred),
                detail="VIX, high-yield spread, 10y-2y, fed funds, EUR/USD",
            )
        except Exception as e:
            log.error("fred failed: %s", e)
            ctx.record("macro", False, detail=f"Update failed: {type(e).__name__}")
    try:
        from convergealpha.sources import history as HIST

        hist = HIST.update(ctx.paths.data, key)
        ctx.record(
            "history",
            hist is not None and not hist.empty,
            as_of=str(hist["month"].iloc[-1]) if hist is not None and not hist.empty else None,
            records=0 if hist is None else len(hist),
            detail="US stock market and T-bills since 1926 (Kenneth R. French), inflation (FRED)",
        )
    except Exception as e:
        log.error("history failed: %s", e)
        ctx.record("history", False, detail=f"Update failed: {type(e).__name__}")
    try:
        ecb = M.fetch_ecb_usd(date(2009, 1, 1))
        M.store_fred(ctx.paths.data, ecb)
        ctx.record(
            "ecb_fx",
            not ecb.empty,
            as_of=pd.Timestamp(ecb["date"].max()).strftime("%Y-%m-%d") if not ecb.empty else None,
            records=len(ecb),
            detail="EUR/USD reference rate (European Central Bank), daily",
        )
    except Exception as e:
        log.error("ecb failed: %s", e)
        ctx.record("ecb_fx", False, detail=f"Update failed: {type(e).__name__}")
    try:
        written = M.update_short_interest(ctx.paths.data, today, today - timedelta(days=75))
        si = M.load_short_interest(ctx.paths.data)
        last = si["settlement"].max() if not si.empty else None
        ctx.record(
            "short_interest",
            last is not None,
            as_of=pd.Timestamp(last).strftime("%Y-%m-%d") if last is not None else None,
            records=int(si["settlement"].eq(last).sum()) if last is not None else 0,
            detail=f"FINRA settlement {pd.Timestamp(last).date() if last is not None else '—'}; {len(written)} new file(s)",
        )
    except Exception as e:
        log.error("finra failed: %s", e)
        ctx.record("short_interest", False, detail=f"Update failed: {type(e).__name__}")
    ctx.save()
    return 0


# =========================================================================== fetch (shard)


def job_fetch(ctx: RunContext, shard: int, shards: int, with_yahoo: bool = True) -> int:
    from convergealpha.sources import yahoo as Y

    ctx.job = f"fetch-s{shard:02d}"
    ctx.load()
    _, tickers = universe_tickers(ctx)
    mine = [t for t in tickers if shard_of(t, shards) == shard]
    if shard == 0:
        mine = [*mine, *BENCHMARKS]
    suffix = f"-s{shard:02d}" if shards > 1 else ""
    log.info("fetch shard %d/%d: %d tickers", shard, shards, len(mine))

    panel = P.build_panel(P.load_rows(ctx.paths.data, mine))
    try:
        rep = P.update(ctx.paths.data, panel, mine, ctx.now, suffix=suffix)
        log.info(
            "prices shard %d: %d new rows, %d new histories, %d repaired, %d without data",
            shard,
            rep.new_rows,
            rep.new_listings,
            rep.repaired,
            len(rep.missing),
        )
    except Exception as e:
        log.error("prices shard %d failed: %s", shard, e)

    if with_yahoo:
        latest = Y.load_latest(ctx.paths.data, days=10, today=ctx.today)
        seen = set(latest.index)
        cands = set(candidates(ctx))
        upcoming: set[str] = set()
        if not latest.empty and "next_earnings" in latest:
            ne = pd.to_datetime(latest["next_earnings"])
            upcoming = set(
                latest.index[
                    (ne > ctx.today - pd.Timedelta(days=8))
                    & (ne < ctx.today + pd.Timedelta(days=8))
                ]
            )
        todo = [
            t
            for t in mine
            if t not in BENCHMARKS
            and (t not in seen or rotation_slice(t, ctx.session) or t in cands or t in upcoming)
        ]
        spots = panel.close.ffill().iloc[-1].to_dict() if not panel.close.empty else {}
        opt = [t for t in mine if t in cands][:120]
        frames = Y.run(todo, opt, {k: float(v) for k, v in spots.items() if pd.notna(v)})
        Y.store(ctx.paths.data, frames, ctx.today, f"s{shard:02d}")
    ctx.save()
    return 0


# =========================================================================== finnhub


def job_finnhub(ctx: RunContext) -> int:
    from convergealpha.features.news import load_lexicon, score_news
    from convergealpha.sources import finnhub as FH

    ctx.job = "finnhub"
    ctx.load()
    key = secret("FINNHUB_API_KEY", ctx.env)
    if not key:
        ctx.save()
        return 0
    s = FH.session(key)
    today = ctx.today.date()
    _, tickers = universe_tickers(ctx)
    try:
        cal = FH.earnings_calendar(s, today - timedelta(days=10), today + timedelta(days=35))
        cal = cal[cal["ticker"].isin(set(tickers))] if not cal.empty else cal
        if not cal.empty:
            write_parquet(
                cal, ctx.paths.data / "events" / "finnhub_calendar" / f"{today:%Y%m%d}.parquet"
            )
        ctx.record(
            "earnings",
            not cal.empty,
            as_of=today.isoformat(),
            records=len(cal),
            detail=f"{len(cal)} reports scheduled between {today - timedelta(days=10)} and {today + timedelta(days=35)}",
        )
    except Exception as e:
        log.error("finnhub calendar failed: %s", e)
        ctx.record("earnings", False, detail=f"Update failed: {type(e).__name__}")

    cands = candidates(ctx)
    rotation = [t for t in tickers if zlib.crc32(t.encode()) % 10 == ctx.session.toordinal() % 10]
    rec_list = list(dict.fromkeys([*cands, *rotation]))[:330]
    try:
        rec = FH.recommendation_trends(s, rec_list)
        if not rec.empty:
            merge_parquet(
                rec,
                ctx.paths.data
                / "snapshots"
                / f"{ctx.today:%Y}"
                / f"{ctx.today:%Y%m%d}"
                / "finnhub_rec.parquet",
            )
        log.info(
            "finnhub: recommendation trends for %d tickers",
            rec["ticker"].nunique() if not rec.empty else 0,
        )
    except Exception as e:
        log.error("finnhub rec failed: %s", e)

    news_list = (cands or [t for t in tickers if t in set(DEMO_TICKERS)])[:150]
    try:
        news = FH.company_news(s, news_list, today - timedelta(days=10), today)
        if not news.empty:
            news = score_news(news, load_lexicon(ctx.paths.data))
            merge_parquet(news, ctx.paths.data / "news" / f"{today:%Y}" / f"{today:%Y%m%d}.parquet")
        ctx.record(
            "news",
            True,
            as_of=today.isoformat(),
            records=len(news),
            detail=f"Headlines for {news['ticker'].nunique() if not news.empty else 0} stocks (top candidates)",
        )
    except Exception as e:
        log.error("finnhub news failed: %s", e)
        ctx.record("news", False, detail=f"Update failed: {type(e).__name__}")
    ctx.save()
    return 0


# =========================================================================== build helpers


def load_news(data_dir: Path, today: pd.Timestamp, days: int = 14) -> pd.DataFrame:
    frames = []
    for d in pd.date_range(today - pd.Timedelta(days=days), today):
        p = data_dir / "news" / f"{d:%Y}" / f"{d:%Y%m%d}.parquet"
        if p.is_file():
            frames.append(pd.read_parquet(p))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates(["ticker", "id"], keep="last")


def load_finnhub_rec(data_dir: Path, today: pd.Timestamp, days: int = 45) -> pd.DataFrame:
    frames = []
    for d in pd.date_range(today - pd.Timedelta(days=days), today):
        p = data_dir / "snapshots" / f"{d:%Y}" / f"{d:%Y%m%d}" / "finnhub_rec.parquet"
        if p.is_file():
            frames.append(pd.read_parquet(p))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_calendar(data_dir: Path) -> pd.DataFrame:
    files = sorted((data_dir / "events" / "finnhub_calendar").glob("*.parquet"))[-5:]
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True).drop_duplicates(
        ["ticker", "date"], keep="last"
    )


def market_summary(panel: P.Panel, snap: pd.DataFrame) -> dict[str, Any]:
    def bench(t: str) -> dict[str, Any] | None:
        if t not in snap.index:
            return None
        return site.record_from(
            snap.loc[t],
            [
                "price",
                "change_1d",
                "ret_1w",
                "ret_1m",
                "ret_3m",
                "ret_ytd",
                "ret_1y",
                "sma50",
                "sma200",
                "vol_63",
                "last_date",
            ],
        )

    out: dict[str, Any] = {"benchmarks": {SPY: bench(SPY), GSPC: bench(GSPC), VIX: bench(VIX)}}
    stocks = snap.drop(index=[b for b in BENCHMARKS if b in snap.index])
    stocks = stocks[stocks["last_date"] == panel.close.index.max()]
    if len(stocks):
        out["breadth"] = {
            "stocks": len(stocks),
            "advancing_pct": float((stocks["change_1d"] > 0).mean()),
            "above_200d_pct": float((stocks["price"] > stocks["sma200"]).mean()),
            "new_highs": int((stocks["dist_52w_high"] >= -0.005).sum()),
        }
    return out


def write_candidates(data_dir: Path, tickers: Sequence[str], as_of: pd.Timestamp) -> None:
    write_json(
        {"as_of": as_of.strftime("%Y-%m-%d"), "tickers": list(tickers)},
        data_dir / "state" / "candidates.json",
        pretty=True,
    )


def float32_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == "float64":
            out[c] = out[c].astype("float32")
    return out


def job_build(ctx: RunContext) -> int:
    from convergealpha import build as B

    ctx.job = "build"
    ctx.load()
    return B.build(ctx)


# =========================================================================== bootstrap (one-time)


def job_bootstrap(ctx: RunContext, what: str) -> int:
    ctx.job = f"bootstrap-{what}"
    ctx.load()
    if what == "brokers":
        return _bootstrap_brokers(ctx)
    stocks, _ = universe_tickers(ctx)
    ciks = sorted({int(c) for c in stocks["cik"].dropna()})
    sec = ctx.sec_session()
    today = ctx.today.date()
    t0 = time.time()
    if what == "sec":
        comp, fil, failed = S.fetch_submissions(sec, ciks)
        S.save_companies(ctx.paths.data, comp, today)
        added = S.append_filings(ctx.paths.data, fil, today, since=today - timedelta(days=400))
        log.info(
            "bootstrap sec: %d companies, %d filings, %d failed", len(comp), added, len(failed)
        )
        written = I.update_datasets(sec, ctx.paths.data, since_year=2010, refresh_last=0)
        log.info("bootstrap insiders: %d quarters", len(written))
    elif what == "fundamentals":
        facts = F.fetch_bulk(sec, ciks, ctx.paths.cache)
        n = F.append_facts(ctx.paths.data, facts, today, existing=F.load_facts(ctx.paths.data))
        log.info(
            "bootstrap fundamentals: %d facts for %d companies",
            n,
            facts["cik"].nunique() if not facts.empty else 0,
        )
    elif what == "finra":
        from convergealpha.sources import macro as M

        written_si = M.update_short_interest(ctx.paths.data, today, date(2018, 1, 1))
        log.info("bootstrap finra: %d settlement files", len(written_si))
    else:
        raise ValueError(f"unknown bootstrap target {what}")
    log.info("bootstrap %s done in %.0fs", what, time.time() - t0)
    ctx.save()
    return 0


def _bootstrap_brokers(ctx: RunContext) -> int:
    """Weekly: the finanzen.net zero list (gettex shares in ESMA FIRDS, mapped to tickers)."""
    from convergealpha.sources import brokers as B

    try:
        meta = B.refresh(ctx.paths.data, ctx.paths.cache, ctx.today.date(), ctx.env)
        ctx.record(
            "brokers",
            True,
            as_of=meta["list_date"],
            records=meta["with_us_ticker"],
            detail=f"{meta['instruments']:,} gettex shares and ADRs, "
            f"{meta['with_us_ticker']:,} with a US ticker",
        )
    except Exception as e:
        log.warning("finanzen.net zero list: %s", e)
        ctx.record("brokers", False, detail=f"List refresh failed: {type(e).__name__}: {e}")
    ctx.save()
    return 0


# =========================================================================== local sequential run


def run_daily(ctx: RunContext) -> int:
    """Every job in one process (local runs, demo)."""
    for name, job in (
        ("prepare", job_prepare),
        ("fetch", lambda c: job_fetch(c, 0, 1)),
        ("finnhub", job_finnhub),
    ):
        try:
            job(ctx)
        except Exception as e:
            log.error("%s failed: %s", name, e)
        ctx.touched = set()
    return job_build(
        RunContext(paths=ctx.paths, now=ctx.now, env=ctx.env, tickers_override=ctx.tickers_override)
    )


def run_backfill(paths: Paths, now: datetime, shard: int, shards: int, env: dict[str, str]) -> int:
    ctx = RunContext(paths=paths, now=now, env=env)
    ctx.load()
    uni = U.load(paths.data)
    if uni is None:
        uni = U.update(paths.data, ctx.today.date(), ctx.sec_session())
    tickers = sorted(set(U.active_stocks(uni)["ticker"]) | set(BENCHMARKS))
    mine = [t for i, t in enumerate(tickers) if i % shards == shard]
    log.info("backfill shard %d/%d: %d tickers", shard, shards, len(mine))
    got = P.backfill(paths.data, mine, now, f"backfill-{shard:02d}of{shards:02d}")
    return 0 if got >= 0.8 * len(mine) else 1
