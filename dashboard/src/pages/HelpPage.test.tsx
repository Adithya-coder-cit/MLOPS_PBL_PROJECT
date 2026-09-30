import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HelpPage } from './HelpPage'

describe('HelpPage', () => {
  it('honestly discloses this is demo data and no model is in production', () => {
    render(<HelpPage />)
    expect(screen.getByText(/synthetic transit network/i)).toBeInTheDocument()
    expect(screen.getByText(/no model has been promoted to production/i)).toBeInTheDocument()
  })

  it('explains that rerouting is a manual simulation, not a live feed', () => {
    render(<HelpPage />)
    expect(screen.getByText(/not connected to a live traffic or incident feed/i)).toBeInTheDocument()
  })
})
