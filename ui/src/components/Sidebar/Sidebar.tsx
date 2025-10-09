import {NavLink} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {library, IconProp} from '@fortawesome/fontawesome-svg-core'
import {fas} from '@awesome.me/kit-83fa1ac5a9/icons'
import {faGithub} from '@fortawesome/free-brands-svg-icons'

// Register the kit's solid icon pack so we can reference icons by [prefix, name]
library.add(fas)

const items: Array<{ path: string; label: string; icon: IconProp; end?: boolean }> = [
    {path: '/', label: 'Home', icon: ['fas', 'house'], end: true},
    {path: '/profiles', label: 'Media Profiles', icon: ['fas', 'clapperboard']},
    {path: '/settings', label: 'Settings', icon: ['fas', 'gear']},
]

export default function Sidebar() {
    const handleLogout = async () => {
        const base = (window as any).appConfig?.API_URL || '/api'
        try {
            await fetch(`${base}/auth/logout`, {
                method: 'POST',
                credentials: 'include',
            })
        } catch (e) {
            // ignore
        } finally {
            // Reload to trigger auth re-check and show login screen
            window.location.reload()
        }
    }

    return (
        <aside className="sidebar" aria-label="Sidebar">
            <header className="sidebar-header" style={{display: 'flex', justifyContent: 'center', paddingTop: 6}}>
                <span className="brand" style={{display: 'flex', alignItems: 'center', gap: 2}}>
                    <img src="/logo-wide-wireloft.png" alt="WireLoft logo" width={150} style={{borderRadius: 2}} />
                </span>
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
            <footer className="sidebar-footer">
                <div className="footer-links">
                    <a
                        href="https://github.com/samuelvisser/wireloft"
                        target="_blank"
                        rel="noreferrer"
                        className="footer-link"
                    >
                        <span className="icon" aria-hidden>
                          <FontAwesomeIcon icon={faGithub} />
                        </span>
                        <span>Github</span>
                    </a>
                    <button
                        type="button"
                        className="footer-link"
                        onClick={handleLogout}
                        style={{ background: 'none', border: 'none', width: '100%', textAlign: 'left', cursor: 'pointer' }}
                    >
                        <span className="icon" aria-hidden>
                          <FontAwesomeIcon icon={["fas", "right-from-bracket"]} />
                        </span>
                        <span>Logout</span>
                    </button>
                </div>
                <div className="footer-meta" style={{textAlign: 'center'}}>
                    <span className="version" aria-label="App version" style={{color: 'gray'}}>
                    v{(window as any).appConfig?.APP_VERSION ?? 'Unknown app version'}
                    </span>
                </div>
            </footer>
        </aside>
    )
}
