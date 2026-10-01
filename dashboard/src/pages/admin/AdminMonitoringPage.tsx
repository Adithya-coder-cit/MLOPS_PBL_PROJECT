import type { useSystemStatus } from '../../hooks/useSystemStatus'
import { MlopsStatusPanel } from '../../components/status/MlopsStatusPanel'
import { RefreshButton } from '../../components/admin/RefreshButton'
import { SectionHeading } from '../../components/common/SectionHeading'
import { ErrorState, LoadingState } from '../../components/common/StatusStates'
import { friendlyErrorMessage } from '../../lib/errorMessages'
import './adminShared.css'

interface AdminMonitoringPageProps {
  systemStatus: ReturnType<typeof useSystemStatus>
}

export function AdminMonitoringPage({ systemStatus }: AdminMonitoringPageProps) {
  return (
    <section aria-labelledby="monitoring-heading">
      <div className="rw-admin-page__heading-row">
        <div id="monitoring-heading">
          <SectionHeading>Monitoring</SectionHeading>
        </div>
        <RefreshButton onRefresh={() => systemStatus.run().catch(() => {})} loading={systemStatus.status === 'loading'} />
      </div>
      <p className="rw-admin-page__intro">
        DVC, MLflow, registry, and Evidently monitoring state, read directly from the backend and its artifacts.
      </p>

      {systemStatus.status === 'loading' && <LoadingState label="Loading MLOps status…" />}
      {systemStatus.status === 'error' && (
        <ErrorState message={friendlyErrorMessage(systemStatus.error)} onRetry={() => systemStatus.run().catch(() => {})} />
      )}
      {systemStatus.status === 'success' && systemStatus.data && <MlopsStatusPanel data={systemStatus.data} />}
    </section>
  )
}
