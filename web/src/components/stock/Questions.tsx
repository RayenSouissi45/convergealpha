import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { formatEur } from '../../lib/costs'
import { useSiteJson } from '../../lib/data'
import { formatPct, formatPctAbs } from '../../lib/format'
import { positions, useJournal } from '../../lib/journal'
import { useTradeSettings } from '../../lib/settings'
import type { PlanFile, StockFile } from '../../types'
import { Badge, Card } from '../ui'
import type { DecisionSection, FamiliesSection, ForecastSection } from './decision'

export interface WhyMove {
  move: number
  market: number
  sector: number
  own: number
  news: { headline: string; source: string | null; url: string | null }[]
  filings: { form: string; what: string }[]
  text: string
}

export interface Valuation {
  value_pct?: number | null
  value_fcf_pct?: number | null
  value_earn_pct?: number | null
  earnings_yield?: number | null
  fcf_yield?: number | null
  value_view?: string | null
}

export interface Distress {
  level: 'low' | 'elevated' | 'high' | null
  why: string | null
}

/** "Why did it move today?": market, sector and its own part, with that day's news or filing. */
export function WhyMoveLine({ w }: { w: WhyMove | null | undefined }) {
  if (!w) return null
  const link = w.news.find((n) => n.url)
  return (
    <p className="mb-3 text-sm text-slate-700 dark:text-zinc-300">
      <strong>Why did it move today?</strong> {w.text}
      {link?.url && (
        <>
          {' '}
          <a href={link.url} target="_blank" rel="noreferrer" className="text-teal-700 underline dark:text-teal-400">
            Read{link.source ? ` (${link.source})` : ''}
          </a>
        </>
      )}
    </p>
  )
}

const DISTRESS_TONE = { low: 'good', elevated: 'warn', high: 'bad' } as const

function Q({ n, q, children }: { n: number; q: string; children: ReactNode }) {
  return (
    <li className="py-2">
      <p className="font-semibold">
        <span className="mr-1 text-slate-500 tabular-nums dark:text-zinc-400">{n}.</span>
        {q}
      </p>
      <div className="mt-0.5 text-sm text-slate-700 dark:text-zinc-300">{children}</div>
    </li>
  )
}

