import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '../../test/mocks/server'
import { AdminExperimentsPage } from './AdminExperimentsPage'

const BASE = 'http://localhost:8000/api/v1'

describe('AdminExperimentsPage', () => {
  it('shows the real MLflow run history and links to the full MLflow UI', async () => {
    render(<AdminExperimentsPage />)

    expect(await screen.findByText('xgboost_stage5')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /open the full mlflow ui/i })).toHaveAttribute('href', 'http://localhost:5000')
  })

  it('opens a run detail panel when a row is clicked', async () => {
    const user = userEvent.setup()
    render(<AdminExperimentsPage />)
    await user.click(await screen.findByRole('button', { name: 'View' }))
    expect(await screen.findByText('Run details')).toBeInTheDocument()
  })

  it('shows an honest unavailable message instead of fake rows when MLflow has no data', async () => {
    server.use(
      http.get(`${BASE}/admin/experiments`, () =>
        HttpResponse.json({
          available: false,
          reason: 'MLflow tracking store is unreachable.',
          experiment_name: 'RouteWise-Disruption-Prediction',
          mlflow_tracking_uri: './mlruns',
          registered_model_name: 'RouteWise-Disruption-Model',
          runs: [],
        }),
      ),
    )
    render(<AdminExperimentsPage />)
    expect(await screen.findByText('MLflow tracking store is unreachable.')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})
