import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { makeRoute, mockStops } from '../../test/mocks/fixtures'
import { buildStopLookup } from '../../lib/stopLabel'
import { RouteCard } from './RouteCard'

const thresholds = { moderate_threshold: 0.2, high_threshold: 0.4 }
const stopLookup = buildStopLookup(mockStops)

describe('RouteCard', () => {
  it('renders real route values — never placeholder numbers', () => {
    const route = makeRoute({ total_time: 43, total_cost: 21.38, transfer_count: 2, score: -0.491 })
    render(<RouteCard route={route} rank={0} isRecommended thresholds={thresholds} stopLookup={stopLookup} onViewDetails={vi.fn()} />)

    expect(screen.getByText('43 min')).toBeInTheDocument()
    expect(screen.getByText('21.38 units')).toBeInTheDocument()
    expect(screen.getByText(/2 transfers/i)).toBeInTheDocument()
    expect(screen.getByText(/-0.491/)).toBeInTheDocument()
  })

  it('shows friendly stop names instead of raw stop IDs', () => {
    const route = makeRoute({ origin: 'S0040', destination: 'S0041' })
    render(<RouteCard route={route} rank={0} isRecommended thresholds={thresholds} stopLookup={stopLookup} onViewDetails={vi.fn()} />)
    expect(screen.getByText(/Stop 40/)).toBeInTheDocument()
    expect(screen.getByText(/Stop 41/)).toBeInTheDocument()
    expect(screen.queryByText('S0040')).not.toBeInTheDocument()
  })

  it('labels the top candidate as Recommended and alternatives by rank', () => {
    const route = makeRoute({})
    const { rerender } = render(
      <RouteCard route={route} rank={0} isRecommended thresholds={thresholds} stopLookup={stopLookup} onViewDetails={vi.fn()} />,
    )
    expect(screen.getByText('Recommended')).toBeInTheDocument()

    rerender(<RouteCard route={route} rank={1} isRecommended={false} thresholds={thresholds} stopLookup={stopLookup} onViewDetails={vi.fn()} />)
    expect(screen.getByText('Alternative 1')).toBeInTheDocument()
  })

  it('never displays model version, lifecycle, or other ML metadata', () => {
    const route = makeRoute({})
    render(<RouteCard route={route} rank={0} isRecommended thresholds={thresholds} stopLookup={stopLookup} onViewDetails={vi.fn()} />)
    expect(screen.queryByText('Candidate')).not.toBeInTheDocument()
    expect(screen.queryByText(/xgboost/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/mlflow/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/RouteWise-Disruption-Model/)).not.toBeInTheDocument()
  })

  it('calls onViewDetails when "View journey" is clicked', async () => {
    const onViewDetails = vi.fn()
    const route = makeRoute({})
    render(<RouteCard route={route} rank={0} isRecommended thresholds={thresholds} stopLookup={stopLookup} onViewDetails={onViewDetails} />)
    await userEvent.click(screen.getByRole('button', { name: /view journey/i }))
    expect(onViewDetails).toHaveBeenCalledTimes(1)
  })
})
