"""The build job: load every source, assemble the evidence table, compute families, labels and
forecasts (later phases), and export the website JSON. It is the only writer of site data."""

from __future__ import annotations

import time
from pathlib import Path
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
    "ticker", "name", "exchange", "sector", "industry", "is_adr", "cik", "eligible", "zero",
    "label", "tier", "blocked", "block_reason", "ev", "p_hat", "gain_per_month", "speed",
    "p_up_1w", "p_up_1m", "p_up_3m", "p_up_6m", "p_beat_1w", "p_beat_1m", "p_beat_3m", "p_beat_6m",
    "med_1w", "med_1m", "med_3m", "med_6m", "p10_1w", "p10_1m", "p10_3m", "p10_6m",
    "p90_1w", "p90_1m", "p90_3m", "p90_6m", "hit_up_1w", "hit_up_1m", "hit_up_3m", "hit_up_6m",
    "f1", "f2", "f3", "f4", "f5", "f6", "n_eff", "disagreement",
    "consensus", "n_analysts", "target_upside", "rev60",
    "insider_net_90d", "insider_buy_7d", "short_pct_float", "days_to_cover", "iv_30d",
    "price", "change_1d", "ret_1w", "ret_1m", "ret_3m", "ret_ytd", "ret_1y",
    "vol_63", "atr_pct", "trend_up", "dist_52w_high", "market_cap", "adv_dollar",
    "next_earnings", "days_to_earnings", "cluster", "last_date", "opp", "opp_event",
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
    from convergealpha.models.dataset import eps_surprise_series

    # EPS vs the same quarter last year, known from the filing date (models and opportunity badge).
    eps_sue = eps_surprise_series(facts) if not facts.empty else None
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
        extras={
            "lexicon": lex.name,
            "data_dir": d,
            "short_all": _short_history(d, stocks.index),
            "eps_sue": eps_sue,
        },
    )


