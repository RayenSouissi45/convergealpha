"""The universe: US common stocks on NYSE, Nasdaq and NYSE American.

Sources: Nasdaq Trader symbol directories (listing exchange, ETF and test-issue flags) joined with
SEC company_tickers_exchange.json (CIK). Every ticker ever seen is kept with first/last seen dates
so the history never loses delisted names (limits survivorship bias going forward).
"""

from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path

import pandas as pd

from convergealpha.util import http
from convergealpha.util.io import write_parquet
from convergealpha.util.log import get

log = get(__name__)

NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
SEC_URL = "https://www.sec.gov/files/company_tickers_exchange.json"

# otherlisted.txt exchange codes we keep: N = NYSE, A = NYSE American.
OTHER_EXCHANGES = {"N": "NYSE", "A": "NYSE American"}

# Security names that are not common stock (warrants, units, rights, preferreds, notes, funds...).
_EXCLUDE = re.compile(
    r"\bwarrants?\b|\bwts?\b|\brights?\b|\bunits?\b|\bpreferred\b|\bpfd\b|\bpref\b"
    r"|\bnotes?\b|\bdebentures?\b|\bbonds?\b"
    r"|\bfund\b|\bfunds\b|\betn\b|exchange[- ]traded|\bmunicipal\b|\bincome trust\b"
    r"|\bcapital securities\b|\btrust preferred\b|\bperpetual\b|\bsubordinated\b"
    r"|\d+(?:\.\d+)?\s?%",
    re.IGNORECASE,
)
# Blank-check shells (SPACs). Refined with SEC SIC code 6770 once SIC data is loaded.
_SPAC = re.compile(
    r"\bacquisition (?:corp|corporation|co|company|inc|ltd|limited)\b|\bspac\b|blank check",
    re.IGNORECASE,
)
_ADR = re.compile(r"american depositary|\bads\b|\badr\b|depositary shares?\b", re.IGNORECASE)


def yahoo_symbol(symbol: str) -> str:
    """Nasdaq Trader 'BRK.B' / 'BRK/B' -> Yahoo 'BRK-B' (also SEC's convention)."""
    return symbol.strip().upper().replace(".", "-").replace("/", "-").replace("$", "-P")


def _read_pipe(text: str) -> pd.DataFrame:
    lines = [ln for ln in text.splitlines() if ln and not ln.startswith("File Creation Time")]
    return pd.read_csv(io.StringIO("\n".join(lines)), sep="|", dtype=str, keep_default_na=False)


