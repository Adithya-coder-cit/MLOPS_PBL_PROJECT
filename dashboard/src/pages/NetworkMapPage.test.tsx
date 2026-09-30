import { render, screen, within } from '@testing-library/react'
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
})
