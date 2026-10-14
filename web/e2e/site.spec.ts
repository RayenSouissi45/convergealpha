import { expect, test } from '@playwright/test'

const PAGES: [string, string][] = [
  ['#/', 'Today'],
  ['#/picks', 'Picks'],
  ['#/plan', 'Plan'],
  ['#/strategies', 'Strategies'],
  ['#/screener', 'Screener'],
  ['#/screener?preset=opportunities', 'Screener'],
  ['#/screener?preset=forecast', 'Screener'],
  ['#/columns', 'Columns explained'],
  ['#/stock/AAPL', 'AAPL Apple Inc. - Common Stock'],
  ['#/compare', 'Compare'],
  ['#/portfolio', 'My portfolio'],
  ['#/scorecard', 'Scorecard'],
  ['#/baseline-race', 'Baseline race'],
  ['#/validation', 'Validation'],
  ['#/health', 'Health'],
  ['#/about', 'About & method'],
  ['#/more', 'More'],
]

for (const [hash, heading] of PAGES) {
  test(`${hash} renders without horizontal scroll or console errors`, async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', (e) => errors.push(e.message))
    page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))

    await page.goto(hash)
    await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible()
    await expect(page.getByRole('complementary', { name: 'Research mode' })).toBeVisible()

    const overflow = await page.evaluate(
      // Compare with the device width: on phones an overflow also widens the layout viewport.
      (w) => document.documentElement.scrollWidth - Math.min(w, document.documentElement.clientWidth),
      page.viewportSize()!.width,
    )
    expect(overflow).toBeLessThanOrEqual(0)
    expect(errors).toEqual([])
  })
}

