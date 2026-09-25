import { useState } from 'react'
import type { RerouteResponse, RiskLabelThresholds, RouteSchema } from '../../api/types'
import { formatPercent } from '../../lib/format'
import { RiskBadge } from '../common/RiskBadge'
import { SectionHeading } from '../common/SectionHeading'
import { ErrorState, LoadingState } from '../common/StatusStates'
import { friendlyErrorMessage } from '../../lib/errorMessages'
import type { AsyncStatus } from '../../hooks/useAsync'
import './ReroutePanel.css'

interface ReroutePanelProps {
  route: RouteSchema
  status: AsyncStatus
  result: RerouteResponse | null
  error: unknown
  onSubmit: (edgeId: string, newProbability: number) => void
  onClose: () => void
  thresholds: RiskLabelThresholds
}

export function ReroutePanel({ route, status, result, error, onSubmit, onClose, thresholds }: ReroutePanelProps) {
  const [edgeId, setEdgeId] = useState(route.segments[0]?.edge_id ?? '')
  const [probability, setProbability] = useState(0.9)

  return (
    <section aria-labelledby="reroute-heading" className="rw-reroute">
      <div className="rw-reroute__header">
        <div id="reroute-heading">
          <SectionHeading>Adaptive rerouting capability</SectionHeading>
        </div>
        <button type="button" onClick={onClose} className="rw-reroute__close" aria-label="Close rerouting panel">
          Close
        </button>
      </div>

      <p className="rw-reroute__disclaimer">
        This is a manual, caller-supplied disruption update for demonstration — <strong>not a live traffic feed</strong>.
        No real-time transportation data source is connected to RouteWise.
      </p>

      <form
        className="rw-reroute__form"
        onSubmit={(e) => {
          e.preventDefault()
          onSubmit(edgeId, probability)
        }}
      >
        <div className="rw-field">
          <label htmlFor="reroute-segment">Segment to update</label>
          <select id="reroute-segment" value={edgeId} onChange={(e) => setEdgeId(e.target.value)}>
            {route.segments.map((segment) => (
              <option key={segment.edge_id} value={segment.edge_id}>
                {segment.from_stop} → {segment.to_stop} ({segment.transport_mode}, route {segment.route_id})
              </option>
            ))}
          </select>
        </div>

        <div className="rw-field">
          <label htmlFor="reroute-probability">
            New disruption probability — <span className="data">{formatPercent(probability)}</span>
          </label>
          <input
            id="reroute-probability"
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={probability}
            onChange={(e) => setProbability(Number(e.target.value))}
          />
        </div>

        <button type="submit" className="rw-reroute__submit" disabled={status === 'loading' || !edgeId}>
          {status === 'loading' ? 'Recalculating…' : 'Apply update and recalculate'}
        </button>
      </form>

      {status === 'loading' && <LoadingState label="Recalculating candidate routes…" />}
      {status === 'error' && <ErrorState message={friendlyErrorMessage(error)} />}

      {status === 'success' && result && (
        <div className="rw-reroute__result">
          <p className={`rw-reroute__verdict ${result.changed ? 'rw-reroute__verdict--changed' : ''}`}>
            {result.changed ? 'Recommendation changed.' : 'Recommendation unchanged.'}
          </p>
          <p className="rw-reroute__reason">{result.reason}</p>

          <div className="rw-reroute__compare">
            <div>
              <p className="rw-reroute__compare-label">Before</p>
              <RiskBadge disruptionRisk={result.old_risk} thresholds={thresholds} />
              <p className="rw-reroute__compare-score">
                Score <span className="data">{result.old_score.toFixed(3)}</span>
              </p>
            </div>
            <div className="rw-reroute__compare-arrow" aria-hidden="true">
              →
            </div>
            <div>
              <p className="rw-reroute__compare-label">After</p>
              <RiskBadge disruptionRisk={result.new_risk} thresholds={thresholds} />
              <p className="rw-reroute__compare-score">
                Score <span className="data">{result.new_score.toFixed(3)}</span>
              </p>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
