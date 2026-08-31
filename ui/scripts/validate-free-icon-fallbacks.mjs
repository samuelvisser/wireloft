import {readdir, readFile} from 'node:fs/promises'
import {extname, join} from 'node:path'
import {fileURLToPath} from 'node:url'
import {fas} from '@fortawesome/free-solid-svg-icons'
import freeIconFallbacks from '../src/icons/freeIconFallbacks.json' with {type: 'json'}

const sourceRoot = fileURLToPath(new URL('../src/', import.meta.url))
const sourceExtensions = new Set(['.ts', '.tsx'])
const freeIconNames = new Set(Object.values(fas).map((definition) => definition.iconName))
const fallbackEntries = Object.entries(freeIconFallbacks)

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

function referencedSolidIcons(source) {
  const icons = new Set()
  const fasArray = /\[\s*['"]fas['"]\s*,([\s\S]*?)\]/g

  for (const match of source.matchAll(fasArray)) {
    const iconExpression = match[1]
    const iconName = /['"]([a-z0-9-]+)['"]/g
    for (const nameMatch of iconExpression.matchAll(iconName)) icons.add(nameMatch[1])
  }

  return icons
}

const invalidFallbacks = fallbackEntries.filter(([, freeName]) => !freeIconNames.has(freeName))
if (invalidFallbacks.length) {
  const details = invalidFallbacks.map(([proName, freeName]) => `${proName} -> ${freeName}`).join(', ')
  throw new Error(`Invalid Font Awesome Free fallback(s): ${details}`)
}

const usedIcons = new Set()
for (const file of await sourceFiles(sourceRoot)) {
  const source = await readFile(file, 'utf8')
  for (const iconName of referencedSolidIcons(source)) usedIcons.add(iconName)
}

const missingFallbacks = [...usedIcons]
  .filter((iconName) => !freeIconNames.has(iconName) && !freeIconFallbacks[iconName])
  .sort()

if (missingFallbacks.length) {
  throw new Error(
    `Font Awesome Pro-only icon(s) need Free fallbacks in src/icons/freeIconFallbacks.json: ${missingFallbacks.join(', ')}`,
  )
}

console.log(`Validated ${usedIcons.size} solid icon reference(s); all are Free or have a Free fallback.`)
