import { useMemo, useRef, useState, type KeyboardEvent } from 'react'
import type { StopSchema } from '../../api/types'
import { stopPrimaryLabel, stopSecondaryLabel } from '../../lib/stopLabel'
import './StopCombobox.css'

interface StopComboboxProps {
  id: string
  label: string
  placeholder: string
  stops: StopSchema[]
  loading: boolean
  value: string
  onChange: (stopId: string) => void
  invalid?: boolean
  describedBy?: string
}

function displayLabel(stop: StopSchema): string {
  return `${stopPrimaryLabel(stop)} · ${stopSecondaryLabel(stop)}`
}

export function StopCombobox({
  id,
  label,
  placeholder,
  stops,
  loading,
  value,
  onChange,
  invalid,
  describedBy,
}: StopComboboxProps) {
  // What the user has actively typed while the listbox is open. While
  // closed, the input's displayed text is derived straight from `value`
  // (the committed selection) — no separate state to keep in sync.
  const [typedQuery, setTypedQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listboxId = `${id}-listbox`

  const selected = useMemo(() => stops.find((s) => s.stop_id === value) ?? null, [stops, value])
  const inputValue = open ? typedQuery : (selected ? displayLabel(selected) : '')

  const filtered = useMemo(() => {
    if (!open || typedQuery.trim() === '') return stops
    const q = typedQuery.toLowerCase()
    return stops.filter((s) => displayLabel(s).toLowerCase().includes(q))
  }, [stops, typedQuery, open])

  function openWithFreshQuery() {
    setTypedQuery('')
    setOpen(true)
    setActiveIndex(0)
  }

  function commit(stop: StopSchema) {
    onChange(stop.stop_id)
    setOpen(false)
  }

  function clearSelection() {
    onChange('')
    setTypedQuery('')
    setOpen(true)
    setActiveIndex(0)
    inputRef.current?.focus()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      if (!open) {
        openWithFreshQuery()
        return
      }
      setActiveIndex((i) => Math.min(i + 1, filtered.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((i) => Math.max(i - 1, 0))
    } else if (event.key === 'Enter') {
      if (open && filtered[activeIndex]) {
        event.preventDefault()
        commit(filtered[activeIndex])
      }
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  const activeId = open && filtered[activeIndex] ? `${listboxId}-option-${filtered[activeIndex].stop_id}` : undefined

  return (
    <div className="rw-combobox">
      <label htmlFor={id}>{label}</label>
      <div className="rw-combobox__field">
        <span className="rw-combobox__icon" aria-hidden="true">
          🔍
        </span>
        <input
          ref={inputRef}
          id={id}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={activeId}
          aria-invalid={invalid || undefined}
          aria-describedby={describedBy}
          autoComplete="off"
          className="rw-combobox__input"
          placeholder={loading ? 'Loading stops…' : placeholder}
          disabled={loading}
          value={inputValue}
          onFocus={openWithFreshQuery}
          onChange={(e) => {
            setTypedQuery(e.target.value)
            setActiveIndex(0)
            if (!open) setOpen(true)
          }}
          onKeyDown={handleKeyDown}
          onBlur={() => setOpen(false)}
        />
        {value && !loading && (
          <button
            type="button"
            className="rw-combobox__clear"
            aria-label={`Clear ${label.toLowerCase()} selection`}
            onMouseDown={(e) => e.preventDefault()}
            onClick={clearSelection}
          >
            ×
          </button>
        )}
      </div>

      {open && !loading && (
        <ul id={listboxId} role="listbox" aria-label={label} className="rw-combobox__listbox">
          {filtered.length === 0 ? (
            <li className="rw-combobox__empty" role="presentation">
              No stops found
            </li>
          ) : (
            filtered.map((stop, index) => (
              <li
                key={stop.stop_id}
                id={`${listboxId}-option-${stop.stop_id}`}
                role="option"
                aria-selected={stop.stop_id === value}
                className={`rw-combobox__option ${index === activeIndex ? 'rw-combobox__option--active' : ''} ${
                  stop.stop_id === value ? 'rw-combobox__option--selected' : ''
                }`}
                onMouseDown={(e) => e.preventDefault()}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => commit(stop)}
              >
                <span className="rw-combobox__option-primary">{stopPrimaryLabel(stop)}</span>
                <span className="rw-combobox__option-secondary">{stopSecondaryLabel(stop)}</span>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  )
}
