"""Insider trades from SEC Forms 4 (official): quarterly bulk data sets for history, and Form 4
XML from the daily index for days the data sets do not cover yet.

Only open-market purchases (code P) and sales (code S) of non-derivative securities are kept.
A trade is *routine* if the same insider traded in the same calendar month in each of the three
prior years, and *planned* if made under a 10b5-1 plan; neither counts as opportunistic.
Every row keeps the filing date: that is when the trade became public (point-in-time).

Stored in the data repo:
  insiders/quarters/<YYYY>q<N>.parquet   from the SEC data sets (written once per quarter)
  insiders/daily/<YYYYMMDD>.parquet      from Form 4 XML (days after the last data set)
"""

from __future__ import annotations

import io
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from convergealpha.util import http
from convergealpha.util.io import write_parquet
from convergealpha.util.log import get

log = get(__name__)

DATASETS_PAGE = "https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets"
ARCHIVE = "https://www.sec.gov/Archives/"
COLS = [
    "accession", "filing_date", "issuer_cik", "ticker", "owner_cik", "owner_name", "relationship",
    "title", "trans_date", "code", "acq_disp", "shares", "price", "value", "plan_10b5_1", "source",
]  # fmt: skip

_PLAN = re.compile(r"10b5-?1", re.IGNORECASE)


# --------------------------------------------------------------------------- data sets


def list_dataset_urls(session: Any) -> dict[str, str]:
    """{'2026q3': url, ...} from the SEC page (paths moved over time, so read them from the page)."""
    r = http.get(session, DATASETS_PAGE, timeout=60)
    assert r is not None
    out: dict[str, str] = {}
    for href in re.findall(r'href="([^"]+?(\d{4}q[1-4])_form345\.zip)"', r.text):
        path, q = href
        url = path if path.startswith("http") else f"https://www.sec.gov{path}"
        out[q] = url
    return dict(sorted(out.items()))


def _read_tsv(z: zipfile.ZipFile, name: str, usecols: list[str]) -> pd.DataFrame:
    with z.open(name) as f:
        return pd.read_csv(
            f,
            sep="\t",
            dtype=str,
            usecols=lambda c: c in usecols,
            keep_default_na=False,
            quoting=3,
            on_bad_lines="skip",
        )


def parse_dataset(raw: bytes) -> pd.DataFrame:
    z = zipfile.ZipFile(io.BytesIO(raw))
    sub = _read_tsv(
        z,
        "SUBMISSION.tsv",
        [
            "ACCESSION_NUMBER",
            "FILING_DATE",
            "ISSUERCIK",
            "ISSUERTRADINGSYMBOL",
            "DOCUMENT_TYPE",
            "AFF10B5ONE",
        ],
    )
    tr = _read_tsv(
        z,
        "NONDERIV_TRANS.tsv",
        [
            "ACCESSION_NUMBER",
            "TRANS_DATE",
            "TRANS_CODE",
            "TRANS_SHARES",
            "TRANS_PRICEPERSHARE",
            "TRANS_ACQUIRED_DISP_CD",
        ],
    )
    own = _read_tsv(
        z,
        "REPORTINGOWNER.tsv",
        [
            "ACCESSION_NUMBER",
            "RPTOWNERCIK",
            "RPTOWNERNAME",
            "RPTOWNER_RELATIONSHIP",
            "RPTOWNER_TITLE",
        ],
    )
    fn = _read_tsv(z, "FOOTNOTES.tsv", ["ACCESSION_NUMBER", "FOOTNOTE_TXT"])

    if (
        "AFF10B5ONE" not in sub
    ):  # the 10b5-1 checkbox exists only since 2023; footnotes cover earlier years
        sub["AFF10B5ONE"] = "0"
    tr = tr[tr["TRANS_CODE"].isin(["P", "S"])]
    own = own.drop_duplicates("ACCESSION_NUMBER")  # primary reporting owner only (joint filings)
    plan_acc = set(fn.loc[fn["FOOTNOTE_TXT"].str.contains(_PLAN, na=False), "ACCESSION_NUMBER"])
    df = tr.merge(sub, on="ACCESSION_NUMBER", how="inner").merge(
        own, on="ACCESSION_NUMBER", how="left"
    )
    df = df[df["DOCUMENT_TYPE"].isin(["4", "4/A"])]
    shares = pd.to_numeric(df["TRANS_SHARES"], errors="coerce")
    price = pd.to_numeric(df["TRANS_PRICEPERSHARE"], errors="coerce")
    out = pd.DataFrame(
        {
            "accession": df["ACCESSION_NUMBER"],
            "filing_date": pd.to_datetime(df["FILING_DATE"], format="%d-%b-%Y", errors="coerce"),
            "issuer_cik": pd.to_numeric(df["ISSUERCIK"], errors="coerce").astype("Int64"),
            "ticker": df["ISSUERTRADINGSYMBOL"].str.upper().str.strip(),
            "owner_cik": pd.to_numeric(df["RPTOWNERCIK"], errors="coerce").astype("Int64"),
            "owner_name": df["RPTOWNERNAME"],
            "relationship": df["RPTOWNER_RELATIONSHIP"],
            "title": df["RPTOWNER_TITLE"],
            "trans_date": pd.to_datetime(df["TRANS_DATE"], format="%d-%b-%Y", errors="coerce"),
            "code": df["TRANS_CODE"],
            "acq_disp": df["TRANS_ACQUIRED_DISP_CD"],
            "shares": shares,
            "price": price,
            "value": shares * price,
            "plan_10b5_1": (df["AFF10B5ONE"].isin(["1", "true", "True"]))
            | df["ACCESSION_NUMBER"].isin(plan_acc),
            "source": "sec-dataset",
        }
    )
    return out.dropna(subset=["filing_date", "issuer_cik"]).reset_index(drop=True)


