import { useId, useState, type FormEvent } from 'react'
import type { StopSchema } from '../../api/types'
import { SectionHeading } from '../common/SectionHeading'
import './SearchPanel.css'

export interface SearchValues {
  origin: string
  destination: string
  departureTime: string
  topN: number
}

interface SearchPanelProps {
  stops: StopSchema[]
  stopsLoading: boolean
  onSearch: (values: SearchValues) => void
  searching: boolean
}

interface FormErrors {
  origin?: string
  destination?: string
}

const stopLabel = (stop: StopSchema) => `${stop.stop_name} (${stop.stop_id})`

export function SearchPanel({ stops, stopsLoading, onSearch, searching }: SearchPanelProps) {
  const [origin, setOrigin] = useState('')
  const [destination, setDestination] = useState('')
  const [departureTime, setDepartureTime] = useState('')
  const [errors, setErrors] = useState<FormErrors>({})
  const originId = useId()
  const destinationId = useId()
  const departureId = useId()

  const validStopIds = new Set(stops.map((s) => s.stop_id))

  function validate(): FormErrors {
    const next: FormErrors = {}
    if (!origin) next.origin = 'Choose an origin stop.'
    else if (!validStopIds.has(origin)) next.origin = "That stop isn't in the current dataset."

    if (!destination) next.destination = 'Choose a destination stop.'
    else if (!validStopIds.has(destination)) next.destination = "That stop isn't in the current dataset."

    if (origin && destination && origin === destination) {
      next.destination = 'Destination must be different from origin.'
    }
    return next
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const validation = validate()
    setErrors(validation)
    if (Object.keys(validation).length > 0) return

    onSearch({
      origin,
      destination,
      departureTime,
      topN: 3,
    })
  }

  return (
    <section aria-labelledby="search-heading">
      <div id="search-heading">
        <SectionHeading>Plan a route</SectionHeading>
      </div>
      <form className="rw-search-form" onSubmit={handleSubmit} noValidate>
        <div className="rw-field">
          <label htmlFor={originId}>Origin</label>
          <select
            id={originId}
            value={origin}
            onChange={(e) => setOrigin(e.target.value)}
            disabled={stopsLoading}
            aria-invalid={Boolean(errors.origin)}
            aria-describedby={errors.origin ? `${originId}-error` : undefined}
          >
            <option value="">{stopsLoading ? 'Loading stops…' : 'Select a stop'}</option>
            {stops.map((stop) => (
              <option key={stop.stop_id} value={stop.stop_id}>
                {stopLabel(stop)}
              </option>
            ))}
          </select>
          {errors.origin && (
            <p className="rw-field__error" id={`${originId}-error`} role="alert">
              {errors.origin}
            </p>
          )}
        </div>

        <div className="rw-field">
          <label htmlFor={destinationId}>Destination</label>
          <select
            id={destinationId}
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            disabled={stopsLoading}
            aria-invalid={Boolean(errors.destination)}
            aria-describedby={errors.destination ? `${destinationId}-error` : undefined}
          >
            <option value="">{stopsLoading ? 'Loading stops…' : 'Select a stop'}</option>
            {stops.map((stop) => (
              <option key={stop.stop_id} value={stop.stop_id}>
                {stopLabel(stop)}
              </option>
            ))}
          </select>
          {errors.destination && (
            <p className="rw-field__error" id={`${destinationId}-error`} role="alert">
              {errors.destination}
            </p>
          )}
        </div>

        <div className="rw-field">
          <label htmlFor={departureId}>Departure time (optional)</label>
          <input
            id={departureId}
            type="datetime-local"
            value={departureTime}
            onChange={(e) => setDepartureTime(e.target.value)}
          />
          <p className="rw-field__hint">Leave blank to use the system's reference schedule time.</p>
        </div>

        <button type="submit" className="rw-search-form__submit" disabled={stopsLoading || searching}>
          {searching ? 'Searching…' : 'Search routes'}
        </button>
      </form>
    </section>
  )
}
