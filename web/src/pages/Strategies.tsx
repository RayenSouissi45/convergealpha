import { lazy, Suspense, useState } from 'react'
import { Link } from 'react-router'
import { OppBadge } from '../components/Opportunity'
import { Dot, LiveLine, MoneyChips, StatusBadge, TickerLink, UniverseSwitch } from '../components/StrategyParts'
import { Tip } from '../components/Tip'
import { Badge, Card, PageHeader } from '../components/ui'
import { WhenVisible } from '../components/WhenVisible'
import { formatEur, formatShares, sellFeeFor } from '../lib/costs'
import { useSiteJson } from '../lib/data'
import { formatDay, formatPct, signClass } from '../lib/format'
import { isOpp } from '../lib/opportunity'
import { evaluate, evaluateSplit, mapPeriod, type Context, type PlanRow, type Verdict } from '../lib/plan'
import { feesFrom, feeText, useTradeSettings } from '../lib/settings'
import { byValue, cardsFor, COLORS, linePoints, liveOf, suggestionsFor, twinOf, UNIVERSE_LABEL, useUniverse, withLive, type LiveCard, type Universe } from '../lib/strategies'
import type { StrategiesFile, StrategiesLiveFile, StrategyCard, StrategySuggestion } from '../types'
import { OutcomeLines, ValidTag, VerdictBox } from './Plan'
import type { ChartSeries } from '../components/StrategyChart'

const StrategyChart = lazy(() => import('../components/StrategyChart'))

const day = (d: string) => formatDay(d)
const pts = (v: number | null) => (v === null ? '—' : `${v >= 0 ? '+' : '−'}${Math.abs(v * 100).toFixed(1)} pts`)
const detailLink = (id: string, u: Universe) => `/strategies/${id}${u === 'all' ? '?stocks=all' : ''}`

/** One strategy at a glance: value, return, what the money is in. The whole tile opens its page. */
function Tile({ s, rank, f, u, live }: { s: LiveCard; rank: number; f: StrategiesFile; u: Universe; live: StrategiesLiveFile | null }) {
  const t0 = twinOf(f, s)
  const twin = t0 ? withLive(t0, live) : null
  return (
    <li className="min-w-0">
      <Link
        to={detailLink(s.id, u)}
        className="block h-full rounded-xl border border-slate-200 bg-white p-3.5 shadow-xs hover:border-teal-600 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-teal-500"
      >
        <div className="flex items-start justify-between gap-3">
          <span className="flex min-w-0 items-center gap-2 font-semibold">
            <span className="text-xs text-slate-500 tabular-nums dark:text-zinc-400">{rank}.</span>
            <Dot id={s.id} />
            <span className="min-w-0">{s.name}</span>
          </span>
          <span className="shrink-0 text-right tabular-nums">
            <span className="block text-lg leading-6 font-semibold">{s.value === null ? '—' : formatEur(s.value)}</span>
            <span className={`block text-sm ${signClass(s.pct)}`}>
              {s.live && <span className="mr-1 text-[10px] font-semibold tracking-wide text-emerald-700 dark:text-emerald-400">LIVE</span>}
              {s.pct === null ? '—' : formatPct(s.pct)}
            </span>
          </span>
        </div>
        <div className="mt-1 flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
          <StatusBadge s={s} />
          <span className="text-xs text-slate-600 tabular-nums dark:text-zinc-400">
            vs S&P 500 <span className={signClass(s.vs_benchmark)}>{pts(s.vs_benchmark)}</span>
          </span>
        </div>
        <MoneyChips s={s} />
        {s.locked && <p className="mt-2 text-xs text-red-700 dark:text-red-400">{s.locked}</p>}
        {twin && (
          <p className="mt-2 border-t border-slate-100 pt-2 text-xs text-slate-600 tabular-nums dark:border-zinc-800 dark:text-zinc-400">
            {u === 'zero' ? 'Same rules on all stocks' : 'Only finanzen.net zero'}: {twin.value === null ? '—' : formatEur(twin.value)}{' '}
            <span className={signClass(twin.pct)}>({twin.pct === null ? '—' : formatPct(twin.pct)})</span>
          </p>
        )}
      </Link>
    </li>
  )
}

