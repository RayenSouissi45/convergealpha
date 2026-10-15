"""Command line entry point: `python -m convergealpha <command>`."""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from convergealpha.config import Paths, load_dotenv
from convergealpha.export import health as H
from convergealpha.util import log as logutil

if TYPE_CHECKING:
    from convergealpha.run import RunContext as RunContextT

REPO_ROOT = Path(__file__).resolve().parents[3]
log = logutil.get(__name__)


def _paths(args: argparse.Namespace) -> Paths:
    return Paths.from_args(args.data, args.out, getattr(args, "cache", None))


def _cmd_health(args: argparse.Namespace) -> int:
    paths = _paths(args)
    states = H.load_states(paths.data) if paths.data.exists() else {}
    path = H.write_health(paths.site, datetime.now(UTC), os.environ, states)
    print(f"wrote {path}")
    return 0


def _ctx(args: argparse.Namespace, paths: Paths | None = None) -> RunContextT:
    from convergealpha.run import RunContext

    tickers = (
        [t.strip().upper() for t in args.tickers.split(",")]
        if getattr(args, "tickers", None)
        else None
    )
    return RunContext(paths=paths or _paths(args), now=datetime.now(UTC), tickers_override=tickers)


def _cmd_daily(args: argparse.Namespace) -> int:
    from convergealpha.run import run_daily

    return run_daily(_ctx(args))


def _cmd_prepare(args: argparse.Namespace) -> int:
    from convergealpha.run import job_prepare

    return job_prepare(_ctx(args))


def _cmd_fetch(args: argparse.Namespace) -> int:
    from convergealpha.run import job_fetch

    return job_fetch(_ctx(args), args.shard, args.shards, with_yahoo=not args.no_yahoo)


def _cmd_finnhub(args: argparse.Namespace) -> int:
    from convergealpha.run import job_finnhub

    return job_finnhub(_ctx(args))


def _cmd_build(args: argparse.Namespace) -> int:
    from convergealpha.run import job_build

    return job_build(_ctx(args))


def _cmd_bootstrap(args: argparse.Namespace) -> int:
    from convergealpha.run import job_bootstrap

    return job_bootstrap(_ctx(args), args.what)


def _cmd_demo(args: argparse.Namespace) -> int:
    """30 tickers end to end into web/public/data, in a separate data dir. Target: < 5 minutes."""
    from convergealpha.run import DEMO_TICKERS, RunContext, run_daily

    t0 = time.time()
    paths = Paths.from_args(
        args.data or REPO_ROOT / ".demo-data", args.out or REPO_ROOT / "web" / "public" / "data"
    )
    ctx = RunContext(paths=paths, now=datetime.now(UTC), tickers_override=list(DEMO_TICKERS))
    code = run_daily(ctx)
    print(f"demo finished in {time.time() - t0:.0f}s -> {paths.site}")
    return code


def _cmd_weekly(args: argparse.Namespace) -> int:
    from convergealpha.models import weekly

    ctx = _ctx(args)
    ctx.load()
    weekly.run(ctx, Path(args.models))
    if not args.no_validation:
        from convergealpha.validate import lab

        # A failing lab must not block the model bundle: without validation.json nothing is
        # marked validated, so every forecast keeps its RESEARCH MODE badge.
        try:
            lab.run(ctx, Path(args.models), Path(args.out))
        except Exception:
            logutil.get(__name__).exception("validation lab failed; models published unvalidated")
    return 0


def _cmd_intraday(args: argparse.Namespace) -> int:
    from convergealpha.intraday import run

    run(Path(args.out), datetime.now(UTC), dict(os.environ))
    return 0


def _cmd_universe(args: argparse.Namespace) -> int:
    from convergealpha.run import step_universe

    ctx = _ctx(args)
    ctx.job = "universe"
    ctx.load()
    step_universe(ctx)
    ctx.save()
    return 0


def _cmd_backfill(args: argparse.Namespace) -> int:
    from convergealpha.run import run_backfill

    return run_backfill(_paths(args), datetime.now(UTC), args.shard, args.shards, dict(os.environ))


