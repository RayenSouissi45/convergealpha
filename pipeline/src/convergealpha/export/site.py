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

# (key, digits). Digits round floats. Probabilities keep 4 digits (the reliability lookup uses
# the same rounded value on both sides); returns shown with one decimal of a percent need 3.
_DIGITS: dict[str, int] = {
    "price": 4,
    "adv_dollar": 0,
    "market_cap": 0,
    "insider_net_90d": 0,
    "insider_buy_7d": 0,
    **{f"f{i}": 1 for i in range(1, 7)},
    "n_eff": 2,
    "disagreement": 1,
    "consensus": 2,
    "days_to_cover": 2,
    **{f"{k}_{h}": 3 for k in ("med", "p10", "p90", "hit_up") for h in ("1w", "1m", "3m", "6m")},
    **{k: 3 for k in ("gain_per_month", "speed", "target_upside", "rev60", "vol_63", "atr_pct")},
    **{k: 3 for k in ("short_pct_float", "iv_30d", "dist_52w_high", "change_1d")},
    **{k: 3 for k in ("ret_1w", "ret_1m", "ret_3m", "ret_ytd", "ret_1y")},
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
    site_dir: Path,
    table: pd.DataFrame,
    fields: Sequence[str],
    as_of: str,
    now: datetime,
    name: str = "screener.json",
    meta: Mapping[str, Any] | None = None,
) -> Path:
    """`table` is indexed by ticker and holds at least the requested fields.

    `meta` adds file-level keys (e.g. the reliability tables and the broker list summary).
    """
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
        **to_jsonable(dict(meta or {})),
    }
    return write_json(payload, site_dir / name)


TODAY_TOP = 20  # per list; the Today page shows at most 12


def today_subset(t: pd.DataFrame) -> pd.DataFrame:
    """Rows any list on the Today page can show, for today.json.

    The page ranks these rows exactly as it would the full screener, and every list takes at most
    TODAY_TOP rows, so the result is identical while phones download a few KB instead of ~1 MB.
    """
    idx = t.index
    elig = (
        t["eligible"].eq(True).fillna(False).astype(bool)
        if "eligible" in t
        else pd.Series(False, index=idx)
    )
    label = t["label"].astype("string") if "label" in t else pd.Series("", index=idx)
    keep = elig & label.isin(["STRONG BUY — TOP CONVICTION", "BUY", "WATCH"]).fillna(False)

    def num(key: str) -> pd.Series:
        return pd.to_numeric(t[key], errors="coerce") if key in t else pd.Series(np.nan, index=idx)

    for key in ("p_up_6m", "p90_6m", "speed"):
        keep |= idx.isin(num(key)[elig].dropna().nlargest(TODAY_TOP).index)
    ins = num("insider_buy_7d")
    keep |= idx.isin(ins[ins > 0].nlargest(TODAY_TOP).index)
    days = num("days_to_earnings")
    soon = pd.DataFrame({"d": days, "adv": -num("adv_dollar").fillna(0)})[elig & days.between(0, 5)]
    keep |= idx.isin(soon.sort_values(["d", "adv"]).head(TODAY_TOP).index)
    return t[keep]


def write_intraday_placeholder(site_dir: Path) -> None:
    """The intraday check overwrites this during market hours; the page hides it when stale."""
    path = site_dir / "intraday.json"
    if not path.exists():
        write_json({"generated_at": None, "checked": 0, "alerts": []}, path)


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
