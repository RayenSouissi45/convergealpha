import { describe, expect, it } from 'vitest'
import { beforeAfter, CVAR95, exposures, maxStocks, overlapWarnings, summary, type Holding } from '../lib/risk'
import type { ScreenerRow } from '../types'

const row = (o: Partial<ScreenerRow>): ScreenerRow => ({ ticker: 'X', vol_63: 0.3, sector: 'Tech', cluster: 1, p10_1m: -0.1, f5: 50, ...o }) as ScreenerRow
const h = (ticker: string, valueEur: number, o: Partial<ScreenerRow> = {}): Holding => ({ ticker, valueEur, row: row({ ticker, ...o }) })

describe('portfolio risk', () => {
  it('a bad month for one stock: 2.06 monthly volatilities, halved when half is cash', () => {
    const one = summary([h('A', 1000)])
    expect(one.monthlyVol).toBeCloseTo(0.3 / Math.sqrt(12), 9)
    expect(one.cvar).toBeCloseTo(CVAR95 * 0.3 / Math.sqrt(12), 9)
    expect(summary([h('A', 1000)], 1000).cvarEur).toBeCloseTo(one.cvarEur, 6) // same euros at risk
    expect(summary([h('A', 1000)], 1000).cvar).toBeCloseTo(one.cvar / 2, 9)
  })

  it('stocks that move together add more risk, and a crash makes everything move together', () => {
    const together = summary([h('A', 500, { cluster: 1 }), h('B', 500, { cluster: 1 })])
    const apart = summary([h('A', 500, { cluster: 1, sector: 'Tech' }), h('B', 500, { cluster: 2, sector: 'Health' })])
    expect(together.cvar).toBeGreaterThan(apart.cvar)
    expect(apart.cvarCrash).toBeGreaterThan(apart.cvar)
    expect(apart.badMonthEur).toBeCloseTo(-100) // each stock at its own 1-in-10 bad month
    expect(apart.crash20Eur).toBeCloseTo(-200)
    expect(apart.gapEur).toBeCloseTo(-100)
  })

  it('finds hidden overlap', () => {
    const hs = [h('A', 400, { sector: 'Tech', cluster: 3, f5: 90 }), h('B', 400, { sector: 'Tech', cluster: 3, f5: 80 }), h('C', 200, { sector: 'Energy', cluster: 4, f5: 30 })]
    expect(exposures(hs).sectors[0]).toEqual({ name: 'Tech', share: 0.8 })
    const w = overlapWarnings(hs)
    expect(w.some((x) => /80% is in one sector/.test(x))).toBe(true)
    expect(w.some((x) => /move together/.test(x))).toBe(true)
    expect(w.some((x) => /strong recent trends/.test(x))).toBe(true)
  })

  it('how many free orders an amount supports, and the portfolio before and after a buy', () => {
    expect(maxStocks(1200, 500)).toBe(2)
    expect(maxStocks(400, 500)).toBe(0)
    const ba = beforeAfter([h('A', 1000)], 1000, 'B', row({ ticker: 'B', cluster: 2, sector: 'Health' }), 500, 'buy')
    expect(ba.positionsAfter).toBe(2)
    expect(ba.after.investedEur).toBeCloseTo(1500)
    expect(ba.after.totalEur).toBeCloseTo(2000)
  })
})
