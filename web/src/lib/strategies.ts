import { useSearchParams } from 'react-router'
import type { Tone } from '../components/ui'
import type { StrategiesFile, StrategyCard, StrategySuggestion } from '../types'
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

/** Ranked by value, best first; ties keep the fixed order (all start at 200 €). */
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
