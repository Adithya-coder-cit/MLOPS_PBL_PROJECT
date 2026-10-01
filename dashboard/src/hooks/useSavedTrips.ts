import { useCallback, useState } from 'react'
import type { RouteSchema } from '../api/types'
import { deleteTrip, listSavedTrips, saveTrip, type SavedTrip } from '../lib/savedTrips'

export function useSavedTrips() {
  const [trips, setTrips] = useState<SavedTrip[]>(() => listSavedTrips())

  const save = useCallback((origin: string, destination: string, route: RouteSchema) => {
    saveTrip(origin, destination, route)
    setTrips(listSavedTrips())
  }, [])

  const remove = useCallback((id: string) => {
    deleteTrip(id)
    setTrips(listSavedTrips())
  }, [])

  return { trips, save, remove }
}
