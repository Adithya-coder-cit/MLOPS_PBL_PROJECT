import { useEffect, useState } from 'react'
import './styles/global.css'
import './App.css'

import { getHealth } from './api/endpoints'
import type { RouteRecommendationResponse } from './api/types'
import { friendlyErrorMessage } from './lib/errorMessages'

import { Header } from './components/layout/Header'
import { DemoDataBanner } from './components/common/DemoDataBanner'
import { EmptyState, ErrorState, LoadingState, StaleOverlay, UnavailableState } from './components/common/StatusStates'
import { SearchPanel, type SearchValues } from './components/search/SearchPanel'
import { SystemStatusPanel } from './components/status/SystemStatusPanel'
import { ModelInfoPanel } from './components/status/ModelInfoPanel'
import { MlopsStatusPanel } from './components/status/MlopsStatusPanel'
import { RouteResultsList } from './components/results/RouteResultsList'
import { RouteDetails } from './components/details/RouteDetails'
import { ReroutePanel } from './components/rerouting/ReroutePanel'

import { useStops } from './hooks/useStops'
import { useSystemStatus } from './hooks/useSystemStatus'
import { useModelInfo } from './hooks/useModelInfo'
import { useRouteSearch } from './hooks/useRouteSearch'
import { useReroute } from './hooks/useReroute'

function App() {
  const stops = useStops()
  const systemStatus = useSystemStatus()
  const modelInfo = useModelInfo()
  const search = useRouteSearch()
  const reroute = useReroute()

  const [health, setHealth] = useState<'checking' | 'ok' | 'down'>('checking')
  const [lastSearch, setLastSearch] = useState<SearchValues | null>(null)
  const [staleResults, setStaleResults] = useState<RouteRecommendationResponse | null>(null)
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null)
  const [reroutingOpen, setReroutingOpen] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal)
      .then(() => setHealth('ok'))
      .catch(() => setHealth('down'))
    return () => controller.abort()
  }, [])

  function runSearch(values: SearchValues) {
    setLastSearch(values)
    setSelectedRouteId(null)
    setReroutingOpen(false)
    if (search.data) setStaleResults(search.data)
    search
      .run({
        origin: values.origin,
        destination: values.destination,
        departure_time: values.departureTime ? new Date(values.departureTime).toISOString() : undefined,
        top_n: values.topN,
      })
      .then(() => setStaleResults(null))
      .catch(() => setStaleResults(null))
  }

  function retrySearch() {
    if (lastSearch) runSearch(lastSearch)
  }

  const selectedRoute = search.data?.candidates.find((r) => r.route_id === selectedRouteId) ?? null
  const thresholds = systemStatus.data?.risk_label_thresholds

  const modelUnavailable = systemStatus.status === 'success' && systemStatus.data && !systemStatus.data.routing_graph_available

  return (
    <div className="rw-shell">
      <Header healthLabel={health === 'checking' ? 'Checking…' : health === 'ok' ? 'API online' : 'API unreachable'} healthOk={health === 'ok'} />

      <aside className="rw-shell__console" aria-label="Search and system status">
        {modelUnavailable ? (
          <UnavailableState message="No prediction model is currently loaded. Route search is paused until the backend reloads a model." />
        ) : (
          <SearchPanel stops={stops.data?.stops ?? []} stopsLoading={stops.status === 'loading'} onSearch={runSearch} searching={search.status === 'loading'} />
        )}

        <SystemStatusPanel status={systemStatus.status} data={systemStatus.data} error={systemStatus.error} onRetry={systemStatus.run} />

        {systemStatus.status === 'success' && systemStatus.data && <MlopsStatusPanel data={systemStatus.data} />}

        <ModelInfoPanel status={modelInfo.status} data={modelInfo.data} error={modelInfo.error} onRetry={modelInfo.run} />

        <DemoDataBanner />
      </aside>

      <main className="rw-shell__main">
        {search.status === 'idle' && !staleResults && (
          <EmptyState
            title="Search for a route to see recommendations"
            description="Choose an origin and destination on the left, then search. Results come directly from the RouteWise API — nothing here is precomputed."
          />
        )}

        {search.status === 'loading' && staleResults && thresholds && (
          <StaleOverlay>
            <RouteResultsList results={staleResults} thresholds={thresholds} onViewDetails={setSelectedRouteId} />
          </StaleOverlay>
        )}

        {search.status === 'loading' && !staleResults && <LoadingState label="Searching for routes…" />}

        {search.status === 'error' && <ErrorState message={friendlyErrorMessage(search.error)} onRetry={retrySearch} />}

        {search.status === 'success' && search.data && thresholds && (
          <RouteResultsList results={search.data} thresholds={thresholds} onViewDetails={setSelectedRouteId} />
        )}

        {selectedRoute && thresholds && !reroutingOpen && (
          <RouteDetails
            route={selectedRoute}
            thresholds={thresholds}
            onClose={() => setSelectedRouteId(null)}
            onReroute={() => setReroutingOpen(true)}
          />
        )}

        {selectedRoute && thresholds && reroutingOpen && (
          <ReroutePanel
            route={selectedRoute}
            status={reroute.status}
            result={reroute.data}
            error={reroute.error}
            thresholds={thresholds}
            onClose={() => setReroutingOpen(false)}
            onSubmit={(edgeId, probability) => {
              reroute.run({
                origin: selectedRoute.origin,
                destination: selectedRoute.destination,
                edge_updates: { [edgeId]: probability },
              }).catch(() => {})
            }}
          />
        )}
      </main>
    </div>
  )
}

export default App
