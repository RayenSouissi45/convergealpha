import type { SortingState } from '@tanstack/react-table'
import { useDeferredValue, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Sheet } from '../components/Sheet'
import { Tip } from '../components/Tip'
import { Card, PageHeader } from '../components/ui'
import { VirtualTable } from '../components/VirtualTable'
import { COLUMN_DOCS } from '../lib/columnDocs'
import { COLUMNS, COLUMN_BY_KEY, forecastColumns, GROUP_ORDER, H_LONG, H_SHORT, HORIZONS, type ColumnDef, type HorizonKey } from '../lib/columns'
import { formatDay, formatInt } from '../lib/format'
import { PHONE, useMediaQuery } from '../lib/media'
import { matches, PRESETS, searchMatches, useScreener, type Filter, type Preset } from '../lib/screener'
import { useBrokerList, useOnlyZero, zeroAvailability, zeroKeep } from '../lib/zero'
import { ZeroToggle } from '../components/Zero'
import type { ScreenerRow } from '../types'

const COLS_KEY = 'ca-screener-columns'

function loadColumns(): string[] | null {
  try {
    const v = localStorage.getItem(COLS_KEY)
    const parsed = v ? (JSON.parse(v) as unknown) : null
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === 'string') : null
  } catch {
    return null
  }
}

function saveColumns(cols: string[]): void {
  try {
    localStorage.setItem(COLS_KEY, JSON.stringify(cols))
  } catch {
    // Storage blocked: the choice lasts for this visit only.
  }
}

const btn =
  'inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium hover:bg-slate-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800'

function FilterEditor({
  filters,
  setFilters,
  available,
  rows,
}: {
  filters: Filter[]
  setFilters: (f: Filter[]) => void
  available: ColumnDef[]
  rows: ScreenerRow[]
}) {
  const [key, setKey] = useState('')
  const numeric = available.filter((c) => !['text', 'ticker', 'bool', 'date', 'label'].includes(c.kind))
  const categorical = available.filter((c) => ['text', 'label'].includes(c.kind) && c.key !== 'name')
  const booleans = available.filter((c) => c.kind === 'bool')

  const update = (i: number, f: Filter | null) => {
    const next = [...filters]
    if (f) next[i] = f
    else next.splice(i, 1)
    setFilters(next)
  }

  const add = (k: string) => {
    const col = COLUMN_BY_KEY[k]
    if (!col) return
    if (col.kind === 'bool') setFilters([...filters, { key: k, op: 'is', value: true }])
    else if (col.kind === 'text' || col.kind === 'label') setFilters([...filters, { key: k, op: 'in', values: [] }])
    else if (col.kind === 'date') setFilters([...filters, { key: k, op: 'withinDays', days: 7 }])
    else setFilters([...filters, { key: k, op: 'range' }])
    setKey('')
  }

  const scale = (k: string) => (['pct', 'pctAbs', 'prob'].includes(COLUMN_BY_KEY[k]?.kind ?? '') ? 100 : 1)
  const input =
    'min-h-11 w-full rounded-lg border border-slate-300 bg-white px-2 text-sm dark:border-zinc-600 dark:bg-zinc-800'

  return (
    <div className="space-y-4">
      {filters.length === 0 && <p className="text-sm text-slate-500 dark:text-zinc-400">No filters yet.</p>}
      {filters.map((f, i) => {
        const col = COLUMN_BY_KEY[f.key]
        const s = scale(f.key)
        const unit = s === 100 ? '%' : ''
        return (
          <div key={`${f.key}-${i}`} className="rounded-lg border border-slate-200 p-3 dark:border-zinc-700">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-semibold">{col?.label ?? f.key}</span>
              <button type="button" className="min-h-11 px-2 text-sm text-red-700 dark:text-red-400" onClick={() => update(i, null)}>
                Remove
              </button>
            </div>
            {f.op === 'range' && (
              <div className="grid grid-cols-2 gap-2">
                <label className="text-xs text-slate-600 dark:text-zinc-400">
                  Min {unit}
                  <input
                    type="number"
                    inputMode="decimal"
                    className={input}
                    value={f.min === undefined ? '' : String(+(f.min * s).toFixed(4))}
                    onChange={(e) => update(i, { ...f, min: e.target.value === '' ? undefined : Number(e.target.value) / s })}
                  />
                </label>
                <label className="text-xs text-slate-600 dark:text-zinc-400">
                  Max {unit}
                  <input
                    type="number"
                    inputMode="decimal"
                    className={input}
                    value={f.max === undefined ? '' : String(+(f.max * s).toFixed(4))}
                    onChange={(e) => update(i, { ...f, max: e.target.value === '' ? undefined : Number(e.target.value) / s })}
                  />
                </label>
              </div>
            )}
            {f.op === 'is' && (
              <select className={input} value={f.value ? 'yes' : 'no'} onChange={(e) => update(i, { ...f, value: e.target.value === 'yes' })} aria-label={col?.label}>
                <option value="yes">Yes</option>
                <option value="no">No</option>
              </select>
            )}
            {f.op === 'withinDays' && (
              <label className="text-xs text-slate-600 dark:text-zinc-400">
                Within the next N days
                <input type="number" inputMode="numeric" className={input} value={f.days} onChange={(e) => update(i, { ...f, days: Number(e.target.value) || 0 })} />
              </label>
            )}
            {f.op === 'in' && (
              <div className="flex max-h-48 flex-wrap gap-1.5 overflow-y-auto">
                {[...new Set(rows.map((r) => r[f.key]).filter((v): v is string => typeof v === 'string'))]
                  .sort()
                  .map((v) => {
                    const on = f.values.includes(v)
                    return (
                      <button
                        key={v}
                        type="button"
                        aria-pressed={on}
                        onClick={() => update(i, { ...f, values: on ? f.values.filter((x) => x !== v) : [...f.values, v] })}
                        className={`min-h-9 rounded-full border px-3 text-xs ${on ? 'border-teal-600 bg-teal-50 text-teal-900 dark:bg-teal-950 dark:text-teal-200' : 'border-slate-300 dark:border-zinc-600'}`}
                      >
                        {on ? '✓ ' : ''}
                        {v}
                      </button>
                    )
                  })}
              </div>
            )}
          </div>
        )
      })}
      <label className="block text-sm font-medium">
        Add a filter
        <select className={`${input} mt-1`} value={key} onChange={(e) => add(e.target.value)}>
          <option value="">Choose a column…</option>
          {[['Numbers', numeric], ['Categories', categorical], ['Yes / no', booleans]].map(([label, list]) => (
            <optgroup key={label as string} label={label as string}>
              {(list as ColumnDef[]).map((c) => (
                <option key={c.key} value={c.key}>
                  {COLUMN_DOCS[c.key]?.name ?? c.label}
                </option>
              ))}
            </optgroup>
          ))}
          {available.some((c) => c.kind === 'date') && (
            <optgroup label="Dates">
              {available
                .filter((c) => c.kind === 'date')
                .map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.label}
                  </option>
                ))}
            </optgroup>
          )}
        </select>
      </label>
    </div>
  )
}

