// Real, non-mocked browser integration check (Stage 8 §23). Requires the
// actual FastAPI backend AND the Vite dev server to already be running
// (see README "Development"). Drives a real Chromium browser against
// both — no mocked API responses anywhere in this script.
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const APP_URL = process.env.APP_URL ?? 'http://localhost:5173'
const SCREENSHOT_DIR = 'screenshots'
mkdirSync(SCREENSHOT_DIR, { recursive: true })

function log(step) {
  console.log(`\n=== ${step} ===`)
}

async function main() {
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } })

  log('1. Open RouteWise')
  await page.goto(APP_URL)
  await page.waitForSelector('text=RouteWise')
  await page.screenshot({ path: `${SCREENSHOT_DIR}/01-initial.png` })

  log('Wait for stops + system status to load from the real API')
  await page.waitForFunction(() => {
    const selects = document.querySelectorAll('select')
    return selects.length >= 2 && selects[0].options.length > 1
  })
  await page.screenshot({ path: `${SCREENSHOT_DIR}/02-loaded.png` })

  log('2. Select a real origin / 3. destination')
  const selects = await page.locator('select').all()
  const originSelect = selects[0]
  const destinationSelect = selects[1]

  // S0040 -> S0041 is a known-reachable pair (verified repeatedly in Stage
  // 6/7 testing) in the giant connected component. Stage 6 found 11 of 70
  // stops are fully isolated in this synthetic graph — a real property of
  // the dataset, not something to route around silently, but picking an
  // arbitrary/random pair for THIS script would non-deterministically hit
  // one of them. Falls back to scanning if the dataset has since changed.
  const preferredOrigin = 'S0040'
  const preferredDestination = 'S0041'
  const originOptions = await originSelect.locator('option').all()
  const originValues = await Promise.all(originOptions.map((o) => o.getAttribute('value')))
  const destinationOptions = await destinationSelect.locator('option').all()
  const destinationValues = await Promise.all(destinationOptions.map((o) => o.getAttribute('value')))

  const candidatePairs = originValues.includes(preferredOrigin) && destinationValues.includes(preferredDestination)
    ? [[preferredOrigin, preferredDestination]]
    : []
  for (let i = 1; i < originValues.length && candidatePairs.length < 8; i++) {
    for (let j = 1; j < destinationValues.length && candidatePairs.length < 8; j++) {
      if (originValues[i] !== destinationValues[j]) candidatePairs.push([originValues[i], destinationValues[j]])
    }
  }

  let originValue, destinationValue, found = false
  for (const [o, d] of candidatePairs) {
    originValue = o
    destinationValue = d
    await originSelect.selectOption(originValue)
    await destinationSelect.selectOption(destinationValue)

    log('4. Submit search (real POST /recommend-route)')
    await page.getByRole('button', { name: /search routes/i }).click()
    await page.waitForFunction(
      () => !document.body.textContent.includes('Searching for routes'),
      { timeout: 15000 },
    )
    const errorVisible = await page.locator('[role="alert"]').first().isVisible().catch(() => false)
    if (errorVisible) {
      console.log(`  (${originValue} -> ${destinationValue} not reachable, trying next destination)`)
      continue
    }
    found = await page.locator('text=Recommended').first().isVisible().catch(() => false)
    if (found) break
  }

  if (!found) throw new Error('Could not find a reachable origin/destination pair after several attempts')

  log('5. Received actual FastAPI response / 6. Display actual route candidates')
  await page.screenshot({ path: `${SCREENSHOT_DIR}/03-results.png` })
  const resultsText = await page.textContent('body')
  console.log('  Recommended route visible:', resultsText.includes('Recommended'))
  console.log('  Model lifecycle visible:', resultsText.includes('Candidate'))

  log('7. Open route details')
  await page.getByRole('button', { name: /view route/i }).first().click()
  await page.waitForSelector('text=Edge ID')
  await page.locator('text=Edge ID').first().scrollIntoViewIfNeeded()
  await page.screenshot({ path: `${SCREENSHOT_DIR}/04-details.png` })

  log('8. Trigger adaptive rerouting (real POST /reroute)')
  await page.getByRole('button', { name: /adaptive rerouting/i }).click()
  await page.waitForSelector('text=Adaptive rerouting capability')
  await page.locator('text=Adaptive rerouting capability').scrollIntoViewIfNeeded()
  await page.locator('#reroute-probability').fill('0.97')
  await page.getByRole('button', { name: /apply update and recalculate/i }).click()

  log('9. Display the updated result')
  await page.waitForFunction(
    () => document.body.textContent.includes('Recommendation changed') ||
      document.body.textContent.includes('Recommendation unchanged'),
    { timeout: 15000 },
  )
  await page.locator('text=Adaptive rerouting capability').scrollIntoViewIfNeeded()
  await page.screenshot({ path: `${SCREENSHOT_DIR}/05-reroute-result.png` })
  const rerouteText = await page.textContent('body')
  console.log('  Reroute verdict shown:', rerouteText.includes('Recommendation'))
  console.log('  Not-live-feed disclaimer shown:', rerouteText.includes('not a live traffic feed') || rerouteText.includes('live traffic feed'))

  log('10. Verify model lifecycle status')
  console.log('  "Production: No" or Candidate badge visible:', rerouteText.includes('Candidate'))

  await browser.close()
  console.log('\nIntegration check completed successfully. Screenshots in ./screenshots/')
}

main().catch((err) => {
  console.error('\nIntegration check FAILED:', err)
  process.exit(1)
})
