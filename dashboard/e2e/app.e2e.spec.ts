import { expect, test } from 'playwright/test'

// End-to-end pass against the REAL running app: the live Vite dev server
// (http://localhost:5173) talking to the real FastAPI backend
// (http://localhost:8000). No MSW, no mocked routes — every assertion
// below is against data that actually came back from the backend.

test.describe('RouteWise — real backend end to end', () => {
  const consoleErrors: string[] = []

  test.beforeEach(({ page }) => {
    consoleErrors.length = 0
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })
    page.on('pageerror', (err) => consoleErrors.push(err.message))
  })

  test.afterEach(() => {
    expect(consoleErrors, `Uncaught browser console errors: ${consoleErrors.join('\n')}`).toEqual([])
  })

  test('open dashboard, confirm API online, and stops load', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('API online')).toBeVisible({ timeout: 10_000 })

    const fromInput = page.getByRole('combobox', { name: 'From' })
    await expect(fromInput).toBeEnabled({ timeout: 10_000 })
  })

  test('full journey: search, results, route details, and reroute', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('API online')).toBeVisible({ timeout: 10_000 })

    const fromInput = page.getByRole('combobox', { name: 'From' })
    await expect(fromInput).toBeEnabled({ timeout: 10_000 })
    await fromInput.click()
    await fromInput.fill('Stop 40')
    await page.getByRole('option', { name: /Stop 40/i }).first().click()

    const toInput = page.getByRole('combobox', { name: 'To' })
    await toInput.click()
    await toInput.fill('Stop 41')
    await page.getByRole('option', { name: /Stop 41/i }).first().click()

    await page.getByRole('button', { name: /find best routes/i }).click()

    // Real API round trip — wait for the actual results heading.
    await expect(page.getByText(/routes from Stop 40 to Stop 41/i)).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('Recommended')).toBeVisible()
    await expect(page.getByRole('button', { name: /view journey/i }).first()).toBeVisible()

    // No ML/model jargon anywhere in the results.
    for (const term of ['XGBoost', 'MLflow', 'Random Forest']) {
      await expect(page.getByText(term)).toHaveCount(0)
    }

    await page.getByRole('button', { name: /view journey/i }).first().click()
    await expect(page.getByText(/edge id/i).first()).toBeVisible()
    await expect(page.locator('svg[aria-label*="Schematic map"]')).toBeVisible()

    await page.getByRole('button', { name: /adaptive rerouting/i }).click()
    await expect(page.getByText(/not a live traffic feed/i)).toBeVisible()

    await page.getByRole('button', { name: /apply update and recalculate/i }).click()
    await expect(page.getByText(/^Recommendation (changed|unchanged)\.$/)).toBeVisible({ timeout: 15_000 })
  })

  test('network map shows the real stop list plotted from real coordinates, with working zoom and route highlighting', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Network Map' }).click()
    await expect(page.getByText(/\d+ stops/)).toBeVisible({ timeout: 10_000 })
    const svg = page.locator('svg[aria-label*="Schematic map"]')
    await expect(svg).toBeVisible()

    // Zoom is a real viewBox change, not cosmetic.
    const initialViewBox = await svg.getAttribute('viewBox')
    await page.getByRole('button', { name: 'Zoom in' }).click()
    await expect(async () => {
      expect(await svg.getAttribute('viewBox')).not.toBe(initialViewBox)
    }).toPass({ timeout: 5_000 })

    // Selecting a real route (from the live /network/routes data) highlights it.
    const picker = page.getByLabel(/highlight a real route/i)
    await picker.selectOption({ index: 1 })
    await expect(page.locator('svg[aria-label*="Schematic map of route"]')).toBeVisible({ timeout: 10_000 })
  })

  test('My Trips: save a real searched route, reopen it, then delete it', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('API online')).toBeVisible({ timeout: 10_000 })

    const fromInput = page.getByRole('combobox', { name: 'From' })
    await expect(fromInput).toBeEnabled({ timeout: 10_000 })
    await fromInput.click()
    await fromInput.fill('Stop 40')
    await page.getByRole('option', { name: /Stop 40/i }).first().click()

    const toInput = page.getByRole('combobox', { name: 'To' })
    await toInput.click()
    await toInput.fill('Stop 41')
    await page.getByRole('option', { name: /Stop 41/i }).first().click()

    await page.getByRole('button', { name: /find best routes/i }).click()
    await expect(page.getByText(/routes from Stop 40 to Stop 41/i)).toBeVisible({ timeout: 15_000 })

    await page.getByRole('button', { name: /view journey/i }).first().click()
    await page.getByRole('button', { name: /save trip/i }).click()
    await expect(page.getByRole('button', { name: /saved/i })).toBeVisible()

    await page.getByRole('button', { name: 'My Trips' }).click()
    await expect(page.getByText(/no saved trips yet/i)).toHaveCount(0)
    await expect(page.getByText(/Stop 40/).first()).toBeVisible()

    await page.getByRole('button', { name: 'Open' }).click()
    await expect(page.getByText(/edge id/i).first()).toBeVisible()
    await page.getByRole('button', { name: 'Close route details' }).click()

    await page.getByRole('button', { name: 'Delete' }).click()
    await expect(page.getByText(/no saved trips yet/i)).toBeVisible()
  })

  test('help page loads static, honest content', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Help' }).click()
    await expect(page.getByText(/app is honest about that everywhere it matters/i)).toBeVisible()
  })

  test('engineering view: Training shows real MODEL_READY state, Experiments/Registry show real MLflow data', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Engineering view' }).click()

    // Lands on Training by default with the real (currently false) readiness gate.
    await expect(page.getByText('Model Training and Evaluation')).toBeVisible()
    await expect(page.getByText(/MODEL_READY/)).toBeVisible()

    await page.getByRole('button', { name: 'Overview' }).click()
    await expect(page.getByText('Production model')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('Model information')).toBeVisible()
    await expect(page.getByText('Validation metrics', { exact: true })).toBeVisible({ timeout: 10_000 })

    await page.getByRole('button', { name: 'Experiments' }).click()
    // This repo's ./mlruns store has real logged runs from earlier stages.
    await expect(page.locator('table')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('xgboost_stage5').first()).toBeVisible()

    await page.getByRole('button', { name: 'Model Registry' }).click()
    await expect(page.getByText('RouteWise-Disruption-Model')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('No production model').first()).toBeVisible()

    await page.getByRole('button', { name: 'Data' }).click()
    await expect(page.getByText(/Total real records/i)).toBeVisible({ timeout: 10_000 })

    await page.getByRole('button', { name: 'Evaluation' }).click()
    await expect(page.getByText(/Confusion matrix/i)).toBeVisible({ timeout: 10_000 })

    await page.getByRole('button', { name: 'Monitoring' }).click()
    await expect(page.getByText('Data (DVC)')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('Monitoring decision')).toBeVisible()

    // Scoped to the engineering sidebar's own Help tab — the page's header
    // nav has an unrelated traveler-facing "Help" button too.
    const adminNav = page.getByRole('navigation', { name: 'Engineering sections' })
    await adminNav.getByRole('button', { name: 'Help' }).click()
    await expect(page.getByText(/engineering/i).first()).toBeVisible()

    await page.getByRole('button', { name: '← Back to RouteWise' }).click()
    await expect(page.getByText(/search for a route to see recommendations/i)).toBeVisible()
  })
})
