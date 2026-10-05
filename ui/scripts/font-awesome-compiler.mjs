import {readdir, readFile} from 'node:fs/promises'
import {extname, join, relative} from 'node:path'
import {fileURLToPath} from 'node:url'
import ts from 'typescript'

const SOURCE_ROOT = fileURLToPath(new URL('../src/', import.meta.url))
const FALLBACKS_PATH = fileURLToPath(new URL('../src/icons/freeIconFallbacks.json', import.meta.url))
const VIRTUAL_MODULE = 'virtual:font-awesome-registry'
const RESOLVED_VIRTUAL_MODULE = `\0${VIRTUAL_MODULE}`
const PRO_ICON_PACKAGE = '@awesome.me/kit-83fa1ac5a9/icons'
const SOURCE_EXTENSIONS = new Set(['.ts', '.tsx'])
const FREE_PACKS = [
  {
    prefix: 'fas',
    packageName: '@fortawesome/free-solid-svg-icons',
    exportName: 'fas',
  },
  {
    prefix: 'fab',
    packageName: '@fortawesome/free-brands-svg-icons',
    exportName: 'fab',
  },
]

function referenceKey(prefix, iconName) {
  return `${prefix}:${iconName}`
}

function parseReference(reference, description) {
  const separator = reference.indexOf(':')
  if (separator <= 0 || separator === reference.length - 1) {
    throw new Error(`Invalid Font Awesome ${description} '${reference}'. Expected "prefix:icon-name".`)
  }

  return {
    prefix: reference.slice(0, separator),
    iconName: reference.slice(separator + 1),
  }
}

async function sourceFiles(directory = SOURCE_ROOT) {
  const entries = await readdir(directory, {withFileTypes: true})
  const files = []

  for (const entry of entries) {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) {
      files.push(...await sourceFiles(path))
      continue
    }

    if (!entry.name.endsWith('.d.ts') && SOURCE_EXTENSIONS.has(extname(entry.name))) files.push(path)
  }

  return files.sort()
}

function sourceLocation(sourceFile, node) {
  const position = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile))
  return `${relative(SOURCE_ROOT, sourceFile.fileName)}:${position.line + 1}:${position.character + 1}`
}

function literalStrings(expression) {
  if (ts.isStringLiteralLike(expression)) return [expression.text]
  if (ts.isParenthesizedExpression(expression)) return literalStrings(expression.expression)
  if (ts.isAsExpression(expression) || ts.isTypeAssertionExpression(expression) || ts.isNonNullExpression(expression)) {
    return literalStrings(expression.expression)
  }
  if (ts.isConditionalExpression(expression)) {
    const values = [
      ...literalStrings(expression.whenTrue),
      ...literalStrings(expression.whenFalse),
    ]
    return [...new Set(values)]
  }

  return []
}

async function scanIconReferences(files) {
  const references = new Map()
  const errors = []

  for (const file of files) {
    const source = await readFile(file, 'utf8')
    const scriptKind = file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS
    const sourceFile = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, scriptKind)

    function visit(node) {
      if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)) {
        const moduleName = node.moduleSpecifier.text
        if (
          moduleName.startsWith('@awesome.me/')
          || /^@fortawesome\/(?:free|pro)-.*-svg-icons$/.test(moduleName)
        ) {
          errors.push(
            `${sourceLocation(sourceFile, node)} imports '${moduleName}' directly. `
            + 'Application code must use faIcon(prefix, iconName); icon packs are compiler-only.',
          )
        }
      }

      if (
        ts.isCallExpression(node)
        && ts.isIdentifier(node.expression)
        && node.expression.text === 'faIcon'
      ) {
        if (node.arguments.length !== 2) {
          errors.push(`${sourceLocation(sourceFile, node)} faIcon() requires exactly a prefix and icon name.`)
        } else {
          const prefixes = literalStrings(node.arguments[0])
          const iconNames = literalStrings(node.arguments[1])

          if (!prefixes.length || !iconNames.length) {
            errors.push(
              `${sourceLocation(sourceFile, node)} faIcon() arguments must be statically analyzable strings `
              + 'or conditional expressions whose branches are strings.',
            )
          } else {
            for (const prefix of prefixes) {
              for (const iconName of iconNames) {
                const key = referenceKey(prefix, iconName)
                const locations = references.get(key) ?? []
                locations.push(sourceLocation(sourceFile, node))
                references.set(key, locations)
              }
            }
          }
        }
      }

      ts.forEachChild(node, visit)
    }

    visit(sourceFile)
  }

  if (errors.length) {
    throw new Error(['Font Awesome source validation failed:', ...errors.map((error) => `- ${error}`)].join('\n'))
  }

  return references
}