def ledger_step(
    ctx: RunContext,
    t: pd.DataFrame,
    extra: dict[str, Any],
    as_of: pd.Timestamp,
    snap_path: Path | None = None,
) -> dict[str, Any] | None:
    """Record new signals before outcomes are known, fill matured outcomes, publish the scorecard."""
    if "label" not in t:
        return None
    from datetime import UTC

    from convergealpha.alerts import telegram
    from convergealpha.config import SPY, holdings_from_env
    from convergealpha.ledger import ledger as LG
    from convergealpha.ledger import monitor as MON

    d = ctx.paths.data
    snaps = sorted(
        p
        for p in (d / "snapshots").glob("*/*/scores.parquet")
        if p.parent.name < as_of.strftime("%Y%m%d")
    )
    prev = (
        pd.read_parquet(snaps[-1], columns=["ticker", "label"])
        .set_index("ticker")["label"]
        .to_dict()
        if snaps
        else {}
    )
    lpath, opath = d / "ledger" / "ledger.jsonl", d / "ledger" / "outcomes.jsonl"
    existing = LG.read(lpath)
    already = {
        (e["ticker"], e["label"]) for e in existing if e["date"] == as_of.strftime("%Y-%m-%d")
    }
    scope = t[t["eligible"].astype(bool) | (t["label"] == "SELL / RISK WARNING")]
    sig = LG.new_signals(scope, prev)
    sig = sig[[(tk, lab) not in already for tk, lab in sig["label"].items()]]
    snap_path = snap_path or d / "snapshots" / f"{as_of:%Y}" / f"{as_of:%Y%m%d}" / "scores.parquet"
    model_version = (extra.get("health") or {}).get("model_version")
    generated = ctx.now.astimezone(UTC).isoformat(timespec="seconds")
    new = (
        LG.append(
            lpath,
            LG.make_entries(
                sig,
                as_of,
                model_version,
                str(snap_path.relative_to(d)).replace("\\", "/"),
                LG.file_sha256(snap_path),
                extra.get("stock_sections", {}),
                prev,
                generated,
            ),
        )
        if len(sig)
        else []
    )
    entries = LG.read(lpath)
    outcomes = LG.read(opath)
    panel_tr = ctx.extras_tr
    if panel_tr is not None and SPY in panel_tr:
        due = LG.due_outcomes(entries, outcomes, panel_tr, panel_tr[SPY], as_of)
        if due:
            LG.append(opath, due)
            outcomes = LG.read(opath)
    ok_l, why_l = LG.verify(lpath)
    ok_o, why_o = LG.verify(opath)
    backtest = None
    val = (extra.get("files") or {}).get("validation.json")
    if val:
        backtest = {
            k: v.get("strategies", {}).get("app") for k, v in (val.get("periods") or {}).items()
        }
        if val.get("holdout"):
            backtest["holdout"] = val["holdout"].get("strategies", {}).get("app")
    site.write_json_file(ctx.paths.site, "scorecard.json", MON.scorecard(outcomes, backtest))
    by_seq: dict[int, list[dict[str, Any]]] = {}
    for o in outcomes:
        by_seq.setdefault(o["entry_seq"], []).append(o)
    recent = entries[-300:]
    site.write_json_file(
        ctx.paths.site,
        "ledger.json",
        {
            "verified": ok_l and ok_o,
            "verify_detail": why_l if not ok_l else why_o,
            "count": len(entries),
            "outcomes": len(outcomes),
            "entries": [{**e, "outcomes": by_seq.get(e["seq"], [])} for e in reversed(recent)],
        },
    )
    # Phone alerts (optional).
    holdings = set(holdings_from_env(ctx.env))
    lines = [
        f"New {e['label']}: {e['ticker']} at {e['price']:.2f}"
        for e in new
        if e["label"].startswith("STRONG BUY")
    ]
    lines += [
        f"{e['ticker']} (holding): {e['label']}"
        for e in new
        if e["ticker"] in holdings and e["label"].startswith("SELL")
    ]
    ks = extra.get("kill_switch") or {}
    if ks.get("active"):
        lines.append("Kill switch ACTIVE: no new BUY labels. " + "; ".join(ks.get("reasons", [])))
    telegram.send_many(lines, ctx.env)
    log.info(
        "ledger: %d new entries (%d total), %d outcomes, chain %s",
        len(new),
        len(entries),
        len(outcomes),
        "ok" if ok_l and ok_o else "BROKEN",
    )
    return {
        "entries": len(entries),
        "new_today": len(new),
        "outcomes": len(outcomes),
        "verified": ok_l and ok_o,
    }


FX_GAP_LIMIT = 0.005  # ECB and FRED are both official rates taken hours apart: 0.5% is a warning


def fx_check(fred: pd.DataFrame) -> dict[str, Any]:
    """Health: the ECB and FRED EUR/USD rates checked against each other."""
    from convergealpha.decide import costs as CO

    gap = CO.fx_gap(fred)
    latest = {}
    for sid in (CO.USER_FX_SERIES, CO.FX_SERIES):
        if fred is not None and not fred.empty and sid in fred and fred[sid].notna().any():
            s = fred[sid].dropna()
            latest[sid] = {
                "rate": round(float(s.iloc[-1]), 5),
                "date": s.index[-1].strftime("%Y-%m-%d"),
            }
    return {
        "latest": latest,
        "max_gap_30d": None if gap is None else round(gap, 5),
        "ok": None if gap is None else gap <= FX_GAP_LIMIT,
        "limit": FX_GAP_LIMIT,
    }


