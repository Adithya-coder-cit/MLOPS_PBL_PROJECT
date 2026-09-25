import type { RiskLabelThresholds } from '../../api/types'
import { formatPercent } from '../../lib/format'
import { deriveRiskLabel } from '../../lib/risk'
import './RiskBadge.css'

interface RiskBadgeProps {
  disruptionRisk: number
  thresholds: RiskLabelThresholds
}

export function RiskBadge({ disruptionRisk, thresholds }: RiskBadgeProps) {
  const label = deriveRiskLabel(disruptionRisk, thresholds)
  return (
    <span className={`rw-risk-badge rw-risk-badge--${label.toLowerCase()}`}>
      <span className="rw-risk-badge__label">{label} risk</span>
      <span className="rw-risk-badge__value data">{formatPercent(disruptionRisk)}</span>
    </span>
  )
}
