import './Header.css'

interface HeaderProps {
  healthLabel: string
  healthOk: boolean
}

export function Header({ healthLabel, healthOk }: HeaderProps) {
  return (
    <header className="rw-header">
      <div className="rw-header__identity">
        <span className="rw-header__mark" aria-hidden="true">
          RW
        </span>
        <div>
          <h1 className="rw-header__title">RouteWise</h1>
          <p className="rw-header__subtitle">AI-Powered Smart Travel Recommendation System</p>
        </div>
      </div>
      <div className={`rw-header__health ${healthOk ? 'rw-header__health--ok' : 'rw-header__health--down'}`}>
        <span className="rw-header__dot" aria-hidden="true" />
        {healthLabel}
      </div>
    </header>
  )
}
