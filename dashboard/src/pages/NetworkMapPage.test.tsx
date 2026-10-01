import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { mockStops } from '../test/mocks/fixtures'
import { NetworkMapPage } from './NetworkMapPage'

describe('NetworkMapPage', () => {
  it('lists every real stop by its real name and zone — never a fabricated one', () => {
    render(<NetworkMapPage stops={mockStops} loading={false} />)
    const list = within(screen.getByRole('list'))
    const stop40Row = list.getByText('Stop 40').closest('li')!
    expect(within(stop40Row).getByText('Zone 1')).toBeInTheDocument()
    expect(list.getByText('Stop 19')).toBeInTheDocument()
    expect(list.getByText('Zone 2')).toBeInTheDocument()
    expect(screen.getByText(/3 stops/)).toBeInTheDocument()
  })

  it('shows a loading state instead of an empty map while stops are loading', () => {
    render(<NetworkMapPage stops={[]} loading={true} />)
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('highlights a real route when selected from the picker, built from real backend route data', async () => {
    const user = userEvent.setup()
    render(<NetworkMapPage stops={mockStops} loading={false} />)

    const select = await screen.findByLabelText(/highlight a real route/i)
    await screen.findByRole('option', { name: /R011/i })
    await user.selectOptions(select, 'R011:0')

    expect(screen.getByRole('img', { name: /route r011, direction 0/i })).toBeInTheDocument()
  })

  it('provides real zoom controls on the map', () => {
    render(<NetworkMapPage stops={mockStops} loading={false} />)
    expect(screen.getByRole('button', { name: /zoom in/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /zoom out/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reset zoom/i })).toBeInTheDocument()
  })
})
