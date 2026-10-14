import { useDeferredValue, useMemo, type ReactNode } from 'react'
import { Link } from 'react-router'
import { LabelBadge } from '../components/LabelBadge'
import { OppBadge } from '../components/Opportunity'
import { isOpp } from '../lib/opportunity'
import { Tip } from '../components/Tip'
import { Badge, Card, PageHeader } from '../components/ui'
import { FeeSettings } from '../components/FeeSettings'
import { TaxSettings } from '../components/TaxSettings'
import { ZeroBadge, ZeroToggle } from '../components/Zero'
import { formatEur, formatEurSigned, formatShares } from '../lib/costs'
import { useSiteJson } from '../lib/data'
import { formatDay, formatInt, formatPct } from '../lib/format'
import { evaluate, evaluateSplit, mapPeriod, rank, sliderMin, toPlanRows, type Context, type Evaluation, type PlanRow, type Rel, type SplitEvaluation, type Verdict } from '../lib/plan'
import { feesFrom, taxFrom, useTradeSettings } from '../lib/settings'
import { taxOnGain } from '../lib/taxes'
import { useBrokerList, useOnlyZero, zeroAvailability } from '../lib/zero'
import type { PlanFile } from '../types'


const VERDICT_STYLE: Record<Verdict['color'], string> = {
  green: 'border-emerald-300 bg-emerald-50 text-emerald-950 dark:border-emerald-700/60 dark:bg-emerald-950/60 dark:text-emerald-100',
  amber: 'border-amber-300 bg-amber-50 text-amber-950 dark:border-amber-700/60 dark:bg-amber-950/60 dark:text-amber-100',
  grey: 'border-slate-300 bg-slate-50 text-slate-800 dark:border-zinc-600 dark:bg-zinc-800/60 dark:text-zinc-100',
}
const VERDICT_MARK: Record<Verdict['color'], string> = { green: '●', amber: '◐', grey: '○' }

export function VerdictBox({ v }: { v: Verdict }) {
  return (
    <div role="status" className={`rounded-lg border px-3 py-2 text-sm ${VERDICT_STYLE[v.color]}`}>
      <p className="font-semibold">
        <span aria-hidden="true">{VERDICT_MARK[v.color]} </span>
        {v.color === 'green' ? 'GREEN' : v.color === 'amber' ? 'AMBER' : 'GREY'}: {v.title}
      </p>
      {v.why.length > 0 && <p className="mt-0.5 text-xs">{v.color === 'green' ? 'All checks pass: ' : 'Because: '}{v.why.join('; ')}.</p>}
    </div>
  )
}

export function ValidTag({ ok }: { ok: boolean }) {
  return ok ? <Badge tone="good">✓ validated</Badge> : <Badge tone="warn">RESEARCH MODE</Badge>
}

function relText(r: Rel | null): ReactNode {
  if (!r) return <span className="text-slate-500 dark:text-zinc-400">no past record</span>
  return (
    <>
      {Math.round(r.rate * 100)}% <span className="text-xs text-slate-500 dark:text-zinc-400">(range {Math.round(r.lo * 100)}–{Math.round(r.hi * 100)}%, {formatInt(r.n)} past cases)</span>
    </>
  )
}

function Line({ label, help, children }: { label: string; help: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-slate-100 py-1.5 text-sm last:border-0 dark:border-zinc-800">
      <dt className="text-slate-600 dark:text-zinc-400">
        <Tip content={help} className="text-left">
          {label}
        </Tip>
      </dt>
      <dd className="text-right font-medium tabular-nums">{children}</dd>
    </div>
  )
}

