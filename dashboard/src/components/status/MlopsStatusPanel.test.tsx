import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { mockSystemStatus } from '../../test/mocks/fixtures'
import { MlopsStatusPanel } from './MlopsStatusPanel'

describe('MlopsStatusPanel', () => {
  it('shows the real per-category monitoring statuses, not a fabricated healthy default', () => {
    render(<MlopsStatusPanel data={mockSystemStatus} />)
    expect(screen.getByText('PASS')).toBeInTheDocument()
    expect(screen.getByText('DRIFT DETECTED')).toBeInTheDocument()
    expect(screen.getByText('NO DRIFT')).toBeInTheDocument()
    expect(screen.getByText('OK')).toBeInTheDocument()
    expect(screen.getByText('REVIEW REQUIRED')).toBeInTheDocument()
    expect(screen.queryByText(/healthy/i)).not.toBeInTheDocument()
  })

  it('labels the monitoring dataset as DEVELOPMENT/DEMO, never live traffic', () => {
    render(<MlopsStatusPanel data={mockSystemStatus} />)
    expect(screen.getByText(/DEVELOPMENT\/DEMO/)).toBeInTheDocument()
    expect(screen.getByText(/not live traffic/i)).toBeInTheDocument()
  })

  it('shows "Never run" for every category when no monitoring run has ever completed', () => {
    const notRun = {
      ...mockSystemStatus,
      monitoring: {
        ...mockSystemStatus.monitoring,
        available: false,
        last_run_at: null,
        dataset_type: null,
        data_quality_status: 'NOT_RUN',
        data_drift_status: 'NOT_RUN',
        prediction_drift_status: 'NOT_RUN',
        performance_status: 'NOT_RUN',
        decision: 'NOT_RUN',
      },
    }
    render(<MlopsStatusPanel data={notRun} />)
    expect(screen.getAllByText('NOT RUN').length).toBeGreaterThan(0)
    expect(screen.getByText('Never run')).toBeInTheDocument()
  })

  it('still labels retraining automation as not implemented (Stage 9 does not retrain)', () => {
    render(<MlopsStatusPanel data={mockSystemStatus} />)
    expect(screen.getByText('Not implemented')).toBeInTheDocument()
  })
})
