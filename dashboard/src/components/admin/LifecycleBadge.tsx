import './LifecycleBadge.css'

export function LifecycleBadge({ stage }: { stage: string }) {
  const key = stage.toLowerCase()
  return <span className={`rw-lifecycle-badge rw-lifecycle-badge--${key}`}>{stage}</span>
}
