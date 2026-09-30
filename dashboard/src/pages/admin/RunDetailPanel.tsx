import { useEffect } from 'react'
import { useRunDetail } from '../../hooks/useRunDetail'
import { ErrorState, LoadingState } from '../../components/common/StatusStates'
import { LifecycleBadge } from '../../components/admin/LifecycleBadge'
import { friendlyErrorMessage } from '../../lib/errorMessages'
import { formatDateTime } from '../../lib/format'
import './RunDetailPanel.css'

interface RunDetailPanelProps {
  runId: string
  onClose: () => void
}

export function RunDetailPanel({ runId, onClose }: RunDetailPanelProps) {
  const { status, data, error, run } = useRunDetail()

  useEffect(() => {
    run(runId).catch(() => {})
  }, [runId, run])

  return (
    <div className="rw-run-detail-overlay" role="presentation" onClick={onClose}>
      <div
        className="rw-run-detail-panel"
        role="dialog"
        aria-modal="true"
        aria-label="Run details"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="rw-run-detail-panel__header">
          <h3>Run details</h3>
          <button type="button" onClick={onClose} aria-label="Close run details">
            Close
          </button>
        </header>

        {status === 'loading' && <LoadingState label="Loading run detail…" />}
        {status === 'error' && <ErrorState message={friendlyErrorMessage(error)} />}

        {status === 'success' && data && (
          <div className="rw-run-detail-panel__body">
            <dl className="rw-run-detail-panel__facts">
              <div>
                <dt>Run</dt>
                <dd>{data.run_name ?? data.run_id}</dd>
              </div>
              <div>
                <dt>Run ID</dt>
                <dd className="data">{data.run_id}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{data.status}</dd>
              </div>
              <div>
                <dt>Registered version</dt>
                <dd>
                  {data.registered_version ?? 'Not registered'}
                  {data.lifecycle_stage && (
                    <>
                      {' '}
                      <LifecycleBadge stage={data.lifecycle_stage} />
                    </>
                  )}
                </dd>
              </div>
              <div>
                <dt>Started</dt>
                <dd>{data.start_time ? formatDateTime(data.start_time) : 'Not available'}</dd>
              </div>
              <div>
                <dt>Ended</dt>
                <dd>{data.end_time ? formatDateTime(data.end_time) : 'Not available'}</dd>
              </div>
            </dl>

            <section>
              <h4>Metrics</h4>
              <dl className="rw-run-detail-panel__kv">
                {Object.entries(data.metrics).map(([k, v]) => (
                  <div key={k}>
                    <dt>{k}</dt>
                    <dd className="data">{v.toFixed(4)}</dd>
                  </div>
                ))}
              </dl>
            </section>

            <section>
              <h4>Parameters</h4>
              <dl className="rw-run-detail-panel__kv">
                {Object.entries(data.params).map(([k, v]) => (
                  <div key={k}>
                    <dt>{k}</dt>
                    <dd className="data">{v}</dd>
                  </div>
                ))}
              </dl>
            </section>

            <section>
              <h4>Artifacts</h4>
              {data.artifact_paths.length > 0 ? (
                <ul className="rw-run-detail-panel__artifacts">
                  {data.artifact_paths.map((p) => (
                    <li key={p} className="data">
                      {p}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="rw-run-detail-panel__unavailable">Artifact unavailable</p>
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  )
}
