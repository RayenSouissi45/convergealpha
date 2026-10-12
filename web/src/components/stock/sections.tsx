import { lazy, Suspense, type ReactNode } from 'react'
import { formatDay, formatMoney, formatNum, formatPct, formatPctAbs, formatPrice, signClass } from '../../lib/format'
import { Missing } from '../Missing'
import { WhenVisible } from '../WhenVisible'
import { Tip } from '../Tip'
import { Badge, Card, Row } from '../ui'

const EpsChart = lazy(() => import('./EpsChart'))

// ---------------------------------------------------------------- section shapes (stocks/<T>.json)

export interface AnalystsSection {
  consensus: number | null
  consensus_label: string | null
  n_analysts: number | null
  target_mean: number | null
  target_median: number | null
  target_high: number | null
  target_low: number | null
  target_upside: number | null
  net_upgrades_90d: number | null
  finnhub_trend_score: number | null
  trend: { period: string; strongBuy: number | null; buy: number | null; hold: number | null; sell: number | null; strongSell: number | null }[]
  changes: { date: string; firm: string; from: string | null; to: string | null; action: string; target: number | null; prior_target: number | null }[]
  as_of: string | null
  source: string
}

export interface EstimatesSection {
  periods: {
    period: string
    end: string | null
    eps: Record<'cur' | '7d' | '30d' | '60d' | '90d', number | null>
    revisions: Record<'up7' | 'up30' | 'down30' | 'down7', number | null>
    analysts: number | null
    revenue: number | null
  }[]
  as_of: string | null
  source: string
}

export interface EarningsSection {
  next: string | null
  days_to_next: number | null
  sue: number | null
  history: {
    date: string
    timing: string
    eps_estimate: number | null
    eps_actual: number | null
    surprise_pct: number | null
    reaction_1d: number | null
    reaction_5d: number | null
    first_tradable: string | null
  }[]
  note: string
  source: string
}

export interface InsidersSection {
  buy_usd_90d: number | null
  sell_usd_90d: number | null
  buyers_30d: number | null
  trades: { filed: string; traded: string | null; insider: string; role: string | null; type: 'Buy' | 'Sell'; shares: number | null; price: number | null; value: number | null; kind: string }[]
  note: string
  source: string
}

export interface OwnershipSection {
  inst_pct: number | null
  insider_pct: number | null
  inst_top_change: number | null
  inst_net_buying_pct: number | null
  short_shares: number | null
  short_pct_float: number | null
  days_to_cover: number | null
  short_settlement: string | null
  source: string
}

export interface OptionsSection {
  iv_1w?: number | null
  iv_1m?: number | null
  move_1w?: number | null
  move_1m?: number | null
  range_1w?: [number, number]
  range_1m?: [number, number]
  put_call_volume?: number | null
  call_volume_oi?: number | null
  source: string
}

export interface FundamentalsSection {
  revenue_ttm: number | null
  net_income_ttm: number | null
  fcf_ttm: number | null
  roic: number | null
  gp_assets: number | null
  accruals: number | null
  fcf_yield: number | null
  debt_ebitda: number | null
  as_of: string | null
  source: string
}

export interface NewsSection {
  items: { datetime: string; headline: string; source: string | null; url: string | null; sentiment: number | null; tags: string[] }[]
  method: string
  ai: string
  source: string
}

export interface FilingItem {
  date: string
  form: string
  items: string[]
  accession: string
}

// ---------------------------------------------------------------- helpers

const dash = (reason: string) => <Missing reason={reason} />
const pct = (v: number | null | undefined, reason = 'Not available for this stock.') =>
  v === null || v === undefined ? dash(reason) : <span className={signClass(v)}>{formatPct(v)}</span>
const money = (v: number | null | undefined) => (v === null || v === undefined ? dash('Not available for this stock.') : formatMoney(v))
const price = (v: number | null | undefined) => (v === null || v === undefined ? dash('Not available for this stock.') : formatPrice(v))

function Source({ children }: { children: ReactNode }) {
  return <p className="mt-2 text-xs text-slate-500 dark:text-zinc-400">{children}</p>
}

