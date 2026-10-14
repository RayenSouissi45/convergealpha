"""Shared trading-cost model for euro amounts at finanzen.net zero (orders go to gettex).

Used by the paper-trading strategies and exported to the website (Plan builder, "Give me a
strategy"), which mirrors these formulas in web/src/lib/costs.ts (both are tested with the same
reference values).

- Fee per order: FEE_BUY_EUR on a buy, FEE_SELL_EUR on a sell (the site lets you change it;
  check your broker's current price list).
- Spread: the existing liquidity estimate (decide/rules.spread_estimate). Half of it is paid on
  the way in, half on the way out.
- Currency: US prices are converted with the daily EUR/USD rate from FRED (DEXUSEU, US dollars
  per euro). FRED publishes it about once a week, so the latest rate can be a few days old.
- Whole shares by default; leftover money stays as cash. Fractional shares are a simulation only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from convergealpha.decide.rules import spread_estimate

FEE_BUY_EUR = 1.0
FEE_SELL_EUR = 1.0
# US dividends paid to an EU resident are taxed 15% at the source (treaty rate with a W-8BEN form).
DIVIDEND_WITHHOLDING = 0.15
FX_SERIES = "DEXUSEU"


@dataclass(frozen=True)
class Fees:
    buy: float = FEE_BUY_EUR
    sell: float = FEE_SELL_EUR
    fractional: bool = False
    free_from: float | None = None  # orders worth at least this many euros pay no fee


DEFAULT_FEES = Fees()  # a flat 1 € each way: the rule the first paper strategies started with
ZERO_FEE_FREE_FROM = 500.0  # finanzen.net zero, checked 2026-10-14: 0 € from 500 €, 1 € below
ZERO_FEES = Fees(free_from=ZERO_FEE_FREE_FROM)


def fee_for(fee: float, volume_eur: float, fees: Fees) -> float:
    """The fee for an order worth `volume_eur` euros under this broker's rule."""
    return 0.0 if fees.free_from is not None and volume_eur >= fees.free_from else fee


@dataclass(frozen=True)
class Buy:
    """A purchase of `amount` euros: what you get and what it costs."""

    amount: float  # euros you set aside
    shares: float  # 0 = cannot afford one share (nothing is bought, no fee is paid)
    mid_eur: float  # price per share in euros before the spread
    pay_eur: float  # price per share paid (mid + half the spread)
    fee: float
    invested: float  # shares x pay_eur
    leftover: float  # amount - invested - fee (stays as cash)
    spread_cost: float  # euros lost to the spread on the way in

    @property
    def spent(self) -> float:
        return self.invested + self.fee


def spread(adv_dollar: float | None) -> float:
    """Quoted spread (fraction of the price) estimated from average daily traded value."""
    return spread_estimate(float(adv_dollar) if adv_dollar is not None else math.nan)


def to_eur(usd: float, fx_usd_per_eur: float) -> float:
    return usd / fx_usd_per_eur


def buy(
    amount: float,
    price_usd: float,
    fx_usd_per_eur: float,
    spread_frac: float,
    fees: Fees = DEFAULT_FEES,
) -> Buy:
    """Buy as many shares as `amount` euros allow after the buy fee (none when the order is big
    enough to be free at this broker)."""
    mid = to_eur(price_usd, fx_usd_per_eur)
    pay = mid * (1 + spread_frac / 2)
    none = Buy(amount, 0.0, mid, pay, 0.0, 0.0, amount, 0.0)
    if amount <= 0 or not (pay > 0):
        return none

    def count(budget: float) -> float:
        return budget / pay if fees.fractional else math.floor(budget / pay + 1e-9)

    free = count(amount)
    is_free = free > 0 and fee_for(fees.buy, free * pay, fees) == 0.0
    fee = 0.0 if is_free else fees.buy
    shares = free if is_free else count(amount - fee)
    if amount - fee <= 0 or shares <= 0:
        return none
    invested = shares * pay
    return Buy(
        amount=amount,
        shares=shares,
        mid_eur=mid,
        pay_eur=pay,
        fee=fee,
        invested=invested,
        leftover=amount - invested - fee,
        spread_cost=shares * (pay - mid),
    )


def sell_value(shares: float, price_usd: float, fx_usd_per_eur: float, spread_frac: float, fee: float) -> float:  # fmt: skip
    """Euros received for selling `shares` (half the spread and the sell fee taken off)."""
    return shares * to_eur(price_usd, fx_usd_per_eur) * (1 - spread_frac / 2) - fee


def break_even(b: Buy, spread_frac: float, fee_sell: float) -> float:
    """How much the stock must rise (vs the mid price at purchase) just to get the money spent
    back after selling: the spread both ways and both fees. NaN if nothing was bought."""
    if b.shares <= 0:
        return math.nan
    need_mid = (b.spent + fee_sell) / (b.shares * (1 - spread_frac / 2))
    return need_mid / b.mid_eur - 1


def result(b: Buy, move: float, spread_frac: float, fee_sell: float) -> float:
    """Profit or loss in euros on the money spent if the stock moves by `move` (euro rate unchanged)."""
    if b.shares <= 0:
        return 0.0
    return b.shares * b.mid_eur * (1 + move) * (1 - spread_frac / 2) - fee_sell - b.spent


def round_trip_cost(value_eur: float, spread_frac: float, fees: Fees = DEFAULT_FEES) -> float:
    """Cost of buying and later selling a position worth `value_eur`, as a fraction of it."""
    if value_eur <= 0:
        return math.inf
    return (
        fee_for(fees.buy, value_eur, fees) + fee_for(fees.sell, value_eur, fees)
    ) / value_eur + spread_frac


def switch_cost(value_eur: float, spread_out: float, spread_in: float, fees: Fees = DEFAULT_FEES) -> float:  # fmt: skip
    """Selling one position and buying another of the same size: both fees and both half-spreads,
    as a fraction of the position."""
    if value_eur <= 0:
        return math.inf
    both = fee_for(fees.sell, value_eur, fees) + fee_for(fees.buy, value_eur, fees)
    return both / value_eur + spread_out / 2 + spread_in / 2


def fx_series(fred: pd.DataFrame) -> pd.Series:
    """DEXUSEU (US dollars per euro) by date, from the FRED table (load_fred)."""
    if fred is None or fred.empty or FX_SERIES not in fred:
        return pd.Series(dtype=float)
    return fred[FX_SERIES].dropna().astype(float).sort_index()


def fx_on(series: pd.Series, day: pd.Timestamp) -> tuple[float, str] | None:
    """The latest published rate dated on or before `day`: (rate, its date)."""
    if series.empty:
        return None
    s = series[series.index <= pd.Timestamp(day)]
    if s.empty:
        return None
    return float(s.iloc[-1]), s.index[-1].strftime("%Y-%m-%d")
