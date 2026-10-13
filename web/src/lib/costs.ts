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
}

export const DEFAULT_FEES: Fees = { buy: 1, sell: 1, fractional: false }

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

/** Buy as many shares as `amount` euros allow after the buy fee. */
export function buy(amount: number, priceUsd: number, fxUsdPerEur: number, spread: number, fees: Fees = DEFAULT_FEES): Buy {
  const mid = toEur(priceUsd, fxUsdPerEur)
  const pay = mid * (1 + spread / 2)
  const budget = amount - fees.buy
  const none: Buy = { amount, shares: 0, midEur: mid, payEur: pay, fee: 0, invested: 0, leftover: amount, spreadCost: 0, spent: 0 }
  if (!(budget > 0) || !(pay > 0)) return none
  const shares = fees.fractional ? budget / pay : Math.floor(budget / pay + 1e-9)
  if (shares <= 0) return none
  const invested = shares * pay
  return {
    amount,
    shares,
    midEur: mid,
    payEur: pay,
    fee: fees.buy,
    invested,
    leftover: amount - invested - fees.buy,
    spreadCost: shares * (pay - mid),
    spent: invested + fees.buy,
  }
}

/** How much the stock must rise (vs the mid price at purchase) just to get the money spent back. */
export function breakEven(b: Buy, spread: number, feeSell: number): number {
  if (b.shares <= 0) return NaN
  const needMid = (b.spent + feeSell) / (b.shares * (1 - spread / 2))
  return needMid / b.midEur - 1
}

/** Profit or loss in euros on the money spent if the stock moves by `move` (euro rate unchanged). */
export function result(b: Buy, move: number, spread: number, feeSell: number): number {
  if (b.shares <= 0) return 0
  return b.shares * b.midEur * (1 + move) * (1 - spread / 2) - feeSell - b.spent
}

/** Fees and spread for buying and later selling, in euros. */
export function roundTripEuros(b: Buy, spread: number, feeSell: number): number {
  if (b.shares <= 0) return 0
  return b.fee + feeSell + b.spreadCost + b.shares * b.midEur * (spread / 2)
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
