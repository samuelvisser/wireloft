import {useEffect, useMemo, useRef, useState} from 'react'
import {NavLink, useLocation} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import type {IconProp} from '@fortawesome/fontawesome-svg-core'
import type { NavItem } from './navTypes'

export type SubmenuProps = {
  label: string
  icon: IconProp
  items: NavItem[]
}

function flattenPaths(items: NavItem[]): string[] {
  const acc: string[] = []
  for (const it of items) {
    if ('children' in it && it.children) {
      acc.push(...flattenPaths(it.children))
    } else if ('path' in it && it.path) {
      acc.push(it.path)
    }
  }
  return acc
}

export default function Submenu({label, icon, items}: SubmenuProps) {
  const location = useLocation()
  const allPaths = useMemo(() => flattenPaths(items), [items])
  const isAnyActive = useMemo(() => allPaths.some(p => location.pathname.startsWith(p)), [allPaths, location.pathname])
  const [open, setOpen] = useState<boolean>(isAnyActive)
  const panelRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (isAnyActive) setOpen(true)
  }, [isAnyActive])

  // Close on outside click for mobile dropdown
  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!panelRef.current) return
      if (!panelRef.current.contains(e.target as Node)) {
        // do not close if clicking on toggle button (handled separately)
        const toggle = panelRef.current.previousElementSibling as HTMLElement | null
        if (toggle && toggle.contains(e.target as Node)) return
        setOpen(false)
      }
    }

    // Use 'click' so navigation/toggles run first
    if (open) document.addEventListener('click', onDocClick)
    return () => document.removeEventListener('click', onDocClick)
  }, [open])

  return (
    <div className={'submenu' + (open ? ' open' : '')}>
      <button
        className={'nav-item submenu-toggle' + (isAnyActive ? ' active' : '')}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen(v => !v)}
        type="button"
      >
        <span className="icon" aria-hidden>
          <FontAwesomeIcon icon={icon} />
        </span>
        <span className="submenu-label">{label}</span>
        <span className="submenu-caret" aria-hidden>
          <FontAwesomeIcon icon={["fas", "chevron-down"]} />
        </span>
      </button>

      <div ref={panelRef} className="submenu-items" role="menu" aria-label={label + ' submenu'}>
        {items.map((item) => {
          if ('children' in item && item.children) {
            return (
              <Submenu key={item.label} label={item.label} icon={item.icon} items={item.children} />
            )
          }
          return (
            <NavLink key={item.path} to={item.path} className={({isActive}) => 'nav-item child' + (isActive ? ' active' : '')} role="menuitem">
              <span className="icon" aria-hidden>
                <FontAwesomeIcon icon={item.icon} />
              </span>
              <span>{item.label}</span>
            </NavLink>
          )
        })}
      </div>
    </div>
  )
}
