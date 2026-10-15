"""Daily prices: download from Yahoo (yfinance), store append-only, rebuild a consistent panel.

Storage in the data repo (never rewritten):
  prices/history/<YYYYMMDD>-<label>.parquet   full histories (backfill, new listings, repairs)
  prices/daily/<YYYY>/<YYYYMMDD>.parquet       rows first seen on that day

Each stored row keeps `basis`: the day it was downloaded. Yahoo's OHLC are split-adjusted as of
that day, so when a split happens later the loader divides older rows by the split ratio
(volume is multiplied). Dividends are stored per share, so a total-return index can be rebuilt
consistently: r_t = (close_t + dividend_t) / close_{t-1} - 1.
"""

from __future__ import annotations

import logging
import time
import warnings
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from convergealpha.config import HISTORY_START, NEW_YORK
from convergealpha.util.calendar import is_trading_day, last_completed_session
from convergealpha.util.io import row_keys, write_parquet
from convergealpha.util.log import get

log = get(__name__)

PRICE_COLS = ["open", "high", "low", "close"]
ROW_COLS = [
    "ticker",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "dividend",
    "split",
    "basis",
]
_YF_COLS = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume",
    "Dividends": "dividend",
    "Stock Splits": "split",
}


# --------------------------------------------------------------------------- download


def _download_batch(tickers: Sequence[str], start: date, end: date | None) -> pd.DataFrame:
    import yfinance as yf

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = yf.download(
            list(tickers),
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat() if end else None,
            auto_adjust=False,
            actions=True,
            progress=False,
            threads=True,
            group_by="column",
            timeout=30,
        )
    if raw is None or raw.empty:
        return pd.DataFrame(columns=ROW_COLS)
    if not isinstance(raw.columns, pd.MultiIndex):  # single ticker
        raw.columns = pd.MultiIndex.from_product([raw.columns, [tickers[0]]])
    long = raw.stack(level=1, future_stack=True)
    long.index.names = ["date", "ticker"]
    long = long.reset_index()
    long = long.rename(columns=_YF_COLS)
    for col in ("dividend", "split"):
        if col not in long:
            long[col] = 0.0
    long = long.dropna(subset=["close"])
    long["date"] = pd.to_datetime(long["date"]).dt.tz_localize(None).dt.normalize()
    return long[[c for c in ROW_COLS if c != "basis"]]


def download(
    tickers: Sequence[str],
    start: date,
    end: date | None = None,
    batch_size: int = 120,
    pause: float = 1.0,
) -> pd.DataFrame:
    """Download daily OHLCV + dividends + splits for many tickers, in polite batches."""
    frames: list[pd.DataFrame] = []
    tickers = list(dict.fromkeys(tickers))
    for i in range(0, len(tickers), batch_size):
        chunk = tickers[i : i + batch_size]
        for attempt in range(3):
            try:
                frames.append(_download_batch(chunk, start, end))
                break
            except Exception as e:  # yfinance raises many types; retry then move on
                log.warning(
                    "price batch %d failed (attempt %d): %s", i // batch_size, attempt + 1, e
                )
                time.sleep(5 * (attempt + 1))
        if pause:
            time.sleep(pause)
        if (i // batch_size) % 10 == 0:
            log.info(
                "prices: %d/%d tickers requested", min(i + batch_size, len(tickers)), len(tickers)
            )
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=[c for c in ROW_COLS if c != "basis"])
    return pd.concat(frames, ignore_index=True)


