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
  coverage?: number | null
  optional?: boolean
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
  labels?: Record<string, number>
  forecast_method?: string
  model_trained_at?: string
  model_metrics?: Record<string, number | null>
  ledger?: { entries: number; new_today: number; outcomes: number; verified: boolean } | null
  drift?: { psi: Record<string, number> | null; alerts: string[] } | null
  actions_usage?: { month: string; runs: number; wall_minutes: number; billing: string } | null
}

export type Cell = string | number | boolean | null

/** screener.json: columnar rows, one per stock. */
export interface ScreenerFile {
  schema_version: number
  as_of: string
  generated_at: string
  count: number
  fields: string[]
  rows: Cell[][]
}

export type ScreenerRow = Record<string, Cell> & { ticker: string }

export interface ChartArrays {
  daily?: { t: string[]; o: (number | null)[]; h: (number | null)[]; l: (number | null)[]; c: (number | null)[]; v: (number | null)[] }
  weekly?: { t: string[]; c: number[] }
}

export interface Freshness {
  source: string
  name: string
  as_of: string | null
  retrieved_at: string | null
}

/** stocks/<TICKER>.json. Sections are optional: each phase adds more. */
export interface StockFile {
  schema_version: number
  ticker: string
  name: string
  exchange: string
  is_adr: boolean
  cik: number | null
  as_of: string
  stats: Record<string, Cell>
  chart: ChartArrays
  freshness: Freshness[]
  [section: string]: unknown
}

export interface BenchmarkStats {
  price: number | null
  change_1d: number | null
  ret_1w: number | null
  ret_1m: number | null
  ret_3m: number | null
  ret_ytd: number | null
  ret_1y: number | null
  sma50: number | null
  sma200: number | null
  vol_63: number | null
  last_date: string | null
}

export interface MarketFile {
  as_of: string
  benchmarks: Record<string, BenchmarkStats | null>
  breadth?: { stocks: number; advancing_pct: number; above_200d_pct: number; new_highs: number }
  regime: null | {
    state: 'Normal' | 'Caution' | 'Stress'
    reasons: string[]
    [key: string]: unknown
  }
  macro?: Record<string, { label: string; value: number; date: string; change_3m: number }>
  [key: string]: unknown
}
