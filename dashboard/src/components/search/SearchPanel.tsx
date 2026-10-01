import { useId, useState, type FormEvent } from 'react'
import type { StopSchema } from '../../api/types'
import { StopCombobox } from './StopCombobox'
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

export function SearchPanel({ stops, stopsLoading, onSearch, searching }: SearchPanelProps) {
  const [origin, setOrigin] = useState('')
  const [destination, setDestination] = useState('')
  const [departureTime, setDepartureTime] = useState('')
  const [errors, setErrors] = useState<FormErrors>({})
  const originId = useId()
  const destinationId = useId()
  const departureId = useId()

  // A handful of real stops genuinely have zero scheduled trips in this
  // dataset (has_scheduled_service, computed from the real routing graph's
  // node degree) — excluded from search here so users can't pick a pair
  // that's guaranteed to fail, without hiding them anywhere else (e.g. the
  // Network Map still shows every real stop, served or not).
  const searchableStops = stops.filter((s) => s.has_scheduled_service)
  const validStopIds = new Set(searchableStops.map((s) => s.stop_id))

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

    onSearch({ origin, destination, departureTime, topN: 3 })
  }

  function swap() {
    setOrigin(destination)
    setDestination(origin)
  }

  return (
    <section aria-labelledby="search-heading" className="rw-search-panel">
      <h2 id="search-heading" className="visually-hidden">
        Plan your journey
      </h2>
      <form className="rw-search-form" onSubmit={handleSubmit} noValidate>
        <div className="rw-search-form__stops">
          <StopCombobox
            id={originId}
            label="From"
            placeholder="Search starting location…"
            stops={searchableStops}
            loading={stopsLoading}
            value={origin}
            onChange={setOrigin}
            invalid={Boolean(errors.origin)}
            describedBy={errors.origin ? `${originId}-error` : undefined}
          />

          <button
            type="button"
            className="rw-search-form__swap"
            aria-label="Swap origin and destination"
            onClick={swap}
            disabled={!origin && !destination}
          >
            ⇄
          </button>

          <StopCombobox
            id={destinationId}
            label="To"
            placeholder="Search destination…"
            stops={searchableStops}
            loading={stopsLoading}
            value={destination}
            onChange={setDestination}
            invalid={Boolean(errors.destination)}
            describedBy={errors.destination ? `${destinationId}-error` : undefined}
          />
        </div>

        <div className="rw-search-form__errors">
          {errors.origin && (
            <p className="rw-field__error" id={`${originId}-error`} role="alert">
              {errors.origin}
            </p>
          )}
          {errors.destination && (
            <p className="rw-field__error" id={`${destinationId}-error`} role="alert">
              {errors.destination}
            </p>
          )}
        </div>

        <details className="rw-search-form__optional">
          <summary>Departure time (optional)</summary>
          <div className="rw-field">
            <label htmlFor={departureId}>Departure</label>
            <input
              id={departureId}
              type="datetime-local"
              value={departureTime}
              onChange={(e) => setDepartureTime(e.target.value)}
            />
            <p className="rw-field__hint">Leave blank to use the system's reference schedule time.</p>
          </div>
        </details>

        <button type="submit" className="rw-search-form__submit" disabled={stopsLoading || searching}>
          {searching ? 'Searching…' : 'Find best routes'}
        </button>
      </form>
    </section>
  )
}
