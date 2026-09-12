import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import App from './App'
import OperationNotifier from './components/OperationNotifier/OperationNotifier'
import {operationNotificationDefinitions} from './components/OperationNotifier/OperationNotificationDefinitions'
import './index.css'
import './reactSelectMultiselect.css'
import './mobileHeaderScroll.css'
import './icons/fontAwesome'
import { queryClient } from './lib/queryClient'
import { prefetchCoreData } from './lib/queries'
import FrontendPuller from './lib/puller'
import { loadShowsFromStorage, loadProfilesFromStorage } from './lib/cache'
import {
  hydrateCachedSeasonQueries,
  hydrateCurrentShowRouteCache,
  installShowDataQueryPersistence,
  scheduleShowDataCacheWarm,
} from './lib/showDataCacheWarmer'
import { loadAppConfig } from './general_utils.js'
import { loadPublicConfig } from './lib/publicConfig'

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

  // A direct reload of a show route should get its local episode/season data before React mounts.
  // Only that one show's episode cache is parsed here; all other shows remain idle/background work.
  hydrateCurrentShowRouteCache(queryClient)

  // Persist episode/season query results regardless of whether they came from startup warming
  // or a normal page-level background refresh.
  installShowDataQueryPersistence(queryClient)

  // Warm the existing core cache without blocking the first render.
  prefetchCoreData(queryClient)

  const rootEl = document.getElementById('root') as HTMLElement
  createRoot(rootEl).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <Toaster position="top-right" />
        <FrontendPuller>
          <OperationNotifier definitions={operationNotificationDefinitions}>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </OperationNotifier>
        </FrontendPuller>
      </QueryClientProvider>
    </React.StrictMode>,
  )

  // Episode lists can be large, so inspect/fetch them only after the first paint. The warmer
  // checks each show's 24-hour timestamp and uses limited concurrency to avoid slowing the UI.
  scheduleShowDataCacheWarm(queryClient)
}
void bootstrap()
