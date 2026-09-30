import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { AdminEvaluationPage } from './AdminEvaluationPage'

describe('AdminEvaluationPage', () => {
  it('shows the real test metrics and confusion matrix for the default (first) model', async () => {
    render(<AdminEvaluationPage />)

    // 0.5074 (xgboost test f1) legitimately appears twice: the metric tile
    // and the model-comparison table row below.
    expect((await screen.findAllByText('0.5074')).length).toBeGreaterThan(0)
    expect(screen.getByText('28,853')).toBeInTheDocument() // tn
    expect(screen.getByText('10,016')).toBeInTheDocument() // tp
  })

  it('shows real feature importance, never a placeholder list', async () => {
    render(<AdminEvaluationPage />)
    expect(await screen.findByText('day_period')).toBeInTheDocument()
    expect(screen.getByText(/787\.03 \(gain\)/)).toBeInTheDocument()
  })

  it('renders scikit-learn "importance" as well as XGBoost "gain" — real, differently-named metrics, never normalized into a fake shared field', async () => {
    const user = userEvent.setup()
    render(<AdminEvaluationPage />)
    await screen.findByText('day_period')

    await user.click(screen.getByRole('button', { name: 'random_forest' }))
    expect(await screen.findByText('transfer_dependency')).toBeInTheDocument()
    expect(screen.getByText(/0\.2647 \(importance\)/)).toBeInTheDocument()
  })

  it('honestly labels the ROC/PR curve as unavailable rather than fabricating one', async () => {
    render(<AdminEvaluationPage />)
    expect(await screen.findByText(/Artifact unavailable — only the scalar ROC-AUC/i)).toBeInTheDocument()
  })

  it('switches models via tabs to show the other model’s real metrics', async () => {
    const user = userEvent.setup()
    render(<AdminEvaluationPage />)
    await screen.findByText('day_period')

    await user.click(screen.getByRole('button', { name: 'random_forest' }))
    // 0.5023 (random_forest test f1) also appears in the comparison table.
    expect((await screen.findAllByText('0.5023')).length).toBeGreaterThan(0)
  })
})