def paper_step(
    ctx: RunContext,
    panel: P.Panel,
    t: pd.DataFrame,
    as_of: pd.Timestamp,
    extra: dict[str, Any],
    validated: list[str],
    base_up: dict[str, float],
    fx_series: pd.Series,
    fx_now: tuple[float, str] | None,
    snapshot_paths: dict[str, Path],
    price_coverage: float,
) -> dict[str, Any]:
    """Paper trading (paper money only): extend the trade ledger with today's fills, values and
    decisions, verify the whole chain, and publish strategies.json."""
    from datetime import UTC

    from convergealpha.ledger import ledger as LG
    from convergealpha.paper import engine as PE
    from convergealpha.paper import export as PX
    from convergealpha.paper import strategies as PS

    d = ctx.paths.data
    specs = PS.ALL_SPECS
    model_ok = extra.get("forecast_method") == "model"
    ks = bool((extra.get("kill_switch") or {}).get("active"))
    if model_ok and not ks:
        why_not = None
    elif not model_ok:
        why_not = "the model forecasts are not available today"
    else:
        why_not = "the kill switch is active"
    snap = snapshot_paths.get("scores")
    inputs = {
        "scores_snapshot": str(snap.relative_to(d)).replace(chr(92), "/") if snap else None,
        "scores_sha256": LG.file_sha256(snap) if snap else None,
        "model_version": (extra.get("health") or {}).get("model_version"),
    }
    today = PE.Today(t, validated, base_up.get("1m"), why_not is None, why_not, inputs)
    status = None
    new: list[dict[str, Any]] = []
    if fx_now is None:
        log.warning("paper trading waits: no EUR/USD rate (FRED DEXUSEU) yet")
        books = PE.replay(LG.read(d / PE.LEDGER), specs)
        status = "waiting for the EUR/USD rate from FRED"
    elif price_coverage <= 0.5:
        log.warning("paper trading waits: prices for only %.0f%% of stocks", 100 * price_coverage)
        books = PE.replay(LG.read(d / PE.LEDGER), specs)
        status = "waiting for good price data"
    else:
        try:
            recorded = ctx.now.astimezone(UTC).isoformat(timespec="seconds")
            books, new = PE.run(d, panel, fx_series, as_of, today, recorded)
        except Exception:
            log.exception("paper trading failed; nothing was recorded today")
            books = PE.replay(LG.read(d / PE.LEDGER), specs)
            status = "error: nothing recorded today"
    ok, why = PE.verify(d)
    n = len(LG.read(d / PE.LEDGER))
    site.write_json_file(
        ctx.paths.site,
        "strategies.json",
        PX.export(
            books,
            t,
            as_of.strftime("%Y-%m-%d"),
            ctx.now,
            fx_now,
            (ok, why, n),
            validated,
            base_up.get("1m"),
            status,
            extra.get("reliability"),
        ),
    )
    log.info("paper trading: %d new ledger entries (%d in total), chain %s", len(new), n, "ok" if ok else "BROKEN")  # fmt: skip
    last = max((b.last_day or "" for b in books.values()), default="") or None
    return {"verified": ok, "detail": why, "entries": n, "new_today": len(new), "last_day": last}


def _reliability_meta(extra: dict[str, Any]) -> dict[str, Any] | None:
    """The "chance up" reliability tables, for the screener's "How often right" column."""
    rel = extra.get("reliability")
    if not rel:
        return None
    return {
        "method": rel.get("method"),
        "years": rel.get("years"),
        "up": {
            h: [
                {k: b[k] for k in ("lo", "hi", "n", "rate", "wilson_lo", "wilson_hi")}
                for b in v.get("up", [])
            ]
            for h, v in (rel.get("horizons") or {}).items()
        },
    }


def record_brokers(ctx: RunContext, summary: dict[str, Any] | None) -> None:
    """Health: the finanzen.net zero list's date and how many of our stocks matched."""
    from convergealpha.sources import brokers as B

    if summary is None:
        return  # never built: the weekly refresh records its own state
    fresh = not summary.get("stale") and summary.get("age_days", 99) <= 16
    if fresh:
        ctx.record(
            "brokers",
            True,
            as_of=summary.get("list_date"),
            records=summary.get("matched"),
            coverage=round(summary["matched"] / max(1, summary["stocks"]), 4),
            detail=B.describe(summary),
        )
    else:
        ctx.record(
            "brokers",
            False,
            detail=f"The list is {summary.get('age_days')} days old (weekly refresh failing?); "
            "older than 35 days, every stock shows as unknown",
        )


