import { lazy, Suspense, type ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import { Dot, LiveLine, MoneyChips, StatusBadge, TickerLink, UniverseSwitch, VersionSwitch } from '../components/StrategyParts'
import { Tip } from '../components/Tip'
import { Badge, Card, PageHeader } from '../components/ui'
import { WhenVisible } from '../components/WhenVisible'
import { formatEur, formatEurSigned, formatShares } from '../lib/costs'
import { useSiteJson } from '../lib/data'
import { formatDay, formatPct, formatPrice, signClass } from '../lib/format'
import { cardsFor, COLORS, investedEur, linePoints, liveFor, liveOf, planned, statusOf, strategyQuery, twinOf, UNIVERSE_LABEL, useUniverse, useVersion, viewOf, withLive, type Universe } from '../lib/strategies'
import type { StrategiesFile, StrategiesLiveFile, StrategyCard, StrategyEvent } from '../types'
import type { ChartSeries } from '../components/StrategyChart'

const StrategyChart = lazy(() => import('../components/StrategyChart'))

const day = (d: string) => formatDay(d)
const pctOrDash = (v: number | null | undefined) => (v === null || v === undefined ? '—' : formatPct(v))
const eurOrDash = (v: number | null | undefined) => (v === null || v === undefined ? '—' : formatEur(v))
const plural = (n: number, w: string) => `${formatShares(n)} ${w}${n === 1 ? '' : 's'}`

function Stat({ label, help, children }: { label: string; help: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-slate-600 dark:text-zinc-400">
        <Tip content={help} className="text-left">
          {label}
        </Tip>
      </dt>
      <dd className="font-semibold tabular-nums">{children}</dd>
    </div>
  )
}

function Summary({ s }: { s: StrategyCard }) {
  const st = statusOf(s)
  return (
    <Card>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-3xl font-semibold tabular-nums">{eurOrDash(s.value)}</p>
          <p className={`text-base tabular-nums ${signClass(s.pct)}`}>
            {pctOrDash(s.pct)} <span className="text-sm text-slate-600 dark:text-zinc-400">since {formatEur(s.capital ?? 200, 0)}</span>
          </p>
        </div>
        <div className="text-right text-sm tabular-nums">
          <span className="text-slate-600 dark:text-zinc-400">vs S&P 500 </span>
          <span className={`font-semibold ${signClass(s.vs_benchmark)}`}>{s.vs_benchmark === null ? '—' : `${s.vs_benchmark >= 0 ? '+' : '−'}${Math.abs(s.vs_benchmark * 100).toFixed(1)} pts`}</span>
        </div>
      </div>
      <p className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        <StatusBadge s={s} /> <span>{st.text}</span>
      </p>
      {s.locked && <p className="mt-2 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-200">{s.locked}</p>}
      <dl className="mt-3 grid grid-cols-3 gap-x-3 gap-y-2 border-t border-slate-100 pt-3 sm:grid-cols-6 dark:border-zinc-800">
        <Stat label="Cash" help="Money not in stocks, in euros.">{eurOrDash(s.cash)}</Stat>
        <Stat label="In stocks" help="Value of the stocks it holds at the last close, in euros.">{formatEur(investedEur(s))}</Stat>
        <Stat label="Fees paid" help={`All buy and sell fees so far (${s.fee_rule === 'zero' ? 'finanzen.net zero: 0 € for orders of 500 € or more, 1 € below' : '1 € each way'}). The spread is inside the prices.`}>{eurOrDash(s.fees)}</Stat>
        <Stat label="Trades" help="Buys and sells that filled.">{s.trades}</Stat>
        <Stat label="Win rate" help="Share of sold positions that made money after fees and spread.">{s.win_rate === null ? '—' : `${Math.round(s.win_rate * 100)}%`}</Stat>
        <Stat label="Worst drop" help="The largest fall from a previous high of the total value, in %.">{pctOrDash(s.max_drawdown)}</Stat>
      </dl>
    </Card>
  )
}

function levelsText(h: StrategyCard['holdings'][number]): string {
  const l = h.levels
  return (
    [
      l.stop_usd !== null && `stop ${formatPrice(l.stop_usd)}`,
      l.trailing_usd !== null && `trailing stop ${formatPrice(l.trailing_usd)}`,
      l.take_profit_usd !== null && `take-profit ${formatPrice(l.take_profit_usd)}`,
      l.days_left !== null && `latest in ${plural(l.days_left, 'trading day')}`,
    ]
      .filter(Boolean)
      .join(' · ') || 'none: held'
  )
}

function RightNow({ s }: { s: StrategyCard }) {
  const next = s.pending[0]?.fill_on
  return (
    <Card title="What it holds and does next">
      {s.holdings.length > 0 ? (
        <ul className="divide-y divide-slate-100 dark:divide-zinc-800" aria-label="Holdings">
          {s.holdings.map((h) => (
            <li key={h.ticker} className="py-2.5 first:pt-0">
              <div className="flex items-baseline justify-between gap-3">
                <span className="min-w-0 truncate">
                  <TickerLink t={h.ticker} /> <span className="text-sm text-slate-600 dark:text-zinc-400">{h.name ?? ''}</span>
                </span>
                <span className={`shrink-0 font-semibold tabular-nums ${signClass(h.stock_move)}`}>{pctOrDash(h.stock_move)}</span>
              </div>
              <p className="text-sm tabular-nums">
                {plural(h.shares, 'share')} · worth {eurOrDash(h.value_eur)} <span className={signClass(h.gain_eur)}>({h.gain_eur === null ? '—' : formatEurSigned(h.gain_eur)})</span>
              </p>
              <p className="text-xs text-slate-600 dark:text-zinc-400">
                Bought {day(h.entry_date)} at {formatPrice(h.entry_usd)} · now {h.close_usd === null ? '—' : formatPrice(h.close_usd)} · sells at: {levelsText(h)}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm">
          No stocks yet: <strong className="tabular-nums">{eurOrDash(s.cash)}</strong> in cash.
        </p>
      )}
      {s.pending.length > 0 && next && (
        <>
          <h3 className="mt-3 mb-1 text-sm font-semibold">At the next open ({day(next)})</h3>
          <ul className="space-y-1.5" aria-label="Orders for the next open">
            {s.pending.map((o) => (
              <li key={`${o.side}-${o.ticker}`} className="rounded-lg bg-slate-50 px-3 py-2 dark:bg-zinc-800/60">
                <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                  <span className="inline-flex items-center gap-2">
                    <Badge tone={o.side === 'buy' ? 'good' : 'neutral'}>{o.side === 'buy' ? 'BUY' : 'SELL'}</Badge>
                    <TickerLink t={o.ticker} />
                  </span>
                  {o.est_shares !== null && o.est_shares !== undefined && o.est_eur !== null && o.est_eur !== undefined && (
                    <span className="text-sm tabular-nums">
                      <Tip content="Estimated from the last close; the real fill uses the official opening price, so the numbers will differ a little.">
                        about {plural(o.est_shares, 'share')} ≈ {formatEur(o.est_eur)}
                      </Tip>
                    </span>
                  )}
                </div>
                {o.name && <p className="truncate text-xs text-slate-600 dark:text-zinc-400">{o.name}</p>}
                <details className="text-xs text-slate-600 dark:text-zinc-400">
                  <summary className="min-h-9 cursor-pointer content-center font-medium text-teal-700 dark:text-teal-400">Why</summary>
                  <p className="pb-1">{planned(o.reason)}</p>
                </details>
              </li>
            ))}
          </ul>
        </>
      )}
      {s.notes.length > 0 && (
        <details className="mt-2 text-sm">
          <summary className="min-h-11 cursor-pointer content-center font-medium text-teal-700 dark:text-teal-400">What it checked at the close{s.last_day ? ` (${day(s.last_day)})` : ''}</summary>
          <ul className="list-disc space-y-1 pl-5 text-slate-700 dark:text-zinc-300">
            {s.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  )
}

function Side({ s, label, current, to, query }: { s: StrategyCard | null; label: string; current: boolean; to: Universe; query: (u: Universe) => string }) {
  const body = s ? (
    <>
      <p className="text-xs font-medium text-slate-600 dark:text-zinc-400">{label}</p>
      <p className="text-lg font-semibold tabular-nums">{eurOrDash(s.value)}</p>
      <p className={`text-sm tabular-nums ${signClass(s.pct)}`}>{pctOrDash(s.pct)}</p>
      <MoneyChips s={s} max={3} />
    </>
  ) : (
    <>
      <p className="text-xs font-medium text-slate-600 dark:text-zinc-400">{label}</p>
      <p className="mt-1 text-sm text-slate-600 dark:text-zinc-400">Starts with the next daily update.</p>
    </>
  )
  const cls = `block h-full min-w-0 rounded-lg border p-2.5 ${current ? 'border-teal-600 ring-1 ring-teal-600 dark:border-teal-500 dark:ring-teal-500' : 'border-slate-200 hover:border-teal-600 dark:border-zinc-700'}`
  if (current || !s) return <div className={cls} aria-current={current ? 'true' : undefined}>{body}</div>
  return (
    <Link to={query(to) || '?'} replace className={cls} aria-label={`Show the ${label} version`}>
      {body}
    </Link>
  )
}

function Compare({ s, twin, u, query }: { s: StrategyCard; twin: StrategyCard | null; u: Universe; query: (u: Universe) => string }) {
  const zero = u === 'zero' ? s : twin
  const all = u === 'all' ? s : twin
  return (
    <Card title="finanzen.net zero vs all stocks">
      <div className="grid grid-cols-2 gap-2">
        <Side s={zero} label="Only finanzen.net zero" current={u === 'zero'} to="zero" query={query} />
        <Side s={all} label="All stocks" current={u === 'all'} to="all" query={query} />
      </div>
      <p className="mt-2 text-xs text-slate-600 dark:text-zinc-400">Same rules, same start, {formatEur(s.capital ?? 200, 0)} each. The only difference: which stocks it may buy. Tap one to see it.</p>
    </Card>
  )
}

function eventLine(e: StrategyEvent): ReactNode {
  if (e.kind === 'fill') {
    const buy = e.side === 'buy'
    return (
      <>
        <span className="inline-flex flex-wrap items-center gap-2">
          <Badge tone={buy ? 'good' : 'neutral'}>{buy ? 'BUY' : 'SELL'}</Badge>
          {e.ticker && <TickerLink t={e.ticker} />}
          <span className="text-sm tabular-nums">
            {plural(e.shares ?? 0, 'share')} × {formatEur(e.price_eur ?? 0)}
          </span>
        </span>
        <span className="shrink-0 text-right text-sm tabular-nums">
          {buy ? `−${formatEur(e.amount_eur ?? 0)}` : `+${formatEur(e.amount_eur ?? 0)}`}
          {!buy && e.pnl_eur !== null && e.pnl_eur !== undefined && (
            <span className={`block text-xs ${signClass(e.pnl_eur)}`}>
              {formatEurSigned(e.pnl_eur)} ({pctOrDash(e.pnl_pct)})
            </span>
          )}
        </span>
      </>
    )
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <Badge tone="neutral">{e.kind === 'cancel' ? 'CANCELLED' : e.kind === 'dividend' ? 'DIVIDEND' : 'SPLIT'}</Badge> {e.ticker && <TickerLink t={e.ticker} />}
      {e.amount_eur ? <span className="text-sm tabular-nums">+{formatEur(e.amount_eur)}</span> : null}
    </span>
  )
}

function History({ s }: { s: StrategyCard }) {
  return (
    <Card title={`Trade history (${s.history.length})`}>
      {s.history.length === 0 ? (
        <p className="text-sm text-slate-600 dark:text-zinc-400">No trades yet.</p>
      ) : (
        <ul className="divide-y divide-slate-100 dark:divide-zinc-800">
          {s.history.map((e, i) => (
            <li key={i} className="py-2">
              <p className="text-xs text-slate-500 dark:text-zinc-400">{day(e.date)}</p>
              <div className="flex items-start justify-between gap-3">{eventLine(e)}</div>
              {(e.reason || e.order_reason) && (
                <details className="text-xs text-slate-600 dark:text-zinc-400">
                  <summary className="min-h-9 cursor-pointer content-center font-medium text-teal-700 dark:text-teal-400">Why</summary>
                  <p className="pb-1">
                    {e.reason}
                    {e.order_reason ? ` (${e.order_reason})` : ''}
                    {e.kind === 'fill' && e.open_usd ? ` Opening price ${formatPrice(e.open_usd)}${e.fx ? ` at ${e.fx.toFixed(4)} $/€` : ''}, half the spread included, fee ${formatEur(e.fee ?? 0)}.` : ''}
                  </p>
                </details>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function Rules({ s, f }: { s: StrategyCard; f: StrategiesFile }) {
  const u: Universe = s.universe === 'all' ? 'all' : 'zero'
  return (
    <Card title={`Rules (version ${s.version}, fixed)`}>
      <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700 dark:text-zinc-300">
        {s.rules.map((r) => (
          <li key={r}>{r}</li>
        ))}
        <li>Stocks: {f.universes?.[u] ?? UNIVERSE_LABEL[u]}</li>
      </ul>
      <details className="mt-1 text-sm">
        <summary className="min-h-11 cursor-pointer content-center font-medium text-teal-700 dark:text-teal-400">Rules shared by all strategies</summary>
        <ul className="list-disc space-y-1 pl-5 text-slate-700 dark:text-zinc-300">
          {f.shared_rules.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      </details>
    </Card>
  )
}

export default function StrategyDetail() {
  const { id = '' } = useParams()
  const res = useSiteJson<StrategiesFile>('strategies.json')
  const liveRes = useSiteJson<StrategiesLiveFile>('strategies_live.json')
  const [u, setU] = useUniverse()
  const [v, setV] = useVersion(res.state === 'ready' ? res.data : null)
  const back = (
    <Link to={`/strategies${res.state === 'ready' ? strategyQuery(res.data, u, v) : u === 'all' ? '?stocks=all' : ''}`} className="mb-2 inline-flex min-h-11 items-center text-sm font-medium text-teal-700 dark:text-teal-400">
      ← All strategies
    </Link>
  )
  if (res.state !== 'ready') {
    return (
      <>
        {back}
        <p className="text-sm text-slate-600 dark:text-zinc-400">{res.state === 'loading' ? 'Loading…' : res.state === 'missing' ? 'The strategies appear after the next daily pipeline run.' : `Could not load the strategies (${res.message}).`}</p>
      </>
    )
  }
  const file = res.data
  const f = viewOf(file, v)
  const live = liveFor(liveOf(file, liveRes.state === 'ready' ? liveRes.data : null), v)
  const query = (to: Universe) => strategyQuery(file, to, v)
  const official = cardsFor(f, u).find((x) => x.id === id)
  const s = official ? withLive(official, live) : undefined
  if (!s) {
    return (
      <>
        {back}
        <Card>
          <p className="text-sm">{f.strategies.some((x) => x.id === id) ? 'The all-stocks version of this strategy starts with the next daily update.' : 'No strategy with this name.'}</p>
        </Card>
      </>
    )
  }
  const t0 = twinOf(f, s)
  const twin = t0 ? withLive(t0, live) : null
  const bench = f.benchmark ? withLive(f.benchmark, live) : null
  const line = (c: StrategyCard, dotted = false) => ({
    key: `${c.id}-${c.universe ?? 'zero'}`,
    name: c.universe === 'all' ? 'All stocks' : 'Only finanzen.net zero',
    color: COLORS[c.id] ?? 'var(--viz-axis)',
    dotted,
    points: linePoints(f, c, live),
  })
  const series: ChartSeries[] = [
    line(s),
    ...(twin ? [line(twin, true)] : []),
    ...(bench ? [{ key: 'sp500', name: 'S&P 500', color: 'var(--viz-ref)', dashed: true, points: linePoints(f, bench, live) }] : []),
  ]
  return (
    <>
      {back}
      <PageHeader
        title={
          <span className="inline-flex items-center gap-2">
            <Dot id={s.id} size="size-3.5" />
            {s.name}
          </span>
        }
        subtitle={s.mindset}
      />
      <p role="note" className="mb-3 text-xs text-slate-600 dark:text-zinc-400">
        <strong>Paper money only. Past and live results do not guarantee future results.</strong> {f.research_mode ? 'RESEARCH MODE: not yet proven live.' : ''}
      </p>
      <VersionSwitch v={v} set={setV} f={file} />
      <UniverseSwitch u={u} set={setU} f={f} />
      {live && <LiveLine live={live} />}
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="grid content-start gap-3">
          <Summary s={s} />
          <RightNow s={s} />
        </div>
        <div className="grid content-start gap-3">
          <Compare s={s} twin={twin} u={u} query={query} />
          <Card title={`Value since ${day(f.start)} (€)`}>
            <WhenVisible height="h-72">
              <Suspense fallback={<div className="h-72" aria-busy="true" />}>
                <StrategyChart series={series} start={f.capital} />
              </Suspense>
            </WhenVisible>
          </Card>
          <History s={s} />
          <Rules s={s} f={f} />
        </div>
      </div>
    </>
  )
}
