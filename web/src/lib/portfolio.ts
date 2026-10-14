// Holding rules (HOLD / ROTATE / SELL), portfolio limits and the drawdown brake. Your holdings come
// from the trade journal (lib/journal.ts), stored only in this browser.
import type { ScreenerRow } from '../types'
import { useFx } from './fx'
import { fifo, MIGRATION_FX, useJournal, type Journal } from './journal'

export interface Holding {
  ticker: string
  shares: number
  entryPrice: number
  entryDate: string // YYYY-MM-DD
  /** Planned exit level at entry (max(E − 2·ATR, 0.92·E)). */
  exitLevel: number | null
  /** ATR at entry, for the break-even and sell-a-third levels. */
  atrAtEntry: number | null
  /** 1-month 25th-percentile forecast at entry (for ROTATE). */
  p25MonthAtEntry: number | null
  highestClose?: number | null
}

export interface PortfolioState {
  version: 1
  equity: number | null
  peakEquity: number | null
  holdings: Holding[]
}

const EMPTY: PortfolioState = { version: 1, equity: null, peakEquity: null, holdings: [] }

/** The old dollar portfolio file (still read by the journal once, to move its holdings over). */
export function parsePortfolio(v: unknown): PortfolioState {
  if (!v || typeof v !== 'object') throw new Error('Not a portfolio file')
  const o = v as Partial<PortfolioState>
  const holdings = Array.isArray(o.holdings) ? o.holdings : []
  const clean = holdings
    .filter((h): h is Holding => !!h && typeof h.ticker === 'string' && Number.isFinite(h.shares) && Number.isFinite(h.entryPrice))
    .map((h) => ({ ...h, ticker: h.ticker.toUpperCase() }))
  const num = (x: unknown) => (typeof x === 'number' && Number.isFinite(x) ? x : null)
  return { ...EMPTY, equity: num(o.equity), peakEquity: num(o.peakEquity), holdings: clean }
}

/** Your open positions from the journal, in the shape the holding rules use (prices in dollars,
 * from what the app knew when you bought). */
export function journalHoldings(j: Journal, fx: number | null): Holding[] {
  const book = fifo(j.trades)
  const byId = new Map(j.trades.map((t) => [t.id, t]))
  return [...book.open.entries()].map(([ticker, lots]) => {
    const first = lots[0]
    const buy = first ? byId.get(first.tradeId) : undefined
    const shares = lots.reduce((s, l) => s + l.shares, 0)
    const costEur = lots.reduce((s, l) => s + l.costEur, 0)
    const rate = buy?.snapshot?.fx ?? fx ?? MIGRATION_FX
    return {
      ticker,
      shares,
      entryPrice: buy?.snapshot?.price_usd ?? (shares > 0 ? (costEur / shares) * rate : 0),
      entryDate: first?.date ?? '',
      exitLevel: buy?.snapshot?.planned_exit_usd ?? null,
      atrAtEntry: buy?.snapshot?.atr_usd ?? null,
      p25MonthAtEntry: buy?.snapshot?.p25_1m ?? null,
    }
  })
}

/** Read-only view of your holdings for Today and the stock pages. */
export function usePortfolioView(): PortfolioState {
  const [j] = useJournal()
  const fx = useFx()
  // Real money only: paper trades never count as holdings.
  return { ...EMPTY, holdings: journalHoldings({ ...j, trades: j.trades.filter((t) => !t.paper) }, fx?.rate ?? null) }
}

/** Drawdown throttle: −10% from the peak -> half risk; −15% -> no new buys. */
export function throttle(p: PortfolioState): { factor: number; drawdown: number | null; text: string } {
  if (p.equity === null || p.peakEquity === null || p.peakEquity <= 0) return { factor: 1, drawdown: null, text: 'Enter your account value to track drawdown.' }
  const dd = p.equity / p.peakEquity - 1
  const eps = 1e-9 // -10% exactly must trigger, despite floating point
  if (dd <= -0.15 + eps) return { factor: 0, drawdown: dd, text: 'Down 15% or more from the peak: no new buys.' }
  if (dd <= -0.1 + eps) return { factor: 0.5, drawdown: dd, text: 'Down 10% or more from the peak: half risk on new buys.' }
  return { factor: 1, drawdown: dd, text: 'Normal risk.' }
}

