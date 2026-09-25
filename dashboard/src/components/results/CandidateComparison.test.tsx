import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { makeRoute } from '../../test/mocks/fixtures'
import { CandidateComparison } from './CandidateComparison'

const thresholds = { moderate_threshold: 0.2, high_threshold: 0.4 }

describe('CandidateComparison', () => {
  it('renders one row per candidate with time/cost/reliability/risk/transfers/modes/score', () => {
    const candidates = [
      makeRoute({ route_id: 'r1', total_time: 43, total_cost: 21.38, transfer_count: 2 }),
      makeRoute({ route_id: 'r2', total_time: 51, total_cost: 20.63, transfer_count: 1 }),
    ]
    render(<CandidateComparison candidates={candidates} thresholds={thresholds} />)

    expect(screen.getAllByRole('row')).toHaveLength(3) // header + 2 candidates
    expect(screen.getByText('43 min')).toBeInTheDocument()
    expect(screen.getByText('51 min')).toBeInTheDocument()
    expect(screen.getByText('21.38 units')).toBeInTheDocument()
    expect(screen.getByText('20.63 units')).toBeInTheDocument()
  })

  it('labels the first row Recommended and the rest as alternatives', () => {
    const candidates = [makeRoute({ route_id: 'r1' }), makeRoute({ route_id: 'r2' }), makeRoute({ route_id: 'r3' })]
    render(<CandidateComparison candidates={candidates} thresholds={thresholds} />)
    expect(screen.getByText('Recommended')).toBeInTheDocument()
    expect(screen.getByText('Alt. 1')).toBeInTheDocument()
    expect(screen.getByText('Alt. 2')).toBeInTheDocument()
  })
})