async function loadFallbacks() {
  const raw = JSON.parse(await readFile(FALLBACKS_PATH, 'utf8'))
  const fallbacks = new Map()

  for (const [source, target] of Object.entries(raw)) {
    parseReference(source, 'fallback source')
    if (typeof target !== 'string') {
      throw new Error(`Invalid Font Awesome fallback for '${source}'. Expected a "prefix:icon-name" string.`)
    }
    parseReference(target, 'fallback target')
    fallbacks.set(source, target)
  }

  return fallbacks
}

function packByName(pack, description) {
  if (!pack || typeof pack !== 'object') {
    throw new Error(`Font Awesome package did not expose the expected ${description} icon pack.`)
  }

  const icons = new Map()
  for (const definition of Object.values(pack)) {
    if (
      definition
      && typeof definition === 'object'
      && typeof definition.iconName === 'string'
      && typeof definition.prefix === 'string'
      && Array.isArray(definition.icon)
    ) {
      icons.set(definition.iconName, definition)
    }
  }
  return icons
}

async function loadFreeIcons() {
  const byPrefix = new Map()

  for (const config of FREE_PACKS) {
    const module = await import(config.packageName)
    byPrefix.set(
      config.prefix,
      packByName(module[config.exportName], `${config.prefix} Free`),
    )
  }

  return byPrefix
}

async function loadProIcons() {
  let module
  try {
    module = await import(PRO_ICON_PACKAGE)
  } catch (error) {
    throw new Error(
      `Font Awesome Pro mode requires the optional paid Kit package '${PRO_ICON_PACKAGE}'. `
      + 'Install dependencies with Font Awesome credentials before using dev:pro-icons or build:pro-icons.',
      {cause: error},
    )
  }

  const byPrefixAndName = module.byPrefixAndName
  if (!byPrefixAndName || typeof byPrefixAndName !== 'object') {
    throw new Error(`The paid Font Awesome Kit did not expose byPrefixAndName from '${PRO_ICON_PACKAGE}'.`)
  }

  return byPrefixAndName
}

function aliasDefinition(definition, requestedPrefix, requestedName) {
  if (definition.prefix === requestedPrefix && definition.iconName === requestedName) return definition

  return {
    ...definition,
    prefix: requestedPrefix,
    iconName: requestedName,
  }
}

function referenceLocations(references, key) {
  return (references.get(key) ?? []).join(', ')
}

function resolveProDefinition(byPrefixAndName, prefix, iconName, references) {
  const definition = byPrefixAndName[prefix]?.[iconName]
  if (!definition) {
    const key = referenceKey(prefix, iconName)
    throw new Error(
      `Font Awesome Pro icon '${key}' is not present in the installed Kit. Referenced at ${referenceLocations(references, key)}.`,
    )
  }

  return definition
}

function resolveExactFreeDefinition(freeIcons, reference, description) {
  const {prefix, iconName} = parseReference(reference, description)
  const definition = freeIcons.get(prefix)?.get(iconName)
  if (!definition) {
    throw new Error(
      `Font Awesome Free fallback '${reference}' is unavailable. `
      + `Free compiler families are: ${[...freeIcons.keys()].join(', ')}.`,
    )
  }

  return definition
}

