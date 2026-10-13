import { useEffect, useState } from 'react'
import type { ScreenerFile, ScreenerRow } from '../types'
import { fetchSiteJson, type Loadable } from './data'

export interface Screener {
  file: ScreenerFile
  rows: ScreenerRow[]
  fields: Set<string>
  byTicker: Map<string, ScreenerRow>
}

let cache: Promise<Loadable<Screener>> | null = null

export function toRows(file: ScreenerFile): ScreenerRow[] {
  return file.rows.map((r) => {
    const o: Record<string, unknown> = {}
    file.fields.forEach((f, i) => {
      o[f] = r[i] ?? null
    })
    return o as ScreenerRow
  })
}

async function load(): Promise<Loadable<Screener>> {
  const res = await fetchSiteJson<ScreenerFile>('screener.json')
  if (res.state !== 'ready') return res
  const rows = toRows(res.data)
  return {
    state: 'ready',
    data: { file: res.data, rows, fields: new Set(res.data.fields), byTicker: new Map(rows.map((r) => [r.ticker, r])) },
  }
}

/** screener.json, loaded once per page view and shared by every page that needs it. */
export function useScreener(enabled = true): Loadable<Screener> {
  const [state, setState] = useState<Loadable<Screener>>({ state: 'loading' })
  useEffect(() => {
    if (!enabled) return
    let alive = true
    if (!cache) cache = load()
    void cache.then((v) => {
      if (alive) setState(v)
      if (v.state === 'error') cache = null
    })
    return () => {
      alive = false
    }
  }, [enabled])
  return state
}

/** For tests. */
export function resetScreenerCache(): void {
  cache = null
}

// ---------------------------------------------------------------- filters

export type Filter =
  | { key: string; op: 'range'; min?: number; max?: number }
  | { key: string; op: 'in'; values: string[] }
  | { key: string; op: 'is'; value: boolean }
  | { key: string; op: 'withinDays'; days: number }

function daysFromToday(ymd: string): number {
  const d = new Date(`${ymd}T00:00:00Z`).getTime()
  const now = new Date()
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())
  return Math.round((d - today) / 86400000)
}

export function matches(row: ScreenerRow, f: Filter): boolean {
  const v = row[f.key]
  switch (f.op) {
    case 'range':
      if (typeof v !== 'number') return false
      return (f.min === undefined || v >= f.min) && (f.max === undefined || v <= f.max)
    case 'in':
      return typeof v === 'string' && f.values.includes(v)
    case 'is':
      return v === f.value
    case 'withinDays': {
      if (typeof v !== 'string') return false
      const d = daysFromToday(v)
      return d >= 0 && d <= f.days
    }
  }
}

export function searchMatches(row: ScreenerRow, q: string): boolean {
  if (!q) return true
  const s = q.trim().toUpperCase()
  if (!s) return true
  if (row.ticker.startsWith(s)) return true
  const name = typeof row.name === 'string' ? row.name.toUpperCase() : ''
  return name.includes(s)
}

// ---------------------------------------------------------------- presets

export interface Preset {
  id: string
  label: string
  help: string
  /** A view replaces the visible columns (the Forecast view). */
  view?: 'forecast'
  /** Fields that must exist in screener.json for the preset to work. */
  needs: string[]
  phase: number
  sort: { key: string; desc: boolean }
  filters: Filter[]
}

export const PRESETS: Preset[] = [
  {
    id: 'forecast',
    label: 'Forecast',
    help: 'Expected change, chance of rising and how often the app was right, for 1 week, 1 month, 3 months and 6 months.',
    needs: ['p_up_6m'],
    phase: 3,
    sort: { key: 'p_up_6m', desc: true },
    filters: [],
    view: 'forecast',
  },
  {
    id: 'likely',
    label: 'Most likely to rise',
    help: 'Eligible stocks ranked by the chance of being higher in 6 months.',
    needs: ['p_up_6m'],
    phase: 3,
    sort: { key: 'p_up_6m', desc: true },
    filters: [{ key: 'eligible', op: 'is', value: true }],
  },
  {
    id: 'upside',
    label: 'Biggest upside',
    help: 'Ranked by the optimistic (90th percentile) 6-month forecast.',
    needs: ['p90_6m'],
    phase: 3,
    sort: { key: 'p90_6m', desc: true },
    filters: [{ key: 'eligible', op: 'is', value: true }],
  },
  {
    id: 'fastest',
    label: 'Fastest',
    help: 'Expected gain per month per unit of monthly volatility.',
    needs: ['speed'],
    phase: 3,
    sort: { key: 'speed', desc: true },
    filters: [{ key: 'eligible', op: 'is', value: true }],
  },
  {
    id: 'safest',
    label: 'Safest',
    help: 'Volatility at most 25% a year and at least a 55% chance of being higher in 6 months.',
    needs: ['p_up_6m', 'vol_63'],
    phase: 3,
    sort: { key: 'p_up_6m', desc: true },
    filters: [
      { key: 'eligible', op: 'is', value: true },
      { key: 'vol_63', op: 'range', max: 0.25 },
      { key: 'p_up_6m', op: 'range', min: 0.55 },
    ],
  },
  {
    id: 'insiders',
    label: 'Insider buying',
    help: 'Opportunistic insider purchases in the last 90 days, largest first.',
    needs: ['insider_net_90d'],
    phase: 2,
    sort: { key: 'insider_net_90d', desc: true },
    filters: [{ key: 'insider_net_90d', op: 'range', min: 1 }],
  },
  {
    id: 'upgrading',
    label: 'Analysts upgrading',
    help: 'This year’s EPS estimate raised over the last 60 days.',
    needs: ['rev60'],
    phase: 2,
    sort: { key: 'rev60', desc: true },
    filters: [{ key: 'rev60', op: 'range', min: 0.0001 }],
  },
  {
    id: 'earnings',
    label: 'Earnings soon',
    help: 'Reporting in the next 7 days.',
    needs: ['next_earnings'],
    phase: 2,
    sort: { key: 'next_earnings', desc: false },
    filters: [{ key: 'next_earnings', op: 'withinDays', days: 7 }],
  },
  {
    id: 'avoid',
    label: 'Avoid',
    help: 'Stocks with a SELL / RISK WARNING label.',
    needs: ['label'],
    phase: 3,
    sort: { key: 'p_up_6m', desc: false },
    filters: [{ key: 'label', op: 'in', values: ['SELL / RISK WARNING'] }],
  },
]
