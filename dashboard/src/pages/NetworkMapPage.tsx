import { useMemo, useState } from 'react'
import type { StopSchema } from '../api/types'
import { RouteSchematicMap } from '../components/common/RouteSchematicMap'
import { SectionHeading } from '../components/common/SectionHeading'
import { LoadingState } from '../components/common/StatusStates'
import { stopSecondaryLabel, buildStopLookup } from '../lib/stopLabel'
import { useNetworkRoutes } from '../hooks/useNetworkRoutes'
import './NetworkMapPage.css'

interface NetworkMapPageProps {
  stops: StopSchema[]
  loading: boolean
}

export function NetworkMapPage({ stops, loading }: NetworkMapPageProps) {
  const networkRoutes = useNetworkRoutes()
  const [selectedKey, setSelectedKey] = useState('')
  const stopLookup = useMemo(() => buildStopLookup(stops), [stops])

  const routes = networkRoutes.data?.routes ?? []
  const selected = routes.find((r) => `${r.route_id}:${r.direction_id}` === selectedKey) ?? null
  const highlightedStops = selected
    ? selected.stop_ids.map((id) => stopLookup.get(id)).filter((s): s is StopSchema => Boolean(s))
    : []

  return (
    <section aria-labelledby="network-map-heading" className="rw-network-map">
      <div id="network-map-heading">
        <SectionHeading>Network map</SectionHeading>
      </div>
      <p className="rw-network-map__intro">
        Every stop currently in the RouteWise dataset, plotted from its real coordinates — {stops.length} stops.
      </p>

      {loading ? (
        <LoadingState label="Loading the network…" />
      ) : (
        <>
          <div className="rw-network-map__route-picker">
            <label htmlFor="network-map-route-select">Highlight a real route</label>
            <select
              id="network-map-route-select"
              value={selectedKey}
              onChange={(e) => setSelectedKey(e.target.value)}
              disabled={networkRoutes.status === 'loading' || routes.length === 0}
            >
              <option value="">All stops (no route selected)</option>
              {routes.map((r) => (
                <option key={`${r.route_id}:${r.direction_id}`} value={`${r.route_id}:${r.direction_id}`}>
                  {r.route_id} — {r.transport_mode} (direction {r.direction_id})
                </option>
              ))}
            </select>
          </div>

          {selected ? (
            <RouteSchematicMap
              stops={highlightedStops}
              connectPath
              highlightIds={[selected.stop_ids[0], selected.stop_ids[selected.stop_ids.length - 1]]}
              label={`Schematic map of route ${selected.route_id}, direction ${selected.direction_id}`}
            />
          ) : (
            <RouteSchematicMap stops={stops} label="Schematic map of every stop in the network" />
          )}

          <ul className="rw-network-map__list">
            {stops.map((stop) => (
              <li key={stop.stop_id} className="rw-network-map__item">
                <span className="rw-network-map__item-name">{stop.stop_name}</span>
                <span className="rw-network-map__item-zone">{stopSecondaryLabel(stop)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
