import { beforeEach, describe, expect, it } from 'vitest'
import { makeRoute } from '../test/mocks/fixtures'
import { deleteTrip, listSavedTrips, saveTrip } from './savedTrips'

describe('savedTrips', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('starts empty', () => {
    expect(listSavedTrips()).toEqual([])
  })

  it('saves a trip using the real route object and lists it back', () => {
    const route = makeRoute({})
    const trip = saveTrip('S0040', 'S0041', route)

    const trips = listSavedTrips()
    expect(trips).toHaveLength(1)
    expect(trips[0].id).toBe(trip.id)
    expect(trips[0].origin).toBe('S0040')
    expect(trips[0].destination).toBe('S0041')
    expect(trips[0].route).toEqual(route)
  })

  it('deletes a trip by id', () => {
    const trip = saveTrip('S0040', 'S0041', makeRoute({}))
    expect(listSavedTrips()).toHaveLength(1)

    deleteTrip(trip.id)
    expect(listSavedTrips()).toHaveLength(0)
  })

  it('persists multiple trips independently', () => {
    saveTrip('S0040', 'S0041', makeRoute({ route_id: 'route-a' }))
    saveTrip('S0001', 'S0002', makeRoute({ route_id: 'route-b' }))

    const trips = listSavedTrips()
    expect(trips.map((t) => t.route.route_id).sort()).toEqual(['route-a', 'route-b'])
  })
})
