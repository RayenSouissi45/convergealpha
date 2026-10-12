"""Runtime configuration: secrets, decision time and time zones.

Secrets come from environment variables (GitHub Actions secrets in production, `.env` locally).
Only their *presence* is ever exported; values never leave this process.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")

# A value may drive a decision for day D only if its `as_of` is before D at 16:15 New York time.
DECISION_TIME = time(16, 15)


@dataclass(frozen=True)
class SecretSpec:
    name: str
    purpose: str
    required: bool = False
    # Phase from which the pipeline starts using it; None = optional upgrade.
    used_from_phase: int | None = None


SECRETS: tuple[SecretSpec, ...] = (
    SecretSpec("SEC_USER_AGENT", "SEC EDGAR contact header", required=True, used_from_phase=1),
    SecretSpec("FINNHUB_API_KEY", "Analyst trends, earnings, news", used_from_phase=2),
    SecretSpec("FRED_API_KEY", "VIX, credit spread, yield curve", used_from_phase=2),
    SecretSpec("POLYGON_API_KEY", "Optional grouped daily prices"),
    SecretSpec("ALPHAVANTAGE_API_KEY", "Optional backup data"),
    SecretSpec("FMP_API_KEY", "Optional backup data"),
    SecretSpec("DANELFIN_API_KEY", "Optional third-party AI score"),
    SecretSpec("ANTHROPIC_API_KEY", "Optional AI news event extraction"),
    SecretSpec("TELEGRAM_BOT_TOKEN", "Optional phone alerts"),
    SecretSpec("TELEGRAM_CHAT_ID", "Optional phone alerts"),
)


def secret(name: str, env: Mapping[str, str] | None = None) -> str | None:
    """Return a secret's value, or None when it is missing or blank."""
    value = (env if env is not None else os.environ).get(name, "").strip()
    return value or None


def decision_cutoff(day: date) -> datetime:
    """The latest moment (exclusive) at which data may be published to count for `day`."""
    return datetime.combine(day, DECISION_TIME, tzinfo=NEW_YORK)
