// Shapes of the JSON files exported by the pipeline (pipeline/src/convergealpha/export/).

export type SourceStatus = 'ok' | 'stale' | 'failed' | 'not_configured' | 'not_implemented'

export interface HealthSource {
  id: string
  name: string
  phase: number
  status: SourceStatus
  last_success: string | null
  as_of: string | null
  records: number | null
  detail: string
  needs_secret: string | null
}

export interface HealthSecret {
  name: string
  purpose: string
  required: boolean
  used_from_phase: number | null
  present: boolean
}

export interface Health {
  schema_version: number
  generated_at: string
  pipeline_version: string
  build_phase: number
  status: 'ok' | 'degraded' | 'failed'
  status_detail: string
  research_mode: boolean
  validated: string[]
  model_version: string | null
  kill_switch: { implemented: boolean; active: boolean | null; reasons: string[] }
  run: {
    workflow: string
    event: string
    run_id: string | null
    run_url: string | null
    git_sha: string | null
  }
  sources: HealthSource[]
  secrets: HealthSecret[]
}
