import type { ReactNode } from 'react'
import { Missing } from '../components/Missing'
import type { Cell } from '../types'
import { COLUMN_BY_KEY, type ColumnKind } from './columns'
import { formatDay, formatMoney, formatNum, formatPct, formatPctAbs, formatPrice, signClass } from './format'

/** Plain-text rendering of a value (no React), e.g. for aria labels and CSV. */
export function cellText(kind: ColumnKind, v: Cell): string {
  if (v === null || v === undefined) return '—'
  switch (kind) {
    case 'price':
      return typeof v === 'number' ? formatPrice(v) : String(v)
    case 'pct':
      return typeof v === 'number' ? formatPct(v) : String(v)
    case 'pctAbs':
      return typeof v === 'number' ? formatPctAbs(v) : String(v)
    case 'prob':
      return typeof v === 'number' ? `${Math.round(v * 100)}%` : String(v)
    case 'score':
      return typeof v === 'number' ? String(Math.round(v)) : String(v)
    case 'money':
      return typeof v === 'number' ? formatMoney(v) : String(v)
    case 'num':
      return typeof v === 'number' ? formatNum(v) : String(v)
    case 'bool':
      return v ? 'Yes' : 'No'
    case 'date':
      return typeof v === 'string' ? formatDay(v) : String(v)
    default:
      return String(v)
  }
}

/** Rendering of a screener value with the "—" convention and sign colouring. */
export function renderCell(key: string, v: Cell, missingReason?: string): ReactNode {
  const col = COLUMN_BY_KEY[key]
  const kind = col?.kind ?? 'text'
  if (v === null || v === undefined) {
    return <Missing reason={missingReason ?? `No value yet for this stock (${col?.label ?? key}).`} />
  }
  const text = cellText(kind, v)
  if (kind === 'pct' && typeof v === 'number') return <span className={signClass(v)}>{text}</span>
  return text
}
