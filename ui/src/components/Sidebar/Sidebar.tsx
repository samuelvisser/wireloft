import {NavLink} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {library, IconProp} from '@fortawesome/fontawesome-svg-core'
import {fas} from '@awesome.me/kit-83fa1ac5a9/icons'
import Footer from '../Footer'

// Register the kit's solid icon pack so we can reference icons by [prefix, name]
library.add(fas)

const items: Array<{ path: string; label: string; icon: IconProp; end?: boolean }> = [
    {path: '/', label: 'Home', icon: ['fas', 'house'], end: true},
    {path: '/local-media-profiles', label: 'Local Media Profiles', icon: ['fas', 'clapperboard']},
    {path: '/download-profiles', label: 'Download Profiles', icon: ['fas', 'download']},
    {path: '/settings', label: 'Settings', icon: ['fas', 'gear']},
]

export default function Sidebar() {

    return (
        <aside className="sidebar" aria-label="Sidebar">
            <header className="sidebar-header" style={{display: 'flex', justifyContent: 'center', paddingTop: 6}}>
                <NavLink to="/" className="brand" style={{display: 'flex', alignItems: 'center', gap: 2}}>
                    <img src="/logo-wide-wireloft.png" alt="WireLoft logo" width={150} style={{borderRadius: 2}} />
                </NavLink>
            </header>

            <div className="sidebar-inner">
                <nav className="nav" aria-label="Primary">
                    {items.map((item) => (
                        <NavLink
                            key={item.path}
                            to={item.path}
                            end={item.end}
                            className={({isActive}) => 'nav-item' + (isActive ? ' active' : '')}
                        >
              <span className="icon" aria-hidden>
                <FontAwesomeIcon icon={item.icon} />
              </span>
                            <span>{item.label}</span>
                        </NavLink>
                    ))}
                </nav>
            </div>
            <Footer wrapperClass="sidebar-footer" />
        </aside>
    )
}
