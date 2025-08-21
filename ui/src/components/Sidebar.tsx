import type { View } from '../App'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { library, IconProp } from '@fortawesome/fontawesome-svg-core'
import { fas } from '@awesome.me/kit-83fa1ac5a9/icons'

// Register the kit's solid icon pack so we can reference icons by [prefix, name]
library.add(fas)

type SidebarProps = {
  currentView: View
  onSelect: (view: View) => void
}

const items: Array<{ id: View; label: string; icon: IconProp }> = [
  { id: 'home', label: 'Home', icon: ['fas', 'house'] },
  { id: 'profiles', label: 'Media Profiles', icon: ['fas', 'clapperboard'] },
  { id: 'settings', label: 'Settings', icon: ['fas', 'gear'] },
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
                <FontAwesomeIcon icon={item.icon} />
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
