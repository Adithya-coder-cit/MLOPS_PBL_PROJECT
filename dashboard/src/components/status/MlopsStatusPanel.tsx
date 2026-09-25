import type { SystemStatusResponse } from '../../api/types'
import { FactList } from '../common/FactList'
import { SectionHeading } from '../common/SectionHeading'
import { StatusPill } from '../common/StatusPill'

export function MlopsStatusPanel({ data }: { data: SystemStatusResponse }) {
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
              value: <StatusPill tone="negative">Not implemented</StatusPill>,
            },
            {
              label: 'Retraining',
              value: <StatusPill tone="negative">Not implemented</StatusPill>,
            },
          ]}
        />
      </div>
    </section>
  )
}
