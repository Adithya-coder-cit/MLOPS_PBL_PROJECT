import type { ReactNode } from 'react'
import './SectionHeading.css'

export function SectionHeading({ children }: { children: ReactNode }) {
  return <h2 className="rw-section-heading">{children}</h2>
}
