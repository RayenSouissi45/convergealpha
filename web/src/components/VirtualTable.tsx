import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef as TColumnDef,
  type SortingState,
} from '@tanstack/react-table'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'
import { COLUMN_BY_KEY } from '../lib/columns'
import { renderCell } from '../lib/cells'
import type { Cell, ScreenerRow } from '../types'
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

function sortValue(v: Cell): string | number | undefined {
  if (v === null || v === undefined) return undefined
  if (typeof v === 'boolean') return v ? 1 : 0
  return v
}

export function VirtualTable({
  rows,
  columns,
  sorting,
  onSortingChange,
}: {
  rows: ScreenerRow[]
  columns: string[]
  sorting: SortingState
  onSortingChange: (s: SortingState) => void
}) {
  const defs = useMemo<TColumnDef<ScreenerRow>[]>(
    () =>
      columns.map((key) => {
        const col = COLUMN_BY_KEY[key]
        const textual = col?.kind === 'text' || col?.kind === 'ticker' || col?.kind === 'label'
        return {
          id: key,
          accessorFn: (r: ScreenerRow) => sortValue(r[key] ?? null),
          header: col?.label ?? key,
          size: col?.width ?? 96,
          sortUndefined: 'last' as const,
          sortDescFirst: !textual,
          sortingFn: textual ? 'text' : 'basic',
        }
      }),
    [columns],
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
        <div role="rowgroup" className="sticky top-0 z-20 flex border-b border-slate-200 bg-slate-50 dark:border-zinc-800 dark:bg-zinc-950">
          {table.getHeaderGroups()[0]?.headers.map((h, i) => {
            const col = COLUMN_BY_KEY[h.column.id]
            const dir = h.column.getIsSorted()
            const numeric = col && !['text', 'ticker', 'label'].includes(col.kind)
            return (
              <div
                key={h.id}
                role="columnheader"
                aria-sort={dir === 'asc' ? 'ascending' : dir === 'desc' ? 'descending' : 'none'}
                className={`flex h-11 shrink-0 items-center gap-1 px-2 text-xs font-semibold text-slate-600 dark:text-zinc-300 ${
                  i === 0 ? 'sticky left-0 z-10 bg-slate-50 dark:bg-zinc-950' : ''
                } ${numeric ? 'justify-end text-right' : ''}`}
                style={{ width: h.getSize() }}
              >
                <button
                  type="button"
                  onClick={h.column.getToggleSortingHandler()}
                  className="min-h-11 truncate"
                  aria-label={`Sort by ${col?.label ?? h.column.id}`}
                >
                  {flexRender(h.column.columnDef.header, h.getContext())}
                  <span aria-hidden="true">{dir === 'asc' ? ' ▲' : dir === 'desc' ? ' ▼' : ''}</span>
                </button>
                {col && (
                  <Tip content={col.help} label={`About ${col.label}`} className="no-underline text-slate-400">
                    ⓘ
                  </Tip>
                )}
              </div>
            )
          })}
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
                  eligible ? '' : 'text-slate-400 dark:text-zinc-500'
                }`}
                style={{ transform: `translateY(${vr.start}px)`, height: ROW_HEIGHT, width: totalWidth, minWidth: '100%' }}
              >
                {row.getVisibleCells().map((cell, i) => {
                  const key = cell.column.id
                  const col = COLUMN_BY_KEY[key]
                  const numeric = col && !['text', 'ticker', 'label'].includes(col.kind)
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
                          className="flex min-h-11 items-center text-teal-700 underline-offset-2 hover:underline dark:text-teal-400"
                          aria-label={`${row.original.ticker}${eligible ? '' : ', not eligible for signals'}`}
                        >
                          {row.original.ticker}
                          {!eligible && (
                            <span className="ml-1 text-[10px] font-normal text-slate-400" aria-hidden="true">
                              n/e
                            </span>
                          )}
                        </Link>
                      ) : key === 'name' ? (
                        <span className="truncate" title={String(value ?? '')}>
                          {value === null ? '—' : String(value)}
                        </span>
                      ) : (
                        renderCell(key, value)
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