function Benchmark({ b }: { b: LiveCard }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-dashed border-slate-300 px-3.5 py-2.5 text-sm dark:border-zinc-700">
      <span className="flex min-w-0 items-center gap-2">
        <span className="inline-block h-0.5 w-3 shrink-0" style={{ background: 'var(--viz-ref)' }} aria-hidden="true" />
        <span className="min-w-0">
          <Tip content="The yardstick: 200 € into the S&P 500 (SPY) at the first open, one buy fee, then held. SPY is not sold to EU investors; it is only the comparison.">
            S&P 500 yardstick
          </Tip>
          <span className="block text-xs text-slate-600 dark:text-zinc-400">
            <StatusBadge s={b} />
          </span>
        </span>
      </span>
      <span className="shrink-0 text-right tabular-nums">
        <span className="block font-semibold">{b.value === null ? '—' : formatEur(b.value)}</span>
        <span className={`block text-sm ${signClass(b.pct)}`}>{b.pct === null ? '—' : formatPct(b.pct)}</span>
      </span>
    </div>
  )
}

/** A suggestion as a Plan-builder row, so both pages compute costs and odds the same way. */
function asRow(x: StrategySuggestion, u: Universe): PlanRow {
  return {
    ticker: x.ticker,
    name: x.name,
    sector: x.sector,
    zero: u === 'zero' ? true : null,
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
  picks: { p: StrategySuggestion; shares: number }[]
  pProfit: number
  verdict: Verdict
  lines: Parameters<typeof OutcomeLines>[0]['e']
  validated: boolean
}

const VERDICT_TONE = { green: 'good', amber: 'warn', grey: 'neutral' } as const

function GiveMeAStrategy({ f, u }: { f: StrategiesFile; u: Universe }) {
  const [settings, set] = useTradeSettings()
  const amount = settings.amount
  if (!f.fx) return <p className="text-sm text-slate-600 dark:text-zinc-400">The EUR/USD rate is not available yet, so euro amounts cannot be computed.</p>
  const ctx: Context = {
    fx: f.fx.rate,
    fees: feesFrom(settings),
    mix: mapPeriod(30),
    reliability: { '1m': f.reliability_1m ?? [] },
    validated: f.validated,
  }
  const all = suggestionsFor(f, u)
  const out: (Suggestion | { s: StrategyCard; none: string })[] = cardsFor(f, u).map((s) => {
    const list = all[s.id] ?? []
    const n = s.max_positions
    const each = amount / n
    // The strategy's own buying rules for your amount: one share must fit, and the Balanced
    // strategy also needs an expected 1-month gain above the round-trip cost.
    const fits = (x: StrategySuggestion) => {
      const e = evaluate(asRow(x, u), each, ctx)
      if (!e) return false
      if (s.id !== 'balanced') return true
      // Same formula as the pipeline: (buy fee + sell fee) / money invested + spread.
      const roundTrip = (e.buy.fee + sellFeeFor(e.buy, ctx.fees)) / e.buy.invested + x.spread
      return (x.med_1m ?? -1) > roundTrip
    }
    const picks = list.filter(fits).slice(0, n)
    const [p1, p2] = picks
    if (!p1) return { s, none: list.length ? `nothing it may buy costs less than ${formatEur(each)} a share` : 'nothing passes its buying rules today' }
    const pair = p2 ? evaluateSplit(asRow(p1, u), asRow(p2, u), amount, ctx) : null
    if (pair && p2) {
      const legs = [
        { p: p1, shares: pair.legs[0].buy.shares },
        { p: p2, shares: pair.legs[1].buy.shares },
      ]
      return { s, picks: legs, pProfit: pair.pProfit, verdict: pair.verdict, lines: pair, validated: pair.validated }
    }
    const e = evaluate(asRow(p1, u), amount, ctx)
    if (!e) return { s, none: `one share of ${p1.ticker} costs more than your amount` }
    return { s, picks: [{ p: p1, shares: e.buy.shares }], pProfit: e.pProfit, verdict: e.verdict, lines: { ...e, shares: e.buy.shares, leftover: e.buy.leftover }, validated: e.validated }
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
        If each strategy started today with your money ({UNIVERSE_LABEL[u]}), held about 1 month. Costs: {feeText(settings)} (change them on <Link to="/plan" className="underline">Plan</Link>). Best overall = the highest chance of more money after costs among the green or amber ones.
      </p>
      {!best && <VerdictBox v={{ color: 'grey', title: 'No good opportunity now: waiting is a valid choice', why: [] }} />}
      <ul className="grid grid-cols-1 gap-2 lg:grid-cols-2">
        {out.map((x) => (
          <li key={x.s.key} className="min-w-0 rounded-xl border border-slate-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="flex min-w-0 items-center gap-2 font-semibold">
                <Dot id={x.s.id} />
                {x.s.name}
              </span>
              {best === x.s.key && <Badge tone="good">★ Best overall today</Badge>}
            </div>
            {'none' in x ? (
              <p className="mt-1 text-sm text-slate-600 dark:text-zinc-400">Stays in cash: {x.none}.</p>
            ) : (
              <>
                <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                  {x.picks.map(({ p, shares }) => (
                    <span key={p.ticker} className="inline-flex items-center gap-1">
                      Buy {formatShares(shares)} × <TickerLink t={p.ticker} />
                      {isOpp(p.opp) && <OppBadge ticker={p.ticker} color={p.opp} compact />}
                    </span>
                  ))}
                </p>
                <p className="mt-1 flex flex-wrap items-center gap-2 text-sm">
                  <Badge tone={VERDICT_TONE[x.verdict.color]}>{x.verdict.color.toUpperCase()}</Badge>
                  <span>
                    Chance of more money after costs: <strong className="tabular-nums">{Math.round(x.pProfit * 100)}%</strong>
                  </span>
                </p>
                <details className="mt-1 text-sm">
                  <summary className="min-h-11 cursor-pointer content-center font-medium text-teal-700 dark:text-teal-400">Details: costs, likely result, why</summary>
                  <ul className="mb-2 space-y-0.5 text-xs text-slate-600 dark:text-zinc-400">
                    {x.picks.map(({ p }) => (
                      <li key={p.ticker}>
                        {p.ticker} {p.name ?? ''}: {p.score_text}
                        {isOpp(p.opp) && p.opp_event ? ` · ${p.opp_event}` : ''}
                      </li>
                    ))}
                  </ul>
                  <VerdictBox v={x.verdict} />
                  <div className="mt-2">
                    <OutcomeLines e={x.lines} amount={amount} validated={x.validated} />
                  </div>
                </details>
              </>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function Strategies() {
  const res = useSiteJson<StrategiesFile>('strategies.json')
  const liveRes = useSiteJson<StrategiesLiveFile>('strategies_live.json')
  const [u, setU] = useUniverse()
  const [show, setShow] = useState(false)
  const header = (
    <>
      <PageHeader title="Strategies" subtitle="Five strategies, 200 € of paper money each, run every trading day by fixed rules. Tap one to see what it holds and why." />
      <p role="note" className="mb-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:border-amber-700/60 dark:bg-amber-950/60 dark:text-amber-100">
        <strong>Paper money only. Past and live results do not guarantee future results.</strong>
      </p>
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
  const live = liveOf(f, liveRes.state === 'ready' ? liveRes.data : null)
  const cards = cardsFor(f, u).map((s) => withLive(s, live))
  const bench = f.benchmark ? withLive(f.benchmark, live) : null
  const ranked = byValue(cards)
  const series: ChartSeries[] = [
    ...cards.map((s) => ({ key: s.id, name: s.name, color: COLORS[s.id] ?? 'var(--viz-axis)', points: linePoints(f, s, live) })),
    ...(bench ? [{ key: 'sp500', name: 'S&P 500', color: 'var(--viz-ref)', dashed: true, points: linePoints(f, bench, live) }] : []),
  ]
  return (
    <>
      {header}
      <div className="mb-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-600 dark:text-zinc-400">
        {f.research_mode ? (
          <Tip content={`Stays until a strategy beats the S&P 500 live over at least 6 months (${f.proven_days} trading days).`} className="no-underline">
            <Badge tone="warn">RESEARCH MODE — not yet proven live</Badge>
          </Tip>
        ) : (
          <Badge tone="good">Beat the S&P 500 live for 6+ months: {f.proven.join(', ')}</Badge>
        )}
        <span>
          Live since {day(f.start)} · prices of {day(f.as_of)} ·{' '}
          <Tip content={`No broker is connected and no real order is placed. Every order, fill and daily value is in an append-only, hash-chained ledger (${f.ledger.entries} entries), checked at every build.${f.fx ? ` Euro values use ${f.fx.rate.toFixed(4)} $/€ (FRED, ${day(f.fx.date)}).` : ''}`}>
            {f.ledger.verified ? 'ledger ✓' : `ledger ✗ ${f.ledger.detail}`}
          </Tip>
        </span>
      </div>
      {live && <LiveLine live={live} />}
      {f.status === 'waiting' && (
        <p className="mb-3 text-sm">
          First decisions at the close of {day(f.start)} (after 16:15 New York time); first orders fill at the next official opening price.
        </p>
      )}
      {f.status !== 'live' && f.status !== 'waiting' && <p className="mb-3 text-sm text-red-700 dark:text-red-400">Today: {f.status}.</p>}
      <UniverseSwitch u={u} set={setU} f={f} />
      <ol className="grid grid-cols-1 gap-2.5 md:grid-cols-2" aria-label="Strategies by value">
        {ranked.map((s, i) => (
          <Tile key={s.key} s={s} rank={i + 1} f={f} u={u} live={live} />
        ))}
      </ol>
      {bench && (
        <div className="mt-2.5">
          <Benchmark b={bench} />
        </div>
      )}
      <div className="mt-4 grid gap-3">
        <Card>
          <button type="button" aria-expanded={show} onClick={() => setShow((v) => !v)} className="inline-flex min-h-12 items-center rounded-xl bg-teal-700 px-4 text-base font-semibold text-white hover:bg-teal-800 dark:bg-teal-600 dark:hover:bg-teal-500">
            {show ? 'Hide' : 'Give me a strategy'}
          </button>
          <p className="mt-1 text-sm text-slate-600 dark:text-zinc-400">What each strategy would buy today with your own amount, and which one looks best.</p>
          {show && (
            <div className="mt-3">
              <GiveMeAStrategy f={f} u={u} />
            </div>
          )}
        </Card>
        <Card title={`Value since ${day(f.start)} (€)`}>
          <WhenVisible height="h-72">
            <Suspense fallback={<div className="h-72" aria-busy="true" />}>
              <StrategyChart series={series} start={f.capital} />
            </Suspense>
          </WhenVisible>
        </Card>
        <details className="rounded-xl border border-slate-200 bg-white px-4 dark:border-zinc-800 dark:bg-zinc-900">
          <summary className="min-h-12 cursor-pointer content-center font-semibold">How it works</summary>
          <ul className="mb-3 list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-slate-700 dark:text-zinc-300">
            <li>
              Two versions of each strategy, 200 € each, same rules and same start: <strong>only finanzen.net zero</strong> ({f.universes?.zero ?? 'stocks on the broker’s list'}) and <strong>all stocks</strong> ({f.universes?.all ?? 'every stock the app covers'}).
            </li>
            {f.shared_rules.map((r) => (
              <li key={r}>{r}</li>
            ))}
            <li>Dividends are added to cash after 15% US withholding tax; German taxes are not included. Exit levels use the stock’s dollar price; the euro value also moves with EUR/USD.</li>
            <li>Rules were fixed before the first decision and are never tuned on past data. A changed rule would be a new version starting again from 200 €; past trades are never edited.</li>
            <li>No broker is connected and no real order is ever placed.</li>
          </ul>
          <p className="mb-3 text-sm">
            <ValidTag ok={false} /> Live results are short so far. <Link to="/plan" className="text-teal-700 underline dark:text-teal-400">Plan builder</Link> · <Link to="/about" className="text-teal-700 underline dark:text-teal-400">About</Link>
          </p>
        </details>
      </div>
    </>
  )
}
