import { lazy, Suspense } from 'react'
import { Link } from 'react-router'
import type { ReliabilityPoint } from '../components/ReliabilityChart'
import { LabelBadge } from '../components/LabelBadge'
import { CommitmentCard, LiveReportCard } from '../components/ReportCard'
import { Tip } from '../components/Tip'
import { Badge, Card, PageHeader } from '../components/ui'
import { useSiteJson } from '../lib/data'
import { formatDay, formatPct, formatPctAbs, formatPrice } from '../lib/format'

const ReliabilityChart = lazy(() => import('../components/ReliabilityChart'))

interface HorizonScore {
  n: number
  hit_rate_up: number
  hit_rate_beat: number
  mean_return: number
  mean_excess: number
  payoff: number | null
  brier_up: number | null
  reliability: ReliabilityPoint[]
}

interface ScorecardFile {
  generated_at: string
  labels: Record<string, Record<string, HorizonScore>>
  backtest: Record<string, { net_excess_annual: number | null; hit_rate: number | null; payoff: number | null; ev: number | null } | null> | null
  note?: string
}

interface LedgerEntry {
  seq: number
  date: string
  ticker: string
  label: string
  price: number
  p_hat: number | null
  ev: number | null
  model_version: string | null
  method: string | null
  hash: string
  outcomes: { horizon: string; return: number; excess: number; up: boolean }[]
}

interface LedgerFile {
  verified: boolean
  verify_detail: string
  count: number
  outcomes: number
  entries: LedgerEntry[]
}

export default function Scorecard() {
  const sc = useSiteJson<ScorecardFile>('scorecard.json')
  const lg = useSiteJson<LedgerFile>('ledger.json')
  return (
    <>
      <PageHeader title="Scorecard" subtitle="Predicted vs what actually happened. Every prediction is recorded before its outcome." />
      <div className="space-y-3">
        <LiveReportCard />
        <CommitmentCard repoUrl={import.meta.env.VITE_REPO_URL} />
        {lg.state === 'ready' && (
          <Card title="Prediction ledger" aside={<Badge tone={lg.data.verified ? 'good' : 'bad'}>{lg.data.verified ? 'Hash chain verified' : 'Chain broken'}</Badge>}>
            <p className="text-sm">
              {lg.data.count.toLocaleString('en-US')} signals recorded, {lg.data.outcomes.toLocaleString('en-US')} outcomes measured so far.{' '}
              <Tip content="Each entry includes the SHA-256 hash of the previous one, so no past prediction can be edited without breaking every later hash. The ledger lives in the private data repository; the daily job verifies it.">How tamper-proofing works</Tip>
            </p>
            {!lg.data.verified && <p className="mt-1 text-sm text-red-700">{lg.data.verify_detail}</p>}
            <ul className="mt-2 max-h-96 divide-y divide-slate-100 overflow-y-auto text-sm dark:divide-zinc-800">
              {lg.data.entries.slice(0, 120).map((e) => (
                <li key={e.seq} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span>
                    <span className="text-xs text-slate-500">#{e.seq} · {formatDay(e.date)}</span>{' '}
                    <Link to={`/stock/${encodeURIComponent(e.ticker)}`} className="font-semibold underline">{e.ticker}</Link> at {formatPrice(e.price)}{' '}
                    {e.p_hat !== null && <span className="text-xs text-slate-500">p̂ {Math.round(e.p_hat * 100)}%</span>}
                  </span>
                  <span className="flex flex-wrap items-center gap-1">
                    <LabelBadge label={e.label} />
                    {e.outcomes.map((o) => (
                      <Badge key={o.horizon} tone={o.excess > 0 ? 'good' : 'bad'}>{o.horizon}: {formatPct(o.excess)} vs S&P</Badge>
                    ))}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        )}
        {sc.state !== 'ready' ? (
          <Card>
            <p className="text-sm text-slate-500">{sc.state === 'loading' ? 'Loading…' : 'The scorecard appears after the first daily run with the ledger.'}</p>
          </Card>
        ) : (
          <>
            {sc.data.note && (
              <Card>
                <p className="text-sm">{sc.data.note}</p>
              </Card>
            )}
            {Object.entries(sc.data.labels).map(([label, hz]) => (
              <Card key={label} title={<span className="flex items-center gap-2">Live results: <LabelBadge label={label} /></span>}>
                <div className="-mx-4 overflow-x-auto px-4">
                  <table className="w-full min-w-max text-sm">
                    <thead>
                      <tr className="border-b border-slate-200 text-left text-xs text-slate-600 dark:border-zinc-700 dark:text-zinc-300">
                        <th className="px-2 py-1.5">Horizon</th>
                        <th className="px-2 py-1.5">Signals</th>
                        <th className="px-2 py-1.5">Went up</th>
                        <th className="px-2 py-1.5">Beat S&P 500</th>
                        <th className="px-2 py-1.5">Avg excess</th>
                        <th className="px-2 py-1.5">Payoff</th>
                        <th className="px-2 py-1.5"><Tip content="Mean squared error of the predicted chance of going up (lower is better).">Brier</Tip></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-zinc-800">
                      {Object.entries(hz).map(([h, v]) => (
                        <tr key={h}>
                          <th scope="row" className="px-2 py-1.5 text-left font-normal">{h}</th>
                          <td className="px-2 py-1.5 tabular-nums">{v.n}</td>
                          <td className="px-2 py-1.5 tabular-nums">{formatPctAbs(v.hit_rate_up, 0)}</td>
                          <td className="px-2 py-1.5 tabular-nums">{formatPctAbs(v.hit_rate_beat, 0)}</td>
                          <td className="px-2 py-1.5 tabular-nums">{formatPct(v.mean_excess)}</td>
                          <td className="px-2 py-1.5 tabular-nums">{v.payoff !== null ? v.payoff.toFixed(2) : '—'}</td>
                          <td className="px-2 py-1.5 tabular-nums">{v.brier_up !== null ? v.brier_up.toFixed(3) : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {Object.entries(hz)
                  .filter(([, v]) => v.reliability.length > 1)
                  .slice(0, 1)
                  .map(([h, v]) => (
                    <Suspense key={h} fallback={<div className="h-56" />}>
                      <h3 className="mt-3 text-sm font-semibold">Reliability, {h}: predicted chance of going up vs what happened</h3>
                      <ReliabilityChart points={v.reliability} label={`Reliability ${h}`} />
                    </Suspense>
                  ))}
              </Card>
            ))}
            {sc.data.backtest && (
              <Card title="Backtest reference (app picks, halved)">
                <ul className="text-sm">
                  {Object.entries(sc.data.backtest).map(([k, v]) => (
                    <li key={k} className="py-1">
                      <span className="font-medium">{k}:</span>{' '}
                      {v ? `net excess ${v.net_excess_annual !== null ? formatPct(v.net_excess_annual * 0.5) : '—'}/yr · hit rate ${v.hit_rate !== null ? formatPctAbs(v.hit_rate, 0) : '—'} · payoff ${v.payoff !== null ? v.payoff.toFixed(2) : '—'} · EV ${v.ev !== null ? formatPct(v.ev * 0.5, 2) : '—'}` : '—'}
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </>
        )}
      </div>
    </>
  )
}
