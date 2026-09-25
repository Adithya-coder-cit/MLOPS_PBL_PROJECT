import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RiskBadge } from './RiskBadge'

const thresholds = { moderate_threshold: 0.2, high_threshold: 0.4 }

describe('RiskBadge', () => {
  it('renders the Low label and real percentage for low risk', () => {
    render(<RiskBadge disruptionRisk={0.05} thresholds={thresholds} />)
    expect(screen.getByText(/low risk/i)).toBeInTheDocument()
    expect(screen.getByText('5%')).toBeInTheDocument()
  })

  it('renders the High label for risk at/above the high threshold', () => {
    render(<RiskBadge disruptionRisk={0.82} thresholds={thresholds} />)
    expect(screen.getByText(/high risk/i)).toBeInTheDocument()
    expect(screen.getByText('82%')).toBeInTheDocument()
  })

  it('never hardcodes a label independent of the supplied thresholds', () => {
    const { rerender } = render(<RiskBadge disruptionRisk={0.3} thresholds={thresholds} />)
    expect(screen.getByText(/moderate risk/i)).toBeInTheDocument()

    rerender(<RiskBadge disruptionRisk={0.3} thresholds={{ moderate_threshold: 0.5, high_threshold: 0.9 }} />)
    expect(screen.getByText(/low risk/i)).toBeInTheDocument()
  })
})
