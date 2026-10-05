import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react-swc'
import {fontAwesomeCompiler} from './scripts/font-awesome-compiler.mjs'

// Normal WireLoft development and production builds deliberately use Font Awesome Free.
// The paid kit is opt-in through `npm run dev:pro-icons` / `build:pro-icons`.
export default defineConfig(({mode}) => ({
  plugins: [
    fontAwesomeCompiler({proIcons: mode === 'pro-icons'}),
    react(),
  ],
}))
