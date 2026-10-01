import { useRef, useState, type PointerEvent, type WheelEvent } from 'react'
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

const BASE_WIDTH = 640
const BASE_HEIGHT = 320
const MIN_SCALE = 1
const MAX_SCALE = 6

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

function clampPan(value: number, viewSize: number, baseSize: number): number {
  const max = baseSize - viewSize
  if (max <= 0) return max / 2
  return Math.min(Math.max(value, 0), max)
}

export function RouteSchematicMap({ stops, connectPath = false, highlightIds = [], label }: RouteSchematicMapProps) {
  const [scale, setScale] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const dragRef = useRef<{ startX: number; startY: number; panX: number; panY: number } | null>(null)

  if (stops.length === 0) return null

  const points = project(stops, BASE_WIDTH, BASE_HEIGHT, 28)
  const highlightSet = new Set(highlightIds)

  const viewWidth = BASE_WIDTH / scale
  const viewHeight = BASE_HEIGHT / scale
  const viewX = clampPan(pan.x, viewWidth, BASE_WIDTH)
  const viewY = clampPan(pan.y, viewHeight, BASE_HEIGHT)

  function zoomBy(factor: number) {
    setScale((s) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, s * factor)))
  }

  function resetView() {
    setScale(1)
    setPan({ x: 0, y: 0 })
  }

  function handleWheel(e: WheelEvent<SVGSVGElement>) {
    e.preventDefault()
    zoomBy(e.deltaY < 0 ? 1.2 : 1 / 1.2)
  }

  function handlePointerDown(e: PointerEvent<SVGSVGElement>) {
    if (scale === 1) return
    dragRef.current = { startX: e.clientX, startY: e.clientY, panX: viewX, panY: viewY }
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  function handlePointerMove(e: PointerEvent<SVGSVGElement>) {
    const drag = dragRef.current
    if (!drag) return
    // Screen pixels -> SVG user units, accounting for the rendered scale.
    const rect = e.currentTarget.getBoundingClientRect()
    const unitsPerPixelX = viewWidth / rect.width
    const unitsPerPixelY = viewHeight / rect.height
    const dx = (e.clientX - drag.startX) * unitsPerPixelX
    const dy = (e.clientY - drag.startY) * unitsPerPixelY
    setPan({ x: drag.panX - dx, y: drag.panY - dy })
  }

  function handlePointerUp() {
    dragRef.current = null
  }

  return (
    <div className="rw-schematic">
      <div className="rw-schematic__controls" role="group" aria-label="Map zoom controls">
        <button type="button" onClick={() => zoomBy(1.4)} aria-label="Zoom in">
          +
        </button>
        <button type="button" onClick={() => zoomBy(1 / 1.4)} aria-label="Zoom out">
          −
        </button>
        <button type="button" onClick={resetView} aria-label="Reset zoom and pan">
          Reset
        </button>
      </div>
      <svg
        viewBox={`${viewX} ${viewY} ${viewWidth} ${viewHeight}`}
        role="img"
        aria-label={label}
        className={`rw-schematic__svg ${scale > 1 ? 'rw-schematic__svg--zoomed' : ''}`}
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
      >
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
        Plotted from each stop's real latitude/longitude — a schematic, not a street map. Scroll or use the buttons
        to zoom; drag to pan once zoomed in.
      </p>
    </div>
  )
}
