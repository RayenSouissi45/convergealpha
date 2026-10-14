import { useState } from 'react'
import { Link } from 'react-router'
import { formatEur, formatEurSigned, formatShares } from '../../lib/costs'
import { formatDay, formatPct, formatPrice, signClass } from '../../lib/format'
import { evidenceChanges, fifo, normalDay, thesis, type Journal, type Position } from '../../lib/journal'
import { holdingStatus, journalHoldings, throttle } from '../../lib/portfolio'
import { exposures, maxStocks, overlapWarnings, summary } from '../../lib/risk'
import { taxFrom, useTradeSettings } from '../../lib/settings'
import { taxOnGain } from '../../lib/taxes'
import { useSiteJson } from '../../lib/data'
import type { MarketFile, ScreenerRow } from '../../types'
import { LabelBadge } from '../LabelBadge'
import { Tip } from '../Tip'
import { Badge, Card } from '../ui'

const input = 'mt-1 min-h-11 w-full rounded-lg border border-slate-300 bg-white px-2 text-base dark:border-zinc-600 dark:bg-zinc-800'
const eur = (v: number | null, d = 2) => (v === null ? '—' : formatEur(v, d))

/** Cash waiting for a buy can earn interest in the meantime (call-money accounts follow the ECB
 * deposit rate). Shown so idle money is a choice, not an accident. */
function IdleCash({ cash }: { cash: number | null }) {
  const market = useSiteJson<MarketFile>('market.json')
  const rate = market.state === 'ready' ? market.data.macro?.ECBDFR : undefined
  if (!cash || cash < 100 || !rate) return null
  const year = (cash * rate.value) / 100
  return (
    <p className="mt-2 text-xs text-slate-600 dark:text-zinc-400">
      Your {formatEur(cash, 0)} in cash earns nothing at the broker. At the ECB deposit rate ({rate.value.toFixed(2)}%, {formatDay(rate.date)}), a free call-money account would pay about <strong>{formatEur(year, 0)} a year</strong> (before tax) while you wait for a buy.
    </p>
  )
}

