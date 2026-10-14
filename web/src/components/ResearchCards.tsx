import { useSiteJson } from '../lib/data'
import { formatDateTime, formatPct, formatPctAbs } from '../lib/format'
import { Badge, Card } from './ui'

interface Stat {
  n: number
  mean: number
  median: number
  hit_rate: number
  worst5: number
  score: number
  avg_days?: number
  stopped_share?: number
  recovered_after_stop?: number | null
  filled?: number
}

export interface ResearchFile {
  protocol: string
  protocol_digest: string
  period: string
  model_version?: string | null
  signals: { model: number; control: number }
  exits: { model: Record<string, Stat>; control: Record<string, Stat>; halves: Record<string, Record<string, Stat>> }
  entries: { model: Record<string, Stat> }
  text: { exits: Record<string, string>; entries: Record<string, string> }
  decision: { exit: string; exit_robust: boolean; entry: string }
}

export interface ExperimentsFile {
  verified: boolean
  detail: string
  count: number
  experiments: { recorded_at: string; experiment: string; question: string; protocol_id: string; protocol_digest: string; period: string; status: string; code_commit: string | null }[]
}

const pct = (x: number | null | undefined) => (x === null || x === undefined ? '—' : formatPct(x, 1))

/** Sell rules and entry timing, tested once with a protocol fixed before the run. */
export function ResearchCard() {
  const res = useSiteJson<ResearchFile>('research.json')
  if (res.state !== 'ready') return null
  const r = res.data
  const rows = Object.entries(r.exits.model).sort((a, b) => b[1].score - a[1].score)
  const hold = r.exits.model.hold_63
  const win = r.exits.model[r.decision.exit]
  return (
    <Card title={`Sell rules and entry timing (tested once, ${r.period})`}>
      <p className="text-sm">
        Chosen by the rule fixed before the run: <strong>{r.text.exits[r.decision.exit] ?? r.decision.exit}</strong>
        {r.decision.exit_robust ? ' (best in both halves of the period)' : ''}. Entry: <strong>{r.text.entries[r.decision.entry] ?? r.decision.entry}</strong> (no other way of buying beat it by 0.2 points in both halves).
      </p>
      {hold && win && (
        <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:bg-amber-950/60 dark:text-amber-100">
          The trade-off, honestly: this rule cut the average of the worst 5% of trades from {pct(hold.worst5)} to {pct(win.worst5)}, but the average trade earned {pct(win.mean)} instead of {pct(hold.mean)} without a stop, and {formatPctAbs(win.recovered_after_stop ?? 0, 0)} of the stopped stocks were back above the buy price 21 days later. The protocol weighs deep losses heavily on purpose.
        </p>
      )}
      <div className="-mx-4 mt-2 overflow-x-auto px-4">
        <table className="w-full min-w-max text-sm tabular-nums">
          <caption className="sr-only">Sell rules on the model's top 2% each month, 63 trading days</caption>
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs text-slate-600 dark:border-zinc-700 dark:text-zinc-300">
              <th className="px-2 py-1.5">Rule</th>
              <th className="px-2 py-1.5 text-right">Average</th>
              <th className="px-2 py-1.5 text-right">Typical</th>
              <th className="px-2 py-1.5 text-right">Worst 5%</th>
              <th className="px-2 py-1.5 text-right">Days</th>
              <th className="px-2 py-1.5 text-right">Recovered after a stop</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-zinc-800">
            {rows.map(([k, v]) => (
              <tr key={k}>
                <th scope="row" className="max-w-56 px-2 py-1.5 text-left font-normal">
                  {r.text.exits[k] ?? k} {k === r.decision.exit && <Badge tone="good">chosen</Badge>}
                </th>
                <td className="px-2 py-1.5 text-right">{pct(v.mean)}</td>
                <td className="px-2 py-1.5 text-right">{pct(v.median)}</td>
                <td className="px-2 py-1.5 text-right">{pct(v.worst5)}</td>
                <td className="px-2 py-1.5 text-right">{v.avg_days?.toFixed(0) ?? '—'}</td>
                <td className="px-2 py-1.5 text-right">{v.recovered_after_stop === null || v.recovered_after_stop === undefined ? '—' : formatPctAbs(v.recovered_after_stop, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="mt-2 space-y-0.5 text-sm" aria-label="Entry methods">
        {Object.entries(r.entries.model).sort((a, b) => b[1].mean - a[1].mean).map(([k, v]) => (
          <li key={k} className="flex justify-between gap-3 tabular-nums">
            <span>{r.text.entries[k] ?? k}</span>
            <span>
              {pct(v.mean)} {v.filled !== undefined && v.filled < 1 ? `(bought in ${formatPctAbs(v.filled, 0)} of cases)` : ''}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-slate-500 dark:text-zinc-400">
        {r.signals.model.toLocaleString('en-US')} buys from the model's top 2% each month and {r.signals.control.toLocaleString('en-US')} random ones as a control, each followed 63 trading days; sells fill at the next open (overnight gaps count); costs included; only prices up to 31 Dec 2023. Protocol {r.protocol} ({r.protocol_digest}), model {r.model_version ?? '—'}. Free data lacks most delisted stocks, so real results would be somewhat worse.
      </p>
    </Card>
  )
}

/** Every experiment ever run, failures included, in a sealed log. */
export function ExperimentsCard() {
  const res = useSiteJson<ExperimentsFile>('experiments.json')
  if (res.state !== 'ready' || res.data.count === 0) return null
  const f = res.data
  return (
    <Card title="Experiment log" aside={<Badge tone={f.verified ? 'good' : 'bad'}>{f.verified ? `sealed · ${f.count}` : 'BROKEN'}</Badge>}>
      <p className="mb-2 text-sm text-slate-600 dark:text-zinc-400">Every research question the app tested, with its fixed protocol and code version. Failed tries stay here too: counting all tries keeps lucky results from looking like skill.</p>
      <ul className="divide-y divide-slate-100 text-sm dark:divide-zinc-800">
        {f.experiments.map((e) => (
          <li key={`${e.recorded_at}-${e.protocol_digest}`} className="py-2">
            <span className="font-medium">{e.experiment}</span> <Badge tone={e.status === 'done' ? 'good' : 'warn'}>{e.status}</Badge>
            <span className="block text-xs text-slate-500 dark:text-zinc-400">
              {formatDateTime(e.recorded_at)} · {e.period} · protocol {e.protocol_id} ({e.protocol_digest}){e.code_commit ? ` · code ${e.code_commit.slice(0, 7)}` : ''}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  )
}
