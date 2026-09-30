import type { ReactNode } from 'react'
import './Hero.css'

export function Hero({ children }: { children: ReactNode }) {
  return (
    <section className="rw-hero">
      <div className="rw-hero__copy">
        <p className="rw-hero__tagline">Smarter routes. Better journeys.</p>
        <h1 className="rw-hero__title">Plan your journey across the network</h1>
        <p className="rw-hero__subtitle">
          Search any two stops and get intelligent, disruption-aware route recommendations in seconds.
        </p>
      </div>
      {children}
    </section>
  )
}
