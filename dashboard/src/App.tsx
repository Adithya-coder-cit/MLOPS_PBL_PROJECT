import { useEffect, useMemo, useState } from 'react'
import './styles/global.css'
import './App.css'

import { getHealth } from './api/endpoints'
import type { RouteRecommendationResponse } from './api/types'
import { friendlyErrorMessage } from './lib/errorMessages'
import { buildStopLookup } from './lib/stopLabel'
import type { AdminSection, AppView } from './types/navigation'

import { Header } from './components/layout/Header'
import { Hero } from './components/layout/Hero'
import { DemoDataBanner } from './components/common/DemoDataBanner'
import { EmptyState, ErrorState, LoadingState, StaleOverlay, UnavailableState } from './components/common/StatusStates'
import { SearchPanel, type SearchValues } from './components/search/SearchPanel'
import { RouteResultsList } from './components/results/RouteResultsList'
import { RouteDetails } from './components/details/RouteDetails'
import { ReroutePanel } from './components/rerouting/ReroutePanel'
import { NetworkMapPage } from './pages/NetworkMapPage'
import { HelpPage } from './pages/HelpPage'
import { AdminLayout } from './pages/admin/AdminLayout'
import { AdminTrainingPage } from './pages/admin/AdminTrainingPage'
import { AdminExperimentsPage } from './pages/admin/AdminExperimentsPage'
import { AdminDataPage } from './pages/admin/AdminDataPage'
import { AdminEvaluationPage } from './pages/admin/AdminEvaluationPage'
import { AdminRegistryPage } from './pages/admin/AdminRegistryPage'
import { AdminHelpPage } from './pages/admin/AdminHelpPage'

import { useStops } from './hooks/useStops'
import { useSystemStatus } from './hooks/useSystemStatus'
import { useRouteSearch } from './hooks/useRouteSearch'
import { useReroute } from './hooks/useReroute'

export type { AppView }

const HEALTH_POLL_INTERVAL_MS = 20_000

function App() {
  const stops = useStops()
  const systemStatus = useSystemStatus()
  const search = useRouteSearch()
  const reroute = useReroute()

  const [view, setView] = useState<AppView>('journey')
  const [adminSection, setAdminSection] = useState<AdminSection>('training')
  const [health, setHealth] = useState<'checking' | 'ok' | 'down'>('checking')
  const [lastSearch, setLastSearch] = useState<SearchValues | null>(null)
  const [staleResults, setStaleResults] = useState<RouteRecommendationResponse | null>(null)
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null)
  const [reroutingOpen, setReroutingOpen] = useState(false)

  // Periodic real health check — never hardcoded. Each poll aborts the
  // previous in-flight request before starting a new one.
  useEffect(() => {
    let cancelled = false
    let controller: AbortController | null = null

    function check() {
      controller?.abort()
      controller = new AbortController()
      getHealth(controller.signal)
        .then(() => {
          if (!cancelled) setHealth('ok')
        })
        .catch((err) => {
          if (!cancelled && !(err instanceof DOMException && err.name === 'AbortError')) setHealth('down')
        })
    }

    check()
    const interval = setInterval(check, HEALTH_POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      controller?.abort()
      clearInterval(interval)
    }
  }, [])

  const stopLookup = useMemo(() => buildStopLookup(stops.data?.stops ?? []), [stops.data])

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

  function navigate(next: AppView) {
    setView(next)
  }

  const selectedRoute = search.data?.candidates.find((r) => r.route_id === selectedRouteId) ?? null
  const thresholds = systemStatus.data?.risk_label_thresholds

  const modelUnavailable = systemStatus.status === 'success' && systemStatus.data && !systemStatus.data.routing_graph_available

  return (
    <div className="rw-shell">
      <Header
        healthLabel={health === 'checking' ? 'Checking…' : health === 'ok' ? 'API online' : 'API offline'}
        healthOk={health === 'ok'}
        view={view}
        onNavigate={navigate}
      />

      {view === 'journey' && (
        <>
          <div className="rw-shell__hero-region">
            <div className="rw-shell__hero-inner">
              <Hero>
                {modelUnavailable ? (
                  <UnavailableState message="No prediction model is currently loaded. Route search is paused until the backend reloads a model." />
                ) : (
                  <SearchPanel stops={stops.data?.stops ?? []} stopsLoading={stops.status === 'loading'} onSearch={runSearch} searching={search.status === 'loading'} />
                )}
              </Hero>
            </div>
          </div>

          <main className="rw-shell__main">
            {search.status === 'idle' && !staleResults && (
              <EmptyState
                title="Search for a route to see recommendations"
                description="Choose an origin and destination above, then search. Results come directly from the RouteWise API — nothing here is precomputed."
              />
            )}

            {search.status === 'loading' && staleResults && thresholds && (
              <StaleOverlay>
                <RouteResultsList results={staleResults} thresholds={thresholds} stopLookup={stopLookup} onViewDetails={setSelectedRouteId} />
              </StaleOverlay>
            )}

            {search.status === 'loading' && !staleResults && <LoadingState label="Planning your best routes…" />}

            {search.status === 'error' && <ErrorState message={friendlyErrorMessage(search.error)} onRetry={retrySearch} />}

            {search.status === 'success' && search.data && thresholds && (
              <RouteResultsList results={search.data} thresholds={thresholds} stopLookup={stopLookup} onViewDetails={setSelectedRouteId} />
            )}

            {selectedRoute && thresholds && !reroutingOpen && (
              <RouteDetails
                route={selectedRoute}
                thresholds={thresholds}
                stopLookup={stopLookup}
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
        </>
      )}

      {view === 'network' && (
        <main className="rw-shell__main rw-shell__main--page">
          <NetworkMapPage stops={stops.data?.stops ?? []} loading={stops.status === 'loading'} />
        </main>
      )}

      {view === 'help' && (
        <main className="rw-shell__main rw-shell__main--page">
          <HelpPage />
        </main>
      )}

      {view === 'admin' && (
        <main className="rw-shell__main rw-shell__main--admin">
          <AdminLayout section={adminSection} onSelectSection={setAdminSection} onExit={() => navigate('journey')}>
            {adminSection === 'training' && <AdminTrainingPage onNavigate={setAdminSection} />}
            {adminSection === 'experiments' && <AdminExperimentsPage />}
            {adminSection === 'data' && <AdminDataPage />}
            {adminSection === 'evaluation' && <AdminEvaluationPage />}
            {adminSection === 'registry' && <AdminRegistryPage />}
            {adminSection === 'help' && <AdminHelpPage />}
          </AdminLayout>
        </main>
      )}

      {view !== 'admin' && (
        <footer className="rw-shell__footer">
          <DemoDataBanner />
          <button type="button" className="rw-shell__admin-link" onClick={() => navigate('admin')}>
            Engineering view
          </button>
        </footer>
      )}
    </div>
  )
}

export default App
