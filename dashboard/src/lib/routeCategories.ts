import type { RouteSchema } from '../api/types'

export type RouteCategory = 'Fastest' | 'Lowest cost' | 'Lowest disruption'

// Derives category tags for each candidate purely from the REAL numeric
// fields the backend already returned (total_time/total_cost/
// disruption_risk) — never invents a duration, cost, or risk value.
export function deriveRouteCategories(candidates: RouteSchema[]): Map<string, RouteCategory[]> {
  const map = new Map<string, RouteCategory[]>()
  if (candidates.length === 0) return map

  const minTime = Math.min(...candidates.map((c) => c.total_time))
  const minCost = Math.min(...candidates.map((c) => c.total_cost))
  const minRisk = Math.min(...candidates.map((c) => c.disruption_risk))

  for (const c of candidates) {
    const tags: RouteCategory[] = []
    if (c.total_time === minTime) tags.push('Fastest')
    if (c.total_cost === minCost) tags.push('Lowest cost')
    if (c.disruption_risk === minRisk) tags.push('Lowest disruption')
    map.set(c.route_id, tags)
  }
  return map
}
