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
  brokers?: BrokerSummary | null
  trade_ledger?: { verified: boolean; detail: string; entries: number; new_today: number; last_day: string | null } | null
}

/** The finanzen.net zero list (gettex shares in ESMA FIRDS, or the owner's manual file). */
export interface BrokerSummary {
  source: string
  list_date: string
  instruments?: number
  with_us_ticker?: number
  age_days?: number
  stale?: boolean
  matched?: number
  matched_eligible?: number
  unknown?: number
  stocks?: number
  eligible?: number
}

/** "How often was it right?" bucket: past cases with a similar probability. */
export interface ReliabilityBucket {
  lo: number
  hi: number
  n: number
  rate: number
  wilson_lo: number
  wilson_hi: number
}

export interface ReliabilityTables {
  method?: string
  years?: number[]
  up: Record<string, ReliabilityBucket[]>
}

/** A stock's lookup result (stock pages, picks.json). */
export interface Reliability {
  rate: number
  lo: number
  hi: number
  n: number | null
  p_lo?: number
  p_hi?: number
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
  reliability?: ReliabilityTables | null
  brokers?: BrokerSummary | null
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

/** picks.json: the Picks page (top 25 per tab). */
export interface PickHorizon {
  median: number | null
  p10: number | null
  p90: number | null
  p_up: number | null
  validated: boolean
  reliability: Reliability | null
}

export interface Pick {
  ticker: string
  name: string | null
  sector: string | null
  label: string
  next_earnings: string | null
  zero: boolean | null
  price: number | null
  scores: { safety: number | null; upside: number | null; confidence: number | null; balanced: number | null }
  rank: number | null
  horizons: Record<'1w' | '1m' | '3m' | '6m', PickHorizon>
  reasons: string[]
  risk: string
  opp?: OppColor | null
  opp_event?: string | null
}

export interface PicksFile {
  schema_version: number
  generated_at: string
  as_of: string
  research_mode: boolean
  validated: string[]
  weights: Record<string, Record<string, number>>
  floor: number
  top: number
  min_sector: number
  summary: {
    eligible: number
    sell: number
    blocked: number
    no_forecast: number
    candidates: number
    passing_floor: number
    probability_source: string
    reliability_available: boolean
  }
  brokers: BrokerSummary | null
  race: { since: string | null; cumulative?: number; months?: number; max_drawdown?: number; points?: { date: string; excess: number }[] } | null
  tabs: Record<'balanced' | 'safest' | 'upside' | 'likely', string[]>
  /** The same tabs without stocks known to be unavailable on finanzen.net zero. */
  tabs_zero?: Record<'balanced' | 'safest' | 'upside' | 'likely', string[]>
  stocks: Record<string, Pick>
}

/** The opportunity badge (opportunities.json and stocks/<TICKER>.json "opportunity"). */
export type OppColor = 'green' | 'amber' | 'red'

export interface OppHistory {
  pattern: string
  scope: 'stock' | 'peers'
  window: string
  n: number
  up_rate: number
  mean_return: number
  mean_excess: number
  hit_rate: number
  q_value: number
  passed: boolean
  halves_ok: boolean
  holdout_ok: boolean | null
}

export interface OppEvent {
  kind: string
  date: string
  text: string
  source: string
  url: string | null
  history: OppHistory | null
  history_note: string | null
}

export interface Opportunity {
  color: OppColor
  title: string
  summary: string
  short: string
  events: OppEvent[]
  checks: { text: string; ok: boolean }[]
  risks: string[]
  missing: string[]
  days_since_event: number | null
  as_of: string
}

export interface OpportunitiesFile {
  as_of: string
  base_up: Record<string, number>
  counts: Record<OppColor, number>
  stocks: Record<string, Opportunity>
}

/** plan.json: the Plan builder's candidates (computed in the browser for your amount). */
export interface PlanFile {
  schema_version: number
  generated_at: string
  as_of: string
  research_mode: boolean
  validated: string[]
  horizons: Record<string, number>
  fx: { rate: number; date: string; series: string; source: string } | null
  base_up: Record<string, number>
  reliability: Record<string, ReliabilityBucket[]>
  reliability_years: number[] | null
  costs: { fee_buy: number; fee_sell: number }
  thresholds: Record<string, unknown>
  count: number
  fields: string[]
  rows: Cell[][]
}

/** strategies.json: paper trading (paper money only). */
export interface StrategyHolding {
  ticker: string
  name: string | null
  shares: number
  entry_date: string
  entry_usd: number
  cost_eur: number
  close_usd: number | null
  value_eur: number | null
  stock_move: number | null
  gain_eur: number | null
  days_held: number
  levels: { stop_usd: number | null; take_profit_usd: number | null; trailing_usd: number | null; max_hold_days: number | null; days_left: number | null }
}

export interface StrategyEvent {
  date: string
  kind: 'fill' | 'cancel' | 'dividend' | 'split'
  ticker: string | null
  side?: 'buy' | 'sell'
  shares?: number | null
  open_usd?: number | null
  price_usd?: number | null
  price_eur?: number | null
  fx?: number | null
  fx_date?: string | null
  fee?: number | null
  amount_eur?: number | null
  pnl_eur?: number | null
  pnl_pct?: number | null
  stock_move?: number | null
  reason?: string | null
  order_reason?: string | null
}

export interface StrategyCard {
  key: string
  id: string
  version: number
  name: string
  mindset: string
  rules: string[]
  max_positions: number
  params: Record<string, unknown>
  benchmark: boolean
  locked: string | null
  last_day: string | null
  value: number | null
  pct: number | null
  vs_benchmark: number | null
  fees: number | null
  dividends: number | null
  trades: number
  closed: number
  wins: number
  win_rate: number | null
  max_drawdown: number | null
  cash: number | null
  holdings: StrategyHolding[]
  pending: { side: 'buy' | 'sell'; ticker: string; name: string | null; reason: string; date: string; fill_on: string }[]
  history: StrategyEvent[]
  notes: string[]
  series: [string, number][]
}

export interface StrategySuggestion {
  rank: number
  ticker: string
  name: string | null
  sector: string | null
  price: number | null
  spread: number
  score: number
  score_text: string
  p_up_1m: number | null
  med_1m: number | null
  p10_1m: number | null
  p90_1m: number | null
  opp: OppColor | null
  opp_event: string | null
}

export interface StrategiesFile {
  schema_version: number
  generated_at: string
  as_of: string
  start: string
  capital: number
  currency: string
  paper_money_only: boolean
  status: string
  research_mode: boolean
  proven: string[]
  proven_days: number
  fx: { rate: number; date: string; series: string; source: string } | null
  costs: { fee_buy: number; fee_sell: number; dividend_withholding: number; min_hold: number; rebuy_cooldown: number }
  shared_rules: string[]
  ledger: { verified: boolean; detail: string; entries: number }
  validated: string[]
  base_up_1m: number | null
  reliability_1m?: ReliabilityBucket[]
  benchmark: StrategyCard | null
  strategies: StrategyCard[]
  suggestions: Record<string, StrategySuggestion[]>
}
