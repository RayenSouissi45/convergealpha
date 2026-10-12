"""Orchestration of the daily pipeline. Each step records its outcome in the source states, and
health.json is written last so it reflects what actually happened."""

from __future__ import annotations

import os
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from convergealpha.config import BENCHMARKS, GSPC, NEW_YORK, SPY, VIX, Paths
from convergealpha.export import health as H
from convergealpha.export import site
from convergealpha.features import price_features as PF
from convergealpha.sources import prices as P
from convergealpha.sources import universe as U
from convergealpha.util import http
from convergealpha.util.io import write_parquet
from convergealpha.util.log import get

log = get(__name__)

DEMO_TICKERS: tuple[str, ...] = (
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK-B", "JPM", "V", "UNH",
    "XOM", "JNJ", "PG", "HD", "COST", "LLY", "AVGO", "KO", "PEP", "MRK",
    "CAT", "DE", "NKE", "DIS", "INTC", "AMD", "CRM", "NFLX", "CON", "PLTR",
)  # fmt: skip

SCREENER_FIELDS: tuple[str, ...] = (
    "ticker", "name", "exchange", "is_adr", "eligible", "price", "change_1d",
    "ret_1w", "ret_1m", "ret_3m", "ret_ytd", "ret_1y", "vol_63", "atr_pct", "trend_up",
    "dist_52w_high", "adv_dollar", "last_date",
)  # fmt: skip

STAT_KEYS: tuple[str, ...] = (
    "price", "change_1d", "ret_1w", "ret_1m", "ret_3m", "ret_6m", "ret_ytd", "ret_1y",
    "vol_21", "vol_63", "vol_252", "atr14", "atr_pct", "sma50", "sma200", "trend_up",
    "high_52w", "low_52w", "dist_52w_high", "adv_dollar", "adv_shares", "gap_stress_pct",
    "max_dd_1y", "history_days", "last_date", "eligible",
)  # fmt: skip


@dataclass
class RunContext:
    paths: Paths
    now: datetime
    env: dict[str, str] = field(default_factory=lambda: dict(os.environ))
    tickers_override: Sequence[str] | None = None
    states: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def today(self) -> pd.Timestamp:
        return pd.Timestamp(self.now.astimezone(NEW_YORK).date())

    def sec_session(self) -> Any:
        ua = self.env.get("SEC_USER_AGENT") or "ConvergeAlpha (contact not configured)"
        return http.make_session({"User-Agent": ua, "Accept-Encoding": "gzip, deflate"})


def step_universe(ctx: RunContext) -> pd.DataFrame:
    try:
        uni = U.update(ctx.paths.data, ctx.today.date(), ctx.sec_session())
        stocks = U.active_stocks(uni)
        H.record(
            ctx.states,
            "universe",
            ctx.now,
            ok=True,
            as_of=ctx.today.strftime("%Y-%m-%d"),
            records=len(stocks),
            detail=f"{len(stocks)} common stocks; {len(uni)} tickers ever seen",
        )
        return uni
    except Exception as e:  # keep going with the last stored universe
        log.error("universe update failed: %s", e)
        H.record(
            ctx.states, "universe", ctx.now, ok=False, detail=f"Update failed: {type(e).__name__}"
        )
        uni_prev = U.load(ctx.paths.data)
        if uni_prev is None:
            raise
        return uni_prev


def step_prices(ctx: RunContext, tickers: Sequence[str]) -> P.Panel:
    t0 = time.time()
    rows = P.load_rows(ctx.paths.data, tickers if ctx.tickers_override else None)
    panel = P.build_panel(rows)
    try:
        rep = P.update(ctx.paths.data, panel, tickers, ctx.now)
        if rep.new_rows:
            rows = P.load_rows(ctx.paths.data, tickers if ctx.tickers_override else None)
            panel = P.build_panel(rows)
        have = set(panel.close.columns)
        fresh = 0
        if not panel.close.empty:
            last = panel.close.index.max()
            row = panel.close.loc[last]
            fresh = int(row[[t for t in tickers if t in have]].notna().sum())
        coverage = fresh / max(1, len(tickers))
        ok = coverage > 0.5
        H.record(
            ctx.states,
            "prices",
            ctx.now,
            ok=ok,
            as_of=rep.last_session.isoformat(),
            records=fresh,
            coverage=round(coverage, 4),
            detail=f"{fresh} of {len(tickers)} tickers priced for {rep.last_session}; {rep.new_listings} new histories, {rep.repaired} repaired"
            if ok
            else f"Only {coverage:.0%} of tickers priced",
        )
        log.info("prices done in %.0fs (%d new rows)", time.time() - t0, rep.new_rows)
    except Exception as e:
        log.error("price update failed: %s", e)
        H.record(
            ctx.states, "prices", ctx.now, ok=False, detail=f"Update failed: {type(e).__name__}"
        )
    return panel