def _short_history(d: Any, tickers: Any) -> pd.DataFrame:
    s = M.load_short_interest(d)
    return s[s["ticker"].isin(set(tickers))] if not s.empty else s


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
        # Any of the five F6 ratios (banks and insurers have no gross profit, for example).
        ratios = [
            c for c in ("roic", "gp_assets", "accruals", "fcf_yield", "debt_ebitda") if c in t
        ]
        has = t[ratios].notna().any(axis=1)
        share = float(has.mean()) if n else 0.0
        elig = t["eligible"].eq(True) if "eligible" in t else has.astype(bool)
        share_el = float(has[elig].mean()) if elig.any() else 0.0
        ctx.record(
            "fundamentals",
            share > 0.3,
            as_of=as_of,
            records=int(has.sum()),
            coverage=round(share, 4),
            detail=f"Point-in-time quality ratios (US-GAAP XBRL) for {share:.0%} of stocks, "
            f"{share_el:.0%} of eligible ones",
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
    ctx.extras_tr = panel.tr
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
    from convergealpha.sources import plugins as PL

    manual = PL.manual_ratings(ctx.paths.data, src.as_of)
    if manual:
        t.attrs["manual_ratings"] = manual
        t["top_rated_sources"] = t["top_rated_sources"] + sum(
            (s.reindex(t.index) >= 100).astype(int) for s in manual.values()
        )
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

    # ---- finanzen.net zero (true / false / unknown) and Picks
    from convergealpha.decide import picks as PK
    from convergealpha.ledger import monitor as MON
    from convergealpha.sources import brokers as B

    t["zero"], zero_summary = B.zero_flags(t, B.load_list(paths.data), as_of)
    record_brokers(ctx, zero_summary)
    validated = list((extra.get("health") or {}).get("validated") or [])
    day = as_of.strftime("%Y-%m-%d")

    # ---- opportunity badge: one per stock, from the signals the app already has
    from convergealpha.decide import costs as CO
    from convergealpha.decide import opportunity as OP

    badges: dict[str, OP.Badge] = {}
    base_up: dict[str, float] = OP.base_rates(extra.get("reliability"))
    if "label" in t:
        badges, base_up = OP.compute(
            t,
            src,
            as_of,
            extra.get("pattern_history"),
            extra.get("reliability"),
            validated,
            src.extras.get("eps_sue"),
        )
    t["opp"] = pd.Series({k: b.color for k, b in badges.items()}, dtype=object).reindex(t.index)
    t["opp_event"] = pd.Series(
        {k: OP.short_text(b) for k, b in badges.items()}, dtype=object
    ).reindex(t.index)
    t["opp_days"] = pd.Series(
        {k: b.days_since_event for k, b in badges.items()}, dtype=float
    ).reindex(t.index)
    opp_export = {k: OP.export(b, day) for k, b in badges.items()}
    counts = {c: sum(1 for b in badges.values() if b.color == c) for c in (OP.GREEN, OP.AMBER, OP.RED)}  # fmt: skip
    site.write_json_file(
        paths.site,
        "opportunities.json",
        {"as_of": day, "base_up": base_up, "counts": counts, "stocks": opp_export},
    )
    log.info("opportunity badges: %s", counts)
    fred = M.load_fred(paths.data)
    fx_series = CO.fx_series(fred)  # the first paper strategies' recorded rule (FRED)
    fx_now = CO.fx_on(fx_series, as_of)
    user_fx, user_fx_id, user_fx_src = CO.user_fx_series(fred)  # ECB daily, for your own numbers
    user_fx_now = CO.fx_on(user_fx, as_of)
    if "label" in t:
        pick_scores, pick_summary = PK.compute(t, validated)
        for k in ("safety", "upside", "confidence", "balanced"):
            t[f"pick_{k}"] = pick_scores[k].reindex(t.index)
        t["pick_passes"] = pick_scores["passes_floor"].reindex(t.index).eq(True)
        race_live = ((extra.get("files") or {}).get("race.json") or {}).get("live") or {}
        site.write_json_file(
            paths.site,
            "picks.json",
            PK.export(
                t,
                pick_scores,
                pick_summary,
                as_of.strftime("%Y-%m-%d"),
                ctx.now,
                validated,
                zero_summary,
                {
                    "since": race_live.get("picks_since"),
                    **((race_live.get("strategies") or {}).get(MON.PICKS_STRATEGY) or {}),
                },
            ),
        )
        scores_snap = (extra.get("snapshots") or {}).get("scores")
        if scores_snap is not None:
            ps = pick_scores.reindex(scores_snap["ticker"])
            scores_snap["pick_balanced"] = ps["balanced"].where(ps["passes_floor"]).to_numpy()
            scores_snap["pick_rank"] = ps["pick_rank"].to_numpy()
            for k in ("safety", "upside", "confidence"):
                scores_snap[f"pick_{k}"] = ps[k].to_numpy()
            scores_snap["opp"] = t["opp"].reindex(scores_snap["ticker"]).astype("string").to_numpy()
        log.info("picks: %s", pick_summary)
        from convergealpha.decide import plan as PLAN

        site.write_json_file(
            paths.site,
            "plan.json",
            PLAN.export(
                t,
                day,
                ctx.now,
                validated,
                extra.get("reliability"),
                base_up,
                user_fx_now,
                (user_fx_id, user_fx_src),
            ),
        )

    # ---- exports
    meta = {
        "reliability": _reliability_meta(extra),
        "brokers": zero_summary,
    }
    site.write_screener(
        paths.site, t, SCREENER_FIELDS, as_of.strftime("%Y-%m-%d"), ctx.now, meta=meta
    )
    site.write_screener(
        paths.site,
        site.today_subset(t),
        SCREENER_FIELDS,
        as_of.strftime("%Y-%m-%d"),
        ctx.now,
        name="today.json",
        meta=meta,
    )
    site.write_intraday_placeholder(paths.site)
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
            # finanzen.net zero: True / False / None (unknown, never "not buyable").
            "zero": bool(z) if pd.api.types.is_bool(z := row.get("zero")) else None,
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
        payload["opportunity"] = opp_export.get(tk)
        site.write_stock(paths.site, tk, payload)

    market = market_summary(panel, snap)
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
    snapshot_paths: dict[str, Path] = {}
    for name, df in extra.get("snapshots", {}).items():
        from convergealpha.run import float32_snapshot
        from convergealpha.util.io import write_parquet

        day_dir = paths.data / "snapshots" / f"{as_of:%Y}" / f"{as_of:%Y%m%d}"
        path = day_dir / f"{name}.parquet"
        if path.exists():
            # Same-day re-run: the day's first file stays as it is (ledger entries store its
            # SHA-256 and the baseline race reads it); this run gets its own file.
            path = day_dir / f"{name}-{ctx.now:%H%M%S}.parquet"
        snapshot_paths[name] = write_parquet(float32_snapshot(df), path)

    ledger_info = ledger_step(ctx, t, extra, as_of, snapshot_paths.get("scores"))
    try:
        paper_info: dict[str, Any] | None = paper_step(
            ctx,
            panel,
            t,
            as_of,
            extra,
            validated,
            base_up,
            fx_series,
            fx_now,
            snapshot_paths,
            coverage,
        )
    except Exception:
        # Paper trading must never stop the site from being published.
        log.exception("paper trading step failed")
        paper_info = {"verified": False, "detail": "the paper-trading step failed", "entries": None}
    usage = None
    try:
        usage = MON.actions_usage()
    except Exception as e:
        log.warning("actions usage: %s", e)

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
            "ledger": ledger_info,
            "actions_usage": usage,
            "plugins": PL.status(paths.data, ctx.env),
            "brokers": zero_summary,
            "trade_ledger": paper_info,
            "fx_check": fx_check(fred),
            **extra.get("health", {}),
        },
    )
    log.info(
        "build done: %d stocks exported for %s in %.0fs", len(t), as_of.date(), time.time() - t0
    )
    return 0
