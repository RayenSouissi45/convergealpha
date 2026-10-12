import { lazy, Suspense } from 'react'
import { Link, useParams } from 'react-router'
import { Missing } from '../components/Missing'
import { WhenVisible } from '../components/WhenVisible'
import { Tip } from '../components/Tip'
import {
  AnalystsCard,
  EarningsCard,
  EstimatesCard,
  FilingsCard,
  FundamentalsCard,
  InsidersCard,
  NewsCard,
  NotAvailable,
  OptionsCard,
  OwnershipCard,
  type AnalystsSection,
  type EarningsSection,
  type EstimatesSection,
  type FilingItem,
  type FundamentalsSection,
  type InsidersSection,
  type NewsSection,
  type OptionsSection,
  type OwnershipSection,
} from '../components/stock/sections'
import {
  DecisionCard,
  FamiliesCard,
  ForecastCard,
  PlanCard,
  type DecisionSection,
  type FamiliesSection,
  type ForecastSection,
  type PlanSection,
} from '../components/stock/decision'
import { PatternsCard, type PatternsSection } from '../components/stock/patterns'
import { Badge, Card, PageHeader, Planned, Row } from '../components/ui'
import { renderCell } from '../lib/cells'
import { stockFile, useSiteJson } from '../lib/data'
import { formatAge, formatDay, formatMoney, formatPct, formatPrice, signClass } from '../lib/format'
import type { Cell, StockFile } from '../types'

const PriceChart = lazy(() => import('../components/PriceChart'))

type StatDef = [key: string, label: string, help: string]

const GROUPS: [string, StatDef[]][] = [
  [
    'Returns (dividends included)',
    [
      ['ret_1w', '1 week', 'Total return over the last 5 trading days.'],
      ['ret_1m', '1 month', 'Total return over the last 21 trading days.'],
      ['ret_3m', '3 months', 'Total return over the last 63 trading days.'],
      ['ret_6m', '6 months', 'Total return over the last 126 trading days.'],
      ['ret_ytd', 'Year to date', 'Total return since the last close of the previous year.'],
      ['ret_1y', '1 year', 'Total return over the last 252 trading days.'],
    ],
  ],
  [
    'Risk',
    [
      ['vol_63', 'Volatility (3 months)', 'Annualized standard deviation of daily returns, last 63 trading days.'],
      ['vol_252', 'Volatility (1 year)', 'Annualized standard deviation of daily returns, last 252 trading days.'],
      ['atr14', 'ATR (14 days)', 'Average true range: a typical daily price move in dollars.'],
      ['atr_pct', 'ATR % of price', 'Typical daily move as a share of price.'],
      ['gap_stress_pct', 'Gap stress', 'Average of the worst 2% overnight gaps over the last 500 days. A stop can be jumped by a gap this size.'],
      ['max_dd_1y', 'Max drawdown (1 year)', 'Largest fall from a peak over the last year.'],
    ],
  ],
  [
    'Trend',
    [
      ['sma50', '50-day average', 'Average close of the last 50 trading days.'],
      ['sma200', '200-day average', 'Average close of the last 200 trading days.'],
      ['trend_up', 'Uptrend', 'Price above the 50-day average, which is above the 200-day average.'],
      ['high_52w', '52-week high', 'Highest price of the last 52 weeks.'],
      ['low_52w', '52-week low', 'Lowest price of the last 52 weeks.'],
      ['dist_52w_high', 'From 52-week high', 'Distance below the 52-week high.'],
    ],
  ],
  [
    'Size and liquidity',
    [
      ['market_cap', 'Market cap', 'Shares outstanding (latest SEC filing) × price.'],
      ['adv_dollar', 'Avg daily $ volume', 'Average daily traded value over 21 days. Signals need at least $10M.'],
      ['adv_shares', 'Avg daily shares', 'Average daily share volume over 21 days.'],
      ['history_days', 'Days of history', 'Number of trading days of price history stored.'],
    ],
  ],
]

const KIND_OVERRIDE: Record<string, string> = { market_cap: 'money', sma50: 'price', sma200: 'price', high_52w: 'price', low_52w: 'price', atr14: 'price', adv_shares: 'num', history_days: 'num', ret_6m: 'pct', vol_252: 'pctAbs', gap_stress_pct: 'pctAbs', max_dd_1y: 'pct' }

