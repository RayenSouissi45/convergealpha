"""Immutable, hash-chained prediction ledger (spec section 10).

ledger/ledger.jsonl    one line per new signal (BUY, STRONG BUY, SELL / RISK WARNING), written
                       the day it appears, BEFORE the outcome is known. Never edited.
ledger/outcomes.jsonl  realized outcomes, appended later (also hash-chained), referencing entries.

Each line carries `prev_hash` and `hash = sha256(prev_hash + canonical JSON of the entry)`, so
changing any past line breaks every hash after it (verify() detects it).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from convergealpha.config import HORIZON_NAMES, HORIZONS

GENESIS = "0" * 64
SIGNAL_LABELS = ("STRONG BUY — TOP CONVICTION", "BUY", "SELL / RISK WARNING")


def _canonical(entry: dict[str, Any]) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def _clean(v: Any) -> Any:
    if isinstance(v, float):
        return None if not math.isfinite(v) else round(v, 6)
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if hasattr(v, "item"):
        return _clean(v.item())
    return v


def read(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def append(path: Path, entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append entries, chaining hashes. Returns the written entries."""
    existing = read(path)
    prev = existing[-1]["hash"] if existing else GENESIS
    seq = existing[-1]["seq"] + 1 if existing else 1
    written = []
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        for e in entries:
            e = _clean({**e, "seq": seq, "prev_hash": prev})
            e["hash"] = hashlib.sha256((prev + _canonical(e)).encode("utf-8")).hexdigest()
            f.write(json.dumps(e, sort_keys=True, ensure_ascii=False) + "\n")
            written.append(e)
            prev = e["hash"]
            seq += 1
    return written


def verify(path: Path) -> tuple[bool, str]:
    prev = GENESIS
    for i, e in enumerate(read(path)):
        if e.get("prev_hash") != prev:
            return False, f"line {i + 1}: prev_hash does not match the previous entry"
        expect = hashlib.sha256((prev + _canonical(e)).encode("utf-8")).hexdigest()
        if e.get("hash") != expect:
            return False, f"line {i + 1}: content does not match its hash (edited?)"
        prev = e["hash"]
    return True, "ok"


def file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def new_signals(today: pd.DataFrame, previous_labels: dict[str, str]) -> pd.DataFrame:
    """Stocks whose label became a signal today (not a signal yesterday, or a different one)."""
    t = today[today["label"].isin(SIGNAL_LABELS)]
    keep = [tk for tk, lab in t["label"].items() if previous_labels.get(str(tk)) != lab]
    return t.loc[keep]


def make_entries(
    sig: pd.DataFrame,
    as_of: pd.Timestamp,
    model_version: str | None,
    snapshot_id: str | None,
    snapshot_sha: str | None,
    sections: dict[str, dict[str, Any]],
    previous_labels: dict[str, str],
    generated_at: str,
) -> list[dict[str, Any]]:
    out = []
    for tk, r in sig.iterrows():
        sec = sections.get(str(tk), {})
        fc = (sec.get("forecast") or {}).get("horizons") or {}
        plan = sec.get("plan") or {}
        out.append(
            {
                "recorded_at": generated_at,
                "date": as_of.strftime("%Y-%m-%d"),
                "ticker": str(tk),
                "label": r["label"],
                "previous_label": previous_labels.get(str(tk)),
                "tier": None if pd.isna(r.get("tier")) else int(r["tier"]),
                "price": float(r["price"]),
                "p_hat": _f(r.get("p_hat")),
                "p_lower": _f((sec.get("decision") or {}).get("p_lower")),
                "ev": _f(r.get("ev")),
                "forecast": {
                    k: {
                        kk: _f(vv)
                        for kk, vv in v.items()
                        if kk in ("p_up", "p_beat", "median", "p10", "p90")
                    }
                    for k, v in fc.items()
                },
                "plan": {
                    k: _f(plan.get(k))
                    for k in ("entry", "planned_exit", "risk_per_share", "atr", "sell_third_at")
                }
                if plan
                else None,
                "families": {f: _f(r.get(f)) for f in ("f1", "f2", "f3", "f4", "f5", "f6")},
                "model_version": model_version,
                "method": (sec.get("forecast") or {}).get("method"),
                "inputs_snapshot": snapshot_id,
                "inputs_sha256": snapshot_sha,
            }
        )
    return out


def _f(v: Any) -> float | None:
    try:
        x = float(v)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- outcomes


def due_outcomes(
    entries: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    tr: pd.DataFrame,
    spy: pd.Series,
    as_of: pd.Timestamp,
) -> list[dict[str, Any]]:
    """Outcomes whose horizon has elapsed and that are not recorded yet."""
    done = {(o["entry_seq"], o["horizon"]) for o in outcomes}
    idx = tr.index
    out = []
    for e in entries:
        d = pd.Timestamp(e["date"])
        if e["ticker"] not in tr.columns or d not in idx:
            continue
        i = idx.get_loc(d)
        for h in HORIZONS:
            name = HORIZON_NAMES[h]
            if (e["seq"], name) in done or i + h >= len(idx) or idx[i + h] > as_of:
                continue
            p0, p1 = tr[e["ticker"]].iloc[i], tr[e["ticker"]].iloc[i + h]
            s0, s1 = spy.iloc[i], spy.iloc[i + h]
            if not (pd.notna(p0) and pd.notna(p1) and p0 > 0):
                continue
            ret = float(p1 / p0 - 1)
            exc = ret - float(s1 / s0 - 1)
            fc = (e.get("forecast") or {}).get(name) or {}
            out.append(
                {
                    "entry_seq": e["seq"],
                    "entry_hash": e["hash"],
                    "ticker": e["ticker"],
                    "label": e["label"],
                    "horizon": name,
                    "measured_on": idx[i + h].strftime("%Y-%m-%d"),
                    "return": ret,
                    "excess": exc,
                    "up": ret > 0,
                    "beat": exc > 0,
                    "predicted_p_up": fc.get("p_up"),
                    "predicted_p_beat": fc.get("p_beat"),
                    "predicted_p_hat": e.get("p_hat") if name == "3m" else None,
                }
            )
    return out
