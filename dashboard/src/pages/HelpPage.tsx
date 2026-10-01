import { SectionHeading } from '../components/common/SectionHeading'
import './HelpPage.css'

const WORKFLOW_STEPS = [
  'You',
  'Stop selection',
  'FastAPI',
  'Disruption prediction',
  'Multimodal graph',
  'Route candidates',
  'Constraint-aware scoring',
  'Recommended route',
  'Adaptive rerouting',
]

export function HelpPage() {
  return (
    <section aria-labelledby="help-heading" className="rw-help">
      <div id="help-heading">
        <SectionHeading>Help</SectionHeading>
      </div>

      <article className="rw-help__card">
        <h3>How a request actually flows through RouteWise</h3>
        <ol className="rw-help__flow" aria-label="RouteWise request workflow">
          {WORKFLOW_STEPS.map((step, i) => (
            <li key={step}>
              <span>{step}</span>
              {i < WORKFLOW_STEPS.length - 1 && (
                <span className="rw-help__flow-arrow" aria-hidden="true">
                  →
                </span>
              )}
            </li>
          ))}
        </ol>
        <p>
          Every one of those steps is a real call in this codebase, not a diagram drawn for the demo: the dashboard
          calls the FastAPI backend, the backend scores disruption risk with a trained model, builds candidates over
          a real multimodal graph, ranks them with a constraint-aware scoring function, and — if you ask it to — can
          adaptively recalculate a route after a supplied disruption update.
        </p>
      </article>

      <article className="rw-help__card">
        <h3>Planning a journey</h3>
        <p>
          Choose a starting location and a destination from the real stop list, then select "Find best routes".
          RouteWise sends your selection to the routing API, which returns ranked route candidates computed from
          the real transit graph and disruption-risk scoring — nothing on the results page is precomputed or
          hardcoded. A handful of stops in this dataset genuinely have no scheduled trips serving them (a data gap,
          not a bug) — those are excluded from the origin/destination search so you can't pick a pair that's
          guaranteed to fail.
        </p>
      </article>

      <article className="rw-help__card">
        <h3>Disruption prediction</h3>
        <p>
          Each leg of each candidate route is scored by a trained classification model (XGBoost, with a Random
          Forest baseline for comparison) for the probability that leg experiences a disruption. The model reads
          weather, time-of-day, transport mode, transfer-dependency, and historical/rolling delay features — see
          Engineering → Model Registry for exactly which model version is currently loaded and its real
          validation/test metrics.
        </p>
      </article>

      <article className="rw-help__card">
        <h3>Reliability and route scoring</h3>
        <p>
          A leg's reliability is simply 1 minus its predicted disruption probability. A whole route's reliability
          combines every leg's reliability and subtracts a configured penalty per transfer — more transfers, lower
          reliability, even if each individual leg looks fine. Candidates are ranked by a multi-objective score
          (cost + time − reliability, each weighted) rather than any single factor alone. When a route's disruption
          risk crosses a configured threshold, RouteWise automatically switches to a "high risk" weighting that
          values reliability more heavily than normal — a documented, deterministic policy switch, not a learned
          behavior. Each route card and journey page shows which policy scored it.
        </p>
      </article>

      <article className="rw-help__card">
        <h3>The multimodal graph</h3>
        <p>
          Routes are found over a real directed graph built from this project's GTFS-style schedule data — one node
          per stop, one edge per scheduled leg. The network mixes five real transport modes (bus, tram, metro, rail,
          and ferry), all of them routable and all of them scored by the prediction model. Open Network Map to see
          the real stops and, by selecting a route, its real ordered stop sequence plotted from real coordinates.
        </p>
      </article>

      <article className="rw-help__card">
        <h3>Adaptive rerouting</h3>
        <p>
          From a journey's details, you can simulate a disruption on one segment and ask RouteWise to recalculate.
          This is a manual, caller-supplied update for demonstration — it is not connected to a live traffic or
          incident feed. The recalculation itself happens entirely in the backend (the same scoring and graph-search
          code used for the original search); the frontend only displays the before/after comparison the backend
          returns, it never recomputes a route itself.
        </p>
      </article>

      <article className="rw-help__card">
        <h3>MLOps: MLflow, monitoring, and retraining</h3>
        <p>
          Every model shown in Engineering comes from a real MLflow tracking server and model registry — experiment
          runs, parameters, metrics, registered versions, and lifecycle stage (Candidate vs. Production) are all
          read live, never hardcoded. Data-quality and drift monitoring (via Evidently) and a retraining
          readiness check run against this project's data; their real, current status — including when nothing has
          been run yet — is visible under Engineering → Monitoring. None of this promotes a model or changes
          registry state by itself; promotion is a separate, explicit, human-run step outside this dashboard.
        </p>
      </article>

      <article className="rw-help__card">
        <h3>About this project</h3>
        <p>
          RouteWise runs on a synthetic transit network generated for this project, not live transportation data.
          That synthetic network itself is not hardcoded into the frontend — every stop, route, and coordinate
          you see is loaded dynamically from the backend's real GTFS-style data files at request time.
        </p>
        <p>
          The disruption-prediction model currently in use is a development/candidate model — no model has been
          promoted to production yet, and the app is honest about that everywhere it matters rather than implying
          otherwise.
        </p>
      </article>
    </section>
  )
}
