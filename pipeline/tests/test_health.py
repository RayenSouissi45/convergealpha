import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from convergealpha.cli import main
from convergealpha.config import NEW_YORK, decision_cutoff
from convergealpha.export import health as H

NOW = datetime(2026, 10, 12, 22, 31, 5, tzinfo=UTC)
ENV = {"SEC_USER_AGENT": "ConvergeAlpha someone@example.com"}


def by_id(health: dict) -> dict:
    return {s["id"]: s for s in health["sources"]}


def test_health_without_state_is_honest() -> None:
    health = H.build_health(NOW, {})
    assert health["generated_at"] == "2026-10-12T22:31:05Z"
    assert health["research_mode"] is True
    assert health["validated"] == []
    assert health["run"]["workflow"] == "local"
    src = by_id(health)
    assert src["universe"]["status"] == "not_configured"  # needs SEC_USER_AGENT
    assert src["prices"]["status"] == "stale" and src["prices"]["detail"] == "Not fetched yet."
    assert all(s["last_success"] is None for s in health["sources"])


def test_recorded_success_and_staleness() -> None:
    states: dict = {}
    H.record(
        states, "prices", NOW, ok=True, as_of="2026-10-12", records=5300, coverage=0.99, detail="ok"
    )
    H.record(
        states, "universe", NOW - timedelta(days=10), ok=True, as_of="2026-10-02", records=5300
    )
    src = by_id(H.build_health(NOW, ENV, states))
    assert src["prices"]["status"] == "ok" and src["prices"]["records"] == 5300
    assert src["universe"]["status"] == "stale"


def test_failure_keeps_last_success() -> None:
    states: dict = {}
    H.record(states, "prices", NOW - timedelta(days=1), ok=True, as_of="2026-10-09", records=5000)
    H.record(states, "prices", NOW, ok=False, detail="Update failed: Timeout")
    p = states["prices"]
    assert p["as_of"] == "2026-10-09" and p["last_error"] == "Update failed: Timeout"
    health = H.build_health(NOW, ENV, states)
    assert by_id(health)["prices"]["status"] == "stale"
    assert health["status"] == "degraded"


def test_health_reports_presence_but_never_secret_values() -> None:
    env = {
        "FINNHUB_API_KEY": "super-secret-finnhub",
        "SEC_USER_AGENT": "ConvergeAlpha someone@example.com",
        "FRED_API_KEY": "   ",
    }
    health = H.build_health(NOW, env)
    present = {s["name"]: s["present"] for s in health["secrets"]}
    assert present["FINNHUB_API_KEY"] is True
    assert present["FRED_API_KEY"] is False  # blank counts as missing
    dumped = json.dumps(health)
    assert "super-secret-finnhub" not in dumped
    assert "someone@example.com" not in dumped


def test_health_links_the_github_run() -> None:
    env = {
        "GITHUB_WORKFLOW": "daily",
        "GITHUB_EVENT_NAME": "schedule",
        "GITHUB_RUN_ID": "42",
        "GITHUB_REPOSITORY": "me/convergealpha",
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_SHA": "abc123",
    }
    run = H.build_health(NOW, env)["run"]
    assert run["run_url"] == "https://github.com/me/convergealpha/actions/runs/42"


def test_health_requires_aware_time() -> None:
    with pytest.raises(ValueError):
        H.build_health(datetime(2026, 10, 12), {})


def test_cli_health_writes_file(tmp_path: Path) -> None:
    assert main(["health", "--data", str(tmp_path / "data"), "--out", str(tmp_path / "out")]) == 0
    health = json.loads((tmp_path / "out" / "health.json").read_text(encoding="utf-8"))
    assert health["schema_version"] == H.SCHEMA_VERSION


def test_decision_cutoff_is_1615_new_york() -> None:
    cutoff = decision_cutoff(date(2026, 10, 12))
    assert cutoff.tzinfo == NEW_YORK
    assert cutoff.astimezone(UTC) == datetime(2026, 10, 12, 20, 15, tzinfo=UTC)