/** The numbers every suggestion shows (Plan and "Give me a strategy"). */
export function OutcomeLines({ e, amount, validated }: { e: Pick<Evaluation, 'breakEven' | 'pProfit' | 'middle' | 'bad' | 'good' | 'rel'> & { shares: number; leftover: number; fees: number }; amount: number; validated: boolean }) {
  const [settings] = useTradeSettings()
  const tax = taxOnGain(e.middle, taxFrom(settings))
  return (
    <dl>
      <Line label="Shares you can buy" help="Whole shares (a fraction only with the simulation setting). The price includes half the estimated spread.">
        {formatShares(e.shares)}
      </Line>
      <Line label="Money left over" help="What is not spent on shares or the buy fee. It stays as cash.">{formatEur(e.leftover)}</Line>
      <Line label="Total fees" help="The buy fee now and the sell fee later. The spread comes on top and is inside the break-even move.">{formatEur(e.fees)}</Line>
      <Line label="Break-even move" help="How much the stock must rise just to get back the money spent, after both fees and the spread (the euro rate unchanged).">
        the stock must rise {formatPct(e.breakEven, 1)}
      </Line>
      <Line label="Chance of ending with more money" help="Chance the stock rises more than the break-even move by the end of the period: the calibrated chance up, lowered by the part of the forecast range between 0 and the break-even move.">
        <span className="inline-flex flex-wrap items-center justify-end gap-1.5">
          {Math.round(e.pProfit * 100)}% <ValidTag ok={validated} />
        </span>
      </Line>
      <Line label="How often right" help="When the app gave a similar chance up before (2016–2023, out of sample), how often the stock really was higher at the end. The range is the 95% Wilson range.">
        {relText(e.rel)}
      </Line>
      <Line label="Middle result" help="If the stock ends at the middle forecast: half of the outcomes are expected better, half worse. After fees and spread.">
        {formatEur(amount + e.middle)} <span className="text-xs">({formatEurSigned(e.middle)})</span>
      </Line>
      {e.middle > 0 && (
        <Line label="Middle result after German tax" help="The middle gain after the tax on it (25% plus solidarity surcharge, plus church tax if set), once your allowance left this year is used up. Losses are not taxed. Set your tax profile on the Plan page.">
          {formatEur(amount + tax.net)} <span className="text-xs">(tax {formatEur(tax.tax)})</span>
        </Line>
      )}
      <Line label="Bad case (1 in 10)" help="Only 1 in 10 outcomes is expected worse than this (the 10th percentile forecast). It can be worse: this is not a maximum loss.">
        {formatEur(amount + e.bad)} <span className="text-xs">({formatEurSigned(e.bad)})</span>
      </Line>
      <Line label="Good case (1 in 10)" help="Only 1 in 10 outcomes is expected better than this (the 90th percentile forecast).">
        {formatEur(amount + e.good)} <span className="text-xs">({formatEurSigned(e.good)})</span>
      </Line>
    </dl>
  )
}

function StockCard({ r, e, place, amount }: { r: PlanRow; e: Evaluation; place: number; amount: number }) {
  return (
    <li className="min-w-0">
      <Card>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="text-xs font-semibold text-slate-500 tabular-nums dark:text-zinc-400">#{place}</span>
              <Link to={`/stock/${encodeURIComponent(r.ticker)}`} className="text-lg font-semibold text-teal-700 underline-offset-2 hover:underline dark:text-teal-400">
                {r.ticker}
              </Link>
              <ZeroBadge value={r.zero} />
            </div>
            <p className="truncate text-sm text-slate-600 dark:text-zinc-400" title={r.name ?? undefined}>
              {r.name ?? '—'}
            </p>
          </div>
          <LabelBadge label={r.label} />
        </div>
        <p className="mt-1 text-xs text-slate-500 dark:text-zinc-400">
          Safety {Math.round(r.safety ?? 0)} · Upside {Math.round(r.upside ?? 0)} · Confidence {Math.round(r.confidence ?? 0)}
          {r.next_earnings ? ` · earnings ${formatDay(r.next_earnings)}` : ''}
        </p>
        {isOpp(r.opp) && (
          <div className="mt-1.5 flex flex-wrap items-center gap-1 text-xs">
            <OppBadge ticker={r.ticker} color={r.opp} compact />
            <span className="text-slate-600 dark:text-zinc-400">{r.opp_event}</span>
          </div>
        )}
        <div className="mt-3">
          <VerdictBox v={e.verdict} />
        </div>
        <div className="mt-2">
          <OutcomeLines e={{ ...e, shares: e.buy.shares, leftover: e.buy.leftover }} amount={amount} validated={e.validated} />
        </div>
      </Card>
    </li>
  )
}

function SplitCard({ a, b, s, amount }: { a: PlanRow; b: PlanRow; s: SplitEvaluation; amount: number }) {
  return (
    <Card title={`Split the amount over the top 2: ${a.ticker} + ${b.ticker}`}>
      <p className="mb-2 text-xs text-slate-600 dark:text-zinc-400">
        {formatEur(amount / 2)} each; every order pays its own fee. Cautious assumption: the two stocks move together, so the range shown is as wide as it can be (owning two different stocks can only narrow it).
      </p>
      <VerdictBox v={s.verdict} />
      <div className="mt-2">
        <OutcomeLines e={s} amount={amount} validated={s.validated} />
      </div>
    </Card>
  )
}

function Slider({ id, label, value, onChange, help, min = 1, max = 10, suffix }: { id: string; label: string; value: number; onChange: (v: number) => void; help: string; min?: number; max?: number; suffix: string }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <label htmlFor={id} className="font-medium">
          {label}: <span className="tabular-nums">{value}</span>
        </label>
        <span className="text-xs text-slate-500 dark:text-zinc-400">{suffix}</span>
      </div>
      <input id={id} type="range" min={min} max={max} step={1} value={value} onChange={(e) => onChange(Number(e.target.value))} className="h-11 w-full accent-teal-700" aria-describedby={`${id}-help`} />
      <p id={`${id}-help`} className="text-xs text-slate-500 dark:text-zinc-400">
        {help}
      </p>
    </div>
  )
}

