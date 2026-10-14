import { describe, expect, it } from 'vitest'
import { behaviour, coolingOff, decisionQuality, EMPTY_JOURNAL, evidenceChanges, fifo, harvestSaving, migrateOld, MIGRATION_FX, normalDay, parseJournal, positions, preTradeChecks, processScore, taxYears, thesis, toCsv, type Journal, type Trade } from '../lib/journal'
import { DEFAULT_TAX } from '../lib/taxes'
import type { ScreenerRow } from '../types'

const t = (o: Partial<Trade> & Pick<Trade, 'date' | 'side' | 'ticker' | 'shares' | 'priceEur'>): Trade => ({ id: `${o.date}-${o.side}-${o.ticker}-${o.shares}`, feeEur: 1, ...o })
const j = (trades: Trade[], rules: Partial<Journal['rules']> = {}): Journal => ({ ...EMPTY_JOURNAL, trades, rules: { ...EMPTY_JOURNAL.rules, ...rules } })
const row = (o: Partial<ScreenerRow>): ScreenerRow => ({ ticker: 'AAA', price: 110, label: 'NO TRADE', f1: 60, f2: 60, f3: 60, f4: 60, f5: 60, f6: 60, zero: true, ...o }) as ScreenerRow

describe('trade journal', () => {
  const buys = [t({ date: '2026-01-02', side: 'buy', ticker: 'AAA', shares: 10, priceEur: 10 }), t({ date: '2026-02-02', side: 'buy', ticker: 'AAA', shares: 10, priceEur: 12 })]

  it('sells the first shares bought first (German law) with fees in the cost and proceeds', () => {
    const book = fifo([...buys, t({ date: '2026-03-03', side: 'sell', ticker: 'AAA', shares: 15, priceEur: 15 })])
    const r = book.realized[0]!
    expect(r.costEur).toBeCloseTo(101 + 0.5 * 121, 9) // first lot whole, half of the second
    expect(r.proceedsEur).toBeCloseTo(15 * 15 - 1, 9)
    expect(r.gainEur).toBeCloseTo(224 - 161.5, 9)
    expect(r.daysHeld).toBe(60)
    const left = book.open.get('AAA')!
    expect(left).toHaveLength(1)
    expect(left[0]!.shares).toBeCloseTo(5)
    expect(left[0]!.costEur).toBeCloseTo(60.5)
  })

  it('flags selling more than you hold', () => {
    const book = fifo([buys[0]!, t({ date: '2026-03-03', side: 'sell', ticker: 'AAA', shares: 12, priceEur: 15 })])
    expect(book.problems[0]).toMatch(/sold 12 AAA but held only 10/)
    expect(book.realized[0]!.shares).toBe(10)
  })

  it('values open positions in euros from the dollar price', () => {
    const ps = positions(j(buys), new Map([['AAA', row({ price: 22 })]]), 1.1)
    expect(ps[0]!.valueEur).toBeCloseTo(20 * 20, 6)
    expect(ps[0]!.gainEur).toBeCloseTo(400 - 222, 6)
  })

  it('works out the yearly tax: stock losses only against stock gains, carried forward', () => {
    const trades = [
      t({ date: '2026-01-02', side: 'buy', ticker: 'AAA', shares: 100, priceEur: 10, feeEur: 0 }),
      t({ date: '2026-06-01', side: 'sell', ticker: 'AAA', shares: 100, priceEur: 40, feeEur: 0 }), // +3,000
      t({ date: '2026-01-02', side: 'buy', ticker: 'BBB', shares: 100, priceEur: 10, feeEur: 0 }),
      t({ date: '2026-07-01', side: 'sell', ticker: 'BBB', shares: 100, priceEur: 5, feeEur: 0 }), // −500
      t({ date: '2027-01-04', side: 'buy', ticker: 'CCC', shares: 100, priceEur: 10, feeEur: 0 }),
      t({ date: '2027-02-01', side: 'sell', ticker: 'CCC', shares: 100, priceEur: 2, feeEur: 0 }), // −800
    ]
    const [y26, y27] = taxYears(j(trades), DEFAULT_TAX)
    expect(y26!.stockNet).toBeCloseTo(2500)
    expect(y26!.taxable).toBeCloseTo(1500)
    expect(y26!.estimatedTax).toBeCloseTo(1500 * 0.26375, 6)
    expect(y27!.lossCarry).toBeCloseTo(800)
    expect(y27!.estimatedTax).toBe(0)
  })

  it('a December loss sale saves tax on this year’s gains', () => {
    expect(harvestSaving(3000, -1000, { ...DEFAULT_TAX, allowanceLeft: 0 })).toBeCloseTo(1000 * 0.26375, 6)
    expect(harvestSaving(0, -1000, DEFAULT_TAX)).toBe(0)
  })

  it('checks your "wrong if" conditions and what changed since you bought', () => {
    const b = { ...buys[0]!, wrongIf: ['below_exit', 'label_sell'] as Trade['wrongIf'], snapshot: { planned_exit_usd: 100, f: [70, 60, 60, 60, 60, 60] } }
    const ps = positions(j([b]), new Map([['AAA', row({ price: 95, f1: 50 })]]), 1.1)
    const checks = thesis(ps[0]!)
    expect(checks.find((c) => c.key === 'below_exit')).toMatchObject({ broken: true })
    expect(checks.find((c) => c.key === 'label_sell')).toMatchObject({ broken: false })
    expect(evidenceChanges(ps[0]!)).toEqual([{ family: 'F1', then: 70, now: 50 }])
  })

  it('says whether today’s move is normal for the stock', () => {
    expect(normalDay(row({ change_1d: -0.05, vol_63: 0.32 }))).toMatchObject({ unusual: true })
    expect(normalDay(row({ change_1d: -0.015, vol_63: 0.32 }))).toMatchObject({ unusual: false })
  })

  it('checks your own rules and the app’s warnings before a trade', () => {
    const jj = j(buys, { minOrderEur: 500, maxPerStock: 0.1, maxTradesPerMonth: 4, noEarningsWithinDays: 5 })
    const ps = positions(jj, new Map([['AAA', row({})]]), 1.1)
    const checks = preTradeChecks({ side: 'buy', ticker: 'BBB', amountEur: 300, row: row({ ticker: 'BBB', days_to_earnings: 3, zero: false }) }, jj, ps, new Date('2026-03-10'))
    const failed = checks.filter((c) => !c.ok).map((c) => c.text)
    expect(failed.some((x) => /Order of 300 €/.test(x))).toBe(true)
    expect(failed.some((x) => /Not on finanzen.net zero/.test(x))).toBe(true)
    expect(failed.some((x) => /Earnings in 3 trading days/.test(x))).toBe(true)
    expect(failed.some((x) => /BBB would be/.test(x))).toBe(true)
    expect(coolingOff({ side: 'buy', ticker: 'BBB', amountEur: 600, row: row({ ret_1w: 0.15 }) }, jj)[0]).toMatch(/rose 15% this week/)
  })

  it('judges decisions by how they were made, not only by the result', () => {
    const good = { ...buys[0]!, reason: 'BUY label, 4 strong families', wrongIf: ['label_sell'] as Trade['wrongIf'], basis: 'label' as const }
    expect(processScore(good).good).toBe(true)
    expect(processScore(buys[1]!).missing).toContain('a written reason')
    const q = decisionQuality(j([good, t({ date: '2026-05-01', side: 'sell', ticker: 'AAA', shares: 10, priceEur: 8 })]))
    expect(q[0]!.quadrant).toBe('unlucky') // a good decision with a bad result
  })

  it('spots chasing and panic', () => {
    const b = behaviour(j([t({ date: '2026-03-01', side: 'buy', ticker: 'AAA', shares: 1, priceEur: 10, snapshot: { ret_1w: 0.2 } }), t({ date: '2026-03-05', side: 'sell', ticker: 'AAA', shares: 1, priceEur: 9, snapshot: { ret_1w: -0.12 } })]), new Date('2026-03-10'))
    expect(b.chasedBuys).toBe(1)
    expect(b.panicSells).toBe(1)
    expect(b.tradesLast30).toBe(2)
  })

  it('moves holdings from the old dollar portfolio, flagged for checking', () => {
    const old = { holdings: [{ ticker: 'aaa', shares: 3, entryPrice: 110, entryDate: '2026-09-01', exitLevel: 101 }] }
    const [m] = migrateOld(old)
    expect(m).toMatchObject({ ticker: 'AAA', shares: 3, side: 'buy', fxGuessed: true })
    expect(m!.priceEur).toBeCloseTo(110 / MIGRATION_FX)
    expect(m!.snapshot?.planned_exit_usd).toBe(101)
  })

  it('never trusts a stored or imported file, and exports a CSV', () => {
    const parsed = parseJournal({ trades: [buys[0], { id: 'x', date: 'bad', side: 'buy', ticker: 'A', shares: 1, priceEur: 1, feeEur: 0 }], rules: { maxPerStock: 7 } })
    expect(parsed.trades).toHaveLength(1)
    expect(parsed.rules.maxPerStock).toBe(1)
    expect(() => parseJournal('nope')).toThrow()
    const csv = toCsv(j([...buys, t({ date: '2026-03-03', side: 'sell', ticker: 'AAA', shares: 15, priceEur: 15 })]))
    expect(csv.split('\n')[0]).toMatch(/^date,side,ticker/)
    expect(csv).toMatch(/2026-03-03,sell,AAA,15,15\.0000,1\.00,0\.00,161\.50,224\.00,62\.50/)
  })
})
