import type { RiskLabelThresholds, RouteSchema } from '../../api/types'
import { formatCost, formatMinutes, formatPercent } from '../../lib/format'
import { RiskBadge } from '../common/RiskBadge'
import { SectionHeading } from '../common/SectionHeading'
import './RouteDetails.css'

interface RouteDetailsProps {
  route: RouteSchema
  thresholds: RiskLabelThresholds
  onClose: () => void
  onReroute: () => void
}

export function RouteDetails({ route, thresholds, onClose, onReroute }: RouteDetailsProps) {
  return (
    <section aria-labelledby="route-details-heading" className="rw-route-details">
      <div className="rw-route-details__header">
        <div id="route-details-heading">
          <SectionHeading>
            Route {route.origin} → {route.destination}
          </SectionHeading>
        </div>
        <div className="rw-route-details__actions">
          <button type="button" onClick={onReroute} className="rw-route-details__reroute">
            Adaptive rerouting
          </button>
          <button type="button" onClick={onClose} className="rw-route-details__close" aria-label="Close route details">
            Close
          </button>
        </div>
      </div>

      <ol className="rw-timeline">
        <li className="rw-timeline__stop">
          <span className="rw-timeline__marker rw-timeline__marker--endpoint" aria-hidden="true" />
          <span className="rw-timeline__label">Origin — {route.origin}</span>
        </li>

        {route.segments.map((segment) => (
          <li key={segment.edge_id} className="rw-timeline__segment">
            {segment.is_transfer_point && <p className="rw-timeline__transfer">Transfer</p>}
            <div className="rw-timeline__segment-card">
              <span className="rw-timeline__marker" aria-hidden="true" />
              <div className="rw-timeline__segment-body">
                <p className="rw-timeline__segment-title">
                  {segment.transport_mode} on route <span className="data">{segment.route_id}</span>
                </p>
                <p className="rw-timeline__segment-stops data">
                  {segment.from_stop} → {segment.to_stop}
                </p>
                <dl className="rw-timeline__segment-stats">
                  <div>
                    <dt>Travel time</dt>
                    <dd className="data">{formatMinutes(segment.travel_time)}</dd>
                  </div>
                  <div>
                    <dt>Cost</dt>
                    <dd className="data">{formatCost(segment.cost)}</dd>
                  </div>
                  <div>
                    <dt>Reliability</dt>
                    <dd className="data">{formatPercent(segment.reliability)}</dd>
                  </div>
                  <div>
                    <dt>Disruption risk</dt>
                    <dd>
                      <RiskBadge disruptionRisk={segment.disruption_probability} thresholds={thresholds} />
                    </dd>
                  </div>
                </dl>
                <p className="rw-timeline__edge-id">
                  Edge ID <span className="data">{segment.edge_id}</span>
                </p>
              </div>
            </div>
          </li>
        ))}

        <li className="rw-timeline__stop">
          <span className="rw-timeline__marker rw-timeline__marker--endpoint" aria-hidden="true" />
          <span className="rw-timeline__label">Destination — {route.destination}</span>
        </li>
      </ol>
    </section>
  )
}
