import { lazy, Suspense } from 'react'
import type { ReliabilityPoint } from '../components/ReliabilityChart'
import { Tip } from '../components/Tip'
import { ExperimentsCard, MoreResearchCard, ResearchCard } from '../components/ResearchCards'
import { Badge, Card, PageHeader } from '../components/ui'
import { useSiteJson } from '../lib/data'
import { formatDateTime, formatPct, formatPctAbs } from '../lib/format'

const ReliabilityChart = lazy(() => import('../components/ReliabilityChart'))

interface StrategySummary {
  months: number
  net_excess_annual: number | null
  t_stat: number
  sharpe_annual: number
  max_drawdown: number
  turnover: number
  trades: number
  hit_rate: number | null
  payoff: number | null
  ev: number | null
}

interface CalBlock {
  brier: number
  brier_base: number
  slope: number | null
  reliability: ReliabilityPoint[]
  n?: number
}

interface PeriodBlock {
  years?: number[]
  period?: string[]
  strategies: Record<string, StrategySummary>
  cost_stress_2x: StrategySummary
  by_regime?: Record<string, number>
  by_sector?: Record<string, number>
  by_size?: Record<string, number>
  calibration: { trade?: CalBlock } & Record<string, { up: CalBlock; beat: CalBlock; coverage_80: number; n: number } | CalBlock | undefined>
  calibration_note?: string
}

interface ValidationFile {
  generated_at: string
  periods: Record<string, PeriodBlock>
  holdout: PeriodBlock | null
  holdout_touches: number
  overfitting: { trials: number; deflated_sharpe: number; pbo: number | null }
  ablation: { full_model: Record<string, number | null>; families: Record<string, { without: Record<string, number | null>; loss_when_removed: Record<string, number | null>; keep: boolean }> }
  verdict: { checks: { check: string; passed: boolean | null; value: string }[]; validated: string[]; summary: string; horizons: Record<string, { up?: boolean; beat?: boolean; coverage_80?: number | null; passed?: boolean }> }
  notes: string[]
}

const NAMES: Record<string, string> = {
  app: 'App (top 2% by model rank)',
  app_meta: 'App + meta-model filter',
  baseline_momentum: 'Baseline: momentum only',
  baseline_family_average: 'Baseline: equal-weight family average',
  baseline_all_eligible: 'Baseline: all eligible stocks',
}

const fmt = (v: number | null | undefined, f: (x: number) => string) => (v === null || v === undefined || Number.isNaN(v) ? '—' : f(v))
/** Spec: halve every backtested excess return before showing it (free data lacks delisted stocks). */
const HAIRCUT = 0.5
const hc = (v: number | null | undefined) => (v === null || v === undefined ? v : v * HAIRCUT)

