import { useRef, useState } from 'react'
import { Link } from 'react-router'
import { LabelBadge } from '../components/stock/decision'
import { Tip } from '../components/Tip'
import { Badge, Card, PageHeader, Row } from '../components/ui'
import { formatMoney, formatPct, formatPctAbs, formatPrice, signClass } from '../lib/format'
import { holdingStatus, parsePortfolio, throttle, usePortfolio, type Holding } from '../lib/portfolio'
import { useScreener } from '../lib/screener'
import type { ScreenerRow } from '../types'

const input = 'min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-zinc-600 dark:bg-zinc-800'
const btn = 'min-h-11 rounded-lg border border-slate-300 px-3 text-sm font-medium dark:border-zinc-600'

function AddHolding({ onAdd, rows }: { onAdd: (h: Holding) => void; rows: Map<string, ScreenerRow> }) {
  const [ticker, setTicker] = useState('')
  const [shares, setShares] = useState('')
  const [price, setPrice] = useState('')
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10))
  const t = ticker.trim().toUpperCase()
  const known = rows.has(t)
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const sh = Number(shares)
    const px = Number(price)
    if (!t || !(sh > 0) || !(px > 0)) return
    const row = rows.get(t)
    const atr = typeof row?.atr_pct === 'number' && typeof row.price === 'number' ? row.atr_pct * row.price : null
    onAdd({ ticker: t, shares: sh, entryPrice: px, entryDate: date, exitLevel: atr ? Math.max(px - 2 * atr, 0.92 * px) : 0.92 * px, atrAtEntry: atr, p25MonthAtEntry: null })
    setTicker('')
    setShares('')
    setPrice('')
  }
  return (
    <form onSubmit={submit} className="grid gap-2 sm:grid-cols-5">
      <label className="text-xs">
        Ticker
        <input className={input} value={ticker} onChange={(e) => setTicker(e.target.value)} autoCapitalize="characters" required aria-invalid={!!t && !known} />
        {t && !known && <span className="text-xs text-amber-700 dark:text-amber-400">Not in today’s stock list</span>}
      </label>
      <label className="text-xs">
        Shares
        <input className={input} type="number" inputMode="decimal" min="0" step="any" value={shares} onChange={(e) => setShares(e.target.value)} required />
      </label>
      <label className="text-xs">
        Entry price
        <input className={input} type="number" inputMode="decimal" min="0" step="any" value={price} onChange={(e) => setPrice(e.target.value)} required />
      </label>
      <label className="text-xs">
        Entry date
        <input className={input} type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
      </label>
      <div className="flex items-end">
        <button type="submit" className="min-h-11 w-full rounded-lg bg-slate-900 px-4 text-sm font-medium text-white dark:bg-zinc-100 dark:text-zinc-900">
          Add
        </button>
      </div>
    </form>
  )
}

