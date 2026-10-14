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

describe('copy a strategy and paper trades', () => {
  it('scales the holdings to your amount with whole shares, fees and limits', async () => {
    const { copyPlan } = await import('../lib/orderHelp')
    const card = {
      value: 5000,
      holdings: [
        { ticker: 'AAA', close_usd: 110, value_eur: 2500 },
        { ticker: 'BBB', close_usd: 550, value_eur: 1000 },
      ],
    } as unknown as Parameters<typeof copyPlan>[0]
    const { lines, cashEur } = copyPlan(card, 2000, 1.1)
    // AAA: 50% of 2,000 € at ~100.10 € → 9 shares (≈ 901 €, free); BBB: 20% = 400 € at ~500.50 € → none.
    expect(lines.map((l) => [l.ticker, l.shares, l.fee])).toEqual([['AAA', 9, 0]])
    expect(cashEur).toBeCloseTo(2000 - 9 * 100 * 1.001, 1)
    expect(lines[0]!.limit).toBe(limitPriceEur(110, 1.1, 0.002))
  })

  it('keeps paper trades apart and merges them back when saved', async () => {
    const { journalView } = await import('../lib/journal')
    const t = (id: string, paper?: boolean): Trade => ({ id, date: '2026-10-14', side: 'buy', ticker: 'AAA', shares: 1, priceEur: 100, feeEur: 0, paper })
    const j: Journal = { ...EMPTY_JOURNAL, trades: [t('r1'), t('p1', true)] }
    const real = journalView(j, false)
    expect(real.view.trades.map((x) => x.id)).toEqual(['r1'])
    const paper = journalView(j, true)
    expect(paper.view.trades.map((x) => x.id)).toEqual(['p1'])
    // Adding a trade in the paper view marks it paper and keeps the real one.
    const saved = paper.merge({ ...paper.view, trades: [...paper.view.trades, t('p2')] })
    expect(saved.trades.map((x) => [x.id, Boolean(x.paper)])).toEqual([['p1', true], ['p2', true], ['r1', false]])
    // Deleting in the real view never touches paper trades.
    expect(real.merge({ ...real.view, trades: [] }).trades.map((x) => x.id)).toEqual(['p1'])
  })
})

describe('your trades vs the S&P 500', () => {
  it('replays every buy and sale into the index on the same day', async () => {
    const { vsMarket } = await import('../lib/vsMarket')
    // The index doubles in euros between Oct 1 and Oct 20.
    const spy = { dates: ['2026-10-01', '2026-10-10', '2026-10-20'], tr: [100, 150, 200], usd_per_eur: [1, 1, 1] }
    const buy: Trade = { id: 'b', date: '2026-10-01', side: 'buy', ticker: 'AAA', shares: 10, priceEur: 100, feeEur: 0 }
    const sell: Trade = { id: 's', date: '2026-10-10', side: 'sell', ticker: 'AAA', shares: 5, priceEur: 120, feeEur: 0 }
    const paper: Trade = { ...buy, id: 'p', paper: true }
    const v = vsMarket([buy, sell, paper], spy)!
    // 1,000 € buys 10 units; the 600 € sale removes 4 units; 6 units × 200 € = 1,200 €.
    expect(v.marketNow).toBeCloseTo(1200)
    expect(v.takenOut).toBe(600)
    expect(v.since).toBe('2026-10-01')
    expect(vsMarket([{ ...buy, date: '2026-09-01' }], spy)).toBeNull() // before the file starts
  })
})

describe('your exits vs the tested sell rule', () => {
  it('sells at the next open after a 5% fall or a 6% rise, else after 63 days', async () => {
    const { ruleExit } = await import('../lib/exits')
    const days = Array.from({ length: 80 }, (_, i) => `2026-${String(1 + Math.floor(i / 28)).padStart(2, '0')}-${String(1 + (i % 28)).padStart(2, '0')}`)
    const flat = { t: days, o: days.map(() => 100), h: days.map(() => 101), l: days.map(() => 99), c: days.map(() => 100), v: days.map(() => 1) }
    expect(ruleExit(flat, days[0]!)).toMatchObject({ ret: 0, why: '63 days', date: days[62] })
    const up = { ...flat, c: days.map((_, i) => (i === 3 ? 107 : 100)), o: days.map((_, i) => (i === 4 ? 108 : 100)) }
    expect(ruleExit(up, days[0]!)).toMatchObject({ why: 'take profit', date: days[4] })
    expect(ruleExit(up, days[0]!)!.ret).toBeCloseTo(0.08)
    const down = { ...flat, c: days.map((_, i) => (i === 2 ? 94 : 100)), o: days.map((_, i) => (i === 3 ? 90 : 100)) }
    expect(ruleExit(down, days[0]!)).toMatchObject({ why: 'stop', date: days[3] })
    expect(ruleExit(down, days[0]!)!.ret).toBeCloseTo(-0.1) // a gap below the stop counts
    expect(ruleExit({ ...flat, t: days.slice(0, 10), o: flat.o.slice(0, 10), c: flat.c.slice(0, 10) }, days[0]!)!.why).toBe('still holding')
  })
})

describe('your money month by month', () => {
  it('values your holdings and the same trades in the index at each month end', async () => {
    const { monthly } = await import('../lib/vsMarket')
    const spy = { dates: ['2026-10-01', '2026-10-30', '2026-11-30'], tr: [100, 110, 120], usd_per_eur: [1, 1, 1] }
    const buy: Trade = { id: 'b', date: '2026-10-01', side: 'buy', ticker: 'AAA', shares: 10, priceEur: 100, feeEur: 0 }
    const closes = new Map([['AAA', { t: ['2026-10-01', '2026-10-30', '2026-11-30'], c: [100, 105, 130] }]])
    const pts = monthly([buy], spy, closes)
    expect(pts.map((p) => p.month)).toEqual(['2026-10', '2026-11'])
    expect(pts[1]).toMatchObject({ paidIn: 1000, you: 1300 })
    expect(pts[1]!.market).toBeCloseTo(1200)
  })
})
