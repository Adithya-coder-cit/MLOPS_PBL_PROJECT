import type { ReactNode } from 'react'
import './StatCard.css'

interface StatCardProps {
  title: string
  action?: ReactNode
  children: ReactNode
}

export function StatCard({ title, action, children }: StatCardProps) {
  return (
    <section className="rw-stat-card">
      <header className="rw-stat-card__header">
        <h3>{title}</h3>
        {action}
      </header>
      <div className="rw-stat-card__body">{children}</div>
    </section>
  )
}
