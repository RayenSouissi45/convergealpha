// Your trade journal: every real trade you make on finanzen.net zero, in euros, with why you did it
// and what would prove you wrong. Holdings, results, German tax and your behaviour are all worked
// out from it. Stored only in this browser; export it as a file to keep a copy.

import { useCallback, useEffect, useState } from 'react'
import type { ScreenerRow } from '../types'
import { capitalTax, taxOnGain, TAX_RULES, type TaxProfile } from './taxes'

export type Side = 'buy' | 'sell' | 'dividend'

/** What the app knew about the stock when you traded (to compare with later). */
export interface Snapshot {
  label?: string | null
  /** Evidence families F1..F6 (0..100). */
  f?: (number | null)[]
  p_up_1m?: number | null
  p10_1m?: number | null
  p25_1m?: number | null
  price_usd?: number | null
  fx?: number | null
  atr_usd?: number | null
  planned_exit_usd?: number | null
  ret_1w?: number | null
  ret_1m?: number | null
  opp?: string | null
  days_to_earnings?: number | null
}

/** Conditions that would prove a buy wrong; the app checks them every day. */
export const WRONG_IF = {
  label_sell: 'The label turns SELL / RISK WARNING',
  evidence_decay: '3 of 6 evidence families fall below 50',
  below_exit: 'The price falls below the planned exit level',
  earnings_miss: 'A weak earnings report (earnings family below 40)',
  analysts_cut: 'Analysts turn negative (opinion or revisions below 40)',
  insider_selling: 'Insiders sell on balance',
  red_badge: 'The opportunity badge turns red (hype)',
} as const
export type WrongIf = keyof typeof WRONG_IF

export interface Trade {
  id: string
  date: string // YYYY-MM-DD
  side: Side
  ticker: string
  /** Shares bought or sold (0 for a dividend). */
  shares: number
  /** Price per share in euros as filled on gettex (for a dividend: the gross amount in euros). */
  priceEur: number
  feeEur: number
  /** Dividends: US tax already withheld, in euros. */
  withheldEur?: number
  reason?: string
  wrongIf?: WrongIf[]
  /** What the decision was based on: an app label, Plan, a strategy, or your own idea. */
  basis?: 'label' | 'plan' | 'strategy' | 'picks' | 'own'
  snapshot?: Snapshot
  /** You saw a warning (cooling-off, a rule) and went ahead anyway. */
  overrode?: string[]
  /** Converted from the old dollar portfolio with an assumed exchange rate: check the price. */
  fxGuessed?: boolean
}

/** Your own rules, written before you invest (an investment policy statement). */
export interface Rules {
  goal: string
  horizonYears: number
  /** The biggest fall of your whole portfolio you can live with, e.g. 0.2. */
  maxLoss: number
  maxPositions: number
  /** Most of the portfolio in one stock, e.g. 0.15. */
  maxPerStock: number
  maxTradesPerMonth: number
  /** Smallest order (finanzen.net zero: 500 € and up is free). */
  minOrderEur: number
  /** Wait this long before a buy after a big jump or several trades in a row. */
  coolingHours: number
  onlyZero: boolean
  noEarningsWithinDays: number
  createdOn: string | null
}

export const DEFAULT_RULES: Rules = {
  goal: '',
  horizonYears: 10,
  maxLoss: 0.2,
  maxPositions: 10,
  maxPerStock: 0.15,
  maxTradesPerMonth: 4,
  minOrderEur: 500,
  coolingHours: 24,
  onlyZero: true,
  noEarningsWithinDays: 5,
  createdOn: null,
}

export interface Journal {
  version: 1
  trades: Trade[]
  rules: Rules
  /** Cash at the broker, in euros (optional; for the total and the drawdown brake). */
  cashEur: number | null
  /** Highest total value seen (for the drawdown brake). */
  peakEur: number | null
}

export const EMPTY_JOURNAL: Journal = { version: 1, trades: [], rules: DEFAULT_RULES, cashEur: null, peakEur: null }

const KEY = 'ca-journal'
const OLD_PORTFOLIO = 'ca-portfolio'
/** Used only to convert holdings saved in dollars before the journal existed. */
export const MIGRATION_FX = 1.1

const isNum = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x)
const ymd = (x: unknown) => typeof x === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(x)

