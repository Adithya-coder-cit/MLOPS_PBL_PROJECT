import type { RouteSchema, RiskLabelThresholds } from '../../api/types'
import { formatCost, formatMinutes, formatPercent } from '../../lib/format'
import { deriveRiskLabel } from '../../lib/risk'
import './CandidateComparison.css'

interface CandidateComparisonProps {
  candidates: RouteSchema[]
  thresholds: RiskLabelThresholds
}

export function CandidateComparison({ candidates, thresholds }: CandidateComparisonProps) {
  return (
    <div className="rw-comparison" role="region" aria-label="Candidate route comparison">
      <table>
        <thead>
          <tr>
            <th scope="col">Route</th>
            <th scope="col">Time</th>
            <th scope="col">Cost</th>
            <th scope="col">Reliability</th>
            <th scope="col">Risk</th>
            <th scope="col">Transfers</th>
            <th scope="col">Modes</th>
            <th scope="col">Score</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((route, index) => (
            <tr key={route.route_id}>
              <th scope="row">{index === 0 ? 'Recommended' : `Alt. ${index}`}</th>
              <td className="data">{formatMinutes(route.total_time)}</td>
              <td className="data">{formatCost(route.total_cost)}</td>
              <td className="data">{formatPercent(route.reliability)}</td>
              <td className="data">
                {deriveRiskLabel(route.disruption_risk, thresholds)} ({formatPercent(route.disruption_risk)})
              </td>
              <td className="data">{route.transfer_count}</td>
              <td>{route.transport_modes.join(', ')}</td>
              <td className="data">{route.score.toFixed(3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
