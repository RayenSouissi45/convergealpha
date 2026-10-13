import type { ReactNode } from 'react'
import { Missing } from '../components/Missing'
import { LabelBadge } from '../components/LabelBadge'
import { OppBadge } from '../components/Opportunity'
import { isOpp, OPP_TEXT } from './opportunity'
import { Tip } from '../components/Tip'
import type { Cell, ReliabilityBucket, ReliabilityTables, ScreenerRow } from '../types'
import { COLUMN_BY_KEY, H_LONG, type ColumnKind, type HorizonKey } from './columns'
import { formatDay, formatInt, formatMoney, formatNum, formatPct, formatPctAbs, formatPrice, signClass } from './format'

/** Plain-text rendering of a value (no React), e.g. for aria labels and CSV. */
export function cellText(kind: ColumnKind, v: Cell): string {
  if (v === null || v === undefined) return '—'
  switch (kind) {
    case 'price':
      return typeof v === 'number' ? formatPrice(v) : String(v)
    case 'pct':
    case 'forecast':
      return typeof v === 'number' ? formatPct(v) : String(v)
    case 'pctAbs':
      return typeof v === 'number' ? formatPctAbs(v) : String(v)
    case 'prob':
    case 'hit':
      return typeof v === 'number' ? `${Math.round(v * 100)}%` : String(v)
    case 'score':
      return typeof v === 'number' ? String(Math.round(v)) : String(v)
    case 'money':
      return typeof v === 'number' ? formatMoney(v) : String(v)
    case 'num':
      return typeof v === 'number' ? formatNum(v) : String(v)
    case 'int':
      return typeof v === 'number' ? formatInt(v) : String(v)
    case 'bool':
    case 'zero':
      return v ? 'Yes' : 'No'
    case 'opp':
      return isOpp(v) ? OPP_TEXT[v].title : String(v)
    case 'date':
      return typeof v === 'string' ? formatDay(v.slice(0, 10)) : String(v)
    default:
      return String(v)
  }
}

/** Green above 50%, red below: always paired with the number itself. */
export function chanceClass(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v) || Math.abs(v - 0.5) < 0.005) return ''
  return v > 0.5 ? 'text-emerald-700 dark:text-emerald-400' : 'text-red-700 dark:text-red-400'
}

/** The reliability bucket a displayed probability falls into (same rule as the pipeline). */
export function findBucket(buckets: ReliabilityBucket[] | undefined, p: Cell | undefined): ReliabilityBucket | null {
  if (!buckets || typeof p !== 'number') return null
  return buckets.find((b) => b.lo <= p && p < b.hi) ?? null
}

export interface CellContext {
  row?: ScreenerRow
  reliability?: ReliabilityTables | null
  validated?: string[]
}

function horizonOf(key: string): HorizonKey | null {
  const m = key.match(/_(1w|1m|3m|6m)$/)
  return m ? (m[1] as HorizonKey) : null
}

/** Rendering of a screener value with the "—" convention and sign colouring. */
export function renderCell(key: string, v: Cell, missingReason?: string, ctx: CellContext = {}): ReactNode {
  const col = COLUMN_BY_KEY[key]
  const kind = col?.kind ?? 'text'
  if (kind === 'zero') {
    if (v === true) return <span className="text-teal-800 dark:text-teal-300">Yes</span>
    if (v === false) return 'No'
    return (
      <Tip content="Not sure: the stock started trading in the US less than 30 days ago, or the finanzen.net zero list is missing or too old." label="Not sure if buyable on finanzen.net zero" className="text-slate-500 dark:text-zinc-400">
        ?
      </Tip>
    )
  }
  if (kind === 'opp') {
    if (isOpp(v) && ctx.row) return <OppBadge ticker={ctx.row.ticker} color={v} compact />
    if (isOpp(v)) return OPP_TEXT[v].title
    return <Missing reason="No badge: no fresh event (last 7 days) and no big price jump." />
  }
  if (v === null || v === undefined) {
    return <Missing reason={missingReason ?? missingFor(key, col?.label)} />
  }
  if (kind === 'label' && typeof v === 'string') return <LabelBadge label={v} />
  const text = cellText(kind, v)
  if (kind === 'pct' && typeof v === 'number') return <span className={signClass(v)}>{text}</span>
  if (kind === 'prob' && typeof v === 'number' && /^p_(up|beat)_/.test(key)) return <span className={chanceClass(v)}>{text}</span>
  if (kind === 'forecast' && typeof v === 'number') {
    const h = horizonOf(key)
    const lo = h ? ctx.row?.[`p10_${h}`] : null
    const hi = h ? ctx.row?.[`p90_${h}`] : null
    return (
      <span className="flex flex-col items-end leading-tight">
        <span className={signClass(v)}>{text}</span>
        {typeof lo === 'number' && typeof hi === 'number' && (
          <span className="text-[11px] text-slate-500 dark:text-zinc-400" title={`80% range: 8 out of 10 outcomes are expected between ${formatPct(lo, 0)} and ${formatPct(hi, 0)}.`}>
            {formatPct(lo, 0)} to {formatPct(hi, 0)}
          </span>
        )}
      </span>
    )
  }
  if (kind === 'hit' && typeof v === 'number') {
    const h = horizonOf(key)
    const b = h ? findBucket(ctx.reliability?.up?.[h], ctx.row?.[`p_up_${h}`]) : null
    const pm = b ? Math.max(b.rate - b.wilson_lo, b.wilson_hi - b.rate) : null
    const ok = h ? (ctx.validated ?? []).includes(`P(up) ${h}`) : false
    return (
      <span className="flex flex-col items-end leading-tight" title={b && h ? `When the app said about this chance, the stock was higher ${Math.round(b.rate * 100)}% of the time after ${H_LONG[h]} (${formatInt(b.n)} past cases, range ${Math.round(b.wilson_lo * 100)}–${Math.round(b.wilson_hi * 100)}%).` : undefined}>
        <span className={chanceClass(v)}>
          {text}
          {pm !== null && <span className="text-xs text-slate-500 dark:text-zinc-400"> ±{Math.max(1, Math.round(pm * 100))}%</span>}
        </span>
        <span className={`text-[11px] ${ok ? 'text-emerald-700 dark:text-emerald-400' : 'text-amber-700 dark:text-amber-400'}`}>{ok ? '✓ validated' : 'research'}</span>
      </span>
    )
  }
  return text
}

function missingFor(key: string, label?: string): string {
  if (key.startsWith('hit_up_')) return 'No past record for this stock yet: the reliability tables come with the weekly model run, and only model forecasts have one.'
  if (/^(med|p10|p90|p_up|p_beat)_/.test(key)) return 'No forecast for this stock (not enough price history).'
  return `No value yet for this stock (${label ?? key}).`
}
