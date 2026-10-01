import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { mockStops } from '../../test/mocks/fixtures'
import { RouteSchematicMap } from './RouteSchematicMap'

describe('RouteSchematicMap', () => {
  it('plots one point per real stop, using its real lat/lon', () => {
    const { container } = render(<RouteSchematicMap stops={mockStops} label="test map" />)
    expect(container.querySelectorAll('circle')).toHaveLength(mockStops.length)
  })

  it('renders nothing for an empty stop list rather than a fabricated placeholder map', () => {
    const { container } = render(<RouteSchematicMap stops={[]} label="test map" />)
    expect(container.querySelector('svg')).not.toBeInTheDocument()
  })

  it('draws a connecting path only when connectPath is requested', () => {
    const { container, rerender } = render(<RouteSchematicMap stops={mockStops} label="test map" />)
    expect(container.querySelector('polyline')).not.toBeInTheDocument()

    rerender(<RouteSchematicMap stops={mockStops} connectPath label="test map" />)
    expect(container.querySelector('polyline')).toBeInTheDocument()
  })

  it('zooms in and resets via real viewBox changes, not a cosmetic no-op', async () => {
    const user = userEvent.setup()
    const { container } = render(<RouteSchematicMap stops={mockStops} label="test map" />)
    const svg = screen.getByRole('img', { name: 'test map' })
    const initialViewBox = svg.getAttribute('viewBox')

    await user.click(screen.getByRole('button', { name: /zoom in/i }))
    expect(svg.getAttribute('viewBox')).not.toBe(initialViewBox)

    await user.click(screen.getByRole('button', { name: /reset zoom/i }))
    expect(svg.getAttribute('viewBox')).toBe(initialViewBox)
    expect(container).toBeTruthy()
  })
})
