"""Command line entry point: `python -m convergealpha <command>`."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from convergealpha.export.health import write_health


def _cmd_health(args: argparse.Namespace) -> int:
    path = write_health(Path(args.out), datetime.now(UTC), os.environ)
    print(f"wrote {path}")
    return 0


def _cmd_daily(args: argparse.Namespace) -> int:
    # Phase 0: the daily run only reports health. Each later phase adds its steps here,
    # and health.json is always written last so it reflects what actually happened.
    return _cmd_health(args)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="convergealpha")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, func, help_text in (
        ("daily", _cmd_daily, "run every implemented daily step and export site JSON"),
        ("health", _cmd_health, "write health.json only"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--out", default="site-data", help="output directory for site JSON")
        p.set_defaults(func=func)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
