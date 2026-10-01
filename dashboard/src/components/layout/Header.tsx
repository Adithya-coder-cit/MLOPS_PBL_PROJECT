import type { AppView } from '../../types/navigation'
import './Header.css'

interface HeaderProps {
  healthLabel: string
  healthOk: boolean
  view: AppView
  onNavigate: (view: AppView) => void
}

const NAV_ITEMS: { view: AppView; label: string }[] = [
  { view: 'journey', label: 'Plan Journey' },
  { view: 'network', label: 'Network Map' },
  { view: 'trips', label: 'My Trips' },
  { view: 'help', label: 'Help' },
]

export function Header({ healthLabel, healthOk, view, onNavigate }: HeaderProps) {
  return (
    <header className="rw-header">
      <button type="button" className="rw-header__identity" onClick={() => onNavigate('journey')} aria-label="RouteWise home">
        <span className="rw-header__mark" aria-hidden="true">
          RW
        </span>
        <span className="rw-header__title">RouteWise</span>
      </button>

      <nav className="rw-header__nav" aria-label="Primary">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.view}
            type="button"
            className={`rw-header__nav-link ${view === item.view ? 'rw-header__nav-link--active' : ''}`}
            aria-current={view === item.view ? 'page' : undefined}
            onClick={() => onNavigate(item.view)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      <div className={`rw-header__health ${healthOk ? 'rw-header__health--ok' : 'rw-header__health--down'}`}>
        <span className="rw-header__dot" aria-hidden="true" />
        {healthLabel}
      </div>
    </header>
  )
}
