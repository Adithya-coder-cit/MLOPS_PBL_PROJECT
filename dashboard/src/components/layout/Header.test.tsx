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

  it('navigates home when the logo is clicked', async () => {
    const user = userEvent.setup()
    const onNavigate = vi.fn()
    render(<Header healthLabel="API online" healthOk view="help" onNavigate={onNavigate} />)

    await user.click(screen.getByRole('button', { name: /routewise home/i }))
    expect(onNavigate).toHaveBeenCalledWith('journey')
  })

  it('navigates to My Trips — saved locally in the browser, no backend storage needed', async () => {
    const user = userEvent.setup()
    const onNavigate = vi.fn()
    render(<Header healthLabel="API online" healthOk view="journey" onNavigate={onNavigate} />)

    const tripsButton = screen.getByRole('button', { name: 'My Trips' })
    expect(tripsButton).toBeEnabled()
    await user.click(tripsButton)
    expect(onNavigate).toHaveBeenCalledWith('trips')
  })
})
