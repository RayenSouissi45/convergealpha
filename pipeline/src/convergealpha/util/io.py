"""File helpers: Parquet for data, compact JSON for the website."""

from __future__ import annotations

import json
import math
import os
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}  # fmt: skip


def stock_file_stem(ticker: str) -> str:
    """File name for a ticker's JSON. Windows cannot create CON.json etc., so those get a '_'.

    The website uses the same rule (web/src/lib/data.ts: stockFile).
    """
    return f"{ticker}_" if ticker.upper() in WINDOWS_RESERVED else ticker


def write_parquet(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False, compression="zstd")
    os.replace(tmp, path)
    return path


def read_parquets(paths: Iterable[Path], columns: list[str] | None = None) -> pd.DataFrame:
    frames = [pd.read_parquet(p, columns=columns) for p in paths]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=columns or [])
    return pd.concat(frames, ignore_index=True)


def _clean(value: Any, digits: int) -> Any:
    """Make a value JSON-safe: NaN/inf -> None, numpy -> python, round floats."""
    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        f = float(value)
        if not math.isfinite(f):
            return None
        return round(f, digits)
    if isinstance(value, (pd.Timestamp, datetime)):
        if pd.isna(value):
            return None
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _clean(v, digits) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v, digits) for v in value]
    if isinstance(value, np.ndarray):
        return [_clean(v, digits) for v in value.tolist()]
    if value is pd.NA or value is pd.NaT:
        return None
    return value


def to_jsonable(obj: Any, digits: int = 6) -> Any:
    return _clean(obj, digits)


def write_json(obj: Any, path: Path, *, digits: int = 6, pretty: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        to_jsonable(obj, digits),
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))
