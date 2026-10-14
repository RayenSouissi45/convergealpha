import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { resetScreenerCache } from '../lib/screener'
import { AppRoutes } from '../routes'
import type { Health, IncidentsFile } from '../types'
import type { CommitmentFile, ReportCardFile } from '../components/ReportCard'
import fixture from './fixtures/health.json'

function stubFetch(files: Record<string, unknown>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      const name = Object.keys(files).find((f) => url.endsWith(`data/${f}`))
      if (!name) return new Response('Not found', { status: 404, headers: { 'content-type': 'text/html' } })
      return new Response(JSON.stringify(files[name]), { status: 200, headers: { 'content-type': 'application/json' } })
    }),
  )
}

const render_ = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  )

const health: Health = {
  ...(fixture as unknown as Health),
  generated_at: new Date().toISOString(),
  data_quality: {
    checked: 2452,
    cross_checked: 55,
    confirmed: 53,
    second_source: 'Finnhub',
    counts: { impossible: 1, jump: 0, frozen: 0, mismatch: 1 },
    blocked: 1,
    issues: [
      { ticker: 'BOXL', kind: 'impossible', detail: "close 2.8 outside the day's range 2.83–3.195", blocks: true },
      { ticker: 'AAPL', kind: 'mismatch', detail: 'close 250 vs 245 at Finnhub (2.0% apart)', blocks: false },
    ],
  },
}

const incidents: IncidentsFile = {
  verified: true,
  detail: 'ok',
  days_checked: 3,
  days_with_open_incident: 1,
  since: '2026-10-14',
  open: [],
  events: [
    { incident: 'fx_gap', status: 'resolved', date: '2026-10-16', title: 'ECB and FRED exchange rates disagree', opened: '2026-10-15' },
    { incident: 'fx_gap', status: 'open', date: '2026-10-15', title: 'ECB and FRED exchange rates disagree', severity: 'warning', detail: 'largest gap 0.40% (limit 0.20%)' },
  ],
}

const reportCard: ReportCardFile = {
  as_of: '2026-10-21',
  since: '2026-10-12',
  forecast_days: 8,
  confident: 0.6,
  horizons: {
    '1w': {
      n: 7350, days: 3, enough: true, skill: 0.012,
      confident_up: { n: 640, rate: 0.58, lo: 0.54, hi: 0.62 },
      confident_down: { n: 210, rate: 0.55, lo: 0.48, hi: 0.61 },
    },
    '1m': { n: 0, days: 0 },
  },
  first_result: { '1w': '2026-10-19', '1m': '2026-11-10' },
  note: 'Every eligible stock of every day counts, losers too.',
}

const commitment: CommitmentFile = {
  date: '2026-10-21',
  generated_at: '2026-10-21T22:59:00+00:00',
  code_commit: 'abcdef1234567',
  data_commit_before_build: null,
  model_version: 'v1',
  snapshots: { scores: { path: 'snapshots/2026/20261021/scores.parquet', sha256: 'f'.repeat(64) } },
  forecast_archive: { path: 'forecasts/2026-10.json', sha256: 'e'.repeat(64) },
  ledgers: { trades: { entries: 512, head: 'a'.repeat(64) } },
}

beforeEach(() => {
  resetScreenerCache()
  localStorage.clear()
})

describe('reliability on Health', () => {
  it('shows today’s price checks and the sealed incident log', async () => {
    stubFetch({ 'health.json': health, 'incidents.json': incidents })
    render_('/health')
    const checks = (await screen.findByRole('heading', { name: 'Price checks today' })).closest('section') ?? document.body
    expect(within(checks).getByText('1 blocked')).toBeInTheDocument()
    expect(within(checks).getByText(/2,452 prices checked/)).toBeInTheDocument()
    expect(within(checks).getByText(/55 compared with Finnhub: 53 within 2%/)).toBeInTheDocument()
    const issues = within(checks).getByRole('list', { name: 'Price issues' })
    expect(within(issues).getByText('no new buys today')).toBeInTheDocument()
    expect(within(issues).getByText('warning')).toBeInTheDocument()
    const log = (await screen.findByRole('heading', { name: 'Incident log' })).closest('section') ?? document.body
    expect(within(log).getByText('none open')).toBeInTheDocument()
    expect(within(log).getByText(/3 days checked since 2026-10-14; 1 with an open incident/)).toBeInTheDocument()
    expect(within(log).getByText('resolved')).toBeInTheDocument()
    expect(within(log).getByText('open since 2026-10-15')).toBeInTheDocument()
  })
})

describe('live report card on the Scorecard', () => {
  it('shows every forecast against what happened, and when the first results come', async () => {
    stubFetch({ 'health.json': health, 'report_card.json': reportCard, 'commitment.json': commitment })
    render_('/scorecard')
    const table = await screen.findByRole('table', { name: 'Live forecast results by horizon' })
    const week = within(table).getByRole('row', { name: /1 week/ })
    expect(within(week).getByText('58%')).toBeInTheDocument()
    expect(within(week).getByText(/n 640, 54%–62%/)).toBeInTheDocument()
    expect(within(week).getByText('yes, 1.2% better')).toBeInTheDocument()
    expect(within(table).getByRole('row', { name: /1 month/ })).toHaveTextContent('First results on Nov 10, 2026.')
    expect(screen.getByText('Public fingerprints')).toBeInTheDocument()
    expect(screen.getByText(/512 entries · seal aaaaaaaaaaaa…/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: "This month's forecasts (JSON)" })).toHaveAttribute('href', 'data/forecasts/2026-10.json')
  })
})
