import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import './index.css'
import { queryClient } from './lib/queryClient'
import { prefetchCoreData } from './lib/queries'
import { loadShowsFromStorage, loadProfilesFromStorage } from './lib/cache'

// Restore cached data synchronously before initial render to prevent flashes
const cachedShows = loadShowsFromStorage()
if (cachedShows) {
  queryClient.setQueryData(['shows'], cachedShows)
}
const cachedProfiles = loadProfilesFromStorage()
if (cachedProfiles) {
  queryClient.setQueryData(['mediaProfiles'], cachedProfiles)
}

// Warm the cache on startup; this will background-refresh the restored data
prefetchCoreData(queryClient)

const rootEl = document.getElementById('root') as HTMLElement
createRoot(rootEl).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
)
