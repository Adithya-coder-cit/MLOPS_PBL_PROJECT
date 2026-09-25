import type { RouteSchema, RiskLabelThresholds } from '../../api/types'
import { formatCost, formatMinutes, formatPercent } from '../../lib/format'
import { ModelLifecycleBadge } from '../common/ModelLifecycleBadge'
import { RiskBadge } from '../common/RiskBadge'
import './RouteCard.css'

interface RouteCardProps {
  route: RouteSchema
  rank: number
  isRecommended: boolean
  thresholds: RiskLabelThresholds
  onViewDetails: () => void
}

export function RouteCard({ route, rank, isRecommended, thresholds, onViewDetails }: RouteCardProps) {
  return (
    <article className={`rw-route-card ${isRecommended ? 'rw-route-card--recommended' : ''}`}>
      <header className="rw-route-card__header">
        <span className="rw-route-card__rank">{isRecommended ? 'Recommended' : `Alternative ${rank}`}</span>
        <ModelLifecycleBadge metadata={route.model_metadata} />
      </header>

      <div className="rw-route-card__headline">
        <span className="rw-route-card__time data">{formatMinutes(route.total_time)}</span>
        <span className="rw-route-card__cost data">{formatCost(route.total_cost)}</span>
      </div>

      <div className="rw-route-card__badges">
        <RiskBadge disruptionRisk={route.disruption_risk} thresholds={thresholds} />
        <span className="rw-route-card__reliability">Reliability {formatPercent(route.reliability)}</span>
        <span className="rw-route-card__transfers">
          {route.transfer_count} {route.transfer_count === 1 ? 'transfer' : 'transfers'}
        </span>
      </div>

      <p className="rw-route-card__modes">{route.transport_modes.join(' / ')}</p>

      <p className="rw-route-card__explanation">{route.explanation}</p>

      <footer className="rw-route-card__footer">
        <span className="rw-route-card__meta">
          Scored <span className="data">{route.score.toFixed(3)}</span> under the {route.decision_policy} policy
        </span>
        <button type="button" onClick={onViewDetails} className="rw-route-card__view">
          View route
        </button>
      </footer>
    </article>
  )
}
