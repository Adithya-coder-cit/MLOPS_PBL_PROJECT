import { useState } from 'react'
import type { RouteRecommendationResponse, RiskLabelThresholds } from '../../api/types'
import { SectionHeading } from '../common/SectionHeading'
import { CandidateComparison } from './CandidateComparison'
import { RouteCard } from './RouteCard'
import './RouteResultsList.css'

interface RouteResultsListProps {
  results: RouteRecommendationResponse
  thresholds: RiskLabelThresholds
  onViewDetails: (routeId: string) => void
}

export function RouteResultsList({ results, thresholds, onViewDetails }: RouteResultsListProps) {
  const [comparing, setComparing] = useState(false)

  return (
    <section aria-labelledby="results-heading">
      <div className="rw-results-header">
        <div id="results-heading">
          <SectionHeading>
            {results.candidates.length} route{results.candidates.length === 1 ? '' : 's'} from {results.origin} to{' '}
            {results.destination}
          </SectionHeading>
        </div>
        {results.candidates.length > 1 && (
          <button type="button" className="rw-results-header__toggle" onClick={() => setComparing((c) => !c)}>
            {comparing ? 'Show cards' : 'Compare candidates'}
          </button>
        )}
      </div>

      {comparing ? (
        <CandidateComparison candidates={results.candidates} thresholds={thresholds} />
      ) : (
        <div className="rw-results-list">
          {results.candidates.map((route, index) => (
            <RouteCard
              key={route.route_id}
              route={route}
              rank={index}
              isRecommended={route.route_id === results.selected.route_id}
              thresholds={thresholds}
              onViewDetails={() => onViewDetails(route.route_id)}
            />
          ))}
        </div>
      )}
    </section>
  )
}
