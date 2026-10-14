"""The incident log: every problem the daily build notices, when it started and when it ended.

Append-only and hash-chained like the other ledgers (ledger/incidents.jsonl in the private data repo)
and published in full as incidents.json: nothing is hidden or deleted, so the app's reliability can
be checked from its own record. An incident is opened the first day a check fails and resolved the
first day it passes again; a same-day re-run adds nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from convergealpha.ledger import ledger as LG

PATH = Path("ledger") / "incidents.jsonl"
COVERAGE_MIN = 0.9  # under 90% of stocks priced for the day is an incident

TITLES = {
    "source_failed": "A data source failed",
    "price_coverage": "Prices missing for many stocks",
    "price_check": "Prices failed a quality check",
    "fx_gap": "ECB and FRED exchange rates disagree",
    "signal_ledger": "Signal ledger check failed",
    "trade_ledger": "Trade ledger check failed",
    "paper_trading": "Paper trading did not run normally",
    "kill_switch": "Kill switch active",
    "model_fallback": "Model forecasts not available",
    "model_rollback": "A new model failed its check; the previous one stays in use",
}


def path(data_dir: Path) -> Path:
    return data_dir / PATH


def detect(health: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Failing checks in this build's health data: kind -> {severity, detail}."""
    out: dict[str, dict[str, Any]] = {}
    failed = [s["name"] for s in health.get("sources") or [] if s.get("status") == "failed" and not s.get("optional")]  # fmt: skip
    if failed:
        out["source_failed"] = {"severity": "warning", "detail": ", ".join(failed)}
    prices = next((s for s in health.get("sources") or [] if s.get("id") == "prices"), None)
    cov = (prices or {}).get("coverage")
    if isinstance(cov, (int, float)) and cov < COVERAGE_MIN:
        out["price_coverage"] = {"severity": "serious" if cov <= 0.5 else "warning", "detail": f"{cov:.0%} of stocks priced"}  # fmt: skip
    dq = health.get("data_quality") or {}
    if dq.get("blocked"):
        names = ", ".join(i["ticker"] for i in (dq.get("issues") or []) if i.get("blocks"))[:200]
        out["price_check"] = {"severity": "warning", "detail": f"{dq['blocked']} stock(s) blocked for new buys: {names}"}  # fmt: skip
    fx = health.get("fx_check") or {}
    if fx.get("ok") is False:
        out["fx_gap"] = {"severity": "warning", "detail": f"largest gap {fx.get('max_gap_30d'):.2%} (limit {fx.get('limit'):.2%})"}  # fmt: skip
    led = health.get("ledger") or {}
    if led and led.get("verified") is False:
        out["signal_ledger"] = {"severity": "critical", "detail": str(led.get("detail") or "")}
    tl = health.get("trade_ledger") or {}
    if tl and tl.get("verified") is False:
        out["trade_ledger"] = {"severity": "critical", "detail": str(tl.get("detail") or "")}
    if tl and tl.get("status"):
        out["paper_trading"] = {"severity": "warning", "detail": str(tl["status"])}
    ks = health.get("kill_switch") or {}
    if ks.get("active"):
        out["kill_switch"] = {"severity": "serious", "detail": "; ".join(ks.get("reasons") or [])}
    gate = health.get("model_gate") or {}
    if gate and gate.get("passed") is False:
        why = "; ".join(c["detail"] for c in gate.get("checks") or [] if not c.get("ok"))
        out["model_rollback"] = {"severity": "warning", "detail": f"{gate.get('new')} not used, {gate.get('previous')} kept: {why}"}  # fmt: skip
    if health.get("forecast_method") and health.get("forecast_method") != "model":
        out["model_fallback"] = {"severity": "serious", "detail": "the fallback estimate was used"}
    return out


def open_now(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """kind -> the entry that opened it, for incidents not resolved yet."""
    state: dict[str, dict[str, Any]] = {}
    for e in entries:
        if e.get("status") == "open":
            state[e["incident"]] = e
        elif e.get("status") == "resolved":
            state.pop(e["incident"], None)
    return state


def record(data_dir: Path, day: str, found: Mapping[str, Mapping[str, Any]], recorded_at: str) -> list[dict[str, Any]]:  # fmt: skip
    """Open new incidents and resolve the ones that passed today. Idempotent per day."""
    p = path(data_dir)
    entries = LG.read(p) if p.is_file() else []
    if any(e.get("date") == day for e in entries):
        return []  # this day is recorded already (same-day re-run)
    current = open_now(entries)
    new: list[dict[str, Any]] = []
    for kind, v in found.items():
        if kind not in current:
            new.append({"kind": "incident", "incident": kind, "status": "open", "date": day, "recorded_at": recorded_at, "title": TITLES.get(kind, kind), **v})  # fmt: skip
    for kind, opened in current.items():
        if kind not in found:
            new.append({"kind": "incident", "incident": kind, "status": "resolved", "date": day, "recorded_at": recorded_at, "title": TITLES.get(kind, kind), "opened": opened.get("date")})  # fmt: skip
    if not new:
        # A quiet day is recorded too, so "no incident" is a fact in the log, not a gap.
        new.append({"kind": "check", "status": "ok" if not current else "unchanged", "date": day, "recorded_at": recorded_at, "open": sorted(current)})  # fmt: skip
    return LG.append(p, new)[-len(new) :]


def export(data_dir: Path, limit: int = 120) -> dict[str, Any]:
    p = path(data_dir)
    entries = LG.read(p) if p.is_file() else []
    ok, detail = LG.verify(p) if p.is_file() else (True, "empty")
    keep = ("incident", "status", "date", "title", "severity", "detail", "opened")
    events = [{k: e.get(k) for k in keep} for e in entries if e.get("kind") == "incident"]
    # A day counts as troubled when an incident was still open at the end of it.
    days: list[str] = []
    bad_days = 0
    state: set[str] = set()
    for e in entries:
        d = e.get("date")
        if d and (not days or days[-1] != d):
            if days and state:
                bad_days += 1
            days.append(d)
        if e.get("status") == "open":
            state.add(e["incident"])
        elif e.get("status") == "resolved":
            state.discard(e["incident"])
    if days and state:
        bad_days += 1
    return {
        "verified": ok,
        "detail": detail,
        "days_checked": len(days),
        "days_with_open_incident": bad_days,
        "since": days[0] if days else None,
        "open": [{k: e.get(k) for k in keep} for e in open_now(entries).values()],
        "events": list(reversed(events))[:limit],
    }


__all__ = ["TITLES", "detect", "export", "open_now", "record"]
