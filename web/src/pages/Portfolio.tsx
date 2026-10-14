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
import { journalView, positions, useJournal, type Journal } from '../lib/journal'
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
  // Real money by default; paper trades (practice, e.g. a copied strategy) are kept apart.
  const paper = params.get('paper') === '1'
  const [all, setAll] = useJournal()
  const { view: j, merge } = journalView(all, paper)
  const setJ = (next: Journal) => setAll(merge(next))
  const screener = useScreener(true)
  const fx = useFx()
  const rows: Map<string, ScreenerRow> = screener.state === 'ready' ? screener.data.byTicker : new Map()
  const ps = positions(j, rows, fx?.rate ?? null)
  const total = ps.reduce((s, p) => s + (p.valueEur ?? p.costEur), 0) + (j.cashEur ?? 0)
  // The drawdown brake needs the highest total seen.
  useEffect(() => {
    if (!paper && screener.state === 'ready' && fx && total > (all.peakEur ?? 0)) setAll({ ...all, peakEur: total })
  }, [paper, screener.state, fx, total, all, setAll])
  return (
    <>
      <PageHeader title="My portfolio" subtitle="Your real trades on finanzen.net zero, in euros, with your own rules and German tax. Stored only in this browser." />
      <div className="mb-2 inline-flex rounded-xl bg-slate-100 p-1 text-sm font-semibold dark:bg-zinc-800" role="group" aria-label="Money">
        {([false, true] as const).map((pp) => (
          <Link key={String(pp)} to={`/portfolio?tab=${tab}${pp ? '&paper=1' : ''}`} aria-current={paper === pp ? 'page' : undefined} className={`inline-flex min-h-11 items-center rounded-lg px-3 ${paper === pp ? 'bg-white text-slate-900 shadow-xs dark:bg-zinc-950 dark:text-zinc-100' : 'text-slate-600 dark:text-zinc-400'}`}>
            {pp ? 'Paper (practice)' : 'Real money'}
          </Link>
        ))}
      </div>
      {paper && <p className="mb-2 text-sm text-slate-600 dark:text-zinc-400">Paper trades: practice a plan or a copied strategy before using real money. They are kept apart from your real holdings, results and German tax.</p>}
      <nav aria-label="Portfolio" className="-mx-1 mb-3 flex gap-1 overflow-x-auto px-1 pb-1">
        {TABS.map(([k, label]) => (
          <Link
            key={k}
            to={`/portfolio?tab=${k}${paper ? '&paper=1' : ''}`}
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
      {tab === 'review' && <ReviewTab j={j} rows={rows} total={total} />}
      {tab === 'taxes' && <TaxTab j={j} ps={ps} />}
      {tab === 'rules' && <RulesTab j={j} setJ={setJ} />}
    </>
  )
}