function resolveFreeDefinition(freeIcons, fallbacks, prefix, iconName, references) {
  const key = referenceKey(prefix, iconName)
  const exact = freeIcons.get(prefix)?.get(iconName)
  if (exact) return {definition: exact, fallback: false}

  const configuredFallback = fallbacks.get(key)
  if (configuredFallback) {
    const definition = resolveExactFreeDefinition(
      freeIcons,
      configuredFallback,
      `fallback target for '${key}'`,
    )
    return {
      definition: aliasDefinition(definition, prefix, iconName),
      fallback: true,
    }
  }

  // Most paid styles have a semantically identical Free Solid icon. Prefer
  // that automatically so the fallback file only contains real exceptions.
  const sameNameSolid = freeIcons.get('fas')?.get(iconName)
  if (sameNameSolid) {
    return {
      definition: aliasDefinition(sameNameSolid, prefix, iconName),
      fallback: true,
    }
  }

  throw new Error(
    `Font Awesome icon '${key}' has no Free equivalent or configured fallback. `
    + `Referenced at ${referenceLocations(references, key)}. `
    + `Add an entry to src/icons/freeIconFallbacks.json, for example "${key}": "fas:some-free-icon".`,
  )
}

function validateConfiguredFallbacks(freeIcons, fallbacks) {
  for (const [source, target] of fallbacks) {
    parseReference(source, 'fallback source')
    resolveExactFreeDefinition(freeIcons, target, `fallback target for '${source}'`)
  }
}

async function compileFontAwesome({proIcons, files}) {
  const references = await scanIconReferences(files)
  const definitions = []
  let fallbackCount = 0

  if (proIcons) {
    const byPrefixAndName = await loadProIcons()
    for (const key of [...references.keys()].sort()) {
      const {prefix, iconName} = parseReference(key, 'source reference')
      definitions.push(resolveProDefinition(byPrefixAndName, prefix, iconName, references))
    }
  } else {
    const [freeIcons, fallbacks] = await Promise.all([loadFreeIcons(), loadFallbacks()])
    validateConfiguredFallbacks(freeIcons, fallbacks)

    for (const key of [...references.keys()].sort()) {
      const {prefix, iconName} = parseReference(key, 'source reference')
      const resolved = resolveFreeDefinition(freeIcons, fallbacks, prefix, iconName, references)
      definitions.push(resolved.definition)
      if (resolved.fallback) fallbackCount += 1
    }
  }

  const mode = proIcons ? 'pro' : 'free'
  const fallbackSummary = proIcons ? '' : `, ${fallbackCount} fallback(s)`
  console.log(
    `[font-awesome] ${mode}: ${references.size} referenced icon(s), ${definitions.length} bundled definition(s)${fallbackSummary}.`,
  )

  return [
    `export const icons = ${JSON.stringify(definitions)}`,
    `export const proIcons = ${JSON.stringify(proIcons)}`,
  ].join('\n')
}

export function fontAwesomeCompiler({proIcons = false} = {}) {
  let compiledSource = null
  let watchedFiles = []

  async function rebuild() {
    watchedFiles = await sourceFiles()
    compiledSource = await compileFontAwesome({proIcons, files: watchedFiles})
    return compiledSource
  }

  function isRelevantFile(file) {
    return file === FALLBACKS_PATH
      || (file.startsWith(SOURCE_ROOT) && SOURCE_EXTENSIONS.has(extname(file)) && !file.endsWith('.d.ts'))
  }

  return {
    name: 'font-awesome-compiler',
    enforce: 'pre',

    async buildStart() {
      await rebuild()
      for (const file of watchedFiles) this.addWatchFile(file)
      this.addWatchFile(FALLBACKS_PATH)
    },

    resolveId(id) {
      if (id === VIRTUAL_MODULE) return RESOLVED_VIRTUAL_MODULE
    },

    async load(id) {
      if (id !== RESOLVED_VIRTUAL_MODULE) return
      return compiledSource ?? rebuild()
    },

    handleHotUpdate(context) {
      if (!isRelevantFile(context.file)) return

      compiledSource = null
      const virtualModule = context.server.moduleGraph.getModuleById(RESOLVED_VIRTUAL_MODULE)
      if (virtualModule) context.server.moduleGraph.invalidateModule(virtualModule)

      // Source edits can add a previously unseen icon. A full reload keeps the
      // registry and the edited module in lock-step without loading whole packs.
      context.server.ws.send({type: 'full-reload', path: '*'})
      return []
    },
  }
}
