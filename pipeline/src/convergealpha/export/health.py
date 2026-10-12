"""health.json: what ran, when, and how fresh every data source is.

Per-source state is kept in the data repo (state/sources.json) so a source that was not refreshed
today still shows its last success. The file must never contain secret values, only whether each
secret is configured.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from convergealpha import BUILD_PHASE, __version__
from convergealpha.config import SECRETS, secret
from convergealpha.util.io import read_json, write_json

SCHEMA_VERSION = 2

SourceStatus = Literal["ok", "stale", "failed", "not_configured", "not_implemented"]


@dataclass(frozen=True)
class SourceSpec:
    id: str
    name: str
    phase: int
    needs_secret: str | None = None
    # Days after the last success before the source counts as stale.
    stale_after_days: float = 4.0
    # Optional sources never make the overall status degraded.
    optional: bool = False


SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec("universe", "Universe (SEC + Nasdaq Trader lists)", 1, "SEC_USER_AGENT"),
    SourceSpec("prices", "Daily prices (Yahoo Finance)", 1),
    SourceSpec("sec_meta", "SEC company data (sector, filings, 8-K items)", 2, "SEC_USER_AGENT", 8),
    SourceSpec("analyst", "Analyst consensus, targets, rating changes", 2, stale_after_days=8),
    SourceSpec("estimates", "EPS estimates and revisions", 2, stale_after_days=8),
    SourceSpec("earnings", "Earnings history and calendar", 2, "FINNHUB_API_KEY"),
    SourceSpec("insiders", "Insider trades (SEC Form 4)", 2, "SEC_USER_AGENT"),
    SourceSpec("fundamentals", "Fundamentals (SEC XBRL, point-in-time)", 2, "SEC_USER_AGENT", 10),
    SourceSpec("short_interest", "Short interest (FINRA)", 2, stale_after_days=20),
    SourceSpec("options", "Options implied volatility", 2),
    SourceSpec("macro", "Macro and regime (FRED)", 2, "FRED_API_KEY"),
    SourceSpec("news", "News and filings", 2, "FINNHUB_API_KEY"),
    SourceSpec("institutional", "Institutional ownership", 2, stale_after_days=10),
    SourceSpec("danelfin", "Danelfin AI score (optional)", 2, "DANELFIN_API_KEY", optional=True),
    SourceSpec(
        "ai_news", "AI news event extraction (optional)", 2, "ANTHROPIC_API_KEY", optional=True
    ),
)


def state_path(data_dir: Path) -> Path:
    return data_dir / "state" / "sources.json"


def load_states(data_dir: Path) -> dict[str, dict[str, Any]]:
    states = read_json(state_path(data_dir), {})
    return states if isinstance(states, dict) else {}


def record(
    states: dict[str, dict[str, Any]],
    source_id: str,
    now: datetime,
    *,
    ok: bool,
    as_of: str | None = None,
    records: int | None = None,
    detail: str = "",
    coverage: float | None = None,
) -> None:
    """Update one source's state after a fetch attempt."""
    prev = states.get(source_id, {})
    stamp = now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    states[source_id] = {
        "last_attempt": stamp,
        "last_success": stamp if ok else prev.get("last_success"),
        "as_of": as_of if ok else prev.get("as_of"),
        "records": records if ok else prev.get("records"),
        "coverage": coverage if ok else prev.get("coverage"),
        "last_error": None if ok else detail,
        "detail": detail if ok else prev.get("detail", ""),
    }


def save_states(data_dir: Path, states: dict[str, dict[str, Any]]) -> None:
    write_json(states, state_path(data_dir), pretty=True)


def _status(
    spec: SourceSpec, state: dict[str, Any] | None, env: Mapping[str, str], now: datetime
) -> SourceStatus:
    if spec.phase > BUILD_PHASE and not state:
        return "not_implemented"
    if spec.needs_secret and secret(spec.needs_secret, env) is None:
        return "not_configured"
    if not state or not state.get("last_success"):
        return "failed" if state and state.get("last_error") else "stale"
    last = datetime.fromisoformat(str(state["last_success"]).replace("Z", "+00:00"))
    if state.get("last_error"):
        return "failed" if (now - last).days > spec.stale_after_days else "stale"
    if (now - last).total_seconds() > spec.stale_after_days * 86400:
        return "stale"
    return "ok"


def _source_entry(
    spec: SourceSpec, state: dict[str, Any] | None, env: Mapping[str, str], now: datetime
) -> dict[str, Any]:
    status = _status(spec, state, env, now)
    state = state or {}
    if status == "not_implemented":
        detail = f"Connected in build phase {spec.phase}."
    elif status == "not_configured":
        detail = f"Needs the {spec.needs_secret} secret (see SETUP.md)."
    elif not state.get("last_success") and not state.get("last_error"):
        detail = "Not fetched yet."
    else:
        detail = state.get("last_error") or state.get("detail") or ""
    return {
        "id": spec.id,
        "name": spec.name,
        "phase": spec.phase,
        "status": status,
        "optional": spec.optional,
        "last_success": state.get("last_success"),
        "as_of": state.get("as_of"),
        "records": state.get("records"),
        "coverage": state.get("coverage"),
        "detail": detail,
        "needs_secret": spec.needs_secret,
    }


def _run_info(env: Mapping[str, str]) -> dict[str, Any]:
    run_id = env.get("GITHUB_RUN_ID")
    repo = env.get("GITHUB_REPOSITORY")
    server = env.get("GITHUB_SERVER_URL", "https://github.com")
    return {
        "workflow": env.get("GITHUB_WORKFLOW", "local"),
        "event": env.get("GITHUB_EVENT_NAME", "manual"),
        "run_id": run_id,
        "run_url": f"{server}/{repo}/actions/runs/{run_id}" if run_id and repo else None,
        "git_sha": env.get("GITHUB_SHA"),
    }


def build_health(
    now: datetime,
    env: Mapping[str, str],
    states: Mapping[str, dict[str, Any]] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    states = states or {}
    sources = [_source_entry(s, states.get(s.id), env, now) for s in SOURCES]
    core = [s for s in sources if not s["optional"] and s["status"] != "not_implemented"]
    live = sum(1 for s in sources if s["status"] == "ok")
    if any(s["status"] == "failed" and s["id"] in ("prices", "universe") for s in sources):
        status = "failed"
    elif any(s["status"] in ("failed", "stale") for s in core):
        status = "degraded"
    else:
        status = "ok"
    extra = dict(extra or {})
    health: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "pipeline_version": __version__,
        "build_phase": BUILD_PHASE,
        "status": status,
        "status_detail": (
            f"Pipeline ran. {live} of {len(sources)} data sources live (build phase {BUILD_PHASE})."
        ),
        "research_mode": True,
        "validated": [],
        "model_version": None,
        "kill_switch": {"implemented": False, "active": None, "reasons": []},
        "run": _run_info(env),
        "sources": sources,
        "secrets": [
            {
                "name": s.name,
                "purpose": s.purpose,
                "required": s.required,
                "used_from_phase": s.used_from_phase,
                "present": secret(s.name, env) is not None,
            }
            for s in SECRETS
        ],
    }
    health.update(extra)
    return health


def write_health(
    out_dir: Path,
    now: datetime,
    env: Mapping[str, str],
    states: Mapping[str, dict[str, Any]] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> Path:
    return write_json(build_health(now, env, states, extra), out_dir / "health.json", pretty=True)
