"""Replay one past day of paper trading and compare it with the sealed trade ledger.

Every daily build stores the exact table the strategies decided from (paper_inputs.parquet, its
SHA-256 in each day entry). `python -m convergealpha replay-paper --date YYYY-MM-DD` rebuilds every
strategy's book from the ledger entries before that day, runs that day again with the stored
inputs, the stored prices and the recorded EUR/USD rate, and reports, per strategy, whether every
fill, order, value and reason comes out the same. Anyone with the data can check that the record
was produced by the published rules and nothing else.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from convergealpha.ledger import ledger as LG
from convergealpha.paper import engine as E
from convergealpha.paper import strategies as S
from convergealpha.sources.prices import Panel

# Every column the strategies and the engine read from the build's table.
COLUMNS = (
    "name", "zero", "eligible", "blocked", "label", "price", "adv_dollar",
    "p_up_1m", "med_1m", "p10_1m", "p90_1m", "hit_up_1m_lo", "f5",
    "pick_passes", "pick_balanced", "pick_safety", "pick_upside", "pick_confidence",
    "opp", "opp_days", "opp_event",
)  # fmt: skip
NAME = "paper_inputs"
IGNORED = ("hash", "prev_hash", "seq", "recorded_at")


def save_inputs(data_dir: Path, t: pd.DataFrame, as_of: pd.Timestamp, now: datetime) -> tuple[str, str]:  # fmt: skip
    """Store the table the strategies decide from today. Returns (path in the data repo, SHA-256).
    A same-day re-run writes its own file; the first one stays as it is."""
    from convergealpha.util.io import write_parquet

    df = t[[c for c in COLUMNS if c in t]].copy()
    df.index = df.index.astype(str)
    df.index.name = "ticker"
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].astype("string")
    day_dir = data_dir / "snapshots" / f"{as_of:%Y}" / f"{as_of:%Y%m%d}"
    path = day_dir / f"{NAME}.parquet"
    if path.exists():
        path = day_dir / f"{NAME}-{now:%H%M%S}.parquet"
    write_parquet(df.reset_index(), path)
    return str(path.relative_to(data_dir)).replace("\\", "/"), LG.file_sha256(path) or ""


def load_inputs(data_dir: Path, rel: str) -> pd.DataFrame:
    df = pd.read_parquet(data_dir / rel).set_index("ticker")
    for c in df.columns:
        if str(df[c].dtype) == "string":
            df[c] = df[c].astype(object).where(df[c].notna(), None)
    return df


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        try:
            x, y = float(a), float(b)
        except (TypeError, ValueError):
            return False
        return (math.isnan(x) and math.isnan(y)) or math.isclose(x, y, rel_tol=1e-9, abs_tol=1e-9)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b, strict=True))
    return bool(a == b)


def differences(got: Sequence[dict[str, Any]], want: Sequence[dict[str, Any]]) -> list[str]:
    """Human-readable differences between replayed and recorded entries ([] = identical)."""
    out: list[str] = []
    got = [LG._clean(e) for e in got]  # the ledger stores floats rounded to 6 decimals
    if len(got) != len(want):
        out.append(f"{len(got)} entries replayed, {len(want)} recorded: {[e['kind'] for e in got]} vs {[e['kind'] for e in want]}")  # fmt: skip
    for g, w in zip(got, want, strict=False):
        keys = (set(g) | set(w)) - set(IGNORED)
        bad = sorted(k for k in keys if not _same(g.get(k), w.get(k)))
        if bad:
            out.append(f"{w.get('kind')} {w.get('ticker') or ''}: {', '.join(bad)} differ".replace("  ", " "))  # fmt: skip
    return out


def replay_day(data_dir: Path, panel: Panel, day: str, specs: Sequence[S.Spec] = S.ALL_SPECS) -> dict[str, Any]:  # fmt: skip
    entries = LG.read(data_dir / E.LEDGER)
    before = [e for e in entries if e["date"] < day or (e["kind"] == "start" and e["date"] <= day)]
    books = E.replay(before, specs)
    px = E.Prices(panel)
    d = pd.Timestamp(day)
    results: dict[str, Any] = {}
    cache: dict[str, pd.DataFrame] = {}
    for spec in specs:
        recorded = [e for e in entries if e.get("strategy") == spec.key and e["date"] == day and e["kind"] != "start"]  # fmt: skip
        dayrec = next((e for e in recorded if e["kind"] == "day"), None)
        if dayrec is None:
            continue
        inputs = dayrec.get("inputs") or {}
        today = None
        if dayrec.get("data") == "full":
            rel = inputs.get("paper_inputs")
            if not rel:
                results[spec.key] = {"status": "not replayable", "why": "the inputs of that day were not stored (before 15 Oct 2026)"}  # fmt: skip
                continue
            if rel not in cache:
                if LG.file_sha256(data_dir / rel) != inputs.get("paper_inputs_sha256"):
                    results[spec.key] = {"status": "mismatch", "why": f"{rel} changed since that day (SHA-256 differs)"}  # fmt: skip
                    continue
                cache[rel] = load_inputs(data_dir, rel)
            why_not = inputs.get("why_not")
            today = E.Today(cache[rel], list(inputs.get("validated") or []), inputs.get("base_up_1m"), why_not is None, why_not, inputs)  # fmt: skip
        got = E.process_day(books[spec.key], d, px, (float(dayrec["fx"]), str(dayrec["fx_date"])), today, dayrec["recorded_at"])  # fmt: skip
        diff = differences(got, recorded)
        results[spec.key] = {"status": "match" if not diff else "mismatch", "entries": len(recorded), **({"differences": diff[:10]} if diff else {})}  # fmt: skip
    statuses = [r["status"] for r in results.values()]
    return {
        "date": day,
        "strategies": results,
        "matched": statuses.count("match"),
        "mismatched": statuses.count("mismatch"),
        "not_replayable": statuses.count("not replayable"),
    }


__all__ = ["COLUMNS", "differences", "load_inputs", "replay_day", "save_inputs"]
