import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
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
})
