"""Point-in-time fundamentals from SEC XBRL company facts.

Every fact keeps its `filed` date and only the FIRST reported value for a given period is kept
(no restated values in history). Flow items become discrete quarters (Q4 = annual - Q1..Q3) and
trailing-twelve-month (TTM) sums; each value is "known from" the latest filing it depends on.

Stored in the data repo (append-only):
  fundamentals/facts/<YYYYMMDD>.parquet   facts first seen that day (cik, concept, start, end, val, filed, accn, form)
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from convergealpha.util import http
from convergealpha.util.io import row_keys, write_parquet
from convergealpha.util.log import get

log = get(__name__)

FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
BULK_URL = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"

# Our name -> us-gaap concepts in priority order (first one a company uses wins per period).
FLOW: dict[str, list[str]] = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "RevenuesNetOfInterestExpense",
    ],
    "cogs": [
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
        "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
    ],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ],
    "income_tax": ["IncomeTaxExpenseBenefit"],
    "pretax_income": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    "dna": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "Depreciation",
    ],
    "cfo": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "eps_diluted": [
        "EarningsPerShareDiluted",
        "EarningsPerShareBasicAndDiluted",
        "EarningsPerShareBasic",
    ],
}
INSTANT: dict[str, list[str]] = {
    "assets": ["Assets"],
    "liabilities": ["Liabilities"],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "Cash",
    ],
    "lt_debt": ["LongTermDebtNoncurrent", "LongTermDebt", "LongTermDebtAndCapitalLeaseObligations"],
    "st_debt": ["LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings", "CommercialPaper"],
}
DEI_SHARES = "EntityCommonStockSharesOutstanding"

_CONCEPT_TO_ITEM: dict[str, tuple[str, int]] = {}
for _item, _names in {**FLOW, **INSTANT}.items():
    for _rank, _name in enumerate(_names):
        _CONCEPT_TO_ITEM[_name] = (_item, _rank)

FACT_COLS = [
    "cik",
    "item",
    "rank",
    "concept",
    "start",
    "end",
    "val",
    "filed",
    "accn",
    "form",
    "unit",
]
MIN_END = pd.Timestamp("2009-01-01")


def extract_facts(cik: int, payload: dict[str, Any]) -> pd.DataFrame:
    """Flatten the concepts we use from one companyfacts JSON."""
    rows: list[tuple[Any, ...]] = []
    facts = payload.get("facts") or {}
    gaap = facts.get("us-gaap") or {}
    for concept, body in gaap.items():
        hit = _CONCEPT_TO_ITEM.get(concept)
        if hit is None:
            continue
        item, rank = hit
        for unit, values in (body.get("units") or {}).items():
            if unit not in ("USD", "USD/shares"):
                continue
            for v in values:
                if v.get("form") not in (
                    "10-K",
                    "10-Q",
                    "10-K/A",
                    "10-Q/A",
                    "20-F",
                    "40-F",
                    "10-KT",
                    "10-QT",
                ):
                    continue
                rows.append(
                    (
                        cik,
                        item,
                        rank,
                        concept,
                        v.get("start"),
                        v.get("end"),
                        v.get("val"),
                        v.get("filed"),
                        v.get("accn"),
                        v.get("form"),
                        unit,
                    )
                )
    dei = (facts.get("dei") or {}).get(DEI_SHARES) or {}
    for unit, values in (dei.get("units") or {}).items():
        for v in values:
            rows.append(
                (
                    cik,
                    "shares_out",
                    0,
                    DEI_SHARES,
                    None,
                    v.get("end"),
                    v.get("val"),
                    v.get("filed"),
                    v.get("accn"),
                    v.get("form"),
                    unit,
                )
            )
    df = pd.DataFrame(rows, columns=FACT_COLS)
    if df.empty:
        return df
    for c in ("start", "end", "filed"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["val"] = pd.to_numeric(df["val"], errors="coerce").astype("float64")
    df = df.dropna(subset=["end", "filed", "val"])
    df = df[df["end"] >= MIN_END]
    # Comparatives repeat each value in later filings: keep only the first report of each period.
    df = df.sort_values("filed").drop_duplicates(["concept", "start", "end"], keep="first")
    return df.reset_index(drop=True)


def fetch_companyfacts(session: Any, ciks: Sequence[int], workers: int = 6) -> pd.DataFrame:
    def one(cik: int) -> pd.DataFrame:
        try:
            r = http.get(session, FACTS_URL.format(cik=int(cik)), ok_404=True, timeout=60)
            return (
                pd.DataFrame(columns=FACT_COLS) if r is None else extract_facts(int(cik), r.json())
            )
        except Exception as e:
            log.debug("companyfacts %s failed: %s", cik, e)
            return pd.DataFrame(columns=FACT_COLS)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        frames = [f for f in pool.map(one, ciks) if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=FACT_COLS)


def fetch_bulk(session: Any, ciks: Iterable[int], tmp: Path) -> pd.DataFrame:
    """Download companyfacts.zip (~1.4 GB) once and keep only our companies."""
    wanted = {f"CIK{int(c):010d}.json": int(c) for c in ciks}
    tmp.mkdir(parents=True, exist_ok=True)
    path = tmp / "companyfacts.zip"
    r = http.get(session, BULK_URL, timeout=1800, stream=True)
    assert r is not None
    with open(path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1 << 22):
            f.write(chunk)
    frames = []
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n in wanted]
        log.info("companyfacts.zip: %d of our companies present", len(names))
        for i, n in enumerate(names):
            with z.open(n) as fh:
                try:
                    payload = json.load(io.TextIOWrapper(fh, encoding="utf-8"))
                except Exception:
                    continue
            df = extract_facts(wanted[n], payload)
            if not df.empty:
                frames.append(df)
            if i and i % 1000 == 0:
                log.info("companyfacts.zip: parsed %d/%d", i, len(names))
    path.unlink(missing_ok=True)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=FACT_COLS)


# --------------------------------------------------------------------------- storage


def facts_dir(data_dir: Path) -> Path:
    return data_dir / "fundamentals" / "facts"


def load_facts(data_dir: Path) -> pd.DataFrame:
    files = sorted(facts_dir(data_dir).glob("*.parquet"))
    if not files:
        return pd.DataFrame(columns=FACT_COLS)
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _key(df: pd.DataFrame) -> pd.Series:
    return row_keys(df, ["cik", "concept", "start", "end", "accn"])


def append_facts(
    data_dir: Path, new: pd.DataFrame, day: date, existing: pd.DataFrame | None = None
) -> int:
    """Store facts not stored before (same company, concept, period and filing)."""
    if new.empty:
        return 0
    old = existing if existing is not None else load_facts(data_dir)
    if not old.empty:
        new = new[~_key(new).isin(set(_key(old)))]
    new = new.drop_duplicates(subset=["cik", "concept", "start", "end", "accn"])
    if new.empty:
        return 0
    # GitHub rejects files over 100 MB: large loads are split into ~1,000-company chunks.
    ciks = sorted(new["cik"].unique())
    chunks = (
        [ciks[i : i + 1000] for i in range(0, len(ciks), 1000)] if len(new) > 1_500_000 else [ciks]
    )
    for k, part in enumerate(chunks):
        rows = new[new["cik"].isin(part)]
        name = f"{day:%Y%m%d}.parquet" if len(chunks) == 1 else f"{day:%Y%m%d}-{k:02d}.parquet"
        path = facts_dir(data_dir) / name
        if path.exists():
            rows = pd.concat([pd.read_parquet(path), rows], ignore_index=True)
        write_parquet(rows, path)
    return len(new)


# --------------------------------------------------------------------------- point-in-time series


def first_reported(facts: pd.DataFrame) -> pd.DataFrame:
    """One value per (cik, item, start, end): the best-ranked concept, as FIRST filed."""
    f = facts.sort_values(["filed", "rank"])
    return f.drop_duplicates(["cik", "item", "start", "end"], keep="first")


def quarterly_flows(facts: pd.DataFrame) -> pd.DataFrame:
    """Discrete quarterly values per (cik, item, end) with `known` = the date it became public.

    10-Q income statements report 3-month values, but cash-flow statements report year-to-date
    (6 and 9 months). Facts sharing a start date are cumulative from that start, so each quarter
    is the difference between consecutive cumulative values; direct 3-month facts win when both
    exist. Q4 comes out as annual minus nine months.
    """
    f = first_reported(facts[facts["item"].isin(FLOW)].dropna(subset=["start"]))
    if f.empty:
        return pd.DataFrame(columns=["cik", "item", "end", "val", "known"])
    f = f.assign(days=(f["end"] - f["start"]).dt.days)
    f = f[f["days"].between(80, 380)]
    direct = f[f["days"].between(80, 100)][["cik", "item", "end", "val", "filed"]].rename(
        columns={"filed": "known"}
    )
    derived = []
    cum = f[f["item"] != "eps_diluted"]  # EPS does not add up across periods
    for (cik, item, _start), g in cum.groupby(["cik", "item", "start"], sort=False):
        if len(g) < 2:
            continue
        g = g.sort_values("end")
        ends, vals, filed, days = (
            g["end"].to_numpy(),
            g["val"].to_numpy(),
            g["filed"].to_numpy(),
            g["days"].to_numpy(),
        )
        for i in range(1, len(g)):
            gap = days[i] - days[i - 1]
            if 80 <= gap <= 100:
                derived.append(
                    (cik, item, ends[i], float(vals[i] - vals[i - 1]), max(filed[i], filed[i - 1]))
                )
    q = direct
    if derived:
        d = pd.DataFrame(derived, columns=["cik", "item", "end", "val", "known"])
        d["end"] = pd.to_datetime(d["end"])
        d["known"] = pd.to_datetime(d["known"])
        q = pd.concat([direct.assign(_direct=0), d.assign(_direct=1)], ignore_index=True)
        q = q.sort_values(["_direct", "known"]).drop(columns="_direct")
    return q.drop_duplicates(["cik", "item", "end"], keep="first").reset_index(drop=True)


def ttm(quarters: pd.DataFrame) -> pd.DataFrame:
    """Trailing four quarters per (cik, item, end), requiring four consecutive quarters."""
    out = []
    for (cik, item), g in quarters.sort_values("end").groupby(["cik", "item"], sort=False):
        ends = g["end"].to_numpy()
        vals = g["val"].to_numpy()
        known = g["known"].to_numpy()
        for i in range(3, len(g)):
            span = (ends[i] - ends[i - 3]) / np.timedelta64(1, "D")
            if 250 <= span <= 300:
                out.append(
                    (
                        cik,
                        item,
                        ends[i],
                        float(vals[i - 3 : i + 1].sum()),
                        known[i - 3 : i + 1].max(),
                    )
                )
    return pd.DataFrame(out, columns=["cik", "item", "end", "val", "known"])


def instants(facts: pd.DataFrame) -> pd.DataFrame:
    f = facts[facts["item"].isin([*INSTANT, "shares_out"])]
    f = f.sort_values(["filed", "rank"]).drop_duplicates(["cik", "item", "end"], keep="first")
    return (
        f[["cik", "item", "end", "val", "filed"]]
        .rename(columns={"filed": "known"})
        .reset_index(drop=True)
    )


def as_of(series: pd.DataFrame, when: pd.Timestamp) -> pd.DataFrame:
    """Latest value per (cik, item) that was public by `when` -> wide (cik x item)."""
    s = series[series["known"] <= when]
    if s.empty:
        return pd.DataFrame()
    s = s.sort_values(["end", "known"]).drop_duplicates(["cik", "item"], keep="last")
    return s.pivot(index="cik", columns="item", values="val")


def known_dates(series: pd.DataFrame, when: pd.Timestamp) -> pd.Series:
    s = series[series["known"] <= when]
    return s.groupby("cik")["known"].max()


def f6_inputs(
    ttm_series: pd.DataFrame, inst: pd.DataFrame, when: pd.Timestamp, market_cap: pd.Series
) -> pd.DataFrame:
    """The five F6 ratios per CIK, point-in-time at `when`. market_cap is indexed by CIK."""
    t = as_of(ttm_series, when)
    b = as_of(inst, when)
    df = t.join(b, how="outer", rsuffix="_bs")
    for col in [
        "revenue",
        "cogs",
        "gross_profit",
        "operating_income",
        "net_income",
        "income_tax",
        "pretax_income",
        "dna",
        "cfo",
        "capex",
        "assets",
        "equity",
        "cash",
        "lt_debt",
        "st_debt",
    ]:
        if col not in df:
            df[col] = np.nan
    gp = df["gross_profit"].where(df["gross_profit"].notna(), df["revenue"] - df["cogs"])
    debt = df["lt_debt"].fillna(0) + df["st_debt"].fillna(0)
    tax_rate = (df["income_tax"] / df["pretax_income"]).clip(0, 0.35).fillna(0.21)
    nopat = df["operating_income"] * (1 - tax_rate)
    invested = df["equity"] + debt - df["cash"].fillna(0)
    out = pd.DataFrame(index=df.index)
    out["roic"] = (nopat / invested).where(invested > 0)
    out["gp_assets"] = (gp / df["assets"]).where(df["assets"] > 0)
    out["accruals"] = ((df["net_income"] - df["cfo"]) / df["assets"]).where(df["assets"] > 0)
    fcf = df["cfo"] - df["capex"].fillna(0)
    mc = market_cap.reindex(out.index)
    out["fcf_yield"] = (fcf / mc).where(mc > 0)
    ebitda = df["operating_income"] + df["dna"].fillna(0)
    lev = (debt / ebitda).where(ebitda > 0)
    # Debt with negative EBITDA is the worst case; no debt is the best.
    lev = lev.where(~((ebitda <= 0) & (debt > 0)), 20.0).where(~(debt <= 0), 0.0)
    out["debt_ebitda"] = lev.clip(upper=20.0)
    out["revenue_ttm"] = df["revenue"]
    out["net_income_ttm"] = df["net_income"]
    out["fcf_ttm"] = fcf
    out["assets"] = df["assets"]
    out["equity"] = df["equity"]
    out["debt"] = debt
    out.index.name = "cik"
    return out