/** Drift brake: when 3 or more model inputs look different from what the model learned on
 * (PSI above 0.25), new positions are sized at half until the next retraining. */
export const DRIFT_ALERTS = 3
export function driftBrake(drift: { alerts: string[] } | null | undefined): { factor: number; text: string | null } {
  const n = drift?.alerts.length ?? 0
  if (n >= DRIFT_ALERTS) return { factor: 0.5, text: `The market looks different from what the model learned on (${n} inputs drifted): new positions at half size until it is retrained.` }
  return { factor: 1, text: null }
}

const NEWS_BREAKERS: Record<string, string> = {
  guidance_down: 'guidance cut in the news',
  lawsuit: 'a lawsuit in the news',
  ceo_exit: 'the CEO or CFO is leaving',
  downgrade: 'an analyst downgrade',
  investigation: 'an investigation in the news',
  going_concern: 'a going-concern doubt',
  offering: 'a share sale (offering)',
  dividend_down: 'a dividend cut',
}

/** News and filings of the last days that can break the reason you bought. */
export function breakers(row: ScreenerRow | undefined): string[] {
  if (!row) return []
  const out: string[] = []
  const tags = typeof row.news_negative_tags === 'string' ? row.news_negative_tags.split(',') : []
  for (const t of tags) if (NEWS_BREAKERS[t]) out.push(NEWS_BREAKERS[t]!)
  if (row.officer_change === true) out.push('a director or officer change was filed (8-K 5.02)')
  if (row.impairment === true) out.push('an impairment was filed (8-K 2.06)')
  if (row.distress === 'high') out.push(`company finances look fragile${typeof row.distress_why === 'string' ? ` (${row.distress_why})` : ''}`)
  return out
}

// ---------------------------------------------------------------- holding labels

export type HoldingLabel = 'HOLD' | 'ROTATE' | 'SELL / RISK WARNING'

export interface HoldingStatus {
  label: HoldingLabel
  reasons: string[]
  actions: string[]
  price: number | null
  ret: number | null
  value: number | null
  openRisk: number | null
  tradingDaysHeld: number
}

function tradingDaysSince(ymd: string, today: Date = new Date()): number {
  const start = new Date(`${ymd}T00:00:00Z`)
  let n = 0
  for (let d = new Date(start); d < today; d.setUTCDate(d.getUTCDate() + 1)) {
    const wd = d.getUTCDay()
    if (wd !== 0 && wd !== 6) n++
  }
  return Math.max(0, n - 1)
}

const FAMS = ['f1', 'f2', 'f3', 'f4', 'f5', 'f6'] as const

