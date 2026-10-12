"""Website JSON: screener.json (one compact row per stock), stocks/<TICKER>.json, market.json.

The screener is columnar: `fields` lists the column keys once and each row is an array in that
order, which keeps 5,000+ rows small. Missing values are null and render as "—".
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from convergealpha.util.io import stock_file_stem, to_jsonable, write_json

SCHEMA_VERSION = 1

# (key, digits). Digits round floats; None keeps the value as is.
_DIGITS: dict[str, int] = {
    "price": 4,
    "adv_dollar": 0,
    "market_cap": 0,
}
_DEFAULT_DIGITS = 4


def _round(key: str, v: Any) -> Any:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return None
    if isinstance(v, (float, np.floating)):
        d = _DIGITS.get(key, _DEFAULT_DIGITS)
        f = float(v)
        if key == "price":
            return round(f, 4) if abs(f) < 10 else round(f, 2)
        return round(f, d) if d else round(f)
    if isinstance(v, (pd.Timestamp, datetime)):
        return None if pd.isna(v) else v.strftime("%Y-%m-%d")
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if v is pd.NA or (not isinstance(v, (str, list, dict)) and pd.isna(v)):
        return None
    return v


def write_screener(
    site_dir: Path, table: pd.DataFrame, fields: Sequence[str], as_of: str, now: datetime
) -> Path:
    """`table` is indexed by ticker and holds at least the requested fields."""
    present = [f for f in fields if f in table.columns or f == "ticker"]
    rows = []
    for ticker, rec in table.iterrows():
        row = []
        for f in present:
            row.append(ticker if f == "ticker" else _round(f, rec[f]))
        rows.append(row)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "as_of": as_of,
        "generated_at": now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "count": len(rows),
        "fields": present,
        "rows": rows,
    }
    return write_json(payload, site_dir / "screener.json")


def reset_stock_dir(site_dir: Path) -> Path:
    d = site_dir / "stocks"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    return d


def write_stock(site_dir: Path, ticker: str, payload: Mapping[str, Any]) -> Path:
    return write_json(
        dict(payload), site_dir / "stocks" / f"{stock_file_stem(ticker)}.json", digits=6
    )


def record_from(row: pd.Series, keys: Sequence[str]) -> dict[str, Any]:
    return {k: _round(k, row[k]) if k in row.index else None for k in keys}


def write_market(site_dir: Path, market: Mapping[str, Any]) -> Path:
    return write_json(to_jsonable(dict(market)), site_dir / "market.json", pretty=True)


def write_json_file(site_dir: Path, name: str, payload: Any) -> Path:
    return write_json(to_jsonable(payload), site_dir / name)
