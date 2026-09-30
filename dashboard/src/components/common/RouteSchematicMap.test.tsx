import { render } from '@testing-library/react'
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
})