export function holdingStatus(h: Holding, row: ScreenerRow | undefined, candidates: ScreenerRow[], today: Date = new Date()): HoldingStatus {
  const price = typeof row?.price === 'number' ? row.price : null
  const ret = price !== null ? price / h.entryPrice - 1 : null
  const days = tradingDaysSince(h.entryDate, today)
  const reasons: string[] = []
  const actions: string[] = []
  let label: HoldingLabel = 'HOLD'

  if (!row) {
    return { label: 'SELL / RISK WARNING', reasons: ['No current data for this stock (delisted, renamed or a data failure).'], actions: [], price, ret, value: null, openRisk: null, tradingDaysHeld: days }
  }
  if (price !== null && h.exitLevel !== null && price <= h.exitLevel) reasons.push(`Price is at or below your planned exit level (${h.exitLevel.toFixed(2)}).`)
  if (row.label === 'SELL / RISK WARNING') reasons.push('The stock has a risk warning.')
  if (row.blocked && typeof row.block_reason === 'string' && /offering|restatement|auditor|investigation|going-concern|late filing/.test(row.block_reason)) reasons.push(`Risk event: ${row.block_reason}.`)
  const weak = FAMS.filter((f) => typeof row[f] === 'number' && (row[f] as number) < 50).length
  if (weak >= 3) reasons.push(`Evidence decay: ${weak} of 6 evidence families are below 50.`)
  const stillCandidate = row.label === 'BUY' || row.label === 'STRONG BUY — TOP CONVICTION'
  if (days >= 60 && !stillCandidate) reasons.push('Time stop: held 60 trading days and no longer a candidate.')
  if (reasons.length) label = 'SELL / RISK WARNING'

  if (label === 'HOLD' && days >= 21 && ret !== null && h.p25MonthAtEntry !== null && ret < h.p25MonthAtEntry) {
    const mySpeed = typeof row.speed === 'number' ? row.speed : 0
    const better = candidates.filter((c) => c.ticker !== h.ticker && typeof c.speed === 'number' && (c.speed as number) >= 1.5 * Math.max(mySpeed, 0.0001))
    if (better.length) {
      label = 'ROTATE'
      reasons.push(`Below its own 1-month 25th-percentile forecast after ${days} trading days, and ${better.length} candidate(s) are at least 1.5× faster (e.g. ${better.slice(0, 3).map((b) => b.ticker).join(', ')}).`)
    }
  }
  if (h.atrAtEntry && price !== null) {
    if (price >= h.entryPrice + 1.5 * h.atrAtEntry) actions.push(`Move the stop to break-even (${h.entryPrice.toFixed(2)}): price is 1.5 ATR above entry.`)
    if (price >= h.entryPrice + 3 * h.atrAtEntry) actions.push(`Sell a third (reached entry + 3 ATR = ${(h.entryPrice + 3 * h.atrAtEntry).toFixed(2)}), then trail at the highest close − 3 ATR.`)
  }
  const value = price !== null ? price * h.shares : null
  const stop = h.exitLevel ?? h.entryPrice * 0.92
  const openRisk = price !== null ? Math.max(0, price - stop) * h.shares : null
  return { label, reasons, actions, price, ret, value, openRisk, tradingDaysHeld: days }
}

export interface LimitCheck {
  ok: boolean
  text: string
}

/** Portfolio limits for a new buy (R12). */
export function limitChecks(p: PortfolioState, rows: Map<string, ScreenerRow>, newRow: ScreenerRow, newValue: number, newRisk: number): LimitCheck[] {
  const eq = p.equity
  const checks: LimitCheck[] = []
  const n = p.holdings.length
  checks.push({ ok: n < 10, text: `Positions: ${n} of at most 10` })
  const today = new Date().toISOString().slice(0, 10)
  const todayBuys = p.holdings.filter((h) => h.entryDate === today).length
  checks.push({ ok: todayBuys < 3, text: `New buys today: ${todayBuys} of at most 3` })
  if (eq && eq > 0) {
    const sector = newRow.sector
    const sectorValue = p.holdings.reduce((s, h) => {
      const r = rows.get(h.ticker)
      return r && r.sector === sector && typeof r.price === 'number' ? s + r.price * h.shares : s
    }, 0)
    const share = (sectorValue + newValue) / eq
    checks.push({ ok: share <= 0.25, text: `${String(sector ?? 'Unknown sector')}: ${(share * 100).toFixed(0)}% of equity after this buy (limit 25%)` })
    const cluster = newRow.cluster
    if (cluster !== null && cluster !== undefined) {
      const cv = p.holdings.reduce((s, h) => {
        const r = rows.get(h.ticker)
        return r && r.cluster === cluster && typeof r.price === 'number' ? s + r.price * h.shares : s
      }, 0)
      const cs = (cv + newValue) / eq
      checks.push({ ok: cs <= 0.2, text: `Correlated group: ${(cs * 100).toFixed(0)}% of equity after this buy (limit 20%)` })
    }
    const risk = p.holdings.reduce((s, h) => {
      const r = rows.get(h.ticker)
      const price = typeof r?.price === 'number' ? r.price : h.entryPrice
      return s + Math.max(0, price - (h.exitLevel ?? h.entryPrice * 0.92)) * h.shares
    }, 0)
    const total = (risk + newRisk) / eq
    checks.push({ ok: total <= 0.06, text: `Total open risk: ${(total * 100).toFixed(1)}% of equity after this buy (limit 6%)` })
  }
  const t = throttle(p)
  checks.push({ ok: t.factor > 0, text: `Drawdown throttle: ${t.text}` })
  return checks
}
