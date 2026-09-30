import { useEffect, useState } from 'react'
import { useRegistryOverview } from '../../hooks/useRegistryOverview'
import { MetricTile } from '../../components/admin/MetricTile'
import { LifecycleBadge } from '../../components/admin/LifecycleBadge'
import { SectionHeading } from '../../components/common/SectionHeading'
import { ErrorState, LoadingState } from '../../components/common/StatusStates'
import { friendlyErrorMessage } from '../../lib/errorMessages'
import { formatDateTime } from '../../lib/format'
import { RunDetailPanel } from './RunDetailPanel'
import './AdminRegistryPage.css'

export function AdminRegistryPage() {
  const { status, data, error, run } = useRegistryOverview()
  const [openRunId, setOpenRunId] = useState<string | null>(null)
  const runRegistry = run

  useEffect(() => {
    runRegistry().catch(() => {})
  }, [runRegistry])

  const productionCount = data?.stage_counts.Production ?? 0

  return (
    <section aria-labelledby="registry-heading">
      <div id="registry-heading">
        <SectionHeading>Model Registry</SectionHeading>
      </div>
      <p className="rw-admin-page__intro">
        The real MLflow Model Registry state. Manage and compare model versions before promotion to production — no
        promotion happens from this view.
      </p>

      {status === 'loading' && <LoadingState label="Loading model registry…" />}
      {status === 'error' && <ErrorState message={friendlyErrorMessage(error)} />}
      {status === 'success' && data && !data.available && (
        <p className="rw-admin-page__unavailable">{data.reason ?? 'MLflow registry is not available.'}</p>
      )}

      {status === 'success' && data?.available && (
        <div className="rw-admin-registry">
          <div className="rw-admin-page__grid">
            <MetricTile label="Total models" value={String(data.total_models)} />
            <MetricTile label="Total versions" value={String(data.total_versions)} />
            <MetricTile label="Candidate" value={String(data.stage_counts.Candidate ?? 0)} />
            <MetricTile label="Validated" value={String(data.stage_counts.Validated ?? 0)} />
            <MetricTile label="Archived" value={String(data.stage_counts.Archived ?? 0)} />
            <MetricTile
              label="Production"
              value={productionCount > 0 ? String(productionCount) : 'No production model'}
            />
          </div>

          {data.models.map((model) => (
            <div key={model.name} className="rw-admin-registry__model">
              <div className="rw-admin-registry__model-header">
                <div>
                  <h3>{model.name}</h3>
                  <p>{model.description ?? 'No description recorded.'}</p>
                </div>
                <div className="rw-admin-registry__model-summary">
                  <span>
                    Latest version <strong>{model.latest_version ?? 'Not available'}</strong>
                  </span>
                  <span>
                    Production:{' '}
                    <strong className={model.production_version ? 'rw-admin-registry__has-prod' : 'rw-admin-registry__no-prod'}>
                      {model.production_version ?? 'No production model'}
                    </strong>
                  </span>
                </div>
              </div>

              <div className="rw-admin-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Version</th>
                      <th scope="col">Lifecycle</th>
                      <th scope="col">Test F1</th>
                      <th scope="col">Test ROC-AUC</th>
                      <th scope="col">Created</th>
                      <th scope="col" />
                    </tr>
                  </thead>
                  <tbody>
                    {model.versions.map((v) => (
                      <tr key={v.version}>
                        <th scope="row" className="data">
                          v{v.version}
                          {v.is_production && <span className="rw-admin-registry__prod-tag">production</span>}
                        </th>
                        <td>
                          <LifecycleBadge stage={v.lifecycle_stage} />
                        </td>
                        <td className="data">{v.test_f1 !== null ? v.test_f1.toFixed(4) : 'Not available'}</td>
                        <td className="data">{v.test_roc_auc !== null ? v.test_roc_auc.toFixed(4) : 'Not available'}</td>
                        <td>{v.created ? formatDateTime(v.created) : 'Not available'}</td>
                        <td>
                          <button type="button" onClick={() => setOpenRunId(v.run_id)}>
                            View run
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}

      {openRunId && <RunDetailPanel runId={openRunId} onClose={() => setOpenRunId(null)} />}
    </section>
  )
}
