import { lazy, Suspense, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { OppBadge } from '../components/Opportunity'
import { isOpp } from '../lib/opportunity'
import { Tip } from '../components/Tip'
import { Badge, Card, PageHeader } from '../components/ui'
import { WhenVisible } from '../components/WhenVisible'
import { formatEur, formatEurSigned, formatShares } from '../lib/costs'
import { useSiteJson } from '../lib/data'
import { formatDay, formatPct, formatPrice, signClass } from '../lib/format'
import { evaluate, evaluateSplit, mapPeriod, type Context, type PlanRow, type Verdict } from '../lib/plan'
import { useTradeSettings } from '../lib/settings'
import type { StrategiesFile, StrategyCard, StrategyEvent, StrategySuggestion } from '../types'
import { OutcomeLines, ValidTag, VerdictBox } from './Plan'
import type { ChartSeries } from '../components/StrategyChart'

const StrategyChart = lazy(() => import('../components/StrategyChart'))

// Colour follows the strategy (fixed order, never its rank).
const COLORS: Record<string, string> = {
  balanced: 'var(--viz-series-1)',
  high_risk: 'var(--viz-series-2)',
  safe_upside: 'var(--viz-series-3)',
  confidence: 'var(--viz-series-4)',
  opportunity: 'var(--viz-series-5)',
}

const day = (d: string) => formatDay(d)
// Ledger reasons are in the past tense (they also explain the fill later); before the fill they are plans.
const planned = (reason: string) => reason.replace(/^Bought /, 'Buy ').replace(/^Sold /, 'Sell ')
const pctOrDash = (v: number | null | undefined, digits = 1) => (v === null || v === undefined ? '—' : formatPct(v, digits))

function TickerLink({ t }: { t: string }) {
  return (
    <Link to={`/stock/${encodeURIComponent(t)}`} className="font-semibold text-teal-700 underline-offset-2 hover:underline dark:text-teal-400">
      {t}
    </Link>
  )
}

function Leaderboard({ f }: { f: StrategiesFile }) {
  const rows = [...f.strategies].sort((a, b) => (b.value ?? 0) - (a.value ?? 0))
  const bench = f.benchmark
  return (
    <Card title={<Tip content="Each strategy started with 200 € of paper money. Value = cash + holdings at the last close, in euros. “vs S&P 500” = its % change minus the S&P 500 yardstick's, in percentage points.">Leaderboard</Tip>}>
      <ol className="divide-y divide-slate-100 dark:divide-zinc-800" aria-label="Strategies by value">
        {rows.map((s, i) => (
          <li key={s.key} className="py-2.5">
            <div className="flex items-baseline justify-between gap-2">
              <a href={`#/strategies#s-${s.id}`} onClick={(e) => { e.preventDefault(); document.getElementById(`s-${s.id}`)?.scrollIntoView() }} className="min-w-0 font-semibold">
                <span className="mr-1 text-xs text-slate-500 tabular-nums dark:text-zinc-400">{i + 1}.</span>
                <span className="mr-1.5 inline-block size-2.5 rounded-full align-middle" style={{ background: COLORS[s.id] }} aria-hidden="true" />
                {s.name}
              </a>
              <span className="shrink-0 text-right tabular-nums">
                <span className="font-semibold">{s.value === null ? '—' : formatEur(s.value)}</span>{' '}
                <span className={`text-sm ${signClass(s.pct)}`}>{pctOrDash(s.pct)}</span>
              </span>
            </div>
            <p className="mt-0.5 text-xs text-slate-600 dark:text-zinc-400">
              vs S&P 500 <span className={signClass(s.vs_benchmark)}>{s.vs_benchmark === null ? '—' : `${s.vs_benchmark >= 0 ? '+' : '−'}${Math.abs(s.vs_benchmark * 100).toFixed(1)} pts`}</span> · fees {formatEur(s.fees ?? 0)} · {s.trades} trade{s.trades === 1 ? '' : 's'} · win rate {s.win_rate === null ? '—' : `${Math.round(s.win_rate * 100)}% (${s.wins} of ${s.closed})`} · worst drop {pctOrDash(s.max_drawdown)} · cash {formatEur(s.cash ?? 0)}
            </p>
            {s.locked && <p className="mt-1 text-xs text-red-700 dark:text-red-400">{s.locked}</p>}
          </li>
        ))}
        {bench && (
          <li className="py-2.5">
            <div className="flex items-baseline justify-between gap-2">
              <span className="min-w-0 font-semibold">
                <span className="mr-1.5 inline-block h-0.5 w-3 align-middle" style={{ background: 'var(--viz-ref)' }} aria-hidden="true" />
                {bench.name} <span className="text-xs font-normal text-slate-500 dark:text-zinc-400">(yardstick)</span>
              </span>
              <span className="shrink-0 text-right tabular-nums">
                <span className="font-semibold">{bench.value === null ? '—' : formatEur(bench.value)}</span> <span className={`text-sm ${signClass(bench.pct)}`}>{pctOrDash(bench.pct)}</span>
              </span>
            </div>
            <p className="mt-0.5 text-xs text-slate-600 dark:text-zinc-400">One buy fee, then held · fees {formatEur(bench.fees ?? 0)} · worst drop {pctOrDash(bench.max_drawdown)}</p>
          </li>
        )}
      </ol>
    </Card>
  )
}

function Holdings({ s }: { s: StrategyCard }) {
  if (s.holdings.length === 0) return <p className="text-sm text-slate-600 dark:text-zinc-400">Nothing: all {formatEur(s.cash ?? 0)} in cash.</p>
  return (
    <ul className="space-y-2">
      {s.holdings.map((h) => (
        <li key={h.ticker} className="rounded-lg border border-slate-200 p-2.5 text-sm dark:border-zinc-700">
          <div className="flex items-baseline justify-between gap-2">
            <span className="min-w-0 truncate">
              <TickerLink t={h.ticker} /> <span className="text-slate-600 dark:text-zinc-400">{h.name ?? ''}</span>
            </span>
            <span className={`shrink-0 tabular-nums font-semibold ${signClass(h.stock_move)}`}>{pctOrDash(h.stock_move)}</span>
          </div>
          <p className="text-xs text-slate-600 dark:text-zinc-400">
            {formatShares(h.shares)} share{h.shares === 1 ? '' : 's'} bought {day(h.entry_date)} at {formatPrice(h.entry_usd)} ({formatEur(h.cost_eur)} paid with the fee) · now {h.close_usd === null ? '—' : formatPrice(h.close_usd)}, worth {h.value_eur === null ? '—' : formatEur(h.value_eur)} ({h.gain_eur === null ? '—' : formatEurSigned(h.gain_eur)}) · {h.days_held} trading day{h.days_held === 1 ? '' : 's'}
          </p>
          <p className="text-xs text-slate-600 dark:text-zinc-400">
            Exit levels:{' '}
            {[
              h.levels.stop_usd !== null && `stop ${formatPrice(h.levels.stop_usd)}`,
              h.levels.trailing_usd !== null && `trailing stop ${formatPrice(h.levels.trailing_usd)}`,
              h.levels.take_profit_usd !== null && `take-profit ${formatPrice(h.levels.take_profit_usd)}`,
              h.levels.days_left !== null && `sells after ${h.levels.days_left} more trading days`,
            ]
              .filter(Boolean)
              .join(' · ') || 'none (held)'}
            . Planned levels, not guarantees: a gap at the open can be worse.
          </p>
        </li>
      ))}
    </ul>
  )
}

function eventText(e: StrategyEvent): ReactNode {
  if (e.kind === 'fill') {
    return (
      <>
        <Badge tone={e.side === 'buy' ? 'good' : 'neutral'}>{e.side === 'buy' ? 'BUY' : 'SELL'}</Badge> {e.ticker && <TickerLink t={e.ticker} />} {formatShares(e.shares ?? 0)} at {formatPrice(e.open_usd ?? 0)} open → {formatEur(e.price_eur ?? 0)} a share with half the spread
        {e.fx ? ` (${e.fx.toFixed(4)} $/€)` : ''} · fee {formatEur(e.fee ?? 0)} · {e.side === 'buy' ? `paid ${formatEur(e.amount_eur ?? 0)}` : `received ${formatEur(e.amount_eur ?? 0)}`}
        {e.side === 'sell' && e.pnl_eur !== null && e.pnl_eur !== undefined && (
          <>
            {' '}
            · <span className={signClass(e.pnl_eur)}>{formatEurSigned(e.pnl_eur)} ({pctOrDash(e.pnl_pct)})</span>
          </>
        )}
      </>
    )
  }
  return (
    <>
      <Badge tone="neutral">{e.kind === 'cancel' ? 'CANCELLED' : e.kind === 'dividend' ? 'DIVIDEND' : 'SPLIT'}</Badge> {e.ticker && <TickerLink t={e.ticker} />}
      {e.amount_eur ? ` +${formatEur(e.amount_eur)}` : ''}
    </>
  )
}

function StrategyCardView({ s, f }: { s: StrategyCard; f: StrategiesFile }) {
  const next = s.pending[0]?.fill_on
  return (
    <section id={`s-${s.id}`} className="scroll-mt-28">
      <Card
        title={
          <span className="inline-flex items-center gap-2">
            <span className="inline-block size-3 rounded-full" style={{ background: COLORS[s.id] }} aria-hidden="true" />
            {s.name}
          </span>
        }
        aside={<span className="shrink-0 text-right text-sm tabular-nums">{s.value === null ? '—' : formatEur(s.value)}</span>}
      >
        <p className="text-sm italic text-slate-700 dark:text-zinc-300">{s.mindset}</p>
        {s.locked && <p className="mt-2 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-200">{s.locked}</p>}
        <h3 className="mt-3 text-sm font-semibold">Rules (version {s.version}, fixed)</h3>
        <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-700 dark:text-zinc-300">
          {s.rules.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
        <details className="mt-1 text-sm">
          <summary className="min-h-11 cursor-pointer font-medium text-teal-700 dark:text-teal-400">Rules shared by all five</summary>
          <ul className="list-disc space-y-1 pl-5 text-slate-700 dark:text-zinc-300">
            {f.shared_rules.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </details>
        <h3 className="mt-3 mb-1 text-sm font-semibold">What it holds now</h3>
        <Holdings s={s} />
        <h3 className="mt-3 mb-1 text-sm font-semibold">What it will do at the next open{next ? ` (${day(next)})` : ''}</h3>
        {s.pending.length ? (
          <ul className="space-y-1 text-sm">
            {s.pending.map((o) => (
              <li key={`${o.side}-${o.ticker}`}>
                <Badge tone={o.side === 'buy' ? 'good' : 'neutral'}>{o.side === 'buy' ? 'BUY' : 'SELL'}</Badge> <TickerLink t={o.ticker} /> at the official opening price. <span className="text-slate-600 dark:text-zinc-400">{planned(o.reason)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-600 dark:text-zinc-400">No order: it keeps what it has.</p>
        )}
        {s.notes.length > 0 && (
          <>
            <h3 className="mt-3 mb-1 text-sm font-semibold">Reasons at the last close{s.last_day ? ` (${day(s.last_day)})` : ''}</h3>
            <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700 dark:text-zinc-300">
              {s.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </>
        )}
        <details className="mt-3 text-sm">
          <summary className="min-h-11 cursor-pointer font-medium text-teal-700 dark:text-teal-400">Trade history ({s.history.length})</summary>
          {s.history.length === 0 ? (
            <p className="text-slate-600 dark:text-zinc-400">No trades yet.</p>
          ) : (
            <ul className="divide-y divide-slate-100 dark:divide-zinc-800">
              {s.history.map((e, i) => (
                <li key={i} className="py-2">
                  <p className="text-xs text-slate-500 dark:text-zinc-400">{day(e.date)}</p>
                  <p>{eventText(e)}</p>
                  {(e.reason || e.order_reason) && <p className="text-xs text-slate-600 dark:text-zinc-400">{e.reason}{e.order_reason ? ` (${e.order_reason})` : ''}</p>}
                </li>
              ))}
            </ul>
          )}
        </details>
      </Card>
    </section>
  )
}

/** A suggestion as a Plan-builder row, so both pages compute costs and odds the same way. */
function asRow(x: StrategySuggestion): PlanRow {
  return {
    ticker: x.ticker,
    name: x.name,
    sector: x.sector,
    zero: true,
    label: '',
    price: x.price,
    spread: x.spread,
    safety: null,
    upside: null,
    confidence: null,
    balanced: null,
    days_to_earnings: null,
    next_earnings: null,
    opp: x.opp,
    opp_event: x.opp_event,
    p_up_1m: x.p_up_1m,
    med_1m: x.med_1m,
    p10_1m: x.p10_1m,
    p90_1m: x.p90_1m,
  }
}

interface Suggestion {
  s: StrategyCard
  picks: StrategySuggestion[]
  pProfit: number
  verdict: Verdict
  lines: Parameters<typeof OutcomeLines>[0]['e']
  validated: boolean
}

function GiveMeAStrategy({ f }: { f: StrategiesFile }) {
  const [settings, set] = useTradeSettings()
  const amount = settings.amount
  if (!f.fx) return <p className="text-sm text-slate-600 dark:text-zinc-400">The EUR/USD rate is not available yet, so euro amounts cannot be computed.</p>
  const ctx: Context = {
    fx: f.fx.rate,
    fees: { buy: settings.feeBuy, sell: settings.feeSell, fractional: settings.fractional },
    mix: mapPeriod(30),
    reliability: { '1m': f.reliability_1m ?? [] },
    validated: f.validated,
  }
  const out: (Suggestion | { s: StrategyCard; none: string })[] = f.strategies.map((s) => {
    const list = f.suggestions[s.id] ?? []
    const n = s.max_positions
    const each = amount / n
    // The strategy's own buying rules for your amount: one share must fit, and the Balanced
    // strategy also needs an expected 1-month gain above the round-trip cost.
    const fits = (x: StrategySuggestion) => {
      const e = evaluate(asRow(x), each, ctx)
      if (!e) return false
      if (s.id !== 'balanced') return true
      // Same formula as the pipeline: (buy fee + sell fee) / money invested + spread.
      const roundTrip = (ctx.fees.buy + ctx.fees.sell) / e.buy.invested + x.spread
      return (x.med_1m ?? -1) > roundTrip
    }
    const picks = list.filter(fits).slice(0, n)
    const [p1, p2] = picks
    if (!p1) return { s, none: list.length ? `nothing it may buy costs less than ${formatEur(each)} a share` : 'nothing passes its buying rules today' }
    const pair = p2 ? evaluateSplit(asRow(p1), asRow(p2), amount, ctx) : null
    if (pair) return { s, picks, pProfit: pair.pProfit, verdict: pair.verdict, lines: pair, validated: pair.validated }
    const e = evaluate(asRow(p1), amount, ctx)
    if (!e) return { s, none: `one share of ${p1.ticker} costs more than your amount` }
    return { s, picks, pProfit: e.pProfit, verdict: e.verdict, lines: { ...e, shares: e.buy.shares, leftover: e.buy.leftover }, validated: e.validated }
  })
  const scored = out.filter((x): x is Suggestion => 'picks' in x && x.verdict.color !== 'grey')
  const best = scored.sort((a, b) => b.pProfit - a.pProfit)[0]?.s.key
  return (
    <div className="space-y-3">
      <label className="block max-w-xs text-sm font-medium">
        Your amount in euros
        <input type="number" inputMode="decimal" min={1} step={10} value={amount} onChange={(e) => set({ amount: Number(e.target.value) || 1 })} className="mt-1 min-h-11 w-full rounded-lg border border-slate-300 bg-white px-2 text-base dark:border-zinc-600 dark:bg-zinc-800" />
      </label>
      <p className="text-xs text-slate-600 dark:text-zinc-400">
        What each strategy would buy today if it started now with your money, held for about 1 month (21 trading days). Fees {formatEur(settings.feeBuy)} / {formatEur(settings.feeSell)} (change them on the <Link to="/plan" className="underline">Plan</Link> page), {settings.fractional ? 'fractional shares (simulation only)' : 'whole shares'}. Best overall = the highest chance of ending with more money after costs among the green or amber ones.
      </p>
      {!best && <VerdictBox v={{ color: 'grey', title: 'No good opportunity now: waiting is a valid choice', why: [] }} />}
      <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {out.map((x) => (
          <li key={x.s.key} className="min-w-0">
            <Card
              title={
                <span className="inline-flex flex-wrap items-center gap-2">
                  {x.s.name}
                  {best === x.s.key && <Badge tone="good">★ Best overall today</Badge>}
                </span>
              }
            >
              {'none' in x ? (
                <p className="text-sm text-slate-600 dark:text-zinc-400">No buy: {x.none}. It would keep the money in cash.</p>
              ) : (
                <>
                  <ul className="mb-2 space-y-1 text-sm">
                    {x.picks.map((p) => (
                      <li key={p.ticker}>
                        Buy <TickerLink t={p.ticker} />
                        <span className="block truncate text-slate-600 dark:text-zinc-400" title={p.name ?? undefined}>
                          {p.name ?? ''}
                        </span>
                        <span className="block text-xs text-slate-600 dark:text-zinc-400">{p.score_text}</span>
                        {isOpp(p.opp) && (
                          <span className="mt-0.5 flex flex-wrap items-center gap-1 text-xs">
                            <OppBadge ticker={p.ticker} color={p.opp} compact /> {p.opp_event}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                  <VerdictBox v={x.verdict} />
                  <div className="mt-2">
                    <OutcomeLines e={x.lines} amount={amount} validated={x.validated} />
                  </div>
                </>
              )}
            </Card>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function Strategies() {
  const res = useSiteJson<StrategiesFile>('strategies.json')
  const [show, setShow] = useState(false)
  const header = (
    <>
      <PageHeader title="Strategies" subtitle="Five paper-money strategies with 200 € each, managed every trading day by fixed rules, against the S&P 500." />
      <div role="note" className="mb-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:border-amber-700/60 dark:bg-amber-950/60 dark:text-amber-100">
        <strong>Paper money only. Past and live results do not guarantee future results.</strong> No broker is connected and no real order is ever placed.
      </div>
    </>
  )
  if (res.state !== 'ready') {
    return (
      <>
        {header}
        <Card>
          <p className="text-sm text-slate-600 dark:text-zinc-400">
            {res.state === 'loading' ? 'Loading strategies…' : res.state === 'missing' ? 'The strategies appear after the next daily pipeline run.' : `Could not load the strategies (${res.message}).`}
          </p>
        </Card>
      </>
    )
  }
  const f = res.data
  const series: ChartSeries[] = [
    ...f.strategies.map((s) => ({ key: s.id, name: s.name, color: COLORS[s.id] ?? 'var(--viz-axis)', points: [[f.start, f.capital] as [string, number], ...s.series.filter(([d]) => d !== f.start)] })),
    ...(f.benchmark ? [{ key: 'sp500', name: 'S&P 500', color: 'var(--viz-ref)', dashed: true, points: [[f.start, f.capital] as [string, number], ...f.benchmark.series.filter(([d]) => d !== f.start)] }] : []),
  ]
  const waiting = f.status === 'waiting'
  return (
    <>
      {header}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {f.research_mode ? (
          <Tip content={`The page keeps this badge until a strategy beats the S&P 500 live over at least 6 months (${f.proven_days} trading days).`} className="no-underline">
            <Badge tone="warn">RESEARCH MODE — not yet proven live</Badge>
          </Tip>
        ) : (
          <Badge tone="good">Beat the S&P 500 live for 6+ months: {f.proven.join(', ')}</Badge>
        )}
        <span className="text-xs text-slate-500 dark:text-zinc-400">
          Live since {day(f.start)} · data as of {day(f.as_of)} ·{' '}
          <Tip content={`Every order, fill and daily value is in an append-only, hash-chained ledger (${f.ledger.entries} entries) in the private data repo, checked at every build.`}>
            ledger {f.ledger.verified ? '✓ verified' : `✗ ${f.ledger.detail}`}
          </Tip>
          {f.fx ? ` · ${f.fx.rate.toFixed(4)} $/€ (FRED, ${day(f.fx.date)})` : ''}
        </span>
      </div>
      {waiting && (
        <Card className="mb-3">
          <p className="text-sm">
            The strategies make their first decisions at the close of {day(f.start)} (after 16:15 New York time). Their first orders fill at the next official opening price.
          </p>
        </Card>
      )}
      {f.status !== 'live' && f.status !== 'waiting' && <p className="mb-3 text-sm text-red-700 dark:text-red-400">Today: {f.status}.</p>}
      <div className="mb-3">
        <button type="button" aria-expanded={show} onClick={() => setShow((v) => !v)} className="inline-flex min-h-12 items-center rounded-xl bg-teal-700 px-4 text-base font-semibold text-white hover:bg-teal-800 dark:bg-teal-600 dark:hover:bg-teal-500">
          {show ? 'Hide' : 'Give me a strategy'}
        </button>
        {show && (
          <div className="mt-3">
            <GiveMeAStrategy f={f} />
          </div>
        )}
      </div>
      <div className="grid gap-3">
        <Leaderboard f={f} />
        <Card title="Value of each strategy (€)">
          <WhenVisible height="h-72">
            <Suspense fallback={<div className="h-72" aria-busy="true" />}>
              <StrategyChart series={series} start={f.capital} />
            </Suspense>
          </WhenVisible>
        </Card>
        {f.strategies.map((s) => (
          <StrategyCardView key={s.key} s={s} f={f} />
        ))}
        <Card title="How it works">
          <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-slate-700 dark:text-zinc-300">
            {f.shared_rules.map((r) => (
              <li key={r}>{r}</li>
            ))}
            <li>Dividends are added to cash after 15% US withholding tax; German taxes are not included. Exit levels use the stock’s dollar price; the euro value also moves with EUR/USD.</li>
            <li>Rules were fixed before the first decision and are never tuned on past data. A changed rule would be a new version starting again from 200 €; past trades are never edited.</li>
          </ul>
          <p className="mt-2 text-sm">
            <ValidTag ok={false} /> Live results are short so far. <Link to="/plan" className="text-teal-700 underline dark:text-teal-400">Plan builder</Link> · <Link to="/about" className="text-teal-700 underline dark:text-teal-400">About</Link>
          </p>
        </Card>
      </div>
    </>
  )
}
