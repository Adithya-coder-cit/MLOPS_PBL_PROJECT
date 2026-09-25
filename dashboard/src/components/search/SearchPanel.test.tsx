import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { mockStops } from '../../test/mocks/fixtures'
import { SearchPanel } from './SearchPanel'

describe('SearchPanel', () => {
  it('requires an origin before submitting', async () => {
    const onSearch = vi.fn()
    render(<SearchPanel stops={mockStops} stopsLoading={false} onSearch={onSearch} searching={false} />)

    await userEvent.click(screen.getByRole('button', { name: /search routes/i }))

    expect(screen.getByText(/choose an origin stop/i)).toBeInTheDocument()
    expect(onSearch).not.toHaveBeenCalled()
  })

  it('requires a destination before submitting', async () => {
    const onSearch = vi.fn()
    render(<SearchPanel stops={mockStops} stopsLoading={false} onSearch={onSearch} searching={false} />)

    await userEvent.selectOptions(screen.getByLabelText(/origin/i), 'S0040')
    await userEvent.click(screen.getByRole('button', { name: /search routes/i }))

    expect(screen.getByText(/choose a destination stop/i)).toBeInTheDocument()
    expect(onSearch).not.toHaveBeenCalled()
  })

  it('rejects origin and destination being the same stop', async () => {
    const onSearch = vi.fn()
    render(<SearchPanel stops={mockStops} stopsLoading={false} onSearch={onSearch} searching={false} />)

    await userEvent.selectOptions(screen.getByLabelText(/origin/i), 'S0040')
    await userEvent.selectOptions(screen.getByLabelText(/destination/i), 'S0040')
    await userEvent.click(screen.getByRole('button', { name: /search routes/i }))

    expect(screen.getByText(/destination must be different from origin/i)).toBeInTheDocument()
    expect(onSearch).not.toHaveBeenCalled()
  })

  it('calls onSearch with valid values', async () => {
    const onSearch = vi.fn()
    render(<SearchPanel stops={mockStops} stopsLoading={false} onSearch={onSearch} searching={false} />)

    await userEvent.selectOptions(screen.getByLabelText(/origin/i), 'S0040')
    await userEvent.selectOptions(screen.getByLabelText(/destination/i), 'S0041')
    await userEvent.click(screen.getByRole('button', { name: /search routes/i }))

    expect(onSearch).toHaveBeenCalledWith(
      expect.objectContaining({ origin: 'S0040', destination: 'S0041' }),
    )
  })

  it('disables the selects and shows a loading option while stops are loading', () => {
    render(<SearchPanel stops={[]} stopsLoading={true} onSearch={vi.fn()} searching={false} />)
    expect(screen.getByLabelText(/origin/i)).toBeDisabled()
    expect(screen.getAllByText(/loading stops/i).length).toBeGreaterThan(0)
  })

  it('shows a searching label and disables submit while a search is in flight', () => {
    render(<SearchPanel stops={mockStops} stopsLoading={false} onSearch={vi.fn()} searching={true} />)
    expect(screen.getByRole('button', { name: /searching/i })).toBeDisabled()
  })
})
