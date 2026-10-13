import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { OppWhy } from '../components/Opportunity'
import { COLUMN_DOCS, EXTRA_DOCS } from '../lib/columnDocs'
import { COLUMNS } from '../lib/columns'
import { resetOpportunities } from '../lib/opportunity'
import { resetScreenerCache } from '../lib/screener'
import { resetSettings } from '../lib/settings'
import { AppRoutes } from '../routes'
import type { Health, OpportunitiesFile, Opportunity, StrategiesFile } from '../types'
import health from './fixtures/health.json'
import opportunities from './fixtures/opportunities.json'
import plan from './fixtures/plan.json'
import strategies from './fixtures/strategies.json'

function stubFetch(files: Record<string, unknown>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const name = Object.keys(files).find((f) => url.endsWith(`data/${f}`))
    if (!name || files[name] === undefined) return new Response('Not found', { status: 404, headers: { 'content-type': 'text/html' } })
    return new Response(JSON.stringify(files[name]), { status: 200, headers: { 'content-type': 'application/json' } })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const FILES = () => ({
  'health.json': { ...(health as unknown as Health), generated_at: new Date().toISOString() },
  'plan.json': plan,
  'strategies.json': strategies,
  'opportunities.json': opportunities,
})

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  resetScreenerCache()
  resetOpportunities()
  resetSettings()
  localStorage.clear()
})

describe('Plan page', () => {
  it('shows the best fits with costs, break-even, chance, results and a verdict', async () => {
    stubFetch(FILES())
    renderAt('/plan')
    expect(await screen.findByRole('heading', { level: 1, name: 'Plan' })).toBeInTheDocument()
    const list = await screen.findByRole('list', { name: 'Best fits' })
    const cards = within(list).getAllByRole('listitem')
    expect(cards.length).toBeGreaterThan(0)
    expect(cards.length).toBeLessThanOrEqual(3)
    const first = cards[0]!
    expect(within(first).getByText(/the stock must rise/)).toBeInTheDocument()
    expect(within(first).getByText('Chance of ending with more money')).toBeInTheDocument()
    expect(within(first).getByText(/GREEN|AMBER|GREY/)).toBeInTheDocument()
    expect(within(first).getByText('Bad case (1 in 10)')).toBeInTheDocument()
    expect(screen.getByText(/Uses the 1-month forecast/)).toBeInTheDocument()
    expect(screen.getByText(/US dollars per euro \(FRED DEXUSEU/)).toBeInTheDocument()
  })

  it('maps a period between horizons and says so', async () => {
    stubFetch(FILES())
    const user = userEvent.setup()
    renderAt('/plan')
    await screen.findByRole('list', { name: 'Best fits' })
    await user.click(screen.getByRole('button', { name: '3 months' }))
    expect(await screen.findByText(/Uses the 3-month forecast/)).toBeInTheDocument()
    // The 3-month chance up is not validated: research mode is shown.
    expect(screen.getAllByText('RESEARCH MODE').length).toBeGreaterThan(0)
  })

  it('lets you change the fees and says to check the broker price list', async () => {
    stubFetch(FILES())
    const user = userEvent.setup()
    renderAt('/plan')
    await screen.findByRole('list', { name: 'Best fits' })
    await user.click(screen.getByText(/^Costs:/))
    expect(screen.getByText(/Check your broker’s current price list/)).toBeInTheDocument()
    const fee = screen.getByRole('spinbutton', { name: 'Fee per buy (€)' })
    await user.clear(fee)
    await user.type(fee, '5')
    expect(screen.getByText(/Costs: €5\.00 per buy/)).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Fractional shares (simulation only)' })).not.toBeChecked()
  })
})

describe('Strategies page', () => {
  it('shows the paper-money banner, research mode, leaderboard and a card per strategy', async () => {
    stubFetch(FILES())
    renderAt('/strategies')
    expect(await screen.findByRole('heading', { level: 1, name: 'Strategies' })).toBeInTheDocument()
    expect(screen.getByText('Paper money only. Past and live results do not guarantee future results.')).toBeInTheDocument()
    expect(await screen.findByText(/RESEARCH MODE — not yet proven live/)).toBeInTheDocument()
    const board = screen.getByRole('list', { name: 'Strategies by value' })
    const f = strategies as unknown as StrategiesFile
    expect(within(board).getAllByRole('listitem')).toHaveLength(f.strategies.length + 1)
    for (const s of f.strategies) expect(screen.getAllByText(s.name).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/What it will do at the next open/).length).toBe(f.strategies.length)
  })

  it('“Give me a strategy” uses your amount and marks the best overall', async () => {
    stubFetch(FILES())
    const user = userEvent.setup()
    renderAt('/strategies')
    await user.click(await screen.findByRole('button', { name: 'Give me a strategy' }))
    const amount = screen.getByRole('spinbutton', { name: 'Your amount in euros' })
    expect(amount).toHaveValue(200)
    expect(screen.getAllByText(/Best overall/).length).toBeGreaterThan(0)
  })
})

