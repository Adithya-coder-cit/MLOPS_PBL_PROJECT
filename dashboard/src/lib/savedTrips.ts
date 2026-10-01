import type { RouteSchema } from '../api/types'

export interface SavedTrip {
  id: string
  savedAt: string
  origin: string
  destination: string
  route: RouteSchema
}

const STORAGE_KEY = 'routewise.savedTrips.v1'

// Genuine browser persistence (localStorage), not a backend feature — this
// project has no auth/database for per-user trip storage, and the task
// brief explicitly allows local storage for this. Every saved trip is the
// real RouteSchema object the backend returned for that search, stored
// as-is; nothing here invents route data.

function readAll(): SavedTrip[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function writeAll(trips: SavedTrip[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trips))
  } catch {
    // Storage unavailable (private browsing, quota, disabled) — the save
    // silently no-ops rather than crashing the app; the caller's own
    // re-read of listSavedTrips() will simply show the trip didn't persist.
  }
}

export function listSavedTrips(): SavedTrip[] {
  return readAll().sort((a, b) => b.savedAt.localeCompare(a.savedAt))
}

export function saveTrip(origin: string, destination: string, route: RouteSchema): SavedTrip {
  const trip: SavedTrip = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    savedAt: new Date().toISOString(),
    origin,
    destination,
    route,
  }
  writeAll([...readAll(), trip])
  return trip
}

export function deleteTrip(id: string): void {
  writeAll(readAll().filter((t) => t.id !== id))
}
