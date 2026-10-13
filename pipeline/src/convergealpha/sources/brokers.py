"""finanzen.net zero: which of our US stocks can be bought there.

finanzen.net zero routes every order to gettex, the market-maker segments of Börse München
(MIC codes MUND and MUNC), and offers the shares and depositary receipts quoted there (gettex
lists ~8,600 of them; the broker advertises "more than 8,500 shares"). The list therefore comes
from the trading venue's own reference data as published in ESMA's FIRDS register: the EU's
official list of every instrument each EU venue trades, free to reuse with the source
acknowledged. ISINs are mapped to US tickers with the OpenFIGI API (public-domain identifiers).
No web page is scraped.

The check is for the exact US-listed security: a foreign company's US ADR is a different
security from its home-market share, so the ADR counts only if gettex quotes the ADR itself.

Stored in the private data repo:
  brokers/finanzen_zero.parquet  one row per gettex share/ADR: isin, name, cfi, mic, ticker
  brokers/finanzen_zero.json     list date, source file names and counts
  brokers/isin_map.parquet       ISIN -> US ticker cache (OpenFIGI), with the mapping date
A hand-made list `manual/brokers/finanzen_zero.csv` (column `isin` or `ticker`, e.g. exported
from the broker's app) replaces the FIRDS list when present.
"""

from __future__ import annotations

import hashlib
import time
import zipfile
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import IO, Any
from xml.etree.ElementTree import iterparse

import numpy as np
import pandas as pd
import requests

from convergealpha.config import secret
from convergealpha.util import http
from convergealpha.util.io import read_json, write_json, write_parquet
from convergealpha.util.log import get

log = get(__name__)

FIRDS_FILES = "https://registers.esma.europa.eu/solr/esma_registers_firds_files/select"
OPENFIGI = "https://api.openfigi.com/v3/mapping"
GETTEX_MICS = frozenset({"MUND", "MUNC"})
# CFI categories kept: ES = shares, ED = depositary receipts (ADRs), EL = limited-partnership
# units, and CB = real estate investment trusts, which ISO 10962 files as collective investment
# vehicles (so US REITs such as AMT, O or PLD are in FIRDS's "C" files, not the equity files).
# EY ("other equity") on gettex is mostly certificates; CE/CI are ETFs and funds.
SHARE_CFI = ("ES", "ED", "EL", "CB")
FIRDS_PREFIXES = ("FULINS_E_", "FULINS_C_")
SOURCE = "ESMA FIRDS reference data (gettex, MIC MUND/MUNC)"
# A list older than this is not trusted: every stock becomes "unknown".
MAX_LIST_AGE_DAYS = 35
# Stocks listed in the US more recently than this may be missing from the venue's weekly file.
NEW_LISTING_DAYS = 30
# OpenFIGI cache entries are re-checked after this many days (tickers change on renames).
REMAP_AFTER_DAYS = 28


# --------------------------------------------------------------------------- ISIN helpers


def isin_check_digit(body: str) -> int:
    """Check digit for the first 11 characters of an ISIN (letters A=10 ... Z=35, then Luhn)."""
    digits = "".join(str(int(c, 36)) for c in body.upper())
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            d = d - 9 if d > 9 else d
        total += d
    return (10 - total % 10) % 10


def isin_valid(isin: str) -> bool:
    s = str(isin).strip().upper()
    if len(s) != 12 or not s[:2].isalpha() or not s[2:11].isalnum() or not s[11].isdigit():
        return False
    return isin_check_digit(s[:11]) == int(s[11])


def us_isin(cusip: str) -> str:
    """A US ISIN is "US" + the 9-character CUSIP + a check digit."""
    body = "US" + cusip.strip().upper()
    return body + str(isin_check_digit(body))


def normalize_ticker(t: str) -> str:
    """OpenFIGI writes share classes as BRK/B; our universe writes BRK-B."""
    return str(t).strip().upper().replace("/", "-").replace(".", "-").replace(" ", "-")


# --------------------------------------------------------------------------- FIRDS