test('phone bottom navigation reaches every page', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'bottom bar is phone-only')
  await page.goto('#/')
  const nav = page.getByRole('navigation', { name: 'Main' })
  await nav.getByRole('link', { name: 'Plan' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Plan' })).toBeVisible()
  await nav.getByRole('link', { name: 'More' }).click()
  await page.getByRole('link', { name: 'Strategies' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Strategies' })).toBeVisible()
  await nav.getByRole('link', { name: 'More' }).click()
  await page.getByRole('link', { name: 'Health' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Health' })).toBeVisible()
  await nav.getByRole('link', { name: 'More' }).click()
  await page.getByRole('link', { name: 'Validation' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Validation' })).toBeVisible()

  // Tap targets in the bottom bar are at least 44px tall.
  for (const box of await nav.getByRole('link').evaluateAll((els) =>
    els.map((el) => el.getBoundingClientRect().height),
  )) {
    expect(box).toBeGreaterThanOrEqual(44)
  }
})

test('missing values explain themselves on tap', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'tap behaviour')
  // Serve a market file without a regime so the "—" placeholder is on the page.
  await page.route('**/data/market.json', async (route) => {
    const res = await route.fetch()
    await route.fulfill({ json: { ...(await res.json()), regime: null } })
  })
  await page.goto('#/')
  await page.getByRole('button', { name: /Not available: The regime also needs/ }).tap()
  await expect(page.getByRole('tooltip')).toContainText('connected in build phase 2')
  const box = await page.getByRole('tooltip').boundingBox()
  const width = page.viewportSize()?.width ?? 0
  expect(box && box.x >= 0 && box.x + box.width <= width).toBeTruthy()
})

test('screener lists stocks and opens a stock page', async ({ page }) => {
  await page.goto('#/screener')
  await expect(page.getByText(/US stocks · prices as of/)).toBeVisible()
  await page.getByRole('searchbox', { name: /search/i }).fill('AAPL')
  await page.getByRole('link', { name: 'AAPL', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1, name: /AAPL/ })).toBeVisible()
  // Charts render only when scrolled into view (keeps the first load fast on phones).
  await page.getByRole('heading', { level: 2, name: 'Price' }).scrollIntoViewIfNeeded()
  await expect(page.getByRole('img', { name: /Price chart/ })).toBeVisible()
  // The chart library draws into a canvas once it loads.
  await expect(page.locator('canvas').first()).toBeVisible()
})

test('6,000-row screener stays virtualized and scrolls to the end', async ({ page }) => {
  // Test-only data: the real file's rows repeated under synthetic tickers, served by interception.
  await page.route('**/data/screener.json', async (route) => {
    const res = await route.fetch()
    const base = (await res.json()) as { fields: string[]; rows: unknown[][]; count: number }
    const ti = base.fields.indexOf('ticker')
    const rows: unknown[][] = []
    for (let i = 0; rows.length < 6000; i++) {
      const r = [...(base.rows[i % base.rows.length] as unknown[])]
      r[ti] = `T${String(i).padStart(4, '0')}`
      rows.push(r)
    }
    await route.fulfill({ json: { ...base, rows, count: rows.length } })
  })
  await page.goto('#/screener')
  await expect(page.getByText(/^6,000 shown/)).toBeVisible()
  const table = page.getByRole('table', { name: 'Stocks' })
  // Only a window of rows is in the DOM, not 6,000.
  expect(await table.getByRole('row').count()).toBeLessThan(80)

  // Scroll through the list and measure frame times.
  const stats = await table.evaluate(async (el) => {
    const frames: number[] = []
    let last = performance.now()
    let running = true
    const tick = (t: number) => {
      frames.push(t - last)
      last = t
      if (running) requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
    for (let i = 0; i < 60; i++) {
      el.scrollTop += 1200
      await new Promise((r) => requestAnimationFrame(() => r(null)))
    }
    running = false
    frames.sort((a, b) => a - b)
    return { p95: frames[Math.floor(frames.length * 0.95)] ?? 0, n: frames.length }
  })
  expect(stats.n).toBeGreaterThan(30)
  expect(stats.p95).toBeLessThan(100)

  await table.evaluate((el) => {
    el.scrollTop = el.scrollHeight
  })
  // The last of 6,000 rows (row index 6,001 counting the header) is reachable.
  await expect(table.locator('[aria-rowindex="6001"]')).toBeVisible()
})

test('long company names never widen the page', async ({ page }) => {
  const long = 'Very Long Company Name Holdings American depositary shares, each representing sixty Class A ordinary shares'
  for (const file of ['screener.json', 'today.json']) {
    await page.route(`**/data/${file}`, async (route) => {
      const res = await route.fetch()
      if (!res.ok() || !(res.headers()['content-type'] ?? '').includes('json')) return route.fulfill({ response: res })
      const json = (await res.json()) as { fields: string[]; rows: unknown[][] }
      const i = json.fields.indexOf('name')
      for (const row of json.rows) row[i] = long
      return route.fulfill({ response: res, json })
    })
  }
  const width = page.viewportSize()!.width
  for (const hash of ['#/', '#/screener', '#/compare', '#/portfolio']) {
    await page.goto(hash)
    await page.waitForLoadState('networkidle')
    // Compare with the device width: on phones an overflow also widens the layout viewport.
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth)
    expect(scrollWidth, hash).toBeLessThanOrEqual(width)
  }
})

test('screener headers show their full names (wrapped, never cut off)', async ({ page }) => {
  for (const hash of ['#/screener', '#/screener?preset=forecast']) {
    await page.goto(hash)
    await expect(page.getByRole('table', { name: 'Stocks' })).toBeVisible()
    const cut = await page.locator('[data-header-label]').evaluateAll((els) =>
      els
        .filter((el) => el.scrollWidth > el.clientWidth + 1 || el.getBoundingClientRect().height > 64)
        .map((el) => el.textContent),
    )
    expect(cut, hash).toEqual([])
  }
})

test('phone Forecast view never scrolls sideways; chips switch the horizon', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'phone layout')
  await page.goto('#/screener?preset=forecast')
  const table = page.getByRole('table', { name: 'Stocks' })
  await expect(table).toBeVisible()
  for (const h of ['1 week', '1 month', '3 months', '6 months']) {
    await page.getByRole('group', { name: 'Forecast horizon' }).getByRole('button', { name: h }).tap()
    const { sw, cw } = await table.evaluate((el) => ({ sw: el.scrollWidth, cw: el.clientWidth }))
    expect(sw, h).toBeLessThanOrEqual(cw)
    await expect(page.getByRole('columnheader')).toHaveCount(4)
  }
  // Narrowest common phone (360 px wide): still no sideways scroll.
  await page.setViewportSize({ width: 360, height: 780 })
  const { sw, cw } = await table.evaluate((el) => ({ sw: el.scrollWidth, cw: el.clientWidth }))
  expect(sw).toBeLessThanOrEqual(cw)
})

test('the finanzen.net zero choice is remembered across pages and reloads', async ({ page }) => {
  await page.goto('#/screener')
  const box = page.getByRole('checkbox', { name: /Only stocks I can buy on finanzen\.net zero/ })
  await expect(box).toBeVisible()
  test.skip(await box.isDisabled(), 'no broker list in this data')
  await box.check()
  await page.goto('#/picks')
  await expect(page.getByRole('checkbox', { name: /Only stocks I can buy/ })).toBeChecked()
  await page.reload()
  await expect(page.getByRole('checkbox', { name: /Only stocks I can buy/ })).toBeChecked()
})

test('picks: tabs, cards and the link to each stock page', async ({ page }) => {
  await page.goto('#/picks')
  await expect(page.getByText(/not guaranteed buys/)).toBeVisible()
  await page.getByRole('tab', { name: 'Most upside' }).click()
  const first = page.getByRole('list', { name: 'Most upside picks' }).getByRole('listitem').first()
  await expect(first).toBeVisible()
  await first.getByRole('link').first().click()
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(page).toHaveURL(/#\/stock\//)
})

test('new pages fit a 360 px phone without sideways scrolling', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'phone layout')
  await page.setViewportSize({ width: 360, height: 780 })
  for (const hash of ['#/plan', '#/strategies', '#/strategies/balanced', '#/strategies/high_risk?stocks=all', '#/', '#/screener?preset=opportunities', '#/stock/AAPL']) {
    await page.goto(hash)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    if (hash.startsWith('#/strategies')) {
      const give = page.getByRole('button', { name: 'Give me a strategy' })
      if (await give.isVisible()) await give.tap()
      // Open every history list and the shared rules too.
      for (const d of await page.locator('details').all()) await d.evaluate((el) => el.setAttribute('open', ''))
    }
    if (hash === '#/plan') await page.locator('details').first().evaluate((el) => el.setAttribute('open', ''))
    await page.waitForTimeout(300)
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(overflow, hash).toBeLessThanOrEqual(0)
  }
})

