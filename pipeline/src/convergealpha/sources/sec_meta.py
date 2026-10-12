"""SEC company data: industry (SIC) -> sector, recent filings with 8-K item numbers, and the
daily filing index (who filed what today). All official EDGAR endpoints, <= 8 requests/second.

Stored in the data repo:
  reference/sec_companies.parquet         one row per CIK (rewritten; small)
  filings/<YYYY>/<YYYYMMDD>.parquet        filings first seen that day (append-only)
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from convergealpha.util import http
from convergealpha.util.io import write_parquet
from convergealpha.util.log import get

log = get(__name__)

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
DAILY_INDEX_URL = "https://www.sec.gov/Archives/edgar/daily-index/{y}/QTR{q}/form.{ymd}.idx"

# --------------------------------------------------------------------------- SIC -> sector

# (low, high, sector) — first match wins, so specific ranges come before broad ones.
_SIC_SECTORS: list[tuple[int, int, str]] = [
    (1311, 1389, "Energy"), (2900, 2999, "Energy"), (4610, 4619, "Energy"), (5170, 5172, "Energy"),
    (2830, 2836, "Health Care"), (3841, 3851, "Health Care"), (5120, 5122, "Health Care"), (8000, 8099, "Health Care"),
    (8730, 8731, "Health Care"),
    (3570, 3579, "Information Technology"), (3660, 3679, "Information Technology"), (3820, 3829, "Information Technology"),
    (3861, 3861, "Information Technology"), (7370, 7379, "Information Technology"), (3577, 3577, "Information Technology"),
    (4800, 4899, "Communication Services"), (2700, 2799, "Communication Services"), (7810, 7829, "Communication Services"),
    (4900, 4949, "Utilities"), (4950, 4991, "Utilities"),
    (6500, 6553, "Real Estate"), (6798, 6798, "Real Estate"),
    (6000, 6799, "Financials"),
    (2000, 2199, "Consumer Staples"), (2840, 2844, "Consumer Staples"), (5140, 5149, "Consumer Staples"),
    (5400, 5499, "Consumer Staples"), (5912, 5912, "Consumer Staples"), (100, 999, "Consumer Staples"),
    (2200, 2399, "Consumer Discretionary"), (2500, 2599, "Consumer Discretionary"), (3100, 3199, "Consumer Discretionary"),
    (3630, 3651, "Consumer Discretionary"), (3711, 3716, "Consumer Discretionary"), (3751, 3751, "Consumer Discretionary"),
    (3900, 3999, "Consumer Discretionary"), (5200, 5999, "Consumer Discretionary"), (7000, 7299, "Consumer Discretionary"),
    (7500, 7549, "Consumer Discretionary"), (7900, 7999, "Consumer Discretionary"), (8200, 8299, "Consumer Discretionary"),
    (1000, 1499, "Materials"), (2400, 2499, "Materials"), (2600, 2699, "Materials"), (2800, 2899, "Materials"),
    (3000, 3099, "Materials"), (3200, 3399, "Materials"),
    (1500, 1799, "Industrials"), (3400, 3569, "Industrials"), (3580, 3629, "Industrials"), (3690, 3799, "Industrials"),
    (3800, 3899, "Industrials"), (4000, 4799, "Industrials"), (5000, 5199, "Industrials"), (7300, 7399, "Industrials"),
    (8700, 8799, "Industrials"), (8100, 8699, "Industrials"), (8800, 8999, "Industrials"),
]  # fmt: skip

SECTORS = (
    "Communication Services", "Consumer Discretionary", "Consumer Staples", "Energy", "Financials",
    "Health Care", "Industrials", "Information Technology", "Materials", "Real Estate", "Utilities",
)  # fmt: skip


def sic_sector(sic: int | str | None) -> str | None:
    try:
        code = int(str(sic))
    except (TypeError, ValueError):
        return None
    if code == 6770:  # blank checks
        return None
    for lo, hi, sector in _SIC_SECTORS:
        if lo <= code <= hi:
            return sector
    return None


def industry_group(sic: int | str | None) -> str | None:
    """3-digit SIC group, used for industry momentum."""
    try:
        return str(int(str(sic)))[:3].zfill(3)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- submissions


def _parse_submissions(
    cik: int, j: dict[str, Any], fetched: datetime
) -> tuple[dict[str, Any], pd.DataFrame]:
    company = {
        "cik": cik,
        "sec_name": j.get("name"),
        "sic": int(j["sic"]) if str(j.get("sic") or "").isdigit() else None,
        "sic_description": j.get("sicDescription") or None,
        "fiscal_year_end": j.get("fiscalYearEnd") or None,
        "state_of_incorporation": j.get("stateOfIncorporation") or None,
        "category": j.get("category") or None,
        "fetched_at": pd.Timestamp(fetched),
    }
    company["sector"] = sic_sector(company["sic"])
    company["industry_group"] = industry_group(company["sic"])
    rec = (j.get("filings") or {}).get("recent") or {}
    n = len(rec.get("form", []))
    filings = pd.DataFrame(
        {
            "cik": [cik] * n,
            "accession": rec.get("accessionNumber", [None] * n),
            "form": rec.get("form", [None] * n),
            "filing_date": rec.get("filingDate", [None] * n),
            "acceptance": rec.get("acceptanceDateTime", [None] * n),
            "report_date": rec.get("reportDate", [None] * n),
            "items": rec.get("items", [""] * n),
            "primary_doc": rec.get("primaryDocument", [None] * n),
            "description": rec.get("primaryDocDescription", [None] * n),
        }
    )
    return company, filings


def fetch_submissions(
    session: Any, ciks: Sequence[int], workers: int = 6
) -> tuple[pd.DataFrame, pd.DataFrame, list[int]]:
    """Fetch company records + recent filings for many CIKs (rate-limited)."""
    companies: list[dict[str, Any]] = []
    filings: list[pd.DataFrame] = []
    failed: list[int] = []

    def one(cik: int) -> tuple[int, dict[str, Any] | None, pd.DataFrame | None]:
        try:
            r = http.get(session, SUBMISSIONS_URL.format(cik=int(cik)), ok_404=True, timeout=30)
            if r is None:
                return cik, None, None
            c, f = _parse_submissions(int(cik), r.json(), datetime.now())
            return cik, c, f
        except Exception as e:
            log.debug("submissions %s failed: %s", cik, e)
            return cik, None, None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, (cik, c, f) in enumerate(pool.map(one, ciks)):
            if c is None:
                failed.append(int(cik))
            else:
                companies.append(c)
                if f is not None and not f.empty:
                    filings.append(f)
            if i and i % 500 == 0:
                log.info("submissions: %d/%d", i, len(ciks))
    comp = pd.DataFrame(companies)
    fil = pd.concat(filings, ignore_index=True) if filings else pd.DataFrame()
    return comp, fil, failed


def companies_dir(data_dir: Path) -> Path:
    return data_dir / "reference" / "sec_companies"


def load_companies(data_dir: Path) -> pd.DataFrame:
    """Latest record per CIK from the append-only daily files."""
    files = sorted(companies_dir(data_dir).glob("*.parquet"))
    if not files:
        return pd.DataFrame(
            columns=["cik", "sector", "sic", "sic_description", "industry_group", "fetched_at"]
        )
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    return df.sort_values("fetched_at").drop_duplicates("cik", keep="last").reset_index(drop=True)


def save_companies(data_dir: Path, new: pd.DataFrame, day: date) -> None:
    if new.empty:
        return
    path = companies_dir(data_dir) / f"{day:%Y%m%d}.parquet"
    if path.exists():
        new = pd.concat([pd.read_parquet(path), new], ignore_index=True).drop_duplicates(
            "cik", keep="last"
        )
    write_parquet(new, path)


RELEVANT_FORMS = (
    # 424B2/424B3 are left out: banks file thousands of structured-note supplements.
    "8-K", "8-K/A", "10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "40-F", "6-K", "424B1",
    "424B4", "424B5", "424B7", "S-1", "S-1/A", "S-3", "F-1", "F-3", "SC TO-T", "SC 14D9", "DEFM14A",
    "PREM14A", "DEFM14C", "PREM14C", "425", "NT 10-K", "NT 10-Q", "NT 20-F", "15-12B", "25-NSE",
)  # fmt: skip


# --------------------------------------------------------------------------- filings store


def filings_dir(data_dir: Path) -> Path:
    return data_dir / "filings"


def known_accessions(data_dir: Path) -> set[str]:
    files = sorted(filings_dir(data_dir).glob("*/*.parquet"))
    out: set[str] = set()
    for f in files:
        out.update(pd.read_parquet(f, columns=["accession"])["accession"].astype(str))
    return out


def append_filings(
    data_dir: Path, filings: pd.DataFrame, day: date, since: date | None = None
) -> int:
    """Store filings not seen before (optionally only those filed on/after `since`)."""
    if filings.empty:
        return 0
    f = filings[filings["form"].isin(RELEVANT_FORMS)].copy()
    if since is not None:
        f = f[pd.to_datetime(f["filing_date"]).dt.date >= since]
    seen = known_accessions(data_dir)
    f = f[~f["accession"].astype(str).isin(seen)].drop_duplicates("accession")
    if f.empty:
        return 0
    path = filings_dir(data_dir) / f"{day:%Y}" / f"{day:%Y%m%d}.parquet"
    if path.exists():
        f = pd.concat([pd.read_parquet(path), f], ignore_index=True).drop_duplicates("accession")
    write_parquet(f, path)
    return len(f)


def load_filings(data_dir: Path, since: date | None = None) -> pd.DataFrame:
    files = sorted(filings_dir(data_dir).glob("*/*.parquet"))
    if not files:
        return pd.DataFrame(
            columns=["cik", "accession", "form", "filing_date", "acceptance", "items"]
        )
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True).drop_duplicates(
        "accession"
    )
    df["filing_date"] = pd.to_datetime(df["filing_date"])
    if since is not None:
        df = df[df["filing_date"] >= pd.Timestamp(since)]
    return df


# --------------------------------------------------------------------------- daily index


_IDX_LINE = re.compile(
    r"^(?P<form>\S+(?: \S+)*?)\s{2,}(?P<name>.+?)\s{2,}(?P<cik>\d+)\s+(?P<date>\d{8})\s+(?P<file>edgar/\S+)"
)


def fetch_daily_index(session: Any, day: date) -> pd.DataFrame:
    """All filings disseminated on `day` (form type, company, CIK, file path). Empty on holidays."""
    q = (day.month - 1) // 3 + 1
    url = DAILY_INDEX_URL.format(y=day.year, q=q, ymd=day.strftime("%Y%m%d"))
    empty = pd.DataFrame(columns=["form", "name", "cik", "date", "file", "accession"])
    try:
        r = http.get(session, url, ok_404=True, timeout=60)
    except http.HttpError as e:
        # EDGAR answers 403 (not 404) for an index that is not published yet.
        if "HTTP 403" in str(e):
            return empty
        raise
    if r is None:
        return empty
    rows = []
    started = False
    for line in r.text.splitlines():
        if line.startswith("-----"):
            started = True
            continue
        if not started or not line.strip():
            continue
        m = _IDX_LINE.match(line)
        if m:
            d = m.groupdict()
            acc = d["file"].rsplit("/", 1)[-1].removesuffix(".txt")
            rows.append(
                {
                    "form": d["form"].strip(),
                    "name": d["name"].strip(),
                    "cik": int(d["cik"]),
                    "date": d["date"],
                    "file": d["file"],
                    "accession": acc,
                }
            )
    return pd.DataFrame(rows)


def recent_index(session: Any, end: date, days: int = 4) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    d = end
    for _ in range(days * 2):
        if len(frames) >= days:
            break
        if d.weekday() < 5:
            df = fetch_daily_index(session, d)
            if not df.empty:
                frames.append(df)
        d -= timedelta(days=1)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def ciks_with_forms(index: pd.DataFrame, forms: Iterable[str]) -> set[int]:
    if index.empty:
        return set()
    wanted = set(forms)
    return set(index.loc[index["form"].isin(wanted), "cik"].astype(int))
