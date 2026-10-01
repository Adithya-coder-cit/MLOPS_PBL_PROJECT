import type { useSystemStatus } from '../../hooks/useSystemStatus'
import { useModelInfo } from '../../hooks/useModelInfo'
import { SystemStatusPanel } from '../../components/status/SystemStatusPanel'
import { ModelInfoPanel } from '../../components/status/ModelInfoPanel'
import { RefreshButton } from '../../components/admin/RefreshButton'
import { SectionHeading } from '../../components/common/SectionHeading'
import './adminShared.css'

interface AdminOverviewPageProps {
  systemStatus: ReturnType<typeof useSystemStatus>
}

export function AdminOverviewPage({ systemStatus }: AdminOverviewPageProps) {
  const modelInfo = useModelInfo()

  function refreshAll() {
    systemStatus.run().catch(() => {})
    modelInfo.run().catch(() => {})
  }

  return (
    <section aria-labelledby="overview-heading">
      <div className="rw-admin-page__heading-row">
        <div id="overview-heading">
          <SectionHeading>Overview</SectionHeading>
        </div>
        <RefreshButton onRefresh={refreshAll} loading={systemStatus.status === 'loading' || modelInfo.status === 'loading'} />
      </div>
      <p className="rw-admin-page__intro">Live system and model state, read directly from the running backend.</p>

      <div className="rw-admin-page__stack">
        <SystemStatusPanel
          status={systemStatus.status}
          data={systemStatus.data}
          error={systemStatus.error}
          onRetry={() => systemStatus.run().catch(() => {})}
        />
        <ModelInfoPanel
          status={modelInfo.status}
          data={modelInfo.data}
          error={modelInfo.error}
          onRetry={() => modelInfo.run().catch(() => {})}
        />
      </div>
    </section>
  )
}