function ColumnChooser({
  visible,
  setVisible,
  fields,
}: {
  visible: string[]
  setVisible: (v: string[]) => void
  fields: Set<string>
}) {
  return (
    <div className="space-y-4">
      <p className="text-sm">
        <Link to="/columns" className="text-teal-700 underline dark:text-teal-400">Columns explained</Link>: what every column means, how it is calculated and how to read it.
      </p>
      {GROUP_ORDER.map((g) => {
        const cols = COLUMNS.filter((c) => c.group === g && c.key !== 'ticker')
        if (!cols.length) return null
        return (
          <fieldset key={g}>
            <legend className="mb-1 text-xs font-semibold tracking-wide text-slate-500 uppercase dark:text-zinc-400">{g}</legend>
            <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
              {cols.map((c) => {
                const has = fields.has(c.key)
                const on = visible.includes(c.key)
                return (
                  <label key={c.key} className={`flex min-h-11 items-center gap-2 text-sm ${has ? '' : 'text-slate-400 dark:text-zinc-500'}`}>
                    <input
                      type="checkbox"
                      className="size-6 accent-teal-700"
                      checked={on && has}
                      disabled={!has}
                      onChange={() => setVisible(on ? visible.filter((k) => k !== c.key) : [...visible, c.key])}
                    />
                    <span>
                      {COLUMN_DOCS[c.key]?.name ?? c.label}
                      {!has && <span className="ml-1 text-xs">(arrives in phase {c.phase})</span>}
                    </span>
                  </label>
                )
              })}
            </div>
          </fieldset>
        )
      })}
    </div>
  )
}

// 72 + 90 + 72 + 92 = 326 px: fits a 360 px phone (16 px gutters, 1 px table borders).
const PHONE_FORECAST_WIDTHS: Record<string, number> = {
  ticker: 72,
  ...Object.fromEntries(HORIZONS.flatMap((h) => [[`med_${h}`, 90], [`p_up_${h}`, 72], [`hit_up_${h}`, 92]])),
}

