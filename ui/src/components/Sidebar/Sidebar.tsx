import { NavLink } from 'react-router-dom'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { library, IconProp } from '@fortawesome/fontawesome-svg-core'
import { fas } from '@awesome.me/kit-83fa1ac5a9/icons'

// Register the kit's solid icon pack so we can reference icons by [prefix, name]
library.add(fas)

const items: Array<{ path: string; label: string; icon: IconProp; end?: boolean }> = [
  { path: '/', label: 'Home', icon: ['fas', 'house'], end: true },
  { path: '/profiles', label: 'Media Profiles', icon: ['fas', 'clapperboard'] },
  { path: '/settings', label: 'Settings', icon: ['fas', 'gear'] },
]

export default function Sidebar() {
  return (
    <aside className="sidebar" aria-label="Sidebar">
      <div className="sidebar-inner">
        <nav className="nav" aria-label="Primary">
          {items.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.end}
              className={({ isActive }) => 'nav-item' + (isActive ? ' active' : '')}
            >
              <span className="icon" aria-hidden>
                <FontAwesomeIcon icon={item.icon} />
              </span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
      <footer className="sidebar-footer">
        <span className="brand">WireLoft</span>
      </footer>
    </aside>
  )
}
