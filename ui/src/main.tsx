import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import App from './App'
import './index.css'
import './reactSelectMultiselect.css'
import './mobileHeaderScroll.css'
import './icons/fontAwesome'
import { queryClient } from './lib/queryClient'
import { prefetchCoreData } from './lib/queries'
import { loadShowsFromStorage, loadProfilesFromStorage } from './lib/cache'
import { loadAppConfig } from './general_utils.js'
import { loadPublicConfig } from './lib/publicConfig'

async function bootstrap() {
  // Load app config before anything renders
  await loadAppConfig()

  // Fetch public config (app settings) before rendering
  await loadPublicConfig()

  // Restore cached data synchronously before initial render to prevent flashes
  const cachedShows = loadShowsFromStorage()
  if (cachedShows) {
    queryClient.setQueryData(['shows'], cachedShows)
  }
  const cachedProfiles = loadProfilesFromStorage()
  if (cachedProfiles) {
    queryClient.setQueryData(['localMediaProfiles'], cachedProfiles)
  }

  // Warm the cache on startup; this will background-refresh the restored data
  prefetchCoreData(queryClient)

  const rootEl = document.getElementById('root') as HTMLElement
  createRoot(rootEl).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <Toaster position="top-right" />
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </React.StrictMode>,
  )
}
void bootstrap()
