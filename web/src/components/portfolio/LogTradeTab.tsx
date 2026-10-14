import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { feeFor, formatEur, formatEurSigned } from '../../lib/costs'
import { stockFile, useSiteJson } from '../../lib/data'
import { formatPct, signClass } from '../../lib/format'
import { coolingOff, fifo, newId, preTradeChecks, WRONG_IF, type Journal, type Position, type Snapshot, type Trade, type WrongIf } from '../../lib/journal'
import { beforeAfter } from '../../lib/risk'
import { feesFrom, taxFrom, useTradeSettings } from '../../lib/settings'
import { taxOnGain } from '../../lib/taxes'
import type { ScreenerRow } from '../../types'
import { Badge, Card } from '../ui'

const input = 'mt-1 min-h-11 w-full rounded-lg border border-slate-300 bg-white px-2 text-base dark:border-zinc-600 dark:bg-zinc-800'
const BASES: [NonNullable<Trade['basis']>, string][] = [
  ['label', 'An app label (BUY / WATCH / SELL)'],
  ['picks', 'Picks'],
  ['plan', 'The Plan page'],
  ['strategy', 'A paper strategy'],
  ['own', 'My own idea'],
]

interface StockJson {
  plan?: { planned_exit?: number; atr?: number } | null
}

function snapshotOf(row: ScreenerRow | undefined, stock: StockJson | null, fx: number | null): Snapshot {
  const n = (k: string) => (row && typeof row[k] === 'number' ? (row[k] as number) : null)
  return {
    label: typeof row?.label === 'string' ? row.label : null,
    f: ['f1', 'f2', 'f3', 'f4', 'f5', 'f6'].map(n),
    p_up_1m: n('p_up_1m'),
    p10_1m: n('p10_1m'),
    price_usd: n('price'),
    fx,
    atr_usd: stock?.plan?.atr ?? null,
    planned_exit_usd: stock?.plan?.planned_exit ?? null,
    ret_1w: n('ret_1w'),
    ret_1m: n('ret_1m'),
    opp: typeof row?.opp === 'string' ? row.opp : null,
    days_to_earnings: n('days_to_earnings'),
  }
}

