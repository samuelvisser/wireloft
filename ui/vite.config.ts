import {existsSync, readFileSync} from 'node:fs'
import {resolve} from 'node:path'
import {defineConfig, type Plugin} from 'vite'
import react from '@vitejs/plugin-react-swc'
import {fontAwesomeCompiler} from './scripts/font-awesome-compiler.mjs'

function findWireLoftManifest(): string {
  const manifestPath = [
    resolve(process.cwd(), '../pyproject.toml'),
    resolve(process.cwd(), 'pyproject.toml'),
  ].find(existsSync)

  if (!manifestPath) {
    throw new Error('Could not find the root WireLoft pyproject.toml')
  }
  return manifestPath
}

const wireLoftManifest = findWireLoftManifest()

function readWireLoftVersion(): string {
  const manifest = readFileSync(wireLoftManifest, 'utf8')
  const projectStart = manifest.indexOf('[project]')
  if (projectStart < 0) {
    throw new Error('Root pyproject.toml does not define a [project] section')
  }

  const afterProjectHeader = manifest.slice(projectStart + '[project]'.length)
  const nextSection = afterProjectHeader.search(/^\[[^\]]+\]\s*$/m)
  const projectSection = nextSection >= 0
    ? afterProjectHeader.slice(0, nextSection)
    : afterProjectHeader
  const version = projectSection.match(/^\s*version\s*=\s*["']([^"']+)["']\s*$/m)?.[1]

  if (!version) {
    throw new Error('Root pyproject.toml does not define [project].version')
  }
  return version
}

function restartDevServerOnVersionChange(): Plugin {
  return {
    name: 'wireloft-version-reload',
    configureServer(server) {
      // The application manifest lives outside Vite's normal UI root. Watch it
      // explicitly so a development version bump cannot leave the old version
      // baked into the running dev server.
      server.watcher.add(wireLoftManifest)
    },
    async handleHotUpdate({file, server}) {
      if (resolve(file) !== wireLoftManifest) return

      // Restarting reloads this config and therefore recomputes the value below.
      // The browser can then reload against a frontend and backend that agree.
      await server.restart()
      return []
    },
  }
}

const wireLoftVersion = readWireLoftVersion()

// Normal WireLoft development and production builds deliberately use Font Awesome Free.
// The paid kit is opt-in through `npm run dev:pro-icons` / `build:pro-icons`.
export default defineConfig(({mode}) => ({
  define: {
    'import.meta.env.VITE_WIRELOFT_VERSION': JSON.stringify(wireLoftVersion),
  },
  plugins: [
    restartDevServerOnVersionChange(),
    fontAwesomeCompiler({proIcons: mode === 'pro-icons'}),
    react(),
  ],
}))
