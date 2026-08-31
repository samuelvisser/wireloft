import {findIconDefinition, library} from '@fortawesome/fontawesome-svg-core'
import type {IconName} from '@fortawesome/fontawesome-svg-core'
import {fas, proIcons} from 'virtual:wireloft-font-awesome'
import freeIconFallbacks from './freeIconFallbacks.json'

/**
 * Pro-only icon names used by WireLoft map to visually and semantically
 * similar Font Awesome Free icons here. The build validator requires every
 * non-Free solid icon reference to have an entry in this data file.
 */
export const FREE_ICON_FALLBACKS: Readonly<Record<string, string>> = freeIconFallbacks

library.add(fas)

if (!proIcons) {
  for (const [proName, freeName] of Object.entries(FREE_ICON_FALLBACKS)) {
    const fallback = findIconDefinition({prefix: 'fas', iconName: freeName as IconName})
    if (!fallback) {
      console.warn(`Font Awesome Free fallback '${freeName}' for '${proName}' is unavailable`)
      continue
    }

    library.add({...fallback, iconName: proName as IconName})
  }
}

export const fontAwesomeIconMode = proIcons ? 'pro' : 'free'
