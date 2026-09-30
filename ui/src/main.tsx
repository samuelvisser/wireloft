import React from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import './index.css'
import './reactSelectMultiselect.css'
import './mobileHeaderScroll.css'
import './icons/fontAwesome'
import { queryClient } from './lib/queryClient'
import { prefetchCoreData } from './lib/queries'
import { loadShowsFromStorage, loadProfilesFromStorage } from './lib/cache'
import {
  hydrateCachedSeasonQueries,
  hydrateCurrentShowRouteCache,
  installShowDataQueryPersistence,
  scheduleShowDataCacheWarm,
} from './lib/showDataCacheWarmer'
import { loadAppConfig } from './general_utils.js'
import { loadPublicConfig } from './lib/publicConfig'
import { router } from './router'

async function bootstrap() {
  // Load app config before anything renders
  await loadAppConfig()

  // Public config only contains auxiliary frontend metadata. A temporary API
  // failure must not prevent React from mounting and leave the page blank.
  try {
    await loadPublicConfig()
  } catch (error) {
    console.error('[publicConfig] Failed to load public config during bootstrap', error)
  }

  // Restore cached data synchronously before initial render to prevent flashes.
  const cachedShows = loadShowsFromStorage()
  if (cachedShows) {
    queryClient.setQueryData(['shows'], cachedShows)
    // Season lists are small and seasonal show pages need them before rendering episode cards.
    // Hydrating them now avoids a skeleton gate without parsing every potentially-large episode list.
    hydrateCachedSeasonQueries(queryClient, cachedShows)
  }
  const cachedProfiles = loadProfilesFromStorage()
  if (cachedProfiles) {
    queryClient.setQueryData(['localMediaProfiles'], cachedProfiles)
  }

  // A direct reload of a seasonal show should get its small cached season list before React mounts.
  // Episode previews are read lazily by ShowPage so startup never parses unrelated episode data.
  hydrateCurrentShowRouteCache(queryClient)

  // Persist small season-query results produced by normal foreground refreshes.
  installShowDataQueryPersistence(queryClient)

  // Warm the existing core cache without blocking the first render.
  prefetchCoreData(queryClient)

  const rootEl = document.getElementById('root') as HTMLElement
  createRoot(rootEl).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <Toaster position="top-right" />
        <RouterProvider router={router} />
      </QueryClientProvider>
    </React.StrictMode>,
  )

  // Warm only the latest five episodes per stale show after first paint, with limited concurrency.
  scheduleShowDataCacheWarm(queryClient)
}
void bootstrap()
