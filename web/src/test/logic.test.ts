import { describe, expect, it } from 'vitest'
import { holdingStatus, parsePortfolio, throttle, type Holding } from '../lib/portfolio'
import { kelly, plannedExit, positionShares } from '../lib/sizing'
import type { ScreenerRow } from '../types'

describe('sizing (same reference numbers as the Python tests)', () => {
  it('Kelly f* = 23.1% for p 0.53, b 11/7', () => {
    expect(kelly(0.53, 11 / 7)).toBeCloseTo(0.2309, 4)
  })

  it('equity $10,000, E $100, X $92, G $9 -> 5 shares (quarter-Kelly binds)', () => {
    const r = positionShares({ equity: 10_000, entry: 100, exit: 92, gap: 9, pLower: 0.53, payoffB: 11 / 7 })
    expect(r.shares).toBe(5)
    expect(r.binding).toBe('kelly')
    expect(r.riskPerShare).toBe(9)
  })

  it('tier 2 halves the risk budget and the drawdown throttle can stop buys', () => {
    expect(positionShares({ equity: 10_000, entry: 100, exit: 92, gap: 9, pLower: 0.7, payoffB: 2, tierMultiplier: 0.5 }).shares).toBe(4)
    expect(positionShares({ equity: 10_000, entry: 100, exit: 92, gap: 9, pLower: 0.7, payoffB: 2, throttle: 0 }).shares).toBe(0)
  })

  it('liquidity cap and negative edge', () => {
    expect(positionShares({ equity: 1_000_000, entry: 50, exit: 46, gap: 1, pLower: 0.6, payoffB: 2, advShares: 10_000 }).shares).toBe(100)
    expect(positionShares({ equity: 1_000_000, entry: 50, exit: 46, gap: 1, pLower: 0.3, payoffB: 1 }).shares).toBe(0)
  })

  it('planned exit is the tighter of 2 ATR and 8%', () => {
    expect(plannedExit(100, 3)).toBe(94)
    expect(plannedExit(100, 6)).toBe(92)
  })
})

const row = (o: Partial<ScreenerRow>): ScreenerRow => ({ ticker: 'X', price: 100, label: 'NO TRADE', f1: 60, f2: 60, f3: 60, f4: 60, f5: 60, f6: 60, speed: 0.1, ...o }) as ScreenerRow
const holding = (o: Partial<Holding> = {}): Holding => ({ ticker: 'X', shares: 10, entryPrice: 100, entryDate: '2026-09-01', exitLevel: 92, atrAtEntry: 2, p25MonthAtEntry: -0.05, ...o })

describe('holding labels', () => {
  const today = new Date('2026-10-12T12:00:00Z')

  it('HOLD when no exit rule triggers', () => {
    expect(holdingStatus(holding(), row({ price: 101, label: 'BUY' }), [], today).label).toBe('HOLD')
  })

  it('SELL / RISK WARNING at the planned exit, on evidence decay, or without data', () => {
    expect(holdingStatus(holding(), row({ price: 91 }), [], today).label).toBe('SELL / RISK WARNING')
    expect(holdingStatus(holding(), row({ f1: 40, f2: 40, f3: 40 }), [], today).label).toBe('SELL / RISK WARNING')
    expect(holdingStatus(holding(), undefined, [], today).label).toBe('SELL / RISK WARNING')
  })

  it('ROTATE after 21 trading days below its 1-month 25th percentile when a 1.5x faster candidate exists', () => {
    const lagging = row({ price: 93.5, speed: 0.1, label: 'BUY' })
    const fast = row({ ticker: 'FAST', speed: 0.2, label: 'BUY' })
    expect(holdingStatus(holding(), lagging, [fast], today).label).toBe('ROTATE')
    expect(holdingStatus(holding(), lagging, [row({ ticker: 'SLOW', speed: 0.12 })], today).label).toBe('HOLD')
  })

  it('suggests break-even and selling a third at the ATR levels', () => {
    const s = holdingStatus(holding(), row({ price: 107, label: 'BUY' }), [], today)
    expect(s.actions.join(' ')).toMatch(/break-even/)
    expect(s.actions.join(' ')).toMatch(/Sell a third/)
  })
})

describe('portfolio storage', () => {
  it('rejects junk and keeps valid holdings', () => {
    expect(() => parsePortfolio('nope')).toThrow()
    const p = parsePortfolio({ equity: 5000, holdings: [{ ticker: 'aapl', shares: 2, entryPrice: 100, entryDate: '2026-10-01' }, { foo: 1 }] })
    expect(p.holdings.map((h) => h.ticker)).toEqual(['AAPL'])
  })

  it('drawdown throttle steps', () => {
    expect(throttle({ version: 1, equity: 9_000, peakEquity: 10_000, holdings: [] }).factor).toBe(0.5)
    expect(throttle({ version: 1, equity: 8_400, peakEquity: 10_000, holdings: [] }).factor).toBe(0)
    expect(throttle({ version: 1, equity: 9_500, peakEquity: 10_000, holdings: [] }).factor).toBe(1)
  })
})