def quarters_dir(data_dir: Path) -> Path:
    return data_dir / "insiders" / "quarters"


def daily_dir(data_dir: Path) -> Path:
    return data_dir / "insiders" / "daily"


def update_datasets(
    session: Any, data_dir: Path, since_year: int = 2010, refresh_last: int = 1
) -> list[str]:
    """Download quarters not stored yet (plus the latest `refresh_last` ones, which the SEC
    may still revise). Returns the quarters written."""
    urls = list_dataset_urls(session)
    have = {p.stem for p in quarters_dir(data_dir).glob("*.parquet")}
    wanted = [q for q in urls if int(q[:4]) >= since_year]
    recent = set(wanted[-refresh_last:]) if refresh_last else set()
    written = []
    for q in wanted:
        if q in have and q not in recent:
            continue
        try:
            r = http.get(session, urls[q], timeout=300)
            assert r is not None
            df = parse_dataset(r.content)
            write_parquet(df, quarters_dir(data_dir) / f"{q}.parquet")
            written.append(q)
            log.info("insiders: %s -> %d open-market trades", q, len(df))
        except Exception as e:
            log.warning("insiders: %s failed: %s", q, e)
    return written


# --------------------------------------------------------------------------- Form 4 XML


def _text(el: ET.Element | None, path: str) -> str | None:
    if el is None:
        return None
    node = el.find(path)
    if node is None:
        return None
    v = node.find("value")
    t = (v.text if v is not None else node.text) or ""
    return t.strip() or None


def parse_form4(text: str, accession: str, filing_date: str) -> list[dict[str, Any]]:
    m = re.search(r"<ownershipDocument>.*?</ownershipDocument>", text, re.DOTALL)
    if not m:
        return []
    try:
        root = ET.fromstring(m.group(0))
    except ET.ParseError:
        return []
    issuer = root.find("issuer")
    owner = root.find("reportingOwner")
    rel = owner.find("reportingOwnerRelationship") if owner is not None else None
    roles = []
    if rel is not None:
        for tag, name in (
            ("isDirector", "Director"),
            ("isOfficer", "Officer"),
            ("isTenPercentOwner", "TenPercentOwner"),
            ("isOther", "Other"),
        ):
            if (rel.findtext(tag) or "").strip().lower() in ("1", "true"):
                roles.append(name)
    footnotes = " ".join((f.text or "") for f in root.iter("footnote"))
    plan = (root.findtext("aff10b5One") or "").strip().lower() in ("1", "true") or bool(
        _PLAN.search(footnotes)
    )
    rows = []
    for t in root.iter("nonDerivativeTransaction"):
        code = (t.findtext("transactionCoding/transactionCode") or "").strip()
        if code not in ("P", "S"):
            continue
        shares = _num(_text(t, "transactionAmounts/transactionShares"))
        price = _num(_text(t, "transactionAmounts/transactionPricePerShare"))
        rows.append(
            {
                "accession": accession,
                "filing_date": pd.Timestamp(filing_date),
                "issuer_cik": _int(issuer.findtext("issuerCik") if issuer is not None else None),
                "ticker": (
                    (issuer.findtext("issuerTradingSymbol") if issuer is not None else "") or ""
                )
                .upper()
                .strip(),
                "owner_cik": _int(
                    owner.findtext("reportingOwnerId/rptOwnerCik") if owner is not None else None
                ),
                "owner_name": (
                    owner.findtext("reportingOwnerId/rptOwnerName") if owner is not None else None
                ),
                "relationship": ",".join(roles),
                "title": (rel.findtext("officerTitle") if rel is not None else None),
                "trans_date": pd.to_datetime(_text(t, "transactionDate"), errors="coerce"),
                "code": code,
                "acq_disp": _text(t, "transactionAmounts/transactionAcquiredDisposedCode"),
                "shares": shares,
                "price": price,
                "value": shares * price if shares is not None and price is not None else np.nan,
                "plan_10b5_1": plan,
                "source": "form4-xml",
            }
        )
    return rows


