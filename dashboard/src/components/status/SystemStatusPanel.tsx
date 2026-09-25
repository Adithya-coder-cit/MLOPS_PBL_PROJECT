import type { SystemStatusResponse } from '../../api/types'
import { FactList } from '../common/FactList'
import { SectionHeading } from '../common/SectionHeading'
import { LoadingState, ErrorState } from '../common/StatusStates'
import { StatusPill } from '../common/StatusPill'
import { friendlyErrorMessage } from '../../lib/errorMessages'
import type { AsyncStatus } from '../../hooks/useAsync'

interface SystemStatusPanelProps {
  status: AsyncStatus
  data: SystemStatusResponse | null
  error: unknown
  onRetry: () => void
}

export function SystemStatusPanel({ status, data, error, onRetry }: SystemStatusPanelProps) {
  return (
    <section aria-labelledby="system-status-heading">
      <div id="system-status-heading">
        <SectionHeading>System</SectionHeading>
      </div>
      <div style={{ marginTop: 'var(--space-4)' }}>
        {status === 'loading' && <LoadingState label="Checking system status…" />}
        {status === 'error' && <ErrorState message={friendlyErrorMessage(error)} onRetry={onRetry} />}
        {status === 'success' && data && (
          <FactList
            facts={[
              { label: 'API', value: <StatusPill tone="positive">Online</StatusPill> },
              { label: 'Model', value: data.model_name ?? 'None loaded' },
              { label: 'Version', value: data.model_version ?? '—', mono: true },
              {
                label: 'Lifecycle',
                value: (
                  <StatusPill tone={data.model_lifecycle_stage === 'Production' ? 'positive' : 'neutral'}>
                    {data.model_lifecycle_stage ?? 'Unavailable'}
                  </StatusPill>
                ),
              },
              {
                label: 'Production model',
                value: (
                  <StatusPill tone={data.production_model_available ? 'positive' : 'negative'}>
                    {data.production_model_available ? 'Available' : 'Not available'}
                  </StatusPill>
                ),
              },
              { label: 'Dataset version', value: data.dataset_version ?? '—', mono: true },
              { label: 'Routing engine', value: data.routing_engine_version, mono: true },
              {
                label: 'Monitoring',
                value: <StatusPill tone="negative">{data.monitoring_status.replace('_', ' ')}</StatusPill>,
              },
            ]}
          />
        )}
      </div>
    </section>
  )
}