test('plan builder: sliders, period, amount and costs change the result', async ({ page }) => {
  await page.goto('#/plan')
  await expect(page.getByText(/Forecast used:/)).toBeVisible()
  await expect(page.getByText(/candidates fit\./)).toBeVisible()
  await page.getByRole('button', { name: '6 months' }).click()
  await expect(page.getByText(/Uses the 6-month forecast/)).toBeVisible()
  await page.getByRole('checkbox', { name: /Allow stocks that report earnings/ }).check()
  await page.getByRole('slider', { name: /Period/ }).fill('60')
  await expect(page.getByText(/is between the 1-month and 3-month forecasts/)).toBeVisible()
  await page.getByRole('spinbutton', { name: 'Amount in euros' }).fill('500')
  const best = page.getByRole('list', { name: 'Best fits' })
  await expect(best.getByRole('listitem').first()).toBeVisible()
  await expect(best.getByText(/the stock must rise/).first()).toBeVisible()
  await expect(best.getByText(/GREEN|AMBER|GREY/).first()).toBeVisible()
  // The setting is remembered.
  await page.reload()
  await expect(page.getByRole('spinbutton', { name: 'Amount in euros' })).toHaveValue('500')
})

test('opportunity badges explain themselves', async ({ page }) => {
  await page.goto('#/screener?preset=opportunities')
  const why = page.getByRole('button', { name: /^Why is .* marked/ }).first()
  await expect(why).toBeVisible()
  await why.click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('What happened')).toBeVisible()
  await expect(dialog.getByText(/What history says|Never green on news alone/).first()).toBeVisible()
})

test('strategies: leaderboard, paper-money banner and Give me a strategy', async ({ page }) => {
  await page.goto('#/strategies')
  await expect(page.getByText('Paper money only. Past and live results do not guarantee future results.')).toBeVisible()
  await expect(page.getByText(/RESEARCH MODE/).first()).toBeVisible()
  await expect(page.getByRole('list', { name: 'Strategies by value' })).toBeVisible()
  await page.getByRole('button', { name: 'Give me a strategy' }).click()
  await expect(page.getByRole('spinbutton', { name: 'Your amount in euros' })).toBeVisible()
})

test('strategies: switch to all stocks, open a strategy, compare both versions', async ({ page }) => {
  await page.goto('#/strategies')
  const board = page.getByRole('list', { name: 'Strategies by value' })
  await expect(board.getByRole('link', { name: /Best overall/ })).toContainText('KSPI')
  await page.getByText('All stocks', { exact: true }).click()
  await expect(page).toHaveURL(/stocks=all/)
  await expect(board.getByRole('link').first()).toContainText('COHU')
  await board.getByRole('link').first().click()
  await expect(page.getByRole('heading', { level: 1, name: /High risk, high reward/ })).toBeVisible()
  await expect(page.getByRole('list', { name: 'Holdings' })).toContainText('COHU')
  await page.getByRole('link', { name: 'Show the Only finanzen.net zero version' }).click()
  await expect(page).not.toHaveURL(/stocks=all/)
  await expect(page.getByRole('radio', { name: 'Only finanzen.net zero' })).toBeChecked()
  // The fixtures include a live estimate: the waiting buy filled at today's open.
  await expect(page.getByText(/LIVE/).first()).toBeVisible()
  await page.getByRole('link', { name: '← All strategies' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Strategies' })).toBeVisible()
})
