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
