import { describe, expect, it } from 'vitest'
import { formatCost, formatMinutes, formatPercent } from './format'

describe('formatMinutes', () => {
  it('formats sub-hour durations as minutes', () => {
    expect(formatMinutes(43)).toBe('43 min')
  })

  it('formats hour-plus durations as hours and minutes', () => {
    expect(formatMinutes(125)).toBe('2 h 5 min')
  })

  it('omits minutes when the duration is an exact number of hours', () => {
    expect(formatMinutes(120)).toBe('2 h')
  })
})

describe('formatCost', () => {
  it('renders cost in synthetic units, never a currency symbol', () => {
    const result = formatCost(21.375)
    expect(result).toBe('21.38 units')
    expect(result).not.toContain('$')
    expect(result).not.toContain('₹')
  })
})

describe('formatPercent', () => {
  it('converts a ratio to a rounded percentage string', () => {
    expect(formatPercent(0.815)).toBe('82%')
    expect(formatPercent(0)).toBe('0%')
    expect(formatPercent(1)).toBe('100%')
  })
})
