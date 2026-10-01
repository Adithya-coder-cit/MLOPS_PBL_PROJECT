import { describe, expect, it } from 'vitest'
import type { StopSchema } from '../api/types'
import { buildStopLookup, labelForStopId, stopSecondaryLabel, zoneLabel } from './stopLabel'

describe('stopLabel', () => {
  it('derives the zone label only from the real zone_id — never invents a city or area', () => {
    expect(zoneLabel('Z05')).toBe('Zone 5')
    expect(zoneLabel('Z00')).toBe('Zone 0')
  })

  it('falls back to the raw zone_id string if it is not the expected Z-prefixed format', () => {
    expect(zoneLabel('unexpected')).toBe('unexpected')
  })

  it('labelForStopId falls back to the real stop_id (not a fabricated name) when the stop is unknown', () => {
    const lookup = buildStopLookup([])
    expect(labelForStopId(lookup, 'S0099')).toBe('S0099')
  })

  it('labelForStopId returns the real stop_name once the stop is loaded', () => {
    const stop: StopSchema = { stop_id: 'S0040', stop_name: 'Stop 40', lat: 1, lon: 2, zone_id: 'Z01', has_scheduled_service: true }
    const lookup = buildStopLookup([stop])
    expect(labelForStopId(lookup, 'S0040')).toBe('Stop 40')
  })

  it('stopSecondaryLabel is derived from the real zone_id field, not invented', () => {
    const stop: StopSchema = { stop_id: 'S0040', stop_name: 'Stop 40', lat: 1, lon: 2, zone_id: 'Z12', has_scheduled_service: true }
    expect(stopSecondaryLabel(stop)).toBe('Zone 12')
  })
})
