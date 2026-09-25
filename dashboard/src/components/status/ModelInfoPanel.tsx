import type { ModelInfoResponse } from '../../api/types'
import { SectionHeading } from '../common/SectionHeading'
import { StatusPill } from '../common/StatusPill'
import { LoadingState, ErrorState } from '../common/StatusStates'
import { friendlyErrorMessage } from '../../lib/errorMessages'
import type { AsyncStatus } from '../../hooks/useAsync'
import './ModelInfoPanel.css'

interface ModelInfoPanelProps {
  status: AsyncStatus
  data: ModelInfoResponse | null
  error: unknown
  onRetry: () => void
}

const METRIC_ORDER = ['precision', 'recall', 'f1', 'roc_auc', 'pr_auc', 'accuracy']

function MetricsTable({ title, metrics }: { title: string; metrics: Record<string, number> }) {
  const entries = METRIC_ORDER.filter((k) => k in metrics)
  return (
    <div className="rw-metrics-table">
      <p className="rw-metrics-table__title">{title}</p>
      <table>
        <tbody>
          {entries.map((key) => (
            <tr key={key}>
              <th scope="row">{key.replace('_', ' ')}</th>
              <td className="data">{metrics[key].toFixed(4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function ModelInfoPanel({ status, data, error, onRetry }: ModelInfoPanelProps) {
  return (
    <section aria-labelledby="model-info-heading">
      <div id="model-info-heading">
        <SectionHeading>Model information</SectionHeading>
      </div>
      <div style={{ marginTop: 'var(--space-4)' }}>
        {status === 'loading' && <LoadingState label="Loading model info…" />}
        {status === 'error' && <ErrorState message={friendlyErrorMessage(error)} onRetry={onRetry} />}
        {status === 'success' && data && (
          <div className="rw-model-info">
            <p className="rw-model-info__name">
              {data.model_type === 'xgboost' ? 'XGBoost' : data.model_type === 'sklearn' ? 'Random Forest' : data.model_type}
            </p>
            <p className="rw-model-info__version">
              Version <span className="data">{data.model_version}</span>
            </p>
            <div className="rw-model-info__badges">
              <StatusPill tone={data.lifecycle_stage === 'Production' ? 'positive' : 'neutral'}>
                {data.lifecycle_stage ?? 'Unknown'}
              </StatusPill>
              <StatusPill tone={data.is_production_model ? 'positive' : 'negative'}>
                Production: {data.is_production_model ? 'Yes' : 'No'}
              </StatusPill>
            </div>

            <p className="rw-model-info__note">
              Validation metrics guided model selection. Test metrics are the final, one-time evaluation — this is
              not a claim of production performance.
            </p>
            <MetricsTable title="Validation metrics" metrics={data.validation_metrics} />
            <MetricsTable title="Test metrics" metrics={data.test_metrics} />
          </div>
        )}
      </div>
    </section>
  )
}
