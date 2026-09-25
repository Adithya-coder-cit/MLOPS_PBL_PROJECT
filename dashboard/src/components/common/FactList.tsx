import type { ReactNode } from 'react'
import './FactList.css'

export interface Fact {
  label: string
  value: ReactNode
  mono?: boolean
}

export function FactList({ facts }: { facts: Fact[] }) {
  return (
    <dl className="rw-fact-list">
      {facts.map((fact) => (
        <div className="rw-fact-list__row" key={fact.label}>
          <dt>{fact.label}</dt>
          <dd className={fact.mono ? 'data' : undefined}>{fact.value}</dd>
        </div>
      ))}
    </dl>
  )
}
