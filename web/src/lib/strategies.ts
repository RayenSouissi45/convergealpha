import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'
import type { Tone } from '../components/ui'
import type { StrategiesFile, StrategiesLiveFile, StrategyCard, StrategySuggestion } from '../types'
import { fetchSiteJson } from './data'
import { formatDay } from './format'

/** Which stocks a strategy may buy: only those on finanzen.net zero (the version you can copy),
 * or every stock the app covers (the same rules, for comparison). */
export type Universe = 'zero' | 'all'

export const UNIVERSE_LABEL: Record<Universe, string> = { zero: 'finanzen.net zero', all: 'All stocks' }

// Colour follows the strategy (fixed order, never its rank); both versions share it.
export const COLORS: Record<string, string> = {
  balanced: 'var(--viz-series-1)',
  high_risk: 'var(--viz-series-2)',
  safe_upside: 'var(--viz-series-3)',
  confidence: 'var(--viz-series-4)',
  opportunity: 'var(--viz-series-5)',
}

/** Version 2 (from 14 Oct 2026: 5,000 €, free orders from 500 €, the tested sell rule) or version 1
 * (the first rules, kept running unchanged so both can be compared live). */
export type Version = 1 | 2

/** The newest version once it has started, else version 1. */
export const defaultVersion = (f: StrategiesFile | null): Version => (f?.v2?.started ? 2 : 1)

/** The `v` URL parameter; the newest started version by default. */
export function useVersion(f: StrategiesFile | null): [Version, (v: Version) => void] {
  const [params, setParams] = useSearchParams()
  const def = defaultVersion(f)
  const raw = params.get('v')
  const v: Version = raw === '1' ? 1 : raw === '2' && f?.v2 ? 2 : def
  const set = (next: Version) =>
    setParams(
      (p) => {
        const q = new URLSearchParams(p)
        if (next === def) q.delete('v')
        else q.set('v', String(next))
        return q
      },
      { replace: true },
    )
  return [v, set]
}

/** The file seen through one version: its start, money, rate, rules and cards. */
export function viewOf(f: StrategiesFile, v: Version): StrategiesFile {
  const x = f.v2
  if (v === 1 || !x) return f
  return { ...f, start: x.start, capital: x.capital, fx: x.fx, costs: x.costs, shared_rules: x.shared_rules, benchmark: x.benchmark, strategies: x.strategies, strategies_all: x.strategies_all }
}

/** The live file with this version's S&P 500 yardstick. */
export const liveFor = (live: StrategiesLiveFile | null, v: Version): StrategiesLiveFile | null =>
  live && v === 2 ? { ...live, benchmark: live.benchmark_v2 ?? null } : live

/** "?stocks=all&v=1": only what differs from the defaults, so links stay short. */
export function strategyQuery(f: StrategiesFile, u: Universe, v: Version): string {
  const q = new URLSearchParams()
  if (u === 'all') q.set('stocks', 'all')
  if (v !== defaultVersion(f)) q.set('v', String(v))
  const s = q.toString()
  return s ? `?${s}` : ''
}

/** The `stocks` URL parameter (shareable, survives a reload); finanzen.net zero by default. */
export function useUniverse(): [Universe, (u: Universe) => void] {
  const [params, setParams] = useSearchParams()
  const u: Universe = params.get('stocks') === 'all' ? 'all' : 'zero'
  const set = (next: Universe) =>
    setParams(
      (p) => {
        const q = new URLSearchParams(p)
        if (next === 'all') q.set('stocks', 'all')
        else q.delete('stocks')
        return q
      },
      { replace: true },
    )
  return [u, set]
}

export const cardsFor = (f: StrategiesFile, u: Universe): StrategyCard[] => (u === 'all' ? (f.strategies_all ?? []) : f.strategies)

export const suggestionsFor = (f: StrategiesFile, u: Universe): Record<string, StrategySuggestion[]> =>
  u === 'all' ? (f.suggestions_all ?? {}) : f.suggestions

/** The same strategy in the other universe (null before the all-stocks versions existed). */
export function twinOf(f: StrategiesFile, s: StrategyCard): StrategyCard | null {
  const other: Universe = s.universe === 'all' ? 'zero' : 'all'
  return cardsFor(f, other).find((x) => x.id === s.id) ?? null
}

/** Ranked by value, best first; ties keep the fixed order (all start with the same money). */
export function byValue(cards: StrategyCard[]): StrategyCard[] {
  return cards
    .map((s, i) => ({ s, i }))
    .sort((a, b) => (b.s.value ?? 0) - (a.s.value ?? 0) || a.i - b.i)
    .map((x) => x.s)
}

// Ledger reasons are in the past tense (they also explain the fill later); before the fill they are plans.
export const planned = (reason: string) => reason.replace(/^Bought /, 'Buy ').replace(/^Sold /, 'Sell ')

export type StatusKind = 'locked' | 'changing' | 'buying' | 'invested' | 'cash'

