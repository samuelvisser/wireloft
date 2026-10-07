import {existsSync, readFileSync} from 'node:fs'
import {resolve} from 'node:path'
import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react-swc'
import {fontAwesomeCompiler} from './scripts/font-awesome-compiler.mjs'

function readWireLoftVersion(): string {
  const manifestPath = [
    resolve(process.cwd(), '../pyproject.toml'),
    resolve(process.cwd(), 'pyproject.toml'),
  ].find(existsSync)

  if (!manifestPath) {
    throw new Error('Could not find the root WireLoft pyproject.toml')
  }

  const manifest = readFileSync(manifestPath, 'utf8')
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

const wireLoftVersion = readWireLoftVersion()

// Normal WireLoft development and production builds deliberately use Font Awesome Free.
// The paid kit is opt-in through `npm run dev:pro-icons` / `build:pro-icons`.
export default defineConfig(({mode}) => ({
  define: {
    'import.meta.env.VITE_WIRELOFT_VERSION': JSON.stringify(wireLoftVersion),
  },
  plugins: [
    fontAwesomeCompiler({proIcons: mode === 'pro-icons'}),
    react(),
  ],
}))