/** Never trust a stored or imported file: keep only well-formed trades and clamp the rules. */
export function parseJournal(v: unknown): Journal {
  if (!v || typeof v !== 'object') throw new Error('Not a journal file')
  const o = v as Partial<Journal>
  const trades = (Array.isArray(o.trades) ? o.trades : [])
    .filter((t): t is Trade => !!t && typeof t.id === 'string' && ymd(t.date) && (t.side === 'buy' || t.side === 'sell' || t.side === 'dividend') && typeof t.ticker === 'string' && isNum(t.shares) && t.shares >= 0 && isNum(t.priceEur) && t.priceEur >= 0 && isNum(t.feeEur) && t.feeEur >= 0)
    .map((t) => ({ ...t, ticker: t.ticker.toUpperCase().trim(), wrongIf: (t.wrongIf ?? []).filter((w): w is WrongIf => w in WRONG_IF) }))
  const r = { ...DEFAULT_RULES, ...(o.rules ?? {}) }
  const clamp = (x: unknown, lo: number, hi: number, d: number) => (isNum(x) ? Math.min(hi, Math.max(lo, x)) : d)
  const rules: Rules = {
    goal: typeof r.goal === 'string' ? r.goal.slice(0, 500) : '',
    horizonYears: Math.round(clamp(r.horizonYears, 1, 60, DEFAULT_RULES.horizonYears)),
    maxLoss: clamp(r.maxLoss, 0.01, 1, DEFAULT_RULES.maxLoss),
    maxPositions: Math.round(clamp(r.maxPositions, 1, 100, DEFAULT_RULES.maxPositions)),
    maxPerStock: clamp(r.maxPerStock, 0.01, 1, DEFAULT_RULES.maxPerStock),
    maxTradesPerMonth: Math.round(clamp(r.maxTradesPerMonth, 0, 1000, DEFAULT_RULES.maxTradesPerMonth)),
    minOrderEur: clamp(r.minOrderEur, 0, 1_000_000, DEFAULT_RULES.minOrderEur),
    coolingHours: clamp(r.coolingHours, 0, 720, DEFAULT_RULES.coolingHours),
    onlyZero: typeof r.onlyZero === 'boolean' ? r.onlyZero : DEFAULT_RULES.onlyZero,
    noEarningsWithinDays: Math.round(clamp(r.noEarningsWithinDays, 0, 30, DEFAULT_RULES.noEarningsWithinDays)),
    createdOn: ymd(r.createdOn) ? (r.createdOn as string) : null,
  }
  return { version: 1, trades: sortTrades(trades), rules, cashEur: isNum(o.cashEur) ? o.cashEur : null, peakEur: isNum(o.peakEur) ? o.peakEur : null }
}

export const sortTrades = (ts: Trade[]) => [...ts].sort((a, b) => (a.date === b.date ? (a.side === b.side ? 0 : a.side === 'buy' ? -1 : 1) : a.date < b.date ? -1 : 1))

/** Holdings saved by the old dollar portfolio become buys in the journal (price converted at an
 * assumed rate and flagged, so you can correct it). */
export function migrateOld(raw: unknown): Trade[] {
  if (!raw || typeof raw !== 'object') return []
  const hs = (raw as { holdings?: unknown[] }).holdings
  if (!Array.isArray(hs)) return []
  return hs
    .filter((h): h is { ticker: string; shares: number; entryPrice: number; entryDate: string; exitLevel?: number | null; atrAtEntry?: number | null; p25MonthAtEntry?: number | null } => !!h && typeof (h as { ticker?: unknown }).ticker === 'string' && isNum((h as { shares?: unknown }).shares) && isNum((h as { entryPrice?: unknown }).entryPrice) && ymd((h as { entryDate?: unknown }).entryDate))
    .map((h, i) => ({
      id: `migrated-${i}-${h.ticker}`,
      date: h.entryDate,
      side: 'buy' as const,
      ticker: h.ticker.toUpperCase(),
      shares: h.shares,
      priceEur: h.entryPrice / MIGRATION_FX,
      feeEur: 0,
      basis: 'own' as const,
      fxGuessed: true,
      snapshot: { price_usd: h.entryPrice, fx: MIGRATION_FX, planned_exit_usd: h.exitLevel ?? null, atr_usd: h.atrAtEntry ?? null, p25_1m: h.p25MonthAtEntry ?? null },
    }))
}

