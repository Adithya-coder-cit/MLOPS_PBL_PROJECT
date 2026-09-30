import { describe, expect, it } from 'vitest'
import { makeRoute } from '../test/mocks/fixtures'
import { deriveRouteCategories } from './routeCategories'

describe('deriveRouteCategories', () => {
  it('tags the candidate with the lowest total_time as Fastest — using real values, not invented ones', () => {
    const fast = makeRoute({ route_id: 'a', total_time: 20, total_cost: 30, disruption_risk: 0.5 })
    const slow = makeRoute({ route_id: 'b', total_time: 40, total_cost: 10, disruption_risk: 0.1 })
    const result = deriveRouteCategories([fast, slow])
    expect(result.get('a')).toContain('Fastest')
    expect(result.get('b')).not.toContain('Fastest')
  })

  it('a single candidate can hold multiple real category tags at once', () => {
    const onlyOption = makeRoute({ route_id: 'a', total_time: 20, total_cost: 10, disruption_risk: 0.1 })
    const result = deriveRouteCategories([onlyOption])
    expect(result.get('a')).toEqual(['Fastest', 'Lowest cost', 'Lowest disruption'])
  })

  it('returns an empty map for an empty candidate list', () => {
    expect(deriveRouteCategories([]).size).toBe(0)
  })
})