def finalize_rows(rows: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """Drop bars that are not final yet, sanitize values, stamp the basis day, compact dtypes."""
    if rows.empty:
        return pd.DataFrame(columns=ROW_COLS)
    last = pd.Timestamp(last_completed_session(now))
    rows = rows[rows["date"] <= last].copy()
    for col in PRICE_COLS:
        rows.loc[rows[col] <= 0, col] = np.nan  # zero/negative prices are data errors
    rows = rows.dropna(subset=["close"])
    rows["dividend"] = rows["dividend"].fillna(0.0)
    rows["split"] = rows["split"].fillna(0.0)
    rows["basis"] = pd.Timestamp(now.astimezone(NEW_YORK).date())
    for col in [*PRICE_COLS, "dividend"]:
        rows[col] = rows[col].astype("float32")
    rows["volume"] = rows["volume"].fillna(0).astype("float64")
    rows["split"] = rows["split"].astype("float32")
    rows["ticker"] = rows["ticker"].astype(str)
    return rows[ROW_COLS].sort_values(["ticker", "date"]).reset_index(drop=True)


# --------------------------------------------------------------------------- storage


def history_dir(data_dir: Path) -> Path:
    return data_dir / "prices" / "history"


def daily_dir(data_dir: Path) -> Path:
    return data_dir / "prices" / "daily"


def write_history_chunk(data_dir: Path, rows: pd.DataFrame, day: date, label: str) -> Path | None:
    if rows.empty:
        return None
    path = history_dir(data_dir) / f"{day:%Y%m%d}-{label}.parquet"
    n = 1
    while path.exists():  # never overwrite
        n += 1
        path = history_dir(data_dir) / f"{day:%Y%m%d}-{label}-{n}.parquet"
    return write_parquet(rows, path)


def write_daily(data_dir: Path, rows: pd.DataFrame, day: date, suffix: str = "") -> Path | None:
    """Rows first stored on `day`. Parallel shards pass a suffix so they never write the same file."""
    if rows.empty:
        return None
    path = daily_dir(data_dir) / f"{day:%Y}" / f"{day:%Y%m%d}{suffix}.parquet"
    if path.exists():  # a second run on the same day only adds rows not stored yet
        old = pd.read_parquet(path)
        key = set(row_keys(old, ["ticker", "date"]))
        rows = rows[~row_keys(rows, ["ticker", "date"]).isin(key)]
        if rows.empty:
            return path
        rows = pd.concat([old, rows], ignore_index=True)
    return write_parquet(rows, path)


def stored_files(data_dir: Path) -> list[Path]:
    return sorted(history_dir(data_dir).glob("*.parquet")) + sorted(
        daily_dir(data_dir).glob("*/*.parquet")
    )


def load_rows(data_dir: Path, tickers: Iterable[str] | None = None) -> pd.DataFrame:
    files = stored_files(data_dir)
    if not files:
        return pd.DataFrame(columns=ROW_COLS)
    wanted = set(tickers) if tickers is not None else None
    frames = []
    for f in files:
        df = pd.read_parquet(f, filters=[("ticker", "in", sorted(wanted))] if wanted else None)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=ROW_COLS)
    rows = pd.concat(frames, ignore_index=True)
    rows["ticker"] = rows["ticker"].astype(str)
    return rows


# --------------------------------------------------------------------------- panel


