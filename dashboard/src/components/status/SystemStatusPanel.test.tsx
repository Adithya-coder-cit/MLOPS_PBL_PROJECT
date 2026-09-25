import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { mockSystemStatus } from '../../test/mocks/fixtures'
import { SystemStatusPanel } from './SystemStatusPanel'

describe('SystemStatusPanel', () => {
  it('shows a loading state', () => {
    render(<SystemStatusPanel status="loading" data={null} error={null} onRetry={vi.fn()} />)
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('shows an error state with a retry action', () => {
    const onRetry = vi.fn()
    render(<SystemStatusPanel status="error" data={null} error={new Error('boom')} onRetry={onRetry} />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })

  it('honestly displays that production is not available and candidate is', () => {
    render(<SystemStatusPanel status="success" data={mockSystemStatus} error={null} onRetry={vi.fn()} />)
    expect(screen.getByText('Not available')).toBeInTheDocument()
    expect(screen.getByText('Candidate')).toBeInTheDocument()
    expect(screen.getByText('RouteWise-Disruption-Model')).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
  })

  it('never claims monitoring is healthy — shows the real monitoring decision', () => {
    render(<SystemStatusPanel status="success" data={mockSystemStatus} error={null} onRetry={vi.fn()} />)
    expect(screen.getByText(/review required/i)).toBeInTheDocument()
    expect(screen.queryByText(/healthy/i)).not.toBeInTheDocument()
  })

  it('shows "Never run" when no monitoring run has ever completed', () => {
    const notRun = {
      ...mockSystemStatus,
      monitoring: { ...mockSystemStatus.monitoring, available: false, decision: 'NOT_RUN' },
    }
    render(<SystemStatusPanel status="success" data={notRun} error={null} onRetry={vi.fn()} />)
    expect(screen.getByText(/never run/i)).toBeInTheDocument()
  })
})
