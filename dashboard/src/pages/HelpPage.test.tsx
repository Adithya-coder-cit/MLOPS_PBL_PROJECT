import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HelpPage } from './HelpPage'

describe('HelpPage', () => {
  it('honestly discloses this is demo data and no model is in production', () => {
    render(<HelpPage />)
    expect(screen.getByText(/synthetic transit network/i)).toBeInTheDocument()
    expect(screen.getByText(/no model has been promoted to production/i)).toBeInTheDocument()
  })

  it('explains that rerouting is a manual simulation, not a live feed', () => {
    render(<HelpPage />)
    expect(screen.getByText(/not connected to a live traffic or incident feed/i)).toBeInTheDocument()
  })

  it('shows the real request workflow, from stop selection through adaptive rerouting', () => {
    render(<HelpPage />)
    const flow = within(screen.getByRole('list', { name: /routewise request workflow/i }))
    for (const step of ['Stop selection', 'FastAPI', 'Disruption prediction', 'Multimodal graph',
      'Route candidates', 'Constraint-aware scoring', 'Recommended route', 'Adaptive rerouting']) {
      expect(flow.getByText(step)).toBeInTheDocument()
    }
  })

  it('explains the MLOps stack (MLflow, monitoring, retraining) without claiming auto-promotion', () => {
    render(<HelpPage />)
    expect(screen.getByText(/real mlflow tracking server and model registry/i)).toBeInTheDocument()
    expect(screen.getByText(/promotion is a separate, explicit, human-run step/i)).toBeInTheDocument()
  })
})
