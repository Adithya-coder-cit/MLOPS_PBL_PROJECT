import { SectionHeading } from '../../components/common/SectionHeading'
import './adminShared.css'

export function AdminHelpPage() {
  return (
    <section aria-labelledby="admin-help-heading">
      <div id="admin-help-heading">
        <SectionHeading>Engineering — Help</SectionHeading>
      </div>
      <div className="rw-admin-page__grid rw-admin-page__grid--spaced">
        <article className="rw-stat-card">
          <header className="rw-stat-card__header">
            <h3>What this view is</h3>
          </header>
          <p className="rw-admin-page__intro rw-admin-page__intro--tight">
            The engineering/MLOps view — separate from the traveler-facing journey pages. Every number here is read
            from a real saved artifact or the real MLflow tracking/registry store, never simulated or invented.
          </p>
        </article>
        <article className="rw-stat-card">
          <header className="rw-stat-card__header">
            <h3>Model readiness</h3>
          </header>
          <p className="rw-admin-page__intro rw-admin-page__intro--tight">
            "MODEL_READY" (Training page) reflects whether the real ingested dataset currently clears the bar for
            training on real data — separate from whether a model has been registered on the synthetic development
            dataset.
          </p>
        </article>
        <article className="rw-stat-card">
          <header className="rw-stat-card__header">
            <h3>Promotion</h3>
          </header>
          <p className="rw-admin-page__intro rw-admin-page__intro--tight">
            Nothing in this view promotes a model or changes registry state. Promotion is a separate, explicit,
            human-run step (training/promote_model.py --confirm) outside this UI.
          </p>
        </article>
      </div>
    </section>
  )
}
