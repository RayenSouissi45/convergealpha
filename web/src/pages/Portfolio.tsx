import { useEffect } from 'react'
import { Link, useSearchParams } from 'react-router'
import { HoldingsTab } from '../components/portfolio/HoldingsTab'
import { JournalTab } from '../components/portfolio/JournalTab'
import { LogTradeTab } from '../components/portfolio/LogTradeTab'
import { ReviewTab } from '../components/portfolio/ReviewTab'
import { RulesTab } from '../components/portfolio/RulesTab'
import { TaxTab } from '../components/portfolio/TaxTab'
import { PageHeader } from '../components/ui'
import { formatDay } from '../lib/format'
import { useFx } from '../lib/fx'
import { positions, useJournal } from '../lib/journal'
import { useScreener } from '../lib/screener'
import type { ScreenerRow } from '../types'

const TABS = [
  ['holdings', 'Holdings'],
  ['log', 'Log a trade'],
  ['journal', 'Journal'],
  ['review', 'Review'],
  ['taxes', 'Taxes'],
  ['rules', 'My rules'],
] as const
type Tab = (typeof TABS)[number][0]

export default function Portfolio() {
  const [params] = useSearchParams()
  const tab: Tab = TABS.find(([k]) => k === params.get('tab'))?.[0] ?? 'holdings'
  const [j, setJ] = useJournal()
  const screener = useScreener(true)
  const fx = useFx()
  const rows: Map<string, ScreenerRow> = screener.state === 'ready' ? screener.data.byTicker : new Map()
  const ps = positions(j, rows, fx?.rate ?? null)
  const total = ps.reduce((s, p) => s + (p.valueEur ?? p.costEur), 0) + (j.cashEur ?? 0)
  // The drawdown brake needs the highest total seen.
  useEffect(() => {
    if (screener.state === 'ready' && fx && total > (j.peakEur ?? 0)) setJ({ ...j, peakEur: total })
  }, [screener.state, fx, total, j, setJ])
  return (
    <>
      <PageHeader title="My portfolio" subtitle="Your real trades on finanzen.net zero, in euros, with your own rules and German tax. Stored only in this browser." />
      <nav aria-label="Portfolio" className="-mx-1 mb-3 flex gap-1 overflow-x-auto px-1 pb-1">
        {TABS.map(([k, label]) => (
          <Link
            key={k}
            to={`/portfolio?tab=${k}`}
            aria-current={tab === k ? 'page' : undefined}
            className={`inline-flex min-h-11 shrink-0 items-center rounded-full border px-3 text-sm font-medium ${tab === k ? 'border-teal-700 bg-teal-700 text-white dark:border-teal-500 dark:bg-teal-600' : 'border-slate-300 bg-white dark:border-zinc-600 dark:bg-zinc-900'}`}
          >
            {label}
          </Link>
        ))}
      </nav>
      {fx && (tab === 'holdings' || tab === 'log') && (
        <p className="mb-2 text-xs text-slate-500 dark:text-zinc-400">
          Euro values use {fx.rate.toFixed(4)} $/€ ({fx.source === 'ECB' ? 'European Central Bank' : 'FRED'}, {formatDay(fx.date)}); gettex prices differ a little.
        </p>
      )}
      {tab === 'holdings' && <HoldingsTab j={j} setJ={setJ} ps={ps} rows={rows} fx={fx?.rate ?? null} />}
      {tab === 'log' && <LogTradeTab key={params.toString()} j={j} setJ={setJ} ps={ps} rows={rows} fx={fx?.rate ?? null} />}
      {tab === 'journal' && <JournalTab j={j} setJ={setJ} />}
      {tab === 'review' && <ReviewTab j={j} />}
      {tab === 'taxes' && <TaxTab j={j} ps={ps} />}
      {tab === 'rules' && <RulesTab j={j} setJ={setJ} />}
    </>
  )
}
