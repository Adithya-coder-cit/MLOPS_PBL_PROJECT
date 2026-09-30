import type { StopSchema, RiskLabelThresholds, RouteSchema } from '../../api/types'
import { formatCost, formatMinutes } from '../../lib/format'
import { labelForStopId } from '../../lib/stopLabel'
import { RiskBadge } from '../common/RiskBadge'
import './RouteCard.css'

interface RouteCardProps {
  route: RouteSchema
  rank: number
  isRecommended: boolean
  thresholds: RiskLabelThresholds
  stopLookup: Map<string, StopSchema>
  categoryLabel?: string | null
  onViewDetails: () => void
}

function modeSequence(route: RouteSchema): string[] {
  const sequence: string[] = []
  for (const segment of route.segments) {
    if (sequence[sequence.length - 1] !== segment.transport_mode) sequence.push(segment.transport_mode)
  }
  return sequence.length > 0 ? sequence : route.transport_modes
}

function capitalize(word: string): string {
  return word.charAt(0).toUpperCase() + word.slice(1)
}

export function RouteCard({
  route,
  rank,
  isRecommended,
  thresholds,
  stopLookup,
  categoryLabel,
  onViewDetails,
}: RouteCardProps) {
  const originLabel = labelForStopId(stopLookup, route.origin)
  const destinationLabel = labelForStopId(stopLookup, route.destination)

  return (
    <article className={`rw-route-card ${isRecommended ? 'rw-route-card--recommended' : ''}`}>
      <header className="rw-route-card__header">
        <span className="rw-route-card__rank">{isRecommended ? 'Recommended' : (categoryLabel ?? `Alternative ${rank}`)}</span>
        <RiskBadge disruptionRisk={route.disruption_risk} thresholds={thresholds} />
      </header>

      <h3 className="rw-route-card__title">
        {originLabel} <span aria-hidden="true">→</span> {destinationLabel}
      </h3>

      <div className="rw-route-card__stats">
        <span className="rw-route-card__stat rw-route-card__stat--time data">{formatMinutes(route.total_time)}</span>
        <span className="rw-route-card__stat-dot" aria-hidden="true" />
        <span className="rw-route-card__stat">
          {route.transfer_count} {route.transfer_count === 1 ? 'transfer' : 'transfers'}
        </span>
        <span className="rw-route-card__stat-dot" aria-hidden="true" />
        <span className="rw-route-card__stat data">{formatCost(route.total_cost)}</span>
      </div>

      <div className="rw-route-card__modes">
        {modeSequence(route).map((mode, index, arr) => (
          <span key={`${mode}-${index}`} className="rw-route-card__mode-group">
            <span className="rw-route-card__mode-chip">{capitalize(mode)}</span>
            {index < arr.length - 1 && (
              <span className="rw-route-card__mode-arrow" aria-hidden="true">
                →
              </span>
            )}
          </span>
        ))}
      </div>

      <footer className="rw-route-card__footer">
        <span className="rw-route-card__meta">
          Scored <span className="data">{route.score.toFixed(3)}</span> under the {route.decision_policy} policy
        </span>
        <button type="button" onClick={onViewDetails} className="rw-route-card__view">
          View journey
        </button>
      </footer>
    </article>
  )
}
