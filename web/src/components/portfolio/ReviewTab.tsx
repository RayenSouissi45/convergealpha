import { useState } from 'react'
import { formatEur, formatEurSigned } from '../../lib/costs'
import { signClass } from '../../lib/format'
import { behaviour, decisionQuality, fifo, type Journal, type Quadrant } from '../../lib/journal'
import { measuredCosts } from '../../lib/orderHelp'
import type { ScreenerRow } from '../../types'
import { Badge, Card } from '../ui'

const QUAD: Record<Quadrant, { title: string; tone: 'good' | 'warn' | 'bad' | 'neutral'; text: string }> = {
  skill: { title: 'Good decision, good result', tone: 'good', text: 'Keep doing this.' },
  unlucky: { title: 'Good decision, bad result', tone: 'neutral', text: 'Bad luck happens: the process was right.' },
  lucky: { title: 'Weak decision, good result', tone: 'warn', text: 'Luck: do not repeat the shortcut.' },
  mistake: { title: 'Weak decision, bad result', tone: 'bad', text: 'Learn from these first.' },
}

/** What trading costs you: fees as a share of your money per year, and your real fills vs the app's estimate. */
function CostsCard({ j, rows, total }: { j: Journal; rows: Map<string, ScreenerRow>; total: number }) {
  const [now] = useState(() => new Date())
  const year = String(now.getFullYear())
  const fees = j.trades.filter((t) => t.date.startsWith(year)).reduce((s, t) => s + t.feeEur, 0)
  const start = new Date(now.getFullYear(), 0, 1)
  const days = Math.max(30, (now.getTime() - start.getTime()) / 86400000)
  const perYear = total > 0 ? ((fees / total) * 365) / days : null
  const m = measuredCosts(j, (tk) => {
    const s = rows.get(tk)?.spread
    return typeof s === 'number' ? s : null
  })
  return (
    <Card title="What trading costs you">
      <ul className="space-y-1.5 text-sm">
        <li>
          Fees this year: <strong className="tabular-nums">{formatEur(fees)}</strong>
          {perYear !== null && (
            <>
              {' '}
              — about <strong className={perYear > 0.005 ? 'text-amber-800 dark:text-amber-300' : ''}>{(perYear * 100).toFixed(2)}% of your money a year</strong>
              {perYear > 0.005 ? ': more than a broad ETF costs. Fewer, bigger orders (500 €+ is free) help.' : '.'}
            </>
          )}
        </li>
        <li>{m.text}</li>
      </ul>
      <p className="mt-2 text-xs text-slate-600 dark:text-zinc-400">The spread is not a fee you see: it is inside the price. Your fills are compared with the app's last price, so a single trade also contains that day's move; the average over 5 or more buys is what counts.</p>
    </Card>
  )
}

export function ReviewTab({ j, rows, total }: { j: Journal; rows: Map<string, ScreenerRow>; total: number }) {
  const [now] = useState(() => new Date())
  const month = now.toISOString().slice(0, 7)
  const b = behaviour(j, now)
  const q = decisionQuality(j)
  const book = fifo(j.trades)
  const thisMonth = j.trades.filter((t) => t.side !== 'dividend' && t.date.startsWith(month))
  const realizedMonth = book.realized.filter((r) => r.date.startsWith(month)).reduce((s, r) => s + r.gainEur, 0)
  const feesMonth = thisMonth.reduce((s, t) => s + t.feeEur, 0)
  const limit = j.rules.maxTradesPerMonth
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <CostsCard j={j} rows={rows} total={total} />
      <Card title="This month">
        <ul className="space-y-1 text-sm">
          <li>
            Trades: <strong>{thisMonth.length}</strong> (your limit {limit}) {thisMonth.length > limit ? <Badge tone="bad">over your limit</Badge> : <Badge tone="good">within your rules</Badge>}
          </li>
          <li>
            Fees: <strong className="tabular-nums">{formatEur(feesMonth)}</strong> · this year <strong className="tabular-nums">{formatEur(b.feesThisYear)}</strong>
          </li>
          <li>
            Sold: <strong className={`tabular-nums ${signClass(realizedMonth)}`}>{formatEurSigned(realizedMonth)}</strong>
          </li>
        </ul>
      </Card>
      <Card title="Your habits">
        <ul className="space-y-1.5 text-sm">
          <li>
            {b.chasedBuys ? <Badge tone="warn">Chasing</Badge> : <Badge tone="good">No chasing</Badge>} {b.chasedBuys} buy{b.chasedBuys === 1 ? '' : 's'} right after a big rise (+10% in a week or +25% in a month).
          </li>
          <li>
            {b.panicSells ? <Badge tone="warn">Panic</Badge> : <Badge tone="good">Calm</Badge>} {b.panicSells} sale{b.panicSells === 1 ? '' : 's'} right after a fall of 8% or more in a week.
          </li>
          {b.winnersHeldDays !== null && b.losersHeldDays !== null && (
            <li>
              {b.winnersHeldDays < b.losersHeldDays ? <Badge tone="warn">Sell winners early?</Badge> : <Badge tone="good">Balanced</Badge>} Sold winners after {Math.round(b.winnersHeldDays)} days on average, losers after {Math.round(b.losersHeldDays)}. Most investors sell winners too early and keep losers too long.
            </li>
          )}
          <li>
            Trades in the last 30 days: <strong>{b.tradesLast30}</strong>. The more people trade, the less they usually keep.
          </li>
        </ul>
      </Card>
      <Card title="Did ignoring warnings pay off?">
        {b.overrides === 0 ? (
          <p className="text-sm">You have not logged a trade against a warning.</p>
        ) : (
          <p className="text-sm">
            {b.overrides} trade{b.overrides === 1 ? '' : 's'} logged despite a warning. Average result once closed: <strong className={signClass(b.overrideAvg)}>{b.overrideAvg === null ? 'none closed yet' : formatEurSigned(b.overrideAvg)}</strong> vs <strong className={signClass(b.plainAvg)}>{b.plainAvg === null ? '—' : formatEurSigned(b.plainAvg)}</strong> without a warning.
          </p>
        )}
        <p className="mt-2 text-xs text-slate-600 dark:text-zinc-400">This measures whether the warnings help you; a warning you ignore every time is not doing its job.</p>
      </Card>
      <Card title="Decisions, not just results">
        {q.length === 0 ? (
          <p className="text-sm text-slate-600 dark:text-zinc-400">Appears once you have sold something. A good decision has a written reason, an "I'm wrong if" condition, a basis in the evidence and no ignored warning.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {(Object.keys(QUAD) as Quadrant[]).map((k) => {
              const items = q.filter((x) => x.quadrant === k)
              return (
                <li key={k}>
                  <Badge tone={QUAD[k].tone}>{items.length}</Badge> <strong>{QUAD[k].title}</strong>: {QUAD[k].text}
                  {items.length > 0 && <span className="block text-xs text-slate-600 dark:text-zinc-400">{items.map((x) => `${x.trade.ticker} ${formatEurSigned(x.gainEur, 0)}`).join(' · ')}</span>}
                </li>
              )
            })}
          </ul>
        )}
      </Card>
    </div>
  )
}
