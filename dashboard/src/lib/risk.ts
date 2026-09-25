import type { RiskLabelThresholds } from '../api/types'

export type RiskLabel = 'Low' | 'Moderate' | 'High'

/**
 * Buckets a REAL disruption_risk value (from the API) into a word label,
 * using the THRESHOLDS the backend serves via GET /system/status
 * (params.yaml ui_risk_labels) — never a value hardcoded separately in
 * the frontend. This is a display/communication policy, not a
 * scientific or safety-certified classification.
 */
export function deriveRiskLabel(disruptionRisk: number, thresholds: RiskLabelThresholds): RiskLabel {
  if (disruptionRisk >= thresholds.high_threshold) return 'High'
  if (disruptionRisk >= thresholds.moderate_threshold) return 'Moderate'
  return 'Low'
}
