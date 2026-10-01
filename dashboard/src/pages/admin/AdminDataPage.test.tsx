import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '../../test/mocks/server'
import { mockDataSummary } from '../../test/mocks/fixtures'
import { AdminDataPage } from './AdminDataPage'

describe('AdminDataPage', () => {
  it('shows real record counts and coverage figures — never rounded/fabricated demo numbers', async () => {
    render(<AdminDataPage />)

    expect(await screen.findByText('4,808,668')).toBeInTheDocument()
    expect(screen.getByText('3,376,547')).toBeInTheDocument()
    expect(screen.getAllByText('bus, metro, tram').length).toBeGreaterThan(0)
    expect(screen.getByText('MBTA (transit) + NOAA GHCNh (weather)')).toBeInTheDocument()
  })

  it('shows the real eligible temporal split with per-split record counts', async () => {
    render(<AdminDataPage />)

    expect(await screen.findByText('train')).toBeInTheDocument()
    expect(screen.getByText('1,506,834')).toBeInTheDocument()
    expect(screen.getByText('328,171')).toBeInTheDocument()
    expect(screen.getByText('1,541,542')).toBeInTheDocument()
  })

  it('refetches real data when Refresh is clicked, not a cosmetic no-op', async () => {
    let calls = 0
    server.use(
      http.get('http://localhost:8000/api/v1/admin/data/summary', () => {
        calls += 1
        return HttpResponse.json(mockDataSummary)
      }),
    )

    const user = userEvent.setup()
    render(<AdminDataPage />)
    await screen.findByText('4,808,668')
    expect(calls).toBe(1)

    await user.click(screen.getByRole('button', { name: /refresh/i }))
    await screen.findByText('4,808,668')
    expect(calls).toBe(2)
  })
})