export interface Status {
  kind: StatusKind
  tone: Tone
  /** Short, for the pill. */
  label: string
  /** One plain sentence: what the money is doing now. */
  text: string
}

const shortDay = (ymd: string) => formatDay(ymd).replace(/, \d{4}$/, '')

/** What the money is doing, at a glance. */
export function statusOf(s: StrategyCard): Status {
  if (s.locked) return { kind: 'locked', tone: 'bad', label: 'Stopped', text: 'Stopped: its rules changed without a new version, so it does not trade.' }
  const next = s.pending[0]?.fill_on
  const n = s.holdings.length
  const held = n ? `Holds ${n} stock${n === 1 ? '' : 's'}` : ''
  if (s.pending.length && next) {
    const buys = s.pending.filter((o) => o.side === 'buy').length
    const sells = s.pending.length - buys
    const what = [sells && `sells ${sells}`, buys && `buys ${buys}`].filter(Boolean).join(' and ')
    if (n) return { kind: 'changing', tone: 'warn', label: `Trades at the open, ${shortDay(next)}`, text: `${held}; ${what} at the open on ${formatDay(next)}.` }
    return { kind: 'buying', tone: 'warn', label: `Buys at the open, ${shortDay(next)}`, text: `All in cash now; ${what} stock${buys === 1 ? '' : 's'} at the open on ${formatDay(next)}.` }
  }
  if (n) return { kind: 'invested', tone: 'good', label: 'Invested', text: `${held}.` }
  return { kind: 'cash', tone: 'neutral', label: 'In cash', text: cashReason(s) }
}

/** The strategy's own reason for holding cash, without the boilerplate. */
export function cashReason(s: StrategyCard): string {
  const note = s.notes.find((x) => /^No (new )?buy/.test(x)) ?? s.notes[0]
  if (!note) return 'All in cash: nothing passes its buying rules today.'
  const core = note
    .replace(/^No (new )?buy( today)?: /, '')
    .replace(/\s*The money stays in cash\.?$/, '')
    .replace(/\.$/, '')
  return `All in cash: ${core}.`
}

/** Euros now in stocks (at the last close). */
export const investedEur = (s: StrategyCard) => s.holdings.reduce((a, h) => a + (h.value_eur ?? 0), 0)

/** The live estimate, only when it belongs to these official numbers and trading has started. */
export function liveOf(f: StrategiesFile, live: StrategiesLiveFile | null | undefined): StrategiesLiveFile | null {
  if (!live || live.official_as_of !== f.as_of || live.market === 'pre-open') return null
  if (Object.keys(live.strategies).length === 0 && !live.benchmark) return null
  return live
}

const NY_TIME = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: 'numeric', minute: '2-digit' })
const LOCAL_TIME = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' })

/** "11:05 AM" in New York time. */
export const nyTime = (iso: string) => NY_TIME.format(new Date(iso))

/** "5:05 PM" in the reader's own time zone. */
export const localTime = (iso: string) => LOCAL_TIME.format(new Date(iso))

/** Where the every-minute live file is pushed: raw files of the public code repository (set by the
 * deploy workflow). The site's own copy is refreshed only every 30 minutes. */
const LIVE_RAW = import.meta.env.VITE_LIVE_RAW

/** live-20261015-1353: the tag the live loop gives one minute's values (UTC). */
export const minuteTag = (d: Date) => `live-${d.toISOString().slice(0, 16).replace(/[-:]/g, '').replace('T', '-')}`

async function rawLive(ref: string, signal: AbortSignal, bust = false): Promise<StrategiesLiveFile | null> {
  try {
    const r = await fetch(`${LIVE_RAW}/${ref}/strategies_live.json${bust ? `?t=${Date.now()}` : ''}`, { cache: 'no-store', signal })
    return r.ok ? ((await r.json()) as StrategiesLiveFile) : null
  } catch {
    return null
  }
}

/** The newest minute's values. GitHub's raw server keeps a branch's old content for up to 5
 * minutes, but a tag never asked for before is always fresh: try the last few minutes' tags, then
 * the `live` branch (after the close the tags are gone and the branch is up to date). */
async function branchLive(signal: AbortSignal): Promise<StrategiesLiveFile | null> {
  for (let back = 1; back <= 5; back++) {
    const v = await rawLive(minuteTag(new Date(Date.now() - back * 60_000)), signal)
    if (v || signal.aborted) return v
  }
  return rawLive('live', signal, true)
}

/** How often an open page looks for new live values (the file changes once a minute). */
export const LIVE_POLL_MS = 30_000

const NY_CLOCK = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', weekday: 'short', hour: 'numeric', minute: 'numeric', hourCycle: 'h23' })

/** New York is (about to be) trading: a weekday between 9:25 and 16:15. Holidays are rare enough
 * that looking then costs nothing. */