export default function Screener() {
  const screener = useScreener()
  const [params, setParams] = useSearchParams()
  const presetId = params.get('preset')
  const preset = PRESETS.find((p) => p.id === presetId) ?? null
  const forecastView = preset?.view === 'forecast'
  const phone = useMediaQuery(PHONE)
  const [horizon, setHorizon] = useState<HorizonKey>('6m')
  const [query, setQuery] = useState('')
  const deferredQuery = useDeferredValue(query)
  const [onlyEligible, setOnlyEligible] = useState(false)
  const [onlyZero] = useOnlyZero()
  const zeroOk = zeroAvailability(useBrokerList()).ok
  const [userFilters, setUserFilters] = useState<Filter[]>([])
  const [sorting, setSorting] = useState<SortingState>(preset ? [{ id: preset.sort.key, desc: preset.sort.desc }] : [{ id: 'adv_dollar', desc: true }])
  const [visible, setVisibleState] = useState<string[]>(() => loadColumns() ?? COLUMNS.filter((c) => c.defaultVisible).map((c) => c.key))
  const [sheet, setSheet] = useState<'filters' | 'columns' | null>(null)

  const setVisible = (v: string[]) => {
    setVisibleState(v)
    saveColumns(v)
  }

  const applyPreset = (p: Preset | null) => {
    const next = new URLSearchParams(params)
    if (p) next.set('preset', p.id)
    else next.delete('preset')
    setParams(next, { replace: true })
    if (p) setSorting([{ id: p.view === 'forecast' ? `p_up_${horizon}` : p.sort.key, desc: p.sort.desc }])
  }

  const pickHorizon = (h: HorizonKey) => {
    setHorizon(h)
    // Keep sorting by the same measure, now for the chosen horizon.
    setSorting((s) => s.map((x) => ({ ...x, id: x.id.replace(/_(1w|1m|3m|6m)$/, `_${h}`) })))
  }

  const data = screener.state === 'ready' ? screener.data : null
  const fields = useMemo(() => data?.fields ?? new Set<string>(), [data])
  const available = COLUMNS.filter((c) => fields.has(c.key))
  let shownColumns: string[]
  if (forecastView) {
    shownColumns = phone ? ['ticker', ...forecastColumns(horizon)] : ['ticker', 'name', ...HORIZONS.flatMap((h) => forecastColumns(h))]
  } else {
    shownColumns = ['ticker', ...visible.filter((k) => k !== 'ticker' && fields.has(k))]
    // Columns a preset sorts or filters on are always shown.
    for (const extra of preset ? [preset.sort.key, ...preset.filters.map((f) => f.key)] : []) {
      if (fields.has(extra) && !shownColumns.includes(extra)) shownColumns.push(extra)
    }
    for (const s of sorting) if (fields.has(s.id) && !shownColumns.includes(s.id)) shownColumns.push(s.id)
  }
  // One horizon on a phone: the chips say which, so the headers can drop it.
  const labels =
    forecastView && phone
      ? Object.fromEntries(forecastColumns(horizon).map((k) => [k, (COLUMN_BY_KEY[k]?.label ?? k).replace(/ (1W|1M|3M|6M)$/, '')]))
      : undefined

  const filters = useMemo(() => {
    const all = [...userFilters]
    if (preset && preset.needs.every((n) => fields.has(n))) all.push(...preset.filters)
    if (onlyEligible) all.push({ key: 'eligible', op: 'is', value: true })
    return all.filter((f) => !(f.op === 'in' && f.values.length === 0))
  }, [userFilters, preset, onlyEligible, fields])

  const baseRows = useMemo(() => {
    if (!data) return []
    return data.rows.filter((r) => searchMatches(r, deferredQuery) && filters.every((f) => matches(r, f)))
  }, [data, deferredQuery, filters])
  const rows = useMemo(() => baseRows.filter((r) => zeroKeep(r.zero, onlyZero && zeroOk)), [baseRows, onlyZero, zeroOk])

  return (
    <>
      <PageHeader
        title="Screener"
        subtitle={
          data
            ? `${formatInt(data.file.count)} US stocks · prices as of ${formatDay(data.file.as_of)} · greyed rows are not eligible for signals`
            : 'Every US common stock, searchable and sortable.'
        }
      />
      {screener.state === 'loading' && <p className="text-sm text-slate-500">Loading all stocks…</p>}
      {screener.state === 'missing' && (
        <Card>
          <p className="text-sm">The stock list has not been published yet. It appears after the first daily pipeline run.</p>
        </Card>
      )}
      {screener.state === 'error' && (
        <Card>
          <p className="text-sm text-red-700 dark:text-red-400">Could not load the stock list ({screener.message}).</p>
        </Card>
      )}
      {data && (
        <>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <label className="min-w-0 flex-1 basis-56">
              <span className="sr-only">Search by ticker or name</span>
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search ticker or name"
                autoComplete="off"
                autoCapitalize="characters"
                className="min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-zinc-600 dark:bg-zinc-900"
              />
            </label>
            <button type="button" className={btn} onClick={() => setSheet('filters')}>
              Filters{userFilters.length ? ` (${userFilters.length})` : ''}
            </button>
            {!forecastView && (
              <button type="button" className={btn} onClick={() => setSheet('columns')}>
                Columns
              </button>
            )}
            <label className="inline-flex min-h-11 items-center gap-2 text-sm">
              <input type="checkbox" className="size-6 accent-teal-700" checked={onlyEligible} onChange={(e) => setOnlyEligible(e.target.checked)} />
              Eligible only
            </label>
          </div>
          <div className="mb-1">
            <ZeroToggle values={baseRows.map((r) => r.zero)} />
          </div>
          <div className="-mx-4 mb-2 flex gap-1.5 overflow-x-auto px-4 pb-1" role="group" aria-label="Presets">
            {PRESETS.map((p) => {
              const ready = p.needs.every((n) => fields.has(n))
              const on = preset?.id === p.id
              const chip = `min-h-9 shrink-0 rounded-full border px-3 text-sm whitespace-nowrap ${
                on ? 'border-teal-700 bg-teal-700 text-white dark:border-teal-500 dark:bg-teal-600' : 'border-slate-300 bg-white dark:border-zinc-600 dark:bg-zinc-900'
              } ${ready ? '' : 'opacity-50'}`
              return ready ? (
                <button key={p.id} type="button" aria-pressed={on} className={chip} title={p.help} onClick={() => applyPreset(on ? null : p)}>
                  {p.label}
                </button>
              ) : (
                <Tip key={p.id} content={`${p.help} Arrives in build phase ${p.phase}.`} label={`${p.label}: arrives in phase ${p.phase}`} className={`${chip} no-underline`}>
                  {p.label}
                </Tip>
              )
            })}
          </div>
          {forecastView && (
            <>
              <p className="mb-2 text-xs leading-relaxed text-slate-600 dark:text-zinc-400" data-testid="forecast-legend">
                <strong>Expected change</strong>: the middle forecast, with the range 8 in 10 outcomes fall in · <strong>Chance up</strong>: chance the price is higher ·{' '}
                <strong>How often right</strong>: how often similar past calls came true (✓ = passed the holdout test).
              </p>
              {phone && (
                <div className="mb-2 flex gap-1.5" role="group" aria-label="Forecast horizon">
                  {HORIZONS.map((h) => (
                    <button
                      key={h}
                      type="button"
                      aria-pressed={horizon === h}
                      onClick={() => pickHorizon(h)}
                      className={`min-h-11 flex-1 rounded-lg border text-sm font-semibold ${
                        horizon === h ? 'border-teal-700 bg-teal-700 text-white dark:border-teal-500 dark:bg-teal-600' : 'border-slate-300 bg-white dark:border-zinc-600 dark:bg-zinc-900'
                      }`}
                      aria-label={`${H_SHORT[h]} (${H_LONG[h]})`}
                    >
                      {H_SHORT[h]}
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
          <p className="mb-2 text-xs text-slate-500 dark:text-zinc-400" aria-live="polite">
            {formatInt(rows.length)} shown{preset ? ` · preset: ${preset.label}` : ''} ·{' '}
            <Link to="/columns" className="underline">
              What do the columns mean?
            </Link>
          </p>
          <VirtualTable
            rows={rows}
            columns={shownColumns}
            sorting={sorting}
            onSortingChange={setSorting}
            widths={forecastView && phone ? PHONE_FORECAST_WIDTHS : undefined}
            labels={labels}
            reliability={data.file.reliability}
          />
          <Sheet
            open={sheet === 'filters'}
            title="Filters"
            onClose={() => setSheet(null)}
            footer={
              <button type="button" className={btn} onClick={() => setUserFilters([])}>
                Clear all filters
              </button>
            }
          >
            <FilterEditor filters={userFilters} setFilters={setUserFilters} available={available} rows={data.rows} />
          </Sheet>
          <Sheet open={sheet === 'columns'} title="Columns" onClose={() => setSheet(null)}>
            <ColumnChooser visible={visible} setVisible={setVisible} fields={fields} />
          </Sheet>
        </>
      )}
    </>
  )
}
