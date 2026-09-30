import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import App from './App'
import { server } from './test/mocks/server'

const BASE = 'http://localhost:8000/api/v1'

async function pickStop(user: ReturnType<typeof userEvent.setup>, fieldLabel: RegExp, query: string, optionName: RegExp) {
  const input = screen.getByLabelText(fieldLabel)
  await waitFor(() => expect(input).not.toBeDisabled())
  await user.click(input)
  await user.type(input, query)
  await user.click(await screen.findByRole('option', { name: optionName }))
}

async function searchForARoute() {
  const user = userEvent.setup()
  render(<App />)
  await pickStop(user, /^From$/i, 'Stop 40', /Stop 40/i)
  await pickStop(user, /^To$/i, 'Stop 41', /Stop 41/i)
  await user.click(screen.getByRole('button', { name: /find best routes/i }))
  return user
}

describe('App — end-to-end component flow (MSW-mocked API)', () => {
  it('shows an empty state before any search', async () => {
    render(<App />)
    expect(await screen.findByText(/search for a route to see recommendations/i)).toBeInTheDocument()
  })

  it('runs a full search and displays real API results with friendly stop names', async () => {
    await searchForARoute()
    expect(await screen.findByText('Recommended')).toBeInTheDocument()
    expect(screen.getByText('43 min')).toBeInTheDocument()
    expect(screen.getByText(/2 routes from Stop 40 to Stop 41/i)).toBeInTheDocument()
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
    expect(await screen.findByRole('alert')).toHaveTextContent(/routewise is temporarily unavailable/i)
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
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn't find a suitable route/i)
  })

  it('opens route details and can trigger adaptive rerouting end to end', async () => {
    const user = await searchForARoute()
    await screen.findByText('Recommended')

    await user.click(screen.getAllByRole('button', { name: /view journey/i })[0])
    expect((await screen.findAllByText(/edge id/i)).length).toBeGreaterThan(0)

    await user.click(screen.getByRole('button', { name: /adaptive rerouting/i }))
    expect(await screen.findByText(/adaptive rerouting capability/i)).toBeInTheDocument()
    expect(screen.getByText(/not a live traffic feed/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /apply update and recalculate/i }))
    expect(await screen.findByText('Recommendation changed.')).toBeInTheDocument()
  })

  it('never exposes model version, lifecycle, registry, or MLflow details in the user-facing dashboard', async () => {
    await searchForARoute()
    await screen.findByText('Recommended')

    for (const term of [/\bcandidate\b/i, /xgboost/i, /random forest/i, /mlflow/i, /\bf1\b/i, /production model/i, /model registry/i, /lifecycle/i]) {
      expect(screen.queryByText(term)).not.toBeInTheDocument()
    }
  })

  it('navigates between Plan Journey, Network Map, and Help via the top nav', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: 'Network Map' }))
    expect(await screen.findByText(/Every stop currently in the RouteWise dataset/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Help' }))
    expect(await screen.findByText(/Planning a journey/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Plan Journey' }))
    expect(await screen.findByText(/search for a route to see recommendations/i)).toBeInTheDocument()
  })

  it('reaches the engineering view via the footer link, kept separate from the traveler nav', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: 'Engineering view' }))
    // Lands on the Training section by default, with the real MODEL_READY
    // state (this repo's real Stage 11 artifacts report it as false).
    expect(await screen.findByText('Model Training and Evaluation')).toBeInTheDocument()
    expect(await screen.findByText('MODEL_READY = false')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Experiments' }))
    expect(await screen.findByText('xgboost_stage5')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Model Registry' }))
    expect((await screen.findAllByText('No production model')).length).toBeGreaterThan(0)

    await user.click(screen.getByRole('button', { name: '← Back to RouteWise' }))
    expect(await screen.findByText(/search for a route to see recommendations/i)).toBeInTheDocument()
  })
})
