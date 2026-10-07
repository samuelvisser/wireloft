import {existsSync, readFileSync} from 'node:fs'
import {resolve} from 'node:path'
import {defineConfig, type Plugin} from 'vite'
import react from '@vitejs/plugin-react-swc'
import {fontAwesomeCompiler} from './scripts/font-awesome-compiler.mjs'

const VIRTUAL_VERSION_MODULE = 'virtual:wireloft-version'
const RESOLVED_VIRTUAL_VERSION_MODULE = '\0' + VIRTUAL_VERSION_MODULE

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

function wireLoftVersionPlugin(): Plugin {
  return {
    name: 'wireloft-version',
    resolveId(id) {
      if (id === VIRTUAL_VERSION_MODULE) {
        return RESOLVED_VIRTUAL_VERSION_MODULE
      }
    },
    load(id) {
      if (id !== RESOLVED_VIRTUAL_VERSION_MODULE) return
      return `export const WIRELOFT_VERSION = ${JSON.stringify(readWireLoftVersion())}`
    },
  }
}

// Normal WireLoft development and production builds deliberately use Font Awesome Free.
// The paid kit is opt-in through `npm run dev:pro-icons` / `build:pro-icons`.
export default defineConfig(({mode}) => ({
  plugins: [
    wireLoftVersionPlugin(),
    fontAwesomeCompiler({proIcons: mode === 'pro-icons'}),
    react(),
  ],
}))
