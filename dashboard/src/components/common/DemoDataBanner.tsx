import './DemoDataBanner.css'

export function DemoDataBanner() {
  return (
    <div className="rw-demo-banner" role="note">
      <strong>Development/Demo Data.</strong> RouteWise runs on a synthetic
      transit network generated for this project — not live Chennai (or any
      real city's) transportation data.
    </div>
  )
}
