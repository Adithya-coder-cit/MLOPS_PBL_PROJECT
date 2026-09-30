import type { RiskLabelThresholds, RouteSchema, StopSchema } from '../../api/types'
import { formatCost, formatMinutes, formatPercent } from '../../lib/format'
import { labelForStopId } from '../../lib/stopLabel'
import { RiskBadge } from '../common/RiskBadge'
import { RouteSchematicMap } from '../common/RouteSchematicMap'
import { SectionHeading } from '../common/SectionHeading'
import './RouteDetails.css'

interface RouteDetailsProps {
  route: RouteSchema
  thresholds: RiskLabelThresholds
  stopLookup: Map<string, StopSchema>
  onClose: () => void
  onReroute: () => void
}

export function RouteDetails({ route, thresholds, stopLookup, onClose, onReroute }: RouteDetailsProps) {
  const originLabel = labelForStopId(stopLookup, route.origin)
  const destinationLabel = labelForStopId(stopLookup, route.destination)
  const journeyStops = route.stops.map((id) => stopLookup.get(id)).filter((s): s is StopSchema => Boolean(s))

  return (
    <section aria-labelledby="route-details-heading" className="rw-route-details">
      <div className="rw-route-details__header">
        <div id="route-details-heading">
          <SectionHeading>
            {originLabel} → {destinationLabel}
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

      <div className="rw-route-details__summary">
        <RiskBadge disruptionRisk={route.disruption_risk} thresholds={thresholds} />
        <span className="rw-route-details__summary-stat data">{formatMinutes(route.total_time)}</span>
        <span className="rw-route-details__summary-stat data">{formatCost(route.total_cost)}</span>
        <span className="rw-route-details__summary-stat">
          {route.transfer_count} {route.transfer_count === 1 ? 'transfer' : 'transfers'}
        </span>
      </div>

      <p className="rw-route-details__explanation">{route.explanation}</p>

      {journeyStops.length > 1 && (
        <RouteSchematicMap
          stops={journeyStops}
          connectPath
          highlightIds={[route.origin, route.destination]}
          label={`Schematic map of the journey from ${originLabel} to ${destinationLabel}`}
        />
      )}

      <ol className="rw-timeline">
        <li className="rw-timeline__stop">
          <span className="rw-timeline__marker rw-timeline__marker--endpoint" aria-hidden="true" />
          <span className="rw-timeline__label">Origin — {originLabel}</span>
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
                <p className="rw-timeline__segment-stops">
                  {labelForStopId(stopLookup, segment.from_stop)} → {labelForStopId(stopLookup, segment.to_stop)}
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
          <span className="rw-timeline__label">Destination — {destinationLabel}</span>
        </li>
      </ol>

      <p className="rw-route-details__meta">
        Scored <span className="data">{route.score.toFixed(3)}</span> under the {route.decision_policy} policy
      </p>
    </section>
  )
}
