import { describe, expect, it } from 'vitest'
import { breakEven, buy, result, sellFeeFor, ZERO_FEES } from '../lib/costs'
import { chanceAbove, cdf, dist, evaluate, evaluateSplit, mapPeriod, quantile, rank, sliderMin, THRESHOLDS, tradingDays, verdict, type Context, type PlanRow } from '../lib/plan'
import { sanitize } from '../lib/settings'

describe('trading costs (same reference values as the pipeline)', () => {
  it('100 € in -> 99 € of stock; the stock must rise 2.02% to get 100 € back', () => {
    const b = buy(100, 10, 1, 0, { buy: 1, sell: 1, fractional: true })
    expect(b.fee).toBe(1)
    expect(b.invested).toBeCloseTo(99, 10)
    expect(b.leftover).toBeCloseTo(0, 10)
    expect(breakEven(b, 0, 1)).toBeCloseTo(101 / 99 - 1, 10)
    expect(result(b, 101 / 99 - 1, 0, 1)).toBeCloseTo(0, 10)
  })

  it('converts dollars to euros, buys whole shares and keeps the rest as cash', () => {
    const b = buy(200, 150, 1.1, 0.0006)
    expect(b.midEur).toBeCloseTo(150 / 1.1, 10)
    expect(b.shares).toBe(1)
    expect(b.payEur).toBeCloseTo((150 / 1.1) * 1.0003, 10)
    expect(b.leftover).toBeCloseTo(200 - 1 - (150 / 1.1) * 1.0003, 10)
    const none = buy(100, 150, 1.1, 0.0006)
    expect(none.shares).toBe(0)
    expect(none.fee).toBe(0)
    expect(buy(200, 150, 1.1, 0.0006, { buy: 1, sell: 1, fractional: true }).shares).toBeCloseTo(199 / ((150 / 1.1) * 1.0003), 10)
  })

  it('a spread raises the break-even move', () => {
    const f = { buy: 1, sell: 1, fractional: true }
    expect(breakEven(buy(100, 10, 1, 0.002, f), 0.002, 1)).toBeGreaterThan(breakEven(buy(100, 10, 1, 0, f), 0, 1) + 0.0019)
  })
})

