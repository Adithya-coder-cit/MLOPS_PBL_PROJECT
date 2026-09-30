import { useMemo, useState } from 'react'
import type { RouteRecommendationResponse, RiskLabelThresholds, StopSchema } from '../../api/types'
import { deriveRouteCategories } from '../../lib/routeCategories'
import { labelForStopId } from '../../lib/stopLabel'
import { SectionHeading } from '../common/SectionHeading'
import { CandidateComparison } from './CandidateComparison'
import { RouteCard } from './RouteCard'
import './RouteResultsList.css'

interface RouteResultsListProps {
  results: RouteRecommendationResponse
  thresholds: RiskLabelThresholds
  stopLookup: Map<string, StopSchema>
  onViewDetails: (routeId: string) => void
}

export function RouteResultsList({ results, thresholds, stopLookup, onViewDetails }: RouteResultsListProps) {
  const [comparing, setComparing] = useState(false)
  const originLabel = labelForStopId(stopLookup, results.origin)
  const destinationLabel = labelForStopId(stopLookup, results.destination)
  const categories = useMemo(() => deriveRouteCategories(results.candidates), [results.candidates])

  return (
    <section aria-labelledby="results-heading">
      <div className="rw-results-header">
        <div id="results-heading">
          <SectionHeading>
            {results.candidates.length} route{results.candidates.length === 1 ? '' : 's'} from {originLabel} to{' '}
            {destinationLabel}
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
              stopLookup={stopLookup}
              categoryLabel={categories.get(route.route_id)?.[0] ?? null}
              onViewDetails={() => onViewDetails(route.route_id)}
            />
          ))}
        </div>
      )}
    </section>
  )
}
