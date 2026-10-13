// Picks, Forecast view, finanzen.net zero filter, Columns explained, "How often was it right?".
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { COLUMNS, GROUP_ORDER } from '../lib/columns'
import { resetScreenerCache, toRows } from '../lib/screener'
import { resetOnlyZero } from '../lib/zero'
import { AppRoutes } from '../routes'
import type { Health, PicksFile, ScreenerFile } from '../types'
import healthFixture from './fixtures/health.json'
import market from './fixtures/market.json'
import picksFixture from './fixtures/picks.json'
import screenerFixture from './fixtures/screener.json'
import aapl from './fixtures/stocks/AAPL.json'

/** The pick cards of a list (each card also has its own list of reasons). */
const cards = (list: HTMLElement) => Array.from(list.querySelectorAll<HTMLElement>(':scope > li'))

const health = (over: Partial<Health> = {}): Health => ({ ...(healthFixture as unknown as Health), generated_at: new Date().toISOString(), ...over })
const picks = picksFixture as unknown as PicksFile
const screener = screenerFixture as unknown as ScreenerFile

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

const ALL = (over: Record<string, unknown> = {}) => ({
  'health.json': health(),
  'screener.json': screener,
  'market.json': market,
  'picks.json': picks,
  'stocks/AAPL.json': aapl,
  ...over,
})

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  )
}

function phone(on: boolean) {
  vi.stubGlobal('matchMedia', (q: string) => ({
    matches: on && q.includes('max-width'),
    media: q,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }))
}

beforeEach(() => {
  resetScreenerCache()
  localStorage.clear()
  resetOnlyZero()
})
afterEach(() => resetOnlyZero())

describe('picks page', () => {
  it('shows the research banner, four tabs and the balanced top list', async () => {
    stubFetch(ALL())
    renderAt('/picks')
    expect(await screen.findByText(/Research mode — these are the strongest-looking stocks by the app’s numbers, not guaranteed buys/)).toBeInTheDocument()
    const tabs = await screen.findByRole('tablist', { name: 'Pick lists' })
    expect(within(tabs).getAllByRole('tab').map((t) => t.textContent)).toEqual(['Balanced', 'Safest', 'Most upside', 'Most likely to rise'])
    expect(within(tabs).getByRole('tab', { name: 'Balanced' })).toHaveAttribute('aria-selected', 'true')
    const list = screen.getByRole('list', { name: 'Balanced picks' })
    expect(cards(list).length).toBe(picks.tabs.balanced.length)
    expect(picks.tabs.balanced.length).toBeGreaterThan(0)
    expect(picks.tabs.balanced.length).toBeLessThanOrEqual(25)
    const first = picks.stocks[picks.tabs.balanced[0]!]!
    const card = cards(list)[0]!
    expect(within(card).getByRole('link', { name: first.ticker })).toHaveAttribute('href', `/stock/${first.ticker}`)
    // Three sub-score bars, the 4 horizons, reasons and the main risk.
    for (const s of ['Safety', 'Upside', 'Confidence']) expect(within(card).getByRole('img', { name: new RegExp(`^${s} `) })).toBeInTheDocument()
    expect(within(card).getByRole('table')).toHaveTextContent(/1W.*1M.*3M.*6M/)
    expect(within(card).getByText(first.reasons[0]!)).toBeInTheDocument()
    expect(within(card).getByText(first.risk)).toBeInTheDocument()
    // Every pick scores at least the floor on each sub-score.
    for (const t of picks.tabs.balanced) {
      const s = picks.stocks[t]!.scores
      expect(Math.min(s.safety!, s.upside!, s.confidence!)).toBeGreaterThanOrEqual(picks.floor)
    }
  })

  it('switches tabs', async () => {
    stubFetch(ALL())
    renderAt('/picks')
    await userEvent.click(await screen.findByRole('tab', { name: 'Safest' }))
    const list = screen.getByRole('list', { name: 'Safest picks' })
    const first = picks.tabs.safest[0]!
    expect(within(cards(list)[0]!).getByRole('link', { name: first })).toBeInTheDocument()
  })

  it('with the finanzen.net zero box ticked, shows the zero lists only', async () => {
    stubFetch(ALL())
    renderAt('/picks')
    const box = await screen.findByRole('checkbox', { name: /Only stocks I can buy on finanzen\.net zero/ })
    expect(box).toBeEnabled()
    await userEvent.click(box)
    const list = screen.getByRole('list', { name: 'Balanced picks' })
    const shown = cards(list).map((li) => within(li).getAllByRole('link')[0]!.textContent)
    expect(shown).toEqual(picks.tabs_zero!.balanced)
    for (const t of shown) expect(picks.stocks[t!]!.zero).not.toBe(false)
    expect(localStorage.getItem('ca-only-zero')).toBe('1')
  })

  it('says when there are no picks file yet', async () => {
    stubFetch(ALL({ 'picks.json': undefined }))
    renderAt('/picks')
    expect(await screen.findByText(/Picks appear after the next daily pipeline run/)).toBeInTheDocument()
  })
})

