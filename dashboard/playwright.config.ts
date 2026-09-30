import { defineConfig } from 'playwright/test'

// Runs against the REAL running dev server + FastAPI backend — no MSW,
// no mocked routes. Start both (`npm run dev` and the uvicorn backend)
// before running `npm run test:e2e`.
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  fullyParallel: false,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5173',
    headless: true,
    screenshot: 'only-on-failure',
  },
})
