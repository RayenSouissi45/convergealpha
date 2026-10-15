import { Link } from 'react-router'
import { formatEur } from '../lib/costs'
import { formatDay, formatPct, signClass } from '../lib/format'
import { COLORS, localTime, nyTime, statusOf, type Universe, type Version } from '../lib/strategies'
import type { StrategiesFile, StrategiesLiveFile, StrategyCard } from '../types'
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

/** Version 2 (newest rules) or version 1 (the first rules, still running for comparison). */
export function VersionSwitch({ v, set, f }: { v: Version; set: (v: Version) => void; f: StrategiesFile }) {
  const x = f.v2
  if (!x) return null
  const short = (d: string) => formatDay(d).replace(/, \d{4}$/, '')
  const opts: [Version, string, string, boolean][] = [
    [2, 'Version 2', `${formatEur(x.capital, 0)} · from ${short(x.start)}`, !x.started],
    [1, 'Version 1', `${formatEur(f.capital, 0)} · from ${short(f.start)}`, false],
  ]
  return (
    <fieldset className="mb-3 min-w-0">
      <legend className="mb-1 text-sm font-medium">Rules version</legend>
      <div className="inline-flex max-w-full rounded-xl bg-slate-100 p-1 dark:bg-zinc-800">
        {opts.map(([k, label, sub, off]) => (
          <label
            key={k}
            className={`inline-flex min-h-11 flex-col justify-center rounded-lg px-3 py-1 text-sm font-semibold has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-teal-600 ${
              v === k ? 'bg-white text-slate-900 shadow-xs dark:bg-zinc-950 dark:text-zinc-100' : 'text-slate-600 dark:text-zinc-400'
            } ${off ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
          >
            <input type="radio" name="version" value={k} checked={v === k} disabled={off} onChange={() => set(k)} className="sr-only" />
            {label}
            <span className="text-xs font-normal">{sub}</span>
          </label>
        ))}
      </div>
      <p className="mt-1 text-xs text-slate-600 dark:text-zinc-400">
        {v === 2
          ? 'The newest rules: free orders from 500 € on finanzen.net zero, the sell rule that tested best on 2016–2023 (−5% stop, +6% take profit; see Validation), up to 8 stocks, the ECB exchange rate.'
          : 'The first rules, still running unchanged so both versions can be compared live. Neither is ever edited.'}
        {!x.started && ` Version 2 starts at the close of ${formatDay(x.start)}.`}
      </p>
    </fieldset>
  )
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

/** "LIVE · prices at 11:05 AM New York": the values are today's estimate, not the sealed record. */
export function LiveLine({ live }: { live: StrategiesLiveFile }) {
  const at = live.prices_at ?? live.generated_at
  const open = live.market === 'open'
  const late = open && (live.checked_at ?? Date.parse(at)) - Date.parse(at) > 10 * 60_000
  const when = `${nyTime(at)} New York (${localTime(at)} your time)`
  return (
    <p className="mb-3 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-950 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-100" role="status">
      <span className="inline-flex items-center gap-1.5 font-semibold">
        <span className={`size-2 rounded-full bg-emerald-500 ${open && !late ? 'motion-safe:animate-pulse' : ''}`} aria-hidden="true" />
        {open ? 'LIVE' : 'Today, after the close'}
      </span>
      <span>
        {!open
          ? `Estimated at ${when}.`
          : late
            ? `Last update at ${when}; the next one is late.`
            : `Prices at ${when}. This page updates by itself every minute; prices can be up to 15 minutes old.`}{' '}
        The official numbers are written after the close.
      </span>
    </p>
  )
}