describe('opportunity badge', () => {
  it('the “Why?” panel shows the event, its source, what history says and what is missing', () => {
    const o = (opportunities as unknown as OpportunitiesFile).stocks
    const amber = Object.values(o).find((x) => x.color === 'amber') as Opportunity
    render(
      <MemoryRouter>
        <OppWhy opp={amber} />
      </MemoryRouter>,
    )
    expect(screen.getByText('Possible, not confirmed')).toBeInTheDocument()
    expect(screen.getByText('What happened')).toBeInTheDocument()
    expect(screen.getAllByText(/What history says/).length).toBe(amber.events.length)
    expect(screen.getByText('What is missing or risky')).toBeInTheDocument()
    expect(screen.getByText(/Never green on news alone/)).toBeInTheDocument()
  })

  it('Today lists opportunities; “Why?” loads the explanation on demand', async () => {
    const o = (opportunities as unknown as OpportunitiesFile).stocks
    const [ticker, op] = Object.entries(o).find(([, v]) => v.color === 'amber')!
    const [redTicker, red] = Object.entries(o).find(([, v]) => v.color === 'red')!
    const fetchMock = stubFetch({
      ...FILES(),
      'today.json': {
        schema_version: 1, as_of: '2026-10-13', generated_at: '2026-10-13T21:00:00Z', count: 2,
        fields: ['ticker', 'name', 'eligible', 'opp', 'opp_event', 'p_up_1m', 'ret_1w'],
        rows: [[ticker, 'X Corp', true, op.color, op.short, 0.56, 0.01], [redTicker, 'Y Corp', true, red.color, red.short, 0.5, 0.3]],
      },
    })
    const user = userEvent.setup()
    renderAt('/')
    expect(await screen.findByText('Opportunities this week')).toBeInTheDocument()
    expect(screen.getByText('Be careful: hype')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Strategies: 5 × 200 € paper money/ })).toHaveAttribute('href', '/strategies')
    const why = await screen.findByRole('button', { name: new RegExp(`Why is ${ticker} marked`) })
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith('opportunities.json'))).toBe(false)
    await user.click(why)
    expect(await screen.findByText('What happened')).toBeInTheDocument()
  })
})

describe('Columns explained covers the new numbers', () => {
  const PARTS = ['name', 'what', 'how', 'example', 'read', 'source', 'mistakes'] as const
  it('every new column and Plan / Strategies number has all 8 parts', () => {
    const docs = [...['opp', 'opp_event'].map((k) => COLUMN_DOCS[k]!), ...EXTRA_DOCS.map((d) => d.doc)]
    expect(COLUMNS.map((c) => c.key)).toEqual(expect.arrayContaining(['opp', 'opp_event']))
    for (const d of docs) {
      for (const p of PARTS) expect(d[p].trim().length, `${d.name}: ${p}`).toBeGreaterThan(3)
      expect(d.status).toBeTruthy()
    }
    const ids = EXTRA_DOCS.map((d) => d.id)
    for (const id of ['plan-shares', 'plan-leftover', 'plan-fees', 'plan-breakeven', 'plan-chance', 'plan-right', 'plan-results', 'plan-verdict', 'strat-value', 'strat-vs', 'strat-fees', 'strat-win', 'strat-drop', 'strat-cash', 'strat-levels']) {
      expect(ids).toContain(id)
    }
  })
})