function PositionCard({ p, rows, fx, j }: { p: Position; rows: Map<string, ScreenerRow>; fx: number | null; j: Journal }) {
  const [settings] = useTradeSettings()
  const holding = journalHoldings(j, fx).find((h) => h.ticker === p.ticker)
  const candidates = [...rows.values()].filter((r) => r.label === 'BUY' || r.label === 'STRONG BUY — TOP CONVICTION')
  const status = holding ? holdingStatus(holding, p.row, candidates) : null
  const day = normalDay(p.row)
  const checks = thesis(p)
  const changes = evidenceChanges(p)
  const tax = p.gainEur !== null ? taxOnGain(p.gainEur, taxFrom(settings)) : null
  const exit = p.buy?.snapshot?.planned_exit_usd ?? null
  return (
    <li className="rounded-xl border border-slate-200 bg-white p-3.5 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex items-start justify-between gap-3">
        <span className="min-w-0">
          <Link to={`/stock/${encodeURIComponent(p.ticker)}`} className="font-semibold text-teal-700 underline-offset-2 hover:underline dark:text-teal-400">
            {p.ticker}
          </Link>{' '}
          <span className="text-sm text-slate-600 dark:text-zinc-400">{typeof p.row?.name === 'string' ? p.row.name : ''}</span>
          <span className="block text-xs text-slate-600 dark:text-zinc-400">
            {formatShares(p.shares)} share{p.shares === 1 ? '' : 's'} since {formatDay(p.firstDate)} · cost {formatEur(p.costEur)} with fees
          </span>
        </span>
        <span className="shrink-0 text-right tabular-nums">
          <span className="block font-semibold">{eur(p.valueEur)}</span>
          <span className={`block text-sm ${signClass(p.gainEur)}`}>
            {p.gainEur === null ? '—' : `${formatEurSigned(p.gainEur)} (${formatPct(p.gainPct ?? 0)})`}
          </span>
        </span>
      </div>
      {status && (
        <div className="mt-2 text-sm">
          <LabelBadge label={status.label} />{' '}
          {status.reasons.length ? <span className="text-slate-700 dark:text-zinc-300">{status.reasons.join(' ')}</span> : <span className="text-slate-600 dark:text-zinc-400">No exit rule triggered.</span>}
          {status.actions.map((a) => (
            <p key={a} className="mt-1 text-xs text-slate-700 dark:text-zinc-300">
              {a}
            </p>
          ))}
        </div>
      )}
      {day && (
        <p className="mt-2 text-sm">
          Today <span className={`tabular-nums ${signClass(day.move)}`}>{formatPct(day.move)}</span>:{' '}
          {day.unusual ? (
            <Badge tone="warn">unusual for this stock</Badge>
          ) : (
            <span className="text-slate-600 dark:text-zinc-400">a normal move for this stock (usual ±{(day.usual * 100).toFixed(1)}% a day)</span>
          )}
          {day.unusual ? <span className="text-slate-600 dark:text-zinc-400"> (usual ±{(day.usual * 100).toFixed(1)}%). Check the news and your reasons before acting.</span> : null}
        </p>
      )}
      {checks.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-sm" aria-label={`${p.ticker}: I'm wrong if`}>
          {checks.map((c) => (
            <li key={c.key}>
              <Badge tone={c.broken === null ? 'neutral' : c.broken ? 'bad' : 'good'}>{c.broken === null ? '?' : c.broken ? 'Broken' : 'Holds'}</Badge> {c.text} <span className="text-xs text-slate-500 dark:text-zinc-400">({c.detail})</span>
            </li>
          ))}
        </ul>
      )}
      {p.buy?.reason && <p className="mt-2 text-xs text-slate-600 dark:text-zinc-400">Why you bought: {p.buy.reason}</p>}
      {changes.length > 0 && (
        <p className="mt-1 text-xs text-amber-800 dark:text-amber-300">
          Since you bought: {changes.map((c) => `${c.family} ${Math.round(c.then)} → ${Math.round(c.now)}`).join(', ')}.
        </p>
      )}
      <p className="mt-1 text-xs text-slate-600 dark:text-zinc-400">
        {exit !== null ? `Planned exit ${formatPrice(exit)}${fx ? ` ≈ ${formatEur(exit / fx)}` : ''}. ` : ''}
        {tax && tax.tax > 0 ? `If you sold today: about ${formatEur(tax.tax)} German tax on the gain.` : tax && (p.gainEur ?? 0) < 0 ? 'If you sold today: a loss you can set against stock gains this year.' : ''}
      </p>
      {p.buy?.fxGuessed && <p className="mt-1 text-xs text-amber-800 dark:text-amber-300">Moved from the old dollar portfolio at an assumed 1.10 $/€: check the price you paid in the Journal tab.</p>}
      <Link to={`/portfolio?tab=log&side=sell&t=${encodeURIComponent(p.ticker)}&shares=${p.shares}`} className="mt-2 inline-flex min-h-11 items-center text-sm font-medium text-teal-700 dark:text-teal-400">
        Log a sale
      </Link>
    </li>
  )
}