def fetch_lists(
    session_sec: object | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Download the three raw lists (nasdaq, other, sec)."""
    plain = http.make_session()
    nasdaq = _read_pipe(http.get(plain, NASDAQ_URL).text)  # type: ignore[union-attr]
    other = _read_pipe(http.get(plain, OTHER_URL).text)  # type: ignore[union-attr]
    sec_session = session_sec if session_sec is not None else plain
    payload = http.get(sec_session, SEC_URL).json()  # type: ignore[arg-type,union-attr]
    sec = pd.DataFrame(payload["data"], columns=payload["fields"])
    return nasdaq, other, sec


def build_universe(nasdaq: pd.DataFrame, other: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """Filter the raw lists to common stocks. Returns one row per ticker."""
    nq = nasdaq[(nasdaq["ETF"] == "N") & (nasdaq["Test Issue"] == "N")]
    nq = pd.DataFrame(
        {
            "symbol": nq["Symbol"],
            "name": nq["Security Name"],
            "exchange": "Nasdaq",
            "financial_status": nq["Financial Status"],
        }
    )
    ot = other[
        (other["ETF"] == "N")
        & (other["Test Issue"] == "N")
        & other["Exchange"].isin(OTHER_EXCHANGES)
    ]
    ot = pd.DataFrame(
        {
            "symbol": ot["ACT Symbol"],
            "name": ot["Security Name"],
            "exchange": ot["Exchange"].map(OTHER_EXCHANGES),
            "financial_status": "",
        }
    )
    u = pd.concat([nq, ot], ignore_index=True)
    u = u[u["symbol"].str.len() > 0]
    names = u["name"].fillna("")
    u = u.assign(
        excluded_reason=None,
        is_adr=names.str.contains(_ADR),
    )
    u.loc[names.str.contains(_EXCLUDE), "excluded_reason"] = "not common stock"
    u.loc[u["excluded_reason"].isna() & names.str.contains(_SPAC), "excluded_reason"] = (
        "blank-check (SPAC)"
    )
    u["ticker"] = u["symbol"].map(yahoo_symbol)

    sec = sec.assign(ticker=sec["ticker"].astype(str).map(yahoo_symbol))
    sec = sec.drop_duplicates("ticker")[["ticker", "cik", "name"]].rename(
        columns={"name": "sec_name"}
    )
    u = u.merge(sec, on="ticker", how="left")
    u["cik"] = u["cik"].astype("Int64")
    u = u.drop_duplicates("ticker").sort_values("ticker").reset_index(drop=True)
    return u[
        [
            "ticker",
            "symbol",
            "name",
            "sec_name",
            "exchange",
            "cik",
            "is_adr",
            "financial_status",
            "excluded_reason",
        ]
    ]


def merge_history(previous: pd.DataFrame | None, today: pd.DataFrame, as_of: date) -> pd.DataFrame:
    """Keep every ticker ever seen. `last_seen` is set only when a ticker disappears, so the
    stored file changes only when the listing set changes (small git history)."""
    cur = today.assign(first_seen=as_of, last_seen=pd.NaT, active=True)
    if previous is None or previous.empty:
        return cur.reset_index(drop=True)
    prev = previous.set_index("ticker")
    cur = cur.set_index("ticker")
    first = prev["first_seen"].reindex(cur.index)
    cur["first_seen"] = first.where(first.notna(), as_of)
    gone = prev.loc[~prev.index.isin(cur.index)].copy()
    newly_gone = gone["active"].astype(bool)
    gone["last_seen"] = pd.to_datetime(gone["last_seen"])
    gone.loc[newly_gone, "last_seen"] = pd.Timestamp(as_of)
    gone["active"] = False
    out = pd.concat([cur, gone])
    return out.reset_index().sort_values("ticker").reset_index(drop=True)


def universe_path(data_dir: Path) -> Path:
    return data_dir / "reference" / "universe.parquet"


def load(data_dir: Path) -> pd.DataFrame | None:
    p = universe_path(data_dir)
    return pd.read_parquet(p) if p.is_file() else None


def update(data_dir: Path, as_of: date, sec_session: object | None = None) -> pd.DataFrame:
    nasdaq, other, sec = fetch_lists(sec_session)
    today = build_universe(nasdaq, other, sec)
    previous = load(data_dir)
    merged = merge_history(previous, today, as_of)
    for col in ("first_seen", "last_seen"):
        merged[col] = pd.to_datetime(merged[col]).dt.date
    if previous is None or not _same(previous, merged):
        write_parquet(merged, universe_path(data_dir))
    eligible = merged[merged["active"] & merged["excluded_reason"].isna()]
    log.info("universe: %d active common stocks (%d tickers ever seen)", len(eligible), len(merged))
    return merged


def _same(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    cols = ["ticker", "name", "exchange", "cik", "excluded_reason", "active"]
    try:
        x = a[cols].astype(str).sort_values("ticker").reset_index(drop=True)
        y = b[cols].astype(str).sort_values("ticker").reset_index(drop=True)
        return bool(x.equals(y))
    except KeyError:
        return False


def active_stocks(universe: pd.DataFrame) -> pd.DataFrame:
    """Rows that count as stocks today (active, common stock)."""
    return universe[universe["active"] & universe["excluded_reason"].isna()].reset_index(drop=True)