export function LogTradeTab({ j, setJ, ps, rows, fx }: { j: Journal; setJ: (j: Journal) => void; ps: Position[]; rows: Map<string, ScreenerRow>; fx: number | null }) {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [settings] = useTradeSettings()
  const [side, setSide] = useState<Trade['side']>(params.get('side') === 'sell' ? 'sell' : 'buy')
  const [ticker, setTicker] = useState((params.get('t') ?? '').toUpperCase())
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [shares, setShares] = useState(params.get('shares') ?? '')
  const [price, setPrice] = useState('')
  const [fee, setFee] = useState('')
  const [withheld, setWithheld] = useState('')
  const [reason, setReason] = useState('')
  const [wrongIf, setWrongIf] = useState<WrongIf[]>(['label_sell', 'below_exit'])
  const [basis, setBasis] = useState<NonNullable<Trade['basis']>>('label')
  const [ack, setAck] = useState(false)
  const row = rows.get(ticker)
  const stock = useSiteJson<StockJson>(row ? stockFile(ticker) : null)
  const nowEur = typeof row?.price === 'number' && fx ? row.price / fx : null
  const priceEur = price !== '' ? Number(price) : (nowEur ?? 0)
  const n = side === 'dividend' ? 0 : Number(shares) || 0
  const amount = side === 'dividend' ? priceEur : n * priceEur
  const autoFee = side === 'dividend' ? 0 : feeFor(side === 'buy' ? feesFrom(settings).buy : feesFrom(settings).sell, amount, feesFrom(settings))
  const feeEur = fee !== '' ? Number(fee) : autoFee
  const planned = { side: side === 'sell' ? ('sell' as const) : ('buy' as const), ticker, amountEur: amount, row }
  const checks = side === 'dividend' || !ticker ? [] : preTradeChecks(planned, j, ps)
  const cool = side === 'dividend' || !ticker ? [] : coolingOff(planned, j)
  const failed = [...checks.filter((c) => !c.ok).map((c) => c.text), ...cool]
  const holdings = ps.map((p) => ({ ticker: p.ticker, valueEur: p.valueEur ?? p.costEur, row: p.row }))
  const ba = ticker && amount > 0 && side !== 'dividend' ? beforeAfter(holdings, j.cashEur, ticker, row, amount, side) : null
  const held = ps.find((p) => p.ticker === ticker)
  // A sale: first in, first out, at this price.
  let saleGain: number | null = null
  if (side === 'sell' && held && n > 0) {
    const book = fifo([...j.trades, { id: 'preview', date, side: 'sell', ticker, shares: Math.min(n, held.shares), priceEur, feeEur }])
    saleGain = book.realized.find((r) => r.tradeId === 'preview')?.gainEur ?? null
  }
  const saleTax = saleGain !== null ? taxOnGain(saleGain, taxFrom(settings)) : null
  const p10 = typeof row?.p10_1m === 'number' ? row.p10_1m : null
  const med = typeof row?.med_1m === 'number' ? row.med_1m : null
  const roundTrip = amount > 0 ? (feeEur + feeFor(feesFrom(settings).sell, amount, feesFrom(settings))) / amount : null
  const waitIsFine = side === 'buy' && ticker !== '' && (failed.length > 0 || (med !== null && roundTrip !== null && med <= roundTrip) || row?.opp === 'red')
  const valid = ticker.length > 0 && priceEur > 0 && (side === 'dividend' || n > 0) && (failed.length === 0 || ack) && (side !== 'sell' || (held !== undefined && n <= held.shares + 1e-9))

  const save = () => {
    if (!valid) return
    const t: Trade = {
      id: newId(),
      date,
      side,
      ticker,
      shares: n,
      priceEur,
      feeEur,
      ...(side === 'dividend' ? { withheldEur: Number(withheld) || 0 } : {}),
      reason: reason.trim() || undefined,
      ...(side === 'buy' ? { wrongIf } : {}),
      basis,
      snapshot: snapshotOf(row, stock.state === 'ready' ? stock.data : null, fx),
      ...(failed.length ? { overrode: failed } : {}),
    }
    setJ({ ...j, trades: [...j.trades, t] })
    navigate('/portfolio?tab=holdings')
  }

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <Card title="Log a trade you made on finanzen.net zero">
        <fieldset className="flex flex-wrap gap-1.5 text-sm">
          <legend className="sr-only">Kind of trade</legend>
          {(['buy', 'sell', 'dividend'] as const).map((s) => (
            <label key={s} className={`inline-flex min-h-11 cursor-pointer items-center rounded-full border px-3 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-teal-600 ${side === s ? 'border-teal-700 bg-teal-700 text-white dark:border-teal-500 dark:bg-teal-600' : 'border-slate-300 dark:border-zinc-600'}`}>
              <input type="radio" name="side" className="sr-only" checked={side === s} onChange={() => setSide(s)} />
              {s === 'buy' ? 'Buy' : s === 'sell' ? 'Sell' : 'Dividend'}
            </label>
          ))}
        </fieldset>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <label className="text-sm font-medium">
            Ticker
            <input className={input} value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase().trim())} placeholder="e.g. MSFT" autoCapitalize="characters" />
          </label>
          <label className="text-sm font-medium">
            Date
            <input className={input} type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          {side !== 'dividend' ? (
            <label className="text-sm font-medium">
              Shares
              <input className={input} type="number" inputMode="decimal" min={0} step={1} value={shares} onChange={(e) => setShares(e.target.value)} />
            </label>
          ) : (
            <label className="text-sm font-medium">
              US tax withheld (€)
              <input className={input} type="number" inputMode="decimal" min={0} step={0.01} value={withheld} onChange={(e) => setWithheld(e.target.value)} />
            </label>
          )}
          <label className="text-sm font-medium">
            {side === 'dividend' ? 'Dividend before tax (€)' : 'Price per share (€)'}
            <input className={input} type="number" inputMode="decimal" min={0} step={0.01} value={price} placeholder={nowEur !== null && side !== 'dividend' ? nowEur.toFixed(2) : ''} onChange={(e) => setPrice(e.target.value)} />
          </label>
          {side !== 'dividend' && (
            <label className="text-sm font-medium">
              Fee (€)
              <input className={input} type="number" inputMode="decimal" min={0} step={0.5} value={fee} placeholder={autoFee.toFixed(2)} onChange={(e) => setFee(e.target.value)} />
            </label>
          )}
        </div>
        {side !== 'dividend' && (
          <>
            <label className="mt-3 block text-sm font-medium">
              Why? (one sentence)
              <textarea className={`${input} min-h-20 py-2`} value={reason} onChange={(e) => setReason(e.target.value)} placeholder={side === 'buy' ? 'e.g. BUY label, insiders bought, 4 strong families' : 'e.g. my reason broke: guidance cut'} />
            </label>
            <label className="mt-2 block text-sm font-medium">
              Based on
              <select className={input} value={basis} onChange={(e) => setBasis(e.target.value as NonNullable<Trade['basis']>)}>
                {BASES.map(([k, l]) => (
                  <option key={k} value={k}>
                    {l}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
        {side === 'buy' && (
          <fieldset className="mt-3 text-sm">
            <legend className="font-medium">I'm wrong if… (the app checks these every day)</legend>
            {(Object.keys(WRONG_IF) as WrongIf[]).map((k) => (
              <label key={k} className="flex min-h-11 items-center gap-2">
                <input type="checkbox" className="size-5 accent-teal-700" checked={wrongIf.includes(k)} onChange={(e) => setWrongIf(e.target.checked ? [...wrongIf, k] : wrongIf.filter((x) => x !== k))} />
                {WRONG_IF[k]}
              </label>
            ))}
          </fieldset>
        )}
      </Card>
      <div className="grid content-start gap-3">
        {ticker && side !== 'dividend' && (
          <Card title="Before you trade">
            <p className="text-sm tabular-nums">
              {side === 'buy' ? 'Buying' : 'Selling'} {n || 0} × {formatEur(priceEur)} = <strong>{formatEur(amount)}</strong>, fee {formatEur(feeEur)}
              {amount > 0 && amount < 500 && settings.feeRule === 'zero' ? ' (orders of 500 € or more are free)' : ''}.
            </p>
            {side === 'buy' && p10 !== null && amount > 0 && (
              <p className="mt-1 text-sm">
                In 1 month out of 10 this stock fell {formatPct(p10)} or more with nothing wrong: with this order that is <strong className="tabular-nums">{formatEur(amount * p10, 0)}</strong>. If that would scare you, buy less.
              </p>
            )}
            {saleGain !== null && (
              <p className="mt-1 text-sm">
                This sale's result (first shares bought sold first): <span className={`font-semibold tabular-nums ${signClass(saleGain)}`}>{formatEurSigned(saleGain)}</span>
                {saleTax && saleTax.tax > 0 ? `, about ${formatEur(saleTax.tax)} German tax` : saleGain < 0 ? ', a loss you can set against stock gains this year' : ''}.
              </p>
            )}
            {side === 'sell' && !held && <p className="mt-1 text-sm text-red-700 dark:text-red-400">You hold no {ticker} in the journal.</p>}
            {side === 'sell' && held && n > held.shares + 1e-9 && <p className="mt-1 text-sm text-red-700 dark:text-red-400">You hold only {held.shares} shares.</p>}
            <ul className="mt-2 space-y-1 text-sm" aria-label="Checks">
              {checks.map((c) => (
                <li key={c.text}>
                  <Badge tone={c.ok ? 'good' : c.rule ? 'bad' : 'warn'}>{c.ok ? 'OK' : c.rule ? 'Your rule' : 'Warning'}</Badge> {c.text}
                </li>
              ))}
              {cool.map((c) => (
                <li key={c}>
                  <Badge tone="warn">Cool off</Badge> {c}
                </li>
              ))}
            </ul>
            {ba && (
              <p className="mt-2 text-xs text-slate-600 dark:text-zinc-400">
                Worst 1 in 20 months for your whole portfolio: −{formatEur(ba.before.cvarEur, 0)} now → −{formatEur(ba.after.cvarEur, 0)} after this trade; {ba.positionsBefore} → {ba.positionsAfter} positions.
              </p>
            )}
            {waitIsFine && <p className="mt-2 rounded-lg bg-slate-100 px-3 py-2 text-sm dark:bg-zinc-800">Doing nothing is a valid choice here: {failed.length ? 'it breaks your rules or a warning applies' : row?.opp === 'red' ? 'it looks like hype' : 'the expected gain does not cover the costs'}.</p>}
          </Card>
        )}
        <Card>
          {failed.length > 0 && (
            <label className="mb-2 flex min-h-11 items-center gap-2 text-sm">
              <input type="checkbox" className="size-5 accent-teal-700" checked={ack} onChange={(e) => setAck(e.target.checked)} />
              I read the warnings and still want to log it (the journal remembers, so you can see later whether ignoring warnings paid off)
            </label>
          )}
          <button type="button" disabled={!valid} onClick={save} className="inline-flex min-h-12 items-center rounded-xl bg-teal-700 px-4 text-base font-semibold text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-teal-600">
            Save to my journal
          </button>
          <p className="mt-2 text-xs text-slate-600 dark:text-zinc-400">Saved only in this browser. The app never places orders: you trade on finanzen.net zero yourself, then log it here.</p>
        </Card>
      </div>
    </div>
  )
}
