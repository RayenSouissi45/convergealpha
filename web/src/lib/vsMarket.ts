// Your real trades replayed into the S&P 500: every euro you put into a stock buys the index on the
// same day instead, every sale takes the same euros out. Same money, same days: the only difference
// is what you picked. Uses SPY with dividends and the European Central Bank's EUR/USD.

import type { Trade } from './journal'

export interface SpyFile {
  dates: string[]
  tr: number[]
  usd_per_eur: (number | null)[]
  fx_source?: string
}

/** Euro price of one S&P 500 unit on or before `date` (null before the file starts). */
function eurPrice(spy: SpyFile, date: string): number | null {
  let lo = 0
  let hi = spy.dates.length - 1
  let found = -1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if ((spy.dates[mid] as string) <= date) {
      found = mid
      lo = mid + 1
    } else hi = mid - 1
  }
  if (found < 0) return null
  const fx = spy.usd_per_eur[found]
  return fx ? (spy.tr[found] as number) / fx : null
}

export interface VsMarket {
  /** Value now if every buy and sale had been the S&P 500 instead (euros). */
  marketNow: number
  /** Euros taken out by sales (the same for you and for the index). */
  takenOut: number
  /** Trades that could not be replayed (before the file starts). */
  skipped: number
  since: string | null
}

export function vsMarket(trades: Trade[], spy: SpyFile | null): VsMarket | null {
  if (!spy || spy.dates.length === 0) return null
  let units = 0
  let takenOut = 0
  let skipped = 0
  let since: string | null = null
  for (const t of trades) {
    if (t.paper || t.side === 'dividend') continue
    const p = eurPrice(spy, t.date)
    if (p === null) {
      skipped++
      continue
    }
    if (since === null || t.date < since) since = t.date
    if (t.side === 'buy') units += (t.shares * t.priceEur + t.feeEur) / p
    else {
      const out = t.shares * t.priceEur - t.feeEur
      units -= out / p
      takenOut += out
    }
  }
  const last = eurPrice(spy, spy.dates[spy.dates.length - 1] as string)
  if (last === null || since === null) return null
  return { marketNow: units * last, takenOut, skipped, since }
}

export interface MonthPoint {
  month: string
  /** Euros put in so far (buys with fees). */
  paidIn: number
  /** Your stocks at that month's last close + euros taken out by sales. */
  you: number
  /** The same trades in the S&P 500 + the same euros taken out. */
  market: number
}

/** Month by month: your money next to the same trades in the S&P 500 (real trades only). */
export function monthly(trades: Trade[], spy: SpyFile | null, closes: Map<string, { t: string[]; c: (number | null)[] }>): MonthPoint[] {
  if (!spy || !spy.dates.length) return []
  const real = trades.filter((t) => !t.paper && t.side !== 'dividend').sort((a, b) => (a.date < b.date ? -1 : 1))
  if (!real.length) return []
  const firstMonth = real[0]!.date.slice(0, 7)
  const ends = new Map<string, string>()
  for (const d of spy.dates) if (d.slice(0, 7) >= firstMonth) ends.set(d.slice(0, 7), d)
  const closeOn = (tk: string, d: string): number | null => {
    const s = closes.get(tk)
    if (!s) return null
    for (let i = s.t.length - 1; i >= 0; i--) if ((s.t[i] as string) <= d && s.c[i] !== null && s.c[i] !== undefined) return s.c[i] as number
    return null
  }
  const out: MonthPoint[] = []
  for (const [month, d] of ends) {
    const fx = spy.usd_per_eur[spy.dates.indexOf(d)]
    if (!fx) continue
    const upTo = real.filter((t) => t.date <= d)
    const vs = vsMarket(upTo, { ...spy, dates: spy.dates.filter((x) => x <= d), tr: spy.tr.slice(0, spy.dates.filter((x) => x <= d).length), usd_per_eur: spy.usd_per_eur.slice(0, spy.dates.filter((x) => x <= d).length) })
    const shares = new Map<string, number>()
    let paidIn = 0
    for (const t of upTo) {
      shares.set(t.ticker, (shares.get(t.ticker) ?? 0) + (t.side === 'buy' ? t.shares : -t.shares))
      if (t.side === 'buy') paidIn += t.shares * t.priceEur + t.feeEur
    }
    let held = 0
    let ok = true
    for (const [tk, n] of shares) {
      if (n <= 1e-9) continue
      const c = closeOn(tk, d)
      if (c === null) ok = false
      else held += (n * c) / fx
    }
    if (!ok || !vs) continue
    out.push({ month, paidIn, you: held + vs.takenOut, market: vs.marketNow + vs.takenOut })
  }
  return out
}
