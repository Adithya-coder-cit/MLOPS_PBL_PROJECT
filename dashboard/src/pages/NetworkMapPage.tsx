import type { StopSchema } from '../api/types'
import { RouteSchematicMap } from '../components/common/RouteSchematicMap'
import { SectionHeading } from '../components/common/SectionHeading'
import { LoadingState } from '../components/common/StatusStates'
import { stopSecondaryLabel } from '../lib/stopLabel'
import './NetworkMapPage.css'

interface NetworkMapPageProps {
  stops: StopSchema[]
  loading: boolean
}

export function NetworkMapPage({ stops, loading }: NetworkMapPageProps) {
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
          <RouteSchematicMap stops={stops} label="Schematic map of every stop in the network" />
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
