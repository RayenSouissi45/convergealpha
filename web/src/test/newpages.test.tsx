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
import { byValue, liveOf, planned, statusOf, twinOf, withLive } from '../lib/strategies'
import { AppRoutes } from '../routes'
import type { Health, OpportunitiesFile, Opportunity, StrategiesFile, StrategiesLiveFile } from '../types'
import health from './fixtures/health.json'
import opportunities from './fixtures/opportunities.json'
import plan from './fixtures/plan.json'
import strategies from './fixtures/strategies.json'
import strategiesLive from './fixtures/strategies_live.json'

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
  const f = strategies as unknown as StrategiesFile

  it('shows each strategy at a glance: value, return, what the money is in', async () => {
    stubFetch(FILES())
    renderAt('/strategies')
    expect(await screen.findByRole('heading', { level: 1, name: 'Strategies' })).toBeInTheDocument()
    expect(screen.getByText('Paper money only. Past and live results do not guarantee future results.')).toBeInTheDocument()
    expect(await screen.findByText(/RESEARCH MODE — not yet proven live/)).toBeInTheDocument()
    // finanzen.net zero by default: the versions you can copy.
    expect(screen.getByRole('radio', { name: 'Only finanzen.net zero' })).toBeChecked()
    const board = screen.getByRole('list', { name: 'Strategies by value' })
    const tiles = within(board).getAllByRole('listitem', { name: (_, el) => el.parentElement === board })
    expect(tiles).toHaveLength(f.strategies.length)
    const balanced = within(board).getByRole('link', { name: /Best overall \(Balanced\)/ })
    expect(balanced).toHaveAttribute('href', '/strategies/balanced')
    expect(within(balanced).getByText('Buys at the open, Oct 14')).toBeInTheDocument()
    expect(within(balanced).getByText('KSPI')).toBeInTheDocument()
    expect(within(balanced).getByText('MTG')).toBeInTheDocument()
    expect(within(balanced).getByText(/Same rules on all stocks: €200\.00/)).toBeInTheDocument()
    const hunter = within(board).getByRole('link', { name: /Opportunity hunter/ })
    expect(within(hunter).getByText('In cash')).toBeInTheDocument()
    expect(within(hunter).getByText('All in cash: no stock it may buy has a green opportunity badge today.')).toBeInTheDocument()
    expect(screen.getByText('S&P 500 yardstick')).toBeInTheDocument()
    // The long texts are folded away.
    expect(screen.getByText('How it works').closest('details')).not.toHaveAttribute('open')
  })

  it('switches to the same rules on all stocks, ranked by value', async () => {
    stubFetch(FILES())
    const user = userEvent.setup()
    renderAt('/strategies')
    await user.click(await screen.findByRole('radio', { name: 'All stocks' }))
    expect(screen.getByRole('radio', { name: 'All stocks' })).toBeChecked()
    const board = screen.getByRole('list', { name: 'Strategies by value' })
    const first = within(board).getAllByRole('link')[0]!
    expect(first).toHaveAttribute('href', '/strategies/high_risk?stocks=all')
    expect(within(first).getByText('Invested')).toBeInTheDocument()
    expect(within(first).getByText('COHU')).toBeInTheDocument()
    expect(within(first).getByText('+3.2%')).toBeInTheDocument()
    expect(within(first).getByText('€214.36')).toBeInTheDocument()
    expect(within(first).getByText(/Only finanzen\.net zero: €200\.00/)).toBeInTheDocument()
  })

  it('a strategy page shows the orders for the next open with shares, euros and why', async () => {
    stubFetch(FILES())
    const user = userEvent.setup()
    renderAt('/strategies/balanced')
    expect(await screen.findByRole('heading', { level: 1, name: /Best overall \(Balanced\)/ })).toBeInTheDocument()
    expect(screen.getByText(/No stocks yet:/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'At the next open (Oct 14, 2026)' })).toBeInTheDocument()
    const orders = screen.getByRole('list', { name: 'Orders for the next open' })
    const kspi = f.strategies[0]!.pending[0]!
    const n = kspi.est_shares!
    expect(within(orders).getByText(`about ${n} share${n === 1 ? '' : 's'} ≈ €${kspi.est_eur!.toFixed(2)}`)).toBeInTheDocument()
    await user.click(within(orders).getAllByText('Why')[0]!)
    expect(within(orders).getByText(/^Buy KSPI: #24 for this strategy/)).toBeInTheDocument()
    expect(within(orders).queryByText(/^Bought KSPI/)).not.toBeInTheDocument()
    // Both versions side by side.
    expect(screen.getByRole('heading', { name: 'finanzen.net zero vs all stocks' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Show the All stocks version' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Trade history (0)' })).toBeInTheDocument()
  })

  it('the all-stocks page shows holdings, exit levels and the trade history', async () => {
    stubFetch(FILES())
    renderAt('/strategies/high_risk?stocks=all')
    expect(await screen.findByRole('heading', { level: 1, name: /High risk, high reward/ })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'All stocks' })).toBeChecked()
    const held = screen.getByRole('list', { name: 'Holdings' })
    expect(within(held).getByRole('link', { name: 'COHU' })).toBeInTheDocument()
    expect(within(held).getByText(/3 shares · worth €206\.74/)).toBeInTheDocument()
    expect(within(held).getByText(/sells at: stop \$57\.38 · trailing stop \$60\.57 · take-profit \$78\.25 · latest in 19 trading days/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Trade history (3)' })).toBeInTheDocument()
    expect(screen.getByText('+€8.60 (+4.6%)')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Show the Only finanzen.net zero version' })).toBeInTheDocument()
  })

  it('“Give me a strategy” uses your amount and marks the best overall', async () => {
    stubFetch(FILES())
    const user = userEvent.setup()
    renderAt('/strategies')
    await user.click(await screen.findByRole('button', { name: 'Give me a strategy' }))
    const amount = screen.getByRole('spinbutton', { name: 'Your amount in euros' })
    expect(amount).toHaveValue(200)
    expect(screen.getAllByText(/Best overall/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Chance of more money after costs/).length).toBeGreaterThan(0)
  })
})