describe('plan builder', () => {
  it('maps the sliders to minimum sub-scores (1 -> 0, 10 -> 90, straight line)', () => {
    expect([1, 2, 5, 9, 10].map(sliderMin)).toEqual([0, 10, 40, 80, 90])
  })

  it('pins the fixed thresholds (same as pipeline decide/plan.py)', () => {
    expect(THRESHOLDS).toEqual({ green_p_profit: 0.55, green_reliability_lo: 0.52, amber_p_profit: 0.5, confidence_weight: 5, trading_days_per_day: 0.7 })
  })

  it('maps the period to the forecast horizons, mixing the nearest two in between', () => {
    expect(tradingDays(30)).toBe(21)
    expect(mapPeriod(30)).toMatchObject({ a: '1m', w: 0, exact: true, used: ['1m'] })
    expect(mapPeriod(180)).toMatchObject({ a: '6m', exact: true, used: ['6m'] })
    expect(mapPeriod(90)).toMatchObject({ a: '3m', exact: true })
    expect(mapPeriod(7)).toMatchObject({ a: '1w', exact: true })
    expect(mapPeriod(5)).toMatchObject({ a: '1w', short: true, exact: false })
    const m = mapPeriod(60) // 42 trading days: half way between 21 and 63
    expect(m).toMatchObject({ a: '1m', b: '3m', exact: false, used: ['1m', '3m'] })
    expect(m.w).toBeCloseTo(0.5, 10)
    expect(m.text).toMatch(/straight-line mix/)
  })

  it('chance above a cost hurdle is anchored on the calibrated chance up', () => {
    const d = dist(0.58, 0.02, -0.08, 0.12)!
    expect(chanceAbove(d, 0)).toBeCloseTo(0.58, 10)
    expect(chanceAbove(d, 0.02)).toBeLessThan(0.58)
    expect(cdf(d, d.med)).toBeCloseTo(0.5, 10)
    expect(quantile(d, cdf(d, 0.05))).toBeCloseTo(0.05, 10)
    expect(quantile(d, cdf(d, -0.1))).toBeCloseTo(-0.1, 10) // extended past the 10th percentile
    expect(cdf(d, -0.5)).toBe(0) // never below 0
  })

  it('verdict thresholds: green only when every check passes', () => {
    expect(verdict({ pProfit: 0.55, relLo: 0.52, middle: 0.01, validated: true }).color).toBe('green')
    expect(verdict({ pProfit: 0.549, relLo: 0.6, middle: 1, validated: true }).color).toBe('amber')
    expect(verdict({ pProfit: 0.6, relLo: 0.519, middle: 1, validated: true }).color).toBe('amber')
    expect(verdict({ pProfit: 0.6, relLo: 0.6, middle: 1, validated: false }).color).toBe('amber')
    expect(verdict({ pProfit: 0.6, relLo: 0.6, middle: 0, validated: true }).color).toBe('grey')
    const g = verdict({ pProfit: 0.49, relLo: 0.6, middle: 1, validated: true })
    expect(g.color).toBe('grey')
    expect(g.title).toBe('No good opportunity now: waiting is a valid choice')
  })

  const row = (ticker: string, extra: Partial<PlanRow> = {}): PlanRow => ({
    ticker,
    name: ticker,
    sector: 'Tech',
    zero: true,
    label: 'NO TRADE',
    price: 50,
    spread: 0.0006,
    safety: 70,
    upside: 70,
    confidence: 70,
    balanced: 70,
    days_to_earnings: 40,
    next_earnings: '2026-12-01',
    opp: null,
    opp_event: null,
    p_up_1m: 0.6,
    med_1m: 0.03,
    p10_1m: -0.07,
    p90_1m: 0.12,
    ...extra,
  })
  const ctx: Context = {
    fx: 1.1,
    fees: { buy: 1, sell: 1, fractional: false },
    mix: mapPeriod(30),
    reliability: { '1m': [{ lo: 0, hi: 1.01, n: 1000, rate: 0.56, wilson_lo: 0.53, wilson_hi: 0.59 }] },
    validated: ['P(up) 1m'],
  }

  it('ranks by the slider mix after the minimum scores, earnings and the zero filter', () => {
    const rows = [
      row('SAFE', { safety: 95, upside: 50 }),
      row('UP', { safety: 50, upside: 95 }),
      row('EARN', { days_to_earnings: 10 }),
      row('NODATE', { days_to_earnings: null }),
      row('NOTZERO', { zero: false }),
      row('UNSURE', { zero: null, safety: 10, upside: 10 }),
    ]
    const safe = rank(rows, { safety: 9, upside: 2, td: 21, allowEarnings: false, onlyZero: true })
    expect(safe.rows.map((r) => r.ticker)).toEqual(['SAFE'])
    expect(safe.left).toEqual({ safety: 4, upside: 0, earnings: 0, noDate: 0, zero: 1 })
    const up = rank(rows, { safety: 1, upside: 3, td: 21, allowEarnings: true, onlyZero: false })
    expect(up.rows[0]!.ticker).toBe('UP')
    expect(up.rows.map((r) => r.ticker)).toContain('EARN')
    expect(up.rows.map((r) => r.ticker)).toContain('NOTZERO')
  })

  it('evaluates a plan in euros and a split as two half amounts', () => {
    const e = evaluate(row('AAA', { p_up_1m: 0.62 }), 200, ctx)!
    expect(e.buy.shares).toBe(4) // 4 × €45.47 = €181.9
    expect(e.fees).toBe(2)
    expect(e.breakEven).toBeCloseTo(183.89 / (4 * (50 / 1.1) * 0.9997) - 1, 3)
    expect(e.rel).toEqual({ rate: 0.56, lo: 0.53, hi: 0.59, n: 1000 })
    expect(e.pProfit).toBeGreaterThan(0.55)
    expect(e.verdict.color).toBe('green')
    // 60% chance up: the 1.2% cost hurdle takes the chance of more money below 55%.
    expect(evaluate(row('AAA'), 200, ctx)!.verdict.color).toBe('amber')
    expect(evaluate(row('BIG', { price: 400 }), 200, ctx)).toBeNull() // one share costs more than 200 €
    const one = evaluateSplit(row('AAA'), row('BBB'), 400, ctx)!
    const single = evaluate(row('AAA'), 200, ctx)!
    // Two identical legs moving together: the same chance as one leg.
    expect(one.pProfit).toBeCloseTo(single.pProfit, 3)
    expect(one.fees).toBe(4)
    expect(one.middle).toBeCloseTo(2 * single.middle, 10)
  })

  it('never trusts stored settings', () => {
    expect(sanitize({ safety: 99, upside: -3, days: 1000, amount: -5, feeBuy: Number.NaN })).toMatchObject({ safety: 10, upside: 1, days: 180, amount: 1, feeBuy: 1 })
  })
})

describe('finanzen.net zero fee rule', () => {
  it('is free from 500 € of order value and 1 € below, both ways', () => {
    // $50 at 1.10 $/€ with a 0.1% spread: 45.4772... € a share.
    const small = buy(400, 50, 1.1, 0.001, ZERO_FEES)
    expect(small.fee).toBe(1)
    expect(small.shares).toBe(Math.floor(399 / ((50 / 1.1) * 1.0005)))
    const big = buy(600, 50, 1.1, 0.001, ZERO_FEES)
    expect(big.fee).toBe(0)
    expect(big.shares).toBe(Math.floor(600 / ((50 / 1.1) * 1.0005)))
    // Selling a 500 €+ position is free too: break-even is the spread alone.
    expect(breakEven(big, 0.001, ZERO_FEES)).toBeCloseTo(1.0005 / 0.9995 - 1, 10)
    expect(sellFeeFor(big, ZERO_FEES)).toBe(0)
    expect(sellFeeFor(small, ZERO_FEES)).toBe(1)
    // A flat fee keeps the old numbers: 100 € in -> 99 € of stock.
    expect(buy(100, 1, 1, 0, { buy: 1, sell: 1, fractional: true }).invested).toBeCloseTo(99)
  })

  it('charges the fee when a sale drops below 500 €', () => {
    const b = buy(600, 50, 1.1, 0, ZERO_FEES)
    expect(result(b, 0, 0, ZERO_FEES)).toBeCloseTo(b.shares * b.midEur - b.spent)
    expect(result(b, -0.5, 0, ZERO_FEES)).toBeCloseTo(b.shares * b.midEur * 0.5 - 1 - b.spent)
  })
})
