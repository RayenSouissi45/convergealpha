import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { resetScreenerCache } from '../lib/screener'
import { AppRoutes } from '../routes'
import type { Health } from '../types'
import fixture from './fixtures/health.json'
import market from './fixtures/market.json'
import screener from './fixtures/screener.json'
import aapl from './fixtures/stocks/AAPL.json'
import con from './fixtures/stocks/CON_.json'
import ledger from './fixtures/ledger.json'
import race from './fixtures/race.json'
import scorecard from './fixtures/scorecard.json'
import validation from './fixtures/validation.json'

function healthAt(generatedAt: Date, overrides: Partial<Health> = {}): Health {
  return { ...(fixture as unknown as Health), generated_at: generatedAt.toISOString(), ...overrides }
}

/** Serves fixture files by URL like the static host does; unknown files are 404. */
function stubFetch(files: Record<string, unknown>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const name = Object.keys(files).find((f) => url.endsWith(`data/${f}`))
    if (!name || files[name] === undefined) {
      return new Response('Not found', { status: 404, headers: { 'content-type': 'text/html' } })
    }
    return new Response(JSON.stringify(files[name]), { status: 200, headers: { 'content-type': 'application/json' } })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const ALL = () => ({
  'health.json': healthAt(new Date()),
  'screener.json': screener,
  'market.json': market,
  'stocks/AAPL.json': aapl,
  'stocks/CON_.json': con,
  'ledger.json': ledger,
  'scorecard.json': scorecard,
  'race.json': race,
})

beforeEach(() => resetScreenerCache())

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  )
}

const PAGES: [string, string][] = [
  ['/', 'Today'],
  ['/screener', 'Screener'],
  ['/stock/aapl', 'AAPL'],
  ['/compare', 'Compare'],
  ['/portfolio', 'My portfolio'],
  ['/scorecard', 'Scorecard'],
  ['/baseline-race', 'Baseline race'],
  ['/validation', 'Validation'],
  ['/health', 'Health'],
  ['/about', 'About & method'],
  ['/more', 'More'],
  ['/no-such-page', 'Page not found'],
]

describe.each(PAGES)('page %s', (path, heading) => {
  it('renders its heading and the research-mode banner', async () => {
    stubFetch(ALL())
    renderAt(path)
    expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeInTheDocument()
    const banner = screen.getByRole('complementary', { name: 'Research mode' })
    expect(banner).toHaveTextContent(/RESEARCH MODE — not yet validated/)
  })
})

describe('health page', () => {
  it('shows the pipeline report from health.json', async () => {
    const fetchMock = stubFetch({ 'health.json': healthAt(new Date()) })
    renderAt('/health')
    expect(await screen.findByText(/data sources live/)).toBeInTheDocument()
    expect(screen.getByText('Daily prices (Yahoo Finance)')).toBeInTheDocument()
    expect(screen.getByText('SEC_USER_AGENT')).toBeInTheDocument()
    // health.json is fetched once and shared by the whole app.
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0]?.[0])).toMatch(/data\/health\.json$/)
  })

  it('says plainly when the pipeline has not run yet', async () => {
    stubFetch({})
    renderAt('/health')
    expect(await screen.findByText(/has not published a health report yet/)).toBeInTheDocument()
    expect(screen.getByText('No data yet')).toBeInTheDocument()
  })

  it('warns when data is stale', async () => {
    stubFetch({ 'health.json': healthAt(new Date(Date.now() - 5 * 86400 * 1000)) })
    renderAt('/')
    expect(await screen.findByText('Data may be out of date.')).toBeInTheDocument()
  })

  it('shows the kill-switch banner when active', async () => {
    stubFetch({
      'health.json': healthAt(new Date(), {
        kill_switch: { implemented: true, active: true, reasons: ['Drawdown −15%'] },
      }),
    })
    renderAt('/')
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText(/KILL SWITCH ACTIVE/)).toBeInTheDocument()
    expect(within(alert).getByText(/Drawdown −15%/)).toBeInTheDocument()
  })
})

