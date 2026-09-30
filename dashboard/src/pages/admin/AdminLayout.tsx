import type { ReactNode } from 'react'
import type { AdminSection } from '../../types/navigation'
import './AdminLayout.css'

interface AdminLayoutProps {
  section: AdminSection
  onSelectSection: (section: AdminSection) => void
  onExit: () => void
  children: ReactNode
}

const SECTIONS: { section: AdminSection; label: string }[] = [
  { section: 'training', label: 'Training' },
  { section: 'experiments', label: 'Experiments' },
  { section: 'data', label: 'Data' },
  { section: 'evaluation', label: 'Evaluation' },
  { section: 'registry', label: 'Model Registry' },
  { section: 'help', label: 'Help' },
]

export function AdminLayout({ section, onSelectSection, onExit, children }: AdminLayoutProps) {
  return (
    <div className="rw-admin-layout">
      <aside className="rw-admin-layout__sidebar" aria-label="Engineering navigation">
        <button type="button" className="rw-admin-layout__exit" onClick={onExit}>
          ← Back to RouteWise
        </button>
        <nav aria-label="Engineering sections">
          <ul>
            {SECTIONS.map((item) => (
              <li key={item.section}>
                <button
                  type="button"
                  className={`rw-admin-layout__nav-link ${section === item.section ? 'rw-admin-layout__nav-link--active' : ''}`}
                  aria-current={section === item.section ? 'page' : undefined}
                  onClick={() => onSelectSection(item.section)}
                >
                  {item.label}
                </button>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
      <div className="rw-admin-layout__content">{children}</div>
    </div>
  )
}