def latest_full_files(session: requests.Session, today: date) -> list[dict[str, str]]:
    """The newest weekly FIRDS full files for equities and funds (FULINS_E/C_<date>_NNofMM.zip).

    Both kinds must come from the same publication date."""
    since = (today - timedelta(days=21)).isoformat()
    r = http.get(
        session,
        FIRDS_FILES,
        params={
            "q": "*",
            "fq": f"publication_date:[{since}T00:00:00Z TO {today.isoformat()}T23:59:59Z]",
            "wt": "json",
            "rows": 500,
        },
        timeout=60,
    )
    docs = (r.json() if r is not None else {}).get("response", {}).get("docs", [])
    full = [d for d in docs if str(d.get("file_name", "")).startswith(FIRDS_PREFIXES)]
    dates = sorted(
        {d["publication_date"] for d in full}
        & {d["publication_date"] for d in full if d["file_name"].startswith("FULINS_C_")}
        & {d["publication_date"] for d in full if d["file_name"].startswith("FULINS_E_")}
    )
    if not dates:
        return []
    files = [d for d in full if d["publication_date"] == dates[-1]]
    return sorted(
        (
            {"name": d["file_name"], "url": d["download_link"], "md5": d.get("checksum", "")}
            for d in files
        ),
        key=lambda d: d["name"],
    )