const input = 'min-h-11 w-full rounded-lg border border-slate-300 bg-white px-2 text-base dark:border-zinc-600 dark:bg-zinc-800'
const PERIODS: [string, number][] = [
  ['1 week', 7],
  ['1 month', 30],
  ['3 months', 90],
  ['6 months', 180],
]

export default function Plan() {
  const res = useSiteJson<PlanFile>('plan.json')
  const [s, set] = useTradeSettings()
  const [onlyZero] = useOnlyZero()
  const zeroOk = zeroAvailability(useBrokerList()).ok
  const rows = useMemo(() => (res.state === 'ready' ? toPlanRows(res.data) : []), [res])
  const deferred = useDeferredValue(s)
  const m = mapPeriod(deferred.days)

  const header = (
    <>
      <PageHeader title="Plan" subtitle="Choose how safe, how much upside, how long and how much money. The app shows its best fits and what they could mean in euros, after costs." />
      <div role="note" className="mb-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:border-amber-700/60 dark:bg-amber-950/60 dark:text-amber-100">
        <strong>Research tool, not advice.</strong> Numbers marked RESEARCH MODE have not passed validation. Nothing here places an order.
      </div>
    </>
  )

  const fileOk = res.state === 'ready'
  const f = fileOk ? res.data : null
  const ctx: Context | null =
    f && f.fx
      ? { fx: f.fx.rate, fees: feesFrom(deferred), mix: m, reliability: f.reliability, validated: f.validated }
      : null
  const td = m.td
  // A filter and a sort over about 2,000 rows: cheap enough for every change.
  const ranked = rank(rows, { safety: deferred.safety, upside: deferred.upside, td, allowEarnings: deferred.allowEarnings, onlyZero: onlyZero && zeroOk })
  const picks: { r: PlanRow; e: Evaluation }[] = []
  let tooExpensive = 0
  if (ctx) {
    for (const r of ranked.rows) {
      const e = evaluate(r, deferred.amount, ctx)
      if (!e) {
        tooExpensive++
        continue
      }
      picks.push({ r, e })
      if (picks.length >= 3) break
    }
  }
  const [first, second] = picks
  const split = ctx && first && second ? { a: first.r, b: second.r, s: evaluateSplit(first.r, second.r, deferred.amount, ctx) } : null
  const usedValidated = f ? m.used.every((h) => f.validated.includes(`P(up) ${h}`)) : false

  return (
    <>
      {header}
      <Card title="Your plan">
        <div className="space-y-4">
          <Slider id="plan-safety" label="Safety" value={s.safety} onChange={(v) => set({ safety: v })} suffix={`Safety score ≥ ${sliderMin(s.safety)}`} help="1 = any risk is fine, 10 = only the calmest stocks (Picks Safety score: low swings, smaller bad case, solid business, no report soon)." />
          <Slider id="plan-upside" label="Upside" value={s.upside} onChange={(v) => set({ upside: v })} suffix={`Upside score ≥ ${sliderMin(s.upside)}`} help="1 = small gains are fine, 10 = only the biggest expected gains (Picks Upside score)." />
          <div>
            <Slider id="plan-days" label="Period" value={s.days} min={5} max={180} onChange={(v) => set({ days: v })} suffix={`days ≈ ${m.td} trading days`} help="How long you plan to keep the money in, in calendar days (5 to 180)." />
            <div className="mt-1 flex flex-wrap gap-1.5" role="group" aria-label="Quick periods">
              {PERIODS.map(([label, d]) => (
                <button key={d} type="button" aria-pressed={s.days === d} onClick={() => set({ days: d })} className={`min-h-11 rounded-full border px-3 text-sm ${s.days === d ? 'border-teal-700 bg-teal-700 text-white dark:border-teal-500 dark:bg-teal-600' : 'border-slate-300 bg-white dark:border-zinc-600 dark:bg-zinc-900'}`}>
                  {label}
                </button>
              ))}
            </div>
          </div>
          <label className="block text-sm font-medium">
            Amount in euros
            <input type="number" inputMode="decimal" min={1} step={10} value={s.amount} onChange={(e) => set({ amount: Number(e.target.value) || 1 })} className={`${input} mt-1`} />
          </label>
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <input type="checkbox" className="size-6 accent-teal-700" checked={s.allowEarnings} onChange={(e) => set({ allowEarnings: e.target.checked })} />
            Allow stocks that report earnings inside the period
          </label>
          <ZeroToggle values={rows.map((r) => r.zero)} noun="candidates" />
          <FeeSettings />
          <TaxSettings />
        </div>
      </Card>

      <div className="my-3 space-y-1 text-sm">
        <p>
          <strong>Forecast used:</strong> {m.text} <ValidTag ok={usedValidated} />
        </p>
        {f?.fx && (
          <p className="text-xs text-slate-600 dark:text-zinc-400">
            Prices in euros at {f.fx.rate.toFixed(4)} US dollars per euro ({f.fx.source === 'ECB' ? 'European Central Bank reference rate' : `FRED ${f.fx.series}, published about weekly`}, {formatDay(f.fx.date)}). The results assume this rate stays the same: a currency move can add or remove a few percent.
          </p>
        )}
      </div>

      {res.state !== 'ready' ? (
        <Card>
          <p className="text-sm text-slate-600 dark:text-zinc-400">
            {res.state === 'loading' ? 'Loading candidates…' : res.state === 'missing' ? 'The Plan builder appears after the next daily pipeline run.' : `Could not load the candidates (${res.message}).`}
          </p>
        </Card>
      ) : !f?.fx ? (
        <Card>
          <p className="text-sm text-slate-600 dark:text-zinc-400">The EUR/USD rate is not available yet (FRED DEXUSEU), so euro amounts cannot be computed. It arrives with the next daily run.</p>
        </Card>
      ) : (
        <>
          <p className="mb-2 text-xs text-slate-600 dark:text-zinc-400" aria-live="polite">
            {formatInt(ranked.rows.length)} of {formatInt(rows.length)} candidates fit. Left out: {formatInt(ranked.left.safety)} below the Safety minimum, {formatInt(ranked.left.upside)} below the Upside minimum
            {s.allowEarnings ? '' : `, ${formatInt(ranked.left.earnings)} report earnings inside the period, ${formatInt(ranked.left.noDate)} without a known earnings date`}
            {onlyZero && zeroOk ? `, ${formatInt(ranked.left.zero)} not on finanzen.net zero` : ''}
            {tooExpensive ? `; ${formatInt(tooExpensive)} skipped because one share costs more than your amount` : ''}.
          </p>
          {picks.length === 0 ? (
            <Card>
              <VerdictBox v={{ color: 'grey', title: 'No good opportunity now: waiting is a valid choice', why: [] }} />
              <p className="mt-2 text-sm text-slate-600 dark:text-zinc-400">
                No stock fits all your choices.{' '}
                {!s.allowEarnings && m.td >= 50
                  ? 'Every company reports earnings about every 3 months, so over a long period almost every stock has a report inside it: tick “Allow stocks that report earnings inside the period”.'
                  : 'Try lower Safety or Upside, a larger amount, or allow earnings reports.'}
              </p>
            </Card>
          ) : (
            <ol className="grid grid-cols-1 gap-3 lg:grid-cols-2" aria-label="Best fits">
              {picks.map(({ r, e }, i) => (
                <StockCard key={r.ticker} r={r} e={e} place={i + 1} amount={s.amount} />
              ))}
            </ol>
          )}
          {split?.s && (
            <div className="mt-3">
              <SplitCard a={split.a} b={split.b} s={split.s} amount={s.amount} />
            </div>
          )}
        </>
      )}

      <Card title="How the Plan works" className="mt-4">
        <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-slate-700 dark:text-zinc-300">
          <li>Candidates: eligible stocks without a SELL / RISK WARNING label or a blocking event, with a full forecast (the same as Picks), {f ? `${formatInt(f.count)} today` : ''}.</li>
          <li>Safety and Upside sliders set minimum scores: 1 → 0, 10 → 90 (straight line). The scores are the Picks sub-scores, 0–100 within the sector.</li>
          <li>Ranking: (Safety slider × Safety + Upside slider × Upside + 5 × Confidence) ÷ (sum of the three weights). Confidence counts like a middle slider so a stock the app is unsure about does not come first.</li>
          <li>Days are calendar days: 30 days = 21 trading days. Between two forecast horizons, every number is a straight-line mix of the nearest two.</li>
          <li>Chance of more money: the calibrated chance up, lowered by the part of the forecast range between 0 and the break-even move. The 25th/75th percentiles sit between the middle and the widened 10th/90th on a bell shape.</li>
          <li>GREEN only if the chance of more money is at least 55%, the low end of “how often right” at least 52%, the middle result beats the costs and the forecast for the period is validated. AMBER if the chance is at least 50% and the middle result beats the costs. Otherwise GREY. These thresholds were fixed in advance.</li>
        </ul>
        <p className="mt-2 text-sm">
          <Link to="/strategies" className="text-teal-700 underline dark:text-teal-400">Strategies: 5 paper-money strategies</Link> ·{' '}
          <Link to="/columns" className="text-teal-700 underline dark:text-teal-400">Columns explained</Link>
        </p>
      </Card>
    </>
  )
}
