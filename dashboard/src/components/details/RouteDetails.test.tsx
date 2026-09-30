import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { makeRoute, mockStops } from '../../test/mocks/fixtures'
import { buildStopLookup } from '../../lib/stopLabel'
import { RouteDetails } from './RouteDetails'

const thresholds = { moderate_threshold: 0.2, high_threshold: 0.4 }
const stopLookup = buildStopLookup(mockStops)

describe('RouteDetails', () => {
  it('renders the backend-generated explanation text verbatim', () => {
    const route = makeRoute({ explanation: 'A specific, backend-computed explanation sentence.' })
    render(<RouteDetails route={route} thresholds={thresholds} stopLookup={stopLookup} onClose={vi.fn()} onReroute={vi.fn()} />)
    expect(screen.getByText('A specific, backend-computed explanation sentence.')).toBeInTheDocument()
  })

  it('shows friendly stop names for origin, destination, and segment stops', () => {
    const route = makeRoute({ origin: 'S0040', destination: 'S0041' })
    render(<RouteDetails route={route} thresholds={thresholds} stopLookup={stopLookup} onClose={vi.fn()} onReroute={vi.fn()} />)
    expect(screen.getByText(/Origin — Stop 40/)).toBeInTheDocument()
    expect(screen.getByText(/Destination — Stop 41/)).toBeInTheDocument()
  })

  it('still shows the real edge_id for each segment', () => {
    const route = makeRoute({})
    render(<RouteDetails route={route} thresholds={thresholds} stopLookup={stopLookup} onClose={vi.fn()} onReroute={vi.fn()} />)
    expect(screen.getAllByText(/edge id/i).length).toBeGreaterThan(0)
    expect(screen.getByText('R011:1:S0040->S0019')).toBeInTheDocument()
  })

  it('calls onReroute and onClose when their buttons are clicked', async () => {
    const user = userEvent.setup()
    const onReroute = vi.fn()
    const onClose = vi.fn()
    const route = makeRoute({})
    render(<RouteDetails route={route} thresholds={thresholds} stopLookup={stopLookup} onClose={onClose} onReroute={onReroute} />)

    await user.click(screen.getByRole('button', { name: /adaptive rerouting/i }))
    expect(onReroute).toHaveBeenCalledTimes(1)

    await user.click(screen.getByRole('button', { name: /close route details/i }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
