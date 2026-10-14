"""Long market history for the savings-plan and goal planner: about 100 years of monthly US stock
market returns, the 1-month Treasury bill rate and inflation.

- Kenneth R. French Data Library (Dartmouth): Fama-French research factors, monthly, from July
  1926. Market return = Mkt-RF + RF (value-weighted US stocks, dividends included); RF = 1-month
  Treasury bill. Free to use with the source acknowledged.
- FRED CPIAUCNS: US consumer prices, not seasonally adjusted, monthly from 1913.

Stored in the private data repo (macro/history_monthly.parquet) and refreshed weekly; the site
gets history.json (about 30 KB).
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from convergealpha.util import http
from convergealpha.util.io import write_parquet
from convergealpha.util.log import get

log = get(__name__)

FRENCH_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_CSV.zip"
)
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
CPI_SERIES = "CPIAUCNS"
REFRESH_DAYS = 7
SOURCE = (
    "Kenneth R. French Data Library (Dartmouth): US stock market incl. dividends and 1-month "
    "Treasury bills; FRED CPIAUCNS for inflation"
)
_MONTH_ROW = re.compile(r"^\s*(\d{6})\s*,([^,]+),([^,]+),([^,]+),([^,]+)\s*$")


def parse_french(text: str) -> pd.DataFrame:
    """The monthly block of the factors file: month, market (total return), rf. Values are in
    percent in the file; the annual block below it uses 4-digit years and is skipped."""
    rows = []
    for line in text.splitlines():
        m = _MONTH_ROW.match(line)
        if not m:
            continue
        ym, mkt_rf, _smb, _hml, rf = m.groups()
        try:
            a, r = float(mkt_rf), float(rf)
        except ValueError:
            continue
        rows.append({"month": f"{ym[:4]}-{ym[4:]}", "market": (a + r) / 100.0, "rf": r / 100.0})
    df = pd.DataFrame(rows, columns=["month", "market", "rf"])
    return df.drop_duplicates("month").sort_values("month").reset_index(drop=True)


def fetch_french() -> pd.DataFrame:
    r = http.get(http.make_session(), FRENCH_URL, timeout=60)
    assert r is not None
    z = zipfile.ZipFile(io.BytesIO(r.content))
    name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
    return parse_french(z.read(name).decode("latin-1"))


def inflation_from_cpi(cpi: pd.Series) -> pd.Series:
    """Monthly inflation by 'YYYY-MM' from a CPI level series indexed by date."""
    s = cpi.dropna().astype(float).sort_index()
    s.index = pd.to_datetime(s.index).strftime("%Y-%m")
    return (s / s.shift(1) - 1).dropna()


def fetch_cpi(api_key: str) -> pd.Series:
    r = http.get(
        http.make_session(),
        FRED_URL,
        params={
            "series_id": CPI_SERIES,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": "1913-01-01",
        },
        timeout=60,
    )
    assert r is not None
    obs = pd.DataFrame(r.json().get("observations", []))
    if obs.empty:
        return pd.Series(dtype=float)
    obs["value"] = pd.to_numeric(obs["value"], errors="coerce")
    return obs.set_index(pd.to_datetime(obs["date"]))["value"].dropna()


def path(data_dir: Path) -> Path:
    return data_dir / "macro" / "history_monthly.parquet"


def update(
    data_dir: Path, fred_key: str | None, now: datetime | None = None
) -> pd.DataFrame | None:
    """Refresh the stored history when it is older than a week. Returns the table (or None)."""
    p = path(data_dir)
    now = now or datetime.now(UTC)
    if p.is_file() and datetime.fromtimestamp(p.stat().st_mtime, UTC) > now - timedelta(
        days=REFRESH_DAYS
    ):
        return pd.read_parquet(p)
    df = fetch_french()
    if df.empty:
        raise ValueError("French data library: no monthly rows")
    if fred_key:
        infl = inflation_from_cpi(fetch_cpi(fred_key))
        df["inflation"] = df["month"].map(infl)
    elif p.is_file():
        old = pd.read_parquet(p)
        if "inflation" in old:
            df["inflation"] = df["month"].map(old.set_index("month")["inflation"])
    write_parquet(df, p)
    log.info("history: %d months %s..%s", len(df), df["month"].iloc[0], df["month"].iloc[-1])
    return df


def load(data_dir: Path) -> pd.DataFrame | None:
    p = path(data_dir)
    return pd.read_parquet(p) if p.is_file() else None


def export(df: pd.DataFrame) -> dict[str, Any]:
    """history.json for the planner (rounded to 6 decimals: plenty for monthly returns)."""

    def col(c: str) -> list[float | None]:
        if c not in df:
            return [None] * len(df)
        return [None if pd.isna(v) else round(float(v), 6) for v in df[c]]

    return {
        "source": SOURCE,
        "months": list(df["month"]),
        "market": col("market"),
        "rf": col("rf"),
        "inflation": col("inflation"),
    }
