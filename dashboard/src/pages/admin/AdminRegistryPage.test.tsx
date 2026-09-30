import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { AdminRegistryPage } from './AdminRegistryPage'

describe('AdminRegistryPage', () => {
  it('shows real registry totals and honestly reports no production model', async () => {
    render(<AdminRegistryPage />)

    expect(await screen.findByText('RouteWise-Disruption-Model')).toBeInTheDocument()
    expect(screen.getAllByText('6').length).toBeGreaterThan(0) // total_versions / candidate count / latest version
    expect(screen.getAllByText('No production model').length).toBeGreaterThan(0)
  })

  it('lists real version rows with lifecycle badges', async () => {
    render(<AdminRegistryPage />)
    expect(await screen.findByText('v6')).toBeInTheDocument()
    expect(screen.getByText('v5')).toBeInTheDocument()
    expect(screen.getAllByText('Candidate').length).toBeGreaterThan(0)
  })

  it('opens the run detail panel for a specific version', async () => {
    const user = userEvent.setup()
    render(<AdminRegistryPage />)
    await user.click((await screen.findAllByRole('button', { name: /view run/i }))[0])
    expect(await screen.findByText('Run details')).toBeInTheDocument()
  })
})
