import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { EmptyState, ErrorState, LoadingState, UnavailableState } from './StatusStates'

describe('StatusStates', () => {
  it('LoadingState announces itself via a status role', () => {
    render(<LoadingState label="Searching for routes…" />)
    expect(screen.getByRole('status')).toHaveTextContent('Searching for routes…')
  })

  it('ErrorState announces itself via an alert role and can retry', async () => {
    const onRetry = vi.fn()
    render(<ErrorState message="Something went wrong." onRetry={onRetry} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong.')
    await userEvent.click(screen.getByRole('button', { name: /try again/i }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('ErrorState omits the retry button when no handler is given', () => {
    render(<ErrorState message="Something went wrong." />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('EmptyState shows a title and optional description', () => {
    render(<EmptyState title="Search for a route" description="Nothing to show yet." />)
    expect(screen.getByText('Search for a route')).toBeInTheDocument()
    expect(screen.getByText('Nothing to show yet.')).toBeInTheDocument()
  })

  it('UnavailableState announces itself via an alert role', () => {
    render(<UnavailableState message="Model unavailable." />)
    expect(screen.getByRole('alert')).toHaveTextContent('Model unavailable.')
  })
})
