import type { ReactNode } from 'react'
import './StatusStates.css'

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="rw-status rw-status--loading" role="status" aria-live="polite">
      <span className="rw-spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rw-status rw-status--error" role="alert">
      <p>{message}</p>
      {onRetry && (
        <button type="button" className="rw-status__retry" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="rw-status rw-status--empty">
      <p className="rw-status__title">{title}</p>
      {description && <p>{description}</p>}
    </div>
  )
}

export function UnavailableState({ message }: { message: string }) {
  return (
    <div className="rw-status rw-status--unavailable" role="alert">
      <p>{message}</p>
    </div>
  )
}

export function StaleOverlay({ children }: { children: ReactNode }) {
  return (
    <div className="rw-stale" aria-busy="true">
      <div className="rw-stale__badge">Updating…</div>
      <div className="rw-stale__content">{children}</div>
    </div>
  )
}
