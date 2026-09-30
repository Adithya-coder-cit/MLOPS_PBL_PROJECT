import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AdminTrainingPage } from './AdminTrainingPage'

describe('AdminTrainingPage', () => {
  it('reports the real MODEL_READY=false state and never fakes progress', async () => {
    render(<AdminTrainingPage onNavigate={vi.fn()} />)

    expect(await screen.findByText('MODEL_READY = false')).toBeInTheDocument()
    expect(screen.getByText('No active training run.')).toBeInTheDocument()
    // The gate-disabled button must state why, never silently launch training.
    expect(
      screen.getByRole('button', { name: /training unavailable — model readiness requirements are not satisfied/i }),
    ).toBeDisabled()
  })

  it('shows the real latest completed run — both models, real record counts', async () => {
    render(<AdminTrainingPage onNavigate={vi.fn()} />)

    expect(await screen.findByText(/272,160/)).toBeInTheDocument()
    expect(screen.getAllByText(/58,320/).length).toBe(2) // validation and test records happen to share this real count
    // Each model name legitimately appears in both the Model Configuration
    // and Evaluation Results cards.
    expect(screen.getAllByText('random_forest').length).toBeGreaterThan(0)
    expect(screen.getAllByText('xgboost').length).toBeGreaterThan(0)
  })

  it('opens a run detail panel with real params/metrics when "View run" is clicked', async () => {
    const user = userEvent.setup()
    render(<AdminTrainingPage onNavigate={vi.fn()} />)

    await user.click((await screen.findAllByRole('button', { name: /view run/i }))[0])
    expect(await screen.findByText('Run details')).toBeInTheDocument()
    expect(await screen.findByText('f1dc3eee9b6746c5885aa0827beda96a')).toBeInTheDocument()
  })

  it('cross-links to the Data and Registry sections instead of duplicating their full content', async () => {
    const onNavigate = vi.fn()
    const user = userEvent.setup()
    render(<AdminTrainingPage onNavigate={onNavigate} />)

    await user.click(await screen.findByRole('button', { name: /view data/i }))
    expect(onNavigate).toHaveBeenCalledWith('data')

    await user.click(screen.getByRole('button', { name: /view registry/i }))
    expect(onNavigate).toHaveBeenCalledWith('registry')
  })
})
