import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { makeRoute, mockStops, mockSystemStatus } from '../test/mocks/fixtures'
import { buildStopLookup } from '../lib/stopLabel'
import type { SavedTrip } from '../lib/savedTrips'
import { MyTripsPage } from './MyTripsPage'

const thresholds = mockSystemStatus.risk_label_thresholds
const stopLookup = buildStopLookup(mockStops)

function makeTrip(overrides: Partial<SavedTrip> = {}): SavedTrip {
  return {
    id: 'trip-1',
    savedAt: '2026-09-30T12:00:00.000Z',
    origin: 'S0040',
    destination: 'S0041',
    route: makeRoute({}),
    ...overrides,
  }
}

describe('MyTripsPage', () => {
  it('shows an honest empty state with no saved trips', () => {
    render(<MyTripsPage trips={[]} thresholds={thresholds} stopLookup={stopLookup} onDelete={vi.fn()} />)
    expect(screen.getByText(/no saved trips yet/i)).toBeInTheDocument()
  })

  it('lists a saved trip using its real saved route data', () => {
    render(<MyTripsPage trips={[makeTrip()]} thresholds={thresholds} stopLookup={stopLookup} onDelete={vi.fn()} />)
    expect(screen.getByText(/Stop 40/)).toBeInTheDocument()
    expect(screen.getByText(/Stop 41/)).toBeInTheDocument()
  })

  it('opens a saved trip to show its journey details', async () => {
    const user = userEvent.setup()
    render(<MyTripsPage trips={[makeTrip()]} thresholds={thresholds} stopLookup={stopLookup} onDelete={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: 'Open' }))
    expect(screen.getAllByText(/edge id/i).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /adaptive rerouting/i })).toBeInTheDocument()
  })

  it('deletes a saved trip', async () => {
    const user = userEvent.setup()
    const onDelete = vi.fn()
    render(<MyTripsPage trips={[makeTrip()]} thresholds={thresholds} stopLookup={stopLookup} onDelete={onDelete} />)

    await user.click(screen.getByRole('button', { name: 'Delete' }))
    expect(onDelete).toHaveBeenCalledWith('trip-1')
  })
})
