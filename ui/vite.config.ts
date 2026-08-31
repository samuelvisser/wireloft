import {defineConfig, type Plugin} from 'vite'
import react from '@vitejs/plugin-react-swc'

const FONT_AWESOME_VIRTUAL_MODULE = 'virtual:wireloft-font-awesome'
const RESOLVED_FONT_AWESOME_VIRTUAL_MODULE = `\0${FONT_AWESOME_VIRTUAL_MODULE}`
const PRO_ICON_PACKAGE = '@awesome.me/kit-83fa1ac5a9/icons'
const FREE_ICON_PACKAGE = '@fortawesome/free-solid-svg-icons'

function fontAwesomePack(mode: string): Plugin {
  const proIcons = mode === 'pro-icons'
  const iconPackage = proIcons ? PRO_ICON_PACKAGE : FREE_ICON_PACKAGE

  return {
    name: 'wireloft-font-awesome-pack',
    resolveId(id) {
      if (id === FONT_AWESOME_VIRTUAL_MODULE) return RESOLVED_FONT_AWESOME_VIRTUAL_MODULE
      if (!proIcons && id === PRO_ICON_PACKAGE) return RESOLVED_FONT_AWESOME_VIRTUAL_MODULE
    },
    load(id) {
      if (id !== RESOLVED_FONT_AWESOME_VIRTUAL_MODULE) return
      return [
        `export { fas } from ${JSON.stringify(iconPackage)}`,
        `export const proIcons = ${JSON.stringify(proIcons)}`,
      ].join('\n')
    },
  }
}

// Normal WireLoft development and builds deliberately use Font Awesome Free.
// The paid kit is opt-in through `npm run build:pro-icons` / `pro-icons` mode.
export default defineConfig(({mode}) => ({
  plugins: [react(), fontAwesomePack(mode)],
}))
