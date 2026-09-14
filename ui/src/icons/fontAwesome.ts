import {findIconDefinition, library} from '@fortawesome/fontawesome-svg-core'
import type {IconName, IconPrefix} from '@fortawesome/fontawesome-svg-core'
import {iconPacks, proIcons} from 'virtual:wireloft-font-awesome'
import freeIconFallbacks from './freeIconFallbacks.json'

type FreeIconFallback = {
  prefix: string
  iconName: string
}

/**
 * Pro-only icon references map to visually and semantically similar Font
 * Awesome Free icons here. References include the family prefix so fallbacks
 * can cross families when a Free build does not provide that style directly.
 */
export const FREE_ICON_FALLBACKS = freeIconFallbacks as Readonly<Record<string, FreeIconFallback>>

function parseIconReference(reference: string) {
  const separator = reference.indexOf(':')
  if (separator <= 0 || separator === reference.length - 1) return undefined
  return {
    prefix: reference.slice(0, separator),
    iconName: reference.slice(separator + 1),
  }
}

for (const pack of iconPacks) {
  for (const definition of Object.values(pack)) {
    library.add(definition)
  }
}

if (!proIcons) {
  for (const [proReference, freeReference] of Object.entries(FREE_ICON_FALLBACKS)) {
    const proIcon = parseIconReference(proReference)
    if (!proIcon) {
      console.warn(`Invalid Font Awesome fallback reference '${proReference}'`)
      continue
    }

    const fallback = findIconDefinition({
      prefix: freeReference.prefix as IconPrefix,
      iconName: freeReference.iconName as IconName,
    })
    if (!fallback) {
      console.warn(
        `Font Awesome Free fallback '${freeReference.prefix}:${freeReference.iconName}' for '${proReference}' is unavailable`,
      )
      continue
    }

    library.add({
      ...fallback,
      prefix: proIcon.prefix as IconPrefix,
      iconName: proIcon.iconName as IconName,
    })
  }
}

export const fontAwesomeIconMode = proIcons ? 'pro' : 'free'
