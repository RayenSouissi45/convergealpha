import { useState } from 'react'
import { Link } from 'react-router'
import { useSiteJson } from '../lib/data'
import { formatAge } from '../lib/format'
import { Badge, Card } from './ui'

interface IntradayFile {
  /** null: no intraday check since the last daily build. */
  generated_at: string | null
  checked: number
  alerts: { ticker: string; type: string; severity: 'high' | 'medium' | 'info'; text: string; url?: string }[]
}

/** Alerts from the intraday check (every ~2 hours in market hours). Hidden when not from today. */
export function IntradayCard() {
  const res = useSiteJson<IntradayFile>('intraday.json')
  const [today] = useState(() => new Date().toDateString())
  if (res.state !== 'ready') return null
  const d = res.data
  if (!d.generated_at || new Date(d.generated_at).toDateString() !== today) return null
  return (
    <Card title="Intraday alerts" aside={<span className="text-xs text-slate-500">checked {formatAge(d.generated_at)} · {d.checked} stocks</span>}>
      {d.alerts.length === 0 ? (
        <p className="text-sm">No alerts for candidates or holdings since the open.</p>
      ) : (
        <ul className="divide-y divide-slate-100 text-sm dark:divide-zinc-800">
          {d.alerts.map((a, i) => (
            <li key={i} className="flex items-start gap-2 py-2">
              <Badge tone={a.severity === 'high' ? 'bad' : a.severity === 'medium' ? 'warn' : 'neutral'}>{a.severity === 'high' ? 'Act' : a.severity === 'medium' ? 'Check' : 'Info'}</Badge>
              <span>
                <Link to={`/stock/${encodeURIComponent(a.ticker)}`} className="font-semibold underline">{a.ticker}</Link> {a.text}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
