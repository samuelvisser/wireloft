import type { IconProp } from '@fortawesome/fontawesome-svg-core'

export type BaseNav = {
  label: string
  icon: IconProp
}

export type NavLinkItem = BaseNav & {
  path: string
  end?: boolean
  children?: never
}

export type NavSubmenu = BaseNav & {
  children: NavItem[]
  path?: never
}

export type NavItem = NavLinkItem | NavSubmenu
