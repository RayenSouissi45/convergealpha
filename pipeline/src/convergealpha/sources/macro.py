"""FRED macro series (VIX, high-yield spread, yield curve, fed funds, EUR/USD) and FINRA short
interest."""

from __future__ import annotations

import io
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from convergealpha.util import http
from convergealpha.util.calendar import add_trading_days, is_trading_day, previous_trading_day
from convergealpha.util.io import row_keys, write_parquet
from convergealpha.util.log import get

log = get(__name__)

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_SERIES = {
    "VIXCLS": "VIX",
    "BAMLH0A0HYM2": "High-yield credit spread",
    "T10Y2Y": "10-year minus 2-year Treasury",
    "DFF": "Fed funds rate",
    # Euro amounts for the Plan builder and the paper-trading strategies. Published about weekly.
    "DEXUSEU": "EUR/USD (US dollars per euro)",
}


def fetch_fred(api_key: str, start: date) -> pd.DataFrame:
    s = http.make_session()
    frames = []
    for sid in FRED_SERIES:
        r = http.get(
            s,
            FRED_URL,
            params={
                "series_id": sid,
                "api_key": api_key,
                "file_type": "json",
                "observation_start": start.isoformat(),
            },
            timeout=60,
        )
        assert r is not None
        obs = r.json().get("observations", [])
        df = pd.DataFrame(obs)
        if df.empty:
            continue
        df = df[["date", "value", "realtime_start"]].assign(series=sid)
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        frames.append(df.dropna(subset=["value"]))
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    return out


def fred_path(data_dir: Path) -> Path:
    return data_dir / "macro" / "fred.parquet"


def store_fred(data_dir: Path, df: pd.DataFrame) -> int:
    """Append observations not stored yet (the file is small)."""
    p = fred_path(data_dir)
    if p.is_file():
        old = pd.read_parquet(p)
        key_old = set(row_keys(old, ["series", "date"]))
        new = df[~row_keys(df, ["series", "date"]).isin(key_old)]
        if new.empty:
            return 0
        df = pd.concat([old, new], ignore_index=True)
        added = len(new)
    else:
        added = len(df)
    write_parquet(df.sort_values(["series", "date"]), p)
    return added


def load_fred(data_dir: Path) -> pd.DataFrame:
    p = fred_path(data_dir)
    if not p.is_file():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    return df.pivot_table(index="date", columns="series", values="value").sort_index()


# --------------------------------------------------------------------------- FINRA short interest

FINRA_URL = "https://cdn.finra.org/equity/otcmarket/biweekly/shrt{ymd}.csv"
# NNM = Nasdaq Global, SC = Nasdaq Capital Market, AMEX = NYSE American.
_MARKETS = {"NNM", "NYSE", "AMEX", "SC", "NAS", "NCM", "NGM", "NGS", "NMS"}


def settlement_dates(start: date, end: date) -> list[date]:
    """FINRA settlement dates: mid-month (15th) and month-end, moved back to a trading day."""
    out = []
    d = date(start.year, start.month, 1)
    while d <= end:
        for target in (
            date(d.year, d.month, 15),
            (pd.Timestamp(d) + pd.offsets.MonthEnd(0)).date(),
        ):
            s = target if is_trading_day(target) else previous_trading_day(target)
            if start <= s <= end:
                out.append(s)
        d = (pd.Timestamp(d) + pd.offsets.MonthBegin(1)).date()
    return sorted(set(out))


def published(settlement: date) -> date:
    """Conservative public date: FINRA disseminates about 7 business days after settlement."""
    return add_trading_days(settlement, 8)


def si_dir(data_dir: Path) -> Path:
    return data_dir / "short_interest"


def update_short_interest(data_dir: Path, today: date, since: date) -> list[date]:
    s = http.make_session()
    have = {p.stem for p in si_dir(data_dir).glob("*.parquet")}
    written = []
    for d in settlement_dates(since, today):
        if d.strftime("%Y%m%d") in have or published(d) > today + timedelta(days=3):
            continue
        try:
            r = http.get(s, FINRA_URL.format(ymd=d.strftime("%Y%m%d")), ok_404=True, timeout=120)
        except http.HttpError as e:
            if "HTTP 403" in str(e):  # the CDN answers 403 for files that do not exist
                continue
            raise
        if r is None:
            continue
        try:
            # Issue names can contain stray quotes: parse with quoting off, strip quotes after.
            df = pd.read_csv(
                io.StringIO(r.text), sep="|", dtype=str, quoting=3, on_bad_lines="skip"
            )
            df.columns = [c.strip('"') for c in df.columns]
            df = df.apply(lambda col: col.str.strip('"'))
        except Exception as e:
            log.warning("finra %s unreadable: %s", d, e)
            continue
        df = df[df["marketClassCode"].isin(_MARKETS)]
        out = pd.DataFrame(
            {
                "ticker": df["symbolCode"]
                .str.upper()
                .str.replace(".", "-", regex=False)
                .str.replace("/", "-", regex=False),
                "settlement": pd.Timestamp(d),
                "published": pd.Timestamp(published(d)),
                "short_shares": pd.to_numeric(df["currentShortPositionQuantity"], errors="coerce"),
                "prev_short_shares": pd.to_numeric(
                    df["previousShortPositionQuantity"], errors="coerce"
                ),
                "avg_daily_volume": pd.to_numeric(
                    df["averageDailyVolumeQuantity"], errors="coerce"
                ),
                "days_to_cover": pd.to_numeric(df["daysToCoverQuantity"], errors="coerce"),
            }
        )
        write_parquet(out, si_dir(data_dir) / f"{d:%Y%m%d}.parquet")
        written.append(d)
    return written


def load_short_interest(data_dir: Path, as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    files = sorted(si_dir(data_dir).glob("*.parquet"))
    if not files:
        return pd.DataFrame()
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    if as_of is not None:
        df = df[df["published"] <= as_of]
    return df


def latest_short_interest(data_dir: Path, as_of: pd.Timestamp) -> pd.DataFrame:
    df = load_short_interest(data_dir, as_of)
    if df.empty:
        return df
    return df.sort_values("settlement").drop_duplicates("ticker", keep="last").set_index("ticker")