def _cmd_research_rules(args: argparse.Namespace) -> int:
    """Sell rules and entry timing on 2016-2023, once per protocol (research/rules.py)."""
    import json

    import pandas as pd

    from convergealpha.ledger import experiments as X
    from convergealpha.research import rules as R
    from convergealpha.sources import prices as P
    from convergealpha.util.io import write_json

    data = Path(args.data)
    digest = R.protocol_digest()
    if X.already_run(data, R.PROTOCOL_ID, digest) and not args.repeat_for_audit:
        log.error("protocol %s (%s) already ran: a protocol is tested once", R.PROTOCOL_ID, digest)
        return 1
    oos = pd.read_parquet(Path(args.models) / "oos_devval.parquet")
    meta = Path(args.models) / "meta.json"
    model_version = (
        json.loads(meta.read_text(encoding="utf-8")).get("version") if meta.is_file() else None
    )
    res_extra = {
        "model_version": model_version,
        "signals_from": "walk-forward out-of-sample predictions 2016-2023",
    }
    sig = R.signals(oos)
    panel = P.build_panel(P.load_rows(data, sorted(set(sig["ticker"]))))
    ps = R.paths(sig, panel.open, panel.high, panel.low, panel.close)
    res = {**R.evaluate(ps), **res_extra}
    write_json(res, data / "validation" / "rules_research.json", pretty=True)
    if not args.repeat_for_audit:
        X.record(
            data,
            {
                "experiment": "sell rules and entry timing",
                "question": (
                    "Which exit rule and entry method give the best trade-off between losses, "
                    "missed recoveries and costs?"
                ),
                "protocol_id": R.PROTOCOL_ID,
                "protocol_digest": digest,
                "period": res["period"],
                "model_version": model_version,
                "status": "done",
                "summary": {k: res["exits"]["model"][k]["score"] for k in res["exits"]["model"]},
                "decision": res["decision"],
            },
        )
    log.info("research rules: %s", res["decision"])
    return 0


def _cmd_research_corrections(args: argparse.Namespace) -> int:
    import json

    import pandas as pd

    from convergealpha.ledger import experiments as X
    from convergealpha.research import corrections as RC
    from convergealpha.util.io import write_json

    data = Path(args.data)
    digest = RC.protocol_digest()
    if X.already_run(data, RC.PROTOCOL_ID, digest) and not args.repeat_for_audit:
        log.error("protocol %s (%s) already ran: a protocol is tested once", RC.PROTOCOL_ID, digest)
        return 1
    oos = pd.read_parquet(Path(args.models) / "oos_devval.parquet")
    meta = Path(args.models) / "meta.json"
    model_version = json.loads(meta.read_text(encoding="utf-8")).get("version") if meta.is_file() else None  # fmt: skip
    res = {**RC.evaluate(oos), "model_version": model_version}
    write_json(res, data / "validation" / "corrections_research.json", pretty=True)
    if not args.repeat_for_audit:
        X.record(
            data,
            {
                "experiment": "sector and stock corrections of the chances of rising",
                "question": "Does a small correction per sector (and per stock) make the chances of rising more accurate?",
                "protocol_id": RC.PROTOCOL_ID,
                "protocol_digest": digest,
                "period": res["period"],
                "model_version": model_version,
                "status": "done",
                "summary": {
                    h: {"gain_sector": v["gain_sector"], "gain_stock": v["gain_stock"]}
                    for h, v in res["horizons"].items()
                },
                "decision": res["decision"],
            },
        )
    log.info("research corrections: %s", res["decision"])
    return 0


