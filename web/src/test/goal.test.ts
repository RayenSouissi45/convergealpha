import { describe, expect, it } from 'vitest'
import { afterTax, chance, fan, monthlyNeeded, mulberry32, simulate, sustainableWithdrawal, type History } from '../lib/goal'
import { DEFAULT_TAX } from '../lib/taxes'

/** 50 years where every month is the same: every replayed future is identical. */
function flat(market: number, rf: number, inflation = 0): History {
  const months = Array.from({ length: 600 }, (_, i) => `${1950 + Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, '0')}`)
  return { months, market: months.map(() => market), rf: months.map(() => rf), inflation: months.map(() => inflation) }
}

const base = { years: 10, stocks: 1, ter: 0, real: false, cautious: false }

describe('goal planner', () => {
  it('random numbers are seeded: the same plan always draws the same futures', () => {
    const a = mulberry32(42)
    const b = mulberry32(42)
    expect([a(), a(), a()]).toEqual([b(), b(), b()])
  })

  it('grows money exactly like compound interest when every month is the same', () => {
    const ps = simulate(flat(0.01, 0.002), base, 50)
    const f = fan(ps, 1000, 100)
    const g = 1.01
    const annuity = (g ** 120 - 1) / 0.01 * g // contributions at the start of each month
    expect(f.at(-1)!.p50).toBeCloseTo(1000 * g ** 120 + 100 * annuity, 6)
    expect(f.at(-1)!.p10).toBeCloseTo(f.at(-1)!.p90, 6)
    expect(f.at(-1)!.paidIn).toBe(1000 + 100 * 120)
  })

  it('mixes stocks and Treasury bills and takes the fund cost off every month', () => {
    const ps = simulate(flat(0.01, 0.002), { ...base, stocks: 0.5, ter: 0.012, years: 1 }, 10)
    const r = 0.5 * 0.01 + 0.5 * 0.002 - 0.001
    expect(fan(ps, 1000, 0).at(-1)!.p50).toBeCloseTo(1000 * (1 + r) ** 12, 9)
  })

  it('finds the exact monthly amount for a goal, and the chance of reaching it', () => {
    const ps = simulate(flat(0.005, 0.001), base, 50)
    const need = monthlyNeeded(ps, 2000, 30000, 0.8)
    expect(chance(ps, 2000, need, 30000)).toBe(1)
    expect(chance(ps, 2000, need - 1, 30000)).toBe(0)
    expect(fan(ps, 2000, need).at(-1)!.p50).toBeCloseTo(30000, 6)
  })

  it('shows today’s euros when inflation is on', () => {
    const ps = simulate(flat(0.01, 0.002, 0.01), { ...base, real: true, years: 5 }, 10)
    expect(fan(ps, 1000, 0).at(-1)!.p50).toBeCloseTo(1000, 6) // 1% a month, 1% inflation
  })

  it('a cautious plan earns 2 points a year less on stocks', () => {
    const plain = fan(simulate(flat(0.01, 0), { ...base, years: 1 }, 5), 1000, 0).at(-1)!.p50
    const cautious = fan(simulate(flat(0.01, 0), { ...base, years: 1, cautious: true }, 5), 1000, 0).at(-1)!.p50
    expect(cautious).toBeCloseTo(1000 * (1 + 0.01 - 0.02 / 12) ** 12, 9)
    expect(cautious).toBeLessThan(plain)
  })

  it('withdrawals: with no growth, a pot lasts exactly pot ÷ months', () => {
    expect(sustainableWithdrawal(flat(0, 0), 12000, 10, base)).toBeCloseTo(100, 6)
    expect(sustainableWithdrawal(flat(0.005, 0), 12000, 10, base)).toBeGreaterThan(100)
  })

  it('takes German tax off the gain at the end, 30% of an equity ETF gain tax free', () => {
    const p = { ...DEFAULT_TAX, allowanceLeft: 0 }
    expect(afterTax(20000, 10000, p)).toBeCloseTo(10000 + 10000 - 7000 * 0.26375, 6)
    expect(afterTax(9000, 10000, p)).toBe(9000)
    expect(afterTax(20000, 10000, null)).toBe(20000)
  })
})