export function loadJournal(): Journal {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) return parseJournal(JSON.parse(raw) as unknown)
    const old = localStorage.getItem(OLD_PORTFOLIO)
    if (old) {
      const o = JSON.parse(old) as { equity?: unknown }
      const trades = migrateOld(JSON.parse(old))
      if (trades.length) return { ...EMPTY_JOURNAL, trades: sortTrades(trades), cashEur: null, peakEur: isNum(o.equity) ? o.equity / MIGRATION_FX : null }
    }
  } catch {
    // A broken file: start empty rather than crash (the old data stays in storage).
  }
  return EMPTY_JOURNAL
}

function save(j: Journal): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(j))
  } catch {
    // Storage blocked: changes last for this visit only.
  }
}

export function useJournal(): [Journal, (j: Journal) => void] {
  const [state, setState] = useState<Journal>(loadJournal)
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === KEY) setState(loadJournal())
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])
  const set = useCallback((j: Journal) => {
    const next = { ...j, trades: sortTrades(j.trades) }
    setState(next)
    save(next)
  }, [])
  return [state, set]
}

export const newId = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`

// ---------------------------------------------------------------- first in, first out

export interface Lot {
  tradeId: string
  date: string
  shares: number
  /** Euros paid for these shares, the buy fee included. */
  costEur: number
}

export interface Realized {
  tradeId: string
  date: string
  ticker: string
  shares: number
  /** Euros received, the sell fee taken off. */
  proceedsEur: number
  costEur: number
  gainEur: number
  /** Days from the earliest lot sold to the sale. */
  daysHeld: number
  /** The buy trade(s) this sale closed (first in, first out). */
  fromTrades: string[]
}

export interface Book {
  open: Map<string, Lot[]>
  realized: Realized[]
  dividends: Trade[]
  /** Sells of more shares than you held (a typo or a missing buy). */
  problems: string[]
}

const days = (a: string, b: string) => Math.round((new Date(`${b}T00:00:00Z`).getTime() - new Date(`${a}T00:00:00Z`).getTime()) / 86400000)

/** German law: shares held in a collective deposit count as sold first in, first out. */
export function fifo(trades: Trade[]): Book {
  const open = new Map<string, Lot[]>()
  const realized: Realized[] = []
  const dividends: Trade[] = []
  const problems: string[] = []
  for (const t of sortTrades(trades)) {
    if (t.side === 'dividend') {
      dividends.push(t)
      continue
    }
    const lots = open.get(t.ticker) ?? []
    if (t.side === 'buy') {
      if (t.shares > 0) lots.push({ tradeId: t.id, date: t.date, shares: t.shares, costEur: t.shares * t.priceEur + t.feeEur })
      open.set(t.ticker, lots)
      continue
    }
    let left = t.shares
    let cost = 0
    let first: string | null = null
    const from: string[] = []
    while (left > 1e-9 && lots.length) {
      const lot = lots[0] as Lot
      const take = Math.min(left, lot.shares)
      const part = lot.costEur * (take / lot.shares)
      cost += part
      first = first ?? lot.date
      from.push(lot.tradeId)
      lot.costEur -= part
      lot.shares -= take
      left -= take
      if (lot.shares <= 1e-9) lots.shift()
    }
    const sold = t.shares - left
    if (left > 1e-9) problems.push(`${t.date}: sold ${t.shares} ${t.ticker} but held only ${sold.toFixed(4).replace(/\.?0+$/, '')}`)
    if (sold > 0) {
      const proceeds = sold * t.priceEur - t.feeEur * (sold / t.shares)
      realized.push({ tradeId: t.id, date: t.date, ticker: t.ticker, shares: sold, proceedsEur: proceeds, costEur: cost, gainEur: proceeds - cost, daysHeld: first ? days(first, t.date) : 0, fromTrades: from })
    }
    if (lots.length) open.set(t.ticker, lots)
    else open.delete(t.ticker)
  }
  return { open, realized, dividends, problems }
}

// ---------------------------------------------------------------- positions now

export interface Position {
  ticker: string
  shares: number
  costEur: number
  firstDate: string
  /** Latest price in euros (US price ÷ EUR/USD); null without data. */
  priceEur: number | null
  valueEur: number | null
  gainEur: number | null
  gainPct: number | null
  /** The buy that opened the oldest lot (its reason, snapshot and checks). */
  buy: Trade | undefined
  row: ScreenerRow | undefined
}

export function positions(j: Journal, rows: Map<string, ScreenerRow>, fx: number | null): Position[] {
  const book = fifo(j.trades)
  const byId = new Map(j.trades.map((t) => [t.id, t]))
  return [...book.open.entries()].map(([ticker, lots]) => {
    const shares = lots.reduce((s, l) => s + l.shares, 0)
    const costEur = lots.reduce((s, l) => s + l.costEur, 0)
    const row = rows.get(ticker)
    const px = typeof row?.price === 'number' && fx ? row.price / fx : null
    const value = px !== null ? px * shares : null
    return {
      ticker,
      shares,
      costEur,
      firstDate: lots[0]?.date ?? '',
      priceEur: px,
      valueEur: value,
      gainEur: value !== null ? value - costEur : null,
      gainPct: value !== null && costEur > 0 ? value / costEur - 1 : null,
      buy: byId.get(lots[0]?.tradeId ?? ''),
      row,
    }
  })
}

// ---------------------------------------------------------------- thesis checks

export interface ThesisCheck {
  key: WrongIf
  text: string
  broken: boolean | null
  detail: string
}

const fam = (row: ScreenerRow | undefined, k: string) => (row && typeof row[k] === 'number' ? (row[k] as number) : null)

/** Your "I'm wrong if…" conditions, checked against today's data. */
export function thesis(p: Position): ThesisCheck[] {
  const row = p.row
  const s = p.buy?.snapshot
  return (p.buy?.wrongIf ?? []).map((key) => {
    let broken: boolean | null = null
    let detail = 'no data today'
    if (row) {
      if (key === 'label_sell') {
        broken = row.label === 'SELL / RISK WARNING'
        detail = `label ${String(row.label ?? '—')}`
      } else if (key === 'evidence_decay') {
        const weak = ['f1', 'f2', 'f3', 'f4', 'f5', 'f6'].filter((f) => (fam(row, f) ?? 100) < 50).length
        broken = weak >= 3
        detail = `${weak} of 6 families below 50`
      } else if (key === 'below_exit') {
        const exit = s?.planned_exit_usd
        if (typeof exit === 'number' && typeof row.price === 'number') {
          broken = row.price <= exit
          detail = `$${row.price.toFixed(2)} vs exit $${exit.toFixed(2)}`
        }
      } else if (key === 'earnings_miss') {
        const f3 = fam(row, 'f3')
        if (f3 !== null) {
          broken = f3 < 40
          detail = `earnings family ${Math.round(f3)}`
        }
      } else if (key === 'analysts_cut') {
        const f1 = fam(row, 'f1')
        const f2 = fam(row, 'f2')
        if (f1 !== null || f2 !== null) {
          broken = (f1 ?? 100) < 40 || (f2 ?? 100) < 40
          detail = `opinion ${f1 === null ? '—' : Math.round(f1)}, revisions ${f2 === null ? '—' : Math.round(f2)}`
        }
      } else if (key === 'insider_selling') {
        const n = fam(row, 'insider_net_90d')
        if (n !== null) {
          broken = n < 0
          detail = n < 0 ? 'insiders sold more than they bought (90 days)' : 'no net insider selling'
        }
      } else if (key === 'red_badge') {
        broken = row.opp === 'red'
        detail = `badge ${String(row.opp ?? 'none')}`
      }
    }
    return { key, text: WRONG_IF[key], broken, detail }
  })
}

/** Evidence families that fell by 15 points or more since you bought. */
export function evidenceChanges(p: Position): { family: string; then: number; now: number }[] {
  const then = p.buy?.snapshot?.f
  if (!then || !p.row) return []
  const out: { family: string; then: number; now: number }[] = []
  ;['f1', 'f2', 'f3', 'f4', 'f5', 'f6'].forEach((k, i) => {
    const a = then.at(i)
    const b = fam(p.row, k)
    if (typeof a === 'number' && b !== null && a - b >= 15) out.push({ family: k.toUpperCase(), then: a, now: b })
  })
  return out
}

/** Is today's move normal for this stock? Its usual daily move is its yearly volatility ÷ √252. */
export function normalDay(row: ScreenerRow | undefined): { move: number; usual: number; unusual: boolean } | null {
  if (!row || typeof row.change_1d !== 'number' || typeof row.vol_63 !== 'number' || !(row.vol_63 > 0)) return null
  const usual = row.vol_63 / Math.sqrt(252)
  return { move: row.change_1d, usual, unusual: Math.abs(row.change_1d) > 2 * usual }
}

// ---------------------------------------------------------------- taxes per year

export interface TaxYear {
  year: number
  stockGains: number
  stockLosses: number
  /** Stock gains minus stock losses (stock losses only offset stock gains). */
  stockNet: number
  dividends: number
  withheld: number
  /** Allowance this year (single or joint). */
  allowance: number
  allowanceUsed: number
  taxable: number
  estimatedTax: number
  /** Stock losses left over, carried to next year. */
  lossCarry: number
}

export function taxYears(j: Journal, profile: TaxProfile): TaxYear[] {
  const book = fifo(j.trades)
  const years = [...new Set([...book.realized.map((r) => Number(r.date.slice(0, 4))), ...book.dividends.map((d) => Number(d.date.slice(0, 4)))])].sort()
  const allowance = TAX_RULES.allowance[profile.filing]
  let carry = 0
  return years.map((year) => {
    const rs = book.realized.filter((r) => r.date.startsWith(String(year)))
    const gains = rs.filter((r) => r.gainEur > 0).reduce((s, r) => s + r.gainEur, 0)
    const losses = -rs.filter((r) => r.gainEur < 0).reduce((s, r) => s + r.gainEur, 0)
    const ds = book.dividends.filter((d) => d.date.startsWith(String(year)))
    const div = ds.reduce((s, d) => s + d.priceEur, 0)
    const withheld = ds.reduce((s, d) => s + (d.withheldEur ?? 0), 0)
    const stockNetRaw = gains - losses - carry
    const stockNet = Math.max(0, stockNetRaw)
    const lossCarry = Math.max(0, -stockNetRaw)
    const income = stockNet + div
    const allowanceUsed = Math.min(allowance, income)
    const taxable = income - allowanceUsed
    const credit = div > 0 && income > 0 ? withheld * (taxable / income) : 0
    const estimatedTax = capitalTax(taxable, profile.church, Math.min(credit, taxable * 0.15)).total
    carry = lossCarry
    return { year, stockGains: gains, stockLosses: losses, stockNet, dividends: div, withheld, allowance, allowanceUsed, taxable, estimatedTax, lossCarry }
  })
}

/** Tax saved by selling a losing position before the year ends, given this year's net stock gain. */
export function harvestSaving(netGainThisYear: number, unrealizedLoss: number, profile: TaxProfile): number {
  if (!(unrealizedLoss < 0) || !(netGainThisYear > 0)) return 0
  const before = taxOnGain(netGainThisYear, profile).tax
  const after = taxOnGain(Math.max(0, netGainThisYear + unrealizedLoss), profile).tax
  return before - after
}

// ---------------------------------------------------------------- behaviour

export interface Behaviour {
  tradesLast30: number
  feesThisYear: number
  /** Buys right after a big rise (1 week +10% or 1 month +25%). */
  chasedBuys: number
  /** Sells right after a big fall (1 week −8%). */
  panicSells: number
  /** Average days held: sold winners vs sold losers (selling winners too early shows up here). */
  winnersHeldDays: number | null
  losersHeldDays: number | null
  /** Trades made despite a warning. */
  overrides: number
  /** Results of trades made despite a warning vs without one (average euros). */
  overrideAvg: number | null
  plainAvg: number | null
}

export function behaviour(j: Journal, today = new Date()): Behaviour {
  const book = fifo(j.trades)
  const cutoff = new Date(today.getTime() - 30 * 86400000).toISOString().slice(0, 10)
  const year = String(today.getUTCFullYear())
  const trades = j.trades.filter((t) => t.side !== 'dividend')
  const sells = new Map(trades.filter((t) => t.side === 'sell').map((t) => [t.id, t]))
  const avg = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null)
  const won = book.realized.filter((r) => r.gainEur > 0)
  const lost = book.realized.filter((r) => r.gainEur <= 0)
  const overrideIds = new Set(trades.filter((t) => t.overrode?.length).map((t) => t.id))
  const outcomeOf = (buyId: string) => book.realized.filter((r) => r.fromTrades.includes(buyId)).reduce((s, r) => s + r.gainEur, 0)
  const closed = trades.filter((t) => t.side === 'buy' && book.realized.some((r) => r.fromTrades.includes(t.id)))
  return {
    tradesLast30: trades.filter((t) => t.date >= cutoff).length,
    feesThisYear: trades.filter((t) => t.date.startsWith(year)).reduce((s, t) => s + t.feeEur, 0),
    chasedBuys: trades.filter((t) => t.side === 'buy' && ((t.snapshot?.ret_1w ?? 0) > 0.1 || (t.snapshot?.ret_1m ?? 0) > 0.25)).length,
    panicSells: [...sells.values()].filter((t) => (t.snapshot?.ret_1w ?? 0) < -0.08).length,
    winnersHeldDays: avg(won.map((r) => r.daysHeld)),
    losersHeldDays: avg(lost.map((r) => r.daysHeld)),
    overrides: overrideIds.size,
    overrideAvg: avg(closed.filter((t) => overrideIds.has(t.id)).map((t) => outcomeOf(t.id))),
    plainAvg: avg(closed.filter((t) => !overrideIds.has(t.id)).map((t) => outcomeOf(t.id))),
  }
}

/** A decision is judged by how it was made, not only by how it turned out: a reason, a "wrong if"
 * condition, an evidence basis and no ignored warning. */
export function processScore(t: Trade): { good: boolean; missing: string[] } {
  const missing: string[] = []
  if (!t.reason || t.reason.trim().length < 8) missing.push('a written reason')
  if (t.side === 'buy' && !(t.wrongIf?.length)) missing.push('a "wrong if" condition')
  if (!t.basis || t.basis === 'own') missing.push('a basis in the app\'s evidence')
  if (t.overrode?.length) missing.push('no ignored warning')
  return { good: missing.length === 0, missing }
}

export type Quadrant = 'skill' | 'unlucky' | 'lucky' | 'mistake'

/** Closed buys sorted into good/bad decision × good/bad result. */
export function decisionQuality(j: Journal): { trade: Trade; gainEur: number; quadrant: Quadrant }[] {
  const book = fifo(j.trades)
  return j.trades
    .filter((t) => t.side === 'buy')
    .map((t) => ({ t, rs: book.realized.filter((r) => r.fromTrades.includes(t.id)) }))
    .filter((x) => x.rs.length > 0)
    .map(({ t, rs }) => {
      const gain = rs.reduce((s, r) => s + r.gainEur, 0)
      const good = processScore(t).good
      const quadrant: Quadrant = good ? (gain > 0 ? 'skill' : 'unlucky') : gain > 0 ? 'lucky' : 'mistake'
      return { trade: t, gainEur: gain, quadrant }
    })
}

// ---------------------------------------------------------------- before a trade

export interface Check {
  ok: boolean
  /** A hard rule of yours vs a warning. */
  rule: boolean
  text: string
}

export interface PlannedTrade {
  side: 'buy' | 'sell'
  ticker: string
  amountEur: number
  row: ScreenerRow | undefined
}

/** Your rules and the app's warnings, checked before you trade. */
export function preTradeChecks(t: PlannedTrade, j: Journal, ps: Position[], now = new Date()): Check[] {
  const r = j.rules
  const checks: Check[] = []
  const row = t.row
  const total = ps.reduce((s, p) => s + (p.valueEur ?? p.costEur), 0) + (j.cashEur ?? 0)
  if (t.side === 'buy') {
    const held = ps.some((p) => p.ticker === t.ticker)
    const n = ps.length + (held ? 0 : 1)
    checks.push({ ok: n <= r.maxPositions, rule: true, text: `Stocks held after this buy: ${n} (your limit ${r.maxPositions})` })
    if (ps.length === 0 && j.cashEur === null) {
      checks.push({ ok: true, rule: true, text: `First stock: enter your cash at the broker (Holdings) to check your ${(r.maxPerStock * 100).toFixed(0)}% per-stock limit` })
    } else if (total > 0 || t.amountEur > 0) {
      const cur = ps.find((p) => p.ticker === t.ticker)?.valueEur ?? 0
      // Without your cash the share is of your stocks only (the buy adds to them).
      const share = (cur + t.amountEur) / (total + (j.cashEur === null ? t.amountEur : 0))
      const of = j.cashEur === null ? 'of your stocks' : 'of your money'
      checks.push({ ok: share <= r.maxPerStock + 1e-9, rule: true, text: `${t.ticker} would be ${(share * 100).toFixed(0)}% ${of} (your limit ${(r.maxPerStock * 100).toFixed(0)}%)` })
    }
    checks.push({ ok: t.amountEur >= r.minOrderEur, rule: true, text: `Order of ${Math.round(t.amountEur)} € (your minimum ${Math.round(r.minOrderEur)} €${r.minOrderEur >= 500 ? ': free on finanzen.net zero' : ''})` })
    if (row) {
      if (r.onlyZero) checks.push({ ok: row.zero === true, rule: true, text: row.zero === true ? 'On finanzen.net zero' : row.zero === null ? 'Not sure it is on finanzen.net zero' : 'Not on finanzen.net zero' })
      const de = typeof row.days_to_earnings === 'number' ? row.days_to_earnings : null
      checks.push({ ok: de === null || de > r.noEarningsWithinDays, rule: true, text: de === null ? 'No earnings date known' : `Earnings in ${de} trading days (your rule: not within ${r.noEarningsWithinDays})` })
      checks.push({ ok: row.label !== 'SELL / RISK WARNING', rule: false, text: `App label: ${String(row.label ?? '—')}` })
      checks.push({ ok: row.opp !== 'red', rule: false, text: row.opp === 'red' ? 'Red badge: looks like hype, be careful' : 'No hype warning' })
    }
  }
  const month = now.toISOString().slice(0, 7)
  const thisMonth = j.trades.filter((x) => x.side !== 'dividend' && x.date.startsWith(month)).length
  checks.push({ ok: thisMonth + 1 <= r.maxTradesPerMonth, rule: true, text: `Trades this month including this one: ${thisMonth + 1} (your limit ${r.maxTradesPerMonth})` })
  return checks
}

/** Reasons to wait before acting (cooling-off): a big jump just before buying, or many trades. */
export function coolingOff(t: PlannedTrade, j: Journal, now = new Date()): string[] {
  const out: string[] = []
  const row = t.row
  const hours = j.rules.coolingHours
  if (hours <= 0) return out
  if (t.side === 'buy' && row) {
    if (typeof row.ret_1w === 'number' && row.ret_1w > 0.1) out.push(`It rose ${(row.ret_1w * 100).toFixed(0)}% this week: wait ${hours} hours and decide again with a cool head.`)
    if (typeof row.change_1d === 'number' && Math.abs(row.change_1d) > 0.07) out.push(`It moved ${(row.change_1d * 100).toFixed(0)}% today: big moves trigger quick decisions that are often regretted.`)
  }
  if (t.side === 'sell' && row && typeof row.ret_1w === 'number' && row.ret_1w < -0.08) out.push(`It fell ${(-row.ret_1w * 100).toFixed(0)}% this week: is your reason broken, or is this a normal dip? Check the holding first.`)
  const since = new Date(now.getTime() - hours * 3600000).toISOString().slice(0, 10)
  const recent = j.trades.filter((x) => x.side !== 'dividend' && x.date >= since).length
  if (recent >= 2) out.push(`You already made ${recent} trades since ${since}: slow down.`)
  return out
}

// ---------------------------------------------------------------- export

export function toCsv(j: Journal): string {
  const book = fifo(j.trades)
  const real = new Map(book.realized.map((r) => [r.tradeId, r]))
  const head = 'date,side,ticker,shares,price_eur,fee_eur,withheld_eur,cost_eur_fifo,proceeds_eur,gain_eur,reason'
  const esc = (s: string) => `"${s.replace(/"/g, '""')}"`
  const lines = j.trades.map((t) => {
    const r = real.get(t.id)
    return [t.date, t.side, t.ticker, t.shares, t.priceEur.toFixed(4), t.feeEur.toFixed(2), (t.withheldEur ?? 0).toFixed(2), r ? r.costEur.toFixed(2) : '', r ? r.proceedsEur.toFixed(2) : '', r ? r.gainEur.toFixed(2) : '', esc(t.reason ?? '')].join(',')
  })
  return [head, ...lines].join('\n')
}
