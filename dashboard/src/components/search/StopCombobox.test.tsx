import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ComponentProps } from 'react'
import { mockStops } from '../../test/mocks/fixtures'
import { StopCombobox } from './StopCombobox'

function setup(overrides: Partial<ComponentProps<typeof StopCombobox>> = {}) {
  const onChange = vi.fn()
  render(
    <StopCombobox
      id="origin"
      label="From"
      placeholder="Search starting location…"
      stops={mockStops}
      loading={false}
      value=""
      onChange={onChange}
      {...overrides}
    />,
  )
  return { onChange }
}

describe('StopCombobox', () => {
  it('filters options as the user types', async () => {
    const user = userEvent.setup()
    setup()
    const input = screen.getByLabelText(/^From$/i)
    await user.click(input)
    await user.type(input, 'Stop 40')

    expect(screen.getByRole('option', { name: /Stop 40/i })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Stop 41/i })).not.toBeInTheDocument()
  })

  it('selects a stop on click and reports its real stop_id', async () => {
    const user = userEvent.setup()
    const { onChange } = setup()
    const input = screen.getByLabelText(/^From$/i)
    await user.click(input)
    await user.type(input, 'Stop 40')
    await user.click(screen.getByRole('option', { name: /Stop 40/i }))

    expect(onChange).toHaveBeenCalledWith('S0040')
  })

  it('supports keyboard navigation: ArrowDown moves the highlight, Enter selects it', async () => {
    const user = userEvent.setup()
    const { onChange } = setup()
    const input = screen.getByLabelText(/^From$/i)
    await user.click(input)
    await user.type(input, 'Stop 4')
    // Matches "Stop 40" and "Stop 41"; one ArrowDown moves off the default
    // first item (Stop 40) onto the second (Stop 41).
    await user.keyboard('{ArrowDown}{Enter}')

    expect(onChange).toHaveBeenCalledWith('S0041')
  })

  it('shows a "no stops found" empty state for a query that matches nothing', async () => {
    const user = userEvent.setup()
    setup()
    const input = screen.getByLabelText(/^From$/i)
    await user.click(input)
    await user.type(input, 'zzzzzz')

    expect(screen.getByText(/no stops found/i)).toBeInTheDocument()
  })

  it('shows a clear button once a stop is selected, which resets the value', async () => {
    const user = userEvent.setup()
    const { onChange } = setup({ value: 'S0040' })
    const clearButton = screen.getByRole('button', { name: /clear from selection/i })
    await user.click(clearButton)

    expect(onChange).toHaveBeenCalledWith('')
  })

  it('shows a loading placeholder and disables the input while stops are loading', () => {
    setup({ loading: true, stops: [] })
    const input = screen.getByLabelText(/^From$/i)
    expect(input).toBeDisabled()
    expect(input).toHaveAttribute('placeholder', 'Loading stops…')
  })
})
