import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from convergealpha.cli import main
from convergealpha.config import NEW_YORK, decision_cutoff
from convergealpha.export.health import SOURCES, build_health

NOW = datetime(2026, 10, 12, 22, 31, 5, tzinfo=UTC)


def test_health_without_env_is_honest() -> None:
    health = build_health(NOW, {})
    assert health["generated_at"] == "2026-10-12T22:31:05Z"
    assert health["research_mode"] is True
    assert health["validated"] == []
    assert health["model_version"] is None
    assert health["kill_switch"]["implemented"] is False
    assert health["run"]["workflow"] == "local"
    assert health["run"]["run_url"] is None
    assert len(health["sources"]) == len(SOURCES)
    assert all(s["status"] == "not_implemented" for s in health["sources"])
    assert all(s["last_success"] is None for s in health["sources"])
    assert not any(s["present"] for s in health["secrets"])


def test_health_reports_presence_but_never_secret_values() -> None:
    env = {
        "FINNHUB_API_KEY": "super-secret-finnhub",
        "SEC_USER_AGENT": "ConvergeAlpha someone@example.com",
        "FRED_API_KEY": "   ",
    }
    health = build_health(NOW, env)
    present = {s["name"]: s["present"] for s in health["secrets"]}
    assert present["FINNHUB_API_KEY"] is True
    assert present["SEC_USER_AGENT"] is True
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
    run = build_health(NOW, env)["run"]
    assert run["run_url"] == "https://github.com/me/convergealpha/actions/runs/42"
    assert run["workflow"] == "daily"
    assert run["git_sha"] == "abc123"


def test_health_requires_aware_time() -> None:
    with pytest.raises(ValueError):
        build_health(datetime(2026, 10, 12), {})


def test_cli_daily_writes_health(tmp_path: Path) -> None:
    assert main(["daily", "--out", str(tmp_path / "out")]) == 0
    health = json.loads((tmp_path / "out" / "health.json").read_text(encoding="utf-8"))
    assert health["status"] == "ok"


def test_decision_cutoff_is_1615_new_york() -> None:
    cutoff = decision_cutoff(date(2026, 10, 12))
    assert cutoff.tzinfo == NEW_YORK
    # 16:15 EDT = 20:15 UTC in October
    assert cutoff.astimezone(UTC) == datetime(2026, 10, 12, 20, 15, tzinfo=UTC)
