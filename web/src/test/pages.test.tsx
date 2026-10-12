import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../routes'
import type { Health } from '../types'
import fixture from './fixtures/health.json'

function healthAt(generatedAt: Date, overrides: Partial<Health> = {}): Health {
  return { ...(fixture as Health), generated_at: generatedAt.toISOString(), ...overrides }
}

function stubFetch(response: { status: number; body?: unknown }) {
  const fetchMock = vi.fn(async (_input: RequestInfo | URL) =>
    response.body === undefined
      ? new Response('Not found', { status: response.status, headers: { 'content-type': 'text/html' } })
      : new Response(JSON.stringify(response.body), {
          status: response.status,
          headers: { 'content-type': 'application/json' },
        }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

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
    stubFetch({ status: 200, body: healthAt(new Date()) })
    renderAt(path)
    expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeInTheDocument()
    const banner = screen.getByRole('complementary', { name: 'Research mode' })
    expect(banner).toHaveTextContent(/RESEARCH MODE — not yet validated/)
  })
})

describe('health page', () => {
  it('shows the pipeline report from health.json', async () => {
    const fetchMock = stubFetch({ status: 200, body: healthAt(new Date()) })
    renderAt('/health')
    expect(await screen.findByText(/0 of 12 data sources connected/)).toBeInTheDocument()
    expect(screen.getByText('Daily prices')).toBeInTheDocument()
    expect(screen.getAllByText(/Not connected yet · phase 1/).length).toBeGreaterThan(0)
    expect(screen.getByText('SEC_USER_AGENT')).toBeInTheDocument()
    // health.json is fetched once and shared by the whole app.
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0]?.[0])).toMatch(/data\/health\.json$/)
  })

  it('says plainly when the pipeline has not run yet', async () => {
    stubFetch({ status: 404 })
    renderAt('/health')
    expect(await screen.findByText(/has not published a health report yet/)).toBeInTheDocument()
    expect(screen.getByText('No data yet')).toBeInTheDocument()
  })

  it('warns when data is stale', async () => {
    stubFetch({ status: 200, body: healthAt(new Date(Date.now() - 5 * 86400 * 1000)) })
    renderAt('/')
    expect(await screen.findByText('Data may be out of date.')).toBeInTheDocument()
  })

  it('shows the kill-switch banner when active', async () => {
    stubFetch({
      status: 200,
      body: healthAt(new Date(), {
        kill_switch: { implemented: true, active: true, reasons: ['Drawdown −15%'] },
      }),
    })
    renderAt('/')
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText(/KILL SWITCH ACTIVE/)).toBeInTheDocument()
    expect(within(alert).getByText(/Drawdown −15%/)).toBeInTheDocument()
  })
})

describe('missing values', () => {
  it('explain themselves when tapped', async () => {
    stubFetch({ status: 200, body: healthAt(new Date()) })
    renderAt('/')
    const dash = await screen.findByRole('button', { name: /Not available: Needs the S&P 500/ })
    expect(dash).toHaveTextContent('—')
    await userEvent.click(dash)
    expect(screen.getByRole('tooltip')).toHaveTextContent(/Connected in build phase 2/)
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })
})
