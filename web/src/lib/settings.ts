// Your trading settings (fees, whole or fractional shares, amount, Plan sliders), shared by the
// Plan and Strategies pages and remembered in this browser only. Storage can be blocked (private
// mode): then the choices last for this visit.

import { useSyncExternalStore } from 'react'
import { formatEur, ZERO_FEES, type Fees } from './costs'

export interface TradeSettings {
  /** finanzen.net zero's rule (0 € from 500 €, 1 € below) or your own flat fee. */
  feeRule: 'zero' | 'custom'
  feeBuy: number
  feeSell: number
  fractional: boolean
  amount: number
  safety: number
  upside: number
  days: number
  allowEarnings: boolean
}

export const DEFAULT_SETTINGS: TradeSettings = {
  feeRule: 'zero',
  feeBuy: 1,
  feeSell: 1,
  fractional: false,
  amount: 200,
  safety: 5,
  upside: 5,
  days: 30,
  allowEarnings: false,
}

const KEY = 'ca-trade-settings'
const listeners = new Set<() => void>()
let current: TradeSettings | null = null

function clamp(v: unknown, lo: number, hi: number, fallback: number): number {
  const n = typeof v === 'number' && Number.isFinite(v) ? v : fallback
  return Math.min(hi, Math.max(lo, n))
}

/** Never trust stored values: clamp everything to the ranges the page allows. */
export function sanitize(raw: Partial<TradeSettings> | null | undefined): TradeSettings {
  const d = DEFAULT_SETTINGS
  const r = raw ?? {}
  return {
    feeRule: r.feeRule === 'custom' ? 'custom' : 'zero',
    feeBuy: clamp(r.feeBuy, 0, 50, d.feeBuy),
    feeSell: clamp(r.feeSell, 0, 50, d.feeSell),
    fractional: typeof r.fractional === 'boolean' ? r.fractional : d.fractional,
    amount: clamp(r.amount, 1, 1_000_000, d.amount),
    safety: Math.round(clamp(r.safety, 1, 10, d.safety)),
    upside: Math.round(clamp(r.upside, 1, 10, d.upside)),
    days: Math.round(clamp(r.days, 5, 180, d.days)),
    allowEarnings: typeof r.allowEarnings === 'boolean' ? r.allowEarnings : d.allowEarnings,
  }
}

function read(): TradeSettings {
  try {
    const v = localStorage.getItem(KEY)
    return sanitize(v ? (JSON.parse(v) as Partial<TradeSettings>) : null)
  } catch {
    return { ...DEFAULT_SETTINGS }
  }
}

function snapshot(): TradeSettings {
  if (current === null) current = read()
  return current
}

export function setSettings(patch: Partial<TradeSettings>): void {
  current = sanitize({ ...snapshot(), ...patch })
  try {
    localStorage.setItem(KEY, JSON.stringify(current))
  } catch {
    // Storage blocked: the choice lasts for this visit only.
  }
  listeners.forEach((fn) => fn())
}

/** For tests. */
export function resetSettings(): void {
  current = null
}

export function useTradeSettings(): [TradeSettings, (patch: Partial<TradeSettings>) => void] {
  const s = useSyncExternalStore(
    (fn) => {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
    snapshot,
    () => DEFAULT_SETTINGS,
  )
  return [s, setSettings]
}

/** The fees your settings describe, for every euro calculation. */
export function feesFrom(s: TradeSettings): Fees {
  if (s.feeRule === 'zero') return { ...ZERO_FEES, fractional: s.fractional }
  return { buy: s.feeBuy, sell: s.feeSell, fractional: s.fractional, freeFrom: null }
}

/** One line: the fee rule in use. */
export function feeText(s: TradeSettings): string {
  const shares = s.fractional ? 'fractional shares (simulation only)' : 'whole shares'
  if (s.feeRule === 'zero') return `finanzen.net zero fees (free from ${formatEur(ZERO_FEES.freeFrom ?? 500, 0)}, else ${formatEur(ZERO_FEES.buy)}), ${shares}`
  return `${formatEur(s.feeBuy)} per buy, ${formatEur(s.feeSell)} per sell, ${shares}`
}

