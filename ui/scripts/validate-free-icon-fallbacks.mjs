import {readdir, readFile} from 'node:fs/promises'
import {extname, join} from 'node:path'
import {fileURLToPath} from 'node:url'
import fontAwesomeFamilies from '../src/icons/fontAwesomeFamilies.json' with {type: 'json'}
import freeIconFallbacks from '../src/icons/freeIconFallbacks.json' with {type: 'json'}

const sourceRoot = fileURLToPath(new URL('../src/', import.meta.url))
const sourceExtensions = new Set(['.ts', '.tsx'])
const supportedPrefixes = new Set(fontAwesomeFamilies.map((family) => family.prefix))
const freeIconNamesByPrefix = new Map()

for (const family of fontAwesomeFamilies) {
  if (!family.freePackage) continue
  const module = await import(family.freePackage)
  const pack = module[family.freeExport ?? family.proExport]
  freeIconNamesByPrefix.set(
    family.prefix,
    new Set(Object.values(pack).map((definition) => definition.iconName)),
  )
}

// Families without their own Free package may alias another configured Free
// family. This mirrors the runtime registry, so validation and rendering stay
// driven by the same family configuration.
const unresolvedFamilies = new Set(
  fontAwesomeFamilies.filter((family) => family.freeFallbackPrefix).map((family) => family.prefix),
)
for (let pass = 0; pass < fontAwesomeFamilies.length && unresolvedFamilies.size > 0; pass += 1) {
  for (const prefix of [...unresolvedFamilies]) {
    const family = fontAwesomeFamilies.find((candidate) => candidate.prefix === prefix)
    const fallbackNames = family?.freeFallbackPrefix
      ? freeIconNamesByPrefix.get(family.freeFallbackPrefix)
      : undefined
    if (!fallbackNames) continue

    freeIconNamesByPrefix.set(prefix, new Set(fallbackNames))
    unresolvedFamilies.delete(prefix)
  }
}

if (unresolvedFamilies.size) {
  throw new Error(
    `Font Awesome family/families have unavailable Free fallback families: ${[...unresolvedFamilies].sort().join(', ')}`,
  )
}

async function sourceFiles(directory) {
  const entries = await readdir(directory, {withFileTypes: true})
  const files = []

  for (const entry of entries) {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) files.push(...await sourceFiles(path))
    else if (sourceExtensions.has(extname(entry.name))) files.push(path)
  }

  return files
}

function referencedIcons(source) {
  const icons = new Set()

  for (const prefix of supportedPrefixes) {
    const tuple = new RegExp(`\\[\\s*['\"]${prefix}['\"]\\s*,([\\s\\S]*?)\\]`, 'g')
    for (const match of source.matchAll(tuple)) {
      const iconExpression = match[1]
      const iconName = /['\"]([a-z0-9-]+)['\"]/g
      for (const nameMatch of iconExpression.matchAll(iconName)) {
        icons.add(`${prefix}:${nameMatch[1]}`)
      }
    }
  }

  return icons
}

function parseReference(reference) {
  const separator = reference.indexOf(':')
  if (separator <= 0 || separator === reference.length - 1) return undefined
  return {
    prefix: reference.slice(0, separator),
    iconName: reference.slice(separator + 1),
  }
}

const invalidFallbacks = []
for (const [proReference, freeReference] of Object.entries(freeIconFallbacks)) {
  const proIcon = parseReference(proReference)
  const targetNames = freeIconNamesByPrefix.get(freeReference.prefix)

  if (!proIcon || !supportedPrefixes.has(proIcon.prefix)) {
    invalidFallbacks.push(`${proReference} -> unsupported source family`)
  } else if (!targetNames?.has(freeReference.iconName)) {
    invalidFallbacks.push(
      `${proReference} -> ${freeReference.prefix}:${freeReference.iconName} (unavailable)`,
    )
  }
}

if (invalidFallbacks.length) {
  throw new Error(`Invalid Font Awesome Free fallback(s): ${invalidFallbacks.join(', ')}`)
}

const usedIcons = new Set()
for (const file of await sourceFiles(sourceRoot)) {
  const source = await readFile(file, 'utf8')
  for (const iconReference of referencedIcons(source)) usedIcons.add(iconReference)
}

const missingFallbacks = [...usedIcons]
  .filter((reference) => {
    const icon = parseReference(reference)
    if (!icon) return true
    return !freeIconNamesByPrefix.get(icon.prefix)?.has(icon.iconName) && !freeIconFallbacks[reference]
  })
  .sort()

if (missingFallbacks.length) {
  throw new Error(
    `Font Awesome Pro-only icon(s) need Free fallbacks in src/icons/freeIconFallbacks.json: ${missingFallbacks.join(', ')}`,
  )
}

console.log(
  `Validated ${usedIcons.size} icon reference(s) across ${supportedPrefixes.size} configured Font Awesome family/families; all are Free or have a Free fallback.`,
)
