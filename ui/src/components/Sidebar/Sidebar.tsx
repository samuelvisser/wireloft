import {NavLink} from 'react-router-dom'
import Footer from './Footer'
import Navbar from './Navbar'
import type { NavItem } from './navTypes'
import {faIcon} from '../../icons/faIcon'


const items: NavItem[] = [
    {path: '/', label: 'Home', icon: faIcon('fass', 'house'), end: true},
    {path: '/library', label: 'Library', icon: faIcon('fas', 'books')},
    {path: '/downloads', label: 'Downloads', icon: faIcon('fas', 'circle-down')},
    {
        label: 'Profiles',
        icon: faIcon('fas', 'layer-group'),
        children: [
            { path: '/local-media-profiles', label: 'Local Media Profiles', icon: faIcon('fasr', 'file-video') },
            { path: '/download-profiles', label: 'Download Profiles', icon: faIcon('fas', 'download') },
            { path: '/stream-profiles', label: 'Stream Profiles', icon: faIcon('fas', 'rss') },
        ]
    },
    {
        label: 'Config',
        icon: faIcon('fas', 'sliders'),
        children: [
            {path: '/settings', label: 'Settings', icon: faIcon('fas', 'gear')},
            {path: '/tasks', label: 'Tasks', icon: faIcon('fas', 'bars-progress')},
            {path: '/logs', label: 'Log', icon: faIcon('fas', 'rectangle-history')},
        ],
    },
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
