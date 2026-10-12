import { Icon } from '../components/Icon'
import { Missing } from '../components/Missing'
import { Badge, Card, PageHeader, Row, type Tone } from '../components/ui'
import { formatAge, formatDateTime, formatNewYork, isStale } from '../lib/format'
import { useHealth } from '../lib/health'
import type { Health as HealthData, HealthSource } from '../types'

const SOURCE_STATUS: Record<HealthSource['status'], { tone: Tone; text: (s: HealthSource) => string }> = {
  ok: { tone: 'good', text: () => 'OK' },
  stale: { tone: 'warn', text: () => 'Stale' },
  failed: { tone: 'bad', text: () => 'Failed' },
  not_configured: { tone: 'warn', text: (s) => `Key missing${s.needs_secret ? `: ${s.needs_secret}` : ''}` },
  not_implemented: { tone: 'neutral', text: (s) => `Not connected yet · phase ${s.phase}` },
}

function Overview({ data }: { data: HealthData }) {
  const stale = isStale(data.generated_at)
  const tone: Tone = data.status === 'failed' ? 'bad' : data.status === 'degraded' || stale ? 'warn' : 'good'
  const label = data.status === 'ok' ? (stale ? 'OK but stale' : 'OK') : data.status === 'degraded' ? 'Degraded' : 'Failed'
  return (
    <Card title="Last pipeline run" aside={<Badge tone={tone}>{label}</Badge>}>
      <p className="mb-2 text-sm text-slate-600 dark:text-zinc-400">{data.status_detail}</p>
      <dl>
        <Row label="Finished">
          {formatAge(data.generated_at)}
          <div className="text-xs font-normal text-slate-500 dark:text-zinc-400">
            {formatDateTime(data.generated_at)} · {formatNewYork(data.generated_at)}
          </div>
        </Row>
        <Row label="Triggered by">
          {data.run.workflow} ({data.run.event})
        </Row>
        <Row label="Build phase">{data.build_phase}</Row>
        <Row label="Pipeline version">{data.pipeline_version}</Row>
        <Row label="Code version">{data.run.git_sha ? data.run.git_sha.slice(0, 7) : <Missing reason="Only known for runs on GitHub Actions." />}</Row>
      </dl>
      {data.run.run_url && (
        <a
          href={data.run.run_url}
          target="_blank"
          rel="noreferrer"
          className="mt-2 inline-flex min-h-11 items-center gap-1 text-sm font-medium text-teal-700 underline dark:text-teal-400"
        >
          View this run on GitHub <Icon name="external" className="size-4" />
        </a>
      )}
    </Card>
  )
}

function Models({ data }: { data: HealthData }) {
  return (
    <Card title="Models and safety">
      <dl>
        <Row label="Validation">
          {data.validated.length > 0 ? (
            <Badge tone="good">Passed: {data.validated.join(', ')}</Badge>
          ) : (
            <Badge tone="warn">Research mode</Badge>
          )}
        </Row>
        <Row label="Model version">
          {data.model_version ?? <Missing reason="No model trained yet. Models arrive in build phase 4." />}
        </Row>
        <Row label="Kill switch">
          {data.kill_switch.implemented ? (
            data.kill_switch.active ? (
              <Badge tone="bad">Active</Badge>
            ) : (
              <Badge tone="good">Off</Badge>
            )
          ) : (
            <Missing reason="Not implemented yet. The kill switch arrives in build phase 6." />
          )}
        </Row>
        <Row label="Actions minutes used">
          <Missing reason="Reported from build phase 6. Standard GitHub-hosted runners are free for public repositories." />
        </Row>
      </dl>
    </Card>
  )
}

function Sources({ data }: { data: HealthData }) {
  const live = data.sources.filter((s) => s.status === 'ok').length
  return (
    <Card title="Data sources" aside={<span className="text-sm text-slate-500 dark:text-zinc-400">{live} of {data.sources.length} live</span>}>
      <ul className="divide-y divide-slate-100 dark:divide-zinc-800">
        {data.sources.map((s) => {
          const status = SOURCE_STATUS[s.status]
          return (
            <li key={s.id} className="py-2.5">
              <div className="flex items-start justify-between gap-3">
                <span className="text-sm font-medium">{s.name}</span>
                <Badge tone={status.tone}>{status.text(s)}</Badge>
              </div>
              <div className="mt-0.5 text-xs text-slate-500 dark:text-zinc-400">
                Last success:{' '}
                {s.last_success ? formatAge(s.last_success) : <Missing reason={s.detail} />}
                {' · '}Data as of: {s.as_of ? formatDateTime(s.as_of) : <Missing reason={s.detail} />}
                {s.records !== null && ` · ${s.records.toLocaleString()} records`}
              </div>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}

function Secrets({ data }: { data: HealthData }) {
  return (
    <Card title="API keys">
      <p className="mb-2 text-xs text-slate-500 dark:text-zinc-400">
        Only whether each key is set is shown, never the key itself. Add keys in GitHub → Settings →
        Secrets and variables → Actions (see SETUP.md).
      </p>
      <ul className="divide-y divide-slate-100 dark:divide-zinc-800">
        {data.secrets.map((s) => (
          <li key={s.name} className="flex items-start justify-between gap-3 py-2.5">
            <div className="min-w-0">
              <div className="font-mono text-xs break-all">{s.name}</div>
              <div className="text-xs text-slate-500 dark:text-zinc-400">
                {s.purpose} · {s.required ? 'required' : s.used_from_phase ? `used from phase ${s.used_from_phase}` : 'optional'}
              </div>
            </div>
            {s.present ? <Badge tone="good">Set</Badge> : <Badge tone={s.required ? 'warn' : 'neutral'}>Not set</Badge>}
          </li>
        ))}
      </ul>
    </Card>
  )
}

export default function Health() {
  const health = useHealth()
  return (
    <>
      <PageHeader title="Health" subtitle="Is the data fresh, and did the last update work?" />
      {health.state === 'loading' && <p className="text-sm text-slate-500">Loading health report…</p>}
      {health.state === 'missing' && (
        <Card>
          <p className="text-sm">
            The daily pipeline has not published a health report yet. It runs Monday–Friday at
            22:30 UTC, after the US close.
          </p>
        </Card>
      )}
      {health.state === 'error' && (
        <Card>
          <p className="text-sm text-red-700 dark:text-red-400">Could not load health.json ({health.message}).</p>
        </Card>
      )}
      {health.state === 'ready' && (
        <div className="grid gap-3 md:grid-cols-2">
          <Overview data={health.data} />
          <Models data={health.data} />
          <Sources data={health.data} />
          <Secrets data={health.data} />
        </div>
      )}
    </>
  )
}
