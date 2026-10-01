import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { mockStops } from '../../test/mocks/fixtures'
import { SearchPanel } from './SearchPanel'

async function pickStop(user: ReturnType<typeof userEvent.setup>, fieldLabel: RegExp, query: string, optionName: RegExp) {
  const input = screen.getByLabelText(fieldLabel)
  await user.click(input)
  await user.type(input, query)
  await user.click(await screen.findByRole('option', { name: optionName }))
}

describe('SearchPanel', () => {
  it('requires an origin before submitting', async () => {
    const onSearch = vi.fn()
    render(<SearchPanel stops={mockStops} stopsLoading={false} onSearch={onSearch} searching={false} />)

    await userEvent.click(screen.getByRole('button', { name: /find best routes/i }))

    expect(screen.getByText(/choose an origin stop/i)).toBeInTheDocument()
    expect(onSearch).not.toHaveBeenCalled()
  })

  it('requires a destination before submitting', async () => {
    const user = userEvent.setup()
    const onSearch = vi.fn()
    render(<SearchPanel stops={mockStops} stopsLoading={false} onSearch={onSearch} searching={false} />)

    await pickStop(user, /^From$/i, 'Stop 40', /Stop 40/i)
    await user.click(screen.getByRole('button', { name: /find best routes/i }))

    expect(screen.getByText(/choose a destination stop/i)).toBeInTheDocument()
    expect(onSearch).not.toHaveBeenCalled()
  })

  it('rejects origin and destination being the same stop', async () => {
    const user = userEvent.setup()
    const onSearch = vi.fn()
    render(<SearchPanel stops={mockStops} stopsLoading={false} onSearch={onSearch} searching={false} />)

    await pickStop(user, /^From$/i, 'Stop 40', /Stop 40/i)
    await pickStop(user, /^To$/i, 'Stop 40', /Stop 40/i)
    await user.click(screen.getByRole('button', { name: /find best routes/i }))

    expect(screen.getByText(/destination must be different from origin/i)).toBeInTheDocument()
    expect(onSearch).not.toHaveBeenCalled()
  })

  it('calls onSearch with valid values', async () => {
    const user = userEvent.setup()
    const onSearch = vi.fn()
    render(<SearchPanel stops={mockStops} stopsLoading={false} onSearch={onSearch} searching={false} />)

    await pickStop(user, /^From$/i, 'Stop 40', /Stop 40/i)
    await pickStop(user, /^To$/i, 'Stop 41', /Stop 41/i)
    await user.click(screen.getByRole('button', { name: /find best routes/i }))

    expect(onSearch).toHaveBeenCalledWith(expect.objectContaining({ origin: 'S0040', destination: 'S0041' }))
  })

  it('disables the inputs and shows a loading placeholder while stops are loading', () => {
    render(<SearchPanel stops={[]} stopsLoading={true} onSearch={vi.fn()} searching={false} />)
    expect(screen.getByLabelText(/^From$/i)).toBeDisabled()
    expect(screen.getAllByPlaceholderText(/loading stops/i).length).toBeGreaterThan(0)
  })

  it('shows a searching label and disables submit while a search is in flight', () => {
    render(<SearchPanel stops={mockStops} stopsLoading={false} onSearch={vi.fn()} searching={true} />)
    expect(screen.getByRole('button', { name: /searching/i })).toBeDisabled()
  })

  it('swaps origin and destination when the swap button is clicked', async () => {
    const user = userEvent.setup()
    const onSearch = vi.fn()
    render(<SearchPanel stops={mockStops} stopsLoading={false} onSearch={onSearch} searching={false} />)

    await pickStop(user, /^From$/i, 'Stop 40', /Stop 40/i)
    await pickStop(user, /^To$/i, 'Stop 41', /Stop 41/i)
    await user.click(screen.getByRole('button', { name: /swap origin and destination/i }))
    await user.click(screen.getByRole('button', { name: /find best routes/i }))

    expect(onSearch).toHaveBeenCalledWith(expect.objectContaining({ origin: 'S0041', destination: 'S0040' }))
  })

  it('excludes stops with no scheduled service from the origin/destination search', async () => {
    const user = userEvent.setup()
    const stopsWithUnserved = [
      ...mockStops,
      { stop_id: 'S0099', stop_name: 'Stop 99', lat: 13.05, lon: 80.25, zone_id: 'Z03', has_scheduled_service: false },
    ]
    render(<SearchPanel stops={stopsWithUnserved} stopsLoading={false} onSearch={vi.fn()} searching={false} />)

    const input = screen.getByLabelText(/^From$/i)
    await user.click(input)
    await user.type(input, 'Stop 99')

    expect(screen.getByText(/no stops found/i)).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Stop 99/i })).not.toBeInTheDocument()
  })
})
