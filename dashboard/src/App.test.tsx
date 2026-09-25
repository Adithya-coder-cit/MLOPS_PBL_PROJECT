import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import App from './App'
import { server } from './test/mocks/server'

const BASE = 'http://localhost:8000/api/v1'

async function searchForARoute() {
  render(<App />)
  // "Stop 40 (S0040)" appears as an <option> in BOTH the origin and
  // destination <select> (both list every stop) — wait for the origin
  // select specifically to be populated, not an ambiguous document-wide match.
  const originSelect = screen.getByLabelText(/origin/i)
  await waitFor(() => expect(within(originSelect).getByText('Stop 40 (S0040)')).toBeInTheDocument())
  await userEvent.selectOptions(originSelect, 'S0040')
  await userEvent.selectOptions(screen.getByLabelText(/destination/i), 'S0041')
  await userEvent.click(screen.getByRole('button', { name: /search routes/i }))
}

describe('App — end-to-end component flow (MSW-mocked API)', () => {
  it('shows an empty state before any search', async () => {
    render(<App />)
    expect(await screen.findByText(/search for a route to see recommendations/i)).toBeInTheDocument()
  })

  it('runs a full search and displays real API results', async () => {
    await searchForARoute()
    expect(await screen.findByText('Recommended')).toBeInTheDocument()
    expect(screen.getByText('43 min')).toBeInTheDocument()
    expect(screen.getByText(/2 routes from S0040 to S0041/i)).toBeInTheDocument()
  })

  it('shows a friendly error message when the API returns 503', async () => {
    server.use(
      http.post(`${BASE}/recommend-route`, () =>
        HttpResponse.json(
          { error: { code: 'model_unavailable', message: 'No model available', detail: {} } },
          { status: 503 },
        ),
      ),
    )
    await searchForARoute()
    expect(await screen.findByRole('alert')).toHaveTextContent(/prediction model is temporarily unavailable/i)
  })

  it('shows a friendly error for an unreachable destination', async () => {
    server.use(
      http.post(`${BASE}/recommend-route`, () =>
        HttpResponse.json(
          { error: { code: 'unreachable_destination', message: 'No route exists', detail: {} } },
          { status: 404 },
        ),
      ),
    )
    await searchForARoute()
    expect(await screen.findByRole('alert')).toHaveTextContent(/no route connects these two stops/i)
  })

  it('opens route details and can trigger adaptive rerouting end to end', async () => {
    await searchForARoute()
    await screen.findByText('Recommended')

    await userEvent.click(screen.getAllByRole('button', { name: /view route/i })[0])
    expect((await screen.findAllByText(/edge id/i)).length).toBeGreaterThan(0)

    await userEvent.click(screen.getByRole('button', { name: /adaptive rerouting/i }))
    expect(await screen.findByText(/adaptive rerouting capability/i)).toBeInTheDocument()
    expect(screen.getByText(/not a live traffic feed/i)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /apply update and recalculate/i }))
    expect(await screen.findByText('Recommendation changed.')).toBeInTheDocument()
  })

  it('displays honest model lifecycle status (Candidate, Production: No)', async () => {
    render(<App />)
    const systemSection = await screen.findByText('System')
    const panel = systemSection.closest('section')!
    expect(within(panel).getByText('Not available')).toBeInTheDocument()
    await waitFor(() => expect(within(panel).getByText('Candidate')).toBeInTheDocument())
  })
})
