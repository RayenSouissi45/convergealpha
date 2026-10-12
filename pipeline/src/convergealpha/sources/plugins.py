"""Plugin slots for third-party ratings (spec: never scrape).

Danelfin needs its own API key and stays disabled without it. Zacks, TipRanks, Seeking Alpha
Quant and Morningstar forbid scraping, so they are disabled; their ratings can still be added by
hand: put `manual/ratings/<source>.csv` in the private data repo with columns
`ticker,rating,date` (rating 1 = best ... 5 = worst, as on most platforms). Each file becomes one
more opinion source in F1 (with zero model weight until its credibility is measured).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from convergealpha.config import secret


@dataclass(frozen=True)
class Plugin:
    id: str
    name: str
    how: str
    secret: str | None = None


PLUGINS: tuple[Plugin, ...] = (
    Plugin("danelfin", "Danelfin AI score", "API key (DANELFIN_API_KEY)", "DANELFIN_API_KEY"),
    Plugin("zacks", "Zacks Rank", "manual CSV import only (no scraping)"),
    Plugin("tipranks", "TipRanks Smart Score", "manual CSV import only (no scraping)"),
    Plugin("seekingalpha", "Seeking Alpha Quant", "manual CSV import only (no scraping)"),
    Plugin("morningstar", "Morningstar rating", "manual CSV import only (no scraping)"),
)


def status(data_dir: Path, env: Mapping[str, str]) -> list[dict[str, object]]:
    manual = {p.stem for p in (data_dir / "manual" / "ratings").glob("*.csv")}
    out = []
    for p in PLUGINS:
        enabled = (p.secret is not None and secret(p.secret, env) is not None) or p.id in manual
        out.append(
            {
                "id": p.id,
                "name": p.name,
                "enabled": enabled,
                "how": p.how,
                "manual_file": p.id in manual,
            }
        )
    return out


def manual_ratings(
    data_dir: Path, as_of: pd.Timestamp, max_age_days: int = 45
) -> dict[str, pd.Series]:
    """{source: rating score 0-100 by ticker} from manual CSV files (latest rating per ticker)."""
    out: dict[str, pd.Series] = {}
    for f in sorted((data_dir / "manual" / "ratings").glob("*.csv")):
        try:
            df = pd.read_csv(f)
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df = df[(df["date"] <= as_of) & (df["date"] > as_of - pd.Timedelta(days=max_age_days))]
            df = df.sort_values("date").drop_duplicates("ticker", keep="last")
            rating = pd.to_numeric(df["rating"], errors="coerce").clip(1, 5)
            out[f.stem] = pd.Series(
                ((5 - rating) / 4 * 100).to_numpy(), index=df["ticker"].str.upper()
            )
        except Exception:
            continue
    return out