export function HoldingsTab({ j, setJ, ps, rows, fx }: { j: Journal; setJ: (j: Journal) => void; ps: Position[]; rows: Map<string, ScreenerRow>; fx: number | null }) {
  const [now] = useState(() => new Date())
  const holdings = ps.map((p) => ({ ticker: p.ticker, valueEur: p.valueEur ?? p.costEur, row: p.row }))
  const risk = summary(holdings, j.cashEur ?? 0)
  const exp = exposures(holdings)
  const overlap = overlapWarnings(holdings)
  const invested = risk.investedEur
  const total = risk.totalEur
  const brake = throttle({ version: 1, equity: total, peakEquity: Math.max(j.peakEur ?? total, total), holdings: [] })
  const year = String(now.getFullYear())
  const realizedYear = fifo(j.trades).realized.filter((r) => r.date.startsWith(year)).reduce((s, r) => s + r.gainEur, 0)
  const open = ps.reduce((s, p) => s + (p.gainEur ?? 0), 0)
  if (j.trades.length === 0) {
    return (
      <Card>
        <p className="text-sm">
          No trades yet. Log your real trades on finanzen.net zero and the app works out your holdings, results, German tax and how well you follow your own rules.
        </p>
        <Link to="/portfolio?tab=log" className="mt-3 inline-flex min-h-11 items-center rounded-xl bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 dark:bg-teal-600">
          Log your first trade
        </Link>
      </Card>
    )
  }
  return (
    <div className="grid gap-3">
      <div className="grid gap-3 lg:grid-cols-2">
        <Card title="Your money">
          <p className="text-3xl font-semibold tabular-nums">{formatEur(total)}</p>
          <dl className="mt-2 grid grid-cols-2 gap-2 text-sm">
            <div>
              <dt className="text-xs text-slate-600 dark:text-zinc-400">In stocks</dt>
              <dd className="font-semibold tabular-nums">{formatEur(invested)}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-600 dark:text-zinc-400">Open result</dt>
              <dd className={`font-semibold tabular-nums ${signClass(open)}`}>{formatEurSigned(open)}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-600 dark:text-zinc-400">Sold this year</dt>
              <dd className={`font-semibold tabular-nums ${signClass(realizedYear)}`}>{formatEurSigned(realizedYear)}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-600 dark:text-zinc-400">
                <Tip content="Your total 10% below its highest: new buys at half size. 15% below: no new buys. It protects you from digging deeper after losses.">Drawdown brake</Tip>
              </dt>
              <dd>
                <Badge tone={brake.factor === 1 ? 'good' : brake.factor > 0 ? 'warn' : 'bad'}>{brake.factor === 1 ? 'normal' : brake.factor > 0 ? 'half size' : 'no new buys'}</Badge>
              </dd>
            </div>
          </dl>
          <label className="mt-3 block text-xs text-slate-600 dark:text-zinc-400">
            Cash at the broker (€), optional
            <input className={input} type="number" inputMode="decimal" min={0} step={50} value={j.cashEur ?? ''} onChange={(e) => setJ({ ...j, cashEur: e.target.value === '' ? null : Math.max(0, Number(e.target.value)) })} />
          </label>
          <IdleCash cash={j.cashEur} />
        </Card>
        <Card title="Risk in plain numbers">
          <ul className="space-y-1.5 text-sm">
            <li>
              A bad month (1 in 10): about <strong className="tabular-nums">{formatEur(risk.badMonthEur, 0)}</strong> if every stock has its own bad month at once.
            </li>
            <li>
              The worst 1 in 20 months: on average <strong className="tabular-nums">−{formatEur(risk.cvarEur, 0)}</strong> ({(risk.cvar * 100).toFixed(1)}%); <strong className="tabular-nums">−{formatEur(risk.cvarCrashEur, 0)}</strong> if your stocks start falling together, as in a crash.
            </li>
            <li>
              Everything −20% in one day: <strong className="tabular-nums">{formatEur(risk.crash20Eur, 0)}</strong>. {risk.biggest} gapping −20% overnight (a stop cannot help): <strong className="tabular-nums">{formatEur(risk.gapEur, 0)}</strong>.
            </li>
            <li>
              Free orders: your money supports about <strong>{Number.isFinite(maxStocks(total, j.rules.minOrderEur)) ? maxStocks(total, j.rules.minOrderEur) : '∞'}</strong> positions of {formatEur(j.rules.minOrderEur, 0)} or more.
            </li>
          </ul>
          {overlap.length > 0 && (
            <ul className="mt-2 space-y-1 text-sm" aria-label="Hidden overlap">
              {overlap.map((w) => (
                <li key={w}>
                  <Badge tone="warn">Overlap</Badge> {w}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-xs text-slate-600 dark:text-zinc-400">
            Sectors: {exp.sectors.slice(0, 4).map((s) => `${s.name} ${Math.round(s.share * 100)}%`).join(' · ')}. A simple model (bell curve, assumed co-movement): real crashes can be worse.
          </p>
        </Card>
      </div>
      <ul className="grid gap-2.5 md:grid-cols-2" aria-label="Positions">
        {ps.map((p) => (
          <PositionCard key={p.ticker} p={p} rows={rows} fx={fx} j={j} />
        ))}
      </ul>
    </div>
  )
}
