import { Link } from 'react-router'
import { formatEur } from '../lib/costs'
import { formatPct, signClass } from '../lib/format'
import { COLORS, statusOf, type Universe } from '../lib/strategies'
import type { StrategiesFile, StrategyCard } from '../types'
import { Badge } from './ui'

export function TickerLink({ t }: { t: string }) {
  return (
    <Link to={`/stock/${encodeURIComponent(t)}`} className="font-semibold text-teal-700 underline-offset-2 hover:underline dark:text-teal-400">
      {t}
    </Link>
  )
}

export function Dot({ id, size = 'size-3' }: { id: string; size?: string }) {
  return <span className={`inline-block shrink-0 rounded-full ${size}`} style={{ background: COLORS[id] ?? 'var(--viz-axis)' }} aria-hidden="true" />
}

/** Two-way switch: the versions you can copy (finanzen.net zero) or the same rules on all stocks. */
export function UniverseSwitch({ u, set, f }: { u: Universe; set: (u: Universe) => void; f: StrategiesFile }) {
  const has = (f.strategies_all?.length ?? 0) > 0
  const opts: [Universe, string][] = [
    ['zero', 'Only finanzen.net zero'],
    ['all', 'All stocks'],
  ]
  return (
    <fieldset className="mb-3 min-w-0">
      <legend className="mb-1 text-sm font-medium">Stocks the strategies may buy</legend>
      <div className="inline-flex max-w-full rounded-xl bg-slate-100 p-1 dark:bg-zinc-800">
        {opts.map(([k, label]) => {
          const off = k === 'all' && !has
          return (
            <label
              key={k}
              className={`inline-flex min-h-11 items-center rounded-lg px-3 text-sm font-semibold has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-teal-600 ${
                u === k ? 'bg-white text-slate-900 shadow-xs dark:bg-zinc-950 dark:text-zinc-100' : 'text-slate-600 dark:text-zinc-400'
              } ${off ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
            >
              <input type="radio" name="stocks" value={k} checked={u === k} disabled={off} onChange={() => set(k)} className="sr-only" />
              {label}
            </label>
          )
        })}
      </div>
      <p className="mt-1 text-xs text-slate-600 dark:text-zinc-400">
        {u === 'zero' ? 'The versions you can copy: they only buy stocks you can buy on finanzen.net zero.' : 'The same rules on every stock the app covers, to compare. You may not be able to buy some of them on finanzen.net zero.'}
        {!has && ' The all-stocks versions start with the next daily update.'}
      </p>
    </fieldset>
  )
}

export function StatusBadge({ s }: { s: StrategyCard }) {
  const st = statusOf(s)
  return <Badge tone={st.tone}>{st.label}</Badge>
}

/** What the money is in, as small chips (plain text: used inside links). */
export function MoneyChips({ s, max = 4 }: { s: StrategyCard; max?: number }) {
  const st = statusOf(s)
  const chips = [
    ...s.holdings.map((h) => ({ key: `h-${h.ticker}`, prefix: '', ticker: h.ticker, extra: h.stock_move === null ? '' : formatPct(h.stock_move), cls: signClass(h.stock_move) })),
    ...s.pending.map((o) => ({
      key: `${o.side}-${o.ticker}`,
      prefix: o.side === 'buy' ? 'Buy' : 'Sell',
      ticker: o.ticker,
      extra: o.est_eur !== null && o.est_eur !== undefined ? `≈ ${formatEur(o.est_eur, 0)}` : '',
      cls: '',
    })),
  ]
  if (!chips.length) return <p className="mt-2 line-clamp-2 text-sm text-slate-600 dark:text-zinc-400">{st.text}</p>
  const shown = chips.slice(0, max)
  return (
    <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Stocks">
      {shown.map((c) => (
        <li key={c.key} className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-sm tabular-nums dark:bg-zinc-800">
          {c.prefix && <span className="text-xs text-slate-600 dark:text-zinc-400">{c.prefix}</span>}
          <span className="font-semibold">{c.ticker}</span>
          {c.extra && <span className={`text-xs ${c.cls || 'text-slate-600 dark:text-zinc-400'}`}>{c.extra}</span>}
        </li>
      ))}
      {chips.length > max && <li className="px-1 text-sm text-slate-600 dark:text-zinc-400">+{chips.length - max} more</li>}
    </ul>
  )
}
