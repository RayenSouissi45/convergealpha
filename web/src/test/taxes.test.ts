import { describe, expect, it } from 'vitest'
import { capitalTax, DEFAULT_TAX, effectiveRate, taxOnGain, usDividendTax, vorabpauschale } from '../lib/taxes'

describe('German tax on investment income (2026 rules)', () => {
  it('is 26.375% without church tax and 27.99% with 9% church tax', () => {
    expect(capitalTax(1000).total).toBeCloseTo(263.75, 2)
    const c = capitalTax(1000, 0.09)
    expect(c.kapest).toBeCloseTo(1000 / 4.09, 6) // 244.50: church tax lowers the 25%
    expect(c.total).toBeCloseTo(279.95, 2)
    expect(effectiveRate(0.08)).toBeCloseTo(0.2782, 4)
  })

  it('uses the allowance first, taxes only gains, and 70% of an equity ETF gain', () => {
    const p = { ...DEFAULT_TAX, allowanceLeft: 1000 }
    expect(taxOnGain(800, p).tax).toBe(0)
    const g = taxOnGain(3000, p)
    expect(g.taxable).toBe(2000)
    expect(g.tax).toBeCloseTo(527.5, 6)
    expect(taxOnGain(-500, p)).toMatchObject({ tax: 0, net: -500 })
    const etf = taxOnGain(3000, { ...p, allowanceLeft: 0 }, 'equityFund')
    expect(etf.taxable).toBeCloseTo(2100, 6)
    expect(etf.tax).toBeCloseTo(2100 * 0.26375, 6)
  })

  it('credits the 15% US withholding on dividends', () => {
    const d = usDividendTax(100, { ...DEFAULT_TAX, allowanceLeft: 0 })
    expect(d.withheld).toBeCloseTo(15)
    expect(d.german).toBeCloseTo((100 - 60) / 4 * 1.055, 6) // 10.55: 25% minus the 15% already paid
    expect(d.net).toBeCloseTo(74.45, 6)
  })

  it('advance tax base on a fund: start value x Basiszins x 0.7, at most the real gain', () => {
    expect(vorabpauschale(10000, 11000, 2026)).toBeCloseTo(224, 6) // 3.20% x 0.7
    expect(vorabpauschale(10000, 10100, 2026)).toBeCloseTo(100, 6)
    expect(vorabpauschale(10000, 9000, 2026)).toBe(0)
    expect(vorabpauschale(10000, 11000, 2026, 6)).toBeCloseTo(112, 6)
  })
})