function StrategyTable({ s, stress }: { s: Record<string, StrategySummary>; stress?: StrategySummary }) {
  const rows = Object.entries(s)
  return (
    <div className="-mx-4 overflow-x-auto px-4">
      <table className="w-full min-w-max text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-xs text-slate-600 dark:border-zinc-700 dark:text-zinc-300">
            <th className="px-2 py-1.5">Strategy</th>
            <th className="px-2 py-1.5"><Tip content="Average monthly return above the S&P 500 after costs, × 12, then halved (survivorship haircut).">Net excess / year (halved)</Tip></th>
            <th className="px-2 py-1.5"><Tip content="t-statistic of the monthly excess returns (≥ 2 needed).">t</Tip></th>
            <th className="px-2 py-1.5">Max drawdown</th>
            <th className="px-2 py-1.5">Turnover / month</th>
            <th className="px-2 py-1.5"><Tip content="Share of 60-day trades that beat the S&P 500 after costs. Never read alone: see payoff and EV.">Hit rate</Tip></th>
            <th className="px-2 py-1.5"><Tip content="Average winning excess ÷ average losing excess.">Payoff</Tip></th>
            <th className="px-2 py-1.5"><Tip content="Average 60-day excess return per trade after costs, halved (survivorship haircut).">EV / trade (halved)</Tip></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-zinc-800">
          {[...rows, ...(stress ? [['App with 2× costs', stress] as [string, StrategySummary]] : [])].map(([k, v]) => (
            <tr key={k}>
              <th scope="row" className="px-2 py-1.5 text-left font-normal">{NAMES[k] ?? k}</th>
              <td className="px-2 py-1.5 tabular-nums">{fmt(hc(v.net_excess_annual), (x) => formatPct(x))}</td>
              <td className="px-2 py-1.5 tabular-nums">{fmt(v.t_stat, (x) => x.toFixed(2))}</td>
              <td className="px-2 py-1.5 tabular-nums">{fmt(v.max_drawdown, (x) => formatPct(x, 0))}</td>
              <td className="px-2 py-1.5 tabular-nums">{fmt(v.turnover, (x) => formatPctAbs(x, 0))}</td>
              <td className="px-2 py-1.5 tabular-nums">{fmt(v.hit_rate, (x) => formatPctAbs(x, 0))}</td>
              <td className="px-2 py-1.5 tabular-nums">{fmt(v.payoff, (x) => x.toFixed(2))}</td>
              <td className="px-2 py-1.5 tabular-nums">{fmt(hc(v.ev), (x) => formatPct(x, 2))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Breakdown({ title, data }: { title: string; data?: Record<string, number> }) {
  if (!data || !Object.keys(data).length) return null
  return (
    <div>
      <h3 className="text-xs font-semibold text-slate-600 dark:text-zinc-400">{title} (net excess / year of the app’s picks, halved)</h3>
      <ul className="mt-1 flex flex-wrap gap-1.5 text-xs">
        {Object.entries(data).map(([k, v]) => (
          <li key={k} className="rounded-full border border-slate-200 px-2 py-0.5 dark:border-zinc-700">{k}: {formatPct(v * HAIRCUT)}</li>
        ))}
      </ul>
    </div>
  )
}

function Calibration({ c, note }: { c: PeriodBlock['calibration']; note?: string }) {
  const trade = c.trade
  const horizons = Object.entries(c).filter(([k]) => k !== 'trade') as [string, { up: CalBlock; beat: CalBlock; coverage_80: number; n: number }][]
  return (
    <div className="space-y-3">
      {note && <p className="text-xs text-slate-500">{note}</p>}
      {trade && (
        <div>
          <h4 className="text-sm font-semibold">60-day trade (“p̂”): Brier {trade.brier.toFixed(4)} vs base rate {trade.brier_base.toFixed(4)} · slope {trade.slope?.toFixed(2) ?? '—'}</h4>
          {trade.reliability.length > 1 && (
            <Suspense fallback={<div className="h-56" />}>
              <ReliabilityChart points={trade.reliability} label="Reliability of p̂" />
            </Suspense>
          )}
        </div>
      )}
      {horizons.length > 0 && (
        <div className="-mx-4 overflow-x-auto px-4">
          <table className="w-full min-w-max text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs text-slate-600 dark:border-zinc-700 dark:text-zinc-300">
                <th className="px-2 py-1.5">Horizon</th>
                <th className="px-2 py-1.5">P(up): Brier vs base · slope</th>
                <th className="px-2 py-1.5">P(beat): Brier vs base · slope</th>
                <th className="px-2 py-1.5"><Tip content="Share of outcomes inside the conformal 80% range (target 80%).">80% range coverage</Tip></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-zinc-800">
              {horizons.map(([h, v]) => (
                <tr key={h}>
                  <th scope="row" className="px-2 py-1.5 text-left font-normal">{h}</th>
                  <td className="px-2 py-1.5 tabular-nums">{v.up.brier.toFixed(4)} vs {v.up.brier_base.toFixed(4)} · {v.up.slope?.toFixed(2) ?? '—'}</td>
                  <td className="px-2 py-1.5 tabular-nums">{v.beat.brier.toFixed(4)} vs {v.beat.brier_base.toFixed(4)} · {v.beat.slope?.toFixed(2) ?? '—'}</td>
                  <td className="px-2 py-1.5 tabular-nums">{formatPctAbs(v.coverage_80, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function Period({ title, p }: { title: string; p: PeriodBlock }) {
  return (
    <Card title={title}>
      <StrategyTable s={p.strategies} stress={p.cost_stress_2x} />
      <div className="mt-3 space-y-2">
        <Breakdown title="By regime" data={p.by_regime} />
        <Breakdown title="By sector" data={p.by_sector} />
        <Breakdown title="By size" data={p.by_size} />
      </div>
      <h3 className="mt-4 mb-1 text-sm font-semibold">Calibration</h3>
      <Calibration c={p.calibration} note={p.calibration_note} />
    </Card>
  )
}

export default function Validation() {
  const res = useSiteJson<ValidationFile>('validation.json')
  return (
    <>
      <PageHeader title="Validation" subtitle="The test every probability must pass before leaving RESEARCH MODE. Failures included." />
      {res.state !== 'ready' ? (
        <Card>
          <p className="text-sm text-slate-600 dark:text-zinc-400">
            {res.state === 'loading' ? 'Loading…' : 'No validation report yet. It is produced by the weekly training job (walk-forward 2016–2023, holdout 2024 to mid-2026 evaluated once).'}
          </p>
        </Card>
      ) : (
        <div className="space-y-3">
          <Card title="Verdict" aside={<Badge tone={res.data.verdict.validated.length ? 'good' : 'warn'}>{res.data.verdict.validated.length ? `${res.data.verdict.validated.length} item(s) validated` : 'Still in research mode'}</Badge>}>
            <p className="text-sm">{res.data.verdict.summary}</p>
            <ul className="mt-2 divide-y divide-slate-100 text-sm dark:divide-zinc-800">
              {res.data.verdict.checks.map((c) => (
                <li key={c.check} className="flex items-start justify-between gap-3 py-2">
                  <span>
                    {c.check}
                    <span className="block text-xs text-slate-500 dark:text-zinc-400">{c.value}</span>
                  </span>
                  <Badge tone={c.passed === true ? 'good' : c.passed === false ? 'bad' : 'neutral'}>{c.passed === true ? 'Pass' : c.passed === false ? 'Fail' : 'No data'}</Badge>
                </li>
              ))}
            </ul>
            {res.data.notes.map((n) => (
              <p key={n} className="mt-2 text-sm text-amber-800 dark:text-amber-300">{n}</p>
            ))}
            <p className="mt-2 text-xs text-slate-500">
              Report generated {formatDateTime(res.data.generated_at)}. Every backtested excess return on this site is halved before it is shown, because free data mostly lacks delisted stocks (survivorship bias). The pass/fail checks use the raw t-statistics and the halved excess over the best baseline.
            </p>
          </Card>
          {Object.entries(res.data.periods).map(([k, p]) => (
            <Period key={k} title={`${k[0]!.toUpperCase()}${k.slice(1)} (${p.years?.join('–')})`} p={p} />
          ))}
          {res.data.holdout && <Period title={`Holdout (${res.data.holdout.period?.join(' to ')}) — evaluated ${res.data.holdout_touches === 1 ? 'once' : `${res.data.holdout_touches} times`}`} p={res.data.holdout} />}
          <Card title="Overfitting checks">
            <dl className="text-sm">
              <div className="flex justify-between py-1"><dt><Tip content="Probability that the true Sharpe ratio beats what the best of all tried variants would show by luck. Needs ≥ 0.95.">Deflated Sharpe ratio</Tip></dt><dd className="tabular-nums">{res.data.overfitting.deflated_sharpe.toFixed(2)}</dd></div>
              <div className="flex justify-between py-1"><dt><Tip content="Probability of backtest overfitting (combinatorially symmetric cross-validation). Needs ≤ 20%.">PBO</Tip></dt><dd className="tabular-nums">{res.data.overfitting.pbo === null ? '—' : formatPctAbs(res.data.overfitting.pbo, 0)}</dd></div>
              <div className="flex justify-between py-1"><dt>Variants tried (trials)</dt><dd className="tabular-nums">{res.data.overfitting.trials}</dd></div>
            </dl>
          </Card>
          <Card title="Ablation: drop one family at a time">
            <div className="-mx-4 overflow-x-auto px-4">
              <table className="w-full min-w-max text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-xs text-slate-600 dark:border-zinc-700 dark:text-zinc-300">
                    <th className="px-2 py-1.5">Family removed</th>
                    <th className="px-2 py-1.5">Loss (development)</th>
                    <th className="px-2 py-1.5">Loss (validation)</th>
                    <th className="px-2 py-1.5">Keep?</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-zinc-800">
                  {Object.entries(res.data.ablation.families).map(([fam, v]) => (
                    <tr key={fam}>
                      <th scope="row" className="px-2 py-1.5 text-left font-normal">{fam}</th>
                      <td className="px-2 py-1.5 tabular-nums">{fmt(v.loss_when_removed.development, (x) => formatPct(x))}</td>
                      <td className="px-2 py-1.5 tabular-nums">{fmt(v.loss_when_removed.validation, (x) => formatPct(x))}</td>
                      <td className="px-2 py-1.5"><Badge tone={v.keep ? 'good' : 'neutral'}>{v.keep ? 'Keep' : 'No proven value'}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-slate-500">A family is kept only if removing it lowers net excess by at least 0.5%/year in both development and validation. F1 (opinion) and F2 (revisions) have no point-in-time history yet, so they carry zero model weight.</p>
          </Card>
        </div>
      )}
      <div className="mt-3 space-y-3">
        <ResearchCard />
        <MoreResearchCard />
        <ExperimentsCard />
      </div>
    </>
  )
}
