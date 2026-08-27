import {NavLink} from 'react-router-dom'
import {library} from '@fortawesome/fontawesome-svg-core'
import {fas} from '@awesome.me/kit-83fa1ac5a9/icons'
import Footer from './Footer'
import Navbar from './Navbar'
import type { NavItem } from './navTypes'

// Register the kit's solid icon pack so we can reference icons by [prefix, name]
library.add(fas)

const items: NavItem[] = [
    {path: '/', label: 'Home', icon: ['fas', 'house'], end: true},
    {path: '/shows', label: 'Shows', icon: ['fas', 'tv']},
    {path: '/downloads', label: 'Downloads', icon: ['fas', 'circle-down']},
    {
        label: 'Profiles',
        icon: ['fas', 'layer-group'],
        children: [
            { path: '/local-media-profiles', label: 'Local Media Profiles', icon: ['fas', 'clapperboard'] },
            { path: '/download-profiles', label: 'Download Profiles', icon: ['fas', 'download'] },
            { path: '/stream-profiles', label: 'Stream Profiles', icon: ['fas', 'rss'] },
        ]
    },
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
                    <Navbar items={items} />
                </nav>
            </div>
            <Footer wrapperClass="sidebar-footer" />
        </aside>
    )
}
