import type { View } from '../App'

type SidebarProps = {
  currentView: View
  onSelect: (view: View) => void
}

const items: Array<{ id: View; label: string; emoji: string }> = [
  { id: 'home', label: 'Home', emoji: '📊' },
  { id: 'profiles', label: 'Media Profiles', emoji: '💽' },
  { id: 'settings', label: 'Settings', emoji: '⚙️' },
]

export default function Sidebar({ currentView, onSelect }: SidebarProps) {
  return (
    <aside className="sidebar" aria-label="Sidebar">
      <div className="sidebar-inner">
        <nav className="nav" aria-label="Primary">
          {items.map((item) => (
            <button
              key={item.id}
              className={'nav-item' + (currentView === item.id ? ' active' : '')}
              onClick={() => onSelect(item.id)}
              aria-current={currentView === item.id ? 'page' : undefined}
            >
              <span className="icon" aria-hidden>
                {item.emoji}
              </span>
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
      </div>
      <footer className="sidebar-footer">
        <span className="brand">WireLoft</span>
      </footer>
    </aside>
  )
}
