import { useEffect, useState } from 'react'
import { useExperiments } from '../../hooks/useExperiments'
import { SectionHeading } from '../../components/common/SectionHeading'
import { ErrorState, LoadingState } from '../../components/common/StatusStates'
import { LifecycleBadge } from '../../components/admin/LifecycleBadge'
import { friendlyErrorMessage } from '../../lib/errorMessages'
import { formatDateTime } from '../../lib/format'
import { RunDetailPanel } from './RunDetailPanel'
import './AdminExperimentsPage.css'

const MLFLOW_UI_URL = 'http://localhost:5000'

export function AdminExperimentsPage() {
  const { status, data, error, run } = useExperiments()
  const [openRunId, setOpenRunId] = useState<string | null>(null)
  const runExperiments = run

  useEffect(() => {
    runExperiments().catch(() => {})
  }, [runExperiments])

  return (
    <section aria-labelledby="experiments-heading">
      <div id="experiments-heading">
        <SectionHeading>Experiments</SectionHeading>
      </div>
      <p className="rw-admin-page__intro">
        Real MLflow experiment run history for <span className="data">{data?.experiment_name ?? '…'}</span>.
      </p>

      {status === 'loading' && <LoadingState label="Loading experiment runs…" />}
      {status === 'error' && <ErrorState message={friendlyErrorMessage(error)} />}
      {status === 'success' && data && !data.available && (
        <p className="rw-admin-page__unavailable">{data.reason ?? 'Experiment history is not available.'}</p>
      )}

      {status === 'success' && data?.available && (
        <>
          <div className="rw-admin-table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Run</th>
                  <th scope="col">Model</th>
                  <th scope="col">Status</th>
                  <th scope="col">Lifecycle</th>
                  <th scope="col">Version</th>
                  <th scope="col">Start time</th>
                  <th scope="col">Test F1</th>
                  <th scope="col" />
                </tr>
              </thead>
              <tbody>
                {data.runs.map((r) => (
                  <tr key={r.run_id}>
                    <th scope="row">{r.run_name ?? r.run_id.slice(0, 8)}</th>
                    <td>{r.model_type ?? 'Not available'}</td>
                    <td>{r.status}</td>
                    <td>{r.lifecycle_stage ? <LifecycleBadge stage={r.lifecycle_stage} /> : 'Not available'}</td>
                    <td>{r.registered_version ?? 'Not available'}</td>
                    <td>{r.start_time ? formatDateTime(r.start_time) : 'Not available'}</td>
                    <td className="data">{r.metrics.test_f1 !== undefined ? r.metrics.test_f1.toFixed(4) : 'Not available'}</td>
                    <td>
                      <button type="button" onClick={() => setOpenRunId(r.run_id)}>
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <a className="rw-admin-mlflow-link" href={MLFLOW_UI_URL} target="_blank" rel="noreferrer">
            Open the full MLflow UI ↗
          </a>
        </>
      )}

      {openRunId && <RunDetailPanel runId={openRunId} onClose={() => setOpenRunId(null)} />}
    </section>
  )
}
