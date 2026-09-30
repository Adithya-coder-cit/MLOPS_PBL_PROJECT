import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AdminLayout } from './AdminLayout'

describe('AdminLayout', () => {
  it('renders all six engineering sections and marks the active one', () => {
    render(
      <AdminLayout section="training" onSelectSection={vi.fn()} onExit={vi.fn()}>
        <p>content</p>
      </AdminLayout>,
    )
    for (const label of ['Training', 'Experiments', 'Data', 'Evaluation', 'Model Registry', 'Help']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
    }
    expect(screen.getByRole('button', { name: 'Training' })).toHaveAttribute('aria-current', 'page')
  })

  it('calls onSelectSection and onExit', async () => {
    const user = userEvent.setup()
    const onSelectSection = vi.fn()
    const onExit = vi.fn()
    render(
      <AdminLayout section="training" onSelectSection={onSelectSection} onExit={onExit}>
        <p>content</p>
      </AdminLayout>,
    )

    await user.click(screen.getByRole('button', { name: 'Data' }))
    expect(onSelectSection).toHaveBeenCalledWith('data')

    await user.click(screen.getByRole('button', { name: '← Back to RouteWise' }))
    expect(onExit).toHaveBeenCalledTimes(1)
  })
})
