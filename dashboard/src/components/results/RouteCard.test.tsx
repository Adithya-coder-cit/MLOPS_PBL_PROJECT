import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { makeRoute } from '../../test/mocks/fixtures'
import { RouteCard } from './RouteCard'

const thresholds = { moderate_threshold: 0.2, high_threshold: 0.4 }

describe('RouteCard', () => {
  it('renders real route values — never placeholder numbers', () => {
    const route = makeRoute({ total_time: 43, total_cost: 21.38, transfer_count: 2, score: -0.491 })
    render(<RouteCard route={route} rank={0} isRecommended thresholds={thresholds} onViewDetails={vi.fn()} />)

    expect(screen.getByText('43 min')).toBeInTheDocument()
    expect(screen.getByText('21.38 units')).toBeInTheDocument()
    expect(screen.getByText(/2 transfers/i)).toBeInTheDocument()
    expect(screen.getByText(/-0.491/)).toBeInTheDocument()
  })

  it('labels the top candidate as Recommended and alternatives by rank', () => {
    const route = makeRoute({})
    const { rerender } = render(
      <RouteCard route={route} rank={0} isRecommended thresholds={thresholds} onViewDetails={vi.fn()} />,
    )
    expect(screen.getByText('Recommended')).toBeInTheDocument()

    rerender(<RouteCard route={route} rank={1} isRecommended={false} thresholds={thresholds} onViewDetails={vi.fn()} />)
    expect(screen.getByText('Alternative 1')).toBeInTheDocument()
  })

  it('shows the model lifecycle status honestly (Candidate, not Production)', () => {
    const route = makeRoute({})
    render(<RouteCard route={route} rank={0} isRecommended thresholds={thresholds} onViewDetails={vi.fn()} />)
    expect(screen.getByText('Candidate')).toBeInTheDocument()
  })

  it('renders the backend-generated explanation text verbatim', () => {
    const route = makeRoute({ explanation: 'A specific, backend-computed explanation sentence.' })
    render(<RouteCard route={route} rank={0} isRecommended thresholds={thresholds} onViewDetails={vi.fn()} />)
    expect(screen.getByText('A specific, backend-computed explanation sentence.')).toBeInTheDocument()
  })

  it('calls onViewDetails when "View route" is clicked', async () => {
    const onViewDetails = vi.fn()
    const route = makeRoute({})
    render(<RouteCard route={route} rank={0} isRecommended thresholds={thresholds} onViewDetails={onViewDetails} />)
    await userEvent.click(screen.getByRole('button', { name: /view route/i }))
    expect(onViewDetails).toHaveBeenCalledTimes(1)
  })
})