export function tradingHours(now: Date): boolean {
  const parts = Object.fromEntries(NY_CLOCK.formatToParts(now).map((p) => [p.type, p.value]))
  const m = Number(parts.hour) * 60 + Number(parts.minute)
  return !['Sat', 'Sun'].includes(parts.weekday ?? '') && m >= 9 * 60 + 25 && m <= 16 * 60 + 15
}

/** The newer of two live files (by when they were made). */
export const newerLive = (a: StrategiesLiveFile | null, b: StrategiesLiveFile | null): StrategiesLiveFile | null =>
  !a ? b : !b ? a : b.generated_at >= a.generated_at ? b : a

async function fetchLive(signal: AbortSignal): Promise<StrategiesLiveFile | null> {
  const site = fetchSiteJson<StrategiesLiveFile>('strategies_live.json', signal).then((r) => (r.state === 'ready' ? r.data : null))
  const branch = LIVE_RAW ? branchLive(signal) : Promise.resolve(null)
  const [a, b] = await Promise.all([site, branch])
  return newerLive(a, b)
}

/** Today's live strategy values, kept up to date while the page is open: looked up again every
 * 30 seconds during New York trading hours (and at once when the tab comes back into view). */
export function useLiveStrategies(): StrategiesLiveFile | null {
  const [live, setLive] = useState<StrategiesLiveFile | null>(null)
  useEffect(() => {
    let controller = new AbortController()
    const load = () => {
      controller.abort()
      controller = new AbortController()
      const { signal } = controller
      void fetchLive(signal).then((v) => {
        // A new object even when nothing changed, so lateness is re-checked at each look.
        if (!signal.aborted && v) {
          const checked = Date.now()
          setLive((prev) => ({ ...newerLive(prev, v)!, checked_at: checked }))
        }
      })
    }
    load()
    const timer = window.setInterval(() => {
      if (!document.hidden && tradingHours(new Date())) load()
    }, LIVE_POLL_MS)
    const onShow = () => {
      if (!document.hidden) load()
    }
    document.addEventListener('visibilitychange', onShow)
    return () => {
      controller.abort()
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onShow)
    }
  }, [])
  return live
}

export type LiveCard = StrategyCard & { live?: boolean }

/** The official card with today's live estimate laid over it: value, holdings at their latest
 * price, orders filled at today's open. The sealed ledger only changes after the close. */
export function withLive(s: StrategyCard, live: StrategiesLiveFile | null): LiveCard {
  const e = live ? (s.benchmark ? live.benchmark : live.strategies[s.key]) : null
  if (!e) return s
  const p = s.params as { stop?: number | null; take_profit?: number | null; trailing?: number | null; max_hold?: number | null }
  const holdings = e.holdings.map((h) => {
    const old = s.holdings.find((x) => x.ticker === h.ticker)
    if (old) return { ...old, close_usd: h.price_usd, value_eur: h.value_eur, stock_move: h.move, gain_eur: h.gain_eur }
    const order = s.pending.find((o) => o.ticker === h.ticker && o.side === 'buy')
    const entry = h.entry_usd ?? h.price_usd
    return {
      ticker: h.ticker,
      name: order?.name ?? null,
      shares: h.shares,
      entry_date: order?.fill_on ?? '',
      entry_usd: entry,
      cost_eur: h.cost_eur ?? h.value_eur,
      close_usd: h.price_usd,
      value_eur: h.value_eur,
      stock_move: h.move,
      gain_eur: h.gain_eur,
      days_held: 1,
      levels: {
        stop_usd: p.stop ? entry * (1 - p.stop) : null,
        take_profit_usd: p.take_profit ? entry * (1 + p.take_profit) : null,
        trailing_usd: p.trailing ? Math.max(entry, h.price_usd) * (1 - p.trailing) : null,
        max_hold_days: p.max_hold ?? null,
        days_left: p.max_hold ? p.max_hold - 1 : null,
      },
    }
  })
  const waiting = new Set(e.waiting.map((w) => `${w.side}:${w.ticker}`))
  return {
    ...s,
    live: true,
    value: e.value,
    pct: e.pct,
    vs_benchmark: s.benchmark ? null : (e.vs_benchmark ?? s.vs_benchmark),
    cash: e.cash,
    holdings,
    pending: s.pending.filter((o) => waiting.has(`${o.side}:${o.ticker}`)),
  }
}

/** A strategy's line: its official daily values, plus today's live value while trading. */
export function linePoints(f: StrategiesFile, s: LiveCard, live: StrategiesLiveFile | null): [string, number][] {
  const start = s.start ?? f.start
  const pts: [string, number][] = [[start, s.capital ?? f.capital], ...s.series.filter(([d]) => d !== start)]
  const at = live?.prices_at ?? live?.generated_at
  if (s.live && at && s.value !== null) {
    const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York' }).format(new Date(at))
    if (today > (pts.at(-1)?.[0] ?? '')) pts.push([today, s.value])
  }
  return pts
}