const th = 'px-2 py-1.5 text-left text-xs font-semibold text-slate-600 dark:text-zinc-300'
const td = 'px-2 py-1.5 tabular-nums'

function Table({ head, children, caption }: { head: ReactNode[]; children: ReactNode; caption: string }) {
  return (
    <div className="-mx-4 overflow-x-auto px-4">
      <table className="w-full min-w-max text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-slate-200 dark:border-zinc-700">
            {head.map((h, i) => (
              <th key={i} scope="col" className={th}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-zinc-800">{children}</tbody>
      </table>
    </div>
  )
}

export function NotAvailable({ title, reason }: { title: string; reason: string }) {
  return (
    <Card title={title}>
      <p className="text-sm text-slate-500 dark:text-zinc-400">{reason}</p>
    </Card>
  )
}

// ---------------------------------------------------------------- sections

export function AnalystsCard({ a }: { a: AnalystsSection }) {
  const up = a.target_upside
  return (
    <Card title="Analysts">
      <dl>
        <Row label={<Tip content="Average analyst recommendation: 1 = strong buy, 3 = hold, 5 = strong sell.">Consensus</Tip>}>
          {a.consensus !== null ? `${a.consensus_label ?? ''} (${a.consensus.toFixed(2)})` : dash('No analyst coverage.')}
        </Row>
        <Row label="Analysts">{a.n_analysts ?? dash('No analyst coverage.')}</Row>
        <Row label={<Tip content="Mean 12-month price target. Analysts' targets are, on average, too optimistic.">Mean target</Tip>}>
          {price(a.target_mean)} {up !== null && <span className={`text-xs ${signClass(up)}`}>({formatPct(up)} vs price)</span>}
        </Row>
        <Row label="Target range">
          {a.target_low !== null && a.target_high !== null ? `${formatPrice(a.target_low)} – ${formatPrice(a.target_high)}` : dash('No targets.')}
        </Row>
        <Row label={<Tip content="Upgrades minus downgrades over the last 90 days.">Net upgrades (90 days)</Tip>}>
          {a.net_upgrades_90d ?? dash('No rating changes recorded.')}
        </Row>
      </dl>
      {a.trend.length > 0 && (
        <>
          <h3 className="mt-3 mb-1 text-sm font-semibold">Recommendations by month</h3>
          <Table head={['', 'Strong buy', 'Buy', 'Hold', 'Sell', 'Strong sell']} caption="Analyst recommendation counts by month">
            {a.trend.map((m) => (
              <tr key={m.period}>
                <th scope="row" className={`${td} text-left font-normal`}>
                  {m.period}
                </th>
                {[m.strongBuy, m.buy, m.hold, m.sell, m.strongSell].map((v, i) => (
                  <td key={i} className={td}>
                    {v ?? '—'}
                  </td>
                ))}
              </tr>
            ))}
          </Table>
        </>
      )}
      {a.changes.length > 0 && (
        <>
          <h3 className="mt-3 mb-1 text-sm font-semibold">Recent rating changes</h3>
          <Table head={['Date', 'Firm', 'Rating', 'Target']} caption="Recent analyst rating changes">
            {a.changes.map((c, i) => (
              <tr key={i}>
                <td className={td}>{formatDay(c.date)}</td>
                <td className={td}>{c.firm}</td>
                <td className={td}>
                  {c.action === 'up' ? '▲ ' : c.action === 'down' ? '▼ ' : ''}
                  {c.from && c.from !== c.to ? `${c.from} → ` : ''}
                  {c.to ?? '—'}
                  <span className="sr-only">{c.action === 'up' ? ' (upgrade)' : c.action === 'down' ? ' (downgrade)' : ''}</span>
                </td>
                <td className={td}>
                  {c.target !== null ? formatPrice(c.target) : '—'}
                  {c.prior_target !== null && c.target !== null && c.prior_target !== c.target ? ` (from ${formatPrice(c.prior_target)})` : ''}
                </td>
              </tr>
            ))}
          </Table>
        </>
      )}
      <Source>
        {a.source}
        {a.as_of ? ` · fetched ${formatDay(a.as_of.slice(0, 10))}` : ''}
      </Source>
    </Card>
  )
}

export function EstimatesCard({ e }: { e: EstimatesSection }) {
  const year = e.periods.find((p) => p.period === 'This year')
  const points = year
    ? (
        [
          ['90d ago', year.eps['90d']],
          ['60d ago', year.eps['60d']],
          ['30d ago', year.eps['30d']],
          ['7d ago', year.eps['7d']],
          ['Now', year.eps.cur],
        ] as const
      ).flatMap(([label, v]) => (v === null ? [] : [{ label, eps: v }]))
    : []
  return (
    <Card title="EPS estimates and revisions">
      {points.length >= 2 && (
        <>
          <h3 className="mb-1 text-sm font-semibold">This year’s EPS estimate over 90 days</h3>
          <WhenVisible height="h-44">
            <Suspense fallback={<div className="h-44" />}>
              <EpsChart points={points} />
            </Suspense>
          </WhenVisible>
        </>
      )}
      <Table head={['Period', 'Now', '30d ago', '90d ago', 'Up / down (30d)', 'Analysts']} caption="EPS estimates by period">
        {e.periods.map((p) => {
          const chg = p.eps.cur !== null && p.eps['90d'] !== null && p.eps['90d'] !== 0 ? p.eps.cur / Math.abs(p.eps['90d']) - Math.sign(p.eps['90d']) : null
          return (
            <tr key={p.period}>
              <th scope="row" className={`${td} text-left font-normal`}>
                {p.period}
              </th>
              <td className={td}>{p.eps.cur !== null ? `$${p.eps.cur.toFixed(2)}` : '—'}</td>
              <td className={td}>{p.eps['30d'] !== null ? `$${p.eps['30d'].toFixed(2)}` : '—'}</td>
              <td className={td}>
                {p.eps['90d'] !== null ? `$${p.eps['90d'].toFixed(2)}` : '—'} {chg !== null && <span className={`text-xs ${signClass(chg)}`}>({formatPct(chg)})</span>}
              </td>
              <td className={td}>
                {p.revisions.up30 ?? '—'} ▲ / {p.revisions.down30 ?? '—'} ▼
              </td>
              <td className={td}>{p.analysts ?? '—'}</td>
            </tr>
          )
        })}
      </Table>
      <Source>{e.source}</Source>
    </Card>
  )
}

export function EarningsCard({ e }: { e: EarningsSection }) {
  return (
    <Card title="Earnings">
      <dl>
        <Row label="Next report">{e.next ? `${formatDay(e.next)}${e.days_to_next !== null ? ` (in ${e.days_to_next} trading days)` : ''}` : dash('No date announced yet.')}</Row>
        <Row label={<Tip content="Standardized unexpected earnings at the last report: (actual − consensus) ÷ the typical size of the last 8 surprises. Above +2 is a big beat.">SUE (last report)</Tip>}>
          {e.sue !== null ? formatNum(e.sue) : dash('Needs at least 4 past surprises.')}
        </Row>
      </dl>
      {e.history.length > 0 && (
        <Table
          head={[
            'Date',
            'EPS est.',
            'Actual',
            'Surprise',
            <Tip key="r1" content="From the first tradable price after the report (the next open) to that day's close.">Reaction 1d</Tip>,
            <Tip key="r5" content="From the first tradable price after the report to the close 5 sessions later.">5d</Tip>,
          ]}
          caption="Earnings history with tradable reactions"
        >
          {e.history.map((h) => (
            <tr key={h.date}>
              <td className={td}>
                {formatDay(h.date)} <span className="text-xs text-slate-500">{h.timing}</span>
              </td>
              <td className={td}>{h.eps_estimate !== null ? h.eps_estimate.toFixed(2) : '—'}</td>
              <td className={td}>{h.eps_actual !== null ? h.eps_actual.toFixed(2) : '—'}</td>
              <td className={td}>{h.surprise_pct !== null ? <span className={signClass(h.surprise_pct)}>{formatPct(h.surprise_pct)}</span> : '—'}</td>
              <td className={td}>{h.reaction_1d !== null ? <span className={signClass(h.reaction_1d)}>{formatPct(h.reaction_1d)}</span> : '—'}</td>
              <td className={td}>{h.reaction_5d !== null ? <span className={signClass(h.reaction_5d)}>{formatPct(h.reaction_5d)}</span> : '—'}</td>
            </tr>
          ))}
        </Table>
      )}
      <Source>
        {e.note} {e.source}.
      </Source>
    </Card>
  )
}

const KIND_TONE = { opportunistic: 'good', routine: 'neutral', 'planned (10b5-1)': 'neutral' } as const

export function InsidersCard({ s }: { s: InsidersSection }) {
  return (
    <Card title="Insider trades">
      <dl>
        <Row label={<Tip content="Opportunistic open-market purchases filed in the last 90 days.">Opportunistic buying (90 days)</Tip>}>{money(s.buy_usd_90d)}</Row>
        <Row label="Opportunistic selling (90 days)">{money(s.sell_usd_90d)}</Row>
        <Row label="Different buyers (30 days)">{s.buyers_30d ?? '—'}</Row>
      </dl>
      {s.trades.length > 0 ? (
        <Table head={['Filed', 'Insider', 'Type', 'Value', 'Kind']} caption="Insider trades in the last year">
          {s.trades.map((t, i) => (
            <tr key={i}>
              <td className={td}>{formatDay(t.filed)}</td>
              <td className={`${td} max-w-48`}>
                <div className="truncate">{t.insider}</div>
                <div className="truncate text-xs text-slate-500">{t.role}</div>
              </td>
              <td className={td}>{t.type === 'Buy' ? '▲ Buy' : '▼ Sell'}</td>
              <td className={td}>{t.value !== null ? formatMoney(t.value) : '—'}</td>
              <td className={td}>
                <Badge tone={KIND_TONE[t.kind as keyof typeof KIND_TONE] ?? 'neutral'}>{t.kind}</Badge>
              </td>
            </tr>
          ))}
        </Table>
      ) : (
        <p className="mt-2 text-sm text-slate-500">No open-market insider trades in the last year.</p>
      )}
      <Source>
        {s.note} {s.source}.
      </Source>
    </Card>
  )
}

export function OwnershipCard({ o }: { o: OwnershipSection }) {
  return (
    <Card title="Ownership and short interest">
      <dl>
        <Row label="Held by institutions">{o.inst_pct !== null ? formatPctAbs(o.inst_pct) : dash('Not reported.')}</Row>
        <Row label="Held by insiders">{o.insider_pct !== null ? formatPctAbs(o.insider_pct) : dash('Not reported.')}</Row>
        <Row label={<Tip content="Average change in position of the largest institutional holders at their last report, weighted by size.">Top holders’ position change</Tip>}>{pct(o.inst_top_change)}</Row>
        <Row label={<Tip content="Shares sold short as a share of the float (FINRA, twice monthly, used only after it is published).">Short interest (% of float)</Tip>}>
          {o.short_pct_float !== null ? formatPctAbs(o.short_pct_float) : dash('Not reported.')}
        </Row>
        <Row label={<Tip content="Short interest ÷ average daily volume: how many days of normal trading it would take shorts to buy back.">Days to cover</Tip>}>
          {o.days_to_cover !== null ? formatNum(o.days_to_cover, 1) : dash('Not reported.')}
        </Row>
        <Row label="Short interest date">{o.short_settlement ? formatDay(o.short_settlement) : dash('Not reported.')}</Row>
      </dl>
      <Source>{o.source}</Source>
    </Card>
  )
}

export function OptionsCard({ o }: { o: OptionsSection }) {
  const line = (label: string, move?: number | null, range?: [number, number], iv?: number | null) => (
    <Row label={<Tip content={`What option prices imply: about two times in three, the price ${label} is expected to stay inside this range. Based on at-the-money implied volatility${iv ? ` of ${formatPctAbs(iv)} a year` : ''}.`}>{`Expected move, ${label}`}</Tip>}>
      {move !== null && move !== undefined ? (
        <>
          ±{formatPctAbs(move)} {range && <span className="text-xs text-slate-500">({formatPrice(range[0])} – {formatPrice(range[1])})</span>}
        </>
      ) : (
        dash('No liquid options for this horizon.')
      )}
    </Row>
  )
  return (
    <Card title="Options-implied move">
      <dl>
        {line('1 week', o.move_1w, o.range_1w, o.iv_1w)}
        {line('1 month', o.move_1m, o.range_1m, o.iv_1m)}
        <Row label={<Tip content="Put volume ÷ call volume for the ~1-month expiry. Above 1 means more puts traded than calls.">Put/call volume</Tip>}>
          {o.put_call_volume !== null && o.put_call_volume !== undefined ? formatNum(o.put_call_volume) : '—'}
        </Row>
      </dl>
      <Source>{o.source}</Source>
    </Card>
  )
}

export function FundamentalsCard({ f }: { f: FundamentalsSection }) {
  const r = (v: number | null, digits = 1) => (v === null ? dash('Not reported in SEC filings.') : formatPctAbs(v, digits))
  return (
    <Card title="Fundamentals (trailing 12 months)">
      <dl>
        <Row label="Revenue">{money(f.revenue_ttm)}</Row>
        <Row label="Net income">{money(f.net_income_ttm)}</Row>
        <Row label="Free cash flow">{money(f.fcf_ttm)}</Row>
        <Row label={<Tip content="After-tax operating profit ÷ (equity + debt − cash). How well the business earns on the capital it uses.">Return on invested capital</Tip>}>{r(f.roic)}</Row>
        <Row label={<Tip content="Gross profit ÷ total assets: a robust profitability measure.">Gross profit / assets</Tip>}>{r(f.gp_assets)}</Row>
        <Row label={<Tip content="(Net income − operating cash flow) ÷ assets. High accruals (profits not backed by cash) tend to be a warning sign.">Accruals</Tip>}>{r(f.accruals)}</Row>
        <Row label={<Tip content="Free cash flow ÷ market value.">FCF yield</Tip>}>{r(f.fcf_yield)}</Row>
        <Row label={<Tip content="Total debt ÷ EBITDA. Above 4 is heavy; negative EBITDA with debt is shown as 20.">Debt / EBITDA</Tip>}>
          {f.debt_ebitda === null ? dash('Not reported in SEC filings.') : formatNum(f.debt_ebitda, 1)}
        </Row>
      </dl>
      <Source>
        {f.source}
        {f.as_of ? ` · latest filing used: ${formatDay(f.as_of)}` : ''}
      </Source>
    </Card>
  )
}

export function NewsCard({ n }: { n: NewsSection }) {
  return (
    <Card title="News">
      <ul className="divide-y divide-slate-100 dark:divide-zinc-800">
        {n.items.map((it, i) => (
          <li key={i} className="py-2">
            {it.url ? (
              <a href={it.url} target="_blank" rel="noreferrer noopener" className="text-sm font-medium hover:underline">
                {it.headline}
              </a>
            ) : (
              <span className="text-sm font-medium">{it.headline}</span>
            )}
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-500 dark:text-zinc-400">
              <span>
                {formatDay(it.datetime.slice(0, 10))} · {it.source}
              </span>
              {it.sentiment !== null && (
                <Badge tone={it.sentiment > 0.2 ? 'good' : it.sentiment < -0.2 ? 'bad' : 'neutral'}>
                  {it.sentiment > 0.2 ? 'positive' : it.sentiment < -0.2 ? 'negative' : 'neutral'} wording
                </Badge>
              )}
              {it.tags.map((t) => (
                <Badge key={t} tone="warn">
                  {t.replace(/_/g, ' ')}
                </Badge>
              ))}
            </div>
          </li>
        ))}
      </ul>
      <Source>
        {n.source}. Tone from the {n.method} financial word lists; event tags from keywords. AI event extraction: {n.ai}.
      </Source>
    </Card>
  )
}

export function FilingsCard({ f }: { f: FilingItem[] }) {
  return (
    <Card title="Recent SEC filings">
      <ul className="divide-y divide-slate-100 text-sm dark:divide-zinc-800">
        {f.map((x) => (
          <li key={x.accession} className="py-2">
            <span className="font-medium">{x.form}</span> · {formatDay(x.date)}
            {x.items.length > 0 && <div className="text-xs text-slate-500 dark:text-zinc-400">{x.items.join(' · ')}</div>}
          </li>
        ))}
      </ul>
      <Source>SEC EDGAR</Source>
    </Card>
  )
}
