// Portfolio risk in plain numbers: how bad a bad month could be, what a crash or an overnight gap
// would cost, and where the money is concentrated. Simple, transparent models; the page says so.

import type { ScreenerRow } from '../types'

export interface Holding {
  ticker: string
  valueEur: number
  row: ScreenerRow | undefined
}

/** Correlation assumed between two stocks: higher when they are in the same group of stocks that
 * moved together (the app's clusters) or the same sector; in a crash nearly everything moves together. */
export const RHO = { cluster: 0.7, sector: 0.5, other: 0.3, crash: 0.8 }
/** Average loss in the worst 5% of outcomes for a bell curve: σ × φ(1.645) / 0.05. */
export const CVAR95 = 2.0627
/** Used when a stock has no volatility figure (a typical US stock). */
export const DEFAULT_VOL = 0.35

const num = (row: ScreenerRow | undefined, k: string) => (row && typeof row[k] === 'number' && Number.isFinite(row[k]) ? (row[k] as number) : null)

function rho(a: ScreenerRow | undefined, b: ScreenerRow | undefined, crash: boolean): number {
  if (crash) return RHO.crash
  if (a?.cluster !== null && a?.cluster !== undefined && a.cluster === b?.cluster) return RHO.cluster
  if (a?.sector && a.sector === b?.sector) return RHO.sector
  return RHO.other
}

export interface RiskSummary {
  totalEur: number
  investedEur: number
  /** Monthly volatility of the whole portfolio (cash counts as riskless). */
  monthlyVol: number
  /** Average loss in the worst 1 in 20 months, as a share of the total and in euros. */
  cvar: number
  cvarEur: number
  /** The same if stocks start moving together, as they do in a crash. */
  cvarCrash: number
  cvarCrashEur: number
  /** A bad month (1 in 10) if every stock hits its own bad case at once (cautious). */
  badMonthEur: number
  /** Every stock falls 20% at once. */
  crash20Eur: number
  /** The biggest holding gaps 20% down overnight (a stop cannot help). */
  gapEur: number
  biggest: string | null
}

export function summary(hs: Holding[], cashEur = 0): RiskSummary {
  const invested = hs.reduce((s, h) => s + h.valueEur, 0)
  const total = invested + Math.max(0, cashEur)
  const w = hs.map((h) => (total > 0 ? h.valueEur / total : 0))
  const sig = hs.map((h) => (num(h.row, 'vol_63') ?? DEFAULT_VOL) / Math.sqrt(12))
  const variance = (crash: boolean) => {
    let v = 0
    for (let i = 0; i < hs.length; i++) {
      for (let k = 0; k < hs.length; k++) {
        const r = i === k ? 1 : rho(hs[i]?.row, hs[k]?.row, crash)
        v += (w[i] as number) * (w[k] as number) * (sig[i] as number) * (sig[k] as number) * r
      }
    }
    return v
  }
  const vol = Math.sqrt(variance(false))
  const volCrash = Math.sqrt(variance(true))
  const bad = hs.reduce((s, h) => s + h.valueEur * Math.min(0, num(h.row, 'p10_1m') ?? -0.15), 0)
  const big = [...hs].sort((a, b) => b.valueEur - a.valueEur)[0]
  return {
    totalEur: total,
    investedEur: invested,
    monthlyVol: vol,
    cvar: CVAR95 * vol,
    cvarEur: CVAR95 * vol * total,
    cvarCrash: CVAR95 * volCrash,
    cvarCrashEur: CVAR95 * volCrash * total,
    badMonthEur: bad,
    crash20Eur: -0.2 * invested,
    gapEur: big ? -0.2 * big.valueEur : 0,
    biggest: big?.ticker ?? null,
  }
}

export interface Exposure {
  name: string
  share: number
}

/** Sectors and groups of stocks that moved together, largest first. */
export function exposures(hs: Holding[]): { sectors: Exposure[]; clusters: Exposure[] } {
  const total = hs.reduce((s, h) => s + h.valueEur, 0)
  const group = (key: (h: Holding) => string | null) => {
    const m = new Map<string, number>()
    for (const h of hs) {
      const k = key(h)
      if (k === null) continue
      m.set(k, (m.get(k) ?? 0) + h.valueEur)
    }
    return [...m.entries()].map(([name, v]) => ({ name, share: total > 0 ? v / total : 0 })).sort((a, b) => b.share - a.share)
  }
  return {
    sectors: group((h) => (typeof h.row?.sector === 'string' ? h.row.sector : 'Unknown')),
    clusters: group((h) => (h.row?.cluster !== null && h.row?.cluster !== undefined ? `Group ${String(h.row.cluster)}` : null)),
  }
}

/** Hidden overlap: a portfolio that looks spread out by name but is one bet. */
export function overlapWarnings(hs: Holding[]): string[] {
  const out: string[] = []
  if (hs.length < 2) return out
  const { sectors, clusters } = exposures(hs)
  const s0 = sectors[0]
  if (s0 && s0.share >= 0.5) out.push(`${Math.round(s0.share * 100)}% is in one sector (${s0.name}).`)
  const c0 = clusters[0]
  if (c0 && c0.share >= 0.4) out.push(`${Math.round(c0.share * 100)}% is in stocks that usually move together (${c0.name}).`)
  const total = hs.reduce((s, h) => s + h.valueEur, 0)
  const share = (pred: (h: Holding) => boolean) => (total > 0 ? hs.filter(pred).reduce((s, h) => s + h.valueEur, 0) / total : 0)
  const mom = share((h) => (num(h.row, 'f5') ?? 0) >= 75)
  if (mom >= 0.7) out.push(`${Math.round(mom * 100)}% is in stocks with very strong recent trends: they tend to fall together when the trend turns.`)
  const wild = share((h) => (num(h.row, 'vol_63') ?? 0) >= 0.5)
  if (wild >= 0.5) out.push(`${Math.round(wild * 100)}% is in very volatile stocks (swings of 50%+ a year).`)
  return out
}

/** How many stocks an amount supports with orders big enough to be free (finanzen.net zero: 500 €). */
export function maxStocks(amountEur: number, minOrderEur: number): number {
  if (!(amountEur > 0)) return 0
  if (!(minOrderEur > 0)) return Infinity
  return Math.floor(amountEur / minOrderEur)
}

/** Before and after a planned buy (or sell) of `amountEur` of `row`. */
export function beforeAfter(hs: Holding[], cashEur: number | null, ticker: string, row: ScreenerRow | undefined, amountEur: number, side: 'buy' | 'sell') {
  const before = summary(hs, cashEur ?? 0)
  const cur = hs.find((h) => h.ticker === ticker)
  const delta = side === 'buy' ? amountEur : -Math.min(amountEur, cur?.valueEur ?? 0)
  const next = cur ? hs.map((h) => (h.ticker === ticker ? { ...h, valueEur: h.valueEur + delta } : h)).filter((h) => h.valueEur > 0.005) : [...hs, { ticker, valueEur: Math.max(0, delta), row }]
  // The money for a buy comes out of cash when you track it; a sale puts it back.
  const cashAfter = cashEur === null ? 0 : Math.max(0, cashEur - delta)
  const after = summary(next, cashAfter)
  return { before, after, positionsBefore: hs.length, positionsAfter: next.length }
}
