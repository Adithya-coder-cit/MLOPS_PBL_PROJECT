import type { SystemStatusResponse } from '../../api/types'
import { formatMonitoringStatus, toneForMonitoringStatus } from '../../lib/monitoringStatus'
import { FactList } from '../common/FactList'
import { SectionHeading } from '../common/SectionHeading'
import { StatusPill } from '../common/StatusPill'

export function MlopsStatusPanel({ data }: { data: SystemStatusResponse }) {
  const monitoring = data.monitoring

  return (
    <section aria-labelledby="mlops-heading">
      <div id="mlops-heading">
        <SectionHeading>MLOps</SectionHeading>
      </div>
      <div style={{ marginTop: 'var(--space-4)' }}>
        <FactList
          facts={[
            {
              label: 'Data (DVC)',
              value: (
                <StatusPill tone={data.dvc_configured ? 'positive' : 'negative'}>
                  {data.dvc_configured ? 'Available' : 'Not configured'}
                </StatusPill>
              ),
            },
            {
              label: 'Experiment tracking (MLflow)',
              value: (
                <StatusPill tone={data.mlflow_reachable ? 'positive' : 'negative'}>
                  {data.mlflow_reachable ? 'Available' : 'Unreachable'}
                </StatusPill>
              ),
            },
            {
              label: 'Registry — Candidate',
              value: <StatusPill tone={data.model_name ? 'positive' : 'negative'}>
                {data.model_name ? 'Available' : 'None'}
              </StatusPill>,
            },
            {
              label: 'Registry — Production',
              value: (
                <StatusPill tone={data.production_model_available ? 'positive' : 'negative'}>
                  {data.production_model_available ? 'Available' : 'Not available'}
                </StatusPill>
              ),
            },
            {
              label: 'CI/CD',
              value: (
                <StatusPill tone={data.ci_cd_configured ? 'positive' : 'negative'}>
                  {data.ci_cd_configured ? 'Configured' : 'Not configured'}
                </StatusPill>
              ),
            },
            {
              label: 'Monitoring',
              value: (
                <StatusPill tone={monitoring.available ? 'positive' : 'negative'}>
                  {monitoring.available ? 'Available' : 'Never run'}
                </StatusPill>
              ),
            },
            {
              label: 'Data quality',
              value: (
                <StatusPill tone={toneForMonitoringStatus(monitoring.data_quality_status)}>
                  {formatMonitoringStatus(monitoring.data_quality_status)}
                </StatusPill>
              ),
            },
            {
              label: 'Data drift',
              value: (
                <StatusPill tone={toneForMonitoringStatus(monitoring.data_drift_status)}>
                  {formatMonitoringStatus(monitoring.data_drift_status)}
                </StatusPill>
              ),
            },
            {
              label: 'Prediction drift',
              value: (
                <StatusPill tone={toneForMonitoringStatus(monitoring.prediction_drift_status)}>
                  {formatMonitoringStatus(monitoring.prediction_drift_status)}
                </StatusPill>
              ),
            },
            {
              label: 'Performance',
              value: (
                <StatusPill tone={toneForMonitoringStatus(monitoring.performance_status)}>
                  {formatMonitoringStatus(monitoring.performance_status)}
                </StatusPill>
              ),
            },
            {
              label: 'Monitoring decision',
              value: (
                <StatusPill tone={toneForMonitoringStatus(monitoring.decision)}>
                  {formatMonitoringStatus(monitoring.decision)}
                </StatusPill>
              ),
            },
            {
              label: 'Retraining automation',
              value: <StatusPill tone="negative">Not implemented</StatusPill>,
            },
          ]}
        />
        {monitoring.dataset_type && (
          <p style={{ marginTop: 'var(--space-3)', color: 'var(--ink-soft)', fontSize: '13px' }}>
            Monitoring dataset: {monitoring.dataset_type} — not live traffic. Last run:{' '}
            {monitoring.last_run_at ?? 'never'}.
          </p>
        )}
      </div>
    </section>
  )
}
