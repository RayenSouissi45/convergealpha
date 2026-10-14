import { useRef, useState } from 'react'
import { formatEur, formatShares } from '../../lib/costs'
import { formatDay } from '../../lib/format'
import { fifo, parseJournal, processScore, toCsv, type Journal } from '../../lib/journal'
import { Badge, Card } from '../ui'

const btn = 'inline-flex min-h-11 items-center rounded-lg border border-slate-300 px-3 text-sm font-medium hover:bg-slate-50 dark:border-zinc-600 dark:hover:bg-zinc-800'

function download(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function JournalTab({ j, setJ }: { j: Journal; setJ: (j: Journal) => void }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const book = fifo(j.trades)
  const gainOf = new Map(book.realized.map((r) => [r.tradeId, r.gainEur]))
  const [today] = useState(() => new Date().toISOString().slice(0, 10))
  const importFile = async (f: File) => {
    try {
      const next = parseJournal(JSON.parse(await f.text()) as unknown)
      setJ(next)
      setMsg(`Imported ${next.trades.length} trades.`)
    } catch (e) {
      setMsg(`Could not import: ${e instanceof Error ? e.message : String(e)}`)
    }
  }
  return (
    <div className="grid gap-3">
      <Card>
        <div className="flex flex-wrap gap-2">
          <button type="button" className={btn} onClick={() => download(`journal-${today}.json`, JSON.stringify(j, null, 1), 'application/json')}>
            Save a copy (file)
          </button>
          <button type="button" className={btn} onClick={() => download(`journal-${today}.csv`, toCsv(j), 'text/csv')}>
            Export for the tax office (CSV)
          </button>
          <button type="button" className={btn} onClick={() => fileRef.current?.click()}>
            Load a copy
          </button>
          <input ref={fileRef} type="file" accept="application/json" className="hidden" onChange={(e) => e.target.files?.[0] && void importFile(e.target.files[0])} />
        </div>
        {msg && (
          <p className="mt-2 text-sm" role="status">
            {msg}
          </p>
        )}
        {book.problems.map((p) => (
          <p key={p} className="mt-2 text-sm text-red-700 dark:text-red-400">
            {p}: check this sale or add the missing buy.
          </p>
        ))}
      </Card>
      {j.trades.length === 0 ? (
        <Card>
          <p className="text-sm text-slate-600 dark:text-zinc-400">No trades yet.</p>
        </Card>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white dark:divide-zinc-800 dark:border-zinc-800 dark:bg-zinc-900" aria-label="Trades">
          {[...j.trades].reverse().map((t) => {
            const ps = processScore(t)
            const g = gainOf.get(t.id)
            return (
              <li key={t.id} className="px-3.5 py-2.5 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="inline-flex flex-wrap items-center gap-2">
                    <span className="text-xs text-slate-500 dark:text-zinc-400">{formatDay(t.date)}</span>
                    <Badge tone={t.side === 'buy' ? 'good' : t.side === 'sell' ? 'neutral' : 'warn'}>{t.side.toUpperCase()}</Badge>
                    <strong>{t.ticker}</strong>
                    {t.side !== 'dividend' && (
                      <span className="tabular-nums">
                        {formatShares(t.shares)} × {formatEur(t.priceEur)}
                        {t.feeEur > 0 ? ` + ${formatEur(t.feeEur)} fee` : ''}
                      </span>
                    )}
                    {t.side === 'dividend' && <span className="tabular-nums">{formatEur(t.priceEur)}</span>}
                  </span>
                  <span className="inline-flex items-center gap-2">
                    {g !== undefined && <span className="tabular-nums">{g >= 0 ? '+' : ''}{formatEur(g)}</span>}
                    <button
                      type="button"
                      className="min-h-9 rounded-md px-2 text-xs text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950"
                      onClick={() => {
                        if (window.confirm(`Delete this ${t.side} of ${t.ticker} on ${t.date}?`)) setJ({ ...j, trades: j.trades.filter((x) => x.id !== t.id) })
                      }}
                    >
                      Delete
                    </button>
                  </span>
                </div>
                {t.reason && <p className="mt-0.5 text-xs text-slate-600 dark:text-zinc-400">Why: {t.reason}</p>}
                {t.side !== 'dividend' && !ps.good && <p className="mt-0.5 text-xs text-amber-800 dark:text-amber-300">Missing: {ps.missing.join(', ')}.</p>}
                {t.fxGuessed && <p className="mt-0.5 text-xs text-amber-800 dark:text-amber-300">Price converted from dollars at an assumed 1.10 $/€: delete and log it again with the real price if it is wrong.</p>}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
