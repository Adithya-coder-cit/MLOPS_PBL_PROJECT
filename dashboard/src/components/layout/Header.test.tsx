import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Header } from './Header'

describe('Header', () => {
  it('reflects the real backend health check, never hardcoded', () => {
    const { rerender } = render(<Header healthLabel="API online" healthOk view="journey" onNavigate={vi.fn()} />)
    expect(screen.getByText('API online')).toBeInTheDocument()

    rerender(<Header healthLabel="API offline" healthOk={false} view="journey" onNavigate={vi.fn()} />)
    expect(screen.getByText('API offline')).toBeInTheDocument()
  })

  it('marks the current view as active and calls onNavigate for the others', async () => {
    const user = userEvent.setup()
    const onNavigate = vi.fn()
    render(<Header healthLabel="API online" healthOk view="journey" onNavigate={onNavigate} />)

    expect(screen.getByRole('button', { name: 'Plan Journey' })).toHaveAttribute('aria-current', 'page')

    await user.click(screen.getByRole('button', { name: 'Network Map' }))
    expect(onNavigate).toHaveBeenCalledWith('network')

    await user.click(screen.getByRole('button', { name: 'Help' }))
    expect(onNavigate).toHaveBeenCalledWith('help')
  })

  it('disables My Trips — there is no saved-journey backend yet', () => {
    render(<Header healthLabel="API online" healthOk view="journey" onNavigate={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'My Trips' })).toBeDisabled()
  })
})
