import {findIconDefinition, library} from '@fortawesome/fontawesome-svg-core'
import type {IconName, IconPack, IconPrefix} from '@fortawesome/fontawesome-svg-core'
import {iconPacks, proIcons} from 'virtual:wireloft-font-awesome'
import fontAwesomeFamilies from './fontAwesomeFamilies.json'
import freeIconFallbacks from './freeIconFallbacks.json'

type FontAwesomeFamily = {
  prefix: string
  freeFallbackPrefix?: string
}

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

library.add(...iconPacks)

if (!proIcons) {
  const families = fontAwesomeFamilies as readonly FontAwesomeFamily[]
  const packsByPrefix = new Map<string, IconPack>()

  for (const pack of iconPacks) {
    const firstDefinition = Object.values(pack)[0]
    if (firstDefinition) packsByPrefix.set(firstDefinition.prefix, pack)
  }

  // A family can inherit the same-named Free icons from another family. This
  // lets styles such as Regular work in credential-free builds without making
  // page code aware of build mode. Pro builds still use the real family.
  const unresolvedFamilies = new Set(
    families.filter((family) => family.freeFallbackPrefix).map((family) => family.prefix),
  )

  for (let pass = 0; pass < families.length && unresolvedFamilies.size > 0; pass += 1) {
    for (const prefix of [...unresolvedFamilies]) {
      const family = families.find((candidate) => candidate.prefix === prefix)
      const fallbackPrefix = family?.freeFallbackPrefix
      const fallbackPack = fallbackPrefix ? packsByPrefix.get(fallbackPrefix) : undefined
      if (!fallbackPack) continue

      const aliasPack = Object.fromEntries(
        Object.entries(fallbackPack).map(([key, definition]) => [
          key,
          {...definition, prefix: prefix as IconPrefix},
        ]),
      ) as IconPack

      library.add(aliasPack)
      packsByPrefix.set(prefix, aliasPack)
      unresolvedFamilies.delete(prefix)
    }
  }

  for (const prefix of unresolvedFamilies) {
    console.warn(`Font Awesome Free fallback family for '${prefix}' is unavailable`)
  }

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
