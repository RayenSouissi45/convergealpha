import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { resetScreenerCache } from '../lib/screener'
import { resetSettings } from '../lib/settings'
import { AppRoutes } from '../routes'
import type { Health } from '../types'
import healthFixture from './fixtures/health.json'
import screener from './fixtures/screener.json'
import aapl from './fixtures/stocks/AAPL.json'

const health = (): Health => ({ ...(healthFixture as unknown as Health), generated_at: new Date().toISOString(), fx_check: { latest: { ECB_USD: { rate: 1.1, date: '2026-10-13' } }, max_gap_30d: 0.001, ok: true, limit: 0.005 } })

function stubFetch() {
  const files: Record<string, unknown> = { 'health.json': health(), 'screener.json': screener, 'stocks/AAPL.json': aapl }
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const name = Object.keys(files).find((f) => String(input).endsWith(`data/${f}`))
      if (!name) return new Response('Not found', { status: 404, headers: { 'content-type': 'text/html' } })
      return new Response(JSON.stringify(files[name]), { status: 200, headers: { 'content-type': 'application/json' } })
    }),
  )
}

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  )

beforeEach(() => {
  resetScreenerCache()
  resetSettings()
  localStorage.clear()
})

describe('portfolio: a journal of your real trades', () => {
  it('logs a buy with its reason and checks, then shows it as a holding in euros', async () => {
    stubFetch()
    const user = userEvent.setup()
    renderAt('/portfolio?tab=log&t=AAPL&shares=2')
    expect(await screen.findByRole('heading', { name: 'Before you trade' })).toBeInTheDocument()
    await user.type(screen.getByRole('spinbutton', { name: 'Price per share (€)' }), '300')
    // 2 x 300 € = 600 €: free on finanzen.net zero.
    expect(screen.getByText((_, el) => el?.tagName === 'P' && /= €600\.00, fee €0\.00/.test(el.textContent ?? ''))).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: 'Fee (€)' })).toHaveAttribute('placeholder', '0.00')
    await user.type(screen.getByRole('textbox', { name: /Why\?/ }), 'BUY label and strong evidence')
    const checks = screen.getByRole('list', { name: 'Checks' })
    expect(within(checks).getByText(/Order of 600 €/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Save to my journal' }))
    const positions = await screen.findByRole('list', { name: 'Positions' })
    expect(within(positions).getByRole('link', { name: 'AAPL' })).toBeInTheDocument()
    // 340.97 $ at 1.10 $/€: 2 shares worth 619.95 €.
    expect(within(positions).getByText('€619.95')).toBeInTheDocument()
    expect(within(positions).getByRole('list', { name: "AAPL: I'm wrong if" })).toBeInTheDocument()
    expect(screen.getByText(/A bad month \(1 in 10\)/)).toBeInTheDocument()
  })

  it('moves holdings from the old dollar portfolio and flags them for checking', async () => {
    localStorage.setItem('ca-portfolio', JSON.stringify({ version: 1, equity: 10000, peakEquity: 10000, holdings: [{ ticker: 'AAPL', shares: 3, entryPrice: 330, entryDate: '2026-09-01', exitLevel: 300, atrAtEntry: 8, p25MonthAtEntry: -0.05 }] }))
    stubFetch()
    renderAt('/portfolio')
    const positions = await screen.findByRole('list', { name: 'Positions' })
    expect(within(positions).getByText(/Moved from the old dollar portfolio/)).toBeInTheDocument()
  })

  it('journal, review, taxes and rules tabs', async () => {
    stubFetch()
    const user = userEvent.setup()
    localStorage.setItem(
      'ca-journal',
      JSON.stringify({
        version: 1,
        cashEur: 1000,
        peakEur: null,
        rules: {},
        trades: [
          { id: 'b1', date: '2026-01-05', side: 'buy', ticker: 'AAPL', shares: 10, priceEur: 200, feeEur: 0, reason: 'BUY label', wrongIf: ['label_sell'], basis: 'label' },
          { id: 's1', date: '2026-06-01', side: 'sell', ticker: 'AAPL', shares: 5, priceEur: 260, feeEur: 0, reason: 'Took part of the gain', basis: 'label' },
        ],
      }),
    )
    renderAt('/portfolio?tab=journal')
    const trades = await screen.findByRole('list', { name: 'Trades' })
    expect(within(trades).getAllByRole('listitem')).toHaveLength(2)
    expect(within(trades).getByText('+€300.00')).toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'Taxes' }))
    expect(await screen.findByRole('heading', { name: 'Taxes by year (estimate)' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '2026' })).toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'Review' }))
    expect(await screen.findByRole('heading', { name: 'Decisions, not just results' })).toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'My rules' }))
    expect(await screen.findByRole('spinbutton', { name: 'Most in one stock (%)' })).toHaveValue(15)
  })
})
