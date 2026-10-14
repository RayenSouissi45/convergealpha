import { useSiteJson } from '../lib/data'
import { formatDay, formatPctAbs } from '../lib/format'
import { Badge, Card } from './ui'

interface Rate {
  n: number
  rate: number | null
  lo: number | null
  hi: number | null
}

interface HorizonCard {
  n: number
  days: number
  first_day?: string
  last_day?: string
  said_avg?: number
  rose?: number
  base_up?: number
  brier?: number
  brier_base?: number
  skill?: number | null
  confident_up?: Rate
  confident_down?: Rate
  buckets?: ({ lo: number; hi: number; said: number } & Rate)[]
  enough?: boolean
}

export interface ReportCardFile {
  as_of: string
  since: string | null
  forecast_days: number
  confident: number
  horizons: Record<string, HorizonCard>
  first_result: Record<string, string | null>
  note: string
  /** Signal decay: each evidence family's live rank correlation with later returns. */
  families?: Record<string, { name: string } & Record<'1w' | '1m', { days: number; periods?: number; ic?: number; t?: number | null; status?: string }>>
}

export interface CommitmentFile {
  date: string
  generated_at: string
  code_commit: string | null
  data_commit_before_build: string | null
  model_version: string | null
  snapshots: Record<string, { path: string; sha256: string | null }>
  forecast_archive: { path: string; sha256: string | null }
  ledgers: Record<string, { entries: number; head: string | null }>
}

const H_LABEL: Record<string, string> = { '1w': '1 week', '1m': '1 month', '3m': '3 months', '6m': '6 months' }
const pct = (x: number | null | undefined) => (x === null || x === undefined ? '—' : formatPctAbs(x, 0))
const range = (r: Rate | undefined) => (r && r.lo !== null && r.hi !== null ? `${pct(r.lo)}–${pct(r.hi)}` : '—')