function StatValue({ k, v }: { k: string; v: Cell }) {
  if (v === null || v === undefined) return <Missing reason="Not enough price history for this value yet." />
  const kind = KIND_OVERRIDE[k]
  if (kind === 'price' && typeof v === 'number') return <>{formatPrice(v)}</>
  if (kind === 'money' && typeof v === 'number') return <>{formatMoney(v)}</>
  if (kind === 'num' && typeof v === 'number') return <>{Math.round(v).toLocaleString('en-US')}</>
  if (kind === 'pct' && typeof v === 'number') return <span className={signClass(v)}>{formatPct(v)}</span>
  if (kind === 'pctAbs' && typeof v === 'number') return <>{(v * 100).toFixed(1)}%</>
  return <>{renderCell(k, v)}</>
}

function eligibilityReason(stats: Record<string, Cell>): string | null {
  const reasons = []
  if (typeof stats.price === 'number' && stats.price < 5) reasons.push('price below $5')
  if (typeof stats.adv_dollar === 'number' && stats.adv_dollar < 10_000_000) reasons.push('average daily traded value below $10M')
  if (!reasons.length) reasons.push('not priced on the last session')
  return reasons.join(' and ')
}

const PLANNED: [string, number, string][] = [
  ['Event patterns', 4, 'How this stock reacted to past events, after a luck test.'],
]

function sections(s: StockFile) {
  const out = []
  const analysts = s.analysts as AnalystsSection | null | undefined
  out.push(analysts ? <AnalystsCard key="a" a={analysts} /> : <NotAvailable key="a" title="Analysts" reason="No analyst data for this stock yet (snapshot rotation refreshes every stock at least weekly)." />)
  const est = s.estimates as EstimatesSection | null | undefined
  out.push(est ? <EstimatesCard key="e" e={est} /> : <NotAvailable key="e" title="EPS estimates and revisions" reason="No analyst estimates for this stock." />)
  const earn = s.earnings as EarningsSection | null | undefined
  out.push(earn ? <EarningsCard key="r" e={earn} /> : <NotAvailable key="r" title="Earnings" reason="No earnings dates recorded for this stock yet." />)
  const ins = s.insiders as InsidersSection | null | undefined
  out.push(ins ? <InsidersCard key="i" s={ins} /> : <NotAvailable key="i" title="Insider trades" reason="No SEC company identifier or no insider data for this stock." />)
  const own = s.ownership as OwnershipSection | null | undefined
  if (own) out.push(<OwnershipCard key="o" o={own} />)
  const opt = s.options as OptionsSection | null | undefined
  out.push(opt ? <OptionsCard key="p" o={opt} /> : <NotAvailable key="p" title="Options-implied move" reason="Options are fetched daily for the top ~400 candidates and your holdings only." />)
  const fund = s.fundamentals as FundamentalsSection | null | undefined
  out.push(fund ? <FundamentalsCard key="f" f={fund} /> : <NotAvailable key="f" title="Fundamentals" reason="No US GAAP XBRL filings for this company (foreign filers using IFRS are not parsed yet)." />)
  const news = s.news as NewsSection | null | undefined
  out.push(news ? <NewsCard key="n" n={news} /> : <NotAvailable key="n" title="News" reason="News is fetched daily for the top ~150 candidates and your holdings only." />)
  const fil = s.filings as FilingItem[] | undefined
  if (fil && fil.length) out.push(<FilingsCard key="s" f={fil} />)
  return out
}