/** Seven questions every buy should answer, from what the app knows, and honest about what it does not. */
export function SevenQuestions({ s }: { s: StockFile }) {
  const d = s.decision as DecisionSection | undefined
  const fc = s.forecast as ForecastSection | undefined
  const fam = s.families as FamiliesSection | undefined
  const val = (s.valuation as Valuation | undefined) ?? null
  const dis = (s.distress as Distress | null | undefined) ?? null
  const plan = useSiteJson<PlanFile>('plan.json')
  const [journal] = useJournal()
  const [settings] = useTradeSettings()
  const m1 = fc?.horizons?.['1m'] ?? null
  const base1m = plan.state === 'ready' ? (plan.data.base_up['1m'] ?? null) : null
  const validated = typeof fc?.validated === 'object' && fc.validated !== null ? Boolean((fc.validated as Record<string, { up: boolean }>)['1m']?.up) : fc?.validated === true
  const strong = (fam?.families ?? []).filter((f) => (f.score ?? 0) >= 60).sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
  const weak = (fam?.families ?? []).filter((f) => f.score !== null && f.score < 40)
  const unknown = (fam?.families ?? []).filter((f) => f.score === null)
  const held = positions({ ...journal, trades: journal.trades.filter((t) => !t.paper) }, new Map(), null)
  const isHeld = held.some((p) => p.ticker === s.ticker)
  const invested = held.reduce((a, p) => a + p.costEur, 0) + (journal.cashEur ?? 0)
  const amount = settings.amount
  const share = invested > 0 ? amount / (invested + (journal.cashEur === null ? amount : 0)) : null
  return (
    <Card title="Seven questions before you buy" className="lg:col-span-2">
      <ol className="divide-y divide-slate-100 dark:divide-zinc-800">
        <Q n={1} q="Why could it rise?">
          {strong.length ? `Strongest evidence: ${strong.slice(0, 3).map((f) => `${f.name} ${Math.round(f.score ?? 0)}`).join(', ')}.` : 'No evidence family is strong (60+) today.'}{' '}
          {d?.why ?? ''}
        </Q>
        <Q n={2} q="How good is the evidence?">
          {m1 ? (
            <>
              Chance of rising in 1 month: <strong>{formatPctAbs(m1.p_up, 0)}</strong>
              {base1m !== null ? ` vs ${formatPctAbs(base1m, 0)} for any stock` : ''}. <Badge tone={validated ? 'good' : 'warn'}>{validated ? '✓ validated' : 'RESEARCH MODE'}</Badge>
            </>
          ) : (
            'No forecast for this stock.'
          )}{' '}
          {fam?.disagreement !== null && fam?.disagreement !== undefined && fam.disagreement > 0.25 ? 'The evidence disagrees with itself: be careful.' : ''}
        </Q>
        <Q n={3} q="What could go wrong?">
          {m1 ? `In 1 month out of 10 it falls ${formatPct(m1.p10, 0)} or worse with nothing wrong. ` : ''}
          {weak.length ? `Weak evidence: ${weak.map((f) => f.name).join(', ')}. ` : ''}
          {d?.blocking?.length ? `Blocked now: ${d.blocking.join('; ')}. ` : ''}
          {d?.risk_reasons?.length ? `Risks: ${d.risk_reasons.join('; ')}. ` : ''}
          {dis?.why && /debt (above 6x EBITDA|with negative EBITDA)/.test(dis.why) && (
            <>
              <Badge tone="warn">Tested warning</Badge> Heavy debt: among the model's top picks in 2016–2023, such stocks did worse (−1.4% vs +0.8% over the next 3 months; the one filter of four that helped in both halves).{' '}
            </>
          )}
          {dis?.level && (
            <>
              Company finances: <Badge tone={DISTRESS_TONE[dis.level]}>{dis.level === 'low' ? 'no warning sign' : dis.level === 'elevated' ? 'some warning signs' : 'fragile'}</Badge> {dis.why ? `(${dis.why})` : ''}
            </>
          )}
        </Q>
        <Q n={4} q="What is already in the price?">
          {val?.value_view ? (
            <>
              It looks <strong>{val.value_view}</strong>
              {typeof val.value_pct === 'number' ? ` (cheaper than ${Math.round(val.value_pct)}% of its sector by cash flow and earnings)` : ''}. Cheap can stay cheap; expensive often means high hopes are priced in.
            </>
          ) : (
            'No valuation: the company accounts are not available in the SEC data the app reads.'
          )}
        </Q>
        <Q n={5} q="What does the app not know?">
          {unknown.length ? `No data for: ${unknown.map((f) => f.name).join(', ')}. ` : ''}
          It cannot see private news, the next earnings surprise, or what big investors are about to do. Free data lacks most delisted companies, so its history looks a bit better than reality.
        </Q>
        <Q n={6} q="What would it do to your portfolio?">
          {isHeld ? (
            <>You already own it: buying more raises the risk in one stock. </>
          ) : share !== null ? (
            <>
              {formatEur(amount, 0)} (your Plan amount) would be about <strong>{formatPctAbs(share, 0)}</strong> of your money.{' '}
            </>
          ) : (
            <>Log your trades on Portfolio to see this against your own holdings. </>
          )}
          <Link to={`/portfolio?tab=log&t=${encodeURIComponent(s.ticker)}`} className="text-teal-700 underline dark:text-teal-400">
            Check it against your rules
          </Link>
        </Q>
        <Q n={7} q="Is it better than the simple alternative?">
          {m1 && base1m !== null ? (
            m1.p_up - base1m >= 0.03 ? (
              <>Its chance of rising is {Math.round((m1.p_up - base1m) * 100)} points above the usual rate. Still, a broad ETF gives you the market's return without picking, for about 0.2% a year.</>
            ) : (
              <>Its chance of rising is close to any stock's ({formatPctAbs(m1.p_up, 0)} vs {formatPctAbs(base1m, 0)}): a broad ETF is the simpler choice unless you have a reason the app cannot see.</>
            )
          ) : (
            'A broad ETF is the default alternative: the market return for about 0.2% a year, no picking needed.'
          )}
        </Q>
      </ol>
    </Card>
  )
}
