"""The build job: load every source, assemble the evidence table, compute families, labels and
forecasts (later phases), and export the website JSON. It is the only writer of site data."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import pandas as pd

from convergealpha.config import BENCHMARKS, GSPC
from convergealpha.export import health as H
from convergealpha.export import site
from convergealpha.features import evidence as E
from convergealpha.features import price_features as PF
from convergealpha.features import stockpage as SP
from convergealpha.features.news import load_lexicon
from convergealpha.features.regime import describe, regime_series
from convergealpha.sources import fundamentals as F
from convergealpha.sources import insiders as I
from convergealpha.sources import macro as M
from convergealpha.sources import prices as P
from convergealpha.sources import sec_meta as S
from convergealpha.sources import yahoo as Y
from convergealpha.util.log import get

if TYPE_CHECKING:
    from convergealpha.run import RunContext

log = get(__name__)

SCREENER_FIELDS: tuple[str, ...] = (
    "ticker", "name", "exchange", "sector", "industry", "is_adr", "eligible",
    "label", "ev", "gain_per_month", "speed",
    "p_up_1w", "p_up_1m", "p_up_3m", "p_up_6m", "p_beat_6m", "med_6m", "p90_6m",
    "f1", "f2", "f3", "f4", "f5", "f6", "n_eff", "disagreement",
    "consensus", "n_analysts", "target_upside", "rev60",
    "insider_net_90d", "short_pct_float", "days_to_cover", "iv_30d",
    "price", "change_1d", "ret_1w", "ret_1m", "ret_3m", "ret_ytd", "ret_1y",
    "vol_63", "atr_pct", "trend_up", "dist_52w_high", "market_cap", "adv_dollar",
    "next_earnings", "last_date",
)  # fmt: skip

STAT_KEYS: tuple[str, ...] = (
    "price", "change_1d", "ret_1w", "ret_1m", "ret_3m", "ret_6m", "ret_ytd", "ret_1y",
    "vol_21", "vol_63", "vol_252", "atr14", "atr_pct", "sma50", "sma200", "trend_up",
    "high_52w", "low_52w", "dist_52w_high", "adv_dollar", "adv_shares", "gap_stress_pct",
    "max_dd_1y", "history_days", "last_date", "eligible", "market_cap", "shares_out",
)  # fmt: skip


def _ts(x: Any) -> pd.Timestamp:
    return pd.Timestamp(x) if x is not None else pd.NaT


def load_sources(
    ctx: RunContext, panel: P.Panel, snap: pd.DataFrame, stocks: pd.DataFrame
) -> E.Sources:
    from convergealpha.run import load_calendar, load_finnhub_rec, load_news

    d = ctx.paths.data
    as_of = panel.close.index.max()
    t0 = time.time()
    trades = I.classify(I.load(d))
    facts = F.load_facts(d)
    q = F.quarterly_flows(facts) if not facts.empty else pd.DataFrame()
    ttm = F.ttm(q) if not q.empty else pd.DataFrame()
    inst = F.instants(facts) if not facts.empty else pd.DataFrame()
    log.info(
        "loaded insiders (%d trades) and fundamentals (%d facts) in %.0fs",
        len(trades),
        len(facts),
        time.time() - t0,
    )
    lex = load_lexicon(d)
    ed = Y.load_events(d, "earnings_dates", ["ticker", "datetime"])
    if not ed.empty:
        ed["datetime"] = pd.to_datetime(ed["datetime"])
    up = Y.load_events(
        d, "upgrades", ["ticker", "date", "firm", "to_grade", "from_grade", "action", "pt_current"]
    )
    if not up.empty:
        up["date"] = pd.to_datetime(up["date"])
    news = load_news(d, ctx.today)
    if not news.empty:
        news["datetime"] = pd.to_datetime(news["datetime"])
    filings = S.load_filings(d, since=(as_of - pd.Timedelta(days=400)).date())
    if not filings.empty:
        filings["cik"] = filings["cik"].astype(int)
    return E.Sources(
        panel=panel,
        snap=snap,
        stocks=stocks,
        companies=S.load_companies(d),
        yahoo=Y.load_latest(d, "summary", days=21, today=ctx.today),
        options=Y.load_latest(d, "options", days=5, today=ctx.today),
        upgrades=up,
        earnings_dates=ed,
        trades=trades,
        ttm=ttm,
        instants=inst,
        short=M.latest_short_interest(d, as_of + pd.Timedelta(hours=23)),
        finnhub_rec=load_finnhub_rec(d, ctx.today),
        calendar=load_calendar(d),
        news=news,
        filings=filings,
        as_of=as_of,
        extras={"lexicon": lex.name},
    )


def compute_regime(ctx: RunContext, panel: P.Panel) -> tuple[dict[str, Any] | None, pd.DataFrame]:
    fred = M.load_fred(ctx.paths.data)
    if GSPC not in panel.close.columns:
        return None, pd.DataFrame()
    spx = panel.close[GSPC].astype("float64").dropna()
    vix = (
        fred["VIXCLS"]
        if "VIXCLS" in fred
        else panel.close.get("^VIX", pd.Series(dtype=float)).astype("float64")
    )
    hy = fred.get("BAMLH0A0HYM2")
    reg = regime_series(spx, vix, hy)
    last = reg.dropna(subset=["state"])
    if last.empty:
        return None, reg
    return describe(last.iloc[-1]), reg


def record_coverage(ctx: RunContext, t: pd.DataFrame, src: E.Sources) -> None:
    n = len(t)
    as_of = src.as_of.strftime("%Y-%m-%d")

    def cov(col: str) -> float:
        return float(t[col].notna().mean()) if col in t and n else 0.0

    fresh = (
        (src.as_of - pd.to_datetime(t["analyst_fetched_at"])).dt.days <= 8
        if "analyst_fetched_at" in t
        else pd.Series(False, index=t.index)
    )
    c = float(fresh.mean()) if n else 0.0
    ctx.record(
        "analyst",
        c > 0.3,
        as_of=as_of,
        records=int(t["consensus"].notna().sum()),
        coverage=round(c, 4),
        detail=f"Snapshot ≤ 8 days old for {c:.0%} of stocks; consensus for {cov('consensus'):.0%}",
    )
    ctx.record(
        "estimates",
        cov("rev60") > 0.2,
        as_of=as_of,
        records=int(t["rev60"].notna().sum()),
        coverage=round(cov("rev60"), 4),
        detail=f"EPS revision data for {cov('rev60'):.0%} of stocks",
    )
    ctx.record(
        "options",
        cov("iv_1m") > 0,
        as_of=as_of,
        records=int(t["iv_1m"].notna().sum()),
        coverage=round(cov("iv_1m"), 4),
        detail=f"Implied volatility for {int(t['iv_1m'].notna().sum())} candidates",
    )
    ctx.record(
        "institutional",
        cov("inst_pct") > 0.3,
        as_of=as_of,
        records=int(t["inst_pct"].notna().sum()),
        coverage=round(cov("inst_pct"), 4),
        detail="Yahoo holders (top-holder position changes); 13F processing not built",
    )
    if "roic" in t:
        ctx.record(
            "fundamentals",
            cov("gp_assets") > 0.3,
            as_of=as_of,
            records=int(t["gp_assets"].notna().sum()),
            coverage=round(cov("gp_assets"), 4),
            detail=f"Point-in-time ratios for {cov('gp_assets'):.0%} of stocks",
        )
    ctx.record(
        "insiders",
        not src.trades.empty,
        as_of=as_of,
        records=len(src.trades),
        detail=f"{len(src.trades):,} open-market insider trades since 2010; opportunistic buys in last 90 days at {int((t['insider_buy_usd'] > 0).sum())} stocks",
    )


def build(ctx: RunContext) -> int:
    from convergealpha.run import market_summary, universe_tickers, write_candidates

    t0 = time.time()
    paths = ctx.paths
    stocks, tickers = universe_tickers(ctx)
    panel = P.build_panel(
        P.load_rows(paths.data, [*tickers, *BENCHMARKS] if ctx.tickers_override else None)
    )
    if panel.close.empty:
        log.error("no price data at all; writing health only")
        ctx.record("prices", False, detail="No price data")
        ctx.save()
        H.write_health(paths.site, ctx.now, ctx.env, ctx.states)
        return 1
    as_of = panel.close.index.max()
    snap = PF.snapshot(panel)
    priced = int(snap.reindex(tickers)["last_date"].eq(as_of).sum())
    coverage = priced / max(1, len(tickers))
    ctx.record(
        "prices",
        coverage > 0.5,
        as_of=as_of.strftime("%Y-%m-%d"),
        records=priced,
        coverage=round(coverage, 4),
        detail=f"{priced:,} of {len(tickers):,} stocks priced for {as_of.date()}",
    )
    log.info("panel %s built in %.0fs", panel.close.shape, time.time() - t0)

    src = load_sources(ctx, panel, snap, stocks)
    t = E.build_table(src)
    t["eligible"] = t["eligible"].fillna(False).astype(bool)
    record_coverage(ctx, t, src)

    regime, _reg_hist = compute_regime(ctx, panel)

    # Later phases add families, labels and forecasts to `t` here.
    extra: dict[str, Any] = {}
    try:
        import importlib

        decide = importlib.import_module("convergealpha.decide.pipeline")
        t, extra = decide.decide(ctx, t, src, regime)
    except ModuleNotFoundError:
        pass

    # ---- exports
    site.write_screener(paths.site, t, SCREENER_FIELDS, as_of.strftime("%Y-%m-%d"), ctx.now)
    site.reset_stock_dir(paths.site)
    charts = PF.ChartBuilder(panel)
    states = ctx.states
    for ticker, row in t.iterrows():
        tk = str(ticker)
        fresh = [
            {
                "source": "prices",
                "name": "Daily prices (Yahoo Finance via yfinance)",
                "as_of": site._round("last_date", row.get("last_date")),
                "retrieved_at": states.get("prices", {}).get("last_success"),
            },
            {
                "source": "analyst",
                "name": "Analyst data (Yahoo Finance)",
                "as_of": SP._date(row.get("analyst_fetched_at")),
                "retrieved_at": SP._v(row.get("analyst_fetched_at")),
            },
            {
                "source": "fundamentals",
                "name": "Fundamentals (SEC XBRL)",
                "as_of": SP._date(row.get("fundamentals_as_of")),
                "retrieved_at": states.get("fundamentals", {}).get("last_success"),
            },
            {
                "source": "short_interest",
                "name": "Short interest (FINRA)",
                "as_of": SP._date(row.get("short_settlement")),
                "retrieved_at": states.get("short_interest", {}).get("last_success"),
            },
            {
                "source": "insiders",
                "name": "Insider trades (SEC Form 4)",
                "as_of": states.get("insiders", {}).get("as_of"),
                "retrieved_at": states.get("insiders", {}).get("last_success"),
            },
        ]
        payload: dict[str, Any] = {
            "schema_version": 2,
            "ticker": tk,
            "name": row["name"],
            "exchange": row["exchange"],
            "is_adr": bool(row["is_adr"]),
            "cik": None if pd.isna(row["cik"]) else int(row["cik"]),
            "sector": SP._v(row.get("sector")),
            "industry": SP._v(row.get("industry")),
            "as_of": as_of.strftime("%Y-%m-%d"),
            "stats": site.record_from(row, STAT_KEYS),
            "chart": charts.series(tk),
            "freshness": fresh,
            "analysts": SP.analysts(row, src, tk),
            "estimates": SP.estimates(src, tk),
            "earnings": SP.earnings(row, src, tk),
            "insiders": SP.insiders(row, src, tk),
            "ownership": SP.ownership(row),
            "options": SP.options(row),
            "fundamentals": SP.fundamentals(row),
            "news": SP.news(src, tk),
            "filings": SP.filings(src, row.get("cik")),
            "events": SP.blocking_inputs(row),
        }
        payload.update(extra.get("stock_sections", {}).get(tk, {}))
        site.write_stock(paths.site, tk, payload)

    market = market_summary(panel, snap)
    fred = M.load_fred(paths.data)
    macro = {}
    for sid, label in M.FRED_SERIES.items():
        if sid in fred:
            s = fred[sid].dropna()
            if len(s):
                macro[sid] = {
                    "label": label,
                    "value": float(s.iloc[-1]),
                    "date": s.index[-1].strftime("%Y-%m-%d"),
                    "change_3m": float(s.iloc[-1] - s.iloc[max(0, len(s) - 64)]),
                }
    market.update(
        {
            "as_of": as_of.strftime("%Y-%m-%d"),
            "regime": regime,
            "macro": macro,
            **extra.get("market", {}),
        }
    )
    site.write_market(paths.site, market)
    for name, payload in extra.get("files", {}).items():
        site.write_json_file(paths.site, name, payload)

    # Candidates for tomorrow's daily refresh of slow data (options, news, analyst data).
    cand = extra.get("candidates")
    if cand is None:
        el = t[t["eligible"]].sort_values("adv_dollar", ascending=False)
        cand = el.index[:400].tolist()
    write_candidates(paths.data, cand, as_of)
    for name, df in extra.get("snapshots", {}).items():
        from convergealpha.run import float32_snapshot
        from convergealpha.util.io import write_parquet

        write_parquet(
            float32_snapshot(df),
            paths.data / "snapshots" / f"{as_of:%Y}" / f"{as_of:%Y%m%d}" / f"{name}.parquet",
        )

    ctx.save()
    states_all = H.load_states(paths.data)
    H.write_health(
        paths.site,
        ctx.now,
        ctx.env,
        states_all,
        {
            "universe_count": len(stocks),
            "as_of": as_of.strftime("%Y-%m-%d"),
            **extra.get("health", {}),
        },
    )
    log.info(
        "build done: %d stocks exported for %s in %.0fs", len(t), as_of.date(), time.time() - t0
    )
    return 0
