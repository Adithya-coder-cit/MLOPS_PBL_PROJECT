import { useEffect } from 'react'
import { useDataSummary } from '../../hooks/useDataSummary'
import { MetricTile } from '../../components/admin/MetricTile'
import { SectionHeading } from '../../components/common/SectionHeading'
import { ErrorState, LoadingState } from '../../components/common/StatusStates'
import { friendlyErrorMessage } from '../../lib/errorMessages'
import { formatCount, formatPercent } from '../../lib/format'
import './AdminDataPage.css'

function pct(v: number | null): string {
  return v === null ? 'Not available' : formatPercent(v)
}

function count(v: number | null | undefined): string {
  return v === null || v === undefined ? 'Not available' : formatCount(v)
}

export function AdminDataPage() {
  const { status, data, error, run } = useDataSummary()
  const runSummary = run

  useEffect(() => {
    runSummary().catch(() => {})
  }, [runSummary])

  return (
    <section aria-labelledby="data-heading">
      <div id="data-heading">
        <SectionHeading>Data</SectionHeading>
      </div>
      <p className="rw-admin-page__intro">Real ingested-dataset summary, read from the Stage 11 pipeline artifacts.</p>

      {status === 'loading' && <LoadingState label="Loading data summary…" />}
      {status === 'error' && <ErrorState message={friendlyErrorMessage(error)} />}
      {status === 'success' && data && !data.available && (
        <p className="rw-admin-page__unavailable">{data.reason ?? 'Real-data reports are not available.'}</p>
      )}

      {status === 'success' && data?.available && (
        <div className="rw-admin-data">
          <div className="rw-admin-data__tiles">
            <MetricTile label="Total real records" value={count(data.total_real_records)} />
            <MetricTile label="Eligible supervised records" value={count(data.eligible_records)} />
            <MetricTile label="Excluded records" value={count(data.excluded_records)} />
            <MetricTile label="Historical feature coverage" value={pct(data.historical_feature_coverage)} />
            <MetricTile label="Weather coverage" value={pct(data.weather_coverage)} />
            <MetricTile label="Modes" value={data.modes.length > 0 ? data.modes.join(', ') : 'Not available'} />
          </div>

          <div className="rw-admin-data__facts">
            <span>
              Data source: <strong>{data.data_source}</strong>
            </span>
            <span>
              DVC configured: <strong>{data.dvc_configured ? 'Yes' : 'No'}</strong>
            </span>
            <span>
              REAL_DATASET_READY:{' '}
              <strong className={data.real_dataset_ready ? 'rw-admin-data__ready-yes' : 'rw-admin-data__ready-no'}>
                {data.real_dataset_ready === null ? 'Not available' : String(data.real_dataset_ready)}
              </strong>
            </span>
          </div>

          {Object.keys(data.weather_coverage_by_mode).length > 0 && (
            <div className="rw-admin-data__section">
              <h4>Weather coverage by mode</h4>
              <div className="rw-admin-data__tiles">
                {Object.entries(data.weather_coverage_by_mode).map(([mode, coverage]) => (
                  <MetricTile key={mode} label={mode} value={formatPercent(coverage)} />
                ))}
              </div>
            </div>
          )}

          {data.splits.length > 0 && (
            <div className="rw-admin-data__section">
              <h4>Eligible temporal split</h4>
              <div className="rw-admin-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Split</th>
                      <th scope="col">Records</th>
                      <th scope="col">Positive rate</th>
                      <th scope="col">Modes present</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.splits.map((s) => (
                      <tr key={s.split}>
                        <th scope="row">{s.split}</th>
                        <td className="data">{formatCount(s.records)}</td>
                        <td className="data">{s.positive_rate !== null ? formatPercent(s.positive_rate) : 'Not available'}</td>
                        <td>{Object.keys(s.modes).join(', ') || 'Not available'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