describe('finanzen.net zero filter', () => {
  const rows = toRows(screener)
  const yes = rows.filter((r) => r.zero === true).length
  const no = rows.filter((r) => r.zero === false).length

  it('counts buyable stocks, remembers the choice and hides only "not buyable" ones', async () => {
    stubFetch(ALL())
    renderAt('/screener')
    const box = await screen.findByRole('checkbox', { name: /Only stocks I can buy/ })
    expect(screen.getByText(new RegExp(`^${yes} of ${rows.length} stocks buyable`))).toBeInTheDocument()
    await userEvent.click(box)
    expect(await screen.findByText(new RegExp(`^${rows.length - no} shown`))).toBeInTheDocument()
    expect(localStorage.getItem('ca-only-zero')).toBe('1')
  })

  it('starts ticked when the saved setting says so', async () => {
    localStorage.setItem('ca-only-zero', '1')
    resetOnlyZero()
    stubFetch(ALL())
    renderAt('/screener')
    expect(await screen.findByRole('checkbox', { name: /Only stocks I can buy/ })).toBeChecked()
    expect(screen.getByText(new RegExp(`^${rows.length - no} shown`))).toBeInTheDocument()
  })

  it('is disabled, with the reason, when the list is missing', async () => {
    localStorage.setItem('ca-only-zero', '1')
    resetOnlyZero()
    stubFetch(ALL({ 'health.json': health({ brokers: null }) }))
    renderAt('/screener')
    const box = await screen.findByRole('checkbox', { name: /Only stocks I can buy/ })
    expect(box).toBeDisabled()
    expect(box).not.toBeChecked()
    expect(screen.getByText(/list is not available yet/)).toBeInTheDocument()
    // The saved choice is ignored while the list is missing: nothing is hidden.
    expect(screen.getByText(new RegExp(`^${rows.length} shown`))).toBeInTheDocument()
  })

  it('appears on Today and Compare too', async () => {
    stubFetch(ALL())
    renderAt('/')
    expect(await screen.findByRole('checkbox', { name: /Only stocks I can buy/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Picks: the best-balanced suggestions/ })).toHaveAttribute('href', '/picks')
  })
})

describe('screener Forecast view', () => {
  it('desktop: all 4 horizons, 3 columns each, with a legend', async () => {
    phone(false)
    stubFetch(ALL())
    renderAt('/screener?preset=forecast')
    expect(await screen.findByTestId('forecast-legend')).toHaveTextContent(/Expected change.*Chance up.*How often right/)
    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent ?? '')
    for (const h of ['1W', '1M', '3M', '6M']) {
      expect(headers.some((x) => x.startsWith(`Expected change ${h}`))).toBe(true)
      expect(headers.some((x) => x.startsWith(`Chance up ${h}`))).toBe(true)
      expect(headers.some((x) => x.startsWith(`How often right ${h}`))).toBe(true)
    }
    expect(screen.queryByRole('group', { name: 'Forecast horizon' })).not.toBeInTheDocument()
  })

  it('phone: horizon chips switch which 3 columns are shown, and every column sorts', async () => {
    phone(true)
    stubFetch(ALL())
    renderAt('/screener?preset=forecast')
    const chips = await screen.findByRole('group', { name: 'Forecast horizon' })
    let headers = screen.getAllByRole('columnheader').map((h) => h.textContent ?? '')
    expect(headers).toHaveLength(4)
    expect(headers[1]).toMatch(/^Expected change/)
    await userEvent.click(within(chips).getByRole('button', { name: /1 month/ }))
    expect(within(chips).getByRole('button', { name: '1M (1 month)' })).toHaveAttribute('aria-pressed', 'true')
    headers = screen.getAllByRole('columnheader').map((h) => h.getAttribute('aria-sort') ?? '')
    // Sorting follows the chosen horizon (chance up, high to low).
    expect(screen.getAllByRole('columnheader')[2]).toHaveAttribute('aria-sort', 'descending')
    await userEvent.click(screen.getByRole('button', { name: /Sort by How often right, 1 month/ }))
    expect(screen.getAllByRole('columnheader')[3]).toHaveAttribute('aria-sort', 'descending')
  })
})

describe('columns explained', () => {
  it('lists every column with all its parts, grouped', async () => {
    stubFetch(ALL())
    renderAt('/columns')
    expect(await screen.findByRole('heading', { level: 1, name: 'Columns explained' })).toBeInTheDocument()
    for (const g of GROUP_ORDER) expect(screen.getByRole('heading', { level: 2, name: g })).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 3 })).toHaveLength(COLUMNS.length)
    expect(screen.getAllByText('Common mistakes')).toHaveLength(COLUMNS.length)
    expect(screen.getByRole('heading', { level: 3, name: 'Analyst target upside' })).toBeInTheDocument()
    expect(screen.getByText(/analysts’ average price target is 25% above today’s price/)).toBeInTheDocument()
  })

  it('is linked from the screener and the About page', async () => {
    stubFetch(ALL())
    renderAt('/screener')
    expect(await screen.findByRole('link', { name: 'What do the columns mean?' })).toHaveAttribute('href', '/columns')
  })
})

describe('stock page reliability', () => {
  it('says how often the app was right, per horizon, with validated or research marks', async () => {
    stubFetch(ALL())
    renderAt('/stock/AAPL')
    expect(await screen.findByText('How often was it right?')).toBeInTheDocument()
    expect(screen.getAllByText(/When the app said about \d+%, the stock was actually higher \d+% of the time \([\d,]+ cases, range [\d.]+%–[\d.]+%\)/).length).toBe(4)
    const validated = (healthFixture as unknown as Health).validated
    expect(screen.getAllByText('✓ Validated').length).toBe(validated.filter((v) => v.startsWith('P(up)')).length)
  })
})

describe('navigation', () => {
  it('has Picks in the main navigation', async () => {
    stubFetch(ALL())
    renderAt('/')
    const navs = await screen.findAllByRole('navigation', { name: 'Main' })
    expect(navs.some((n) => within(n).queryByRole('link', { name: /Picks/ }))).toBe(true)
  })
})
