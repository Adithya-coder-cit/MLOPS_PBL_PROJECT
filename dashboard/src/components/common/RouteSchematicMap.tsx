import type { StopSchema } from '../../api/types'
import './RouteSchematicMap.css'

interface RouteSchematicMapProps {
  // Real stops with real lat/lon — in visual order for a route, or
  // unordered for a network overview. Never a fabricated coordinate.
  stops: StopSchema[]
  connectPath?: boolean
  highlightIds?: string[]
  label: string
}

interface Projected {
  stop: StopSchema
  x: number
  y: number
}

function project(stops: StopSchema[], width: number, height: number, padding: number): Projected[] {
  const lats = stops.map((s) => s.lat)
  const lons = stops.map((s) => s.lon)
  const minLat = Math.min(...lats)
  const maxLat = Math.max(...lats)
  const minLon = Math.min(...lons)
  const maxLon = Math.max(...lons)
  const latRange = maxLat - minLat || 1
  const lonRange = maxLon - minLon || 1
  return stops.map((s) => ({
    stop: s,
    x: padding + ((s.lon - minLon) / lonRange) * (width - 2 * padding),
    // Latitude increases northward; SVG y increases downward — invert.
    y: padding + (1 - (s.lat - minLat) / latRange) * (height - 2 * padding),
  }))
}

export function RouteSchematicMap({ stops, connectPath = false, highlightIds = [], label }: RouteSchematicMapProps) {
  if (stops.length === 0) return null

  const width = 640
  const height = 320
  const padding = 28
  const points = project(stops, width, height, padding)
  const highlightSet = new Set(highlightIds)

  return (
    <div className="rw-schematic">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label} className="rw-schematic__svg">
        {connectPath && points.length > 1 && (
          <polyline
            className="rw-schematic__path"
            points={points.map((p) => `${p.x},${p.y}`).join(' ')}
          />
        )}
        {points.map(({ stop, x, y }) => (
          <g key={stop.stop_id}>
            <circle
              cx={x}
              cy={y}
              r={highlightSet.has(stop.stop_id) ? 6 : 3.5}
              className={highlightSet.has(stop.stop_id) ? 'rw-schematic__dot--highlight' : 'rw-schematic__dot'}
            />
            <title>{stop.stop_name}</title>
          </g>
        ))}
      </svg>
      <p className="rw-schematic__caption">
        Plotted from each stop's real latitude/longitude — a schematic, not a street map.
      </p>
    </div>
  )
}
