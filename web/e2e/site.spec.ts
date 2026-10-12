import { expect, test } from '@playwright/test'

const PAGES: [string, string][] = [
  ['#/', 'Today'],
  ['#/screener', 'Screener'],
  ['#/stock/AAPL', 'AAPL'],
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
  await page.goto('#/')
  await page.getByRole('button', { name: /Not available: Needs the S&P 500/ }).tap()
  await expect(page.getByRole('tooltip')).toContainText('Connected in build phase 2')
  const box = await page.getByRole('tooltip').boundingBox()
  const width = page.viewportSize()?.width ?? 0
  expect(box && box.x >= 0 && box.x + box.width <= width).toBeTruthy()
})
