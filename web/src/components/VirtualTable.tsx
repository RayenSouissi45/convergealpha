import {
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef as TColumnDef,
  type SortingState,
} from '@tanstack/react-table'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'
import { COLUMN_DOCS, statusText } from '../lib/columnDocs'
import { COLUMN_BY_KEY } from '../lib/columns'
import { useHealth } from '../lib/health'
import { renderCell } from '../lib/cells'
import { ZeroBadge } from './Zero'
import type { Cell, ReliabilityTables, ScreenerRow } from '../types'
import { Tip } from './Tip'

const ROW_HEIGHT = 44

/** Fills the viewport below its top edge (minus the phone bottom bar). */
function useAvailableHeight(ref: React.RefObject<HTMLElement | null>, min = 320): number {
  const [h, setH] = useState(560)
  useLayoutEffect(() => {
    const update = () => {
      const top = ref.current?.getBoundingClientRect().top ?? 200
      const bottomBar = window.innerWidth < 1024 ? 72 : 16
      setH(Math.max(min, Math.floor(window.innerHeight - Math.max(top, 0) - bottomBar)))
    }
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [ref, min])
  return h
}

// Opportunity badges sort confirmed first: green, then amber, then red.
const OPP_RANK: Record<string, number> = { green: 3, amber: 2, red: 1 }

function sortValue(v: Cell): string | number | undefined {
  if (v === null || v === undefined) return undefined
  if (typeof v === 'boolean') return v ? 1 : 0
  return v
}

/** The (i) tooltip: plain name, meaning, formula, validation status and a link to the full page. */
export function ColumnTip({ colKey, validated }: { colKey: string; validated: string[] }) {
  const col = COLUMN_BY_KEY[colKey]
  const doc = COLUMN_DOCS[colKey]
  if (!col) return null
  const content = doc ? (
    <span className="block space-y-1">
      <strong className="block">{doc.name}</strong>
      <span className="block">{doc.what}</span>
      <span className="block text-slate-300">How: {doc.how}</span>
      <span className="block text-slate-300">{statusText(doc, validated).text}</span>
      <Link to={`/columns#col-${colKey}`} className="block font-medium text-teal-300 underline">
        Full explanation
      </Link>
    </span>
  ) : (
    col.help
  )
  return (
    <Tip content={content} label={`About ${col.label}`} className="pointer-events-auto relative z-10 ml-0.5 inline-flex min-h-6 min-w-6 items-center justify-center align-middle text-slate-400 no-underline">
      ⓘ
    </Tip>
  )
}

export function VirtualTable({
  rows,
  columns,
  sorting,
  onSortingChange,
  widths,
  labels,
  reliability,
}: {
  rows: ScreenerRow[]
  columns: string[]
  sorting: SortingState
  onSortingChange: (s: SortingState) => void
  /** Per-column width overrides (e.g. the compact phone Forecast view). */
  widths?: Record<string, number>
  /** Per-column header overrides (e.g. without the horizon when only one is shown). */
  labels?: Record<string, string>
  reliability?: ReliabilityTables | null
}) {
  const defs = useMemo<TColumnDef<ScreenerRow>[]>(
    () =>
      columns.map((key) => {
        const col = COLUMN_BY_KEY[key]
        const textual = col?.kind === 'text' || col?.kind === 'ticker' || col?.kind === 'label'
        return {
          id: key,
          accessorFn: (r: ScreenerRow) => (col?.kind === 'opp' ? OPP_RANK[String(r[key])] : sortValue(r[key] ?? null)),
          header: labels?.[key] ?? col?.label ?? key,
          size: widths?.[key] ?? col?.width ?? 96,
          sortUndefined: 'last' as const,
          sortDescFirst: !textual,
          sortingFn: textual ? 'text' : 'basic',
        }
      }),
    [columns, widths, labels],
  )

  const table = useReactTable({
    data: rows,
    columns: defs,
    state: { sorting },
    onSortingChange: (updater) => onSortingChange(typeof updater === 'function' ? updater(sorting) : updater),
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId: (r) => r.ticker,
  })

  const scrollRef = useRef<HTMLDivElement>(null)
  const height = useAvailableHeight(scrollRef)
  const health = useHealth()
  const validated = health.state === 'ready' ? health.data.validated : []
  const model = table.getRowModel().rows
  const virtualizer = useVirtualizer({
    count: model.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  })
  const totalWidth = table.getTotalSize()

  return (
    <div
      ref={scrollRef}
      role="table"
      aria-label="Stocks"
      aria-rowcount={model.length + 1}
      className="relative overflow-auto overscroll-contain rounded-xl border border-slate-200 bg-white dark:border-zinc-800 dark:bg-zinc-900"
      style={{ height }}
    >
      <div style={{ width: totalWidth, minWidth: '100%' }}>
        <div role="rowgroup" className="sticky top-0 z-20 border-b border-slate-200 bg-slate-50 dark:border-zinc-800 dark:bg-zinc-950">
          <div role="row" aria-rowindex={1} className="flex">
          {table.getHeaderGroups()[0]?.headers.map((h, i) => {
            const col = COLUMN_BY_KEY[h.column.id]
            const dir = h.column.getIsSorted()
            const numeric = col && !['text', 'ticker', 'label', 'opp'].includes(col.kind)
            const label = String(h.column.columnDef.header ?? h.column.id)
            return (
              <div
                key={h.id}
                role="columnheader"
                aria-sort={dir === 'asc' ? 'ascending' : dir === 'desc' ? 'descending' : 'none'}
                className={`relative flex min-h-12 shrink-0 items-center px-2 py-1 text-xs leading-tight font-semibold text-slate-600 dark:text-zinc-300 ${
                  i === 0 ? 'sticky left-0 z-10 bg-slate-50 dark:bg-zinc-950' : ''
                } ${numeric ? 'justify-end text-right' : ''}`}
                style={{ width: h.getSize() }}
              >
                {/* The whole cell sorts; the label wraps to two lines and is never cut off. */}
                <button
                  type="button"
                  onClick={h.column.getToggleSortingHandler()}
                  className="absolute inset-0 cursor-pointer"
                  aria-label={`Sort by ${COLUMN_DOCS[h.column.id]?.name ?? label}`}
                />
                <span className="pointer-events-none relative min-w-0 [overflow-wrap:anywhere]" data-header-label>
                  {label}
                  <span aria-hidden="true">{dir === 'asc' ? ' ▲' : dir === 'desc' ? ' ▼' : ''}</span>
                  {col && <ColumnTip colKey={h.column.id} validated={validated} />}
                </span>
              </div>
            )
          })}
          </div>
        </div>
        <div role="rowgroup" style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
          {virtualizer.getVirtualItems().map((vr) => {
            const row = model[vr.index]
            if (!row) return null
            const eligible = row.original.eligible !== false
            return (
              <div
                key={row.id}
                role="row"
                aria-rowindex={vr.index + 2}
                className={`absolute left-0 flex border-b border-slate-100 text-sm dark:border-zinc-800 ${
                  eligible ? '' : 'text-slate-500 dark:text-zinc-400'
                }`}
                style={{ transform: `translateY(${vr.start}px)`, height: ROW_HEIGHT, width: totalWidth, minWidth: '100%' }}
              >
                {row.getVisibleCells().map((cell, i) => {
                  const key = cell.column.id
                  const col = COLUMN_BY_KEY[key]
                  const numeric = col && !['text', 'ticker', 'label', 'opp'].includes(col.kind)
                  const value = row.original[key] ?? null
                  return (
                    <div
                      key={cell.id}
                      role="cell"
                      className={`flex shrink-0 items-center px-2 tabular-nums ${
                        i === 0 ? 'sticky left-0 z-10 bg-white font-semibold dark:bg-zinc-900' : ''
                      } ${numeric ? 'justify-end' : ''} ${key === 'name' ? 'truncate' : ''}`}
                      style={{ width: cell.column.getSize() }}
                    >
                      {key === 'ticker' ? (
                        <Link
                          to={`/stock/${encodeURIComponent(row.original.ticker)}`}
                          className="flex min-h-11 min-w-0 flex-col justify-center text-teal-700 underline-offset-2 hover:underline dark:text-teal-400"
                          aria-label={`${row.original.ticker}${eligible ? '' : ', not eligible for signals'}`}
                        >
                          <span className="truncate">{row.original.ticker}</span>
                          <span className="flex items-center gap-1">
                            <ZeroBadge value={row.original.zero} interactive={false} />
                            {!eligible && (
                              <span className="text-[10px] leading-4 font-normal text-slate-500 dark:text-zinc-400" aria-hidden="true">
                                n/e
                              </span>
                            )}
                          </span>
                        </Link>
                      ) : key === 'name' ? (
                        <span className="truncate" title={String(value ?? '')}>
                          {value === null ? '—' : String(value)}
                        </span>
                      ) : (
                        renderCell(key, value, undefined, { row: row.original, reliability, validated })
                      )}
                    </div>
                  )
                })}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
