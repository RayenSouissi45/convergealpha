// Trading costs in euros at finanzen.net zero (orders go to gettex). Mirrors
// pipeline/src/convergealpha/decide/costs.py; both are tested with the same reference values
// (100 € in -> 99 € of stock; the stock must rise 2.02% just to get 100 € back).

export interface Fees {
  /** Euros per buy order. */
  buy: number
  /** Euros per sell order. */
  sell: number
  /** Simulation only: real orders at this broker are whole shares. */
  fractional: boolean
  /** Orders worth at least this many euros pay no fee (finanzen.net zero: 500). */
  freeFrom?: number | null
}

/** A flat 1 € each way: the rule the first paper strategies were started with. */
export const DEFAULT_FEES: Fees = { buy: 1, sell: 1, fractional: false }

/** finanzen.net zero (checked 14 Oct 2026): 0 € for orders of 500 € or more, 1 € below. */
export const ZERO_FEES: Fees = { buy: 1, sell: 1, fractional: false, freeFrom: 500 }
export const ZERO_FEES_CHECKED = '2026-10-14'

/** The fee for an order worth `volume` euros. */
export function feeFor(fee: number, volume: number, fees: Fees): number {
  return fees.freeFrom !== null && fees.freeFrom !== undefined && volume >= fees.freeFrom ? 0 : fee
}

/** The sell fee: a number, or the broker's rule applied to the sale's value. */
function sellFee(sell: number | Fees, volume: number): number {
  return typeof sell === 'number' ? sell : feeFor(sell.sell, volume, sell)
}

export interface Buy {
  amount: number
  /** 0 = one share costs more than the amount: nothing is bought, no fee is paid. */
  shares: number
  /** Price per share in euros before the spread. */
  midEur: number
  /** Price per share paid: the mid price plus half the spread. */
  payEur: number
  fee: number
  invested: number
  /** Money left over, kept as cash. */
  leftover: number
  /** Euros lost to the spread on the way in. */
  spreadCost: number
  /** invested + fee */
  spent: number
}

export function toEur(usd: number, fxUsdPerEur: number): number {
  return usd / fxUsdPerEur
}

/** Buy as many shares as `amount` euros allow after the buy fee (none when the order is big
 * enough to be free at this broker). */
export function buy(amount: number, priceUsd: number, fxUsdPerEur: number, spread: number, fees: Fees = DEFAULT_FEES): Buy {
  const mid = toEur(priceUsd, fxUsdPerEur)
  const pay = mid * (1 + spread / 2)
  const none: Buy = { amount, shares: 0, midEur: mid, payEur: pay, fee: 0, invested: 0, leftover: amount, spreadCost: 0, spent: 0 }
  if (!(amount > 0) || !(pay > 0)) return none
  const count = (budget: number) => (fees.fractional ? budget / pay : Math.floor(budget / pay + 1e-9))
  // Without a fee the order may be big enough to be free; otherwise the fee comes off first.
  const free = count(amount)
  const isFree = feeFor(fees.buy, free * pay, fees) === 0 && free > 0
  const fee = isFree ? 0 : fees.buy
  const shares = isFree ? free : count(amount - fee)
  if (!(amount - fee > 0) || shares <= 0) return none
  const invested = shares * pay
  return {
    amount,
    shares,
    midEur: mid,
    payEur: pay,
    fee,
    invested,
    leftover: amount - invested - fee,
    spreadCost: shares * (pay - mid),
    spent: invested + fee,
  }
}

/** How much the stock must rise (vs the mid price at purchase) just to get the money spent back.
 * `sell` = the sell fee in euros, or the broker's fees (the rule applied to the sale's value). */
export function breakEven(b: Buy, spread: number, sell: number | Fees): number {
  if (b.shares <= 0) return NaN
  const needMid = (b.spent + sellFee(sell, b.spent)) / (b.shares * (1 - spread / 2))
  return needMid / b.midEur - 1
}

/** Profit or loss in euros on the money spent if the stock moves by `move` (euro rate unchanged). */
export function result(b: Buy, move: number, spread: number, sell: number | Fees): number {
  if (b.shares <= 0) return 0
  const value = b.shares * b.midEur * (1 + move) * (1 - spread / 2)
  return value - sellFee(sell, value) - b.spent
}

/** The sell fee for selling this purchase at about its cost. */
export function sellFeeFor(b: Buy, sell: number | Fees): number {
  return b.shares > 0 ? sellFee(sell, b.invested) : 0
}

/** Fees and spread for buying and later selling, in euros. */
export function roundTripEuros(b: Buy, spread: number, sell: number | Fees): number {
  if (b.shares <= 0) return 0
  return b.fee + sellFeeFor(b, sell) + b.spreadCost + b.shares * b.midEur * (spread / 2)
}

export function formatEur(v: number, digits = 2): string {
  const s = Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
  return `${v < 0 ? '−' : ''}€${s}`
}

/** Signed euros: "+€3.20", "−€1.05". */
export function formatEurSigned(v: number, digits = 2): string {
  if (Math.abs(v) < 0.005) return formatEur(0, digits)
  return `${v > 0 ? '+' : ''}${formatEur(v, digits)}`
}

export function formatShares(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(4)
}
