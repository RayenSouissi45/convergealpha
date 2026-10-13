import { useEffect, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Missing } from '../components/Missing'
import { LabelBadge } from '../components/LabelBadge'
import { type DecisionSection, type FamiliesSection, type ForecastSection, type PlanSection } from '../components/stock/decision'
import { Card, PageHeader } from '../components/ui'
import { fetchSiteJson, stockFile } from '../lib/data'
import { formatDay, formatMoney, formatPct, formatPctAbs, formatPrice } from '../lib/format'
import { useBrokerList, useOnlyZero, zeroAvailability, zeroKeep } from '../lib/zero'
import { ZeroBadge, ZeroToggle } from '../components/Zero'
import type { StockFile } from '../types'

type Getter = (s: StockFile) => ReactNode

const d = (s: StockFile) => s.decision as DecisionSection | undefined
const f = (s: StockFile) => s.forecast as ForecastSection | undefined
const fam = (s: StockFile, id: string) => (s.families as FamiliesSection | undefined)?.families.find((x) => x.id === id)?.score ?? null
const stat = (s: StockFile, k: string) => (typeof s.stats[k] === 'number' ? (s.stats[k] as number) : null)
const dash = <Missing reason="Not available for this stock." />
const pct = (v: number | null | undefined) => (v === null || v === undefined ? dash : formatPct(v))
const prob = (v: number | null | undefined) => (v === null || v === undefined ? dash : `${Math.round(v * 100)}%`)

const ROWS: [string, Getter][] = [
  ['Label', (s) => (d(s) ? <LabelBadge label={d(s)!.label} /> : dash)],
  ['Why', (s) => <span className="text-xs">{d(s)?.why ?? '—'}</span>],
  ['Sector', (s) => String(s.sector ?? '—')],
  ['Price', (s) => (stat(s, 'price') !== null ? formatPrice(stat(s, 'price')!) : dash)],
  ['Market cap', (s) => (stat(s, 'market_cap') !== null ? formatMoney(stat(s, 'market_cap')!) : dash)],
  ['Chance higher, 1 week', (s) => prob(f(s)?.horizons?.['1w'].p_up)],
  ['Chance higher, 1 month', (s) => prob(f(s)?.horizons?.['1m'].p_up)],
  ['Chance higher, 3 months', (s) => prob(f(s)?.horizons?.['3m'].p_up)],
  ['Chance higher, 6 months', (s) => prob(f(s)?.horizons?.['6m'].p_up)],
  ['Chance to beat S&P 500, 6 months', (s) => prob(f(s)?.horizons?.['6m'].p_beat)],
  ['Median 6 months', (s) => pct(f(s)?.horizons?.['6m'].median)],
  ['80% range, 6 months', (s) => (f(s)?.horizons ? `${formatPct(f(s)!.horizons!['6m'].p10, 0)} to ${formatPct(f(s)!.horizons!['6m'].p90, 0)}` : dash)],
  ['Expected value (60-day trade)', (s) => pct(d(s)?.ev)],
  ...(['f1', 'f2', 'f3', 'f4', 'f5', 'f6'] as const).map((id): [string, Getter] => [`${id.toUpperCase()} score`, (s) => (fam(s, id) !== null ? String(Math.round(fam(s, id)!)) : dash)]),
  ['N_eff', (s) => String((s.families as FamiliesSection | undefined)?.n_eff ?? '—')],
  ['Disagreement D', (s) => String((s.families as FamiliesSection | undefined)?.disagreement ?? '—')],
  ['Analyst target upside', (s) => pct((s.analysts as { target_upside: number | null } | null)?.target_upside)],
  ['Return 1 year', (s) => pct(stat(s, 'ret_1y'))],
  ['Volatility (3 months)', (s) => (stat(s, 'vol_63') !== null ? formatPctAbs(stat(s, 'vol_63')!) : dash)],
  ['From 52-week high', (s) => pct(stat(s, 'dist_52w_high'))],
  ['Planned exit level', (s) => ((s.plan as PlanSection | null) ? formatPrice((s.plan as PlanSection).planned_exit) : dash)],
  ['Next earnings', (s) => ((s.earnings as { next: string | null } | null)?.next ? formatDay((s.earnings as { next: string }).next) : dash)],
  ['Blocking events', (s) => (d(s)?.blocking.length ? d(s)!.blocking.join('; ') : 'none')],
]

