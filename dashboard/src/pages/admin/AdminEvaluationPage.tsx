import { useEffect, useState } from 'react'
import type { EvaluationModelSchema } from '../../api/types'
import { useEvaluationOverview } from '../../hooks/useEvaluationOverview'
import { MetricTile } from '../../components/admin/MetricTile'
import { RefreshButton } from '../../components/admin/RefreshButton'
import { SectionHeading } from '../../components/common/SectionHeading'
import { ErrorState, LoadingState } from '../../components/common/StatusStates'
import { friendlyErrorMessage } from '../../lib/errorMessages'
import { formatCount } from '../../lib/format'
import './AdminEvaluationPage.css'

const METRIC_LABELS: Record<string, string> = {
  accuracy: 'Accuracy',
  precision: 'Precision',
  recall: 'Recall',
  f1: 'F1',
  roc_auc: 'ROC-AUC',
  pr_auc: 'PR-AUC',
}

function ConfusionMatrix({ cm }: { cm: { tn: number; fp: number; fn: number; tp: number } }) {
  return (
    <table className="rw-confusion-matrix">
      <tbody>
        <tr>
          <td />
          <th scope="col">Predicted no disruption</th>
          <th scope="col">Predicted disruption</th>
        </tr>
        <tr>
          <th scope="row">Actual no disruption</th>
          <td className="data">{formatCount(cm.tn)}</td>
          <td className="data rw-confusion-matrix__off">{formatCount(cm.fp)}</td>
        </tr>
        <tr>
          <th scope="row">Actual disruption</th>
          <td className="data rw-confusion-matrix__off">{formatCount(cm.fn)}</td>
          <td className="data">{formatCount(cm.tp)}</td>
        </tr>
      </tbody>
    </table>
  )
}

function ModelEvaluation({ model }: { model: EvaluationModelSchema }) {
  return (
    <article className="rw-admin-eval-model">
      <h3>{model.model_type}</h3>

      <div className="rw-admin-page__grid">
        {Object.entries(METRIC_LABELS).map(([key, label]) =>
          model.test_metrics[key] !== undefined ? (
            <MetricTile key={key} label={label} value={model.test_metrics[key].toFixed(4)} />
          ) : null,
        )}
      </div>

      <div className="rw-admin-eval-model__section">
        <h4>Confusion matrix (test set)</h4>
        {model.confusion_matrix ? <ConfusionMatrix cm={model.confusion_matrix} /> : <p className="rw-admin-page__unavailable">Artifact unavailable</p>}
      </div>

      <div className="rw-admin-eval-model__section">
        <h4>Feature importance</h4>
        {model.feature_importance && model.feature_importance.length > 0 ? (
          <ul className="rw-admin-eval-model__importance">
            {model.feature_importance.slice(0, 10).map((f) => {
              // Real metric names differ by library — never normalize XGBoost's
              // "gain" and scikit-learn's "importance" into one fabricated value.
              const metric = f.gain !== undefined ? 'gain' : 'importance'
              const value = f.gain ?? f.importance
              return (
                <li key={f.feature}>
                  <span>{f.feature}</span>
                  <span className="data">
                    {value !== undefined ? value.toFixed(metric === 'gain' ? 2 : 4) : 'Not available'} ({metric})
                  </span>
                </li>
              )
            })}
          </ul>
        ) : (
          <p className="rw-admin-page__unavailable">Artifact unavailable</p>
        )}
      </div>

      <div className="rw-admin-eval-model__section">
        <h4>Threshold sensitivity (validation set — precision/recall/F1 at each real evaluated threshold)</h4>
        {model.threshold_sensitivity && model.threshold_sensitivity.length > 0 ? (
          <div className="rw-admin-table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Threshold</th>
                  <th scope="col">Precision</th>
                  <th scope="col">Recall</th>
                  <th scope="col">F1</th>
                </tr>
              </thead>
              <tbody>
                {model.threshold_sensitivity.map((row) => (
                  <tr key={row.threshold}>
                    <th scope="row" className="data">{row.threshold.toFixed(1)}</th>
                    <td className="data">{row.precision.toFixed(4)}</td>
                    <td className="data">{row.recall.toFixed(4)}</td>
                    <td className="data">{row.f1.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="rw-admin-page__unavailable">Artifact unavailable</p>
        )}
      </div>

      <div className="rw-admin-eval-model__section">
        <h4>ROC curve / Precision-Recall curve</h4>
        <p className="rw-admin-page__unavailable">
          Artifact unavailable — only the scalar ROC-AUC/PR-AUC and the 9-point threshold sensitivity table above were
          saved, not continuous curve points.
        </p>
      </div>
    </article>
  )
}

export function AdminEvaluationPage() {
  const { status, data, error, run } = useEvaluationOverview()
  const [selectedModel, setSelectedModel] = useState<string | null>(null)
  const runEvaluation = run

  useEffect(() => {
    runEvaluation().catch(() => {})
  }, [runEvaluation])

  const models = data?.models ?? []
  const active = models.find((m) => m.model_type === selectedModel) ?? models[0] ?? null

  return (
    <section aria-labelledby="evaluation-heading">
      <div className="rw-admin-page__heading-row">
        <div id="evaluation-heading">
          <SectionHeading>Evaluation</SectionHeading>
        </div>
        <RefreshButton onRefresh={() => runEvaluation().catch(() => {})} loading={status === 'loading'} />
      </div>
      <p className="rw-admin-page__intro">Real saved evaluation artifacts from the latest completed training run.</p>

      {status === 'loading' && <LoadingState label="Loading evaluation artifacts…" />}
      {status === 'error' && <ErrorState message={friendlyErrorMessage(error)} />}
      {status === 'success' && data && !data.available && (
        <p className="rw-admin-page__unavailable">{data.reason ?? 'No evaluation artifacts are available.'}</p>
      )}

      {status === 'success' && data?.available && active && (
        <>
          {models.length > 1 && (
            <div className="rw-admin-eval-tabs">
              {models.map((m) => (
                <button
                  key={m.model_type}
                  type="button"
                  className={`rw-admin-eval-tabs__tab ${active.model_type === m.model_type ? 'rw-admin-eval-tabs__tab--active' : ''}`}
                  onClick={() => setSelectedModel(m.model_type)}
                >
                  {m.model_type}
                </button>
              ))}
            </div>
          )}
          <ModelEvaluation model={active} />

          {data.comparison.length > 0 && (
            <div className="rw-admin-eval-model__section">
              <h4>Model comparison (test set, selection metric: {data.selection_metric})</h4>
              <div className="rw-admin-table-wrap">
                <table>
                  <thead>
                    <tr>
                      {Object.keys(data.comparison[0]).map((k) => (
                        <th scope="col" key={k}>{k}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.comparison.map((row, i) => (
                      <tr key={i}>
                        {Object.values(row).map((v, j) => (
                          <td key={j} className="data">{typeof v === 'number' ? v.toFixed(4) : String(v)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  )
}