/** Every published forecast against what really happened, losers included. */
export function LiveReportCard() {
  const res = useSiteJson<ReportCardFile>('report_card.json')
  if (res.state !== 'ready') return null
  const f = res.data
  const entries = Object.entries(f.horizons)
  return (
    <Card title="Every forecast vs what happened" aside={<Badge tone="neutral">{f.forecast_days} forecast days</Badge>}>
      <p className="text-sm">
        Every day since {f.since ? formatDay(f.since) : '—'} the app gives each eligible stock a chance of rising. Here they are checked once the time has passed: "we said 60%+, this share really rose". Every stock counts, losers too.
      </p>
      <div className="-mx-4 mt-2 overflow-x-auto px-4">
        <table className="w-full min-w-max text-sm tabular-nums">
          <caption className="sr-only">Live forecast results by horizon</caption>
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs text-slate-600 dark:border-zinc-700 dark:text-zinc-300">
              <th className="px-2 py-1.5">Horizon</th>
              <th className="px-2 py-1.5 text-right">Checked</th>
              <th className="px-2 py-1.5 text-right">Said {pct(f.confident)}+ → rose</th>
              <th className="px-2 py-1.5 text-right">Said {pct(1 - f.confident)} or less → fell</th>
              <th className="px-2 py-1.5 text-right">Better than the usual rate?</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-zinc-800">
            {entries.map(([h, c]) => (
              <tr key={h}>
                <th scope="row" className="px-2 py-1.5 text-left font-normal">
                  {H_LABEL[h] ?? h}
                </th>
                {c.n === 0 ? (
                  <td colSpan={4} className="px-2 py-1.5 text-slate-600 dark:text-zinc-400">
                    First results {f.first_result[h] ? `on ${formatDay(f.first_result[h]!)}` : 'later'}.
                  </td>
                ) : (
                  <>
                    <td className="px-2 py-1.5 text-right">
                      {c.n.toLocaleString('en-US')} <span className="text-xs text-slate-500 dark:text-zinc-400">({c.days} day{c.days === 1 ? '' : 's'})</span>
                    </td>
                    <td className="px-2 py-1.5 text-right">
                      {pct(c.confident_up?.rate)} <span className="text-xs text-slate-500 dark:text-zinc-400">n {c.confident_up?.n ?? 0}, {range(c.confident_up)}</span>
                    </td>
                    <td className="px-2 py-1.5 text-right">
                      {pct(c.confident_down?.rate)} <span className="text-xs text-slate-500 dark:text-zinc-400">n {c.confident_down?.n ?? 0}, {range(c.confident_down)}</span>
                    </td>
                    <td className="px-2 py-1.5 text-right">
                      {!c.enough ? (
                        <span className="text-slate-600 dark:text-zinc-400">too few yet</span>
                      ) : c.skill !== null && c.skill !== undefined && c.skill > 0 ? (
                        <Badge tone="good">yes, {(c.skill * 100).toFixed(1)}% better</Badge>
                      ) : (
                        <Badge tone="bad">no</Badge>
                      )}
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {f.families && Object.keys(f.families).length > 0 && (
        <>
          <h3 className="mt-3 text-sm font-semibold">Which evidence still works live</h3>
          <ul className="mt-1 space-y-0.5 text-sm" aria-label="Evidence families live">
            {Object.entries(f.families).map(([k, fam]) => {
              const m = fam['1m']?.days ? fam['1m'] : fam['1w']
              const label = fam['1m']?.days ? '1 month' : '1 week'
              return (
                <li key={k} className="flex flex-wrap justify-between gap-x-3 tabular-nums">
                  <span>{fam.name}</span>
                  <span className="text-slate-600 dark:text-zinc-400">
                    {m?.days ? (
                      <>
                        {label}: rank correlation {m.ic !== undefined ? m.ic.toFixed(3) : '—'} over {m.days} days ·{' '}
                        <Badge tone={m.status === 'working' ? 'good' : m.status === 'not working live' ? 'bad' : 'neutral'}>{m.status}</Badge>
                      </>
                    ) : (
                      'first results with the 1-week horizon'
                    )}
                  </span>
                </li>
              )
            })}
          </ul>
          <p className="mt-1 text-xs text-slate-600 dark:text-zinc-400">A family is called "not working live" only after 6 independent periods with a negative average (t below −2). That is a reason for the next rules version, never a silent change.</p>
        </>
      )}
      <p className="mt-2 text-xs text-slate-600 dark:text-zinc-400">
        "Better than the usual rate" compares the Brier score (the average squared miss of the chances) with simply using how often stocks rose in 2016–2023. {f.note}
      </p>
    </Card>
  )
}

const short = (h: string | null | undefined) => (h ? `${h.slice(0, 12)}…` : '—')

/** Today's fingerprints of every forecast and sealed record, also committed to the public repository. */
export function CommitmentCard({ repoUrl }: { repoUrl?: string }) {
  const res = useSiteJson<CommitmentFile>('commitment.json')
  if (res.state !== 'ready') return null
  const c = res.data
  return (
    <Card title="Public fingerprints">
      <p className="text-sm">
        Every day the app publishes the SHA-256 fingerprint of all its forecasts and the latest seal of each record, and commits them to the public code repository, where GitHub records the time. A forecast or trade changed later would no longer match.
      </p>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs tabular-nums">
        <dt className="text-slate-600 dark:text-zinc-400">Day</dt>
        <dd>{c.date}</dd>
        {Object.entries(c.snapshots).map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-slate-600 dark:text-zinc-400">{k === 'scores' ? 'Forecasts' : k}</dt>
            <dd className="break-all" title={v.sha256 ?? ''}>
              {short(v.sha256)}
            </dd>
          </div>
        ))}
        {Object.entries(c.ledgers).map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-slate-600 dark:text-zinc-400">{k} record</dt>
            <dd title={v.head ?? ''}>
              {v.entries.toLocaleString('en-US')} entries · seal {short(v.head)}
            </dd>
          </div>
        ))}
        <dt className="text-slate-600 dark:text-zinc-400">Code</dt>
        <dd>{c.code_commit ? c.code_commit.slice(0, 7) : '—'}</dd>
      </dl>
      <p className="mt-2 text-xs">
        <a className="text-teal-700 underline dark:text-teal-400" href={`data/${c.forecast_archive.path}`}>
          This month's forecasts (JSON)
        </a>
        {repoUrl && (
          <>
            {' · '}
            <a className="text-teal-700 underline dark:text-teal-400" href={`${repoUrl}/commits/ledger-heads`} target="_blank" rel="noreferrer">
              Fingerprint history on GitHub
            </a>
          </>
        )}
      </p>
    </Card>
  )
}
