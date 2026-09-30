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
  { view: 'help', label: 'Help' },
]

export function Header({ healthLabel, healthOk, view, onNavigate }: HeaderProps) {
  return (
    <header className="rw-header">
      <div className="rw-header__identity">
        <span className="rw-header__mark" aria-hidden="true">
          RW
        </span>
        <span className="rw-header__title">RouteWise</span>
      </div>

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
        <button
          type="button"
          className="rw-header__nav-link rw-header__nav-link--disabled"
          disabled
          title="My Trips needs saved-journey storage, which this backend doesn't have yet."
        >
          My Trips
        </button>
      </nav>

      <div className={`rw-header__health ${healthOk ? 'rw-header__health--ok' : 'rw-header__health--down'}`}>
        <span className="rw-header__dot" aria-hidden="true" />
        {healthLabel}
      </div>
    </header>
  )
}
