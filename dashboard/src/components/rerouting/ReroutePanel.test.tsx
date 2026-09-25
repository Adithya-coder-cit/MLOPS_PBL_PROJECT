import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { RerouteResponse } from '../../api/types'
import { makeRoute } from '../../test/mocks/fixtures'
import { ReroutePanel } from './ReroutePanel'

const thresholds = { moderate_threshold: 0.2, high_threshold: 0.4 }

describe('ReroutePanel', () => {
  it('clearly distinguishes this as a manual capability, not a live feed', () => {
    render(
      <ReroutePanel
        route={makeRoute({})}
        status="idle"
        result={null}
        error={null}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
        thresholds={thresholds}
      />,
    )
    expect(screen.getByText(/not a live traffic feed/i)).toBeInTheDocument()
  })

  it('submits the selected edge_id and probability', async () => {
    const onSubmit = vi.fn()
    render(
      <ReroutePanel
        route={makeRoute({})}
        status="idle"
        result={null}
        error={null}
        onSubmit={onSubmit}
        onClose={vi.fn()}
        thresholds={thresholds}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: /apply update and recalculate/i }))
    expect(onSubmit).toHaveBeenCalledWith('R011:1:S0040->S0019', 0.9)
  })

  it('shows loading state while recalculating', () => {
    render(
      <ReroutePanel
        route={makeRoute({})}
        status="loading"
        result={null}
        error={null}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
        thresholds={thresholds}
      />,
    )
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /recalculating/i })).toBeDisabled()
  })

  it('shows the real before/after comparison from a successful result', () => {
    const result: RerouteResponse = {
      data_source: 'manual_update',
      original_route: makeRoute({}),
      updated_route: makeRoute({ route_id: 'different' }),
      changed: true,
      old_risk: 0.82,
      new_risk: 0.9,
      old_score: -0.491,
      new_score: -0.1,
      reason: 'Recommendation changed because risk increased.',
    }
    render(
      <ReroutePanel
        route={makeRoute({})}
        status="success"
        result={result}
        error={null}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
        thresholds={thresholds}
      />,
    )
    expect(screen.getByText('Recommendation changed.')).toBeInTheDocument()
    expect(screen.getByText('Recommendation changed because risk increased.')).toBeInTheDocument()
    expect(screen.getByText('82%')).toBeInTheDocument()
    expect(screen.getAllByText('90%').length).toBeGreaterThan(0) // also matches the probability slider label
  })

  it('shows an error state if the reroute request fails', () => {
    render(
      <ReroutePanel
        route={makeRoute({})}
        status="error"
        result={null}
        error={{ name: 'ApiError', message: 'x', status: 503, code: 'model_unavailable', detail: {} }}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
        thresholds={thresholds}
      />,
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })
})
