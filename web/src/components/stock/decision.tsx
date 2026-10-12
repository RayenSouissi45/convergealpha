import { lazy, Suspense, useState } from 'react'
import { Link } from 'react-router'
import { formatDay, formatMoney, formatPct, formatPctAbs, formatPrice } from '../../lib/format'
import { holdingStatus, limitChecks, throttle, usePortfolio } from '../../lib/portfolio'
import { useScreener } from '../../lib/screener'
import type { ScreenerRow } from '../../types'
import { positionShares } from '../../lib/sizing'
import { LabelBadge } from '../LabelBadge'
import { Missing } from '../Missing'
import { WhenVisible } from '../WhenVisible'
import { Tip } from '../Tip'
import { Badge, Card, Row } from '../ui'

const FanChart = lazy(() => import('./FanChart'))

// ---------------------------------------------------------------- shapes

export interface RuleRow {
  id: string
  text: string
  passed: boolean | null
  value: string
}

export interface DecisionSection {
  label: string
  why: string
  tier: number | null
  provisional: boolean
  research_mode: boolean
  rules: RuleRow[]
  blocking: string[]
  risk_reasons: string[]
  ev: number | null
  p_hat: number | null
  p_lower: number | null
  meta: number | null
  cost: number | null
}

export interface HorizonForecast {
  days: number
  p_up: number
  p_beat: number
  median: number
  p10: number
  p90: number
  p25: number
}

export interface ForecastSection {
  method: string
  validated: boolean | Record<string, { up: boolean; beat: boolean }>
  horizons: Record<'1w' | '1m' | '3m' | '6m', HorizonForecast> | null
  inputs: { beta: number; risk_free: number; composite: number | null } | null
  options_move: { '1w': number | null; '1m': number | null }
  analog: { n: number; up: number; rate: number; lo: number; hi: number; model_gap: number | null; text: string } | null
  sample_size: Record<string, number> | null
}

export interface FamiliesSection {
  families: { id: string; name: string; score: number | null }[]
  n_eff: number | null
  disagreement: number | null
  fresh: number
  inputs: Record<string, number | boolean | null>
}

export interface PlanSection {
  entry: number
  entry_limit: number
  skip_if_gap_above: number
  planned_exit: number
  gap_stress: number
  risk_per_share: number
  atr: number
  breakeven_after: number
  sell_third_at: number
  trail_atr_multiple: number
  time_stop_days: number
  tier: number | null
  tier_multiplier: number
  p_lower: number | null
  payoff_b: number | null
  adv_shares: number | null
}

// ---------------------------------------------------------------- label badge


const RESEARCH = (
  <Tip content="This has not passed the validation lab yet. Treat it as research, not a promise." label="Research mode: not yet validated" className="no-underline">
    <Badge tone="warn">RESEARCH MODE — not yet validated</Badge>
  </Tip>
)

// ---------------------------------------------------------------- decision