def _cmd_research_filters(args: argparse.Namespace) -> int:
    import json

    import pandas as pd

    from convergealpha.ledger import experiments as X
    from convergealpha.research import filters as RF
    from convergealpha.util.io import write_json

    data = Path(args.data)
    digest = RF.protocol_digest()
    if X.already_run(data, RF.PROTOCOL_ID, digest) and not args.repeat_for_audit:
        log.error("protocol %s (%s) already ran: a protocol is tested once", RF.PROTOCOL_ID, digest)
        return 1
    models = Path(args.models)
    oos = pd.read_parquet(models / "oos_devval.parquet")
    cols = ["date", "ticker", "sector", "eligible", "fcf_yield", "debt_ebitda", "accruals"]
    ds = pd.read_parquet(models / "dataset.parquet", columns=cols)
    meta = models / "meta.json"
    model_version = json.loads(meta.read_text(encoding="utf-8")).get("version") if meta.is_file() else None  # fmt: skip
    res = {**RF.evaluate(oos, ds), "model_version": model_version}
    write_json(res, data / "validation" / "filters_research.json", pretty=True)
    if not args.repeat_for_audit:
        X.record(
            data,
            {
                "experiment": "quality filters on the model's top picks",
                "question": "Do cash-burn, debt, price or earnings-quality filters improve the model's top 2%?",
                "protocol_id": RF.PROTOCOL_ID,
                "protocol_digest": digest,
                "period": res["period"],
                "model_version": model_version,
                "status": "done",
                "summary": {c: v["all"]["score"] for c, v in res["filters"].items()},
                "decision": res["decision"],
            },
        )
    log.info("research filters: %s", res["decision"])
    return 0


def _cmd_register_exam2(args: argparse.Namespace) -> int:
    from convergealpha.models import challenger as CH
    from convergealpha.research import exam2 as E2

    e = E2.register(Path(args.data))
    log.info("exam 2: %s", "registered" if e else "already registered")
    c = CH.register(Path(args.data))
    log.info("challenger: %s", "registered" if c else "already registered")
    return 0


def _cmd_model_gate(args: argparse.Namespace) -> int:
    import json

    from convergealpha.models import gate as G
    from convergealpha.util.io import write_json

    new = json.loads((Path(args.models) / "meta.json").read_text(encoding="utf-8"))
    prev_path = Path(args.previous) / "meta.json"
    prev = json.loads(prev_path.read_text(encoding="utf-8")) if prev_path.is_file() else None
    res = G.check(new, prev)
    write_json(res, Path(args.data) / "state" / "model_gate.json", pretty=True)
    for c in res["checks"]:
        log.info("model gate %s: %s (%s)", c["check"], "ok" if c["ok"] else "FAILED", c["detail"])
    if not res["passed"]:
        log.error("model gate failed: %s is not published; the daily builds keep %s", res["new"], res["previous"])  # fmt: skip
        return 1
    return 0


