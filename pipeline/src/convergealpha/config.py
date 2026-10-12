"""Runtime configuration: secrets, paths, decision time and time zones.

Secrets come from environment variables (GitHub Actions secrets in production, `.env` locally).
Only their *presence* is ever exported; values never leave this process.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")

# A value may drive a decision for day D only if its `as_of` is before D at 16:15 New York time.
DECISION_TIME = time(16, 15)

# First date of stored price history (needs 3+ years of warm-up before the 2016+ backtests).
HISTORY_START = date(2010, 1, 1)

# Benchmarks downloaded with the universe but never shown as stocks.
SPY = "SPY"  # S&P 500 total-return proxy (dividends reinvested)
GSPC = "^GSPC"  # S&P 500 price index, used for the 200-day regime rule
VIX = "^VIX"
BENCHMARKS: tuple[str, ...] = (SPY, GSPC, VIX)

# Trade eligibility (spec R11).
MIN_PRICE = 5.0
MIN_ADV_DOLLARS = 10_000_000.0

# Horizons in trading days: 1 week, 1 month, 3 months, 6 months.
HORIZONS: tuple[int, ...] = (5, 21, 63, 126)
HORIZON_NAMES: dict[int, str] = {5: "1w", 21: "1m", 63: "3m", 126: "6m"}


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


def load_dotenv(path: Path) -> None:
    """Load KEY=VALUE lines from a local .env into os.environ (existing values win)."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def secret(name: str, env: Mapping[str, str] | None = None) -> str | None:
    """Return a secret's value, or None when it is missing or blank."""
    value = (env if env is not None else os.environ).get(name, "").strip()
    return value or None


def secret_values(env: Mapping[str, str] | None = None) -> list[str]:
    """All configured secret values, for redacting them from logs and error messages."""
    values = [secret(s.name, env) for s in SECRETS]
    return [v for v in values if v and len(v) >= 6]


def decision_cutoff(day: date) -> datetime:
    """The latest moment (exclusive) at which data may be published to count for `day`."""
    return datetime.combine(day, DECISION_TIME, tzinfo=NEW_YORK)


def holdings_from_env(env: Mapping[str, str] | None = None) -> list[str]:
    """Tickers listed in the optional HOLDINGS variable ("AAPL, MSFT"), refreshed daily."""
    raw = (env if env is not None else os.environ).get("HOLDINGS", "")
    return sorted({t.strip().upper() for t in raw.replace(";", ",").split(",") if t.strip()})


@dataclass(frozen=True)
class Paths:
    """Where the pipeline reads and writes.

    data: clone of the private data repo (raw data, snapshots, ledger).
    site: JSON for the website (copied into web/public/data at build time).
    cache: scratch space that can always be rebuilt.
    """

    data: Path
    site: Path
    cache: Path

    @classmethod
    def from_args(
        cls, data: str | Path, site: str | Path, cache: str | Path | None = None
    ) -> Paths:
        data_path = Path(data)
        return cls(data_path, Path(site), Path(cache) if cache else data_path.parent / ".cache")

    def ensure(self) -> None:
        for p in (self.data, self.site, self.cache):
            p.mkdir(parents=True, exist_ok=True)