def market_summary(panel: P.Panel, snap: pd.DataFrame) -> dict[str, Any]:
    def bench(t: str) -> dict[str, Any] | None:
        if t not in snap.index:
            return None
        r = snap.loc[t]
        return site.record_from(
            r,
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
        up = (stocks["change_1d"] > 0).mean()
        above200 = (stocks["price"] > stocks["sma200"]).mean()
        out["breadth"] = {
            "stocks": len(stocks),
            "advancing_pct": float(up),
            "above_200d_pct": float(above200),
            "new_highs": int((stocks["dist_52w_high"] >= -0.005).sum()),
        }
    return out


def run_daily(ctx: RunContext) -> int:
    paths = ctx.paths
    paths.ensure()
    ctx.states = H.load_states(paths.data)
    uni = step_universe(ctx)
    stocks = U.active_stocks(uni).set_index("ticker")
    if ctx.tickers_override:
        stocks = stocks.loc[[t for t in ctx.tickers_override if t in stocks.index]]
    tickers = [*stocks.index.tolist(), *BENCHMARKS]

    panel = step_prices(ctx, tickers)
    if panel.close.empty:
        log.error("no price data at all; writing health only")
        H.save_states(paths.data, ctx.states)
        H.write_health(paths.site, ctx.now, ctx.env, ctx.states)
        return 1

    as_of = panel.close.index.max()
    snap = PF.snapshot(panel)
    table = stocks.join(snap, how="left")
    table["eligible"] = table["eligible"].fillna(False).astype(bool)

    site.write_screener(paths.site, table, SCREENER_FIELDS, as_of.strftime("%Y-%m-%d"), ctx.now)
    site.reset_stock_dir(paths.site)
    prices_state = ctx.states.get("prices", {})
    for ticker, row in table.iterrows():
        payload = {
            "schema_version": 1,
            "ticker": ticker,
            "name": row["name"],
            "exchange": row["exchange"],
            "is_adr": bool(row["is_adr"]),
            "cik": None if pd.isna(row["cik"]) else int(row["cik"]),
            "as_of": as_of.strftime("%Y-%m-%d"),
            "stats": site.record_from(row, STAT_KEYS),
            "chart": PF.chart_series(panel, str(ticker)),
            "freshness": [
                {
                    "source": "prices",
                    "name": "Daily prices (Yahoo Finance via yfinance)",
                    "as_of": site._round("last_date", row.get("last_date")),
                    "retrieved_at": prices_state.get("last_success"),
                }
            ],
        }
        site.write_stock(paths.site, str(ticker), payload)
    market = market_summary(panel, snap)
    market.update({"as_of": as_of.strftime("%Y-%m-%d"), "regime": None})
    site.write_market(paths.site, market)

    # Append-only daily snapshot of what was computed (used later for drift checks).
    snap_out = table.reset_index()[
        [c for c in ("ticker", *STAT_KEYS) if c in table.reset_index().columns]
    ].copy()
    for c in snap_out.columns:
        if snap_out[c].dtype == "float64":
            snap_out[c] = snap_out[c].astype("float32")
    write_parquet(
        snap_out,
        paths.data / "snapshots" / f"{as_of:%Y}" / f"{as_of:%Y%m%d}" / "price_features.parquet",
    )

    H.save_states(paths.data, ctx.states)
    H.write_health(
        paths.site,
        ctx.now,
        ctx.env,
        ctx.states,
        {"universe_count": len(stocks), "as_of": as_of.strftime("%Y-%m-%d")},
    )
    log.info("daily done: %d stocks exported for %s", len(table), as_of.date())
    return 0


def run_backfill(paths: Paths, now: datetime, shard: int, shards: int, env: dict[str, str]) -> int:
    paths.ensure()
    ctx = RunContext(paths=paths, now=now, env=env)
    ctx.states = H.load_states(paths.data)
    uni = U.load(paths.data)
    if uni is None:
        uni = U.update(paths.data, ctx.today.date(), ctx.sec_session())
    tickers = sorted(set(U.active_stocks(uni)["ticker"]) | set(BENCHMARKS))
    mine = [t for i, t in enumerate(tickers) if i % shards == shard]
    log.info("backfill shard %d/%d: %d tickers", shard, shards, len(mine))
    got = P.backfill(paths.data, mine, now, f"backfill-{shard:02d}of{shards:02d}")
    return 0 if got >= 0.8 * len(mine) else 1
