import { describe, expect, it } from 'vitest'
import { deriveRiskLabel } from './risk'

const thresholds = { moderate_threshold: 0.2, high_threshold: 0.4 }

describe('deriveRiskLabel', () => {
  it('labels risk below the moderate threshold as Low', () => {
    expect(deriveRiskLabel(0.1, thresholds)).toBe('Low')
    expect(deriveRiskLabel(0, thresholds)).toBe('Low')
  })

  it('labels risk at or above moderate but below high as Moderate', () => {
    expect(deriveRiskLabel(0.2, thresholds)).toBe('Moderate')
    expect(deriveRiskLabel(0.35, thresholds)).toBe('Moderate')
  })

  it('labels risk at or above the high threshold as High', () => {
    expect(deriveRiskLabel(0.4, thresholds)).toBe('High')
    expect(deriveRiskLabel(0.99, thresholds)).toBe('High')
  })

  it('uses the thresholds passed in, never a hardcoded value', () => {
    const wideThresholds = { moderate_threshold: 0.5, high_threshold: 0.9 }
    expect(deriveRiskLabel(0.3, wideThresholds)).toBe('Low')
    expect(deriveRiskLabel(0.3, thresholds)).toBe('Moderate')
  })
})
