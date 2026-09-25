import type { PillTone } from '../components/common/StatusPill'

// In this design system StatusPill's "neutral" tone renders amber
// (attention) and "negative" renders muted gray (absent/not applicable) —
// see StatusPill.css. So: PASS/NO_DRIFT/OK/NO_ACTION read as healthy
// (positive/teal); FAIL/DRIFT_DETECTED/DEGRADED/REVIEW_REQUIRED/
// RETRAINING_RECOMMENDED need attention (neutral/amber); NOT_RUN/
// NOT_AVAILABLE mean nothing has happened yet, not a problem (negative/gray)
// — never a fabricated "healthy" default for any of them.
const POSITIVE_STATUSES = new Set(['PASS', 'NO_DRIFT', 'OK', 'NO_ACTION'])
const ABSENT_STATUSES = new Set(['NOT_RUN', 'NOT_AVAILABLE'])

export function toneForMonitoringStatus(status: string): PillTone {
  if (POSITIVE_STATUSES.has(status)) return 'positive'
  if (ABSENT_STATUSES.has(status)) return 'negative'
  return 'neutral'
}

export function formatMonitoringStatus(status: string): string {
  return status.replace(/_/g, ' ')
}