export default function Stock() {
  const ticker = decodeURIComponent(useParams().ticker ?? '').toUpperCase()
  const res = useSiteJson<StockFile>(stockFile(ticker))

  if (res.state === 'loading') return <PageHeader title={ticker} subtitle="Loading…" />
  if (res.state !== 'ready') {
    return (
      <>
        <PageHeader title={ticker || 'Stock'} />
        <Card>
          <p className="text-sm text-slate-600 dark:text-zinc-400">
            {res.state === 'missing'
              ? `No data for ${ticker}. It may not be a US common stock on NYSE, Nasdaq or NYSE American, or it is not in today's universe.`
              : `Could not load ${ticker} (${res.message}).`}
          </p>
          <Link to="/screener" className="mt-3 inline-flex min-h-11 items-center text-sm font-medium text-teal-700 underline dark:text-teal-400">
            Search the screener
          </Link>
        </Card>
      </>
    )
  }

  const s = res.data
  const st = s.stats
  const price = typeof st.price === 'number' ? st.price : null
  const chg = typeof st.change_1d === 'number' ? st.change_1d : null
  const eligible = st.eligible === true

  return (
    <>
      <PageHeader
        title={
          <span className="flex flex-wrap items-baseline gap-x-3">
            <span>{s.ticker}</span>
            <span className="text-base font-normal text-slate-600 dark:text-zinc-400">{s.name}</span>
          </span>
        }
        subtitle={`${s.exchange}${s.is_adr ? ' · ADR' : ''}${s.sector ? ` · ${String(s.sector)}` : ''}${s.industry ? ` · ${String(s.industry)}` : ''} · prices as of ${formatDay(s.as_of)}`}
      />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <span className="text-3xl font-semibold tabular-nums">{price !== null ? formatPrice(price) : '—'}</span>
        {chg !== null && <span className={`text-lg tabular-nums ${signClass(chg)}`}>{formatPct(chg, 2)} today</span>}
        {eligible ? (
          <Badge tone="good">Eligible for signals</Badge>
        ) : (
          <Tip content={`Not eligible: ${eligibilityReason(st)}. Only eligible stocks can get a BUY label.`} label="Why not eligible" className="no-underline">
            <Badge tone="neutral">Not eligible for signals</Badge>
          </Tip>
        )}
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        {s.decision ? <DecisionCard d={s.decision as DecisionSection} /> : null}
        {s.forecast ? <ForecastCard f={s.forecast as ForecastSection} /> : null}
        {s.families ? <FamiliesCard f={s.families as FamiliesSection} /> : null}
        <Card title="Price" className="lg:col-span-2">
          {s.chart?.daily || s.chart?.weekly ? (
            <WhenVisible height="h-[21rem] sm:h-[27rem]">
              <Suspense fallback={<div className="h-[21rem] sm:h-[27rem]" aria-busy="true" />}>
                <PriceChart chart={s.chart} />
              </Suspense>
            </WhenVisible>
          ) : (
            <p className="text-sm text-slate-500">No chart data.</p>
          )}
        </Card>
        <Card title="Data freshness">
          <ul className="space-y-2 text-sm">
            {s.freshness.map((f) => (
              <li key={f.source}>
                <div className="font-medium">{f.name}</div>
                <div className="text-xs text-slate-500 dark:text-zinc-400">
                  As of {f.as_of ? formatDay(f.as_of) : <Missing reason="No data from this source yet." />}
                  {f.retrieved_at ? ` · fetched ${formatAge(f.retrieved_at)}` : ''}
                </div>
              </li>
            ))}
          </ul>
        </Card>
        {GROUPS.map(([title, stats]) => (
          <Card key={title} title={title}>
            <dl>
              {stats.map(([k, label, help]) => (
                <Row key={k} label={<Tip content={help}>{label}</Tip>}>
                  <StatValue k={k} v={st[k] ?? null} />
                </Row>
              ))}
            </dl>
          </Card>
        ))}
        {s.plan ? <PlanCard p={s.plan as PlanSection} ticker={s.ticker} label={(s.decision as DecisionSection | undefined)?.label ?? 'NO TRADE'} sector={typeof s.sector === 'string' ? s.sector : null} /> : null}
        {sections(s).map((card) => (
          <WhenVisible key={card.key} height="h-64">
            {card}
          </WhenVisible>
        ))}
        {s.patterns ? <PatternsCard p={s.patterns as PatternsSection} /> : null}
        {!s.patterns && PLANNED.map(([title, phase, text]) => (
          <Planned key={title} title={title} phase={phase}>
            <p>{text}</p>
          </Planned>
        ))}
      </div>
    </>
  )
}