def _num(s: str | None) -> float:
    try:
        return float(s) if s is not None else math.nan
    except ValueError:
        return math.nan


def _int(s: str | None) -> int | None:
    try:
        return int(str(s).strip()) if s else None
    except ValueError:
        return None


def fetch_form4s(
    session: Any, index: pd.DataFrame, universe_ciks: Iterable[int], workers: int = 6
) -> pd.DataFrame:
    """Parse the Form 4 filings in a daily-index frame whose issuer or filer is in the universe."""
    if index.empty:
        return pd.DataFrame(columns=COLS)
    ciks = set(int(c) for c in universe_ciks)
    f4 = index[index["form"].isin(["4", "4/A"])]
    relevant = set(f4.loc[f4["cik"].isin(ciks), "accession"])
    f4 = f4[f4["accession"].isin(relevant)].drop_duplicates("accession")
    log.info("form 4: %d filings to parse", len(f4))

    def one(rec: tuple[str, str, str]) -> list[dict[str, Any]]:
        acc, path, d = rec
        try:
            r = http.get(session, ARCHIVE + path, timeout=30, ok_404=True)
            if r is None:
                return []
            return parse_form4(r.text, acc, f"{d[:4]}-{d[4:6]}-{d[6:]}")
        except Exception as e:
            log.debug("form 4 %s failed: %s", acc, e)
            return []

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for r in pool.map(one, zip(f4["accession"], f4["file"], f4["date"], strict=True)):
            rows.extend(r)
    df = pd.DataFrame(rows, columns=COLS)
    if not df.empty:
        df["issuer_cik"] = df["issuer_cik"].astype("Int64")
        df["owner_cik"] = df["owner_cik"].astype("Int64")
        df = df[df["issuer_cik"].isin(ciks)]
    return df.reset_index(drop=True)


def write_daily(data_dir: Path, df: pd.DataFrame, day: date) -> None:
    if df.empty:
        return
    path = daily_dir(data_dir) / f"{day:%Y%m%d}.parquet"
    if path.exists():
        df = pd.concat([pd.read_parquet(path), df], ignore_index=True)
    write_parquet(df.drop_duplicates(["accession", "trans_date", "code", "shares", "price"]), path)


# --------------------------------------------------------------------------- load + classify


