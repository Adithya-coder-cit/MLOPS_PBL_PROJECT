import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const APP_URL = process.env.APP_URL ?? 'http://localhost:5173'
mkdirSync('screenshots', { recursive: true })

const viewports = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'laptop', width: 1280, height: 800 },
  { name: 'tablet', width: 834, height: 1112 },
]

async function main() {
  const browser = await chromium.launch()
  for (const vp of viewports) {
    const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } })
    await page.goto(APP_URL)
    await page.waitForFunction(() => {
      const selects = document.querySelectorAll('select')
      return selects.length >= 2 && selects[0].options.length > 1
    })
    await page.screenshot({ path: `screenshots/responsive-${vp.name}.png`, fullPage: false })
    await page.close()
    console.log(`captured ${vp.name} (${vp.width}x${vp.height})`)
  }
  await browser.close()
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
