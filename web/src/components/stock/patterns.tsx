import { formatPct } from '../../lib/format'
import { Tip } from '../Tip'
import { Badge, Card } from '../ui'

export interface Pattern {
  event: string
  n: number
  horizon: string
  mean_excess: number
  hit_rate: number
  q_value: number | null
  halves_ok: boolean
  holdout_ok: boolean | null
  scope: 'stock' | 'peers'
}

export interface PatternsSection {
  passed: Pattern[]
  likely_luck: Pattern[]
  tested: number
  method: string
}

function PatternList({ items }: { items: Pattern[] }) {
  return (
    <ul className="divide-y divide-slate-100 text-sm dark:divide-zinc-800">
      {items.map((p, i) => (
        <li key={i} className="py-2">
          <div className="font-medium">{p.event}</div>
          <div className="text-xs text-slate-600 dark:text-zinc-400">
            {p.n} events ({p.scope === 'peers' ? 'this stock and its peers' : 'this stock'}) · average {formatPct(p.mean_excess)} vs its own base rate over {p.horizon} ·{' '}
            {Math.round(p.hit_rate * 100)}% beat the base rate
            {p.q_value !== null && ` · false-discovery q = ${p.q_value.toFixed(2)}`}
          </div>
        </li>
      ))}
    </ul>
  )
}

export function PatternsCard({ p }: { p: PatternsSection }) {
  return (
    <Card title="Event patterns">
      <h3 className="mb-1 text-sm font-semibold">
        <Tip content="A pattern passes only with ≥ 20 events for this stock (or ≥ 200 across peers), a Benjamini–Hochberg false discovery rate ≤ 10% across every pattern tested, and the same sign in both halves of history and in the holdout.">
          Passed the luck test
        </Tip>
      </h3>
      {p.passed.length ? <PatternList items={p.passed} /> : <p className="text-sm text-slate-500">None. That is the usual outcome: most apparent patterns are luck.</p>}
      {p.likely_luck.length > 0 && (
        <details className="mt-3">
          <summary className="min-h-11 cursor-pointer text-sm font-medium">
            Looks like a pattern, but likely luck <Badge tone="neutral">{p.likely_luck.length}</Badge>
          </summary>
          <PatternList items={p.likely_luck} />
        </details>
      )}
      <p className="mt-2 text-xs text-slate-500 dark:text-zinc-400">
        {p.tested.toLocaleString('en-US')} patterns tested across all stocks. Measured from the first tradable price after each event. {p.method}
      </p>
    </Card>
  )
}