def download(session: requests.Session, f: Mapping[str, str], cache: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f["name"]
    if path.is_file() and (not f.get("md5") or _md5(path) == f["md5"]):
        return path
    r = http.get(session, f["url"], timeout=600, stream=True)
    if r is None:
        raise http.HttpError(f"no response for {f['name']}")
    tmp = path.with_suffix(".part")
    with open(tmp, "wb") as out:
        for chunk in r.iter_content(1 << 20):
            out.write(chunk)
    if f.get("md5") and _md5(tmp) != f["md5"]:
        tmp.unlink(missing_ok=True)
        raise http.HttpError(f"checksum mismatch for {f['name']}")
    tmp.replace(path)
    return path


def _md5(path: Path) -> str:
    h = hashlib.md5(usedforsecurity=False)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_firds(stream: IO[bytes], mics: frozenset[str] = GETTEX_MICS) -> pd.DataFrame:
    """Shares and depositary receipts that `mics` trade, streamed from a FIRDS XML file.

    Each <RefData> record is one instrument on one venue: ISIN, name, CFI code, the venue's MIC,
    the first trading day and (when it stopped) the termination date.
    """
    rows: list[dict[str, Any]] = []
    for _, el in iterparse(stream, events=("end",)):
        if not el.tag.endswith("}RefData"):
            continue
        ns = el.tag[: -len("RefData")]
        g = el.find(f"{ns}FinInstrmGnlAttrbts")
        v = el.find(f"{ns}TradgVnRltdAttrbts")
        if g is not None and v is not None:
            mic = v.findtext(f"{ns}Id")
            cfi = g.findtext(f"{ns}ClssfctnTp") or ""
            if mic in mics and cfi.startswith(SHARE_CFI):
                rows.append(
                    {
                        "isin": g.findtext(f"{ns}Id"),
                        "name": g.findtext(f"{ns}FullNm"),
                        "cfi": cfi,
                        "currency": g.findtext(f"{ns}NtnlCcy"),
                        "mic": mic,
                        "first_trade": (v.findtext(f"{ns}FrstTradDt") or "")[:10] or None,
                        "terminated": (v.findtext(f"{ns}TermntnDt") or "")[:10] or None,
                    }
                )
        el.clear()
    return pd.DataFrame(
        rows, columns=["isin", "name", "cfi", "currency", "mic", "first_trade", "terminated"]
    )


def read_firds_zip(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as z:
        frames = []
        for name in z.namelist():
            if name.lower().endswith(".xml"):
                with z.open(name) as f:
                    frames.append(parse_firds(f))
    return pd.concat(frames, ignore_index=True) if frames else parse_firds_empty()


def parse_firds_empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["isin", "name", "cfi", "currency", "mic", "first_trade", "terminated"]
    )


def active(df: pd.DataFrame, today: date) -> pd.DataFrame:
    """Instruments still traded today, one row per ISIN."""
    if df.empty:
        return df
    term = pd.to_datetime(df["terminated"], errors="coerce")
    live = df[term.isna() | (term.dt.date > today)]
    return live.sort_values(["isin", "mic"]).drop_duplicates("isin", keep="last")


# --------------------------------------------------------------------------- OpenFIGI


def openfigi_map(
    isins: Iterable[str],
    api_key: str | None = None,
    session: requests.Session | None = None,
    sleep: Any = time.sleep,
) -> pd.DataFrame:
    """US ticker of each ISIN (exchange code "US" = any US exchange), or None if not US-listed.

    Without an API key OpenFIGI allows 25 requests a minute with 10 ISINs each; with a free key,
    25 requests every 6 seconds with 100 ISINs each.
    """
    isins = list(dict.fromkeys(isins))
    per_req, gap = (100, 6 / 25) if api_key else (10, 60 / 25)
    s = session or http.make_session(
        {"Content-Type": "application/json", **({"X-OPENFIGI-APIKEY": api_key} if api_key else {})}
    )
    out: list[dict[str, Any]] = []
    for i in range(0, len(isins), per_req):
        batch = isins[i : i + per_req]
        jobs = [{"idType": "ID_ISIN", "idValue": x, "exchCode": "US"} for x in batch]
        res = _post_with_retry(s, jobs, sleep)
        for isin, item in zip(batch, res, strict=True):
            hit = _pick(item.get("data") or [])
            out.append(
                {
                    "isin": isin,
                    "ticker": normalize_ticker(hit["ticker"]) if hit else None,
                    "figi": hit.get("compositeFIGI") if hit else None,
                    "security_type": hit.get("securityType") if hit else None,
                }
            )
        if (i // per_req) % 20 == 0:
            log.info("openfigi: %d of %d ISINs mapped", min(i + per_req, len(isins)), len(isins))
        if i + per_req < len(isins):
            sleep(gap)
    return pd.DataFrame(out, columns=["isin", "ticker", "figi", "security_type"])


def _post_with_retry(s: requests.Session, jobs: list[dict[str, str]], sleep: Any) -> list[Any]:
    for attempt in range(6):
        try:
            r = s.post(OPENFIGI, json=jobs, timeout=60)
        except requests.RequestException as e:
            if attempt == 5:
                raise http.HttpError(f"OpenFIGI: {type(e).__name__}") from None
            sleep(10 * (attempt + 1))
            continue
        if r.status_code == 429:
            sleep(float(r.headers.get("ratelimit-reset") or 60) + 1)
            continue
        if r.status_code >= 400:
            raise http.HttpError(f"OpenFIGI HTTP {r.status_code}")
        res = r.json()
        if not isinstance(res, list) or len(res) != len(jobs):
            raise http.HttpError("OpenFIGI: unexpected response shape")
        return res
    raise http.HttpError("OpenFIGI: still rate-limited after 6 tries")


def _pick(data: list[dict[str, Any]]) -> dict[str, Any] | None:
    eq = [d for d in data if d.get("marketSector") == "Equity" and d.get("ticker")]
    return eq[0] if eq else None


def update_map(
    cache_path: Path,
    isins: Iterable[str],
    today: date,
    api_key: str | None,
    max_remap: int,
    mapper: Any = openfigi_map,
) -> pd.DataFrame:
    """Map new ISINs and re-check the oldest stale entries (at most `max_remap` per run)."""
    want = list(dict.fromkeys(isins))
    cached = (
        pd.read_parquet(cache_path)
        if cache_path.is_file()
        else pd.DataFrame(columns=["isin", "ticker", "figi", "security_type", "mapped_at"])
    )
    have = cached.set_index("isin") if not cached.empty else cached
    new = [x for x in want if x not in have.index]
    stale: list[str] = []
    if not cached.empty:
        age = (pd.Timestamp(today) - pd.to_datetime(cached["mapped_at"])).dt.days
        old = cached[(age > REMAP_AFTER_DAYS) & cached["isin"].isin(set(want))]
        stale = old.sort_values("mapped_at")["isin"].head(max_remap).tolist()
    todo = new + stale
    if todo:
        log.info("openfigi: %d new and %d stale ISINs to map", len(new), len(stale))
        got = mapper(todo, api_key)
        got["mapped_at"] = today.isoformat()
        keep = cached[~cached["isin"].isin(set(got["isin"]))] if not cached.empty else cached
        cached = pd.concat([keep, got], ignore_index=True) if not keep.empty else got
        write_parquet(cached, cache_path)
    return cached


# --------------------------------------------------------------------------- refresh (weekly)


def refresh(data_dir: Path, cache_dir: Path, today: date, env: Mapping[str, str]) -> dict[str, Any]:
    """Download the newest FIRDS equity files, keep gettex shares/ADRs, map them to tickers."""
    s = http.make_session({"User-Agent": "ConvergeAlpha personal research"})
    files = latest_full_files(s, today)
    if not files:
        raise http.HttpError("no FIRDS equity + fund full files published in the last 3 weeks")
    frames = [read_firds_zip(download(s, f, cache_dir / "firds")) for f in files]
    venue = active(pd.concat(frames, ignore_index=True), today)
    key = secret("OPENFIGI_API_KEY", env)
    out_dir = data_dir / "brokers"
    mapping = update_map(
        out_dir / "isin_map.parquet",
        venue["isin"],
        today,
        key,
        max_remap=100_000 if key else 2_000,
    )
    m = mapping.drop_duplicates("isin", keep="last").set_index("isin")
    venue = venue.assign(ticker=venue["isin"].map(m["ticker"]))
    list_date = files[0]["name"].split("_")[2]
    list_date = f"{list_date[:4]}-{list_date[4:6]}-{list_date[6:8]}"
    write_parquet(venue, out_dir / "finanzen_zero.parquet")
    meta = {
        "source": SOURCE,
        "list_date": list_date,
        "files": [f["name"] for f in files],
        "downloaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "instruments": len(venue),
        "with_us_ticker": int(venue["ticker"].notna().sum()),
    }
    write_json(meta, out_dir / "finanzen_zero.json", pretty=True)
    log.info(
        "finanzen.net zero list %s: %d gettex shares/ADRs, %d with a US ticker",
        list_date,
        meta["instruments"],
        meta["with_us_ticker"],
    )
    return meta


# --------------------------------------------------------------------------- daily use


def load_list(data_dir: Path) -> tuple[set[str], dict[str, Any]] | None:
    """(tickers buyable at finanzen.net zero, metadata), or None when no list exists.

    The owner's manual file wins over the FIRDS list.
    """
    manual = data_dir / "manual" / "brokers" / "finanzen_zero.csv"
    if manual.is_file():
        df = pd.read_csv(manual, dtype=str)
        cols = {c.lower().strip(): c for c in df.columns}
        tickers: set[str] = set()
        if "ticker" in cols:
            tickers |= {normalize_ticker(t) for t in df[cols["ticker"]].dropna()}
        if "isin" in cols:
            isins = [x.strip().upper() for x in df[cols["isin"]].dropna() if isin_valid(x)]
            cache = data_dir / "brokers" / "isin_map.parquet"
            if cache.is_file():
                m = pd.read_parquet(cache).dropna(subset=["ticker"]).set_index("isin")["ticker"]
                tickers |= {m[x] for x in isins if x in m.index}
        mtime = datetime.fromtimestamp(manual.stat().st_mtime, UTC).date().isoformat()
        return tickers, {
            "source": "Your manual list (manual/brokers/finanzen_zero.csv)",
            "list_date": mtime,
            "instruments": len(df),
            "with_us_ticker": len(tickers),
        }
    path = data_dir / "brokers" / "finanzen_zero.parquet"
    if not path.is_file():
        return None
    df = pd.read_parquet(path)
    meta = read_json(data_dir / "brokers" / "finanzen_zero.json", {})
    return {str(t) for t in df["ticker"].dropna()}, dict(meta)


def zero_flags(
    t: pd.DataFrame, listed: tuple[set[str], dict[str, Any]] | None, as_of: pd.Timestamp
) -> tuple[pd.Series, dict[str, Any] | None]:
    """True / False / None (unknown) per stock, plus a summary for Health.

    Unknown, never "not buyable": when there is no list, when the list is too old, or when the
    stock started trading in the US so recently that the venue's weekly file may not have it.
    """
    unknown = pd.Series(None, index=t.index, dtype=object)
    if listed is None:
        return unknown, None
    tickers, meta = listed
    list_date = pd.Timestamp(meta.get("list_date") or "1970-01-01")
    age = (as_of - list_date).days
    summary = {**meta, "age_days": int(age)}
    if age > MAX_LIST_AGE_DAYS:
        return unknown, {**summary, "stale": True, "matched": 0}
    flags = pd.Series(
        np.where(t.index.isin(list(tickers)), True, False), index=t.index, dtype=object
    )
    days = pd.to_numeric(t["history_days"], errors="coerce") if "history_days" in t else None
    if days is not None:
        flags[(days < NEW_LISTING_DAYS) & ~t.index.isin(list(tickers))] = None
    elig = t["eligible"].eq(True) if "eligible" in t else pd.Series(True, index=t.index)
    summary.update(
        {
            "stale": False,
            "matched": int(flags.eq(True).sum()),
            "matched_eligible": int((flags.eq(True) & elig).sum()),
            "unknown": int(flags.isna().sum()),
            "stocks": len(t),
            "eligible": int(elig.sum()),
        }
    )
    return flags, summary


def describe(summary: dict[str, Any]) -> str:
    return (
        f"List dated {summary.get('list_date')} ({summary.get('source')}): "
        f"{summary.get('matched', 0):,} of {summary.get('stocks', 0):,} stocks buyable, "
        f"{summary.get('matched_eligible', 0):,} of {summary.get('eligible', 0):,} eligible ones"
    )
