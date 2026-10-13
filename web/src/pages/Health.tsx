import { Icon } from '../components/Icon'
import { Missing } from '../components/Missing'
import { Tip } from '../components/Tip'
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
  const m = data.model_metrics
  return (
    <Card title="Models and safety">
      <dl>
        <Row label="Validation">
          {data.validated.length > 0 ? (
            <span className="flex flex-col items-end gap-1">
              <Badge tone="good">{data.validated.length} passed</Badge>
              <span className="text-xs font-normal">{data.validated.join(', ')}</span>
            </span>
          ) : (
            <Badge tone="warn">Research mode: nothing validated yet</Badge>
          )}
        </Row>
        <Row label="Forecast method">{data.forecast_method === 'model' ? 'Trained models (walk-forward, calibrated)' : 'Fallback estimate — not calibrated'}</Row>
        <Row label="Model version">
          {data.model_version ?? <Missing reason="No trained model bundle yet: the weekly job trains them. Until then forecasts use the transparent fallback." />}
        </Row>
        {m && (
          <Row label={<Tip content="Out-of-sample (walk-forward) quality of the 60-day trade probability: AUC above 0.5 means better than chance; Brier must beat the base rate.">Out-of-sample quality</Tip>}>
            {`AUC ${m.auc_correct?.toFixed(3) ?? '—'} · Brier ${m.brier_correct?.toFixed(4) ?? '—'} vs ${m.brier_base?.toFixed(4) ?? '—'}`}
          </Row>
        )}
        <Row label={<Tip content="No new BUY labels if the live strategy falls 15% from its peak, its rolling 12-month excess is below −5%, or the data fails to update.">Kill switch</Tip>}>
          {data.kill_switch.implemented ? (data.kill_switch.active ? <Badge tone="bad">Active</Badge> : <Badge tone="good">Off</Badge>) : <Missing reason="Not computed in this run." />}
        </Row>
        <Row label={<Tip content="The prediction ledger is hash-chained: each entry includes the hash of the previous one, so past predictions cannot be edited unnoticed.">Prediction ledger</Tip>}>
          {data.ledger ? (
            <Badge tone={data.ledger.verified ? 'good' : 'bad'}>
              {data.ledger.verified ? 'verified' : 'BROKEN'} · {data.ledger.entries} entries, {data.ledger.new_today} new
            </Badge>
          ) : (
            '—'
          )}
        </Row>
        <Row label={<Tip content="Every paper-trading order, fill and daily value is appended to a separate hash-chained ledger in the private data repo and checked at every build.">Trade ledger (paper money)</Tip>}>
          {data.trade_ledger ? (
            <Badge tone={data.trade_ledger.verified ? 'good' : 'bad'}>
              {data.trade_ledger.verified ? 'verified' : 'BROKEN'} · {data.trade_ledger.entries} entries, {data.trade_ledger.new_today} new
            </Badge>
          ) : (
            <Missing reason="Starts with the first daily build of the strategies (close of Oct 13, 2026)." />
          )}
        </Row>
        <Row label={<Tip content="Population stability index of each model input vs the last two years of training data. Above 0.25 = the inputs look different from what the model learned on.">Data drift (PSI)</Tip>}>
          {data.drift ? (data.drift.alerts.length ? <Badge tone="warn">Drift in {data.drift.alerts.join(', ')}</Badge> : <Badge tone="good">No input above 0.25</Badge>) : <Missing reason="Needs the trained model bundle." />}
        </Row>
        <Row label="Actions minutes used">
          {data.actions_usage ? `${data.actions_usage.wall_minutes} min in ${data.actions_usage.runs} runs (${data.actions_usage.month}); ${data.actions_usage.billing}` : <Missing reason="Only measured on GitHub Actions. Standard runners are free for public repositories." />}
        </Row>
      </dl>
      {data.kill_switch.active && <p className="mt-2 text-sm text-red-700 dark:text-red-400">{data.kill_switch.reasons.join(' · ')}</p>}
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
              {s.detail && s.status !== 'not_implemented' && <div className="mt-0.5 text-xs text-slate-600 dark:text-zinc-300">{s.detail}</div>}
              <div className="mt-0.5 text-xs text-slate-500 dark:text-zinc-400">
                Last success:{' '}
                {s.last_success ? formatAge(s.last_success) : <Missing reason={s.detail} />}
                {' · '}Data as of: {s.as_of ? formatDateTime(s.as_of) : <Missing reason={s.detail} />}
                {s.records !== null && ` · ${s.records.toLocaleString('en-US')} records`}
                {s.coverage != null && ` · coverage ${Math.round(s.coverage * 100)}%`}
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