export function DecisionCard({ d }: { d: DecisionSection }) {
  const [open, setOpen] = useState(false)
  const failed = d.rules.filter((r) => r.passed === false).length
  return (
    <Card title="Decision" aside={<LabelBadge label={d.label} />} className="lg:col-span-3">
      <p className="text-base">{d.why}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        {RESEARCH}
        {d.provisional && (
          <Tip content="The trained models (calibrated chance, its Wilson lower bound and the meta-model) are not available for this label yet, so it rests on the transparent fallback estimate." className="no-underline">
            <Badge tone="warn">Provisional: models not applied</Badge>
          </Tip>
        )}
        {d.tier && <Badge tone="neutral">Tier {d.tier}{d.tier === 2 ? ' (half size)' : ''}</Badge>}
      </div>
      <dl className="mt-3 grid gap-x-6 sm:grid-cols-2">
        <Row label={<Tip content="Chance the 60-day trade ends ahead of the S&P 500 after costs (triple-barrier rules). Before models: an uncalibrated estimate.">Chance the trade works (p̂)</Tip>}>
          {d.p_hat !== null ? `${(d.p_hat * 100).toFixed(1)}%` : <Missing reason="Not enough data for a forecast." />}
        </Row>
        <Row label={<Tip content="Lower end of the 95% Wilson interval of p̂, from how often similar forecasts came true in the walk-forward history.">Lower bound (95%)</Tip>}>
          {d.p_lower !== null && !d.provisional ? `${(d.p_lower * 100).toFixed(1)}%` : <Missing reason="Needs calibrated models (phase 4)." />}
        </Row>
        <Row label={<Tip content="Expected value of the 60-day trade after costs: p̂ × average win − (1 − p̂) × average loss − costs.">Expected value after costs</Tip>}>
          {d.ev !== null ? formatPct(d.ev, 2) : <Missing reason="Not enough data." />}
        </Row>
        <Row label={<Tip content="Estimated round trip: spread + 2 × commission + 2 × market impact for a $10,000 order.">Trading costs</Tip>}>{d.cost !== null ? formatPctAbs(d.cost, 2) : '—'}</Row>
      </dl>
      {d.blocking.length > 0 && (
        <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-2 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
          <strong>Blocking events:</strong> {d.blocking.join('; ')}
        </div>
      )}
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="mt-3 inline-flex min-h-11 items-center text-sm font-medium text-teal-700 underline dark:text-teal-400">
        {open ? 'Hide' : 'Show'} all {d.rules.length} rules ({failed} not met)
      </button>
      {open && (
        <ul className="mt-1 divide-y divide-slate-100 text-sm dark:divide-zinc-800">
          {d.rules.map((r) => (
            <li key={r.id} className="flex items-start justify-between gap-3 py-2">
              <div>
                <span className="font-mono text-xs text-slate-500">{r.id}</span> {r.text}
                <div className="text-xs text-slate-500 dark:text-zinc-400">{r.value}</div>
              </div>
              <Badge tone={r.passed === true ? 'good' : r.passed === false ? 'bad' : 'neutral'}>{r.passed === true ? 'Met' : r.passed === false ? 'Not met' : 'Not evaluated'}</Badge>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

// ---------------------------------------------------------------- forecast

const H_LABEL = { '1w': '1 week', '1m': '1 month', '3m': '3 months', '6m': '6 months' } as const

export function ForecastCard({ f }: { f: ForecastSection }) {
  if (!f.horizons) {
    return (
      <Card title="Forecast">
        <p className="text-sm text-slate-500">Not enough price history for a forecast.</p>
      </Card>
    )
  }
  const keys = ['1w', '1m', '3m', '6m'] as const
  const n = (k: string) => f.sample_size?.[k]
  const isValid = (k: string, kind: 'up' | 'beat') => (typeof f.validated === 'object' ? !!f.validated[k]?.[kind] : !!f.validated)
  const promise = (k: (typeof keys)[number], what: string, kind: 'up' | 'beat') =>
    `${what} after ${H_LABEL[k]} (${f.horizons?.[k].days} trading days). ${isValid(k, kind) ? 'Validated on the holdout.' : 'RESEARCH MODE: not yet validated.'} Method: ${f.method}.${n(k) ? ` Calibrated on ${n(k)!.toLocaleString('en-US')} held-out past cases.` : ' No sample size: this is a model-free estimate.'}`
  const nValid = keys.reduce((a, k) => a + (isValid(k, 'up') ? 1 : 0) + (isValid(k, 'beat') ? 1 : 0), 0)
  const aside =
    nValid === 0 ? (
      RESEARCH
    ) : (
      <Tip content="Probabilities without a * passed the validation lab on the holdout (better than the base rate and well calibrated). Those with a * are still research." label="Partly validated" className="no-underline">
        <Badge tone={nValid === 2 * keys.length ? 'good' : 'warn'}>{nValid === 2 * keys.length ? 'Validated' : `Partly validated (${nValid} of ${2 * keys.length})`}</Badge>
      </Tip>
    )
  return (
    <Card title="Forecast" aside={aside} className="lg:col-span-2">
      <p className="mb-2 text-xs text-slate-500 dark:text-zinc-400">Method: {f.method}</p>
      <WhenVisible height="h-52">
        <Suspense fallback={<div className="h-52" />}>
          <FanChart points={keys.map((k) => ({ label: H_LABEL[k], days: f.horizons![k].days, median: f.horizons![k].median, band: [f.horizons![k].p10, f.horizons![k].p90] }))} />
        </Suspense>
      </WhenVisible>
      <div className="-mx-4 overflow-x-auto px-4">
        <table className="mt-2 w-full min-w-max text-sm">
          <caption className="sr-only">Forecast by horizon</caption>
          <thead>
            <tr className="border-b border-slate-200 text-xs text-slate-600 dark:border-zinc-700 dark:text-zinc-300">
              <th scope="col" className="px-2 py-1.5 text-left">Horizon</th>
              <th scope="col" className="px-2 py-1.5 text-left">Chance higher</th>
              <th scope="col" className="px-2 py-1.5 text-left">Chance to beat S&P 500</th>
              <th scope="col" className="px-2 py-1.5 text-left">Median</th>
              <th scope="col" className="px-2 py-1.5 text-left">80% range</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-zinc-800">
            {keys.map((k) => {
              const h = f.horizons![k]
              return (
                <tr key={k}>
                  <th scope="row" className="px-2 py-1.5 text-left font-normal">{H_LABEL[k]}</th>
                  <td className="px-2 py-1.5 tabular-nums"><Tip content={promise(k, 'Chance the price (with dividends) is higher', 'up')}>{`${Math.round(h.p_up * 100)}%${isValid(k, 'up') ? '' : '*'}`}</Tip></td>
                  <td className="px-2 py-1.5 tabular-nums"><Tip content={promise(k, 'Chance the stock does better than the S&P 500 (total return)', 'beat')}>{`${Math.round(h.p_beat * 100)}%${isValid(k, 'beat') ? '' : '*'}`}</Tip></td>
                  <td className="px-2 py-1.5 tabular-nums">{formatPct(h.median)}</td>
                  <td className="px-2 py-1.5 tabular-nums"><Tip content={`Between the 10th and 90th percentile: 8 out of 10 outcomes are expected inside this range after ${H_LABEL[k]}.`}>{`${formatPct(h.p10, 0)} to ${formatPct(h.p90, 0)}`}</Tip></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-xs text-slate-500 dark:text-zinc-400">* research mode: this horizon has not passed the validation lab yet.</p>
      {(f.options_move['1w'] !== null || f.options_move['1m'] !== null) && (
        <p className="mt-2 text-xs text-slate-500 dark:text-zinc-400">
          Options-implied move: {f.options_move['1w'] !== null ? `±${formatPctAbs(f.options_move['1w']!)} in 1 week` : ''}
          {f.options_move['1w'] !== null && f.options_move['1m'] !== null ? ' · ' : ''}
          {f.options_move['1m'] !== null ? `±${formatPctAbs(f.options_move['1m']!)} in 1 month` : ''} (about two times in three).
        </p>
      )}
      <div className="mt-2 text-sm">
        <span className="font-medium">Analog check: </span>
        {f.analog ? (
          <>
            {f.analog.text}
            {f.analog.model_gap !== null && Math.abs(f.analog.model_gap) > 0.08 && (
              <Badge tone="warn">Model and history differ by {Math.round(Math.abs(f.analog.model_gap) * 100)} points</Badge>
            )}
          </>
        ) : (
          <Missing reason="The 200 most similar past setups are computed with the trained models (phase 4)." />
        )}
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------- families

export function FamiliesCard({ f }: { f: FamiliesSection }) {
  return (
    <Card title="Evidence families">
      <ul className="space-y-2">
        {f.families.map((fam) => (
          <li key={fam.id}>
            <div className="flex justify-between text-sm">
              <Tip content={FAMILY_HELP[fam.id] ?? ''}>{`${fam.id.toUpperCase()} ${fam.name}`}</Tip>
              <span className="tabular-nums">{fam.score !== null ? Math.round(fam.score) : <Missing reason="No fresh data for this family." />}</span>
            </div>
            <div className="relative mt-1 h-2 rounded-full bg-slate-100 dark:bg-zinc-800" aria-hidden="true">
              {fam.score !== null && <div className="h-2 rounded-full" style={{ width: `${Math.max(2, fam.score)}%`, background: 'var(--viz-series-1)' }} />}
              <div className="absolute top-[-2px] h-3 w-px bg-slate-400" style={{ left: '50%' }} />
              <div className="absolute top-[-2px] h-3 w-px bg-slate-400" style={{ left: '60%' }} />
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-slate-500 dark:text-zinc-400">0–100 within the stock’s sector; 50 = sector median. Ticks at 50 and 60 (the BUY rule needs four families at 60 or more).</p>
      <dl className="mt-2">
        <Row label={<Tip content="Effective number of independent bullish families: correlated families count less. BUY needs at least 2.5.">Independent evidence (N_eff)</Tip>}>{f.n_eff ?? '—'}</Row>
        <Row label={<Tip content="Standard deviation of the six family scores. BUY needs 22 or less; Top Conviction 15 or less.">Disagreement (D)</Tip>}>{f.disagreement ?? '—'}</Row>
        <Row label="Families with fresh data">{f.fresh} of 6</Row>
      </dl>
    </Card>
  )
}

const FAMILY_HELP: Record<string, string> = {
  f1: 'Analyst consensus, targets, recommendation trends and rating changes — counted only for what they add beyond revisions and momentum.',
  f2: 'Changes in this year’s EPS estimate over 60 days and how many analysts raised vs cut.',
  f3: 'Size of the last earnings surprise (SUE) and news tone, within 60 trading days after the report.',
  f4: 'Opportunistic insider buying (routine and planned trades excluded) and institutional accumulation.',
  f5: 'Stock-specific momentum after removing market and sector moves, industry momentum and trend.',
  f6: 'Return on capital, gross profitability, accruals, free-cash-flow yield and leverage from SEC filings.',
}

// ---------------------------------------------------------------- position plan

export function PlanCard({ p, ticker, label, sector }: { p: PlanSection; ticker: string; label: string; sector: string | null }) {
  const [portfolio, setPortfolio] = usePortfolio()
  // The full stock list is only needed for limit checks against existing holdings.
  const screener = useScreener(portfolio.holdings.length > 0)
  const [equityInput, setEquityInput] = useState(portfolio.equity !== null ? String(portfolio.equity) : '')
  const equity = Number(equityInput) > 0 ? Number(equityInput) : null
  const t = throttle({ ...portfolio, equity: equity ?? portfolio.equity })
  const sizing =
    equity && p.p_lower !== null && p.payoff_b !== null
      ? positionShares({ equity, entry: p.entry, exit: p.planned_exit, gap: p.gap_stress, pLower: p.p_lower, payoffB: p.payoff_b, tierMultiplier: p.tier_multiplier, advShares: p.adv_shares, throttle: t.factor })
      : null
  const isBuy = label === 'BUY' || label === 'STRONG BUY — TOP CONVICTION'
  const rows = screener.state === 'ready' ? screener.data.byTicker : new Map()
  const row = rows.get(ticker) ?? ({ ticker, sector } as ScreenerRow)
  const checks = equity && sizing ? limitChecks({ ...portfolio, equity }, rows, row, sizing.shares * p.entry, sizing.shares * sizing.riskPerShare) : []
  const held = portfolio.holdings.some((h) => h.ticker === ticker)
  const add = () => {
    if (!sizing) return
    setPortfolio({
      ...portfolio,
      equity,
      holdings: [
        ...portfolio.holdings,
        { ticker, shares: sizing.shares, entryPrice: p.entry, entryDate: today, exitLevel: p.planned_exit, atrAtEntry: p.atr, p25MonthAtEntry: null },
      ],
    })
  }
  const [timeStop] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() + Math.round((p.time_stop_days * 7) / 5))
    return d
  })
  const [today] = useState(() => new Date().toISOString().slice(0, 10))
  return (
    <Card title="Position plan" aside={isBuy ? <LabelBadge label={label} /> : <Badge tone="neutral">For reference only</Badge>}>
      {!isBuy && <p className="mb-2 text-sm text-slate-600 dark:text-zinc-400">This stock is not a BUY today. The plan shows what the rules would do if it became one.</p>}
      <label className="block text-sm font-medium">
        Your account value (stored only in this browser)
        <input
          type="number"
          inputMode="decimal"
          min="0"
          value={equityInput}
          onChange={(e) => setEquityInput(e.target.value)}
          onBlur={() => equity && setPortfolio({ ...portfolio, equity })}
          placeholder="e.g. 10000"
          className="mt-1 min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-zinc-600 dark:bg-zinc-800"
        />
      </label>
      <dl className="mt-3">
        <Row label={<Tip content="Buy in the next session after the first 15 minutes, with a limit at most 1% above the signal close. Skip it if the stock opens more than 3% higher.">Entry</Tip>}>
          {formatPrice(p.entry)} <span className="text-xs text-slate-500">limit ≤ {formatPrice(p.entry_limit)}</span>
        </Row>
        <Row label={<Tip content="max(entry − 2 × ATR, 92% of entry). A planned exit, not a maximum loss: prices can gap past it.">Planned exit level</Tip>}>{formatPrice(p.planned_exit)}</Row>
        <Row label={<Tip content="Entry × the average of the worst 2% overnight gaps of the last 500 days. Risk per share uses the larger of this and the distance to the exit.">Gap stress</Tip>}>{formatPrice(p.gap_stress)}</Row>
        <Row label="Risk per share">{formatPrice(p.risk_per_share)}</Row>
        {sizing ? (
          <>
            <Row label={<Tip content={`0.75% of your account × tier ÷ risk per share, capped by ¼-Kelly on the lower-bound chance, 10% of your account and 1% of daily volume. Binding limit: ${sizing.binding}.`}>Shares</Tip>}>
              <span className="text-lg font-semibold">{sizing.shares.toLocaleString('en-US')}</span>
            </Row>
            <Row label="Position value">{formatMoney(sizing.shares * p.entry)}</Row>
            <Row label="Money at risk to the planned exit">{formatMoney(sizing.shares * sizing.riskPerShare)}</Row>
          </>
        ) : (
          <Row label="Shares">{equity ? <Missing reason="Needs a chance and payoff estimate for this stock." /> : 'Enter your account value'}</Row>
        )}
        <Row label="Move stop to break-even after">{formatPrice(p.breakeven_after)}</Row>
        <Row label="Sell a third at">{`${formatPrice(p.sell_third_at)}, then trail at highest close − ${p.trail_atr_multiple} ATR`}</Row>
        <Row label="Time stop">{`${formatDay(timeStop.toISOString().slice(0, 10))} (60 trading days), unless still a candidate`}</Row>
      </dl>
      {checks.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm">
          {checks.map((c) => (
            <li key={c.text}>
              <Badge tone={c.ok ? 'good' : 'bad'}>{c.ok ? 'OK' : 'Limit'}</Badge> {c.text}
            </li>
          ))}
        </ul>
      )}
      {sizing && sizing.shares > 0 && !held && (
        <button type="button" onClick={add} className="mt-3 min-h-11 rounded-lg bg-slate-900 px-4 text-sm font-medium text-white dark:bg-zinc-100 dark:text-zinc-900">
          Add {sizing.shares} shares to My portfolio
        </button>
      )}
      {held && (
        <p className="mt-3 text-sm">
          In <Link to="/portfolio" className="underline">your portfolio</Link>
          {rows.get(ticker) ? ` · ${holdingStatus(portfolio.holdings.find((h) => h.ticker === ticker)!, rows.get(ticker), []).label}` : ''}
        </p>
      )}
      <p className="mt-2 text-xs text-slate-500 dark:text-zinc-400">{sector ? `Sector: ${sector}. ` : ''}Always a “planned exit level”, never a “maximum loss”: gaps can be worse.</p>
    </Card>
  )
}
