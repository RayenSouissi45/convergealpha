// Help for placing an order on finanzen.net zero (gettex): a euro limit price, when to trade, how
// many stocks an amount supports with free orders, buying in parts, and what your own fills really
// cost compared with the app's estimate.

import type { Journal } from './journal'

/** gettex trades US shares 8:00–22:00 German time, but the US market is only open 15:30–22:00
 * (Berlin): outside it, market makers quote wider spreads. */
export function usSession(now: Date): { open: boolean; text: string } {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Berlin', weekday: 'short', hour: '2-digit', minute: '2-digit', hour12: false }).formatToParts(now)
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? ''
  const weekday = get('weekday')
  const minutes = Number(get('hour')) * 60 + Number(get('minute'))
  const weekend = weekday === 'Sat' || weekday === 'Sun'
  const open = !weekend && minutes >= 15 * 60 + 30 && minutes < 22 * 60
  return {
    open,
    text: open
      ? 'The US market is open (15:30–22:00 German time): spreads on gettex are usually at their narrowest now.'
      : 'The US market is closed now. On gettex, US shares then trade with wider spreads: better to buy between 15:30 and 22:00 German time on a weekday (US holidays excepted).',
  }
}

/** The limit to type: today's price in euros plus half the spread and 1% room, rounded up to the
 * cent. The order then never fills more than about 1% above the price you planned with. */
export function limitPriceEur(priceUsd: number, fxUsdPerEur: number, spread: number): number {
  return Math.ceil((priceUsd / fxUsdPerEur) * (1 + spread / 2) * 1.01 * 100) / 100
}

/** Free-order advice for an amount: how many stocks at 500 € or more, and buying in parts. */
export function amountAdvice(amountEur: number, freeFrom = 500): { stocks: number; parts: number; text: string; partsText: string } {
  const stocks = amountEur >= freeFrom ? Math.floor(amountEur / freeFrom) : 0
  const parts = stocks >= 2 ? Math.min(3, stocks) : 1
  const text =
    stocks === 0
      ? `With ${Math.round(amountEur)} € every order pays the 1 € fee (orders are free from ${freeFrom} €): one stock, or wait and save up to ${freeFrom} €.`
      : stocks === 1
        ? `With ${Math.round(amountEur)} € one stock gets a free order (from ${freeFrom} €); two stocks would pay 1 € each way per order.`
        : `With ${Math.round(amountEur)} € up to ${stocks} stocks can be bought with free orders (${freeFrom} € or more each).`
  const partsText =
    parts > 1
      ? `Buying in ${parts} parts (e.g. a week apart) stays free while each part is ${freeFrom} € or more. It lowers the risk of buying on one bad day but did not raise the result: tested on 2016–2023, no way of buying beat buying at the next open.`
      : `Buying in parts would make each order smaller than ${freeFrom} € and pay the fee: one order is cheaper.`
  return { stocks, parts, text, partsText }
}

/** Spread cost of an order as a range: the estimate, and a bad case of 3× (thin quotes outside US
 * hours or on a volatile day). The fee is separate. */
export function spreadRange(amountEur: number, spread: number): { typical: number; bad: number } {
  const typical = amountEur * spread
  return { typical, bad: typical * 3 }
}

export interface MeasuredCosts {
  n: number
  /** Average extra paid over the app's mid price when you logged it (fills vs last close). */
  paid: number | null
  /** The app's estimate for the same trades: half the spread. */
  estimate: number | null
  /** How much more careful Plan's spread estimates become (1 = unchanged, at most 3). */
  factor: number
  text: string
}

const MIN_TRADES = 5

/** What your buys really cost vs the price the app showed: (price paid ÷ (last close ÷ EUR/USD)) − 1,
 * averaged. A single fill also contains the move since the close, so only 5 or more buys count. */
export function measuredCosts(j: Journal, spreadOf: (ticker: string) => number | null): MeasuredCosts {
  const xs: { paid: number; est: number }[] = []
  for (const t of j.trades) {
    const s = t.snapshot
    if (t.side !== 'buy' || !s?.price_usd || !s.fx || !(t.priceEur > 0)) continue
    const mid = s.price_usd / s.fx
    const spread = spreadOf(t.ticker)
    xs.push({ paid: t.priceEur / mid - 1, est: (spread ?? 0.002) / 2 })
  }
  if (xs.length < MIN_TRADES) {
    return { n: xs.length, paid: null, estimate: null, factor: 1, text: `Needs ${MIN_TRADES} logged buys with the app's price (you have ${xs.length}).` }
  }
  const paid = xs.reduce((a, x) => a + x.paid, 0) / xs.length
  const estimate = xs.reduce((a, x) => a + x.est, 0) / xs.length
  const factor = estimate > 0 ? Math.min(3, Math.max(1, paid / estimate)) : 1
  const text =
    factor > 1.05
      ? `Your buys cost ${(paid * 100).toFixed(2)}% above the app's price on average, ${factor.toFixed(1)}× its estimate (${(estimate * 100).toFixed(2)}%): Plan now counts ${factor.toFixed(1)}× the spread.`
      : `Your buys cost ${(paid * 100).toFixed(2)}% above the app's price on average, within its estimate (${(estimate * 100).toFixed(2)}%).`
  return { n: xs.length, paid, estimate, factor, text }
}