export default function Compare() {
  const [params, setParams] = useSearchParams()
  const tickers = (params.get('t') ?? '').split(',').map((x) => x.trim().toUpperCase()).filter(Boolean).slice(0, 4)
  const [draft, setDraft] = useState(tickers.join(', '))
  const [stocks, setStocks] = useState<Record<string, StockFile | 'missing'>>({})

  const key = tickers.join(',')
  useEffect(() => {
    let alive = true
    for (const t of key.split(',').filter(Boolean)) {
      void fetchSiteJson<StockFile>(stockFile(t)).then((r) => {
        if (alive) setStocks((prev) => (prev[t] ? prev : { ...prev, [t]: r.state === 'ready' ? r.data : 'missing' }))
      })
    }
    return () => {
      alive = false
    }
  }, [key])

  const [onlyZero] = useOnlyZero()
  const zeroOk = zeroAvailability(useBrokerList()).ok
  const zeroOf = (s: StockFile | 'missing' | undefined) => (s && s !== 'missing' ? ((s.zero as boolean | null | undefined) ?? null) : null)
  const all = tickers.map((t) => [t, stocks[t]] as const)
  const loaded = all.filter(([, s]) => zeroKeep(zeroOf(s), onlyZero && zeroOk))
  const hidden = all.filter(([, s]) => !zeroKeep(zeroOf(s), onlyZero && zeroOk)).map(([t]) => t)
  return (
    <>
      <PageHeader title="Compare" subtitle="2–4 stocks side by side." />
      <form
        className="mb-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          setParams({ t: draft.split(/[,\s]+/).filter(Boolean).slice(0, 4).join(',').toUpperCase() })
        }}
      >
        <label className="flex-1">
          <span className="sr-only">Tickers to compare</span>
          <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="e.g. AAPL, MSFT, NVDA" autoCapitalize="characters" className="min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-zinc-600 dark:bg-zinc-900" />
        </label>
        <button type="submit" className="min-h-11 rounded-lg bg-slate-900 px-4 text-sm font-medium text-white dark:bg-zinc-100 dark:text-zinc-900">Compare</button>
      </form>
      <div className="mb-3">
        <ZeroToggle values={all.map(([, s]) => zeroOf(s))} />
        {hidden.length > 0 && (
          <p className="text-xs text-slate-500 dark:text-zinc-400">Hidden because they are not on finanzen.net zero: {hidden.join(', ')}.</p>
        )}
      </div>
      {tickers.length < 2 ? (
        <Card>
          <p className="text-sm text-slate-600 dark:text-zinc-400">Enter 2 to 4 tickers separated by commas.</p>
        </Card>
      ) : (
        <div className="-mx-4 overflow-x-auto px-4">
          <table className="w-full min-w-max border-separate border-spacing-0 text-sm">
            <caption className="sr-only">Comparison of {tickers.join(', ')}</caption>
            <thead>
              <tr>
                <th scope="col" className="sticky left-0 bg-slate-50 p-2 text-left dark:bg-zinc-950"><span className="sr-only">Measure</span></th>
                {loaded.map(([t]) => (
                  <th key={t} scope="col" className="min-w-36 p-2 text-left">
                    <span className="flex flex-wrap items-center gap-1.5">
                      <Link to={`/stock/${encodeURIComponent(t)}`} className="text-base underline">{t}</Link>
                      <ZeroBadge value={zeroOf(stocks[t])} />
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROWS.map(([label, get]) => (
                <tr key={label} className="border-t border-slate-200 dark:border-zinc-800">
                  <th scope="row" className="sticky left-0 border-t border-slate-200 bg-slate-50 p-2 text-left text-xs font-medium text-slate-600 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-400">{label}</th>
                  {loaded.map(([t, s]) => (
                    <td key={t} className="max-w-56 border-t border-slate-200 p-2 align-top tabular-nums dark:border-zinc-800">
                      {s === undefined ? '…' : s === 'missing' ? <Missing reason={`No data for ${t}.`} /> : get(s)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
