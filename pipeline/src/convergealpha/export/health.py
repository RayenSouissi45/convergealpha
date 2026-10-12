"""health.json: what ran, when, and how fresh every data source is.

The website's Health page and the global banners read this file. It must never contain
secret values, only whether each secret is configured.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from convergealpha import BUILD_PHASE, __version__
from convergealpha.config import SECRETS, secret

SCHEMA_VERSION = 1

SourceStatus = Literal["ok", "stale", "failed", "not_configured", "not_implemented"]


@dataclass(frozen=True)
class SourceSpec:
    id: str
    name: str
    phase: int
    needs_secret: str | None = None


SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec("universe", "Universe (SEC + Nasdaq Trader lists)", 1, "SEC_USER_AGENT"),
    SourceSpec("prices", "Daily prices", 1),
    SourceSpec("analyst", "Analyst consensus, targets, rating changes", 2),
    SourceSpec("estimates", "EPS estimates and revisions", 2),
    SourceSpec("earnings", "Earnings history and calendar", 2, "FINNHUB_API_KEY"),
    SourceSpec("insiders", "Insider trades (SEC Form 4)", 2, "SEC_USER_AGENT"),
    SourceSpec("fundamentals", "Fundamentals (SEC XBRL, point-in-time)", 2, "SEC_USER_AGENT"),
    SourceSpec("short_interest", "Short interest (FINRA)", 2),
    SourceSpec("options", "Options implied volatility", 2),
    SourceSpec("macro", "Macro and regime (FRED)", 2, "FRED_API_KEY"),
    SourceSpec("news", "News and filings", 2, "FINNHUB_API_KEY"),
    SourceSpec("institutional", "Institutional ownership (13F)", 2, "SEC_USER_AGENT"),
)


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


def _source_entry(spec: SourceSpec) -> dict[str, Any]:
    # Phase 0: no source is connected yet. Later phases replace this with real fetch results.
    status: SourceStatus = "not_implemented"
    return {
        "id": spec.id,
        "name": spec.name,
        "phase": spec.phase,
        "status": status,
        "last_success": None,
        "as_of": None,
        "records": None,
        "detail": f"Connected in build phase {spec.phase}.",
        "needs_secret": spec.needs_secret,
    }


def build_health(now: datetime, env: Mapping[str, str]) -> dict[str, Any]:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    sources = [_source_entry(s) for s in SOURCES]
    live = sum(1 for s in sources if s["status"] == "ok")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "pipeline_version": __version__,
        "build_phase": BUILD_PHASE,
        "status": "ok",
        "status_detail": (
            f"Pipeline ran. {live} of {len(sources)} data sources connected "
            f"(build phase {BUILD_PHASE})."
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


def write_health(out_dir: Path, now: datetime, env: Mapping[str, str]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "health.json"
    path.write_text(json.dumps(build_health(now, env), indent=2) + "\n", encoding="utf-8")
    return path
