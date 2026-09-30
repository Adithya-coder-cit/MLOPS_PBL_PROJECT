import { SectionHeading } from '../components/common/SectionHeading'
import './HelpPage.css'

export function HelpPage() {
  return (
    <section aria-labelledby="help-heading" className="rw-help">
      <div id="help-heading">
        <SectionHeading>Help</SectionHeading>
      </div>

      <article className="rw-help__card">
        <h3>Planning a journey</h3>
        <p>
          Choose a starting location and a destination from the real stop list, then select "Find best routes".
          RouteWise sends your selection to the routing API, which returns ranked route candidates computed from
          the real transit graph and disruption-risk scoring — nothing on the results page is precomputed or
          hardcoded.
        </p>
      </article>

      <article className="rw-help__card">
        <h3>Reading a route card</h3>
        <p>
          Each card shows real values returned by the API: total travel time, cost, number of transfers, the
          sequence of transport modes, and a disruption-risk band (Low/Moderate/High). The risk band's thresholds
          come from the backend's configuration, not a hardcoded frontend value.
        </p>
      </article>

      <article className="rw-help__card">
        <h3>Adaptive rerouting</h3>
        <p>
          From a journey's details, you can simulate a disruption on one segment and ask RouteWise to recalculate.
          This is a manual, caller-supplied update for demonstration — it is not connected to a live traffic or
          incident feed.
        </p>
      </article>

      <article className="rw-help__card">
        <h3>About this project</h3>
        <p>
          RouteWise runs on a synthetic transit network generated for this project, not live transportation data.
          The disruption-prediction model currently in use is a development/candidate model — no model has been
          promoted to production yet, and the app is honest about that everywhere it matters rather than implying
          otherwise.
        </p>
      </article>
    </section>
  )
}
