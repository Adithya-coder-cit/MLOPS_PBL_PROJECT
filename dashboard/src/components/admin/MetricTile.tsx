import './MetricTile.css'

interface MetricTileProps {
  label: string
  value: string
}

export function MetricTile({ label, value }: MetricTileProps) {
  return (
    <div className="rw-metric-tile">
      <span className="rw-metric-tile__label">{label}</span>
      <span className="rw-metric-tile__value data">{value}</span>
    </div>
  )
}