describe('today page', () => {
  it('uses the small today.json and skips the full screener when there are no holdings', async () => {
    localStorage.clear()
    const fetchMock = stubFetch({ ...ALL(), 'today.json': screener })
    renderAt('/')
    expect(await screen.findByText('Insider buying this week')).toBeInTheDocument()
    const urls = fetchMock.mock.calls.map((c) => String(c[0]))
    expect(urls.some((u) => u.endsWith('data/today.json'))).toBe(true)
    expect(urls.some((u) => u.endsWith('data/screener.json'))).toBe(false)
  })

  it('falls back to screener.json when today.json does not exist', async () => {
    const fetchMock = stubFetch(ALL())
    renderAt('/')
    expect(await screen.findByText('Insider buying this week')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some((c) => String(c[0]).endsWith('data/screener.json'))).toBe(true)
  })
})

describe('missing values', () => {
  it('explain themselves when tapped', async () => {
    stubFetch({ ...ALL(), 'market.json': { ...market, regime: null } })
    renderAt('/')
    const dash = await screen.findByRole('button', { name: /Not available: The regime also needs/ })
    expect(dash).toHaveTextContent('—')
    await userEvent.click(dash)
    expect(screen.getByRole('tooltip')).toHaveTextContent(/connected in build phase 2/)
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })
})

describe('screener', () => {
  it('lists every stock from screener.json and searches by ticker or name', async () => {
    stubFetch(ALL())
    renderAt('/screener')
    expect(await screen.findByText(/30 US stocks/)).toBeInTheDocument()
    expect(screen.getByText(/^30 shown/)).toBeInTheDocument()
    await userEvent.type(screen.getByRole('searchbox', { name: /search/i }), 'apple')
    expect(await screen.findByText(/^1 shown/)).toBeInTheDocument()
  })

  it('applies a preset (filters + sort) when tapped', async () => {
    stubFetch(ALL())
    renderAt('/screener')
    const preset = await screen.findByRole('button', { name: 'Most likely to rise' })
    await userEvent.click(preset)
    expect(preset).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText(/preset: Most likely to rise/)).toBeInTheDocument()
  })

  it('says plainly when no stock list exists yet', async () => {
    stubFetch({ 'health.json': healthAt(new Date()) })
    renderAt('/screener')
    expect(await screen.findByText(/has not been published yet/)).toBeInTheDocument()
  })
})

describe('stock page', () => {
  it('shows real stats and freshness for a stock', async () => {
    stubFetch(ALL())
    renderAt('/stock/AAPL')
    expect(await screen.findByText('Eligible for signals')).toBeInTheDocument()
    expect(screen.getByText(/Apple Inc/)).toBeInTheDocument()
    expect(screen.getByText('Daily prices (Yahoo Finance via yfinance)')).toBeInTheDocument()
    expect(screen.getByText('Returns (dividends included)')).toBeInTheDocument()
  })

  it('loads Windows-reserved tickers from their safe file name', async () => {
    stubFetch(ALL())
    renderAt('/stock/CON')
    expect(await screen.findByRole('heading', { level: 1, name: /CON.*Concentra/ })).toBeInTheDocument()
  })

  it('explains an unknown ticker instead of inventing data', async () => {
    stubFetch(ALL())
    renderAt('/stock/NOPE')
    expect(await screen.findByText(/No data for NOPE/)).toBeInTheDocument()
  })
})

describe('monitoring pages', () => {
  it('scorecard shows the verified ledger', async () => {
    stubFetch(ALL())
    renderAt('/scorecard')
    expect(await screen.findByText('Hash chain verified')).toBeInTheDocument()
  })

  it('validation explains when no report exists yet', async () => {
    stubFetch(ALL())
    renderAt('/validation')
    expect(await screen.findByText(/No validation report yet/, {}, { timeout: 15000 })).toBeInTheDocument()
  }, 30000)

  it('validation shows a real report: verdict, failed checks and the single holdout', async () => {
    stubFetch({ ...ALL(), 'validation.json': validation })
    renderAt('/validation')
    expect(await screen.findByText('5 item(s) validated', {}, { timeout: 15000 })).toBeInTheDocument()
    expect(screen.getAllByText(/Deflated Sharpe ratio/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/evaluated once/).length).toBeGreaterThan(0)
    expect(screen.getByText('Ablation: drop one family at a time')).toBeInTheDocument()
  }, 30000)

  it('baseline race explains the live race before it has results', async () => {
    stubFetch(ALL())
    renderAt('/baseline-race')
    expect(await screen.findByText(/live race starts/i)).toBeInTheDocument()
  })
})
