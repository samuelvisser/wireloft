import {defineConfig, type Plugin} from 'vite'
import react from '@vitejs/plugin-react-swc'
import fontAwesomeFamilies from './src/icons/fontAwesomeFamilies.json'

const FONT_AWESOME_VIRTUAL_MODULE = 'virtual:wireloft-font-awesome'
const RESOLVED_FONT_AWESOME_VIRTUAL_MODULE = `\0${FONT_AWESOME_VIRTUAL_MODULE}`
const PRO_ICON_PACKAGE = '@awesome.me/kit-83fa1ac5a9/icons'

type FontAwesomeFamily = {
  prefix: string
  proExport: string
  freePackage?: string
  freeExport?: string
  freeFallbackPrefix?: string
}

const FONT_AWESOME_FAMILIES = fontAwesomeFamilies as readonly FontAwesomeFamily[]

function fontAwesomeModuleSource(proIcons: boolean) {
  const imports: string[] = []
  const declarations: string[] = []
  const exports: string[] = []
  const registeredPacks: string[] = []

  FONT_AWESOME_FAMILIES.forEach((family, index) => {
    const localName = `iconPack${index}`

    if (proIcons) {
      imports.push(
        `import { ${family.proExport} as ${localName} } from ${JSON.stringify(PRO_ICON_PACKAGE)}`,
      )
      registeredPacks.push(localName)
    } else if (family.freePackage) {
      imports.push(
        `import { ${family.freeExport ?? family.proExport} as ${localName} } from ${JSON.stringify(family.freePackage)}`,
      )
      registeredPacks.push(localName)
    } else {
      // Keep the named export available in credential-free builds. The runtime
      // registry supplies this family through its configured Free fallback.
      declarations.push(`const ${localName} = {}`)
    }

    // Preserve the kit's named-pack API for the few legacy modules that still
    // import a pack directly. New code should rely on the centralized registry.
    exports.push(`export const ${family.proExport} = ${localName}`)
  })

  return [
    ...imports,
    ...declarations,
    ...exports,
    `export const iconPacks = [${registeredPacks.join(', ')}]`,
    `export const proIcons = ${JSON.stringify(proIcons)}`,
  ].join('\n')
}

function fontAwesomePack(mode: string): Plugin {
  const proIcons = mode === 'pro-icons'

  return {
    name: 'wireloft-font-awesome-pack',
    resolveId(id) {
      if (id === FONT_AWESOME_VIRTUAL_MODULE) return RESOLVED_FONT_AWESOME_VIRTUAL_MODULE
      if (!proIcons && id === PRO_ICON_PACKAGE) return RESOLVED_FONT_AWESOME_VIRTUAL_MODULE
    },
    load(id) {
      if (id !== RESOLVED_FONT_AWESOME_VIRTUAL_MODULE) return
      return fontAwesomeModuleSource(proIcons)
    },
  }
}

// Normal WireLoft development and builds deliberately use Font Awesome Free.
// The paid kit is opt-in through `npm run build:pro-icons` / `pro-icons` mode.
export default defineConfig(({mode}) => ({
  plugins: [react(), fontAwesomePack(mode)],
}))
