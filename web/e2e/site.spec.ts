import { expect, test } from '@playwright/test'

const PAGES: [string, string][] = [
  ['#/', 'Today'],
  ['#/screener', 'Screener'],
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
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(0)
    expect(errors).toEqual([])
  })
}

test('phone bottom navigation reaches every page', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'bottom bar is phone-only')
  await page.goto('#/')
  const nav = page.getByRole('navigation', { name: 'Main' })
  await nav.getByRole('link', { name: 'Health' }).click()
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
  await expect(page.getByText('6,000 shown')).toBeVisible()
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
