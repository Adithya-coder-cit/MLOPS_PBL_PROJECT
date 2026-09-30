import type { StopSchema } from '../api/types'

// The backend's demo dataset does not carry real city/area names — only a
// synthetic `stop_name` ("Stop 40") and a grid `zone_id` ("Z05"). We format
// those honestly rather than inventing geography (e.g. "Boston — Downtown")
// that isn't in the data. See generate_demo_data.py: zone_id is a lat/lon
// grid index, not a real place.
export function zoneLabel(zoneId: string): string {
  const num = Number.parseInt(zoneId.replace(/^Z/i, ''), 10)
  return Number.isNaN(num) ? zoneId : `Zone ${num}`
}

export function stopPrimaryLabel(stop: StopSchema): string {
  return stop.stop_name
}

export function stopSecondaryLabel(stop: StopSchema): string {
  return zoneLabel(stop.zone_id)
}

export function stopDisplayLabel(stop: StopSchema): string {
  return `${stopPrimaryLabel(stop)} · ${stopSecondaryLabel(stop)}`
}

export function buildStopLookup(stops: StopSchema[]): Map<string, StopSchema> {
  return new Map(stops.map((s) => [s.stop_id, s]))
}

// Falls back to the raw stop_id (real data, never fabricated) if the stop
// isn't in the currently-loaded lookup — e.g. while stops are still loading.
export function labelForStopId(lookup: Map<string, StopSchema>, stopId: string): string {
  const stop = lookup.get(stopId)
  return stop ? stopPrimaryLabel(stop) : stopId
}