def _cmd_replay_paper(args: argparse.Namespace) -> int:
    import json

    from convergealpha.ledger import ledger as LG
    from convergealpha.paper import engine as PE
    from convergealpha.paper import replay as RP
    from convergealpha.sources import prices as P

    data = Path(args.data)
    entries = LG.read(data / PE.LEDGER)
    tickers = {str(e["ticker"]) for e in entries if e.get("ticker")}
    for e in entries:
        rel = (e.get("inputs") or {}).get("paper_inputs") if e.get("date") == args.date else None
        if rel and (data / rel).is_file():
            tickers |= set(RP.load_inputs(data, rel).index.astype(str))
            break
    panel = P.build_panel(P.load_rows(data, sorted(tickers)))
    out = RP.replay_day(data, panel, args.date)
    print(json.dumps(out, indent=2))
    return 1 if out["mismatched"] else 0


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv(REPO_ROOT / ".env")
    logutil.setup()
    parser = argparse.ArgumentParser(prog="convergealpha")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(
        p: argparse.ArgumentParser,
        data_default: str | None = "data",
        out_default: str | None = "site-data",
    ) -> None:
        p.add_argument("--data", default=data_default, help="clone of the private data repo")
        p.add_argument("--out", default=out_default, help="output directory for site JSON")
        p.add_argument("--cache", default=None, help="scratch directory (rebuildable)")

    def tick(p: argparse.ArgumentParser) -> None:
        p.add_argument("--tickers", default=None, help="comma-separated subset (testing)")

    for name, func, help_text in (
        ("daily", _cmd_daily, "run every job in one process (local runs)"),
        ("prepare", _cmd_prepare, "universe, SEC filings, insiders, fundamentals, FRED, FINRA"),
        ("finnhub", _cmd_finnhub, "earnings calendar, recommendation trends, news"),
        ("build", _cmd_build, "compute everything and export the website JSON"),
    ):
        p = sub.add_parser(name, help=help_text)
        common(p)
        tick(p)
        p.set_defaults(func=func)

    p = sub.add_parser("fetch", help="prices + Yahoo analyst data for one shard of the universe")
    common(p)
    tick(p)
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--shards", type=int, default=1)
    p.add_argument("--no-yahoo", action="store_true")
    p.set_defaults(func=_cmd_fetch)

    p = sub.add_parser(
        "bootstrap", help="history loads and weekly lists: sec | fundamentals | finra | brokers"
    )
    common(p)
    tick(p)
    p.add_argument("what", choices=["sec", "fundamentals", "finra", "brokers"])
    p.set_defaults(func=_cmd_bootstrap)

    p = sub.add_parser("demo", help="30-ticker end-to-end run into web/public/data")
    common(p, None, None)
    p.set_defaults(func=_cmd_demo)

    p = sub.add_parser("backfill", help="download full price history for one shard of the universe")
    common(p)
    p.add_argument("--shard", type=int, required=True)
    p.add_argument("--shards", type=int, required=True)
    p.set_defaults(func=_cmd_backfill)

    p = sub.add_parser(
        "intraday", help="risk/event check for candidates and holdings (adds intraday.json)"
    )
    common(p)
    p.set_defaults(func=_cmd_intraday)

    p = sub.add_parser("weekly", help="rebuild the dataset, train and validate the models")
    common(p)
    tick(p)
    p.add_argument("--models", default="models-out", help="where to write the model bundle")
    p.add_argument("--no-validation", action="store_true")
    p.set_defaults(func=_cmd_weekly)

    p = sub.add_parser(
        "research-rules", help="test sell rules and entry timing on 2016-2023 (once)"
    )
    common(p)
    p.add_argument("--models", default="models-out", help="model bundle with oos_devval.parquet")
    p.add_argument("--repeat-for-audit", action="store_true", help="re-run without recording (checks reproducibility)")  # fmt: skip
    p.set_defaults(func=_cmd_research_rules)

    p = sub.add_parser(
        "research-corrections", help="test sector and stock corrections on 2016-2023 (once)"
    )
    common(p)
    p.add_argument("--models", default="models-out", help="model bundle with oos_devval.parquet")
    p.add_argument("--repeat-for-audit", action="store_true", help="re-run without recording (checks reproducibility)")  # fmt: skip
    p.set_defaults(func=_cmd_research_corrections)

    p = sub.add_parser("research-filters", help="test quality filters on the top picks (once)")
    common(p)
    p.add_argument("--models", default="models-out", help="bundle with oos_devval and dataset")
    p.add_argument("--repeat-for-audit", action="store_true", help="re-run without recording (checks reproducibility)")  # fmt: skip
    p.set_defaults(func=_cmd_research_filters)

    p = sub.add_parser("register-exam2", help="seal the second clean exam's plan in advance")
    common(p)
    p.set_defaults(func=_cmd_register_exam2)

    p = sub.add_parser(
        "model-gate", help="compare a new weekly model bundle with the one in use (rollback)"
    )
    common(p)
    p.add_argument("--models", default="models-out", help="the new bundle")
    p.add_argument("--previous", required=True, help="the bundle the daily builds use now")
    p.set_defaults(func=_cmd_model_gate)

    p = sub.add_parser(
        "replay-paper", help="replay one day of paper trading and compare it with the ledger"
    )
    common(p)
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.set_defaults(func=_cmd_replay_paper)

    p = sub.add_parser("universe", help="refresh the stock universe only")
    common(p)
    p.set_defaults(func=_cmd_universe)

    p = sub.add_parser("health", help="write health.json only")
    common(p)
    p.set_defaults(func=_cmd_health)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
