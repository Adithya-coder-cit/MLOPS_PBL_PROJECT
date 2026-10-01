import { useState } from 'react'
import type { RiskLabelThresholds, StopSchema } from '../api/types'
import type { SavedTrip } from '../lib/savedTrips'
import { labelForStopId } from '../lib/stopLabel'
import { formatCost, formatMinutes } from '../lib/format'
import { RiskBadge } from '../components/common/RiskBadge'
import { SectionHeading } from '../components/common/SectionHeading'
import { EmptyState } from '../components/common/StatusStates'
import { RouteDetails } from '../components/details/RouteDetails'
import { ReroutePanel } from '../components/rerouting/ReroutePanel'
import { useReroute } from '../hooks/useReroute'
import './MyTripsPage.css'

interface MyTripsPageProps {
  trips: SavedTrip[]
  thresholds: RiskLabelThresholds | undefined
  stopLookup: Map<string, StopSchema>
  onDelete: (id: string) => void
}

export function MyTripsPage({ trips, thresholds, stopLookup, onDelete }: MyTripsPageProps) {
  const [openTripId, setOpenTripId] = useState<string | null>(null)
  const [reroutingOpen, setReroutingOpen] = useState(false)
  const reroute = useReroute()

  const openTrip = trips.find((t) => t.id === openTripId) ?? null

  function close() {
    setOpenTripId(null)
    setReroutingOpen(false)
  }

  if (openTrip && thresholds) {
    return (
      <section aria-labelledby="my-trips-heading" className="rw-my-trips">
        <div id="my-trips-heading">
          <SectionHeading>My Trips</SectionHeading>
        </div>
        <p className="rw-my-trips__saved-note">
          Saved on {new Date(openTrip.savedAt).toLocaleString()} — this is the real route the backend returned at
          save time, not a live re-query.
        </p>
        {!reroutingOpen && (
          <RouteDetails
            route={openTrip.route}
            thresholds={thresholds}
            stopLookup={stopLookup}
            onClose={close}
            onReroute={() => setReroutingOpen(true)}
          />
        )}
        {reroutingOpen && (
          <ReroutePanel
            route={openTrip.route}
            status={reroute.status}
            result={reroute.data}
            error={reroute.error}
            thresholds={thresholds}
            onClose={() => setReroutingOpen(false)}
            onSubmit={(edgeId, probability) => {
              reroute
                .run({
                  origin: openTrip.origin,
                  destination: openTrip.destination,
                  edge_updates: { [edgeId]: probability },
                })
                .catch(() => {})
            }}
          />
        )}
      </section>
    )
  }

  return (
    <section aria-labelledby="my-trips-heading" className="rw-my-trips">
      <div id="my-trips-heading">
        <SectionHeading>My Trips</SectionHeading>
      </div>
      <p className="rw-my-trips__intro">
        Trips you've saved from real search results, kept in this browser only — RouteWise has no account system or
        server-side trip storage.
      </p>

      {trips.length === 0 ? (
        <EmptyState
          title="No saved trips yet"
          description="Find a route, open its journey details, and choose Save trip to keep it here."
        />
      ) : (
        <ul className="rw-my-trips__list">
          {trips.map((trip) => (
            <li key={trip.id} className="rw-my-trips__item">
              <div className="rw-my-trips__item-main">
                <p className="rw-my-trips__item-title">
                  {labelForStopId(stopLookup, trip.origin)} <span aria-hidden="true">→</span>{' '}
                  {labelForStopId(stopLookup, trip.destination)}
                </p>
                <div className="rw-my-trips__item-stats">
                  {thresholds && <RiskBadge disruptionRisk={trip.route.disruption_risk} thresholds={thresholds} />}
                  <span className="data">{formatMinutes(trip.route.total_time)}</span>
                  <span className="data">{formatCost(trip.route.total_cost)}</span>
                  <span className="rw-my-trips__item-saved">Saved {new Date(trip.savedAt).toLocaleDateString()}</span>
                </div>
              </div>
              <div className="rw-my-trips__item-actions">
                <button type="button" onClick={() => setOpenTripId(trip.id)}>
                  Open
                </button>
                <button type="button" className="rw-my-trips__delete" onClick={() => onDelete(trip.id)}>
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
