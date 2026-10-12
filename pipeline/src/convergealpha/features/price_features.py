"""Per-stock price statistics for one date: returns, volatility, ATR, trend, 52-week range,
liquidity, gap stress. Everything uses only data up to and including that date."""

from __future__ import annotations

import numpy as np
import pandas as pd

from convergealpha.config import MIN_ADV_DOLLARS, MIN_PRICE
from convergealpha.sources.prices import Panel

TRADING_DAYS = 252


def _ret(tr: pd.DataFrame, n: int) -> pd.Series:
    if len(tr) <= n:
        return pd.Series(np.nan, index=tr.columns)
    return tr.iloc[-1] / tr.iloc[-1 - n] - 1.0


def wilder_atr(
    high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, n: int = 14
) -> pd.DataFrame:
    prev = close.ffill().shift(1)
    rng = np.fmax(
        np.fmax((high - low).to_numpy(), (high - prev).abs().to_numpy()),
        (low - prev).abs().to_numpy(),
    )
    true_range = pd.DataFrame(rng, index=close.index, columns=close.columns)
    return true_range.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def snapshot(panel: Panel, as_of: pd.Timestamp | None = None, window: int = 520) -> pd.DataFrame:
    """Statistics per ticker at `as_of` (default: last date in the panel)."""
    if panel.close.empty:
        return pd.DataFrame()
    as_of = pd.Timestamp(as_of) if as_of is not None else panel.close.index.max()
    sl = slice(None, as_of)
    close = panel.close.loc[sl].tail(window).astype("float64")
    high = panel.high.loc[sl].tail(window).astype("float64")
    low = panel.low.loc[sl].tail(window).astype("float64")
    open_ = panel.open.loc[sl].tail(window).astype("float64")
    vol = panel.volume.loc[sl].tail(window).astype("float64")
    tr = panel.tr.loc[sl].tail(window).ffill()

    last_date = close.apply(lambda s: s.last_valid_index())
    px = close.ffill().iloc[-1]
    daily = np.log(tr / tr.shift(1))

    out = pd.DataFrame(index=close.columns)
    out["price"] = px
    out["last_date"] = last_date
    out["change_1d"] = _ret(tr, 1)
    out["ret_1w"] = _ret(tr, 5)
    out["ret_1m"] = _ret(tr, 21)
    out["ret_3m"] = _ret(tr, 63)
    out["ret_6m"] = _ret(tr, 126)
    out["ret_1y"] = _ret(tr, 252)
    prev_year = tr.loc[tr.index.year < as_of.year]
    out["ret_ytd"] = tr.iloc[-1] / prev_year.iloc[-1] - 1.0 if len(prev_year) else np.nan
    out["vol_21"] = daily.tail(21).std() * np.sqrt(TRADING_DAYS)
    out["vol_63"] = daily.tail(63).std() * np.sqrt(TRADING_DAYS)
    out["vol_252"] = daily.tail(252).std() * np.sqrt(TRADING_DAYS)
    atr = wilder_atr(high, low, close).iloc[-1]
    out["atr14"] = atr
    out["atr_pct"] = atr / px
    out["sma50"] = close.tail(50).mean()
    out["sma200"] = close.tail(200).mean()
    enough200 = close.tail(200).count() >= 180  # tolerate a few missing bars
    out["trend_up"] = ((px > out["sma50"]) & (out["sma50"] > out["sma200"])).where(enough200)
    out["high_52w"] = high.tail(TRADING_DAYS).max()
    out["low_52w"] = low.tail(TRADING_DAYS).min()
    out["dist_52w_high"] = px / out["high_52w"] - 1.0
    dollar = close * vol
    out["adv_dollar"] = dollar.tail(21).mean()
    out["adv_shares"] = vol.tail(21).mean()
    overnight = (open_ / close.ffill().shift(1) - 1.0).tail(500)
    q = overnight.quantile(0.02)
    worst = overnight.where(overnight.le(q, axis=1))
    out["gap_stress_pct"] = worst.mean().abs()
    roll_max = tr.tail(TRADING_DAYS).cummax()
    out["max_dd_1y"] = (tr.tail(TRADING_DAYS) / roll_max - 1.0).min()
    out["history_days"] = panel.close.loc[sl].count()
    fresh = out["last_date"] == close.index.max()
    out["eligible"] = fresh & (out["price"] >= MIN_PRICE) & (out["adv_dollar"] >= MIN_ADV_DOLLARS)
    out.index.name = "ticker"
    return out


def chart_series(
    panel: Panel, ticker: str, daily_sessions: int = 260, weekly_years: int = 10
) -> dict[str, object]:
    """Compact columnar arrays for the stock page chart."""
    if ticker not in panel.close.columns:
        return {}
    c = panel.close[ticker].dropna()
    if c.empty:
        return {}
    idx = c.index[-daily_sessions:]

    def arr(df: pd.DataFrame) -> list[float | None]:
        return [None if pd.isna(v) else _px(float(v)) for v in df[ticker].reindex(idx).to_numpy()]

    weekly = panel.close[ticker].dropna().resample("W-FRI").last().dropna()
    weekly = weekly[weekly.index >= weekly.index.max() - pd.DateOffset(years=weekly_years)]
    return {
        "daily": {
            "t": [d.strftime("%Y-%m-%d") for d in idx],
            "o": arr(panel.open),
            "h": arr(panel.high),
            "l": arr(panel.low),
            "c": arr(panel.close),
            "v": [
                None if pd.isna(v) else int(v) for v in panel.volume[ticker].reindex(idx).to_numpy()
            ],
        },
        "weekly": {
            "t": [d.strftime("%Y-%m-%d") for d in weekly.index],
            "c": [_px(float(v)) for v in weekly.to_numpy()],
        },
    }


def _px(v: float) -> float:
    return round(v, 4) if abs(v) < 10 else round(v, 2)
