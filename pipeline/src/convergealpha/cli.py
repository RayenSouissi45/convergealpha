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

    p = sub.add_parser("bootstrap", help="one-time history loads: sec | fundamentals | finra")
    common(p)
    tick(p)
    p.add_argument("what", choices=["sec", "fundamentals", "finra"])
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
