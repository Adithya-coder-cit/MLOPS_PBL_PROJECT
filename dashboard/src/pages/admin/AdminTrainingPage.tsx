import { useEffect, useState } from 'react'
import type { AdminSection } from '../../types/navigation'
import { useTrainingStatus } from '../../hooks/useTrainingStatus'
import { RefreshButton } from '../../components/admin/RefreshButton'
import { StatCard } from '../../components/admin/StatCard'
import { SectionHeading } from '../../components/common/SectionHeading'
import { ErrorState, LoadingState } from '../../components/common/StatusStates'
import { friendlyErrorMessage } from '../../lib/errorMessages'
import { formatCount, formatDateTime } from '../../lib/format'
import { RunDetailPanel } from './RunDetailPanel'
import './AdminTrainingPage.css'

interface AdminTrainingPageProps {
  onNavigate: (section: AdminSection) => void
}

export function AdminTrainingPage({ onNavigate }: AdminTrainingPageProps) {
  const { status, data, error, run } = useTrainingStatus()
  const [openRunId, setOpenRunId] = useState<string | null>(null)
  const runStatus = run

  useEffect(() => {
    runStatus().catch(() => {})
  }, [runStatus])

  return (
    <section aria-labelledby="training-heading">
      <div className="rw-admin-page__heading-row">
        <div id="training-heading">
          <SectionHeading>Model Training and Evaluation</SectionHeading>
        </div>
        <RefreshButton onRefresh={() => runStatus().catch(() => {})} loading={status === 'loading'} />
      </div>
      <p className="rw-admin-page__intro">
        Train and evaluate models for transit disruption prediction. Every value below is read from a real saved
        artifact — nothing is simulated.
      </p>

      {status === 'loading' && <LoadingState label="Loading training status…" />}
      {status === 'error' && <ErrorState message={friendlyErrorMessage(error)} />}

      {status === 'success' && data && (
        <div className="rw-admin-page__grid">
          <StatCard title="Training Pipeline">
            <p className="rw-admin-training__no-run">No active training run.</p>
            <div className="rw-admin-training__readiness">
              <span>Real-data training readiness</span>
              {data.real_data_model_ready ? (
                <span className="rw-admin-training__ready rw-admin-training__ready--yes">MODEL_READY</span>
              ) : (
                <span className="rw-admin-training__ready rw-admin-training__ready--no">MODEL_READY = false</span>
              )}
            </div>
            {!data.real_data_model_ready && data.real_data_model_ready_reason && (
              <p className="rw-admin-training__reason">{data.real_data_model_ready_reason}</p>
            )}
            <button
              type="button"
              className="rw-admin-training__start-button"
              disabled
              title={
                data.real_data_model_ready
                  ? 'Model readiness is satisfied, but this interface does not trigger real training jobs.'
                  : 'Training unavailable — model readiness requirements are not satisfied.'
              }
            >
              {data.real_data_model_ready ? 'Start New Run' : 'Training unavailable — model readiness requirements are not satisfied.'}
            </button>
          </StatCard>

          <StatCard title="Data Overview" action={<button type="button" onClick={() => onNavigate('data')}>View data →</button>}>
            {data.latest_completed_run ? (
              <dl className="rw-admin-training__facts">
                <div>
                  <dt>Dataset</dt>
                  <dd>{data.latest_completed_run.dataset_label}</dd>
                </div>
                <div>
                  <dt>Train records</dt>
                  <dd className="data">
                    {data.latest_completed_run.train_records !== null ? formatCount(data.latest_completed_run.train_records) : 'Not available'}
                  </dd>
                </div>
                <div>
                  <dt>Validation records</dt>
                  <dd className="data">
                    {data.latest_completed_run.validation_records !== null ? formatCount(data.latest_completed_run.validation_records) : 'Not available'}
                  </dd>
                </div>
                <div>
                  <dt>Test records</dt>
                  <dd className="data">
                    {data.latest_completed_run.test_records !== null ? formatCount(data.latest_completed_run.test_records) : 'Not available'}
                  </dd>
                </div>
              </dl>
            ) : (
              <p className="rw-admin-training__unavailable">Artifact unavailable</p>
            )}
          </StatCard>

          <StatCard
            title="Model Configuration"
            action={<button type="button" onClick={() => onNavigate('registry')}>View registry →</button>}
          >
            {data.latest_completed_run && data.latest_completed_run.models.length > 0 ? (
              <ul className="rw-admin-training__models">
                {data.latest_completed_run.models.map((m) => (
                  <li key={m.model_type}>
                    <div className="rw-admin-training__model-row">
                      <span className="rw-admin-training__model-name">{m.model_type}</span>
                      {m.registered_version && <span className="rw-admin-training__version data">v{m.registered_version}</span>}
                    </div>
                    <span className="rw-admin-training__model-detail">
                      {m.feature_count ?? '—'} features · gate {m.gate_passed ? 'passed' : 'not passed'}
                    </span>
                    {m.run_id && (
                      <button type="button" className="rw-admin-training__view-run" onClick={() => setOpenRunId(m.run_id)}>
                        View run
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="rw-admin-training__unavailable">Artifact unavailable</p>
            )}
          </StatCard>

          <StatCard
            title="Evaluation Results"
            action={<button type="button" onClick={() => onNavigate('evaluation')}>View evaluation →</button>}
          >
            {data.latest_completed_run && data.latest_completed_run.models.length > 0 ? (
              <div className="rw-admin-training__eval-grid">
                {data.latest_completed_run.models.map((m) => (
                  <div key={m.model_type} className="rw-admin-training__eval-tile">
                    <span className="rw-admin-training__model-name">{m.model_type}</span>
                    <span className="data">F1 {m.test_f1?.toFixed(4) ?? 'Not available'}</span>
                    <span className="data">ROC-AUC {m.test_roc_auc?.toFixed(4) ?? 'Not available'}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="rw-admin-training__unavailable">Artifact unavailable</p>
            )}
          </StatCard>

          <StatCard title="Run Information">
            {data.latest_completed_run ? (
              <dl className="rw-admin-training__facts">
                <div>
                  <dt>Training timestamp</dt>
                  <dd>{data.latest_completed_run.training_timestamp ? formatDateTime(data.latest_completed_run.training_timestamp) : 'Not available'}</dd>
                </div>
                <div>
                  <dt>Git commit</dt>
                  <dd className="data">{data.latest_completed_run.git_commit_sha?.slice(0, 12) ?? 'Not available'}</dd>
                </div>
                <div>
                  <dt>Dataset version</dt>
                  <dd className="data">{data.latest_completed_run.dataset_version ?? 'Not available'}</dd>
                </div>
              </dl>
            ) : (
              <p className="rw-admin-training__unavailable">No completed training run recorded.</p>
            )}
            {data.latest_retraining_check && (
              <p className="rw-admin-training__retrain-note">
                Latest retraining safety check: <strong>{data.latest_retraining_check.decision}</strong>
                {data.latest_retraining_check.dry_run ? ' (dry run — no model was actually trained)' : ''}, on{' '}
                {data.latest_retraining_check.timestamp ? formatDateTime(data.latest_retraining_check.timestamp) : 'an unrecorded date'}.
              </p>
            )}
          </StatCard>
        </div>
      )}

      {openRunId && <RunDetailPanel runId={openRunId} onClose={() => setOpenRunId(null)} />}
    </section>
  )
}
