import type {IconProp} from '@fortawesome/fontawesome-svg-core'

/**
 * Reference a Font Awesome icon by its Kit prefix and icon name.
 *
 * Keep both arguments statically analyzable (literal strings or string
 * conditionals). The Font Awesome compiler validates them and ships only the
 * referenced definitions in production.
 */
export function faIcon(prefix: string, iconName: string): IconProp {
  return [prefix, iconName] as unknown as IconProp
}