def load(data_dir: Path) -> pd.DataFrame:
    files = sorted(quarters_dir(data_dir).glob("*.parquet")) + sorted(
        daily_dir(data_dir).glob("*.parquet")
    )
    if not files:
        return pd.DataFrame(columns=COLS)
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    # A filing can be in a daily file and later in a data set: keep one copy per transaction.
    df = df.drop_duplicates(["accession", "trans_date", "code", "shares", "price"], keep="first")
    df["filing_date"] = pd.to_datetime(df["filing_date"])
    df["trans_date"] = pd.to_datetime(df["trans_date"])
    # Empty "day processed" marker files have untyped columns; force the real types.
    for c in ("shares", "price", "value"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    for c in ("issuer_cik", "owner_cik"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    df["plan_10b5_1"] = df["plan_10b5_1"].fillna(False).astype(bool)
    return df.dropna(subset=["filing_date", "issuer_cik"]).reset_index(drop=True)


def classify(df: pd.DataFrame) -> pd.DataFrame:
    """Add `routine` and `opportunistic` columns (Cohen, Malloy & Pomorski style)."""
    if df.empty:
        return df.assign(routine=pd.Series(dtype=bool), opportunistic=pd.Series(dtype=bool))
    d = df.copy()
    d["ym_year"] = d["trans_date"].dt.year
    d["ym_month"] = d["trans_date"].dt.month
    traded = set(
        zip(d["owner_cik"].astype("Int64").astype(str), d["ym_year"], d["ym_month"], strict=True)
    )
    routine = []
    for owner, y, m in zip(
        d["owner_cik"].astype("Int64").astype(str), d["ym_year"], d["ym_month"], strict=True
    ):
        if owner == "<NA>" or pd.isna(y):
            routine.append(False)
            continue
        routine.append(all((owner, int(y) - k, int(m)) in traded for k in (1, 2, 3)))
    d["routine"] = routine
    d["opportunistic"] = ~d["routine"] & ~d["plan_10b5_1"].astype(bool)
    return d.drop(columns=["ym_year", "ym_month"])


def f4_raw(
    trades: pd.DataFrame, as_of: pd.Timestamp, window_days: int = 90, cluster_days: int = 30
) -> pd.DataFrame:
    """Per issuer CIK: the spec's insider value using only filings public by `as_of`.

    value = log(1 + $bought / 100,000), x1.5 if >= 2 different insiders bought within 30 days;
    opportunistic sells count negative with a quarter of the weight.
    """
    if trades.empty:
        return pd.DataFrame(
            columns=["insider_value", "insider_buy_usd", "insider_sell_usd", "insider_buyers"]
        )
    w = trades[
        (trades["filing_date"] <= as_of)
        & (trades["filing_date"] > as_of - pd.Timedelta(days=window_days))
        & trades["opportunistic"]
    ]
    buys = w[w["code"] == "P"]
    sells = w[w["code"] == "S"]
    bought = buys.groupby("issuer_cik")["value"].sum()
    sold = sells.groupby("issuer_cik")["value"].sum()
    recent = buys[buys["filing_date"] > as_of - pd.Timedelta(days=cluster_days)]
    buyers = recent.groupby("issuer_cik")["owner_cik"].nunique()
    idx = bought.index.union(sold.index)
    out = pd.DataFrame(index=idx)
    out["insider_buy_usd"] = bought.reindex(idx).fillna(0.0)
    out["insider_sell_usd"] = sold.reindex(idx).fillna(0.0)
    out["insider_buyers"] = buyers.reindex(idx).fillna(0).astype(int)
    val = np.log1p(out["insider_buy_usd"].clip(lower=0) / 100_000)
    val = val * np.where(out["insider_buyers"] >= 2, 1.5, 1.0)
    val = val - 0.25 * np.log1p(out["insider_sell_usd"].clip(lower=0) / 100_000)
    out["insider_value"] = val
    out.index.name = "issuer_cik"
    return out


def recent_trades(
    trades: pd.DataFrame, cik: int, as_of: pd.Timestamp, days: int = 365, limit: int = 40
) -> list[dict[str, Any]]:
    t = trades[
        (trades["issuer_cik"] == cik)
        & (trades["filing_date"] <= as_of)
        & (trades["filing_date"] > as_of - pd.Timedelta(days=days))
    ]
    t = t.sort_values("filing_date", ascending=False).head(limit)
    return [
        {
            "filed": r.filing_date.strftime("%Y-%m-%d"),
            "traded": r.trans_date.strftime("%Y-%m-%d") if pd.notna(r.trans_date) else None,
            "insider": r.owner_name,
            "role": r.title or r.relationship,
            "type": "Buy" if r.code == "P" else "Sell",
            "shares": None if pd.isna(r.shares) else float(r.shares),
            "price": None if pd.isna(r.price) else float(r.price),
            "value": None if pd.isna(r.value) else float(r.value),
            "kind": "planned (10b5-1)"
            if r.plan_10b5_1
            else ("routine" if r.routine else "opportunistic"),
        }
        for r in t.itertuples()
    ]


def last_dataset_end(data_dir: Path) -> date | None:
    qs = sorted(p.stem for p in quarters_dir(data_dir).glob("*.parquet"))
    if not qs:
        return None
    y, q = int(qs[-1][:4]), int(qs[-1][-1])
    month = q * 3
    end = pd.Timestamp(year=y, month=month, day=1) + pd.offsets.MonthEnd(0)
    return date(end.year, end.month, end.day)


def needs_xml_days(data_dir: Path, today: date) -> Sequence[date]:
    """Trading days after the last data set that have no daily Form 4 file yet (max 90 days)."""
    from convergealpha.util.calendar import is_trading_day

    end = last_dataset_end(data_dir)
    if end is None:
        return []
    have = {p.stem for p in daily_dir(data_dir).glob("*.parquet")}
    days = []
    d = max(
        end + pd.Timedelta(days=1).to_pytimedelta(), today - pd.Timedelta(days=90).to_pytimedelta()
    )
    while d <= today:
        if is_trading_day(d) and d.strftime("%Y%m%d") not in have:
            days.append(d)
        d += pd.Timedelta(days=1).to_pytimedelta()
    return days