describe('strategy status at a glance', () => {
  const f = strategies as unknown as StrategiesFile
  const base = f.strategies[0]!

  it('says whether the money is in cash, waiting to buy, invested or changing', () => {
    expect(statusOf(base)).toMatchObject({ kind: 'buying', tone: 'warn', label: 'Buys at the open, Oct 14' })
    expect(statusOf(base).text).toBe('All in cash now; buys 2 stocks at the open on Oct 14, 2026.')
    const hr = f.strategies_all!.find((x) => x.id === 'high_risk')!
    expect(statusOf(hr)).toMatchObject({ kind: 'invested', tone: 'good', label: 'Invested', text: 'Holds 1 stock.' })
    const changing = { ...hr, pending: [{ ...base.pending[0]!, side: 'sell' as const, ticker: 'COHU' }] }
    expect(statusOf(changing)).toMatchObject({ kind: 'changing', text: 'Holds 1 stock; sells 1 at the open on Oct 14, 2026.' })
    const cash = { ...base, pending: [], notes: ['Skipped: AAA (too expensive).', 'No buy: nothing else it may buy fits today. The money stays in cash.'] }
    expect(statusOf(cash)).toMatchObject({ kind: 'cash', text: 'All in cash: nothing else it may buy fits today.' })
    expect(statusOf({ ...base, locked: 'changed' }).kind).toBe('locked')
  })

  it('ranks by value and keeps the fixed order on ties; reasons read as plans before the fill', () => {
    const [a, b, c] = f.strategies
    const ranked = byValue([a!, b!, { ...c!, value: 250 }])
    expect(ranked.map((x) => x.id)).toEqual([c!.id, a!.id, b!.id])
    expect(planned('Bought KSPI: #1')).toBe('Buy KSPI: #1')
    expect(planned('Sold KSPI to switch into MTG: x')).toBe('Sell KSPI to switch into MTG: x')
    expect(twinOf(f, a!)?.key).toBe('balanced-all-v1')
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
    for (const id of ['plan-shares', 'plan-leftover', 'plan-fees', 'plan-breakeven', 'plan-chance', 'plan-right', 'plan-results', 'plan-verdict', 'strat-value', 'strat-vs', 'strat-fees', 'strat-win', 'strat-drop', 'strat-cash', 'strat-levels', 'strat-universe', 'strat-status', 'strat-estimate']) {
      expect(ids).toContain(id)
    }
  })
})

describe('live strategies during US trading hours', () => {
  const f = strategies as unknown as StrategiesFile
  const live = strategiesLive as unknown as StrategiesLiveFile

  it('only uses a live estimate made on top of these official numbers, once trading started', () => {
    expect(liveOf(f, live)).toBe(live)
    expect(liveOf(f, { ...live, official_as_of: '2026-10-12' })).toBeNull()
    expect(liveOf(f, { ...live, market: 'pre-open' })).toBeNull()
    expect(liveOf(f, null)).toBeNull()
  })

  it('lays the estimate over the card: filled orders become holdings with exit levels', () => {
    const card = withLive(f.strategies[0]!, live)
    expect(card.live).toBe(true)
    expect(card.pending).toEqual([])
    expect(card.holdings.map((h) => h.ticker)).toEqual(['KSPI', 'MTG'])
    const kspi = card.holdings[0]!
    expect(kspi.entry_usd).toBe(85)
    expect(kspi.levels.stop_usd).toBeCloseTo(85 * 0.94)
    expect(kspi.levels.take_profit_usd).toBeCloseTo(85 * 1.08)
    expect(card.value).toBeCloseTo(live.strategies['balanced-v1']!.value)
    expect(statusOf(card).label).toBe('Invested')
  })

  it('the page says LIVE with the time, and tiles show live values', async () => {
    stubFetch({ ...FILES(), 'strategies_live.json': live })
    renderAt('/strategies')
    const line = await screen.findByText(/Updated .* New York, every 30 minutes/)
    expect(line).toBeInTheDocument()
    const board = screen.getByRole('list', { name: 'Strategies by value' })
    const hr = within(board).getByRole('link', { name: /High risk, high reward/ })
    expect(within(hr).getByText('€202.72')).toBeInTheDocument()
    expect(within(hr).getByText('LIVE')).toBeInTheDocument()
    expect(within(hr).getByText('Invested')).toBeInTheDocument()
  })
})
