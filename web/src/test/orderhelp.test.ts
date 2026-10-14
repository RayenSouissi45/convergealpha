import { describe, expect, it } from 'vitest'
import { EMPTY_JOURNAL, type Journal, type Trade } from '../lib/journal'
import { amountAdvice, limitPriceEur, measuredCosts, spreadRange, usSession } from '../lib/orderHelp'

describe('order help for finanzen.net zero', () => {
  it('knows when the US market is open in German time', () => {
    expect(usSession(new Date('2026-10-14T13:45:00Z')).open).toBe(true) // 15:45 Berlin (CEST)
    expect(usSession(new Date('2026-10-14T13:15:00Z')).open).toBe(false) // 15:15 Berlin
    expect(usSession(new Date('2026-10-14T20:05:00Z')).open).toBe(false) // 22:05 Berlin
    expect(usSession(new Date('2026-10-17T15:00:00Z')).open).toBe(false) // Saturday
    expect(usSession(new Date('2026-12-14T14:45:00Z')).open).toBe(true) // 15:45 Berlin (CET)
  })

  it('a limit price in euros: price + half the spread + 1%, rounded up to the cent', () => {
    // $100 at 1.10 $/€ = €90.909…; × 1.0005 × 1.01 = €91.86 (rounded up)
    expect(limitPriceEur(100, 1.1, 0.001)).toBe(91.87)
    expect(limitPriceEur(100, 1.1, 0.001)).toBeGreaterThanOrEqual((100 / 1.1) * 1.0005 * 1.01)
  })

  it('says how many stocks an amount supports with free orders, and when parts make sense', () => {
    expect(amountAdvice(300)).toMatchObject({ stocks: 0, parts: 1 })
    expect(amountAdvice(700).stocks).toBe(1)
    const a = amountAdvice(1600)
    expect(a.stocks).toBe(3)
    expect(a.parts).toBe(3)
    expect(a.text).toMatch(/up to 3 stocks/)
    expect(a.partsText).toMatch(/no way of buying beat buying at the next open/)
    expect(spreadRange(1000, 0.002)).toEqual({ typical: 2, bad: 6 })
  })

  it('measures your real costs and makes Plan more careful when they are higher', () => {
    const buy = (i: number, paidOver: number): Trade => ({ id: String(i), date: '2026-10-1' + i, side: 'buy', ticker: 'AAA', shares: 1, priceEur: (100 / 1.1) * (1 + paidOver), feeEur: 0, snapshot: { price_usd: 100, fx: 1.1 } })
    const few: Journal = { ...EMPTY_JOURNAL, trades: [buy(1, 0.004)] }
    expect(measuredCosts(few, () => 0.002)).toMatchObject({ n: 1, factor: 1 })
    const j: Journal = { ...EMPTY_JOURNAL, trades: [0, 1, 2, 3, 4].map((i) => buy(i, 0.002)) }
    const m = measuredCosts(j, () => 0.002) // paid 0.2% over vs an estimate of 0.1% (half the spread)
    expect(m.n).toBe(5)
    expect(m.factor).toBeCloseTo(2)
    expect(m.text).toMatch(/2\.0× its estimate/)
    expect(measuredCosts({ ...j, trades: j.trades.map((_, i) => buy(i, 0.0005)) }, () => 0.002).factor).toBe(1)
  })
})