@dataclass
class Panel:
    """Wide matrices (dates x tickers) of split-consistent prices."""

    open: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame
    dividend: pd.DataFrame
    tr: pd.DataFrame  # total-return index (dividends reinvested), 1.0 at each ticker's first day
    split_events: pd.DataFrame

    @property
    def dates(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(self.close.index)

    @property
    def last_date(self) -> pd.Timestamp | None:
        return self.close.index.max() if len(self.close.index) else None

    def last_valid(self) -> pd.DataFrame:
        """Per ticker: last date with a close and that close."""
        idx = self.close.apply(lambda s: s.last_valid_index())
        vals = pd.Series(
            {
                t: self.close.at[d, t] if d is not None and not pd.isna(d) else np.nan
                for t, d in idx.items()
            }
        )
        return pd.DataFrame({"last_date": idx, "last_close": vals})


def split_events(rows: pd.DataFrame) -> pd.DataFrame:
    ev = rows.loc[
        (rows["split"] > 0) & (np.abs(rows["split"] - 1.0) > 1e-6), ["ticker", "date", "split"]
    ]
    return (
        ev.drop_duplicates(["ticker", "date"])
        .rename(columns={"split": "ratio"})
        .reset_index(drop=True)
    )


def adjustment_factors(rows: pd.DataFrame, events: pd.DataFrame) -> pd.Series:
    """Factor per row: product of split ratios with ex-date after the row's basis day."""
    factor = pd.Series(1.0, index=rows.index)
    if events.empty:
        return factor
    keys = rows[["ticker", "basis"]].drop_duplicates()
    merged = keys.merge(events, on="ticker", how="inner")
    merged = merged[merged["date"] > merged["basis"]]
    if merged.empty:
        return factor
    per_key = merged.groupby(["ticker", "basis"])["ratio"].prod()
    idx = pd.MultiIndex.from_frame(rows[["ticker", "basis"]])
    mapped = per_key.reindex(idx).to_numpy()
    return pd.Series(np.where(np.isnan(mapped), 1.0, mapped), index=rows.index)


def build_panel(rows: pd.DataFrame) -> Panel:
    if rows.empty:
        empty = pd.DataFrame()
        return Panel(
            empty,
            empty,
            empty,
            empty,
            empty,
            empty,
            empty,
            pd.DataFrame(columns=["ticker", "date", "ratio"]),
        )
    rows = rows.reset_index(drop=True)
    rows["date"] = pd.to_datetime(rows["date"])
    rows["basis"] = pd.to_datetime(rows["basis"])
    # Index quotes (e.g. ^VIX) sometimes exist on NYSE holidays; keep NYSE sessions only.
    uniq = rows["date"].unique()
    sessions = pd.DatetimeIndex([d for d in uniq if is_trading_day(pd.Timestamp(d).date())])
    rows = rows[rows["date"].isin(sessions)].reset_index(drop=True)
    events = split_events(rows)
    factor = adjustment_factors(rows, events).to_numpy(dtype="float64")

    # Integer coordinates instead of pivots: much faster on ~15M rows.
    d_codes, dates = pd.factorize(rows["date"], sort=True)
    t_codes, tickers = pd.factorize(rows["ticker"], sort=True)
    n_d, n_t = len(dates), len(tickers)
    # Latest download wins for duplicate (ticker, date): keep the row with the greatest basis.
    key = d_codes.astype("int64") * n_t + t_codes
    order = np.lexsort((rows["basis"].to_numpy(), key))
    key_sorted = key[order]
    last = np.r_[key_sorted[1:] != key_sorted[:-1], True]
    keep = order[last]
    di, ti = d_codes[keep], t_codes[keep]
    f = factor[keep]

    def mat(values: np.ndarray, dtype: str, scale: str | None) -> pd.DataFrame:
        v = values[keep].astype("float64")
        if scale == "div":
            v = v / f
        elif scale == "mul":
            v = v * f
        out = np.full((n_d, n_t), np.nan, dtype="float64")
        out[di, ti] = v
        return pd.DataFrame(
            out.astype(dtype),
            index=pd.DatetimeIndex(dates, name="date"),
            columns=pd.Index(tickers, name="ticker"),
        )

    close = mat(rows["close"].to_numpy(), "float64", "div")
    dividend = mat(rows["dividend"].to_numpy(), "float64", "div")
    # Total return vs the last known close, so a day missing for one ticker doesn't drop its move.
    prev = close.ffill().shift(1)
    ret = ((close + dividend.fillna(0.0)) / prev - 1.0).where(close.notna() & prev.notna())
    # Starts at 1.0 on each ticker's first day (leading returns are NaN -> 0).
    tr = (1.0 + ret.fillna(0.0)).cumprod().where(close.notna())
    return Panel(
        open=mat(rows["open"].to_numpy(), "float32", "div"),
        high=mat(rows["high"].to_numpy(), "float32", "div"),
        low=mat(rows["low"].to_numpy(), "float32", "div"),
        close=close.astype("float32"),
        volume=mat(rows["volume"].to_numpy(), "float64", "mul"),
        dividend=dividend.astype("float32"),
        tr=tr,
        split_events=events,
    )


# --------------------------------------------------------------------------- daily update


@dataclass
class UpdateReport:
    requested: int
    new_rows: int
    new_listings: int
    repaired: int
    missing: list[str]
    last_session: date


def plan_update(
    panel: Panel, tickers: Sequence[str], today: date, max_gap_days: int = 12
) -> tuple[list[str], list[str]]:
    """Split tickers into (incremental, full-history) download lists."""
    if panel.close.empty:
        return [], list(tickers)
    lv = panel.last_valid()
    incremental, full = [], []
    for t in tickers:
        last = lv["last_date"].get(t)
        if (
            last is None
            or pd.isna(last)
            or (pd.Timestamp(today) - pd.Timestamp(last)).days > max_gap_days
        ):
            full.append(t)
        else:
            incremental.append(t)
    return incremental, full


def unexplained_adjustments(
    panel: Panel, fresh: pd.DataFrame, tolerance: float = 0.02
) -> list[str]:
    """Tickers whose freshly downloaded history disagrees with what we stored (missed corporate
    action or Yahoo revision). Those get a full re-download."""
    if panel.close.empty or fresh.empty:
        return []
    lv = panel.last_valid()
    bad = []
    for t, grp in fresh.groupby("ticker"):
        last = lv["last_date"].get(t)
        if last is None or pd.isna(last):
            continue
        same = grp[grp["date"] == pd.Timestamp(last)]
        if same.empty:
            continue
        later_splits = grp.loc[
            (grp["date"] > pd.Timestamp(last))
            & (grp["split"] > 0)
            & (np.abs(grp["split"] - 1) > 1e-6),
            "split",
        ]
        expected = 1.0 / float(np.prod(later_splits)) if len(later_splits) else 1.0
        ratio = float(same["close"].iloc[0]) / float(lv["last_close"][t])
        if abs(ratio / expected - 1.0) > tolerance:
            bad.append(str(t))
    return bad


RETRIES = 2
RETRY_PAUSE = 60.0
RETRY_MIN_SHARE = 0.05  # retry only when more than 5% of stocks lack the latest session


def update(
    data_dir: Path,
    panel: Panel,
    tickers: Sequence[str],
    now: datetime,
    lookback_days: int = 14,
    suffix: str = "",
) -> UpdateReport:
    """Download what is new since the last run and store it append-only."""
    today = now.astimezone(NEW_YORK).date()
    session = last_completed_session(now)
    incremental, full = plan_update(panel, tickers, today)
    log.info("prices: %d incremental, %d full-history downloads", len(incremental), len(full))

    repaired: list[str] = []
    new_rows = 0
    got: set[str] = set()
    if incremental:
        fresh = finalize_rows(download(incremental, today - timedelta(days=lookback_days)), now)
        # Yahoo sometimes serves the latest session for only part of the stocks (seen on
        # 15 Oct 2026: 45%). Ask again for the stocks without it, after a pause.
        for attempt in range(RETRIES):
            have = fresh.groupby("ticker")["date"].max() if not fresh.empty else pd.Series(dtype="datetime64[ns]")  # fmt: skip
            behind = [
                t for t in incremental if have.get(t, pd.Timestamp.min) < pd.Timestamp(session)
            ]
            if len(behind) <= RETRY_MIN_SHARE * len(incremental):
                break
            log.warning("prices: %d of %d stocks lack %s; asking again (%d)", len(behind), len(incremental), session, attempt + 1)  # fmt: skip
            time.sleep(RETRY_PAUSE)
            again = finalize_rows(download(behind, today - timedelta(days=lookback_days), batch_size=60), now)  # fmt: skip
            if not again.empty:
                fresh = pd.concat([fresh[~fresh["ticker"].isin(set(again["ticker"]))], again], ignore_index=True)  # fmt: skip
        repaired = unexplained_adjustments(panel, fresh)
        lv = panel.last_valid()
        last_dates = fresh["ticker"].map(lv["last_date"])
        new = fresh[(fresh["date"] > last_dates) & ~fresh["ticker"].isin(repaired)]
        write_daily(data_dir, new, today, suffix)
        new_rows += len(new)
        got |= set(fresh["ticker"].unique())
    to_full = full + repaired
    if to_full:
        hist = finalize_rows(download(to_full, HISTORY_START), now)
        write_history_chunk(
            data_dir, hist, today, ("repair" if repaired and not full else "new") + suffix
        )
        new_rows += len(hist)
        got |= set(hist["ticker"].unique())
    # Tickers with no bar in the lookback window (halted, delisted, or Yahoo has no data).
    missing = sorted(set(tickers) - got)
    if repaired:
        log.info("prices: re-downloaded %d tickers after unexplained adjustments", len(repaired))
    return UpdateReport(len(tickers), new_rows, len(full), len(repaired), missing, session)


def backfill(data_dir: Path, tickers: Sequence[str], now: datetime, label: str) -> int:
    rows = finalize_rows(download(tickers, HISTORY_START, batch_size=100), now)
    write_history_chunk(data_dir, rows, now.astimezone(NEW_YORK).date(), label)
    got = rows["ticker"].nunique() if not rows.empty else 0
    logging.getLogger(__name__).info(
        "backfill %s: %d rows for %d/%d tickers", label, len(rows), got, len(tickers)
    )
    return got
