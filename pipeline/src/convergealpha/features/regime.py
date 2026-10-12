"""Market regime (spec section 6).

Normal  = S&P 500 above its 200-day average and VIX < 25.
Stress  = S&P 500 below its 200-day average and VIX >= 30 -> no new buys.
Caution = anything else, or the high-yield spread is up more than 1 point over 3 months.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def regime_series(spx: pd.Series, vix: pd.Series, hy: pd.Series | None) -> pd.DataFrame:
    """Daily regime from the S&P 500 index, VIX and the high-yield spread (all point-in-time)."""
    df = pd.DataFrame({"spx": spx}).dropna()
    df["sma200"] = df["spx"].rolling(200, min_periods=200).mean()
    df["vix"] = vix.reindex(df.index).ffill()
    if hy is not None and not hy.empty:
        h = hy.reindex(df.index).ffill()
        df["hy"] = h
        df["hy_change_3m"] = h - h.shift(63)
    else:
        df["hy"] = np.nan
        df["hy_change_3m"] = np.nan
    above = df["spx"] > df["sma200"]
    state = np.where(above & (df["vix"] < 25) & ~(df["hy_change_3m"] > 1.0), "Normal", "Caution")
    state = np.where(~above & (df["vix"] >= 30), "Stress", state)
    df["state"] = pd.Series(state, index=df.index).where(df["sma200"].notna() & df["vix"].notna())
    return df


def describe(row: pd.Series) -> dict[str, Any]:
    reasons = []
    above = row["spx"] > row["sma200"]
    reasons.append(
        f"S&P 500 {'above' if above else 'below'} its 200-day average ({(row['spx'] / row['sma200'] - 1) * 100:+.1f}%)"
    )
    reasons.append(f"VIX {row['vix']:.1f}")
    if pd.notna(row.get("hy_change_3m")):
        reasons.append(
            f"high-yield spread {row['hy']:.2f} ({row['hy_change_3m']:+.2f} points over 3 months)"
        )
    return {
        "state": row["state"],
        "reasons": reasons,
        "spx": float(row["spx"]),
        "sma200": float(row["sma200"]),
        "vix": float(row["vix"]),
        "hy_spread": None if pd.isna(row.get("hy")) else float(row["hy"]),
        "hy_change_3m": None if pd.isna(row.get("hy_change_3m")) else float(row["hy_change_3m"]),
    }
