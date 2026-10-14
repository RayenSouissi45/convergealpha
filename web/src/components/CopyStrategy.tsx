import { useState } from 'react'
import { Link } from 'react-router'
import { formatEur, formatShares } from '../lib/costs'
import { newId, sortTrades, useJournal, type Trade } from '../lib/journal'
import { copyPlan } from '../lib/orderHelp'
import type { StrategyCard } from '../types'
import { Badge, Card } from './ui'

/** Copy a strategy with your own money, or first as paper trades in your journal. */
export function CopyStrategy({ s, fallbackFx }: { s: StrategyCard; fallbackFx?: number | null }) {
  const [amount, setAmount] = useState(s.capital ?? 5000)
  const [journal, setJournal] = useJournal()
  const [now] = useState(() => new Date())
  const [done, setDone] = useState(false)
  const fx = s.fx_rate ?? fallbackFx ?? null
  if (!fx) return null
  const { lines, cashEur } = copyPlan(s, amount, fx)
  const buys = s.pending.filter((o) => o.side === 'buy')
  const small = lines.filter((l) => l.fee > 0)
  const paperTrade = () => {
    const day = now.toISOString().slice(0, 10)
    const trades: Trade[] = lines.map((l) => ({
      id: newId(),
      date: day,
      side: 'buy',
      ticker: l.ticker,
      shares: l.shares,
      priceEur: Math.round(l.priceEur * 100) / 100,
      feeEur: l.fee,
      reason: `Copied from the strategy "${s.name}" (version ${s.version}) as paper trades.`,
      basis: 'strategy',
      paper: true,
      snapshot: { price_usd: s.holdings.find((h) => h.ticker === l.ticker)?.close_usd ?? null, fx },
    }))
    setJournal({ ...journal, trades: sortTrades([...journal.trades, ...trades]) })
    setDone(true)
  }
  return (
    <Card title="Copy it with your money">
      {s.universe === 'all' && <p className="mb-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:bg-amber-950/60 dark:text-amber-100">This is the all-stocks version: some of its stocks may not be on finanzen.net zero. Copy the finanzen.net zero version instead.</p>}
      <label className="block text-sm font-medium">
        Your amount in euros
        <input type="number" inputMode="decimal" min={1} step={100} value={amount} onChange={(e) => setAmount(Number(e.target.value) || 0)} className="mt-1 min-h-11 w-full rounded-lg border border-slate-300 bg-white px-2 text-base dark:border-zinc-600 dark:bg-zinc-800" />
      </label>
      {lines.length === 0 ? (
        <p className="mt-2 text-sm text-slate-600 dark:text-zinc-400">{s.holdings.length ? 'Your amount is too small for one share of its holdings.' : 'It holds no stocks right now.'}</p>
      ) : (
        <ul className="mt-2 space-y-1 text-sm" aria-label="Orders to copy it">
          {lines.map((l) => (
            <li key={l.ticker} className="flex flex-wrap items-baseline justify-between gap-x-3 tabular-nums">
              <span>
                Buy <strong>{formatShares(l.shares)} × {l.ticker}</strong> ≈ {formatEur(l.orderEur, 0)} <span className="text-xs text-slate-600 dark:text-zinc-400">({Math.round(l.weight * 100)}% of the strategy)</span>
              </span>
              <span className="text-xs">
                limit {formatEur(l.limit)} · {l.fee ? <Badge tone="warn">1 € fee</Badge> : <Badge tone="good">free</Badge>}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-xs text-slate-600 dark:text-zinc-400">
        Left as cash: about {formatEur(cashEur, 0)} (whole shares).{small.length ? ` ${small.length} order${small.length === 1 ? ' is' : 's are'} under 500 € and pay 1 €: a larger amount makes every order free.` : ''}
        {buys.length ? ` It also buys ${buys.map((o) => o.ticker).join(', ')} at the next open: add those then with the same share of your money.` : ''} The strategy bought at earlier prices, so your result will differ from its line. The best moment to copy is when it places new orders.
      </p>
      {lines.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button type="button" onClick={paperTrade} disabled={done} className="inline-flex min-h-11 items-center rounded-xl border border-teal-700 px-3 text-sm font-semibold text-teal-800 hover:bg-teal-50 disabled:opacity-60 dark:border-teal-500 dark:text-teal-300 dark:hover:bg-teal-950">
            {done ? 'Added as paper trades' : 'Practice first: add as paper trades'}
          </button>
          {done && (
            <Link to="/portfolio?paper=1" className="text-sm text-teal-700 underline dark:text-teal-400">
              See them in Portfolio (paper)
            </Link>
          )}
        </div>
      )}
      <p className="mt-2 text-xs text-slate-600 dark:text-zinc-400">Paper money only here: nothing is ever sent to a broker.</p>
    </Card>
  )
}