export default function Portfolio() {
  const [p, setP] = usePortfolio()
  const screener = useScreener()
  const rows = screener.state === 'ready' ? screener.data.byTicker : new Map<string, ScreenerRow>()
  const candidates = screener.state === 'ready' ? screener.data.rows.filter((r) => r.eligible === true && (r.label === 'BUY' || r.label === 'STRONG BUY — TOP CONVICTION')) : []
  const fileRef = useRef<HTMLInputElement>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const t = throttle(p)
  const statuses = p.holdings.map((h) => ({ h, s: holdingStatus(h, rows.get(h.ticker), candidates), row: rows.get(h.ticker) }))
  const invested = statuses.reduce((s, x) => s + (x.s.value ?? 0), 0)
  const openRisk = statuses.reduce((s, x) => s + (x.s.openRisk ?? 0), 0)
  const eq = p.equity
  const bySector = new Map<string, number>()
  const byCluster = new Map<string, number>()
  for (const x of statuses) {
    const sec = String(x.row?.sector ?? 'Unknown')
    bySector.set(sec, (bySector.get(sec) ?? 0) + (x.s.value ?? 0))
    if (x.row?.cluster !== null && x.row?.cluster !== undefined) {
      const c = String(x.row.cluster)
      byCluster.set(c, (byCluster.get(c) ?? 0) + (x.s.value ?? 0))
    }
  }

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(p, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `convergealpha-portfolio-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(a.href)
  }
  const importJson = async (f: File) => {
    try {
      setP(parsePortfolio(JSON.parse(await f.text()) as unknown))
      setMsg('Portfolio imported.')
    } catch {
      setMsg('That file is not a ConvergeAlpha portfolio export.')
    }
  }

  return (
    <>
      <PageHeader title="My portfolio" subtitle="Stored only in this browser. Nothing is uploaded." />
      <div className="grid gap-3 lg:grid-cols-3">
        <Card title="Account">
          <label className="block text-sm font-medium">
            Account value (cash + positions)
            <input
              className={`${input} mt-1`}
              type="number"
              inputMode="decimal"
              min="0"
              defaultValue={eq ?? ''}
              onBlur={(e) => {
                const v = Number(e.target.value)
                setP({ ...p, equity: v > 0 ? v : null })
              }}
              placeholder="e.g. 10000"
            />
          </label>
          <dl className="mt-2">
            <Row label="Peak account value">{p.peakEquity !== null ? formatMoney(p.peakEquity) : '—'}</Row>
            <Row label={<Tip content="−10% from the peak halves the risk of new positions; −15% stops new buys.">Drawdown throttle</Tip>}>
              <Badge tone={t.factor === 1 ? 'good' : t.factor > 0 ? 'warn' : 'bad'}>{t.drawdown !== null ? `${formatPct(t.drawdown)} · ` : ''}{t.factor === 1 ? 'normal' : t.factor > 0 ? 'half risk' : 'no new buys'}</Badge>
            </Row>
            <Row label="Positions">{`${p.holdings.length} of at most 10`}</Row>
            <Row label="Invested">{formatMoney(invested)}{eq ? ` (${formatPctAbs(invested / eq, 0)})` : ''}</Row>
            <Row label={<Tip content="Sum over positions of shares × (price − planned exit level). The limit is 6% of the account.">Open risk</Tip>}>
              {formatMoney(openRisk)}
              {eq ? <Badge tone={openRisk / eq <= 0.06 ? 'good' : 'bad'}>{formatPctAbs(openRisk / eq, 1)} of 6% max</Badge> : null}
            </Row>
          </dl>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" className={btn} onClick={exportJson}>Export JSON</button>
            <button type="button" className={btn} onClick={() => fileRef.current?.click()}>Import JSON</button>
            <input ref={fileRef} type="file" accept="application/json" className="hidden" onChange={(e) => e.target.files?.[0] && void importJson(e.target.files[0])} />
          </div>
          {msg && <p className="mt-2 text-sm" role="status">{msg}</p>}
        </Card>
        <Card title="Exposure" className="lg:col-span-2">
          {bySector.size === 0 ? (
            <p className="text-sm text-slate-500">No holdings yet.</p>
          ) : (
            <ul className="space-y-1.5 text-sm">
              {[...bySector.entries()].sort((a, b) => b[1] - a[1]).map(([sec, v]) => {
                const share = eq ? v / eq : null
                return (
                  <li key={sec} className="flex items-center justify-between gap-2">
                    <span>{sec}</span>
                    <span className="tabular-nums">
                      {formatMoney(v)} {share !== null && <Badge tone={share <= 0.25 ? 'good' : 'bad'}>{formatPctAbs(share, 0)} of 25% max</Badge>}
                    </span>
                  </li>
                )
              })}
              {[...byCluster.entries()].filter(([, v]) => eq && v / eq > 0.2).map(([c, v]) => (
                <li key={c}>
                  <Badge tone="bad">Correlated group {c}: {formatPctAbs(v / (eq ?? 1), 0)} (limit 20%)</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Holdings" className="lg:col-span-3">
          <AddHolding rows={rows} onAdd={(h) => setP({ ...p, holdings: [...p.holdings.filter((x) => x.ticker !== h.ticker), h] })} />
          {statuses.length > 0 && (
            <ul className="mt-3 divide-y divide-slate-100 dark:divide-zinc-800">
              {statuses.map(({ h, s }) => (
                <li key={h.ticker} className="py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <Link to={`/stock/${encodeURIComponent(h.ticker)}`} className="text-base font-semibold underline">{h.ticker}</Link>{' '}
                      <span className="text-sm text-slate-500">
                        {h.shares} @ {formatPrice(h.entryPrice)} since {h.entryDate} · {s.tradingDaysHeld} trading days
                      </span>
                    </div>
                    <LabelBadge label={s.label} />
                  </div>
                  <div className="mt-1 flex flex-wrap gap-x-4 text-sm tabular-nums">
                    <span>Price {s.price !== null ? formatPrice(s.price) : '—'}</span>
                    <span className={signClass(s.ret)}>Return {s.ret !== null ? formatPct(s.ret) : '—'}</span>
                    <span>Value {s.value !== null ? formatMoney(s.value) : '—'}</span>
                    <span>Planned exit {h.exitLevel !== null ? formatPrice(h.exitLevel) : '—'}</span>
                  </div>
                  {s.reasons.length > 0 && <p className="mt-1 text-sm text-slate-700 dark:text-zinc-300">{s.reasons.join(' ')}</p>}
                  {s.actions.map((a) => (
                    <p key={a} className="mt-1 text-sm text-teal-800 dark:text-teal-300">→ {a}</p>
                  ))}
                  <button type="button" className="mt-1 min-h-11 text-sm text-red-700 underline dark:text-red-400" onClick={() => setP({ ...p, holdings: p.holdings.filter((x) => x.ticker !== h.ticker) })}>
                    Remove {h.ticker}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-xs text-slate-500 dark:text-zinc-400">
            HOLD = no exit rule triggered. ROTATE = after 21 trading days below its own 1-month 25th-percentile forecast while a candidate is at least 1.5× faster.
            SELL / RISK WARNING = planned exit hit, risk event, evidence decay (3 of 6 families below 50), data failure, or the 60-day time stop.
            To get daily alerts and refreshed data for your holdings, list their tickers in the HOLDINGS repository variable (SETUP.md).
          </p>
        </Card>
      </div>
    </>
  )
}
