import { useMemo, type ReactNode } from 'react'
import { Link } from 'react-router'
import { Icon } from '../components/Icon'
import { IntradayCard } from '../components/IntradayCard'
import { MarketCard } from '../components/MarketCard'
import { LabelBadge } from '../components/LabelBadge'
import { Tip } from '../components/Tip'
import { Card, PageHeader } from '../components/ui'
import { formatDay, formatMoney, formatNum, formatPct } from '../lib/format'
import { holdingStatus, usePortfolio } from '../lib/portfolio'
import { useSiteJson } from '../lib/data'
import { toRows, useScreener } from '../lib/screener'
import { useBrokerList, useOnlyZero, zeroAvailability, zeroKeep } from '../lib/zero'
import { ZeroBadge, ZeroToggle } from '../components/Zero'
import type { ScreenerFile, ScreenerRow } from '../types'

const num = (r: ScreenerRow, k: string) => (typeof r[k] === 'number' ? (r[k] as number) : null)
const isBuy = (r: ScreenerRow) => r.label === 'BUY' || r.label === 'STRONG BUY — TOP CONVICTION'

function StockList({
  title,
  help,
  rows,
  metric,
  empty,
  more,
}: {
  title: string
  help: string
  rows: ScreenerRow[]
  metric: (r: ScreenerRow) => ReactNode
  empty: string
  more?: string
}) {
  return (
    <Card
      className="min-h-[22rem]"
      title={<Tip content={help}>{title}</Tip>}
      aside={more ? <Link to={more} className="min-h-11 text-sm text-teal-700 underline dark:text-teal-400">All</Link> : undefined}
    >
      {rows.length === 0 ? (
        <p className="text-sm text-slate-500 dark:text-zinc-400">{empty}</p>
      ) : (
        <ul className="divide-y divide-slate-100 dark:divide-zinc-800">
          {rows.map((r) => (
            <li key={r.ticker}>
              <Link to={`/stock/${encodeURIComponent(r.ticker)}`} className="flex min-h-12 items-center justify-between gap-3 py-1.5 hover:bg-slate-50 dark:hover:bg-zinc-800">
                <span className="flex min-w-0 items-baseline gap-1.5">
                  <span className="shrink-0 font-semibold">{r.ticker}</span>
                  <span className="shrink-0 self-center">
                    <ZeroBadge value={r.zero} interactive={false} />
                  </span>
                  <span className="min-w-0 truncate text-sm text-slate-500 dark:text-zinc-400">{String(r.name ?? '')}</span>
                </span>
                <span className="shrink-0 text-right text-sm tabular-nums">{metric(r)}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

const RM = 'RESEARCH MODE: not yet validated.'

export default function Today() {
  const [portfolio] = usePortfolio()
  // today.json holds only the rows these lists can show (a few KB). The full screener (~1 MB) is
  // loaded only to check holdings, or when an older export has no today.json.
  const todayFile = useSiteJson<ScreenerFile>('today.json')
  const todayRows = useMemo(() => (todayFile.state === 'ready' ? toRows(todayFile.data) : null), [todayFile])
  const needFull = portfolio.holdings.length > 0 || todayFile.state === 'missing' || todayFile.state === 'error'
  const screener = useScreener(needFull)
  const full = screener.state === 'ready' ? screener.data.rows : null
  const [onlyZero] = useOnlyZero()
  const zeroOk = zeroAvailability(useBrokerList()).ok
  const allRows = todayRows ?? full ?? []
  const rows = allRows.filter((r) => zeroKeep(r.zero, onlyZero && zeroOk))
  const listState = todayRows ? 'ready' : needFull ? screener.state : 'loading'
  const byTicker = screener.state === 'ready' ? screener.data.byTicker : new Map<string, ScreenerRow>()
  const elig = rows.filter((r) => r.eligible === true)
  const top = (list: ScreenerRow[], key: string, n = 8, asc = false) =>
    list
      .filter((r) => num(r, key) !== null)
      .sort((a, b) => (asc ? 1 : -1) * ((num(a, key) ?? 0) - (num(b, key) ?? 0)))
      .slice(0, n)

  const conviction = elig.filter((r) => r.label === 'STRONG BUY — TOP CONVICTION')
  const buys = top(elig.filter((r) => r.label === 'BUY'), 'ev', 12)
  const watch = top(elig.filter((r) => r.label === 'WATCH'), 'ev', 6)
  const earnings = rows
    .filter((r) => num(r, 'days_to_earnings') !== null && (num(r, 'days_to_earnings') as number) >= 0 && (num(r, 'days_to_earnings') as number) <= 5 && r.eligible === true)
    .sort((a, b) => (num(a, 'days_to_earnings') ?? 0) - (num(b, 'days_to_earnings') ?? 0) || (num(b, 'adv_dollar') ?? 0) - (num(a, 'adv_dollar') ?? 0))
    .slice(0, 10)
  const candidates = (full ?? rows).filter((r) => r.eligible === true && isBuy(r))
  const warnings = portfolio.holdings
    .map((h) => ({ h, s: holdingStatus(h, byTicker.get(h.ticker), candidates) }))
    .filter((x) => x.s.label !== 'HOLD')

  return (
    <>
      <PageHeader title="Today" subtitle="What to look at after today's close." />
      <Link
        to="/picks"
        className="mb-3 flex min-h-14 items-center justify-between gap-3 rounded-xl border border-teal-600/30 bg-teal-50 px-4 py-2.5 hover:bg-teal-100 dark:border-teal-400/30 dark:bg-teal-950 dark:hover:bg-teal-900"
      >
        <span className="min-w-0">
          <span className="block font-semibold text-teal-900 dark:text-teal-100">Picks: the best-balanced suggestions</span>
          <span className="block text-sm text-teal-900/80 dark:text-teal-100/80">Safety, upside and confidence together, with how often the app was right before.</span>
        </span>
        <Icon name="chevron" className="size-5 shrink-0 text-teal-700 dark:text-teal-300" />
      </Link>
      <div className="mb-3">
        <ZeroToggle values={allRows.map((r) => r.zero)} noun="stocks in these lists" />
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <MarketCard />
        <IntradayCard />
        {portfolio.holdings.length > 0 && (
          <Card title="Warnings for my holdings" aside={<Link to="/portfolio" className="text-sm text-teal-700 underline dark:text-teal-400">Portfolio</Link>}>
            {screener.state !== 'ready' ? (
              <p className="text-sm text-slate-500" aria-busy={screener.state === 'loading'}>{screener.state === 'loading' ? 'Checking your holdings…' : 'Stock data is not available yet.'}</p>
            ) : warnings.length === 0 ? (
              <p className="text-sm">All {portfolio.holdings.length} holdings: HOLD (no exit rule triggered).</p>
            ) : (
              <ul className="divide-y divide-slate-100 dark:divide-zinc-800">
                {warnings.map(({ h, s }) => (
                  <li key={h.ticker} className="py-2">
                    <div className="flex items-center justify-between">
                      <Link to={`/stock/${h.ticker}`} className="font-semibold underline">{h.ticker}</Link>
                      <LabelBadge label={s.label} />
                    </div>
                    <p className="text-sm text-slate-600 dark:text-zinc-400">{s.reasons.join(' ')}</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        )}
        {listState === 'ready' ? (
          <>
            <StockList
              title="Top Conviction"
              help="Shown only when every C1–C7 rule passes: all families strong and in agreement, a calm market, and ≥ 100 similar past setups whose 6-month up rate has a Wilson lower bound ≥ 65%."
              rows={conviction}
              metric={(r) => <LabelBadge label={String(r.label)} />}
              empty="None today. That is normal: Top Conviction needs almost all independent evidence to agree and history to back it."
            />
            <StockList
              title="Buy list (by expected value)"
              help={`Stocks passing all trade rules R1–R12, sorted by expected value of the 60-day trade after costs. ${RM}`}
              rows={buys}
              metric={(r) => (
                <>
                  EV {formatPct(num(r, 'ev') ?? 0, 2)} <span className="text-xs text-slate-500">tier {String(r.tier ?? '—')}</span>
                </>
              )}
              empty="No stock passes every rule today. The app says NO TRADE when the evidence is weak."
              more="/screener?preset=likely"
            />
            {watch.length > 0 && (
              <StockList title="Watch" help="Stocks that miss exactly one evidence rule by a small margin." rows={watch} metric={(r) => <LabelBadge label={String(r.label)} />} empty="" />
            )}
            <StockList
              title="Most likely to rise (6 months)"
              help={`Eligible stocks with the highest chance of being higher (with dividends) in 6 months (126 trading days). ${RM}`}
              rows={top(elig, 'p_up_6m')}
              metric={(r) => `${Math.round((num(r, 'p_up_6m') ?? 0) * 100)}% chance up`}
              empty="Forecasts are not available yet."
              more="/screener?preset=likely"
            />
            <StockList
              title="Biggest upside (6 months)"
              help={`Optimistic scenario: the 90th-percentile 6-month forecast (only 1 in 10 outcomes expected above). Analyst target upside shown for reference. ${RM}`}
              rows={top(elig, 'p90_6m')}
              metric={(r) => (
                <>
                  {formatPct(num(r, 'p90_6m') ?? 0, 0)} <span className="text-xs text-slate-500">target {num(r, 'target_upside') !== null ? formatPct(num(r, 'target_upside')!, 0) : '—'}</span>
                </>
              )}
              empty="Forecasts are not available yet."
              more="/screener?preset=upside"
            />
            <StockList
              title="Fastest"
              help={`Expected gain per month divided by volatility per month (median 6-month forecast ÷ 6). ${RM}`}
              rows={top(elig, 'speed')}
              metric={(r) => (
                <>
                  {formatPct(num(r, 'gain_per_month') ?? 0, 1)}/mo <span className="text-xs text-slate-500">speed {formatNum(num(r, 'speed') ?? 0)}</span>
                </>
              )}
              empty="Forecasts are not available yet."
              more="/screener?preset=fastest"
            />
            <StockList
              title="Insider buying this week"
              help="Opportunistic open-market purchases filed with the SEC in the last 7 days (routine traders and 10b5-1 plan trades excluded)."
              rows={top(rows.filter((r) => (num(r, 'insider_buy_7d') ?? 0) > 0), 'insider_buy_7d', 10)}
              metric={(r) => formatMoney(num(r, 'insider_buy_7d') ?? 0)}
              empty="No opportunistic insider purchases filed in the last 7 days."
              more="/screener?preset=insiders"
            />
            <StockList
              title="Earnings this week"
              help="Eligible stocks reporting in the next 5 trading days. New entries are blocked until the report (post-earnings entries 1–10 days after are allowed)."
              rows={earnings}
              metric={(r) => (
                <>
                  {typeof r.next_earnings === 'string' ? formatDay(r.next_earnings.slice(0, 10)) : '—'} <span className="text-xs text-amber-700 dark:text-amber-400">blocks entries</span>
                </>
              )}
              empty="No eligible stock reports in the next 5 trading days."
              more="/screener?preset=earnings"
            />
          </>
        ) : listState === 'loading' ? (
          ['Top Conviction', 'Buy list (by expected value)', 'Most likely to rise (6 months)', 'Biggest upside (6 months)'].map((title) => (
            <Card key={title} title={title} className="min-h-[22rem]">
              <p className="text-sm text-slate-500" aria-busy="true">Loading…</p>
            </Card>
          ))
        ) : (
          <Card>
            <p className="text-sm text-slate-500">Stock lists appear after the first daily pipeline run.</p>
          </Card>
        )}
      </div>
    </>
  )
}
