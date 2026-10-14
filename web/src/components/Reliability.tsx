import { useSiteJson } from '../lib/data'
import type { Health, IncidentsFile } from '../types'
import { Badge, Card, type Tone } from './ui'

const KIND_TEXT: Record<string, string> = {
  impossible: 'impossible price',
  jump: 'jump without a split',
  frozen: 'frozen price',
  mismatch: 'differs from Finnhub',
}

/** Today's prices checked before use, with a second source for what matters most. */
export function DataQualityCard({ data }: { data: Health }) {
  const q = data.data_quality
  if (!q) return null
  const tone: Tone = q.blocked ? 'warn' : 'good'
  return (
    <Card title="Price checks today" aside={<Badge tone={tone}>{q.blocked ? `${q.blocked} blocked` : 'all passed'}</Badge>}>
      <p className="text-sm">
        {q.checked.toLocaleString('en-US')} prices checked for impossible values, jumps without a split and frozen prices.{' '}
        {q.second_source ? (
          <>
            {q.cross_checked} compared with {q.second_source}: {q.confirmed} within 2%.
          </>
        ) : (
          'The second source was not available today.'
        )}
      </p>
      {q.issues.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm" aria-label="Price issues">
          {q.issues.map((i) => (
            <li key={`${i.ticker}-${i.kind}`} className="flex flex-wrap items-baseline gap-x-2">
              <strong>{i.ticker}</strong>
              <Badge tone={i.blocks ? 'warn' : 'neutral'}>{i.blocks ? 'no new buys today' : 'warning'}</Badge>
              <span className="text-slate-600 dark:text-zinc-400">
                {KIND_TEXT[i.kind] ?? i.kind}: {i.detail}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-xs text-slate-600 dark:text-zinc-400">A stock that fails is blocked for new buys that day; stored prices are never changed.</p>
    </Card>
  )
}

const SEVERITY: Record<string, Tone> = { warning: 'warn', serious: 'bad', critical: 'bad' }

/** Every problem the daily build noticed, when it started and ended: nothing is deleted. */
export function IncidentsCard() {
  const res = useSiteJson<IncidentsFile>('incidents.json')
  if (res.state !== 'ready') return null
  const f = res.data
  return (
    <Card title="Incident log" aside={<Badge tone={!f.verified ? 'bad' : f.open.length ? 'warn' : 'good'}>{!f.verified ? 'BROKEN' : f.open.length ? `${f.open.length} open` : 'none open'}</Badge>}>
      <p className="text-sm">
        {f.days_checked} day{f.days_checked === 1 ? '' : 's'} checked{f.since ? ` since ${f.since}` : ''}; {f.days_with_open_incident} with an open incident. Append-only and sealed like the trade ledger{f.verified ? '' : ` (check failed: ${f.detail})`}.
      </p>
      {f.events.length === 0 ? (
        <p className="mt-2 text-sm text-slate-600 dark:text-zinc-400">No incident so far.</p>
      ) : (
        <ul className="mt-2 divide-y divide-slate-100 text-sm dark:divide-zinc-800">
          {f.events.slice(0, 20).map((e, i) => (
            <li key={`${e.date}-${e.incident}-${i}`} className="py-1.5">
              <span className="flex flex-wrap items-baseline gap-x-2">
                <span className="text-xs text-slate-500 tabular-nums dark:text-zinc-400">{e.date}</span>
                {e.status === 'open' ? <Badge tone={SEVERITY[e.severity ?? ''] ?? 'warn'}>started</Badge> : <Badge tone="good">resolved</Badge>}
                <strong>{e.title}</strong>
              </span>
              {e.detail && <span className="block text-xs text-slate-600 dark:text-zinc-400">{e.detail}</span>}
              {e.status === 'resolved' && e.opened && <span className="block text-xs text-slate-600 dark:text-zinc-400">open since {e.opened}</span>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
