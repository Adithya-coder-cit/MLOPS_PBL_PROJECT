import type { ReactNode } from 'react'
import './StatusPill.css'

export type PillTone = 'positive' | 'negative' | 'neutral'

export function StatusPill({ tone, children }: { tone: PillTone; children: ReactNode }) {
  return <span className={`rw-pill rw-pill--${tone}`}>{children}</span>
}
